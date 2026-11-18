---
name: thermobridge-electrothermal
description: Work on ThermoBridge's finite-volume microhotplate model, compact RC plant, geometry surrogate, or paired heater-supply evaluation.
---

- Find the active protocol in `docs/STATE.md` and `docs/REPRODUCE.md`. Inspect `configs/physics.json`, `configs/materials.json`, `src/physics/`, and `src/models/` for units, geometry, and fitted parameters.
- Use `make test-physics` and the relevant numerical validation script. For a supply-envelope change, check `scripts/validate_operating_point.py` and validate an independent pulse against a frozen fit. Include peak temperature, modeled range, and time-step sensitivity.
- For geometry search, start from `scripts/run_geometry_study.py` and keep whole geometries together in each split. Recheck claimed Pareto points with the solver and retain rejected or failed cases.
- For supply comparisons, hold the controller and scenario inputs fixed within each pair. Use saved trace power and distinguish peak available heater power from integrated heater energy. See the v4 protocol and the November review before selecting fresh cases.
