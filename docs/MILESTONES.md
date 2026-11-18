# ThermoBridge milestones

## Baseline and source map

The electrothermal model in `src/physics/` drives the compact plant in `src/models/`. `src/sensing/` models the external resistance readout and calibration. The fixed-point reference in `src/control/` provides the numeric contract for `rtl/thermobridge_top.sv`. The cocotb bridge in `tb/` applies RTL duty to the simulated plant and returns ADC samples to the RTL. `configs/` freezes study inputs, `scripts/` runs them, `flow/` defines the SKY130A digital implementation, and `reports/` and `results/` hold the evidence.

The November baseline contains a fresh-case simulated pass at the proposed 0.18 V external heater supply and a retained miss at 0.15 V. The routed digital geometry has archived Magic and KLayout DRC and Netgen LVS evidence, with 10 MHz timing conditional on the ADC15 interface. [November review](REVIEW_20261109.md) · [Frozen v4 evidence](../reports/rtl_study_v4.json) · [Digital physical summary](../reports/asic/summary.json)

## 1. Review and extend the heater operating point

Record the design review of the candidate supply, including heater power, the modeled temperature envelope, and the energy trade-off against 0.15 V. Freeze a new paired protocol with independent cases for ambient, resistance and conductance variation, readout error and delay. Retain both supplies and energy traces, and use new cases after any retuning.

**Exit gate.** Reproduce the archived v4 reference. Publish all new cases with hold RMSE, overshoot, settling, heater energy and powered faults. Evaluate the declared ≤2 °C RMSE and ≤5 °C overshoot targets against the frozen protocol and report misses individually. [Operating-point reproduction](REPRODUCE.md#9-november-calibration-and-operating-point-studies) · [Spatial validation](../reports/operating_point_validation.json)

## 2. Reproduce the digital baseline and compare arithmetic variants

Use a clean source snapshot and recorded image and PDK revisions. Rerun the primary core through route, extraction, STA, Magic and KLayout DRC, and Netgen LVS. Confirm the ADC arrival budget and document any slew, capacitance, or unconstrained-path findings. The independent physical rerun can start alongside the operating-point review.

**Exit gate.** Archive reproducible primary and at least two alternative routed arithmetic implementations under comparable constraints. Verify each variant against its own bit-accurate contract and the mapped netlist by formal equivalence or gate-level comparison. Publish STA by supported corner, DRC/LVS, area and numeric trade-offs. Include power only if workload activity and coverage are available. [Physical brief](DESKTOP_CODEX_BRIEF.md#9-asic-implementation-and-verification) · [Current limitations](LIMITATIONS.md)

## 3. Characterize the separate SKY130A readout OTA

Derive load, common-mode limits, swing, settling and noise requirements from the sampled sensor-divider interface. Build the five-transistor OTA in Xschem and a native editable layout. Reuse the selected PDK and record the available corners and model assumptions.

**Exit gate.** Archive the schematic, layout, DRC and LVS reports, extracted netlist, and pre- and post-layout gain, bandwidth, swing, noise, current and settling. Feed the extracted gain, offset, delay and noise back into the readout model for a paired closed-loop study once the heater operating envelope is frozen. [Analogue brief](DESKTOP_CODEX_BRIEF.md#analogue-macro-required-for-the-full-simulation-based-pfe-scope)

## 4. Extend the geometry study and assemble the PFE evidence

Expand the bounded geometry search from the existing screening study. Split by whole geometry, validate proposed Pareto points with the spatial solver, and use a common closed-loop protocol to compare thermal uniformity, tracking and heater energy. Run an independent 3-D or experimental cross-check if a working solver or measured data becomes available.

**Exit gate.** Publish held-out surrogate errors, refined solver traces and candidate trade-offs. Assemble the clean reproduction record, the digital and analogue gate matrix, remaining limitations and reviewed technical report. Explicitly record any dependency that still prevents a full PFE claim. [Geometry evidence](../reports/geometry_study.json) · [PFE release gates](DESKTOP_CODEX_BRIEF.md#13-deadline-release-versus-full-pfe-release)
