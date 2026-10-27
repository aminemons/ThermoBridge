"""Icarus/cocotb RTL checks against the bit-exact integer reference."""
import json
import random
from pathlib import Path
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.control.fixed_point import PIState, calibrate, feedforward_q8, pwm_level

REG_CTRL = 0x00
REG_SETPOINT = 0x04
REG_CAL_OFFSET = 0x08
REG_ADC_GAIN = 0x0C
REG_KP = 0x10
REG_KI = 0x14
REG_LIMIT = 0x18
REG_OUT_MIN = 0x1C
REG_OUT_MAX = 0x20
REG_CLEAR = 0x24
REG_STATUS = 0x28
REG_TEMP = 0x2C
REG_DUTY = 0x30
REG_COMMIT = 0x34
CLEAR_KEY = 0x5442C1EA
SEED = 0x5442
CHECKS = {"accepted_sample_comparisons": 0, "randomized_sample_comparisons": 0}


async def bus_write(dut, address, value):
    dut.cfg_addr.value = address
    dut.cfg_wdata.value = value & 0xFFFFFFFF
    dut.cfg_write.value = 1
    dut.cfg_valid.value = 1
    await RisingEdge(dut.clk)
    dut.cfg_valid.value = 0
    dut.cfg_write.value = 0
    await RisingEdge(dut.clk)


async def wait_sample(dut, code, max_cycles=128):
    dut.adc_code.value = code
    dut.adc_valid.value = 1
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if int(dut.sample_accepted.value):
            dut.adc_valid.value = 0
            return int(dut.temp_q6.value.to_signed())
    dut.adc_valid.value = 0
    raise AssertionError("no sample accepted within expected control interval")


async def await_committed(dut, max_cycles=128):
    for _ in range(max_cycles):
        await RisingEdge(dut.clk)
        if int(dut.active_enable.value):
            return
    raise AssertionError("configuration did not commit")


async def commit(dut):
    await bus_write(dut, REG_COMMIT, 1)
    for _ in range(128):
        await RisingEdge(dut.clk)
        if not int(dut.commit_pending.value):
            return
    raise AssertionError("commit did not apply at a control tick")


async def expect_sample(dut, code, gain, offset, expected_duty=None):
    observed = await wait_sample(dut, code)
    expected = calibrate(code, gain, offset)
    assert observed == expected, f"ADC {code}: RTL {observed}, reference {expected}"
    if expected_duty is not None:
        actual_duty = int(dut.duty_q8.value)
        assert actual_duty == expected_duty, f"RTL duty {actual_duty}, reference {expected_duty}"
    CHECKS["accepted_sample_comparisons"] += 1
    if expected_duty is not None:
        CHECKS["controller_update_comparisons"] = CHECKS.get("controller_update_comparisons", 0) + 1


def write_summary(**extra):
    path = Path(__file__).resolve().parents[1] / "build" / "rtl_cocotb" / "rtl_test_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "simulator": "Icarus Verilog 14.0 (devel) with cocotb 2.1.0",
        "control_div_cycles": 32,
        "random_seed": SEED,
        "fault_coverage": ["reset", "disabled", "adc_rail", "invalid_calibration",
                           "overtemperature", "stale_adc", "shutdown", "safe_clear"],
        **CHECKS,
        **extra,
    }
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


async def clear_safe(dut, code=100):
    dut.adc_code.value = code
    dut.adc_valid.value = 1
    dut.cfg_addr.value = REG_CLEAR
    dut.cfg_wdata.value = CLEAR_KEY
    dut.cfg_write.value = 1
    dut.cfg_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.cfg_valid.value = 0
    dut.cfg_write.value = 0
    dut.adc_valid.value = 0
    assert int(dut.fault_cause.value) == 0


