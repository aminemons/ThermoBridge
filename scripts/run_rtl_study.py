"""Run frozen actual-RTL training and paired evaluation protocols."""
from datetime import datetime, timezone
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_manifest import write_manifest


def run_trial(case, coefficients, label, protocol_path, output):
    calibration = coefficients.get("calibration_c", [40, 80])
    arguments = [
        sys.executable, "scripts/run_rtl_experiment.py",
        "--case", case["id"], "--protocol", str(protocol_path),
        "--kp-q14", str(coefficients["kp_q14"]),
        "--ki-q14", str(coefficients["ki_per_sample_q14"]),
        "--calibration-c", *map(str, calibration),
    ]
    name = (
        f"{label}-{case['id']}-{coefficients['kp_q14']}-"
        f"{coefficients['ki_per_sample_q14']}-{calibration[0]}-{calibration[1]}"
    )
    log = output / f"{name}.log"
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(
            arguments, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            check=True,
        )
    marker = "RTL-in-loop trace saved: "
    owned_run = next(
        Path(line[len(marker):])
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith(marker)
    )
    metrics = json.loads((owned_run / "metrics.json").read_text())
    metrics["study_label"] = label
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "configs/rtl_study_v2.json"
    )
    arguments = parser.parse_args()
    protocol_path = arguments.protocol.resolve()
    protocol = json.loads(protocol_path.read_text())
    report_name = protocol.get("report_name", "rtl_study_v2.json")
    if Path(report_name).name != report_name:
        parser.error("The report name must be a filename")
    started = datetime.now(timezone.utc)
    run_id = "rtl-study-" + started.strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "results/rtl_study" / run_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")

    training = []
    candidates = itertools.product(
        protocol["candidate_kp_q14"],
        protocol["candidate_ki_per_sample_q14"],
        protocol.get("calibration_candidates_c", [[40, 80]]),
    )
    for kp, ki, calibration in candidates:
        coefficients = {
            "kp_q14": kp,
            "ki_per_sample_q14": ki,
            "calibration_c": calibration,
        }
        scores = [
            run_trial(case, coefficients, "training", protocol_path, output)
            for case in protocol["training"]
        ]
        candidate = {
            **coefficients,
            "mean_training_rmse_c": sum(s["rmse_hold_c"] for s in scores) / len(scores),
            "runs": scores,
        }
        training.append(candidate)
        print("TRAIN", kp, ki, calibration, round(candidate["mean_training_rmse_c"], 4), flush=True)

    best = min(training, key=lambda candidate: candidate["mean_training_rmse_c"])
    selected = {key: value for key, value in best.items() if key != "runs"}
    (output / "selection.json").write_text(json.dumps(selected, indent=2) + "\n")
    evaluation = []
    for case in protocol["evaluation"]:
        paired = [
            run_trial(case, coefficients, label, protocol_path, output)
            for label, coefficients in [
                ("baseline", protocol["baseline"]), ("retuned", selected)
            ]
        ]
        evaluation.extend(paired)
        print("TEST", case["id"], *[round(m["rmse_hold_c"], 4) for m in paired], flush=True)

    summary = {
        "protocol": protocol["protocol"], "run_id": run_id,
        "selected": selected, "training": training, "evaluation": evaluation,
        "rtl_modified": False, "baseline_result_retained": True,
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    write_manifest(
        output / "manifest.json", run_id=run_id,
        command=[sys.executable, "scripts/run_rtl_study.py", *sys.argv[1:]],
        input_paths=[protocol_path, ROOT / "scripts/run_rtl_study.py"],
        seed=[case["seed"] for case in protocol["evaluation"]],
        started=started, status="complete",
        output_paths=[summary_path, output / "protocol.json", output / "selection.json"],
    )
    report = {
        "run": output.relative_to(ROOT).as_posix(),
        "protocol": protocol["protocol"], "selected": selected,
        "evaluation": evaluation, "scope": protocol["scope"],
    }
    temporary = ROOT / "reports" / f".{run_id}.json"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(ROOT / "reports" / report_name)
    print("Completed", output, flush=True)


if __name__ == "__main__":
    main()
