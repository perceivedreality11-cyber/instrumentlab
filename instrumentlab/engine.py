from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import queue
import threading
import time
import uuid

from .analysis import Alarm, Metrics, analyze
from .storage import SessionStore


@dataclass(frozen=True)
class Frame:
    seq: int
    start: float
    raw: list
    samples: list
    spectrum: list
    metrics: Metrics
    alarm: bool
    event: str | None


class AcquisitionEngine:
    """One worker owns the driver and DB; UI consumes a bounded display queue."""

    def __init__(self, driver, config, directory):
        self.driver, self.config = driver, config.validate()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = Path(directory) / f"session-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
        self.frames = queue.Queue(maxsize=8)
        self.messages = queue.SimpleQueue()
        self.stop_event = threading.Event()
        self.thread = None
        self.dropped_display_frames = 0

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.thread is not None:
            raise RuntimeError("一次采集引擎只能启动一次")
        self.thread = threading.Thread(target=self._run, name="instrument-acquisition", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        store = None
        try:
            identity = self.driver.connect()
            store = SessionStore(self.path, self.config, identity)
            self.messages.put(("connected", identity))
            alarm = Alarm(self.config.alarm_high, self.config.hysteresis, self.config.alarm_confirm)
            seq = 0
            deadline = time.monotonic()
            while not self.stop_event.is_set():
                start, raw = self.driver.read_block()
                calibrated = [v * self.config.gain + self.config.offset for v in raw]
                metrics, spectrum = analyze(calibrated, self.config.sample_rate)
                event = alarm.update(metrics.peak)
                frame = Frame(seq, start, raw, calibrated, spectrum, metrics, alarm.active, event)
                store.append(frame)
                if event:
                    self.messages.put(("event", (start, event, metrics.peak)))
                try:
                    self.frames.put_nowait(frame)
                except queue.Full:
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass  # UI may have drained the queue after put_nowait failed.
                    self.frames.put_nowait(frame)
                    self.dropped_display_frames += 1
                seq += 1
                deadline += self.config.block_size / self.config.sample_rate
                self.stop_event.wait(max(0, deadline - time.monotonic()))
        except Exception as exc:
            self.messages.put(("error", f"{type(exc).__name__}: {exc}"))
        finally:
            try:
                if store:
                    store.close()
            finally:
                try:
                    self.driver.close()
                finally:
                    self.messages.put(("stopped", str(self.path)))
