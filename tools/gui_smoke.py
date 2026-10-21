"""Exercise the actual Tk window and optionally capture only this app's area.

Run from repository root: python tools/gui_smoke.py [--capture]
Pillow is optional and used only for the documentation screenshot.
"""

import argparse
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instrumentlab.ui import InstrumentApp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        root = tk.Tk()
        app = InstrumentApp(root, folder)
        app.scenario.set("周期过载")
        root.update()
        app.start()
        deadline = time.monotonic() + 3.8
        try:
            while time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert app.last_frame and app.last_frame.alarm, "Overload scenario did not trigger alarm"
            assert app.start_button.cget("state") == "disabled"
            if args.capture:
                from PIL import ImageGrab
                root.lift()
                root.update()
                path = Path("docs/screenshot.png")
                path.parent.mkdir(exist_ok=True)
                ImageGrab.grab(window=root.winfo_id()).save(path)
                print(f"Screenshot: {path.resolve()}")
            root.geometry("1160x800")
            root.update()
            for widget in [app.events, app.export_button, app.spectrum_plot]:
                assert widget.winfo_ismapped()
                assert widget.winfo_rooty() + widget.winfo_height() <= root.winfo_rooty() + root.winfo_height(), "Widget clipped at minimum size"
            app.stop()
            deadline = time.monotonic() + 4
            while app.engine.running and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            root.update()
            app.poll()
            assert not app.engine.running
            assert app.last_database and app.last_database.exists()
            assert app.export_button.cget("state") == "normal"
            # Verify a fresh session can follow a completed session.
            app.scenario.set("稳定正弦")
            app.start()
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            assert app.last_frame and not app.last_frame.alarm
            print("GUI PASS: acquisition, plots, overload, save, restart and recovery")
        finally:
            if app.engine:
                app.engine.stop()
                app.engine.thread.join(4)
            root.destroy()


if __name__ == "__main__":
    main()
