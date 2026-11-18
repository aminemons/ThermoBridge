"""Generate the complete v5 comparison table and the study figure."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def main():
    report = json.loads((REPORTS / "rtl_study_v5.json").read_text())
    protocol = json.loads((ROOT / "configs/rtl_study_v5.json").read_text())
    rows = report["evaluation"]
    metrics = (
        "rmse_hold_c", "overshoot_hold_c", "settling_time_after_step_s", "energy_total_j",
        "sensing_energy_j", "powered_fault_count", "peak_temperature_c",
    )
    with (REPORTS / "rtl_study_v5.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        gate_names = tuple(rows[0]["gates"])
        writer.writerow(("case_id", "scenario", "seed", "heater_voltage_v", "run_id",
                         *metrics, *gate_names))
        for row in rows:
            record = row["metrics"]
            writer.writerow((row["case_id"], record["case"]["scenario"], record["seed"],
                             row["heater_voltage_v"], record["run_id"],
                             *(record[key] for key in metrics),
                             *(row["gates"][name] for name in gate_names)))

    baseline = [r["metrics"] for r in rows if r["label"] == "baseline"]
    candidate = [r["metrics"] for r in rows if r["label"] == "candidate"]
    baseline_rmse = [m["rmse_hold_c"] for m in baseline]
    candidate_rmse = [m["rmse_hold_c"] for m in candidate]
    paired = list(zip(baseline, candidate, strict=True))
    delta_energy = [(b["energy_total_j"] - a["energy_total_j"]) * 1e6 for a, b in paired]
    delta_rmse = [b["rmse_hold_c"] - a["rmse_hold_c"] for a, b in paired]
    limit = protocol["engineering_limits"]["hold_rmse_c"]
    plt.rcParams["svg.hashsalt"] = "thermobridge-rtl-v5"
    fig, (ax, delta) = plt.subplots(1, 2, figsize=(7.1, 3.0), layout="constrained")
    lower = min(*baseline_rmse, *candidate_rmse, limit) * .85
    upper = max(*baseline_rmse, *candidate_rmse, limit) * 1.15
    ax.plot([lower, upper], [lower, upper], color="#657389", linestyle="--", linewidth=1)
    ax.axvline(limit, color="#aa592e", linestyle=":", linewidth=1.2)
    ax.axhline(limit, color="#aa592e", linestyle=":", linewidth=1.2)
    ax.scatter(baseline_rmse, candidate_rmse, color="#146577", s=15, alpha=.65)
    ticks = [value for value in (1, 1.5, 2, 3, 5, 10, 20, 30) if lower <= value <= upper]
    ax.set(xscale="log", yscale="log", xlim=(lower, upper), ylim=(lower, upper),
           xlabel="0.15 V hold RMSE (°C)",
           ylabel="0.18 V hold RMSE (°C)", title="(a) Paired tracking")
    ax.set_xticks(ticks, [str(value) for value in ticks])
    ax.set_yticks(ticks, [str(value) for value in ticks])
    ax.minorticks_off()
    delta.axvline(0, color="#657389", linestyle="--", linewidth=1)
    delta.axhline(0, color="#657389", linestyle="--", linewidth=1)
    delta.scatter(delta_energy, delta_rmse, color="#146577", s=15, alpha=.65)
    delta.set(xlabel="Change in heater energy (µJ)", ylabel="Change in hold RMSE (°C)",
              title="(b) Energy and tracking trade-off")
    for panel in (ax, delta):
        panel.grid(alpha=.18)
    svg = REPORTS / "rtl_study_v5_figure.svg"
    fig.savefig(svg, metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
