"""Two-point calibration for the implemented temperature register format."""
import math


def calibration_coefficients(low_code, high_code, low_celsius, high_celsius):
    """Return signed Q14 gain and Q6 offset within the RTL register limits."""
    if not 0 <= low_code < high_code <= 4095:
        raise ValueError("Calibration codes must increase within the ADC range")
    if not all(math.isfinite(value) for value in (low_celsius, high_celsius)):
        raise ValueError("Calibration temperatures must be finite")
    if low_celsius >= high_celsius:
        raise ValueError("Calibration temperatures must increase")

    gain_q14 = round(
        (high_celsius - low_celsius) * 64 / (high_code - low_code) * 16384
    )
    offset_q6 = round(low_celsius * 64 - low_code * gain_q14 / 16384)
    if not 0 < gain_q14 < 131072 or not -32768 <= offset_q6 < 32768:
        raise ValueError("Calibration coefficients exceed the RTL register range")
    return gain_q14, offset_q6
