"""Run or verify the frozen paired v5 RTL robustness campaign."""
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_manifest import sha256_file, write_manifest
from scripts.run_rtl_study import run_trial

PROTOCOL = ROOT / "configs/rtl_study_v5.json"
REPORT = ROOT / "reports/rtl_study_v5.json"
LABELS = ("baseline", "candidate")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def gates(metrics, limits):
    return {
        "hold_rmse": metrics["rmse_hold_c"] <= limits["hold_rmse_c"],
        "hold_overshoot": metrics["overshoot_hold_c"] <= limits["hold_overshoot_c"],
        "no_powered_fault": metrics["powered_fault_count"] == limits["powered_fault_count"],
        "settled_after_step": metrics["settling_time_after_step_s"] is not None,
    }


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_trace(rows, metrics, robustness):
    dt = metrics["control_dt_s"]
    require(len(rows) == metrics["sample_count"], "trace length")
    hold = [row for row in rows if row["phase"] == "hold"]
    post = [row for row in hold if row["post_step"] == "1"]
    errors = [float(row["temp_c"]) - float(row["setpoint_c"]) for row in hold]
    post_errors = errors[-len(post):]
    dwell = robustness["settling_dwell_samples"]
    band = robustness["settling_band_c"]
    settling = next((i * dt for i in range(len(post) - dwell + 1)
                     if max(map(abs, post_errors[i:i + dwell])) <= band), None)
    require(bool(post) and settling == metrics["settling_time_after_step_s"], "settling")
    require(sum(int(row["fault_cause"]) != 0 for row in rows if row["phase"] != "cooldown")
            == metrics["powered_fault_count"], "powered faults")
    computed = {
        "rmse_hold_c": math.sqrt(sum(e * e for e in errors) / len(errors)),
        "overshoot_hold_c": max(0.0, max(errors)),
        "energy_total_j": dt * sum(float(row["heater_power_w"]) for row in rows),
        "sensing_energy_j": dt * sum(float(row["sensing_power_w"]) for row in rows),
        "peak_temperature_c": max(float(row["temp_c"]) for row in rows),
    }
    for key, value in computed.items():
        require(math.isclose(value, metrics[key], rel_tol=1e-10, abs_tol=1e-12), key)
    require(all(float(row["heater_power_w"]) == 0 for row in rows
                if row["phase"] == "cooldown" or int(row["fault_cause"])),
            "heater applied while disabled or faulted")
    require(all(math.isclose(float(row["t_s"]), i * dt) for i, row in enumerate(rows)), "sample grid")


def verify(report):
    protocol = read_json(PROTOCOL)
    result = read_json(report)
    manifest = read_json(ROOT / result["manifest"])
    require(manifest["status"] == "complete", "campaign did not complete")
    require(manifest["input_sha256"][PROTOCOL.relative_to(ROOT).as_posix()] == sha256_file(PROTOCOL),
            "frozen protocol checksum")
    archive = ROOT / result["archive"]
    require(manifest["outputs"][result["archive"]] == sha256_file(archive), "archive checksum")
    require(manifest["outputs"][report.relative_to(ROOT).as_posix()] == sha256_file(report),
            "report checksum")
    expected = [(case, label, supply) for case in protocol["evaluation"]
                for label, supply in zip(LABELS, protocol["heater_supplies_v"], strict=True)]
    require(len(result["evaluation"]) == len(expected), "paired evaluation count")
    nominal = read_json(ROOT / "configs/evaluation_v1.json")["baseline"]
    timings, calibrations, run_ids = set(), set(), set()
    with ZipFile(archive) as evidence:
        for row, (case, label, supply) in zip(result["evaluation"], expected, strict=True):
            metrics = row["metrics"]
            require((row["label"], row["case_id"], row["heater_voltage_v"]) ==
                    (label, case["id"], supply), "pair identity")
            run_id = metrics["run_id"]
            require(run_id not in run_ids, "reused simulator run")
            run_ids.add(run_id)
            prefix = f"results/raw/experiments/{run_id}"
            per_run = json.loads(evidence.read(f"{prefix}/manifest.json"))
            require(per_run["status"] == "complete" and per_run["seed"] == case["seed"]
                    and per_run["source_commit"] == manifest["source_commit"]
                    and per_run["source_sha256"] == manifest["source_sha256"]
                    and per_run["tool_versions"] == manifest["tool_versions"],
                    f"{run_id} provenance")
            for member, digest in per_run["outputs"].items():
                require(hashlib.sha256(evidence.read(member)).hexdigest() == digest, member)
            require(metrics == json.loads(evidence.read(f"{prefix}/metrics.json")), "metrics copy")
            require(row["case_id"] == metrics["scenario_id"] and metrics["case"] == case
                    and metrics["heater_voltage_v"] == supply and not metrics["training_only"],
                    f"{run_id} case configuration")
            for key, value in protocol["fixed_controller"].items():
                observed = metrics["readout"]["calibration_c"] if key == "calibration_c" else metrics[key]
                require(observed == value, f"{run_id} controller settings")
            for parameter, scale in (("heater_r_ohm", "heater_r_scale"), ("r_tcr_per_k", "tcr_scale"),
                                     ("r_th_k_per_w", "rth_scale"), ("c_th_j_per_k", "cth_scale")):
                require(metrics["applied_plant"][parameter] == nominal[parameter] * case[scale],
                        f"{run_id} applied plant")
            for parameter in ("delay_samples", "gain_error", "offset_v", "noise_rms_v"):
                require(metrics["readout"][parameter] == case[parameter], f"{run_id} applied readout")
            calibrations.add((metrics["readout"]["calibration_gain_q14"],
                              metrics["readout"]["calibration_offset_q6"]))
            trace = list(csv.DictReader(io.StringIO(evidence.read(f"{prefix}/trace.csv").decode())))
            timings.add((len(trace), sum(r["phase"] == "hold" for r in trace),
                         sum(r["post_step"] == "1" for r in trace)))
            verify_trace(trace, metrics, protocol["robustness"])
            require(row["gates"] == gates(metrics, protocol["engineering_limits"]), f"{run_id} gates")
            require(b"PASS=1 FAIL=0" in evidence.read(row["simulator_log"]), f"{run_id} RTL log")
    require(len(timings) == 1 and len(calibrations) == 1, "cycle timing or calibration varied")
    print(f"Verified {len(run_ids)} simulator traces, their manifest hashes, and the paired gates.")


