"""Bit-exact integer reference for rtl/thermobridge_top.sv numeric contract v1."""
from __future__ import annotations

from dataclasses import dataclass

TEMP_FRAC = 6
COEFF_FRAC = 14
DUTY_MAX = 256
INTEGRATOR_BITS = 24
I16_MIN, I16_MAX = -(1 << 15), (1 << 15) - 1
I24_MIN, I24_MAX = -(1 << 23), (1 << 23) - 1


def sat(value: int, bits: int) -> int:
    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return min(hi, max(lo, int(value)))


def round_shift_even(value: int, shift: int) -> int:
    """Signed division by 2**shift, nearest with exact ties to even."""
    if shift <= 0:
        return int(value) << -shift
    sign = -1 if value < 0 else 1
    magnitude = abs(int(value))
    q, rem = divmod(magnitude, 1 << shift)
    half = 1 << (shift - 1)
    if rem > half or (rem == half and q & 1):
        q += 1
    return sign * q


def calibrate(adc_code: int, gain_q14: int, offset_q6: int) -> int:
    if not 0 <= adc_code <= 4095:
        raise ValueError("adc_code must fit 12 bits")
    if gain_q14 <= 0:
        raise ValueError("invalid calibration gain")
    return sat(offset_q6 + round_shift_even(adc_code * gain_q14, COEFF_FRAC), 16)


DEFAULT_FF_LUT_Q8 = [0, 14, 28, 43, 59, 74, 91, 108, 125, 143, 161, 180, 199, 218, 239, 256]


def feedforward_index_q6(setpoint_q6: int) -> int:
    if setpoint_q6 < 1600:
        return 0
    thresholds = [1920 + 320 * i for i in range(15)]
    for index, threshold in enumerate(thresholds):
        if setpoint_q6 < threshold:
            return index
    return 15


def feedforward_q8(setpoint_q6: int, table=DEFAULT_FF_LUT_Q8) -> int:
    # Inverse nominal spatial-FVM curve; export and units are in config JSON.
    if setpoint_q6 < 1600:
        return 0
    return min(256, max(0, int(table[feedforward_index_q6(setpoint_q6)])))


@dataclass
class PIState:
    integrator_q8: int = 0
    duty_q8: int = 0

    def update(
        self,
        *,
        temp_q6: int,
        setpoint_q6: int,
        kp_q14: int,
        ki_q14: int,
        ff_q8: int = 0,
        out_min: int = 0,
        out_max: int = DUTY_MAX,
    ) -> int:
        error = sat(setpoint_q6 - temp_q6, 16)
        p = sat(round_shift_even(kp_q14 * error, COEFF_FRAC + TEMP_FRAC - 8), 24)
        di = sat(round_shift_even(ki_q14 * error, COEFF_FRAC + TEMP_FRAC - 8), 24)
        unsat = p + self.integrator_q8 + ff_q8
        unsat_next = unsat + di
        if not ((unsat >= out_max and error > 0) or (unsat <= out_min and error < 0)):
            self.integrator_q8 = sat(self.integrator_q8 + di, INTEGRATOR_BITS)
        self.duty_q8 = min(out_max, max(out_min, unsat_next))
        return self.duty_q8


@dataclass(frozen=True)
class NumericContract:
    """Width/scale alternative evaluated by the integer reference only."""
    name: str
    temp_bits: int
    temp_frac: int
    coeff_bits: int
    coeff_frac: int

    @property
    def product_shift(self) -> int:
        return self.coeff_frac + self.temp_frac - 8


NUMERIC_CONTRACTS = {
    # All three retain the same approximate full temperature range; widths
    # trade quantization for product/accumulator cost. RTL route is primary only.
    "compact_14f4_16f12": NumericContract("compact_14f4_16f12", 14, 4, 16, 12),
    "primary_16f6_18f14": NumericContract("primary_16f6_18f14", 16, 6, 18, 14),
    "wide_20f8_20f16": NumericContract("wide_20f8_20f16", 20, 8, 20, 16),
}


def calibrate_contract(adc_code: int, gain: int, offset: int, contract: NumericContract) -> int:
    if not 0 <= adc_code <= 4095:
        raise ValueError("adc_code must fit 12 bits")
    if gain <= 0:
        raise ValueError("invalid calibration gain")
    return sat(offset + round_shift_even(adc_code * gain, contract.coeff_frac), contract.temp_bits)


def pi_update_contract(
    state: PIState,
    *,
    temp: int,
    setpoint: int,
    kp: int,
    ki: int,
    ff_q8: int = 0,
    out_min: int = 0,
    out_max: int = DUTY_MAX,
    contract: NumericContract,
) -> int:
    """Update using one of the documented width/scale arithmetic choices."""
    error = sat(setpoint - temp, contract.temp_bits)
    p = sat(round_shift_even(kp * error, contract.product_shift), 24)
    di = sat(round_shift_even(ki * error, contract.product_shift), 24)
    unsat = p + state.integrator_q8 + ff_q8
    unsat_next = unsat + di
    if not ((unsat >= out_max and error > 0) or (unsat <= out_min and error < 0)):
        state.integrator_q8 = sat(state.integrator_q8 + di, INTEGRATOR_BITS)
    state.duty_q8 = min(out_max, max(out_min, unsat_next))
    return state.duty_q8


def pwm_level(duty_q8: int, phase: int) -> int:
    """Exact 0/full endpoints plus 256-phase, high-first PWM."""
    if not 0 <= duty_q8 <= DUTY_MAX or not 0 <= phase < 256:
        raise ValueError("PWM input out of range")
    return int(duty_q8 == DUTY_MAX or (duty_q8 != 0 and phase < duty_q8))
