# Reproduce the research snapshot

Reuse the installed image/PDK recorded in [ENVIRONMENT.md](ENVIRONMENT.md). No Docker/image/tools reinstall is needed.

## Windows, existing installation

Open PowerShell in `C:\Users\bouba\eda\ThermoBridge`:

```powershell
python scripts/container.py sync
python scripts/container.py run make test-physics test-rtl
python scripts/container.py run make simulate
python scripts/container.py fetch results/raw/experiments
```

`sync` copies scoped source to `/foss/designs/thermobridge` on the Linux filesystem, preserving unrelated designs. Physical jobs use two workers. Default sync excludes archived data/GDS; explicitly sync `reports results outputs docs README.md release` when archived evidence is needed inside the container. This is a copy, not live two-way synchronization; fetch changed outputs before committing.

## Configured Linux tool environment

```bash
make doctor
make test-physics test-rtl
make simulate
make figures
make synth             # synthesis only
make gds               # explicit, expensive full physical run
make verify-layout     # checks archived GDS/RTL/SDC hashes and physical reports
make release-check     # conditional snapshot; not all targets achieved
python3 scripts/release_check.py --strict  # intentionally fails <=2 C target
python3 scripts/release_check.py --operating-point  # checks the proposed 0.18 V point
```

`simulate` preserves the original frozen campaign. Original training is separate: `python3 scripts/tune_rtl.py`. The new bounded protocol is `python3 scripts/run_rtl_study.py`, followed by fetching `reports/rtl_study_v2.json`, `results/rtl_study`, and `python scripts/fetch_rtl_study.py` for its 46 raw runs. `make sweep` now executes 27 geometries at three conditions with selected 2 um refinements. Full physical design has not been independently rerun from a clean image; retained geometry and the separate STA recheck remain the physical evidence.

## Report on the host

```powershell
python -m pip install -r requirements-report.txt
python scripts/build_article.py
python scripts/release_check.py
```

The article generator reads archived evidence, writes `reports/thermobridge_article.pdf`, and renders README.md from `docs/article.template.md`. Edit that template for reproducible article changes. The earlier `reports/technical_report.pdf` is preserved. New runs receive new IDs; do not overwrite old measurements or select coefficients from held-out results. Host spatial-study packages are recorded in its run manifest, separately from the OSIC environment.

To run the spatial solver on the host, install `requirements-host.txt` as well. Article rendering uses a lightweight shared feature function and does not import SciPy or launch the PDE solver.

## 9 November calibration and operating-point studies

```powershell
python scripts/container.py sync
python scripts/container.py run python3 scripts/run_rtl_study.py --protocol configs/rtl_study_v3.json
python scripts/container.py run python3 scripts/run_rtl_study.py --protocol configs/rtl_study_v4.json
python scripts/container.py run python3 scripts/validate_operating_point.py
python scripts/container.py fetch reports/rtl_study_v3.json reports/rtl_study_v4.json results/rtl_study reports/operating_point_validation.json results/operating_point
python scripts/fetch_rtl_study.py --report reports/rtl_study_v3.json
python scripts/fetch_rtl_study.py --report reports/rtl_study_v4.json
python scripts/check_heating_reference.py
python scripts/release_check.py --operating-point
```

The v3 protocol uses 36 training runs and 16 paired evaluation runs. The v4 protocol uses three fixed-setting training runs and 16 paired evaluations. Its six fresh pairs compare only external heater voltage, 0.15 versus 0.18 V. Gains and calibration come from v3 training. Record the 44% increase in peak available heater power when describing the passing 0.18 V result.

`make simulate-operating-point` provides the standard entry point for the 19-run v4 study. Fetch its outputs and rebuild the article after rerunning it.

Each RTL experiment owns a separate simulator directory and XML result. Its fully qualified test module supports that isolation. The article generator supports `--refresh-figures` for regenerating the archived baseline plots. Normal report generation reuses those images and builds the current operating-point plot.

The current clean-source check exports commit `1e91b8f4308d79f3d539d2b4390815eda2a57033`. It reproduces all 540 original metric rows and baseline RTL energy/RMSE. The command below reproduces the worst fresh 0.18 V case from that extraction.

```powershell
python scripts/check_clean_rtl_case.py --report reports/rtl_study_v4.json --case v4_E03
```

Its recorded RMSE is 1.777189 C with matching energy at relative tolerance 1e-10 and absolute tolerance 1e-12. Concurrent-run checks are recorded in `reports/rtl_isolation.json`.

## Historical material

`release/` preserves an earlier desktop runner/tests. Local `release_out/` and ZIP exports predate final conditional timing and are superseded. Canonical evidence is `reports/asic/summary.json` and `reports/release_snapshot.json`. `reports/asic/manifest.json` is a failed earlier attempt. Selected earlier failure manifests/metrics are retained under `results/history/`; bulky historical traces remain local.

No gate-level power, analogue macro, fabricated sensor or completed PFE sweep is implied. See [LIMITATIONS.md](LIMITATIONS.md).

## Executed clean-source check

`python scripts/clean_reproduce.py` exports a committed Git archive into a new Linux directory in the existing container. The latest source commit is recorded in [reproduction report](../reports/reproduction/summary.json); earlier checks remain in Git history. Tests, the frozen Python campaign, real RTL loop and archived-evidence audit returned zero. `python scripts/compare_reproduction.py` compared 540 rows and baseline RTL RMSE/energy at relative tolerance 1e-10 / absolute tolerance 1e-12. `python scripts/check_clean_rtl_case.py` additionally reproduces one frozen v2 case. This is a fresh source extraction, not an independent image or full physical rerun, and not a repetition of all 46 v2 runs.