@cocotb.test()
async def controller_directed_and_randomized(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.reset_n.value = 0
    dut.adc_code.value = 1
    dut.adc_valid.value = 0
    dut.cfg_valid.value = 0
    dut.cfg_write.value = 0
    dut.cfg_addr.value = 0
    dut.cfg_wdata.value = 0
    await Timer(40, unit="ns")
    dut.reset_n.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    assert int(dut.pwm_out.value) == 0
    assert int(dut.duty_q8.value) == 0
    assert int(dut.fault_cause.value) == 0

    # Stage all values and prove they stay shadowed until one atomic commit.
    await bus_write(dut, REG_CTRL, 5)
    await bus_write(dut, REG_SETPOINT, 5000)
    await bus_write(dut, REG_CAL_OFFSET, -64)
    await bus_write(dut, REG_ADC_GAIN, 8192)  # half a temperature LSB/code
    await bus_write(dut, REG_KP, 0)
    await bus_write(dut, REG_KI, 0)
    await bus_write(dut, REG_LIMIT, 30000)
    await bus_write(dut, REG_OUT_MIN, 0)
    await bus_write(dut, REG_OUT_MAX, 256)
    assert int(dut.active_enable.value) == 0
    await commit(dut)
    await await_committed(dut)
    assert int(dut.active_setpoint.value.to_signed()) == 5000
    assert int(dut.active_adc_gain.value.to_signed()) == 8192

    # Signed setpoint and ADC-gain endpoints read back correctly in shadow storage.
    await bus_write(dut, REG_SETPOINT, -32768)
    dut.cfg_addr.value = REG_SETPOINT
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == -32768
    await bus_write(dut, REG_SETPOINT, 32767)
    dut.cfg_addr.value = REG_SETPOINT
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == 32767
    await bus_write(dut, REG_ADC_GAIN, 0)
    dut.cfg_addr.value = REG_ADC_GAIN
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == 0
    await bus_write(dut, REG_ADC_GAIN, 131071)
    dut.cfg_addr.value = REG_ADC_GAIN
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == 131071
    assert int(dut.active_setpoint.value.to_signed()) == 5000
    assert int(dut.active_adc_gain.value.to_signed()) == 8192
    await bus_write(dut, REG_SETPOINT, 5000)
    await bus_write(dut, REG_ADC_GAIN, 8192)

    # Index 10 spans 75..<80 C. Its shadow changes only after whole-bank commit.
    await bus_write(dut, 0x68, 222)
    dut.cfg_addr.value = 0x68
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value) == 222
    await expect_sample(dut, 100, 8192, -64, 161)
    await commit(dut)
    await expect_sample(dut, 100, 8192, -64, 222)
    await bus_write(dut, 0x68, 161)
    await commit(dut)

    # Calibration ties-to-even for positive and negative offset results.
    await expect_sample(dut, 1, 8192, -64)  # -63.5 rounds to -64
    await expect_sample(dut, 3, 8192, -64)  # -62.5 rounds to -62
    await expect_sample(dut, 4094, 8192, -64)
    dut.cfg_addr.value = REG_TEMP
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == calibrate(4094, 8192, -64)
    dut.cfg_addr.value = REG_SETPOINT
    await Timer(1, unit="ns")
    assert int(dut.cfg_rdata.value.to_signed()) == 5000

    # A changed shadow gain remains inactive until a later commit.
    await bus_write(dut, REG_ADC_GAIN, 32768)
    assert int(dut.active_adc_gain.value.to_signed()) == 8192
    await commit(dut)
    await expect_sample(dut, 100, 32768, -64)

    # Exact PWM off and full-on endpoints.
    await bus_write(dut, REG_OUT_MIN, 0)
    await bus_write(dut, REG_OUT_MAX, 0)
    await commit(dut)
    await wait_sample(dut, 100)
    assert int(dut.duty_q8.value) == 0
    assert int(dut.pwm_out.value) == 0
    await bus_write(dut, REG_OUT_MIN, 256)
    await bus_write(dut, REG_OUT_MAX, 256)
    await commit(dut)
    await wait_sample(dut, 100)
    assert int(dut.duty_q8.value) == 256
    assert int(dut.pwm_out.value) == 1
    assert [pwm_level(0, p) for p in (0, 1, 255)] == [0, 0, 0]
    assert [pwm_level(256, p) for p in (0, 1, 255)] == [1, 1, 1]
    assert sum(pwm_level(77, p) for p in range(256)) == 77

    # Deterministic randomized samples across the ADC range excluding rail codes.
    await bus_write(dut, REG_OUT_MIN, 0)
    await bus_write(dut, REG_OUT_MAX, 256)
    await commit(dut)
    rng = random.Random(SEED)
    randomized_codes = [1, 2, 2047, 2048, 4094] + [rng.randint(1, 4094) for _ in range(256)]
    for code in randomized_codes:
        temp = calibrate(code, 32768, -64)
        expected = PIState().update(
            temp_q6=temp, setpoint_q6=5000, kp_q14=0, ki_q14=0,
            ff_q8=feedforward_q8(5000), out_min=0, out_max=256,
        )
        await expect_sample(dut, code, 32768, -64, expected)
        CHECKS["randomized_sample_comparisons"] += 1

    # Extreme positive gain plus offset must saturate calibrated temperature, not wrap.
    await bus_write(dut, REG_CAL_OFFSET, 32767)
    await bus_write(dut, REG_ADC_GAIN, 131071)
    await bus_write(dut, REG_LIMIT, 32767)
    await commit(dut)
    saturated_temp = await wait_sample(dut, 4094)
    assert saturated_temp == 32767
    assert int(dut.fault_cause.value) & 0x01
    await bus_write(dut, REG_CAL_OFFSET, -64)
    await bus_write(dut, REG_ADC_GAIN, 32768)
    await bus_write(dut, REG_LIMIT, 30000)
    await commit(dut)
    await wait_sample(dut, 100)
    await clear_safe(dut)

    # PI product rounding ties are covered in RTL at 0.5 and 1.5 duty counts.
    await bus_write(dut, REG_CAL_OFFSET, -1)
    await bus_write(dut, REG_ADC_GAIN, 16384)
    await bus_write(dut, REG_SETPOINT, 2)
    await bus_write(dut, REG_KP, 1024)
    await bus_write(dut, REG_KI, 0)
    await commit(dut)
    await expect_sample(dut, 1, 16384, -1, 0)
    await bus_write(dut, REG_SETPOINT, 6)
    await commit(dut)
    await expect_sample(dut, 1, 16384, -1, 2)

    # Negative error clamps at zero. Large positive error saturates without windup.
    await bus_write(dut, REG_CAL_OFFSET, -64)
    await bus_write(dut, REG_ADC_GAIN, 32768)
    await bus_write(dut, REG_SETPOINT, 0)
    await bus_write(dut, REG_KP, 16384)
    await bus_write(dut, REG_KI, 0)
    await commit(dut)
    temp = calibrate(100, 32768, -64)
    expected = PIState().update(temp_q6=temp, setpoint_q6=0, kp_q14=16384,
                                ki_q14=0, ff_q8=0)
    await expect_sample(dut, 100, 32768, -64, expected)
    assert expected == 0
    await bus_write(dut, REG_SETPOINT, 16000)
    await bus_write(dut, REG_KP, 131071)
    await bus_write(dut, REG_KI, 131071)
    await commit(dut)
    temp = calibrate(1, 32768, -64)
    state = PIState()
    expected = state.update(temp_q6=temp, setpoint_q6=16000, kp_q14=131071,
                            ki_q14=131071, ff_q8=feedforward_q8(16000))
    await expect_sample(dut, 1, 32768, -64, expected)
    assert expected == 256
    assert int(dut.integrator_q8.value.to_signed()) == 0

    # Invalid calibration latches a fault. A fresh safe sample plus explicit key clears it.
    await bus_write(dut, REG_ADC_GAIN, 0)
    await commit(dut)
    dut.adc_code.value = 100
    dut.adc_valid.value = 1
    for _ in range(128):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if int(dut.sample_accepted.value):
            break
    dut.adc_valid.value = 0
    assert int(dut.fault_cause.value) & 0x02
    # A clear acknowledgment cannot erase an invalid-calibration fault.
    dut.adc_code.value = 100
    dut.adc_valid.value = 1
    dut.cfg_addr.value = REG_CLEAR
    dut.cfg_wdata.value = CLEAR_KEY
    dut.cfg_write.value = 1
    dut.cfg_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.adc_valid.value = 0
    dut.cfg_write.value = 0
    dut.cfg_valid.value = 0
    assert int(dut.fault_cause.value) & 0x02
    await bus_write(dut, REG_ADC_GAIN, 32768)
    await commit(dut)
    await wait_sample(dut, 100)
    await clear_safe(dut)

    # ADC rail, overtemperature and commanded shutdown latch independently.
    await wait_sample(dut, 0)
    assert int(dut.fault_cause.value) & 0x10
    await clear_safe(dut)
    await wait_sample(dut, 4095)
    assert int(dut.fault_cause.value) & 0x10
    await clear_safe(dut)
    await bus_write(dut, REG_LIMIT, 64)
    await commit(dut)
    await wait_sample(dut, 100)
    assert int(dut.fault_cause.value) & 0x01
    await bus_write(dut, REG_LIMIT, 30000)
    await commit(dut)
    await wait_sample(dut, 100)
    await clear_safe(dut)
    await bus_write(dut, REG_CTRL, 3)
    await commit(dut)
    assert int(dut.fault_cause.value) & 0x08
    assert int(dut.pwm_out.value) == 0
    await bus_write(dut, REG_CTRL, 1)
    await commit(dut)
    await clear_safe(dut)
    assert int(dut.fault_cause.value) == 0
    CHECKS["directed_cases"] = [
        "signed calibration ties", "register shadow/readback/commit", "setpoint/gain endpoints",
        "calibration saturation", "PI rounding ties",
        "negative error", "anti-windup", "PWM exact off/full/partial", "ADC rails 0 and 4095",
        "invalid calibration cannot clear", "overtemperature safe clear", "commanded shutdown clear",
    ]
    write_summary()


