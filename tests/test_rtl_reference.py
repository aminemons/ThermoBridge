from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.control.fixed_point import (
    NUMERIC_CONTRACTS, PIState, calibrate, calibrate_contract, feedforward_q8,
    pi_update_contract, pwm_level, round_shift_even, sat,
)


def test_signed_round_ties_even_and_saturation():
    assert [round_shift_even(v, 1) for v in (1, 3, 5, -1, -3, -5)] == [0, 2, 2, 0, -2, -2]
    assert sat(40000, 16) == 32767
    assert sat(-40000, 16) == -32768


def test_calibration_ties_and_full_code_domain():
    assert calibrate(1, 8192, -64) == -64
    assert calibrate(3, 8192, -64) == -62
    assert calibrate(4094, 32768, -64) == 8124


def test_feedforward_and_exact_pwm_endpoints():
    assert feedforward_q8(0) == 0
    assert feedforward_q8(1600) == 0
    assert feedforward_q8(1920) == 14
    assert feedforward_q8(6400) == 256
    assert [pwm_level(0, p) for p in range(256)] == [0] * 256
    assert [pwm_level(256, p) for p in range(256)] == [1] * 256
    assert sum(pwm_level(77, p) for p in range(256)) == 77


def test_anti_windup_and_recovery_direction():
    state = PIState()
    high = state.update(temp_q6=0, setpoint_q6=64000, kp_q14=131071, ki_q14=131071, out_max=256)
    assert high == 256
    assert state.integrator_q8 == 0
    low = state.update(temp_q6=64000, setpoint_q6=0, kp_q14=131071, ki_q14=131071, out_min=0)
    assert low == 0


def test_three_width_contracts_preserve_one_degree_scale():
    cases = [
        ("compact_14f4_16f12", 4096, 4096, 16, 1600),
        ("primary_16f6_18f14", 16384, 16384, 64, 6400),
        ("wide_20f8_20f16", 65536, 65536, 256, 25600),
    ]
    for name, adc_gain, kp, temp_one_degree, setpoint_100c in cases:
        contract = NUMERIC_CONTRACTS[name]
        temp = calibrate_contract(1, adc_gain, 0, contract)
        assert temp == 1
        assert pi_update_contract(
            PIState(), temp=0, setpoint=temp_one_degree, kp=kp, ki=0,
            contract=contract,
        ) == 256
        assert calibrate_contract(4095, adc_gain, 0, contract) <= (1 << (contract.temp_bits - 1)) - 1
        assert setpoint_100c == 100 * (1 << contract.temp_frac)
