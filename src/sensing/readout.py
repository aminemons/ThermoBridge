"""Calibrated heater-resistance divider and sampled 12-bit ADC model.

The divider is a low-current, synchronized measurement circuit. It is not the
heater power path. A sample is marked invalid when the synchronized window is
unavailable or the heater is off, so an unobservable resistance is never
silently reused as a fresh temperature.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class ReadoutConfig:
    r0_ohm: float = 12.0
    tcr_per_k: float = 0.0032
    reference_c: float = 25.0
    calibration_r0_ohm: float | None = None
    calibration_tcr_per_k: float | None = None
    valid_temperature_c: tuple[float, float] = (0.0, 350.0)
    excitation_v: float = 1.8
    divider_reference_ohm: float = 12.0
    adc_reference_v: float = 1.8
    front_end_gain: float = 1.0
    front_end_reference_v: float = 0.0
    adc_bits: int = 12
    gain_error_fraction: float = 0.0
    offset_error_v: float = 0.0
    noise_rms_v: float = 0.0
    delay_samples: int = 1
    window_min_duty: float = 1.0 / 256.0

    def __post_init__(self):
        if min(self.r0_ohm, self.excitation_v, self.divider_reference_ohm, self.adc_reference_v, self.front_end_gain) <= 0:
            raise ValueError("resistances and voltages must be positive")
        if self.adc_bits != 12:
            raise ValueError("this bridge model is specified for a 12-bit ADC")
        if not -1 < self.gain_error_fraction or self.delay_samples < 0:
            raise ValueError("invalid gain error or sample delay")
        if not 0 <= self.window_min_duty <= 1:
            raise ValueError("window_min_duty must be in [0,1]")
        if self.valid_temperature_c[0] >= self.valid_temperature_c[1]:
            raise ValueError("invalid calibration temperature range")


@dataclass(frozen=True)
class ReadoutSample:
    code: int
    temperature_estimate_c: float
    valid: bool
    resistance_ohm: float | None
    divider_voltage_v: float | None
    sense_power_w: float


class HeaterReadout:
    """Forward heater R(T), explicit divider, ADC and delayed sample model."""

    def __init__(self, config: ReadoutConfig = ReadoutConfig(), seed: int = 1):
        self.config = config
        self.rng = random.Random(seed)
        self.max_code = (1 << config.adc_bits) - 1
        # Delay holds the pending measured (code, validity) samples.
        self._pending: deque[tuple[int, bool, float | None, float | None, float]] = deque(
            [(0, False, None, None, 0.0)] * config.delay_samples
        )

    def resistance(self, temperature_c: float) -> float:
        c = self.config
        if not c.valid_temperature_c[0] <= temperature_c <= c.valid_temperature_c[1]:
            raise ValueError("temperature outside documented heater calibration range")
        r = c.r0_ohm * (1.0 + c.tcr_per_k * (temperature_c - c.reference_c))
        if r <= 0:
            raise ValueError("calibration predicts non-positive resistance")
        return r

    def voltage(self, temperature_c: float) -> float:
        r = self.resistance(temperature_c)
        c = self.config
        return c.front_end_gain * (c.excitation_v * r / (c.divider_reference_ohm + r) - c.front_end_reference_v)

    def _encode(self, measured_v: float) -> int:
        c = self.config
        v = (measured_v + c.offset_error_v) * (1.0 + c.gain_error_fraction)
        v += self.rng.gauss(0.0, c.noise_rms_v) if c.noise_rms_v else 0.0
        # ADC saturates to rails. Python round implements ties-to-even.
        return max(0, min(self.max_code, round(v / c.adc_reference_v * self.max_code)))

    def decode(self, code: int) -> float:
        if not 0 <= code <= self.max_code:
            raise ValueError("ADC code outside 12-bit range")
        c = self.config
        v = code / self.max_code * c.adc_reference_v / c.front_end_gain
        v += c.front_end_reference_v
        v /= c.excitation_v
        ratio = v
        if ratio <= 0 or ratio >= 1:
            return math.nan
        resistance = c.divider_reference_ohm * ratio / (1.0 - ratio)
        r0 = c.calibration_r0_ohm if c.calibration_r0_ohm is not None else c.r0_ohm
        tcr = c.calibration_tcr_per_k if c.calibration_tcr_per_k is not None else c.tcr_per_k
        return c.reference_c + (resistance / r0 - 1.0) / tcr

    def sample(self, temperature_c: float, duty: float, *, window_valid: bool = True) -> ReadoutSample:
        c = self.config
        observable = window_valid and duty >= c.window_min_duty
        if observable:
            v = self.voltage(temperature_c)
            code = self._encode(v)
            r = self.resistance(temperature_c)
            sense_power = c.excitation_v**2 / (c.divider_reference_ohm + r)
        else:
            v, code, r, sense_power = None, 0, None, 0.0
        item = (code, observable, r, v, sense_power)
        if c.delay_samples:
            self._pending.append(item)
            code, valid, r, v, sense_power = self._pending.popleft()
        else:
            code, valid, r, v, sense_power = item
        estimate = self.decode(code) if valid else math.nan
        return ReadoutSample(code, estimate, valid, r, v, sense_power)