@cocotb.test()
async def stale_fault_after_three_control_ticks(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.reset_n.value = 0
    dut.adc_code.value = 1
    dut.adc_valid.value = 0
    dut.cfg_valid.value = 0
    dut.cfg_write.value = 0
    dut.cfg_addr.value = 0
    dut.cfg_wdata.value = 0
    await Timer(30, unit="ns")
    dut.reset_n.value = 1
    await bus_write(dut, REG_CTRL, 1)
    await bus_write(dut, REG_SETPOINT, 5000)
    await bus_write(dut, REG_KI, 16384)
    await bus_write(dut, REG_OUT_MIN, 256)
    await bus_write(dut, REG_OUT_MAX, 256)
    await commit(dut)
    await wait_sample(dut, 100)
    assert int(dut.duty_q8.value) == 256
    assert int(dut.pwm_out.value) == 1
    integral_before_invalid = int(dut.integrator_q8.value.to_signed())
    assert integral_before_invalid > 0
    await RisingEdge(dut.control_tick)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ps")
    assert int(dut.sample_accepted.value) == 0
    assert int(dut.integrator_q8.value.to_signed()) == integral_before_invalid
    missed_ticks = 1
    for _ in range(160):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ps")
        if int(dut.control_tick.value):
            missed_ticks += 1
        if int(dut.fault_cause.value) & 0x04:
            assert missed_ticks == 3, f"stale fault after {missed_ticks} control ticks"
            break
        if missed_ticks == 3:
            await RisingEdge(dut.clk)
            await Timer(1, unit="ps")
            assert int(dut.fault_cause.value) & 0x04, "stale fault missing one clock after third tick"
            break
    assert int(dut.fault_cause.value) & 0x04
    assert int(dut.pwm_out.value) == 0
    write_summary(stale_asserted_on_missed_tick=missed_ticks,
                  stale_asserted_one_clock_after_tick=True,
                  invalid_sample_left_integrator_unchanged=True,
                  stale_pwm_was_active_before_fault=True)
