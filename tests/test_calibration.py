import pytest

from src.control.fixed_point import calibrate
from src.sensing import HeaterReadout, ReadoutConfig
from src.sensing.calibration import calibration_coefficients


def test_legacy_two_point_coefficients_match_the_implemented_formula():
    readout = HeaterReadout(ReadoutConfig(
        r0_ohm=84.78097, divider_reference_ohm=84.78097,
        excitation_v=.018, front_end_gain=800,
        front_end_reference_v=.0086, delay_samples=0,
    ))
    low = readout.sample(40, 1).code
    high = readout.sample(80, 1).code
    gain, offset = calibration_coefficients(low, high, 40, 80)
    assert gain == round(40 * 64 / (high - low) * 16384)
    assert offset == round(40 * 64 - low * gain / 16384)
    assert abs(calibrate(low, gain, offset) - 40 * 64) <= 1
    assert abs(calibrate(high, gain, offset) - 80 * 64) <= 1


def test_invalid_or_unrepresentable_calibration_is_rejected():
    for arguments in [
        (100, 100, 40, 80), (200, 100, 40, 80),
        (-1, 100, 40, 80), (100, 4096, 40, 80),
        (100, 200, 80, 40), (100, 200, float('nan'), 80),
        (100, 101, 20, 350),
    ]:
        with pytest.raises(ValueError):
            calibration_coefficients(*arguments)
