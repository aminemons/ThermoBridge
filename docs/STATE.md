# ThermoBridge checkpoint

18 November 2026. Phase: preparing the PFE extensions from the November prototype baseline.

- Validated source: upstream `2bd44b9`. Host Python and cocotb tests, the frozen v4_E03 RTL replay, both archived evidence audits and an isolated SKY130A synthesis smoke passed. Local logs, runtime versions and outputs are under `build/codex-bootstrap/`.
- Release evidence: `reports/rtl_study_v4.json`, `reports/operating_point_validation.json` and `reports/reproduction/rtl_v4_case.json`. The proposed 0.18 V case series passes its simulated targets. Original 0.15 V failures remain in the archive.
- Physical evidence: `reports/asic/summary.json`. Archived route, DRC and LVS passed, with 10 MHz timing conditional on ADC15. The clean physical rerun, electrical warning review and extracted OTA remain open. A broader operating-point decision still needs engineering review.
- Next: review the heater operating envelope and freeze a fresh paired protocol. Reproduce the reference core through route and verification. Derive the sampled readout requirements for the separate OTA. See the milestone document for exit gates.
