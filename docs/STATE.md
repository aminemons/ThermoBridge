# ThermoBridge checkpoint

18 November 2026. Phase: frozen v5 heater robustness study completed.

- Validated source: `5d569b6`. Host Python and cocotb tests pass, 16 v4 RTL evaluation rows reproduce, and the v5 archive verifier recomputes all 80 traces.
- v5: 0.18 V passes all four gates in 19 of 40 pairs, versus 8 at 0.15 V. Both supplies latch an ADC-rail fault in the low-resistance case. The wider operating envelope remains open. See [v5 report](../reports/rtl_study_v5.md) and its trace archive.
- Physical evidence remains conditional on ADC15. The archived core passed DRC and LVS, and the latest clean smoke reached SKY130A synthesis.
- Next: fix the modeled readout range and test delay margins on a new protocol. Reproduce the digital baseline through route and verification. Derive the sampled readout requirements for the separate OTA.
