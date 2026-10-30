"""Frozen paired controller/readout campaign on the simple RC plant.

This is a Python reference simulation, not an RTL-in-loop result. Run with
`python scripts/run_experiments.py`; outputs are immutable run directories.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.physics.rc import ThermalRC
from src.sensing import HeaterReadout, ReadoutConfig, RTNChannel
from scripts.run_manifest import write_manifest

CONFIG_PATH = ROOT / "configs/evaluation_v1.json"
LUT_PATH = ROOT / "configs/feedforward_lut.json"


def feedforward_q8(setpoint_c: float) -> int:
    """Interpolate the shared table; RTL uses a step index between table knots."""
    table=json.loads(LUT_PATH.read_text(encoding="utf-8"))["bins"]
    if setpoint_c < table[0]["setpoint_c"]: return 0
    for a,b in zip(table,table[1:]):
        if setpoint_c <= b["setpoint_c"]:
            fraction=(setpoint_c-a["setpoint_c"])/(b["setpoint_c"]-a["setpoint_c"])
            return min(256,max(0,round(a["duty_q8"]+fraction*(b["duty_q8"]-a["duty_q8"]))))
    return 256


def cycle_constants(cfg):
    base = cfg["baseline"]
    tau = base["r_th_k_per_w"] * base["c_th_j_per_k"]
    dt = cfg["time_step_s"]
    return tau, dt, round(cfg["cycle"]["warmup_tau"] * tau / dt), round(cfg["cycle"]["hold_tau"] * tau / dt), round(cfg["cycle"]["cool_tau"] * tau / dt)


def _signed_sat(value: int, width: int) -> int:
    lo, hi = -(1 << (width-1)), (1 << (width-1))-1
    return min(hi, max(lo, value))


def _fixed_pi_output(error_c: float, integral_c_s: float, kp: float, ki: float, ff: float, width: int) -> tuple[float, float]:
    """Separate Q6 temperature/Q14 coefficient/Q8 duty arithmetic study.

    Each multiply rounds to nearest/even before the Q8 sum; the error
    accumulator is signed `width` bits in Q6 °C·s and saturates. These are
    controller arithmetic profiles, not the exact primary RTL accumulator model
    and not RTL-in-loop measurements.
    """
    q6 = 1 << 6
    q14 = 1 << 14
    q8 = 1 << 8
    eq = _signed_sat(round(error_c*q6), width)
    iq = _signed_sat(round(integral_c_s*q6), width)
    kpq = _signed_sat(round(kp*q14), width)
    kiq = _signed_sat(round(ki*q14), width)
    # (Q14 * Q6) -> Q8: shift 12; Python round uses ties-to-even.
    p_q8 = round(kpq*eq/(1 << 12))
    i_q8 = round(kiq*iq/(1 << 12))
    ff_q8 = round(ff*q8)
    duty_q8 = min(256, max(0, ff_q8+p_q8+i_q8))
    return duty_q8/q8, iq/q6


def _trial(scenario, controller_name, seed_id, params, cfg, record=True):
    base = cfg["baseline"]
    tau, dt, nw, nh, nc = cycle_constants(cfg)
    plant = ThermalRC(
        r_th_k_per_w=base["r_th_k_per_w"] * scenario["rth_scale"],
        c_th_j_per_k=base["c_th_j_per_k"] * scenario["cth_scale"],
        ambient_c=scenario["ambient_c"], heater_v=base["heater_v"],
        heater_r_ohm=base["heater_r_ohm"] * scenario["heater_r_scale"],
        r_tcr_per_k=base["r_tcr_per_k"] * scenario["tcr_scale"],
    )
    rng_seed = seed_id + 100000 * (sum(ord(ch) for ch in scenario["id"]) % 997)
    ro = HeaterReadout(ReadoutConfig(
        r0_ohm=plant.heater_r_ohm, tcr_per_k=plant.r_tcr_per_k,
        reference_c=base.get("reference_c", 25.0), excitation_v=0.018, front_end_gain=100.0,
        divider_reference_ohm=base["heater_r_ohm"], adc_reference_v=1.8,
        valid_temperature_c=(20.0, 350.0),
        calibration_r0_ohm=base["heater_r_ohm"], calibration_tcr_per_k=base["r_tcr_per_k"],
        gain_error_fraction=scenario["gain_error"], offset_error_v=scenario["offset_v"],
        noise_rms_v=scenario["noise_rms_v"], delay_samples=scenario["delay_samples"],
    ), seed=rng_seed)
    cycle = cfg["cycle"]
    initial_sp = cycle["initial_setpoint_c"]
    step_sp = initial_sp + cycle["step_c"]
    total = nw + nh + nc
    step_i = nw + round(nh * cycle["step_at_hold_fraction"])
    cool_i = nw + nh
    temp = plant.ambient_c
    latest = temp
    integral = 0.0
    duty_prev = 0.0
    temps, duties, setpoints, powers, errors, measurement_errors, valid_list = [], [], [], [], [], [], []
    phase_energy = {"warmup": 0.0, "hold": 0.0, "cooldown": 0.0}
    phase_sense_energy = {"warmup": 0.0, "hold": 0.0, "cooldown": 0.0}
    for i in range(total):
        sp = initial_sp if i < step_i else step_sp
        phase = "warmup" if i < nw else "hold" if i < cool_i else "cooldown"
        if phase == "cooldown":
            duty = 0.0
        else:
            e = sp - latest
            fixed_width = int(controller_name.split("_")[0][5:]) if controller_name.startswith("fixed") else None
            if fixed_width:
                e = _signed_sat(round(e * 64), fixed_width) / 64.0
            if controller_name == "bangbang":
                if e > params["hysteresis_c"]:
                    duty = 1.0
                elif e < -params["hysteresis_c"]:
                    duty = 0.0
                else:
                    duty = duty_prev
            else:
                # Back-calculation-free conditional integration: integrate only
                # when unsaturated or when error drives away from saturation.
                correction = params["kp"] * e + params["ki"] * integral
                kind = controller_name.split("_")[-1] if controller_name.startswith("fixed") else controller_name
                if kind == "ffpi":
                    ff = feedforward_q8(sp) / 256.0
                else:
                    ff = 0.0
                unsat = ff + correction
                if fixed_width:
                    duty, _ = _fixed_pi_output(e, integral, params["kp"], params["ki"], ff, fixed_width)
                else:
                    duty = min(1.0, max(0.0, unsat))
                if 0.0 < unsat < 1.0 or (unsat >= 1 and e < 0) or (unsat <= 0 and e > 0):
                    integral += e * dt
                    if fixed_width:
                        integral = _signed_sat(round(integral * 64), fixed_width) / 64.0
        duty = min(1.0, max(0.0, duty))
        # Synchronized low-duty measurement pulse: when regulation asks for
        # zero output, apply a 1/256 heater pulse during this sampled window so
        # resistance remains observable. Its real Joule energy is included.
        if phase != "cooldown" and duty == 0.0:
            duty = 1.0 / 256.0
        p = plant.power(duty, temp)
        # Actual heater-terminal V*I integral for this averaged-PWM interval.
        phase_energy[phase] += p * dt
        temps.append(temp); duties.append(duty); setpoints.append(sp); powers.append(p)
        errors.append(temp - sp)
        # Plant advances under the controller's actual duty; resistance readout
        # is captured synchronously and delayed by the configured sample count.
        temp = plant.step(temp, duty, dt)
        sample = ro.sample(temp, duty)
        phase_sense_energy[phase] += sample.sense_power_w * dt
        if sample.valid and math.isfinite(sample.temperature_estimate_c):
            latest = sample.temperature_estimate_c
        measurement_errors.append((latest - sp) if sample.valid else math.nan)
        valid_list.append(sample.valid)
        duty_prev = duty
    # RMSE only over valid measured samples in controlled warmup/hold windows.
    controlled = list(range(nw, cool_i))
    warmup_indices = list(range(nw))
    rmse = math.sqrt(sum(errors[i] ** 2 for i in controlled) / len(controlled)) if controlled else math.nan
    warmup_rmse = math.sqrt(sum(errors[i] ** 2 for i in warmup_indices) / len(warmup_indices)) if warmup_indices else math.nan
    max_abs = max((abs(errors[i]) for i in controlled), default=math.nan)
    overshoots = []
    for start, target in ((0, initial_sp), (step_i, step_sp)):
        end = step_i if start == 0 else cool_i
        overshoots.append(max([temps[k] - target for k in range(start, end)] + [0.0]))
    settle = None
    dwell_n = max(1, round(cycle["settling_dwell_s"] / dt))
    for i in range(step_i, cool_i - dwell_n + 1):
        if all(abs(errors[j]) <= cycle["settling_band_c"] for j in range(i, i + dwell_n)):
            settle = (i - step_i) * dt
            break
    result = {
        "scenario_id": scenario["id"], "controller": controller_name, "seed": seed_id,
        "status": "ok" if settle is not None else "settling_failure",
        "rmse_c": rmse, "warmup_rmse_c": warmup_rmse, "max_abs_error_c": max_abs,
        "overshoot_pre_step_c": overshoots[0], "overshoot_post_step_c": overshoots[1],
        "settling_time_after_step_s": settle if settle is not None else "",
        "energy_warmup_j": phase_energy["warmup"], "energy_hold_j": phase_energy["hold"],
        "energy_cooldown_j": phase_energy["cooldown"], "energy_total_j": sum(phase_energy.values()),
        "sensing_energy_j": sum(phase_sense_energy.values()),
        "sensing_energy_upper_bound_j": sum(phase_sense_energy.values()),
        "sensing_excitation_v": ro.config.excitation_v, "sensing_front_end_gain": ro.config.front_end_gain,
        "energy_total_including_sensing_j": sum(phase_energy.values()) + sum(phase_sense_energy.values()),
        "valid_sample_fraction": sum(valid_list) / len(valid_list),
        "duration_s": total * dt, "plant_tau_s": plant.tau_s,
        "simulation_kind": "python_reference_rc_replay",
        "arithmetic_profile": (f"signed {controller_name.split('_')[0][5:]}-bit Q6/Q14/Q8 saturating Python model" if controller_name.startswith("fixed") else "IEEE-754 Python float reference"),
    }
    trace = None
    if record:
        trace = [{"t_s": i*dt, "temp_c": temps[i], "setpoint_c": setpoints[i], "duty": duties[i], "heater_power_w": powers[i], "tracking_error_c": errors[i], "measured_error_c": measurement_errors[i], "sample_valid": int(valid_list[i]), "phase": "warmup" if i < nw else "hold" if i < cool_i else "cooldown"} for i in range(total)]
    return result, trace


def tune_controllers(cfg):
    """A small training-only grid; held-out scenarios never influence gains."""
    training = cfg["training_scenarios"]
    grid = [(kp, ki) for kp in (0.002, 0.005, 0.01, 0.02, 0.04, 0.08) for ki in (0.005, 0.02, 0.05, 0.1, 0.2, 0.4)]
    chosen = {}
    candidates = {}
    for kind in ("pi", "ffpi"):
        scores = []
        for kp, ki in grid:
            trial_scores = []
            for scenario in training:
                for seed in (3, 7):
                    res, _ = _trial(scenario, kind, seed, {"kp":kp,"ki":ki}, cfg, record=False)
                    rmse = res["rmse_c"]
                    # Failed settling incurs explicit penalty, selection only.
                    score = rmse + (20.0 if res["status"] != "ok" else 0.0)
                    trial_scores.append(score)
            scores.append((sum(trial_scores)/len(trial_scores), kp, ki))
        best = min(scores)
        chosen[kind] = {"kp":best[1],"ki":best[2]}
        candidates[kind] = [{"mean_training_score":a,"kp":b,"ki":c} for a,b,c in sorted(scores)[:5]]
    bands=[]
    for band in (0.5, 1.0, 2.0, 3.0):
        scores=[]
        for scenario in training:
            for seed in (3,7):
                res,_=_trial(scenario,"bangbang",seed,{"hysteresis_c":band},cfg,record=False)
                scores.append(res["rmse_c"]+(20.0 if res["status"]!="ok" else 0.0))
        bands.append((sum(scores)/len(scores),band))
    chosen["bangbang"]={"hysteresis_c":min(bands)[1]}
    candidates["bangbang"]=[{"mean_training_score":a,"hysteresis_c":b} for a,b in sorted(bands)]
    return chosen, candidates


def run(outdir: Path):
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc)
    run_id = "exp-" + started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    target = outdir / run_id
    target.mkdir(parents=True, exist_ok=False)
    (target / "config_snapshot.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    params, tune = tune_controllers(cfg)
    (target / "training_tuning.json").write_text(json.dumps({"training_only":True,"selected":params,"top_grid_candidates":tune}, indent=2)+"\n",encoding="utf-8")
    summaries = []
    trace_path = target / "traces.csv"
    with trace_path.open("w", newline="", encoding="utf-8") as ftrace:
        trace_writer = None
        for scenario in cfg["heldout_scenarios"]:
            for seed in cfg["seed_ids"]:
                for kind in ("bangbang", "pi", "ffpi"):
                    result, trace = _trial(scenario, kind, seed, params[kind], cfg)
                    result["parameters_json"] = json.dumps(params[kind], sort_keys=True)
                    summaries.append(result)
                    for row in trace:
                        row.update({"scenario_id":scenario["id"],"seed":seed,"controller":kind})
                        if trace_writer is None:
                            trace_writer = csv.DictWriter(ftrace, fieldnames=list(row))
                            trace_writer.writeheader()
                        trace_writer.writerow(row)
    # Arithmetic-width ablation uses identical coefficients (selected only on
    # training data) and identical paired seeds; no per-width retuning.
    for width in (16, 20, 24):
        for base_kind in ("pi", "ffpi"):
            fixed_kind = f"fixed{width}_{base_kind}"
            for scenario in cfg["heldout_scenarios"]:
                for seed in cfg["seed_ids"]:
                    result, _ = _trial(scenario, fixed_kind, seed, params[base_kind], cfg, record=False)
                    result["parameters_json"] = json.dumps(params[base_kind], sort_keys=True)
                    result["arithmetic_profile"] = f"signed {width}-bit Q6 temperature/integrator; signed Q14 gains; Q8 duty; saturating accumulators; float-tuned shared coefficients"
                    summaries.append(result)
    summary_path = target / "metrics.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summaries[0]))
        w.writeheader(); w.writerows(summaries)
    # Separate RTN channel characterization: no gas response and no coupling to
    # the heater control loop is asserted by this phenomenological process.
    rtn = RTNChannel(occupancy_p=0.35, total_rate_per_s=2.0, amplitude_s=2e-6, seed=19)
    dt = cfg["time_step_s"]
    rtn_trace = rtn.simulate([i*dt for i in range(25000)])
    states = [state for state, _ in rtn_trace]
    rtn_stats = rtn.dwell_statistics(states, dt)
    (target / "rtn_statistics.json").write_text(json.dumps({"model":"two-state CTMC phenomenological conductance perturbation","p":rtn.occupancy_p,"total_rate_per_s":rtn.total_rate_per_s,"rate_0_to_1_per_s":rtn.rate_0_to_1,"rate_1_to_0_per_s":rtn.rate_1_to_0,"amplitude_s":rtn.amplitude_s,"seed":rtn.seed,"sample_dt_s":dt,"sample_count":len(states),"statistics":rtn_stats},indent=2)+"\n",encoding="utf-8")
    log_path=target/"run.log"
    status_counts={}
    for item in summaries:
        status_counts[item["controller"]]=status_counts.get(item["controller"],0)+int(item["status"]!="ok")
    log_path.write_text("ThermoBridge paired Python reference campaign completed.\n"+f"scenario_count={len(cfg['heldout_scenarios'])}; seeds={cfg['seed_ids']}; rows={len(summaries)}\n"+f"controllers_with_settling_failures={status_counts}\n"+f"source_model={cfg['plant']}\nfeedforward_lut={LUT_PATH.name}\n",encoding="utf-8")
    manifest_path = target / "manifest.json"
    input_paths=[CONFIG_PATH,LUT_PATH,ROOT/"configs/physics.json",ROOT/"src/physics/fvm.py",ROOT/"src/models/compact.py",ROOT/"outputs/physics/validation.json"]
    write_manifest(manifest_path, run_id=run_id, command=[sys.executable,"scripts/run_experiments.py"], input_paths=input_paths, seed=cfg["seed_ids"], started=started, status="complete", output_paths=[trace_path,summary_path,target/"training_tuning.json",target/"rtn_statistics.json",log_path], extra={"simulation_kind":"Python reference only; not RTL-in-loop","scenario_count":len(cfg["heldout_scenarios"]),"paired_seeds_per_scenario":len(cfg["seed_ids"]),"controller_count":3,"tuning_scenarios":[x["id"] for x in cfg["training_scenarios"]],"fitted_rom":{"r_th_k_per_w":cfg["baseline"]["r_th_k_per_w"],"c_th_j_per_k":cfg["baseline"]["c_th_j_per_k"],"tau_s":cfg["baseline"]["fit_tau_s"]}})
    print(f"{target}\ntrials={len(summaries)} trace_rows={len(cfg['heldout_scenarios'])*len(cfg['seed_ids'])*3*sum(cycle_constants(cfg)[2:])} manifest_status={manifest_path}")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=ROOT / "results/raw/experiments")
    args = parser.parse_args()
    run(args.outdir)
