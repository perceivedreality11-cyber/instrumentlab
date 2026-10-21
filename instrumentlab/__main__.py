import argparse
import json
from dataclasses import asdict
import math
from pathlib import Path
import queue
import time

from .config import AcquisitionConfig
from .drivers import SimulatedInstrument, TCPInstrument
from .engine import AcquisitionEngine
from .storage import export_csv


def main():
    parser = argparse.ArgumentParser(description="InstrumentLab 智能仪器采集与分析平台")
    parser.add_argument("--headless", action="store_true", help="命令行采集，不启动桌面界面")
    parser.add_argument("--demo", action="store_true", help="打开界面后自动开始周期过载演示")
    parser.add_argument("--seconds", type=float, default=5.0, help="命令行采集时长（秒）")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--scenario", default="normal", choices=["normal", "overload", "harmonic", "drift"])
    parser.add_argument("--tcp", metavar="HOST:PORT", help="使用自定义 TCP 协议仪器")
    parser.add_argument("--sample-rate", type=int, default=1024)
    parser.add_argument("--csv", type=Path, help="命令行采集完成后导出 CSV")
    args = parser.parse_args()
    if not args.headless:
        from .ui import launch
        launch(args.data_dir, args.demo)
        return
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
        parser.error("--seconds 必须在 (0, 3600] 秒以内")
    try:
        config = AcquisitionConfig(sample_rate=args.sample_rate, scenario=args.scenario).validate()
        if args.tcp:
            host, port = args.tcp.rsplit(":", 1)
            if not host or not 1 <= int(port) <= 65535:
                raise ValueError("无效的 TCP 地址")
            driver = TCPInstrument(config, host, int(port))
        else:
            driver = SimulatedInstrument(config)
    except ValueError as exc:
        parser.error(str(exc))
    engine = AcquisitionEngine(driver, config, args.data_dir)
    engine.start()
    latest = None
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and engine.running:
            try:
                latest = engine.frames.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        engine.thread.join(timeout=5)
    errors = []
    while not engine.messages.empty():
        kind, value = engine.messages.get()
        if kind == "error":
            errors.append(value)
    if errors or engine.running:
        parser.exit(1, "\n".join(errors or ["采集线程未能按时停止"]) + "\n")
    if latest:
        print(json.dumps(asdict(latest.metrics), indent=2))
    print(f"Database: {engine.path}")
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        print(f"Exported {export_csv(engine.path, args.csv)} samples to {args.csv}")


if __name__ == "__main__":
    main()
