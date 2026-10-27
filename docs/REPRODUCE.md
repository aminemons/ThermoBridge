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
```

`simulate` uses frozen coefficients, not test-based retuning. Training is separate: `python3 scripts/tune_rtl.py`. `make sweep` explicitly fails because the PFE geometry Pareto sweep is pending. Full physical design has not been independently rerun from a clean image; current evidence reuses the earlier routed core and a separate STA recheck.

## Report on the host

```powershell
python -m pip install -r requirements-report.txt
python scripts/evidence_figures.py
python scripts/build_report.py
python scripts/release_check.py
```

The report reads archived data and writes `reports/technical_report.pdf`. The README selects campaign `exp-20261027T135345Z-7afca8`; a fresh experiment receives its own directory/manifest. Use `scripts/make_figures.py --run` with that directory for a rerun comparison. Changed source requires new validation rather than editing old passing reports.

## Historical material

`release/` preserves an earlier desktop runner/tests. Local `release_out/` and ZIP exports predate final conditional timing and are superseded. Canonical evidence is `reports/asic/summary.json` and `reports/release_snapshot.json`. `reports/asic/manifest.json` is a failed earlier attempt. Selected earlier failure manifests/metrics are retained under `results/history/`; bulky historical traces remain local.

No gate-level power, analogue macro, fabricated sensor or completed PFE sweep is implied. See [LIMITATIONS.md](LIMITATIONS.md).

## Executed clean-source check

`python scripts/clean_reproduce.py` exported commit `883543a6d007b3df1e7ce73ea2837b9ab267ccd7` with `git archive` into a new Linux directory in the existing container. Tests, frozen campaign, real RTL loop and archived-evidence audit all returned zero. `python scripts/compare_reproduction.py` compared 540 rows and RTL RMSE/energy against the baselines, finding no differences at relative tolerance 1e-10 / absolute tolerance 1e-12. Logs and exact scope: [reproduction report](../reports/reproduction/summary.json). This is a fresh source extraction, not an independent image or full physical rerun.
