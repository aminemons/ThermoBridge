# ThermoBridge contributor quick start

ThermoBridge uses a host Git checkout together with an existing IIC-OSIC-TOOLS Docker container.

## Existing Windows installation

Open PowerShell in the project checkout. Docker Desktop and the existing `iic-osic-tools` container must be running. Reuse the installed image and PDK; the project does not require another tools download.

```powershell
python scripts/container.py sync
python scripts/container.py run make test-physics test-rtl
python scripts/container.py run make simulate
python scripts/container.py fetch results/raw/experiments
```

The host checkout and `/foss/designs/thermobridge` are separate copies. Run `sync` after editing sources and `fetch` after simulations. Fetch only the directories needed; local historical outputs are preserved.

## New contributor checkout

```bash
mkdir -p ~/Dev/Projects
cd ~/Dev/Projects
git clone https://github.com/aminemons/project.git project
cd project

python3 -m venv .venv
source .venv/bin/activate
```

For simulation, use the pinned OSIC environment described in [ENVIRONMENT.md](ENVIRONMENT.md). `requirements.txt` records the versions already installed there; it is not a Windows EDA-tool installer. In a configured Linux tool environment, run `make test-physics test-rtl` and `make simulate` from the checkout.

For host-side article/report generation only:

```bash
python -m pip install -r requirements-report.txt
python scripts/build_article.py
```

## Bounded research studies

```bash
python scripts/run_rtl_study.py       # 36 training runs; 10 paired evaluation runs
make sweep                          # 27 geometries, three duty conditions, selected 2 um refinements
```

Read frozen protocols before changing them: `configs/rtl_study_v2.json` and `configs/geometry_study_v1.json`. Preserve old data, use new run IDs and never select coefficients on test cases. Do not call a passing simulation fabricated silicon or describe an earlier result as a new held-out test.

See [REPRODUCE.md](REPRODUCE.md) for expensive physical commands and evidence-audit scope. Make substantive commits with actual timestamps. Ishaq's original guide is retained in Git history; this revision completes its open code block and setup instructions.
