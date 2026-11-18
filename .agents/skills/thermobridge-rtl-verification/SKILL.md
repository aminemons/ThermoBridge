---
name: thermobridge-rtl-verification
description: Verify ThermoBridge fixed-point arithmetic, calibration, ADC handshakes, PWM and fault logic, cocotb integration, or actual RTL-in-loop experiments.
---

- Read `rtl/thermobridge_top.sv`, `src/control/fixed_point.py`, and `tb/test_thermobridge.py` before changing a register, a Q format, or a control-cycle rule. Check every accepted transaction against the reference and keep boundary, saturation and safe-off coverage.
- Run `make test-rtl` with a Python environment containing cocotb and a working Icarus executable. Use `tb/rtl_plant_bridge.py` and `scripts/run_rtl_experiment.py` for actual feedback runs. The accelerated controller divider represents the model sample interval. Use dedicated PWM tests for physical-clock behavior.
- For a new study, use versioned protocols and separate train and evaluation schedules. Let each simulator invocation own its run directory and XML. Preserve ADC calibration, supply, fault count and raw traces with each run.
- Audit the archived 0.18 V evidence with `python scripts/release_check.py --operating-point`. Follow `docs/REPRODUCE.md` for rerunning a frozen case and comparing raw metrics.
