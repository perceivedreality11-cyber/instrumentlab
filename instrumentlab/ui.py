"""Tk desktop UI. Acquisition, sockets, DSP and storage run outside Tk's thread."""

from collections import deque
from dataclasses import replace
from pathlib import Path
import queue
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .analysis import linear_calibration
from .config import AcquisitionConfig
from .drivers import SimulatedInstrument, TCPInstrument
from .engine import AcquisitionEngine
from .storage import export_csv


BG = "#0b1120"
PANEL = "#111c2e"
INPUT = "#19273b"
GRID = "#233249"
TEXT = "#e3ecf8"
MUTED = "#8fa4bd"
TEAL = "#40dfb6"
BLUE = "#61a7ff"
AMBER = "#ffbc63"
RED = "#ff7588"
FONT = "Microsoft YaHei UI"
SCENARIOS = {"稳定正弦": "normal", "周期过载": "overload", "三次谐波": "harmonic", "零点漂移": "drift"}


class Plot(tk.Canvas):
    def __init__(self, parent, title, subtitle, color):
        super().__init__(parent, bg=PANEL, highlightthickness=0, height=240)
        self.title, self.subtitle, self.color = title, subtitle, color
        self.values = []
        self.xmax, self.ymax, self.bipolar = 1, 5, True
        self.threshold = None
        self.bind("<Configure>", lambda event: self.draw())

    def set_data(self, values, xmax, ymax, bipolar=True, threshold=None):
        self.values, self.xmax, self.ymax = values, xmax, max(ymax, 0.01)
        self.bipolar, self.threshold = bipolar, threshold
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 120 or h < 90:
            return
        self.create_text(20, 21, text=self.title, fill=TEXT, anchor="w", font=(FONT, 11, "bold"))
        self.create_text(w - 20, 21, text=self.subtitle, fill=MUTED, anchor="e", font=(FONT, 9))
        left, top, right, bottom = 62, 53, w - 23, h - 33
        ymin = -self.ymax if self.bipolar else 0
        span = self.ymax - ymin
        for i in range(5):
            y = top + (bottom - top) * i / 4
            value = self.ymax - span * i / 4
            self.create_line(left, y, right, y, fill=GRID, dash=(2, 4))
            self.create_text(left - 10, y, text=f"{value:.1f}", fill=MUTED, anchor="e", font=(FONT, 8))
        for i in range(6):
            x = left + (right - left) * i / 5
            self.create_line(x, top, x, bottom, fill=GRID, dash=(2, 4))
            self.create_text(x, bottom + 18, text=f"{self.xmax * i / 5:.0f}", fill=MUTED, font=(FONT, 8))
        def ycoord(value):
            return top + (self.ymax - max(ymin, min(self.ymax, value))) / span * (bottom - top)
        if self.threshold is not None and self.threshold < self.ymax:
            for threshold in (self.threshold, -self.threshold):
                if threshold >= ymin:
                    self.create_line(left, ycoord(threshold), right, ycoord(threshold), fill=AMBER, dash=(5, 5))
        if len(self.values) > 1:
            coords = []
            for i, value in enumerate(self.values):
                coords.extend((left + i / (len(self.values) - 1) * (right - left), ycoord(value)))
            self.create_line(*coords, fill=self.color, width=1.8)
        else:
            self.create_text((left + right) / 2, (top + bottom) / 2, text="等待采集数据",
                             fill=MUTED, font=(FONT, 12))


