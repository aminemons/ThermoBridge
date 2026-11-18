---
name: thermobridge-sky130-flow
description: Reproduce or review ThermoBridge SKY130A synthesis, routed timing, DRC, LVS, extracted digital evidence, or the separate readout OTA layout.
---

- Identify the actual installed image, LibreLane/OpenROAD versions and SKY130A revision. Compare them with `docs/ENVIRONMENT.md` and `reports/environment.json`. Run new jobs in a clean scratch checkout so the published evidence remains available.
- Start with `make verify-layout` to audit archived digital evidence. Use `make doctor` and `make synth` in the configured environment before launching `make gds` for a new physical run.
- Read both `flow/constraints.sdc` and `flow/adc15.sdc`. The published 10 MHz result assumes the ADC15 input budget and reuses the routed geometry. Compare original and revised timing by supported corner and preserve failed runs and electrical warnings.
- For the separate OTA, use the requirements in the desktop brief. Keep schematic and extracted results linked to the model corner and testbench, then pass the characterized transfer, settling and noise to the sampled readout model.
