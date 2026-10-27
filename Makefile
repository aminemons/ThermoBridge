.PHONY: doctor test-physics test-rtl simulate sweep synth gds verify-layout figures report release-check
PYTHON ?= python3
RUN ?= results/raw/experiments/exp-20261027T135345Z-7afca8
doctor:
	$(PYTHON) scripts/doctor.py
test-physics:
	$(PYTHON) -m pytest -q tests/test_physics.py
test-rtl:
	$(PYTHON) -m pytest -q tests/test_rtl_reference.py tests/test_sensing.py tests/test_experiments.py release/tests
	$(PYTHON) scripts/run_rtl.py
simulate:
	$(PYTHON) scripts/run_experiments.py
	$(PYTHON) scripts/run_rtl_experiment.py
sweep:
	@echo "PFE geometry-optimization sweep is not implemented in this release."
	@exit 1
synth:
	$(PYTHON) scripts/run_flow.py --synth-only
gds:
	$(PYTHON) scripts/run_flow.py
verify-layout:
	$(PYTHON) scripts/release_check.py --physical-only
figures:
	$(PYTHON) scripts/make_figures.py --run $(RUN)
report:
	$(PYTHON) scripts/build_report.py
release-check:
	$(PYTHON) scripts/release_check.py
