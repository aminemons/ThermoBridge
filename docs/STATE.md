# ThermoBridge checkpoint

Date: 9 November 2026. Phase: heater operating-point validation and prototype release.

- Current checks cover 29 Python tests and two RTL unit tests. The v3/v4 studies add 71 actual RTL runs. Six fresh 0.18 V cases meet 2 C hold RMSE, spanning 1.675-1.777 C, with worst hold overshoot 1.297 C.
- The proposed operating point raises the external heater from 0.15 to 0.18 V with v3-trained gains and calibration. Available peak heater power increases 44%. Original 0.15 V failures remain recorded.
- The independent 0.18 V pulse validates the frozen RC fit with 0.128 C RMS error at 0.25 ms and 0.324% refinement sensitivity. All declared numerical checks pass.
- Physical: unchanged routed geometry, 10 MHz only with ADC arrival <=15 ns. Original20ns timing failed. Electrical warnings remain; no foundry signoff.
- Runtime: reused `iic-osic-tools`, `/foss/designs/thermobridge`, UID/GID1000. No image/PDK reinstall.
- GitHub: Ishaq-ML write access confirmed; contribution reviewed: quickstart `6e23643` / PR#1. Existing rewritten history preserved; new work uses actual dates.
- Evidence: `reports/rtl_study_v3.json`, `reports/rtl_study_v4.json`, `reports/operating_point_validation.json`, `reports/heating_reference.json`, and the revision3 article.
- Next: human review of the proposed heater supply; transistor OTA and extracted layout; arithmetic alternatives and independent physical rerun per `docs/LIMITATIONS.md`.
- Last physical milestone: `fcd61fb`. Final validation commit is recorded by Git and the reproduction audit.
- Clean source `ac59234` passed current tests, campaign, RTL and evidence audit; all 540 metric rows and baseline RTL metrics reproduced. A representative v2 case is checked separately in `reports/reproduction/`.
