"""Small, testable DSP primitives. No numerical runtime dependency."""

from dataclasses import dataclass
import cmath
import math
import statistics


def fft(values):
    """Radix-2 Cooley-Tukey FFT, O(N log N)."""
    n = len(values)
    if n < 2 or n & (n - 1):
        raise ValueError("FFT 输入长度必须为大于 1 的 2 的幂")
    data = [complex(v) for v in values]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            data[i], data[j] = data[j], data[i]
    length = 2
    while length <= n:
        rotation = cmath.exp(-2j * math.pi / length)
        for start in range(0, n, length):
            weight = 1 + 0j
            for k in range(length // 2):
                a = data[start + k]
                b = weight * data[start + k + length // 2]
                data[start + k] = a + b
                data[start + k + length // 2] = a - b
                weight *= rotation
        length *= 2
    return data


@dataclass(frozen=True)
class Metrics:
    rms: float
    peak: float
    peak_to_peak: float
    mean: float
    dominant_hz: float
    crest_factor: float


def analyze(samples, sample_rate):
    if not samples or any(not math.isfinite(v) for v in samples):
        raise ValueError("采样数据必须非空且全部为有限数值")
    n = len(samples)
    if n < 4 or n & (n - 1):
        raise ValueError("分析块长度必须为不小于 4 的 2 的幂")
    mean = statistics.fmean(samples)
    rms = math.sqrt(statistics.fmean(v * v for v in samples))
    peak = max(abs(v) for v in samples)
    window = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
    transformed = fft([(v - mean) * w for v, w in zip(samples, window)])
    scale = sum(window)
    # Single-sided amplitude spectrum, DC removed; Nyquist is not doubled.
    spectrum = [abs(v) * (1 if i in (0, n // 2) else 2) / scale
                for i, v in enumerate(transformed[:n // 2 + 1])]
    best = max(range(1, len(spectrum)), key=spectrum.__getitem__)
    frequency = 0.0
    if max(spectrum[1:]) > 1e-10:
        delta = 0.0
        if 1 < best < len(spectrum) - 1:
            a, b, c = [math.log(max(v, 1e-15)) for v in spectrum[best - 1:best + 2]]
            denominator = a - 2 * b + c
            if abs(denominator) > 1e-15:
                delta = max(-0.5, min(0.5, 0.5 * (a - c) / denominator))
        frequency = (best + delta) * sample_rate / n
    return Metrics(rms, peak, max(samples) - min(samples), mean, frequency,
                   peak / rms if rms > 1e-12 else 0.0), spectrum


class Alarm:
    """Peak alarm with separate clear threshold and consecutive-frame debounce."""

    def __init__(self, high, hysteresis, confirm=2):
        self.high = high
        self.low = high - hysteresis
        self.confirm = confirm
        self.active = False
        self.pending = 0

    def update(self, peak):
        crossing = peak < self.low if self.active else peak >= self.high
        self.pending = self.pending + 1 if crossing else 0
        if self.pending < self.confirm:
            return None
        self.active = not self.active
        self.pending = 0
        return "ALARM" if self.active else "RECOVERED"


def linear_calibration(measured, reference):
    if len(measured) != len(reference) or len(measured) < 2:
        raise ValueError("需要至少两组测量值与参考值")
    if any(not math.isfinite(v) for v in [*measured, *reference]):
        raise ValueError("标定点必须为有限数值")
    mx, my = statistics.fmean(measured), statistics.fmean(reference)
    denominator = sum((x - mx) ** 2 for x in measured)
    if denominator < 1e-12:
        raise ValueError("测量值不能全部相同")
    gain = sum((x - mx) * (y - my) for x, y in zip(measured, reference)) / denominator
    offset = my - gain * mx
    if gain <= 0:
        raise ValueError("当前版本仅支持正增益标定")
    residual = math.sqrt(statistics.fmean((gain * x + offset - y) ** 2
                                        for x, y in zip(measured, reference)))
    return gain, offset, residual
