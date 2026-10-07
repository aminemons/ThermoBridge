# ThermoBridge checkpoint

Date: 27 October 2026. Phase: conditional research snapshot and evidence publication.

- Passed: numerical validation, 25 Python tests, 2 cocotb tests, routed Magic/KLayout DRC and Netgen LVS, STA conditional on ADC15.
- Missed: held-out RTL RMSE 2.342 C versus <=2 C target; broad settling failures remain published; no demonstrated energy saving.
- Physical: unchanged routed geometry, 10 MHz only with ADC arrival <=15 ns. Original20ns timing failed. Electrical warnings remain; no foundry signoff.
- Runtime: reused `iic-osic-tools`, `/foss/designs/thermobridge`, UID/GID1000. No image/PDK reinstall.
- GitHub: Ishaq-ML write invitation pending acceptance (`reports/collaborator.json`).
- Evidence: `reports/release_snapshot.json`, `reports/asic/summary.json`, primary campaign `exp-20261027T135345Z-7afca8`, `reports/technical_report.pdf`.
- Next: human review; new training/calibration with fresh held-out protocol; independent physical rerun/PFE work in `docs/LIMITATIONS.md`.
- Last physical milestone: `fcd61fb`. Final validation commit is recorded by Git and the reproduction audit.
