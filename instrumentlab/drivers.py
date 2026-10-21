"""Driver boundary: deterministic simulator and line-framed TCP adapter."""

import json
import math
import random
import socket


class SimulatedInstrument:
    def __init__(self, config, seed=42):
        self.config = config.validate()
        self.random = random.Random(seed)
        self.cursor = 0

    def connect(self):
        return "InstrumentLab, Virtual DAQ, SIM-001, 1.0"

    def read_block(self):
        c = self.config
        start = self.cursor / c.sample_rate
        result = []
        for i in range(c.block_size):
            t = (self.cursor + i) / c.sample_rate
            amplitude = c.amplitude
            if c.scenario == "overload" and 2 <= t % 10 < 6:
                amplitude *= 2
            value = amplitude * math.sin(2 * math.pi * c.frequency * t)
            if c.scenario == "harmonic":
                value += 0.35 * amplitude * math.sin(2 * math.pi * 3 * c.frequency * t)
            if c.scenario == "drift":
                value += min(t * 0.08, 4.0)
            result.append(value + self.random.gauss(0, c.noise))
        self.cursor += c.block_size
        return start, result

    def close(self):
        pass


class TCPInstrument:
    """SCPI-style custom subset, not a generic oscilloscope compatibility claim."""

    def __init__(self, config, host="127.0.0.1", port=5025, timeout=2.0):
        self.config = config.validate()
        self.host, self.port, self.timeout = host, port, timeout
        self.socket = None
        self.reader = None
        self.cursor = 0

    def query(self, command):
        self.socket.sendall((command + "\n").encode("ascii"))
        response = self.reader.readline(1_048_577)
        if not response.endswith(b"\n") or len(response) > 1_048_576:
            raise ValueError("设备响应未完整结束或超过 1 MiB")
        return response.decode("utf-8").strip()

    def connect(self):
        self.socket = socket.create_connection((self.host, self.port), self.timeout)
        self.reader = self.socket.makefile("rb")
        identity = self.query("*IDN?")
        # Validate negotiated framing instead of silently assuming sample rate.
        settings = json.loads(self.query("ACQ:CONF?"))
        if (settings.get("sample_rate"), settings.get("block_size")) != (
                self.config.sample_rate, self.config.block_size):
            raise ValueError("设备采样率/块长度与界面不一致，请匹配设置后重连")
        return identity

    def read_block(self):
        values = json.loads(self.query("MEAS:WAV?"))
        if not isinstance(values, list) or len(values) != self.config.block_size:
            raise ValueError("设备返回的采样点数不正确")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in values):
            raise ValueError("设备采样包含非法数值")
        start = self.cursor / self.config.sample_rate
        self.cursor += len(values)
        return start, values

    def close(self):
        if self.reader:
            self.reader.close()
        if self.socket:
            self.socket.close()
