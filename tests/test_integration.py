import csv
from contextlib import closing
import json
from pathlib import Path
import socketserver
import sqlite3
import tempfile
import threading
import time
import unittest

from instrumentlab.config import AcquisitionConfig
from instrumentlab.drivers import SimulatedInstrument, TCPInstrument
from instrumentlab.engine import AcquisitionEngine
from instrumentlab.mock_server import InstrumentServer
from instrumentlab.storage import SessionStore, export_csv


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = AcquisitionConfig(sample_rate=4096, gain=2, offset=0.1)

    def run_engine(self, driver, frames=4):
        engine = AcquisitionEngine(driver, self.config, self.temp.name)
        engine.start()
        try:
            for _ in range(frames):
                engine.frames.get(timeout=3)
        finally:
            engine.stop()
            engine.thread.join(4)
        self.assertFalse(engine.running)
        messages = []
        while not engine.messages.empty():
            messages.append(engine.messages.get())
        self.assertFalse([m for m in messages if m[0] == "error"], messages)
        return engine

    def test_simulation_sqlite_calibration_and_csv_round_trip(self):
        engine = self.run_engine(SimulatedInstrument(self.config))
        with closing(sqlite3.connect(engine.path)) as db:
            blocks = db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
            raw, calibrated = db.execute("SELECT raw,calibrated FROM blocks LIMIT 1").fetchone()
            for before, after in zip(json.loads(raw), json.loads(calibrated)):
                self.assertAlmostEqual(after, before * 2 + 0.1)
            self.assertGreater(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        destination = Path(self.temp.name) / "export.csv"
        count = export_csv(engine.path, destination)
        self.assertEqual(count, blocks * 256)
        with destination.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), count)
        self.assertEqual(float(rows[0]["time_s"]), 0)
        self.assertAlmostEqual(float(rows[-1]["time_s"]), (count - 1) / 4096, places=8)
        times = [float(row["time_s"]) for row in rows]
        self.assertTrue(all(b > a for a, b in zip(times, times[1:])))

    def server(self, config=None):
        server = InstrumentServer(("127.0.0.1", 0), config or self.config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_actual_tcp_socket_to_recording(self):
        server = self.server()
        engine = self.run_engine(TCPInstrument(self.config, *server.server_address))
        self.assertTrue(engine.path.exists())

    def test_tcp_rejects_sample_rate_mismatch(self):
        server = self.server(AcquisitionConfig())
        device = TCPInstrument(self.config, *server.server_address)
        try:
            with self.assertRaisesRegex(ValueError, "采样率"):
                device.connect()
        finally:
            device.close()

    def test_tcp_rejects_malformed_samples_and_partial_frame(self):
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for response in [b"bad-id\n", b'{"sample_rate":4096,"block_size":256}\n', b'[true]\n']:
                    self.rfile.readline()
                    self.wfile.write(response)
                    self.wfile.flush()
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        driver = TCPInstrument(self.config, *server.server_address)
        try:
            driver.connect()
            with self.assertRaises(ValueError):
                driver.read_block()
            with self.assertRaises((ValueError, ConnectionError)):
                driver.read_block()  # peer closed: incomplete line
        finally:
            driver.close()

    def test_device_error_surfaces_and_closes_driver(self):
        class Broken:
            closed = False
            def connect(self):
                raise ConnectionError("test disconnected")
            def close(self):
                self.closed = True
        driver = Broken()
        engine = AcquisitionEngine(driver, self.config, self.temp.name)
        engine.start()
        engine.thread.join(3)
        self.assertTrue(driver.closed)
        self.assertFalse(engine.path.exists())
        self.assertEqual(engine.messages.get()[0], "error")
        self.assertEqual(engine.messages.get()[0], "stopped")

    def test_slow_display_does_not_lose_recorded_blocks(self):
        engine = AcquisitionEngine(SimulatedInstrument(self.config), self.config, self.temp.name)
        engine.start()
        deadline = time.monotonic() + 4
        while not engine.dropped_display_frames and time.monotonic() < deadline:
            time.sleep(0.02)  # Deliberately do not consume the 8-frame display queue.
        engine.stop()
        engine.thread.join(3)
        self.assertGreater(engine.dropped_display_frames, 0)
        with closing(sqlite3.connect(engine.path)) as db:
            count = db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        self.assertEqual(count, engine.frames.qsize() + engine.dropped_display_frames)

    def test_existing_database_is_not_overwritten(self):
        path = Path(self.temp.name) / "existing.sqlite3"
        path.write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            SessionStore(path, self.config, "test")
        self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_csv_cannot_overwrite_database(self):
        engine = self.run_engine(SimulatedInstrument(self.config), frames=1)
        with self.assertRaises(ValueError):
            export_csv(engine.path, engine.path)

    def test_engine_cannot_start_twice(self):
        engine = self.run_engine(SimulatedInstrument(self.config), frames=1)
        with self.assertRaises(RuntimeError):
            engine.start()
