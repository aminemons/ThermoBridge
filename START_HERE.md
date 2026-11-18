# Start here

ThermoBridge models and controls a microhotplate. The software closes an electrothermal feedback loop around synthesizable RTL, and the repository archives a routed SKY130A digital core. The heater, analogue readout and ADC are external to that core.

1. Read [AGENTS.md](AGENTS.md), the [checkpoint](docs/STATE.md) and the [next milestones](docs/MILESTONES.md). The [desktop brief](docs/DESKTOP_CODEX_BRIEF.md) defines the original research and PFE acceptance gates.
2. Use the [contributor guide](docs/CONTRIBUTOR_QUICKSTART.md) and [reproduction guide](docs/REPRODUCE.md). Verify the host baseline with `make test-physics test-rtl`, then audit the archived layout with `make verify-layout`.
3. Read the [revision review](docs/REVIEW_20261109.md) before changing the controller or its evaluation. The proposed 0.18 V heater result and the archived ADC15 timing contract have separate assumptions.

[ThermoBridge on GitHub](https://github.com/aminemons/ThermoBridge)
