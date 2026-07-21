import json
from pathlib import Path

from scripts.run_experiments import CONFIG_PATH, _trial, cycle_constants


def test_frozen_campaign_is_paired_and_has_enough_test_cases():
    cfg = json.loads(CONFIG_PATH.read_text())
    assert cfg["frozen"]
    assert len(cfg["heldout_scenarios"]) >= 20
    assert len(cfg["seed_ids"]) >= 3
    assert len({x["id"] for x in cfg["heldout_scenarios"]}) == len(cfg["heldout_scenarios"])


def test_evaluation_cycle_uses_feasible_temperatures_and_real_durations():
    cfg = json.loads(CONFIG_PATH.read_text())
    plant = cfg["baseline"]
    cycle = cfg["cycle"]
    # At nominal maximum duty, calculate the positive fixed point including
    # the stated heater TCR. The chosen initial and stepped setpoints are below it.
    import scipy.optimize
    r0, tcr, ref = plant["heater_r_ohm"], plant["r_tcr_per_k"], 25
    maximum_temp = scipy.optimize.brentq(lambda t: plant["ambient_c"] + plant["r_th_k_per_w"] * plant["heater_v"]**2 / (r0*(1+tcr*(t-ref))) - t, 25, 350)
    assert cycle["initial_setpoint_c"] + cycle["step_c"] < maximum_temp
    tau, dt, warm, hold, cool = cycle_constants(cfg)
    assert warm * dt >= 3 * tau
    assert hold * dt >= 1.5 * tau
    assert cool * dt >= 2 * tau


def test_trace_replay_is_deterministic_and_keeps_off_samples_invalid():
    cfg = json.loads(CONFIG_PATH.read_text())
    scenario = cfg["heldout_scenarios"][0]
    params = {"kp":.04,"ki":.00015}
    a, ta = _trial(scenario, "pi", 11, params, cfg)
    b, tb = _trial(scenario, "pi", 11, params, cfg)
    assert a == b and ta == tb
    assert ta[0]["sample_valid"] == 0
    assert any(row["phase"] == "cooldown" and row["sample_valid"] == 0 for row in ta)
