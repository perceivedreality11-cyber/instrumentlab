"""An actual TCP loopback instrument for adapter integration tests and demos."""

import argparse
from dataclasses import asdict
import json
import socketserver

from .config import AcquisitionConfig
from .drivers import SimulatedInstrument


class InstrumentHandler(socketserver.StreamRequestHandler):
    def handle(self):
        device = SimulatedInstrument(self.server.config)
        try:
            while True:
                line = self.rfile.readline(4097)
                if not line:
                    return
                if len(line) > 4096 or not line.endswith(b"\n"):
                    return
                command = line.decode("ascii").strip().upper()
                if command == "*IDN?":
                    response = device.connect()
                elif command == "ACQ:CONF?":
                    response = json.dumps(asdict(self.server.config))
                elif command == "MEAS:WAV?":
                    response = json.dumps(device.read_block()[1])
                else:
                    response = 'ERROR: unsupported command'
                self.wfile.write((response + "\n").encode("utf-8"))
                self.wfile.flush()
        except (ConnectionError, OSError, UnicodeError):
            return


class InstrumentServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, config):
        self.config = config.validate()
        super().__init__(address, InstrumentHandler)


def main():
    parser = argparse.ArgumentParser(description="InstrumentLab TCP 仿真仪器（默认仅监听本机）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5025)
    parser.add_argument("--sample-rate", type=int, default=1024)
    parser.add_argument("--scenario", choices=["normal", "overload", "harmonic", "drift"], default="normal")
    args = parser.parse_args()
    config = AcquisitionConfig(sample_rate=args.sample_rate, scenario=args.scenario)
    with InstrumentServer((args.host, args.port), config) as server:
        print(f"Virtual instrument listening on {server.server_address}; Ctrl+C to stop", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
