from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AcquisitionConfig:
    sample_rate: int = 1024
    block_size: int = 256
    frequency: float = 50.0
    amplitude: float = 2.0
    noise: float = 0.04
    scenario: str = "normal"
    alarm_high: float = 3.0
    hysteresis: float = 0.3
    alarm_confirm: int = 2
    gain: float = 1.0
    offset: float = 0.0

    def validate(self):
        for name in ("frequency", "amplitude", "noise", "alarm_high", "hysteresis", "gain", "offset"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} 必须是有限数值")
        if self.sample_rate not in (512, 1024, 2048, 4096):
            raise ValueError("采样率必须为 512 / 1024 / 2048 / 4096 Hz")
        if self.block_size != 256:
            raise ValueError("当前版本固定使用 256 点采样块")
        if not 0 < self.frequency < self.sample_rate / 2:
            raise ValueError("信号频率必须大于 0 且小于采样率的一半")
        if not 0 < self.amplitude <= 20 or not 0 <= self.noise <= 2:
            raise ValueError("幅值范围为 (0, 20] V，噪声范围为 [0, 2] V")
        if not 0 < self.alarm_high <= 100 or not 0 <= self.hysteresis < self.alarm_high:
            raise ValueError("告警阈值必须在 (0,100]，回差必须小于阈值")
        if self.alarm_confirm < 1 or self.gain <= 0:
            raise ValueError("确认帧数和标定增益必须为正")
        if self.scenario not in ("normal", "overload", "harmonic", "drift"):
            raise ValueError("未知仿真场景")
        if self.scenario == "harmonic" and 3 * self.frequency >= self.sample_rate / 2:
            raise ValueError("三次谐波场景要求 3 倍信号频率小于采样率的一半")
        return self
