# ThermoBridge checkpoint

Date: 30 October 2026. Phase: reviewed prototype revision and article publication.

- Passed: 26 Python and 2 cocotb tests; 46 new actual RTL study runs; 81 spatial operating points on 27 geometries and 2 refined candidates; existing numerical/physical gates retained.
- Missed: original RTL RMSE 2.342 C, retuned regression 2.101 C. All four new retuned cases exceed 2 C. No energy-saving claim; warm-ambient retuning counterexample retained.
- Physical: unchanged routed geometry, 10 MHz only with ADC arrival <=15 ns. Original20ns timing failed. Electrical warnings remain; no foundry signoff.
- Runtime: reused `iic-osic-tools`, `/foss/designs/thermobridge`, UID/GID1000. No image/PDK reinstall.
- GitHub: Ishaq-ML write access confirmed; contribution reviewed: quickstart `6e23643` / PR#1. Existing rewritten history preserved; new work uses actual dates.
- Evidence: `reports/rtl_study_v2.json`, `reports/geometry_study.json`, `reports/thermobridge_article.pdf`; baseline physical/snapshot evidence unchanged.
- Next: human review; close calibration/tracking on a newly frozen protocol; analogue/layout alternatives and independent physical rerun per `docs/LIMITATIONS.md`.
- Last physical milestone: `fcd61fb`. Final validation commit is recorded by Git and the reproduction audit.
- Clean source `ac59234` passed current tests, campaign, RTL and evidence audit; all 540 metric rows and baseline RTL metrics reproduced. A representative v2 case is checked separately in `reports/reproduction/`.
