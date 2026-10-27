"""Generate controller figures only from a completed experiment run."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_manifest import write_manifest


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def run(run_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    metrics_path, traces_path = run_dir / "metrics.csv", run_dir / "traces.csv"
    if not metrics_path.exists() or not traces_path.exists():
        raise FileNotFoundError("metrics.csv and traces.csv are required from a completed campaign")
    metrics = list(csv.DictReader(metrics_path.open(encoding="utf-8", newline="")))
    traces = list(csv.DictReader(traces_path.open(encoding="utf-8", newline="")))
    figdir = ROOT / "docs/figures"
    procdir = ROOT / "results/processed"
    figdir.mkdir(parents=True, exist_ok=True); procdir.mkdir(parents=True, exist_ok=True)
    run_id = "fig-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]

    groups = {}
    for row in metrics:
        groups.setdefault(row["controller"], []).append(row)
    agg_path = procdir / f"experiment_summary_{run_dir.name}.csv"
    with agg_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["controller", "arithmetic_profile", "n", "failure_count", "failure_rate", "rmse_mean_c", "rmse_median_c", "rmse_worst_c", "energy_mean_j", "energy_median_j", "overshoot_mean_c", "settling_median_s"]
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
        for controller, rows in sorted(groups.items()):
            rmses=[float(x["rmse_c"]) for x in rows]
            energies=[float(x["energy_total_j"]) for x in rows]
            overs=[float(x["overshoot_post_step_c"]) for x in rows]
            settles=[float(x["settling_time_after_step_s"]) for x in rows if x["settling_time_after_step_s"]]
            w.writerow({"controller":controller,"arithmetic_profile":rows[0]["arithmetic_profile"],"n":len(rows),"failure_count":sum(x["status"]!="ok" for x in rows),"failure_rate":sum(x["status"]!="ok" for x in rows)/len(rows),"rmse_mean_c":mean(rmses),"rmse_median_c":statistics.median(rmses),"rmse_worst_c":max(rmses),"energy_mean_j":mean(energies),"energy_median_j":statistics.median(energies),"overshoot_mean_c":mean(overs),"settling_median_s":statistics.median(settles) if settles else ""})

    main = ["bangbang", "pi", "ffpi"]
    nominal = [x for x in traces if x["scenario_id"]=="E01_nominal" and x["seed"]=="11" and x["controller"] in main]
    fig, axes = plt.subplots(2,1,figsize=(9.2,6.2),sharex=True,layout="constrained")
    colors={"bangbang":"#b45b37","pi":"#356b9a","ffpi":"#248b72"}
    for c in main:
        rows=[x for x in nominal if x["controller"]==c]
        axes[0].plot([float(x["t_s"]) for x in rows],[float(x["temp_c"]) for x in rows],label=c.upper(),color=colors[c],linewidth=1.5)
    rows=[x for x in nominal if x["controller"]=="ffpi"]
    axes[0].step([float(x["t_s"]) for x in rows],[float(x["setpoint_c"]) for x in rows],where="post",color="#333333",linestyle="--",label="setpoint")
    axes[0].set_ylabel("heater temperature (°C)"); axes[0].legend(ncol=4,frameon=False); axes[0].grid(alpha=.2)
    for c in main:
        rows=[x for x in nominal if x["controller"]==c]
        axes[1].step([float(x["t_s"]) for x in rows],[float(x["duty"]) for x in rows],where="post",label=c.upper(),color=colors[c],linewidth=1.1)
    axes[1].set_ylabel("applied duty"); axes[1].set_xlabel("time (s)"); axes[1].set_ylim(-.04,1.04); axes[1].grid(alpha=.2)
    fig.suptitle("Paired nominal cycle (one seed; Python RC reference)")
    p1=figdir/"experiment_paired_trace.png"; s1=figdir/"experiment_paired_trace.svg"; fig.savefig(p1,dpi=180); fig.savefig(s1); plt.close(fig)

    # Mean per paired scenario/seed, with failed settling trials shown explicitly.
    fig, ax=plt.subplots(figsize=(8.5,5.4),layout="constrained")
    cdict={"bangbang":"#b45b37","pi":"#356b9a","ffpi":"#248b72"}
    for c in main:
        rows=[r for r in metrics if r["controller"]==c]
        for r in rows:
            marker="x" if r["status"]!="ok" else "o"
            ax.scatter(float(r["rmse_c"]),float(r["energy_total_j"]),marker=marker,color=cdict[c],alpha=.58,s=25)
        ax.scatter([],[],color=cdict[c],marker="o",label=c.upper())
    ax.scatter([],[],color="#444",marker="x",label="settling failure")
    ax.set_xlabel("hold-window tracking RMSE (°C)"); ax.set_ylabel("heater-terminal cycle energy (J)")
    ax.set_title("Energy and tracking across paired held-out runs"); ax.grid(alpha=.22); ax.legend(frameon=False)
    p2=figdir/"experiment_energy_tracking.png"; s2=figdir/"experiment_energy_tracking.svg"; fig.savefig(p2,dpi=180); fig.savefig(s2); plt.close(fig)

    labels=main+[f"fixed{w}_{k}" for w in (16,20,24) for k in ("pi","ffpi")]
    vals=[[float(r["rmse_c"]) for r in metrics if r["controller"]==lab] for lab in labels]
    fig,ax=plt.subplots(figsize=(10.5,5.6),layout="constrained")
    bp=ax.boxplot(vals,tick_labels=labels,showfliers=False,patch_artist=True)
    for i,patch in enumerate(bp["boxes"]): patch.set_facecolor("#8cb8b2" if i<3 else "#9aabc4")
    failure_rates=[sum(r["controller"]==lab and r["status"]!="ok" for r in metrics)/sum(r["controller"]==lab for r in metrics) for lab in labels]
    ax2=ax.twinx(); ax2.plot(range(1,len(labels)+1),failure_rates,color="#b45b37",marker="D",linewidth=1.2,label="failure rate")
    ax.set_ylabel("hold-window tracking RMSE (°C)"); ax2.set_ylabel("settling failure fraction"); ax2.set_ylim(0,1)
    ax.set_xticklabels(labels,rotation=25,ha="right"); ax.grid(axis="y",alpha=.2); ax.set_title("Robustness and arithmetic-width comparison (same float-tuned gains)")
    p3=figdir/"experiment_robustness_width.png"; s3=figdir/"experiment_robustness_width.svg"; fig.savefig(p3,dpi=180); fig.savefig(s3); plt.close(fig)

    started=datetime.now(timezone.utc)
    manifest=figdir/f"{run_id}.manifest.json"
    write_manifest(manifest,run_id=run_id,command=[sys.executable,"scripts/make_figures.py","--run",str(run_dir)],input_paths=[metrics_path,traces_path],seed=None,started=started,status="complete",output_paths=[agg_path,p1,s1,p2,s2,p3,s3],extra={"source_experiment_run":run_dir.name,"figure_source":"saved CSV data; no fabricated traces"})
    print(f"figures written under {figdir}; summary={agg_path}; manifest={manifest}")


if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--run",type=Path,required=True); args=parser.parse_args(); run(args.run)