def run():
    protocol = read_json(PROTOCOL)
    require(not protocol["training"], "v5 holds controller coefficients fixed")
    started = datetime.now(timezone.utc)
    run_id = "rtl-robustness-" + started.strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "results/rtl_study" / run_id
    output.mkdir(parents=True)
    archive = output / "evidence.zip"
    manifest = output / "manifest.json"
    print(f"Study output: {output}", flush=True)
    write_json(output / "protocol.json", protocol)
    evaluation = []
    tools = {}
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as evidence:
        evidence.write(output / "protocol.json", PROTOCOL.relative_to(ROOT))
        for case in protocol["evaluation"]:
            for label, supply in zip(LABELS, protocol["heater_supplies_v"], strict=True):
                row = dict(case_id=case["id"], label=label, heater_voltage_v=supply)
                try:
                    metrics = run_trial(case, {**protocol["fixed_controller"], "heater_v": supply},
                                        label, PROTOCOL, output)
                    metrics.pop("study_label")
                    raw = ROOT / "results/raw/experiments" / metrics["run_id"]
                    for file in sorted(raw.iterdir()):
                        evidence.write(file, file.relative_to(ROOT))
                    tools = read_json(raw / "manifest.json")["tool_versions"]
                    row.update(metrics=metrics, gates=gates(metrics, protocol["engineering_limits"]))
                except (subprocess.CalledProcessError, StopIteration) as error:
                    row["simulation_error"] = str(error)
                log, = output.glob(f"{label}-{case['id']}-*.log")
                row["simulator_log"] = log.relative_to(ROOT).as_posix()
                evidence.write(log, row["simulator_log"])
                evaluation.append(row)
            print(case["id"], [row.get("gates", "simulation error") for row in evaluation[-2:]], flush=True)

    summary = dict(run_id=run_id, protocol=protocol["protocol"], archive=archive.relative_to(ROOT).as_posix(),
                   manifest=manifest.relative_to(ROOT).as_posix(), evaluation=evaluation)
    failed = any("simulation_error" in row for row in evaluation)
    result = output / "summary.json" if failed else REPORT
    write_json(result, summary)
    write_manifest(
        manifest, run_id=run_id, command=[sys.executable, "scripts/run_rtl_robustness.py"],
        input_paths=[PROTOCOL, Path(__file__), ROOT / "configs/evaluation_v1.json"],
        seed=[case["seed"] for case in protocol["evaluation"]], started=started,
        status="failed" if failed else "complete", output_paths=[archive, result],
        extra={"tool_versions": tools},
    )
    if failed:
        raise SystemExit(f"Simulator failures recorded in {result}")
    verify(REPORT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="audit archived v5 traces")
    if parser.parse_args().verify:
        verify(REPORT)
    else:
        run()


if __name__ == "__main__":
    main()
