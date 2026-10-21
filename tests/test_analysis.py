import math
import unittest

from instrumentlab.analysis import Alarm, analyze, fft, linear_calibration
from instrumentlab.config import AcquisitionConfig
from instrumentlab.drivers import SimulatedInstrument


class AnalysisTests(unittest.TestCase):
    def test_fft_matches_direct_transform(self):
        samples = [0, 1, 4, -2, 3, 0.5, 2, -1]
        result = fft(samples)
        for k, actual in enumerate(result):
            expected = sum(v * complex(math.cos(-2*math.pi*k*i/8), math.sin(-2*math.pi*k*i/8))
                           for i, v in enumerate(samples))
            self.assertAlmostEqual(actual.real, expected.real, places=9)
            self.assertAlmostEqual(actual.imag, expected.imag, places=9)

    def test_bin_aligned_sine_metrics_and_amplitude(self):
        samples = [2 * math.sin(2 * math.pi * 64 * i / 1024) for i in range(256)]
        metrics, spectrum = analyze(samples, 1024)
        self.assertAlmostEqual(metrics.rms, math.sqrt(2), places=10)
        self.assertAlmostEqual(metrics.peak_to_peak, 4, places=10)
        self.assertAlmostEqual(metrics.dominant_hz, 64, delta=0.01)
        self.assertAlmostEqual(spectrum[16], 2, delta=0.002)

    def test_non_bin_frequency_estimation(self):
        samples = [2 * math.sin(2 * math.pi * 50 * i / 1024) for i in range(256)]
        metrics, _ = analyze(samples, 1024)
        self.assertAlmostEqual(metrics.dominant_hz, 50, delta=0.12)

    def test_constant_signal_has_no_ac_frequency(self):
        metrics, spectrum = analyze([2.0] * 256, 1024)
        self.assertEqual(metrics.dominant_hz, 0)
        self.assertEqual(metrics.mean, 2)
        self.assertEqual(metrics.rms, 2)
        self.assertEqual(max(spectrum), 0)

    def test_zero_signal(self):
        metrics, _ = analyze([0.0] * 256, 1024)
        self.assertEqual(metrics.crest_factor, 0)

    def test_invalid_data(self):
        for samples in ([], [1], [1, 2], [1, 2, 3], [math.nan] * 256, [math.inf] * 256):
            with self.subTest(samples=samples[:3]), self.assertRaises(ValueError):
                analyze(samples, 1024)

    def test_alarm_debounce_hysteresis_and_recovery(self):
        alarm = Alarm(3, 0.3, 2)
        self.assertIsNone(alarm.update(3.1))
        self.assertIsNone(alarm.update(2.9))  # interrupts pending alarm
        self.assertIsNone(alarm.update(3.2))
        self.assertEqual(alarm.update(3.3), "ALARM")
        self.assertIsNone(alarm.update(2.9))  # inside hysteresis band
        self.assertTrue(alarm.active)
        self.assertIsNone(alarm.update(2.6))
        self.assertEqual(alarm.update(2.5), "RECOVERED")
        self.assertFalse(alarm.active)

    def test_known_calibration(self):
        gain, offset, residual = linear_calibration([0.1, 1.1, 2.1], [0, 2, 4])
        self.assertAlmostEqual(gain, 2)
        self.assertAlmostEqual(offset, -0.2)
        self.assertAlmostEqual(residual, 0)

    def test_bad_calibration(self):
        for x, y in [([1], [1]), ([1, 1], [2, 3]), ([1, 2], [3]),
                     ([0, 1], [1, 0]), ([0, math.nan], [1, 2])]:
            with self.subTest(x=x), self.assertRaises(ValueError):
                linear_calibration(x, y)

    def test_config_rejects_aliasing_nonfinite_and_bad_thresholds(self):
        for kwargs in [{"frequency": 512}, {"amplitude": -1}, {"noise": math.nan},
                       {"hysteresis": 3}, {"sample_rate": 123}, {"gain": 0},
                       {"scenario": "harmonic", "frequency": 200}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                AcquisitionConfig(**kwargs).validate()

    def test_seeded_simulation_and_continuous_time(self):
        config = AcquisitionConfig()
        a, b = SimulatedInstrument(config), SimulatedInstrument(config)
        self.assertEqual(a.read_block(), b.read_block())
        self.assertEqual(a.read_block()[0], 0.25)

    def test_scenarios_have_observable_effect(self):
        normal = SimulatedInstrument(AcquisitionConfig(noise=0))
        overload = SimulatedInstrument(AcquisitionConfig(noise=0, scenario="overload"))
        for _ in range(9):
            _, a = normal.read_block()
            _, b = overload.read_block()
        self.assertAlmostEqual(max(b), 2 * max(a), places=8)
        harmonic = SimulatedInstrument(AcquisitionConfig(noise=0, frequency=64, scenario="harmonic"))
        _, spectrum = analyze(harmonic.read_block()[1], 1024)
        self.assertAlmostEqual(spectrum[48], 0.7, delta=0.01)
