from dataclasses import asdict
import json
import socketserver
import threading
import time
import unittest

from instrumentlab.config import AcquisitionConfig
from instrumentlab.drivers import TCPInstrument


class ProtocolTests(unittest.TestCase):
    def device(self, payload, fragment=False, delay=0):
        config = AcquisitionConfig()
        responses = [b"InstrumentLab,Test,001,1\n", json.dumps(asdict(config)).encode() + b"\n", payload]

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                try:
                    for index, response in enumerate(responses):
                        self.rfile.readline()
                        if index == 2 and delay:
                            time.sleep(delay)
                        if fragment:
                            # Deliberately split JSON across writes (TCP has no message boundary).
                            for start in range(0, len(response), 7):
                                self.wfile.write(response[start:start+7])
                                self.wfile.flush()
                        else:
                            self.wfile.write(response)
                            self.wfile.flush()
                except OSError:
                    pass

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        device = TCPInstrument(config, *server.server_address, timeout=0.1 if delay else 2)
        device.connect()
        self.addCleanup(device.close)
        return device

    def test_fragmented_response(self):
        device = self.device(json.dumps([0.25] * 256).encode() + b"\n", fragment=True)
        self.assertEqual(device.read_block(), (0, [0.25] * 256))

    def test_nonfinite_samples(self):
        for invalid in [float("nan"), float("inf"), True, "1.5"]:
            with self.subTest(invalid=invalid):
                values = [0.0] * 255 + [invalid]
                device = self.device(json.dumps(values).encode() + b"\n")
                with self.assertRaises(ValueError):
                    device.read_block()
                device.close()

    def test_oversized_response(self):
        device = self.device(b" " * 1_048_577 + b"\n")
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            device.read_block()

    def test_truncated_json(self):
        device = self.device(b"[1,2\n")
        with self.assertRaises(ValueError):
            device.read_block()

    def test_read_timeout(self):
        device = self.device(b"[]\n", delay=0.3)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            device.read_block()
        self.assertLess(time.monotonic() - started, 1)