class InstrumentApp:
    def __init__(self, root, data_dir="data"):
        self.root = root
        self.data_dir = Path(data_dir)
        self.engine = None
        self.last_database = None
        self.calibration = (1.0, 0.0)
        self.wave = deque(maxlen=512)
        self.closing = False
        self.last_frame = None
        self.config_widgets = []
        self.root.title("InstrumentLab | 智能仪器采集与分析平台")
        self.root.geometry("1420x900")
        self.root.minsize(1160, 800)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._styles()
        self._build()
        self._log("READY", "工作站就绪；仿真模式无需连接硬件")
        self.root.after(60, self.poll)

    def _styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT,
                        foreground=TEXT, arrowcolor=MUTED, bordercolor=GRID, padding=2)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT)],
                  foreground=[("readonly", TEXT), ("disabled", MUTED)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=MUTED, borderwidth=0, rowheight=26, font=(FONT, 9))
        style.configure("Treeview.Heading", background=INPUT, foreground=TEXT,
                        font=(FONT, 9), relief="flat")
        style.map("Treeview", background=[("selected", GRID)])

    def label(self, parent, text, size=10, color=TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=(FONT, size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=TEAL if primary else INPUT,
                         fg=BG if primary else TEXT, activebackground=BLUE, activeforeground=BG,
                         font=(FONT, 10, "bold"), relief="flat", bd=0, cursor="hand2", pady=6,
                         disabledforeground=MUTED)

    def field(self, parent, label, value, choices=None):
        self.label(parent, label, 9, MUTED).pack(anchor="w", pady=(4, 2))
        var = tk.StringVar(value=str(value))
        if choices:
            widget = ttk.Combobox(parent, textvariable=var, values=choices, state="readonly",
                                  font=(FONT, 10))
        else:
            widget = tk.Entry(parent, textvariable=var, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=(FONT, 11), highlightthickness=1,
                              highlightbackground=GRID, highlightcolor=TEAL,
                              disabledbackground=INPUT, disabledforeground=MUTED)
        widget.pack(fill="x")
        self.config_widgets.append((widget, "readonly" if choices else "normal"))
        return var

    def _build(self):
        sidebar = tk.Frame(self.root, bg=PANEL, width=264)
        sidebar.pack(side="left", fill="y", padx=(0, 20))
        sidebar.pack_propagate(False)
        self.label(sidebar, "◈  InstrumentLab", 19, TEAL, True).pack(anchor="w", padx=22, pady=(18, 4))
        self.label(sidebar, "MEASUREMENT WORKSTATION", 8, MUTED).pack(anchor="w", padx=24)
        controls = tk.Frame(sidebar, bg=PANEL)
        controls.pack(fill="x", padx=24, pady=(10, 0))
        self.label(controls, "01  /  采集配置", 11, TEXT, True).pack(anchor="w", pady=(0, 2))
        self.mode = self.field(controls, "设备来源", "内置信号仿真", ["内置信号仿真", "TCP 仪器"])
        self.host = self.field(controls, "TCP 地址  ·  host:port", "127.0.0.1:5025")
        self.rate = self.field(controls, "采样率  /  Hz", "1024", ["512", "1024", "2048", "4096"])
        self.frequency = self.field(controls, "仿真频率  /  Hz", "50")
        self.amplitude = self.field(controls, "仿真幅值  /  V peak", "2.0")
        self.scenario = self.field(controls, "仿真场景", "稳定正弦", list(SCENARIOS))
        self.threshold = self.field(controls, "峰值告警阈值  /  V", "3.0")
        self.label(controls, "固定回差 0.3 V · 连续 2 帧确认", 8, MUTED).pack(anchor="w", pady=(6, 13))
        self.start_button = self.button(controls, "▶   开始采集", self.start, True)
        self.start_button.pack(fill="x")
        self.stop_button = self.button(controls, "■   停止并保存", self.stop)
        self.stop_button.pack(fill="x", pady=(8, 0))
        self.stop_button.configure(state="disabled")
        self.cal_button = self.button(controls, "线性标定工具", self.calibrate)
        self.cal_button.pack(fill="x", pady=(8, 0))
        self.export_button = self.button(controls, "导出本次 CSV", self.export)
        self.export_button.pack(fill="x", pady=(8, 0))
        self.export_button.configure(state="disabled")
        self.label(sidebar, "v1.0.0  /  单通道电压采集", 8, MUTED,
                   justify="left").pack(side="bottom", anchor="w", padx=24, pady=12)

        main = tk.Frame(self.root, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=(0, 22), pady=(24, 18))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1, minsize=140)
        main.rowconfigure(4, weight=1, minsize=140)
        header = tk.Frame(main, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.label(header, "采集工作站", 23, TEXT, True).pack(side="left")
        self.state_label = self.label(header, "●  READY", 11, MUTED, True)
        self.state_label.pack(side="right", pady=8)
        info = tk.Frame(main, bg=BG)
        info.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        self.device_label = self.label(info, "VIRTUAL DAQ  /  CH 01  /  电压", 9, MUTED)
        self.device_label.pack(side="left")
        self.record_label = self.label(info, "256 samples / block · SQLite 自动录制", 9, MUTED)
        self.record_label.pack(side="right")
        cards = tk.Frame(main, bg=BG)
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self.metrics_labels = {}
        for index, (key, title, unit, color) in enumerate([
                ("rms", "有效值 RMS", "V", TEAL), ("peak_to_peak", "峰峰值 Vpp", "V", BLUE),
                ("dominant_hz", "主频估计", "Hz", TEXT), ("peak", "绝对峰值", "V", AMBER)]):
            card = tk.Frame(cards, bg=PANEL, padx=18, pady=14)
            card.grid(row=0, column=index, sticky="ew", padx=(0, 12 if index < 3 else 0))
            cards.columnconfigure(index, weight=1, uniform="cards")
            self.label(card, title, 9, MUTED).pack(anchor="w")
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", pady=(7, 0))
            value = self.label(row, "—", 26, color, True)
            value.pack(side="left")
            self.label(row, unit, 10, MUTED).pack(side="left", padx=(7, 0), pady=(12, 0))
            self.metrics_labels[key] = value
        self.wave_plot = Plot(main, "时域波形", "V  /  ms  ·  最近 512 点", TEAL)
        self.wave_plot.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        self.spectrum_plot = Plot(main, "幅度频谱", "V peak  /  Hz  ·  Hann 窗", BLUE)
        self.spectrum_plot.grid(row=4, column=0, sticky="nsew", pady=(0, 12))
        status = tk.Frame(main, bg=PANEL, padx=15, pady=11)
        status.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        self.diagnosis = self.label(status, "状态分析  /  等待首帧数据", 10, TEAL)
        self.diagnosis.pack(side="left")
        self.counter = self.label(status, "00:00  ·  0 samples", 9, MUTED)
        self.counter.pack(side="right")
        self.events = ttk.Treeview(main, columns=("time", "kind", "detail"), show="headings", height=4)
        for key, title, width in [("time", "时间 / s", 95), ("kind", "事件", 115), ("detail", "采集事件与记录", 600)]:
            self.events.heading(key, text=title)
            self.events.column(key, width=width, stretch=key == "detail")
        self.events.tag_configure("ALARM", foreground=RED)
        self.events.tag_configure("RECOVERED", foreground=TEAL)
        self.events.tag_configure("ERROR", foreground=RED)
        self.events.grid(row=6, column=0, sticky="ew")

    def _log(self, kind, detail, time_s=0):
        self.events.insert("", "end", values=(f"{time_s:.2f}", kind, detail), tags=(kind,))
        children = self.events.get_children()
        if len(children) > 200:
            self.events.delete(children[0])
        self.events.yview_moveto(1)

    def _lock(self, running):
        for widget, normal in self.config_widgets:
            widget.configure(state="disabled" if running else normal)
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.cal_button.configure(state="disabled" if running else "normal")
        self.export_button.configure(state="normal" if not running and self.last_database else "disabled")

    def start(self):
        if self.engine and self.engine.running:
            return
        try:
            config = AcquisitionConfig(sample_rate=int(self.rate.get()), frequency=float(self.frequency.get()),
                                       amplitude=float(self.amplitude.get()), scenario=SCENARIOS[self.scenario.get()],
                                       alarm_high=float(self.threshold.get()), gain=self.calibration[0],
                                       offset=self.calibration[1]).validate()
            if self.mode.get() == "TCP 仪器":
                host, port = self.host.get().rsplit(":", 1)
                if not host or not 1 <= int(port) <= 65535:
                    raise ValueError("TCP 地址格式应为 host:port，端口范围 1–65535")
                driver = TCPInstrument(config, host, int(port))
            else:
                driver = SimulatedInstrument(config)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("采集参数有误", str(exc), parent=self.root)
            return
        self.wave.clear()
        self.last_frame = None
        self.last_database = None
        self.engine = AcquisitionEngine(driver, config, self.data_dir)
        self._lock(True)
        self.state_label.configure(text="●  CONNECTING", fg=AMBER)
        self.engine.start()

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.stop_button.configure(state="disabled")
            self.state_label.configure(text="●  SAVING", fg=AMBER)

    def poll(self):
        if self.engine:
            # Keep newest charts; all frames have already been persisted by worker.
            latest = None
            while True:
                try:
                    frame = self.engine.frames.get_nowait()
                    self.wave.extend(frame.samples)
                    latest = frame
                except queue.Empty:
                    break
            if latest:
                self.render(latest)
            while True:
                try:
                    kind, value = self.engine.messages.get_nowait()
                except queue.Empty:
                    break
                if kind == "connected":
                    self.device_label.configure(text=value)
                    self.state_label.configure(text="●  RECORDING", fg=TEAL)
                    self._log("CONNECTED", value)
                elif kind == "event":
                    start, event, peak = value
                    self._log(event, f"绝对峰值 {peak:.3f} V；阈值 {self.engine.config.alarm_high:.2f} V", start)
                elif kind == "error":
                    self._log("ERROR", value)
                    self.state_label.configure(text="●  ERROR", fg=RED)
                elif kind == "stopped":
                    self.last_database = Path(value) if Path(value).exists() else None
                    if "ERROR" not in self.state_label.cget("text"):
                        self.state_label.configure(text="●  STOPPED", fg=MUTED)
                    if self.last_database:
                        self._log("SAVED", self.last_database.name)
                    self._lock(False)
        if self.closing and (not self.engine or not self.engine.running):
            self.root.destroy()
            return
        self.root.after(60, self.poll)

    def render(self, frame):
        self.last_frame = frame
        for key, label in self.metrics_labels.items():
            value = getattr(frame.metrics, key)
            label.configure(text=f"{value:.1f}" if key == "dominant_hz" else f"{value:.3f}")
        config = self.engine.config
        wave = list(self.wave)
        self.wave_plot.set_data(wave, (len(wave) - 1) / config.sample_rate * 1000,
                                max(config.alarm_high * 1.25, max(abs(v) for v in wave) * 1.15),
                                threshold=config.alarm_high)
        self.spectrum_plot.set_data(frame.spectrum, config.sample_rate / 2,
                                    max(max(frame.spectrum) * 1.25, 0.1), False)
        duration = frame.start + config.block_size / config.sample_rate
        self.counter.configure(text=f"{int(duration)//60:02d}:{int(duration)%60:02d}  ·  {(frame.seq+1)*config.block_size:,} samples")
        self.record_label.configure(text=f"{config.sample_rate:,} Hz · gain {config.gain:.4f} · DISPLAY DROP {self.engine.dropped_display_frames}")
        if frame.alarm:
            text, color = "峰值过载  /  已满足连续帧确认条件", RED
        elif abs(frame.metrics.mean) > 0.3:
            text, color = f"零点偏移  /  块均值 {frame.metrics.mean:+.3f} V（规则提示）", AMBER
        elif frame.metrics.crest_factor > 2:
            text, color = "高峰值因数  /  建议检查瞬态干扰（规则提示）", AMBER
        else:
            text, color = "状态正常  /  峰值、块均值与峰值因数在规则范围内", TEAL
        self.diagnosis.configure(text=text, fg=color)

    def export(self):
        if not self.last_database or (self.engine and self.engine.running):
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="导出采样数据", defaultextension=".csv",
                                           initialfile=self.last_database.stem + ".csv",
                                           filetypes=[("CSV 文件", "*.csv")])
        if path:
            try:
                count = export_csv(self.last_database, path)
                self._log("EXPORTED", f"已导出 {count:,} 个采样点：{Path(path).name}")
                messagebox.showinfo("导出完成", f"已导出 {count:,} 个采样点", parent=self.root)
            except (OSError, ValueError, sqlite3.Error) as exc:
                messagebox.showerror("导出失败", str(exc), parent=self.root)

    def calibrate(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("线性标定 / 最小二乘拟合")
        dialog.configure(bg=PANEL)
        dialog.geometry("540x350")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        body = tk.Frame(dialog, bg=PANEL, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        self.label(body, "校正电压 = gain × 原始电压 + offset", 12, TEAL, True).pack(anchor="w")
        self.label(body, "输入至少 2 组对应值，用英文逗号分隔；单位 V。", 9, MUTED).pack(anchor="w", pady=(8, 2))
        variables = []
        for text, default in [("仪器测量值", "0.02, 1.02, 2.02"), ("标准参考值", "0, 1, 2")]:
            self.label(body, text, 10).pack(anchor="w", pady=(10, 4))
            var = tk.StringVar(value=default)
            tk.Entry(body, textvariable=var, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                     relief="flat", font=(FONT, 11)).pack(fill="x", ipady=6)
            variables.append(var)
        result = self.label(body, f"当前 gain={self.calibration[0]:.6f}  offset={self.calibration[1]:+.6f}", 9, MUTED)
        result.pack(anchor="w", pady=14)
        def apply():
            try:
                points = [[float(v.strip()) for v in var.get().split(",")] for var in variables]
                gain, offset, residual = linear_calibration(*points)
                self.calibration = (gain, offset)
                self._log("CALIBRATED", f"gain={gain:.6f}, offset={offset:+.6f} V, 残差 RMSE={residual:.6f} V")
                dialog.destroy()
            except ValueError as exc:
                result.configure(text=str(exc), fg=RED)
        self.button(body, "应用到下一次采集", apply, True).pack(fill="x")

    def close(self):
        self.closing = True
        if self.engine and self.engine.running:
            self.stop()
            self.root.title("InstrumentLab | 正在关闭连接并保存…")
        else:
            self.root.destroy()


def launch(data_dir="data", demo=False):
    root = tk.Tk()
    app = InstrumentApp(root, data_dir)
    if demo:
        app.scenario.set("周期过载")
        root.after(300, app.start)
    root.mainloop()
