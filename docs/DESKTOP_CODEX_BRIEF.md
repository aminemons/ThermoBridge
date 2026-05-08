# ThermoBridge — desktop execution brief

Version 1.0 · 27 October 2026 · repository: https://github.com/aminemons/project

## 1. Mission and scope

Build a reproducible research prototype connecting **multiphysics simulation, nanoelectronic sensor interfacing, and VLSI implementation**. Deliver real data, tested RTL, an actual routed ASIC core and a readable technical explanation. Continue implementing until the release gates pass or a concrete external blocker is documented; another proposal is not the requested outcome.

Project title: **ThermoBridge: Electrothermal Co-design of a Fixed-point Microhotplate Controller ASIC**.

Research question: **For an explicitly modelled suspended microhotplate, how do controller structure, arithmetic precision and thermal-model uncertainty affect heating-cycle energy, temperature tracking and implemented silicon cost?**

Primary hypothesis to test, not a promised result: a model-based feedforward term plus an inexpensive PI controller may reduce warm-up overshoot or cycle energy at matched tracking quality, while a bounded fixed-point implementation may retain adequate performance with lower hardware cost than a wider implementation. If improvements do not occur, publish that result and its explanation.

The useful application is programmable heating for resistive micro/nanosensor characterization. The project does not need to demonstrate gas identification. It must not claim battery-failure prediction, ppm detection limits, selectivity, certified safety, experimental nanomaterial performance or fabricated silicon without real evidence.

### What is inside and outside the chip

- **Inside the deadline ASIC core:** sample capture, calibration arithmetic, PI/feedforward control, PWM generation, fault handling, configuration/status registers and a simple configuration interface.
- **External in the first release:** the membrane and heater, power transistor, sense circuitry and ADC. Interface them through documented behavioural models and a sampled-data simulation bridge.
- **PFE extension:** a separately laid-out and verified transistor-level analogue readout amplifier macro. Publish its own GDS and extracted results. Do not imply it is integrated into the digital GDS unless an actual combined top-level flow and verification pass.
- **Nanoelectronics component:** a parameterized resistive sensing channel with thermal cross-sensitivity and optional random-telegraph noise (RTN). Treat it as a phenomenological interface/noise study unless supported by measured device data. A 130 nm CMOS core is mature-node VLSI, not a novel nanodevice.
- No CPU, RTOS, large neural network, custom SRAM, cloud dashboard or gas classifier in the critical path. Consider an X-HEEP interface only after the standalone core is complete.

Amine's relevant foundation is CDTA electrothermal microheater work and micro/nanoelectronics. Ishaq's public profile supports ML, optimization and hardware interests. Both must review the results and accurately record their actual contributions. Never invent months of activity, backdate commits or assign another person's Git identity.

## 2. First hour: inspect, invite, and establish a working environment

1. Locate the requested repository or clone it into a new writable project directory. Read applicable agent instructions. Inspect `git status`, branch, remotes and existing files before editing. Preserve user changes and other designs.
2. Check exact GitHub account/repository authorization. The user explicitly requested the collaborator **Ishaq-ML** on **aminemons/project**. Check existing access and pending invitations first. If absent, use a supported authenticated operation with write access, not admin. Where GitHub CLI is available and authenticated, the intended operation is:

   ```bash
   gh api --method PUT repos/aminemons/project/collaborators/Ishaq-ML -f permission=push
   ```

   Check current GitHub API documentation and the command response. An invitation response is pending acceptance; an already-collaborator response is different. Do not expose credentials, access other repositories, or claim success on an authorization failure. If blocked, record it and keep implementing; do not block the engineering work on the invite.
3. Inspect the existing IIC-OSIC-TOOLS container/image and mounted host folder. Do not reinstall Docker, update the whole image, or replace a working PDK as a first step. Record image tag/digest, OS, CPU, free RAM/disk, tool versions and PDK revisions in `reports/environment.json` and `docs/ENVIRONMENT.md`. Keep host/user secrets out of public logs.
4. Test that the project and netlist/output directories are writable **as the actual container user**. Use project-local build directories. Address ownership or mount mapping narrowly; no recursive chmod/chown of `/foss` or the user's home. Do not reuse a non-writable Xschem example directory.
5. Inspect executables/help for Yosys, simulator, OpenROAD, LibreLane or OpenLane, KLayout, ngspice, Xschem, Magic and Netgen. The upstream image currently includes LibreLane, but installed versions may differ. Discover supported invocations from installed help/examples; do not assume every release accepts the same config or CLI flags.
6. Prefer **sky130A + sky130_fd_sc_hd** for the primary complete physical flow, with 1.8 V core models and the appropriate nominal libraries. If a different installed process has a demonstrably working end-to-end flow, choose it once, document why, and keep all primary ASIC artifacts consistent. Do not mix Liberty, LEF, GDS, SPICE or model corners between PDKs. Do not select IHP solely because an analogue example opens: upstream notes partial support, and digital flow/deck compatibility must be tested.
7. Run a tiny counter through simulation, synthesis, placement, routing, GDS export and the available verification steps **before investing in the controller**. Record missing stages explicitly. Spend at most about 90 minutes on one blocked path before testing a supported installed alternative. Keep the counter under `build/smoke`, not as a claimed research result.

Create a small versioned environment lock. Respect existing upstream instructions if editing tool sources, although project work should not require editing the tools repository.

## 3. Finish a vertical prototype before expanding the physics

First implement a one-node thermal RC model with explicit assumed parameters, a floating-point PI, a bit-accurate reference, RTL PWM/controller, and a simulation bridge. This is the integration baseline, not the final spatial multiphysics result.

One-node plant:

\[
C_{th}\,dT/dt=P_h-(T-T_a)/R_{th}.
\]

For voltage PWM, use `P_h = duty * V_h^2/R_h(T)` only where the thermal system averages many PWM periods. Validate against switched pulses for a representative case. Do not use `(duty*V_h)^2/R_h` for that average.

Choose positive, clearly labelled assumed RC values producing a tractable example; the target is a working interface. Include a zero-power cool-down test, an equilibrium check and analytic step-response comparison for constant resistance. Replace/supplement these assumptions with fitted parameters from the spatial model later.

Immediately synthesize the initial core and attempt a first routed layout. This reveals integration and arithmetic-size problems early. Do not postpone physical design to the final day.

## 4. Spatial electrothermal plant

### Geometry and materials

Model an external suspended membrane with a central active region, a patterned resistive heater, and narrow support beams to fixed-temperature anchors. A sensible **initial illustrative geometry** is a roughly 200 by 200 micrometre active membrane, a submicrometre-to-micrometre dielectric thickness, and a thin-film serpentine heater. These are starting assumptions, not CDTA measurements or foundry design rules. Select dimensions/mesh so heater traces and anchors resolve with several cells across their width; reject unresolved geometries.

Keep a material/parameter table with SI units, source, temperature range and status (`measured`, `literature`, `assumed`, `fitted`). Verify literature values from primary sources if used. Include thickness, density, heat capacity, thermal conductivity, resistivity, TCR, emissivity and environmental heat-loss assumptions. Avoid double-counting anchor conduction as convection. No confidential CDTA geometries/data without authorization.

### Equations and discretization

Use a genuine **2-D thin-film finite-volume model** with NumPy/SciPy sparse matrices. It is sufficient for the first spatial release if assumptions and validation are clear; do not label it COMSOL, 3-D FEM, TCAD or fabrication simulation. Gmsh may generate a mesh for a later independent solver, but is not itself a thermal PDE solver.

On the electrically conducting heater domain solve:

\[
\nabla\cdot(\sigma_s(T)\nabla\phi)=0,\qquad
q''_J=\sigma_s(T)|\nabla\phi|^2.
\]

Here `sigma_s = electrical_conductivity * heater_thickness` is sheet conductance (siemens), `phi` is volts and `q_J` is W/m². Use fixed terminal potentials, insulating other electrical edges, and temperature-dependent resistivity over a documented valid range. Reconstruct terminal current and verify `V*I` against integrated Joule power.

On the membrane/heater thermal domain solve:

\[
C_s\,\partial T/\partial t=\nabla\cdot(K_s\nabla T)+q''_J
-g_{env}(T-T_a)-\epsilon\sigma_{SB}(T^4-T_a^4).
\]

`C_s = sum(rho_i*c_i*t_i)` has units J/(m² K); `K_s = sum(k_i*t_i)` has units W/K. `g_env` is the effective top/bottom environmental loss coefficient in W/(m² K); define whether it already includes both faces. Radiation temperatures are kelvin. Include radiation explicitly or justify its omission with a quantified bound over the operating range. The thin-film assumption imposes common through-thickness temperature and omits interfacial thermal resistance unless modelled separately.

Thermal anchors have `T=T_a`; suspended edges have no lateral flux. Apply spatial Joule sources only on the heater mask and map cells conservatively. Use harmonic face conductance for material interfaces. Handle disconnected electrical components explicitly. Use implicit thermal time integration and a converged electrical/thermal iteration; bound nonlinear iterations and report failures rather than silently clipping invalid material properties.

Mesh/time convergence: start coarse, then use at least three resolved refinements with consistent geometry. Save active-area mean, peak temperature, hotspot location, resistance, input power and balance residual. At least halve the thermal time step once. Compute active-area nonuniformity over a fixed central sensing ROI, not the cooled support anchors.

Mandatory validation:

- Rectangular uniform resistor: analytical `R=rho*L/(w*t)` within a predefined discretization tolerance, initially 2%.
- Constant-source thermal RC against analytical transient for the lumped baseline, initially 1% normalized error.
- Constant-temperature/zero-source solution remains constant within solver tolerance.
- Electrical power balance and thermal energy balance, with initial normalized residual targets below 1% after convergence. Define normalization near zero power separately.
- Finite temperatures, positive resistance, and no unconnected singular matrix hidden by arbitrary regularization.
- Peak/mean temperature change below an initial 2% criterion on the final mesh refinement; tighten for the PFE release. If a gate fails, refine or publish the limitation, not a false pass.

Export raw fields, masks and mesh metadata. Thermal maps must show scale bars, actual geometry, temperature units and boundary assumptions. Keep this membrane illustration separate from the CMOS GDS screenshot.

## 5. Compact model, surrogate and optimization

Fit a positive-parameter one- or two-node thermal network to spatial step/transient responses. Prefer a two-node heater/membrane network only if held-out responses justify its extra parameters. Save fit parameters, residuals and held-out errors. Fit on selected powers and test unseen pulse amplitudes and durations; fitting a single transient and testing its own samples is not validation.

Start a bounded design sweep: about **24–48 distinct geometries** varying trace width, pitch and anchor width over physically resolved bounds, at three operating conditions each. Benchmark runtime first and scale down the initial release if needed while retaining a disclosed held-out set. Vary actual geometry masks and material properties, not merely relabel an RC coefficient as multiphysics simulation.

Compare exhaustive/random search within a modest fixed budget to optional Gaussian-process Bayesian optimization. A lightweight GP or simple regression is sufficient; add no Transformer. Split by whole geometry, freeze the split before fitting, keep test geometries out of tuning, and evaluate candidates selected by the surrogate using the spatial solver. Save the split manifest. Report median and worst-case errors, runtime and all solver failures.

Multi-objective design study: electrical heating-cycle energy, central-region temperature nonuniformity, and warm-up time under common tracking constraints. Use actual spatial solves to validate the final Pareto candidates. Do not claim global optimality. If the sweep cannot be completed before the deadline, publish the compact-model/control study and mark the geometry study as continuing work.

Optional ML contribution is therefore **offline surrogate-assisted design**, not an on-chip neural accelerator. Only claim hardware inference if inference logic really exists and passes equivalence/physical checks.

## 6. Sensor/readout model and nanoelectronics connection

Primary feedback uses the heater's calibrated resistance versus temperature. Start with `R_h(T)=R_0*(1+alpha*(T-T_0))` within a documented valid range. Map a temperature range to a 12-bit ADC code through explicit current-sense/divider gain and offset. Include quantization, sample delay, offset/gain error and measurement noise. Document how resistance is measured during PWM: synchronized measurement windows or an equivalent filtered measurement, with bandwidth and delay. An unobservable off-state must not be treated as a valid sample. Power used by sensing must be included or separately bounded.

For the separate nanoresistive channel, use a labelled phenomenological `R_s(T)` or `G_s(T)` law and optional stochastic conductance fluctuations. A useful controlled experiment is an RTN channel `deltaG=A*(s-p)` with a two-state continuous-time Markov process, declared transition rates, stationary occupancy `p`, seed and amplitude. Use transition probabilities consistent with sample interval and validate dwell-time statistics. Study how finite precision/noise affects measured resistance/temperature and controller robustness. Do not call arbitrary Gaussian noise RTN, claim foundry-calibrated trap parameters, or infer gas sensitivity from a synthetic response.

Separate heater-temperature calibration from sensor-material response. These are physically different devices. The high-temperature membrane may operate at an illustrative 200–350 °C only if its assumed materials support it; **the CMOS die does not share that temperature**. Run PDK circuits only in their documented model range and explain the external thermal/voltage isolation. External heater voltage/current must never be applied directly to 1.8 V core transistors.

## 7. Controller and RTL specification

### Reference algorithms

Implement and fairly tune three controllers using training scenarios only:

1. A hysteretic/bang-bang baseline with the same actuator limits and evaluation cycle.
2. A conventional PI with saturation, anti-windup and explicit sample delay.
3. PI plus a precomputed model-based feedforward term / compact lookup table. For a simple steady-state ROM, `P_ff=(T_set-T_a)/R_th`, and `d_ff=P_ff*R_h(T_set)/V_h^2` before clamping; include any dynamic warm-up term separately. Offline compute coefficients; RTL need not divide in real time.

Equalize setpoint schedules, initial states, plant samples, noise seeds, settling constraints and evaluation horizons. Heating the same object to the same temperature requires physical energy; better control is not a perpetual saving at an identical steady state. Separate warm-up, hold and cool-down energy, and disclose any reduced temperature exposure.

### Numeric contract

Use signed arithmetic with explicit widths and scales. A practical initial temperature representation is **signed 16-bit with 6 fractional bits**, resolution 1/64 °C and range -512 to +511.984375 °C. Coefficients can begin as signed 18-bit with 14 fractional bits; this is an initial choice to validate, not a universal stable controller. Derive product/accumulator widths from bounds, make rounding/saturation rules explicit, and emulate them exactly in Python. Avoid ambiguous Q-format names. No unsized signed literals, wraparound integrators or simulator-only real arithmetic in synthesizable RTL.

Explore at least three viable arithmetic widths and two implementation choices, for example constant shift-add arithmetic versus a time-multiplexed multiplier. Quantization requires retuning or a documented fixed-coefficient comparison; do not bias the wider baseline. Use named parameters and a bit-width design table.

### Timing and interfaces

- Initial clock target: 10 MHz, verified against actual timing. A target is not measured Fmax.
- Initial PWM: 8-bit counter, hence `10 MHz/256 = 39.0625 kHz`, with exact 0% and full-on endpoint handling.
- Initial control interval: 1 ms, conditional on ROM identification and stability tests. Increase sampling rate if the model is faster; document PWM/sample phase relationship and measurement latency.
- Use one internal clock and clock-enable pulses. If an external asynchronous interface exists, synchronize control signals and document multi-bit capture, not just individual bit synchronizers.
- Primary sampled input: 12-bit `adc_code`, synchronous `adc_valid`; invalid samples never advance the integral. Expose sample acceptance/status.
- Config/status interface: a documented synchronous register bus for first integration. Add a mode-0 SPI register wrapper only after the core works; do not let it block the deadline release. In the core-only GDS, exported bus pins are macro pins, not a fabricated package pinout.
- PWM output drives an **external** stage. Fault output and status are accessible independently of controller data.

Suggested module split: `sample_capture`, `calibration`, `pi_core`, `feedforward_lut`, `pwm`, `fault_manager`, `register_bank`, `thermobridge_top`. Avoid adding a module for every arithmetic operator.

### Fault semantics

Reset and disabled state force PWM low. Over-temperature, invalid calibration, stale data, commanded shutdown and out-of-range sensor codes force safe off and latch a cause. Initial stale timeout: three control periods; specify exact off latency. Clear a fault only through an explicit acknowledged clear with valid safe conditions. Use an independent absolute limit in calibrated units and cover calibration corruption in tests. State clearly that this is simulated fail-safe logic, not a certified safety mechanism or protection against all physical failures.

## 8. Verification and integration

Use pytest for solver/contracts and cocotb with Icarus/Verilator for RTL. Build a bit-accurate Python reference that emits expected transactions. Include boundary-value tests, randomized constrained samples and directed control/fault sequences. Compare every accepted sample/controller update, not only the final temperature.

Required tests: reset; disabled PWM; minimum/maximum setpoint and gains; negative errors; rounding ties; arithmetic saturation; anti-windup; exact PWM endpoints/duty; stale/invalid sample; fault latch and clear; register readback; coefficient update atomicity; full sensor range; deterministic replay. If adding SPI, test clock edges, framing, abort and CDC behavior. Use meaningful design tests rather than dozens of implementation-mirroring assertions.

Implement a true closed-loop bridge: simulator produces RTL duty, Python advances the thermal plant over the control interval, the ADC model returns a code, and the next RTL update consumes it. Verify the bridge on a short known trace. Distinguish **RTL-in-the-loop** from Python replay of precomputed duty; record which generated each result. PWM ripple validation requires either explicit switched integration over representative windows or a justified averaged model.

Use long ROM closed-loop campaigns plus a smaller number of spatial-model spot checks. Do not run a full nonlinear PDE at every 10 MHz clock. Add synthesis-netlist equivalence if supported; for a stable digital block, use formal equivalence or a documented gate-level reference comparison. Do not substitute Python tests for RTL verification.

## 9. ASIC implementation and verification

Create a flow config checked against the installed release. Begin with modest utilization (roughly 30–45% as an initial target), explicit clock, input/output delays, reset treatment, core pins, power network and suitable synthesis constraints. Keep port counts/physical dimensions traceable. Resolve setup/hold and unconstrained-path warnings; record supported corner coverage and any remaining exceptions.

Archive synthesis cell statistics and mapped netlist, floorplan, placement, CTS/routing logs, final DEF/GDS/LEF, SDC, parasitic extraction where supported, routed STA reports, and full physical-check reports. Measure area from the reported implemented core/cell geometry; do not infer it from RTL lines or weight counts.

Run the available correct PDK DRC deck and LVS comparison of the routed layout versus the intended netlist. State which deck, version, extraction, blackboxes and top-level scope were used. Initial goal is zero unexplained violations, matched connectivity and no unintended blackboxes; missing verification means incomplete status. Distinguish flow-internal routing checks from foundry-qualified sign-off. Record antenna checks if the flow supports them. Core-only GDS excludes a complete pad ring, ESD, package, fabrication approval and measured silicon.

Obtain power estimates only with stated voltage, frequency, corner, activity trace and parasitic assumptions. Prefer a gate-level VCD/SAIF workload; retain activity coverage. Separate heater supply energy from digital-core estimated power. If activity-based estimation is unavailable, report area/timing and mark power unavailable instead of inventing mW or claiming total system savings.

Export **real** KLayout captures from the generated GDS: full routed core and one routing/cell detail view with scale/legend. Obtain a real Xschem capture for any implemented analogue block. A 3-D GDS rendering may supplement these, labelled a visualization; it is not a fabricated chip photograph.

## 10. Experiments and success criteria

Create a frozen evaluation manifest. For the deadline study use at least 20 independent, reproducible test scenarios spanning nominal conditions, ambient change, heater-resistance/TCR variation, thermal conductance variation and measurement imperfections. These are assumed variation ranges unless measured; document them. Reuse paired scenarios across controllers. Start with 3 seeds for stochastic cases, extend to 5 or more for PFE. Keep test scenarios separate from coefficient selection.

Evaluate a fixed cycle such as warm-up, controlled hold, setpoint step and cool-down. Select feasible actual durations from model time constants; do not hard-code an impossible one-second transient simply for appearance. Measure:

| Quantity | Definition / evidence |
|---|---|
| Heating energy | Integral of actual heater-terminal `V*I` over the same cycle; J or mJ |
| Tracking error | RMSE and max absolute error in °C over declared windows |
| Overshoot | Maximum temperature minus setpoint after each declared step |
| Settling time | First time remaining in a declared band for a specified dwell; failure if never achieved |
| Uniformity | Central ROI spatial standard deviation and peak-to-mean difference |
| Quantization cost | Tracking/energy differences versus float and bit-exact agreement versus RTL |
| Hardware cost | Cell/core area, routed slack/delay, achievable constrained clock and optionally workload-based power |
| Robustness | Failure rate, worst scenario and paired distribution, with seeds/ranges |
| Model quality | Held-out ROM/surrogate error, convergence and energy-balance residual |

Initial engineering targets: nominal hold RMSE <=2 °C, overshoot <=5 °C, no unexplained RTL/reference mismatch, safe-off within the specified fault latency, and a routed implementation meeting the 10 MHz constraint with all required timing checks identified. Validate target feasibility from the model and record any principled revision before final testing. A **5–15% cycle-energy reduction is only an aspiration**, never an acceptance condition that invites result manipulation. Zero or negative improvement is a valid experimental result.

Required ablations: bang-bang versus tuned PI versus feedforward+PI; float versus fixed versus RTL; at least three numeric widths; nominal versus uncertain plant; clean versus noisy/delayed readout. For the geometry extension add raw solver versus surrogate predictions and solver-validated Pareto candidates. Show distributions and failures; do not cherry-pick one successful curve.

## 11. Repository and reproducibility contract

Create these paths when implementing them; do not fill the repository with empty files now:

| Path | Contents |
|---|---|
| `configs/` | SI-unit geometry/material inputs, control and evaluation manifests |
| `src/physics/` | Geometry, electrical/thermal FVM and numerical checks |
| `src/models/` | ROM fitting and bounded surrogate/design search |
| `src/control/` | Float and bit-accurate references |
| `rtl/`, `tb/`, `tests/` | Synthesizable modules and meaningful verification |
| `flow/`, `scripts/` | Installed-version physical config and automation |
| `analog/` | PFE schematic/layout/netlists and characterization scripts |
| `results/raw/`, `results/processed/` | Selected versioned datasets and computed tables |
| `reports/` | Environment, validation, timing/physical reports and technical report |
| `docs/figures/` | Data-generated plots and real tool screenshots |
| `docs/STATE.md` | Compact restart checkpoint |

Provide working `make` targets: `doctor`, `test-physics`, `test-rtl`, `simulate`, `sweep`, `synth`, `gds`, `verify-layout`, `figures`, `report`, `release-check`. Implement each target genuinely; fail nonzero when requirements are absent. Mark PFE-only targets explicitly. The first reproducible path should be `make doctor`, targeted tests, a small simulation, then GDS. Large optional sweeps must not run implicitly on every test.

Every run writes `manifest.json` with run ID, UTC timestamp, source commit, dirty-state indication or source hash, input/config hashes, seed, tool/PDK versions, command, duration and status. Link summary metrics to raw CSV/NPZ and logs with checksums. Never silently reuse cached results after config/code changes. Cache solver results by content hash and keep job manifests for resuming.

Use pinned minimal Python dependencies and no unnecessary GPU training. Archive bulky flow intermediates outside Git or as release assets; commit the small inputs, selected final artifacts, raw summary data, reports and figures. Do not commit the whole PDK, Docker image, credentials, student identity documents or admissions transcripts. Add a license only after checking ownership and keeping upstream attribution/licensing for reused IP/data.

## 12. README and technical report

Keep the README concise and evidence-first. Its final order:

1. One-paragraph problem and a status statement.
2. Actual system diagram with on/off-chip boundaries.
3. Verified result table with run/release links and assumptions.
4. Six to eight readable figures, each linked to its raw data or report.
5. Real routed-GDS image and verification table.
6. Quick reproduction commands, limitations and actual contributions.

Figure set: geometry/temperature field; electrical/Joule-power validation and mesh convergence; paired controller temperature+duty traces; energy versus tracking-quality trade-off; robustness distribution; numeric width versus area/timing/error; GDS full view/detail. Add surrogate/Pareto and analogue pre/post-layout plots only after those stages exist. Use consistent axes, physical units, captions and restrained colors. Export SVG plus PNG for plots. No invented progress badges or placeholders linked as completed results.

Write an 8–12 page technical report for the deadline prototype if the evidence supports it; extend to roughly 15–25 pages for the PFE release. Quality takes precedence over page count. Cover question/prior art, assumptions/equations, model validation, controller arithmetic, verification, physical design, results/uncertainty, limitations and reproduction. Render and inspect the PDF before publishing; use the available PDF skill if working in ChatGPT Work. Cite real primary sources and keep claimed novelty modest.

Add `docs/CONTRIBUTIONS.md` listing work actually performed and reviewed. Planned roles are not completed contributions. Add a short AI-assistance statement if applicable; both students should be able to explain the solver, fixed-point arithmetic, validation and layouts in an interview.

## 13. Deadline release versus full PFE release

E3 closes **1 November 2026 at 23:55 Algeria/Swiss time**. Aim for a verified application snapshot by **31 October**, leaving time for documents and portal issues. The project must not cause a missed application deadline. A completed recent prototype is credible; it need not pretend to be old.

| Window | Work and exit gate |
|---|---|
| 27 Oct | Inspect tools, invite collaborator if possible, RC/float/fixed/RTL loop, physical-flow smoke pass |
| 28 Oct | Controller/fault tests and first routed core; document achieved physical verification |
| 29 Oct | Spatial model, analytical/balance/convergence checks, compact-model validation |
| 30 Oct | Paired closed-loop evaluations, width trade-offs and primary figures |
| 31 Oct | Fix failures, clean reproduction, real GDS captures, report and frozen release |
| 1 Nov | Final evidence/application review and submit before deadline; project polish is secondary |

This is a demanding target, not a promise that all external tools will work. **Deadline release gates:** numerical validation; working bit-accurate and RTL-in-loop control; directed fault tests; at least one complete routed core with honest DRC/LVS/timing status; paired test data and figures; reproducible commands; status/limitations in README. Missing items must be named in the release. Do not call a partial physical flow a verified ASIC.

**PFE release (estimated additional 4–8 weeks, depending on actual progress):** expanded spatial/design dataset and solver-validated Pareto study; larger variation/noise campaign; at least three physically implemented arithmetic variants; the analogue macro below; independent 3-D thermal or experimental validation when tools/data allow; documented clean rerun; final reviewed report. Optional FPGA hardware tests require an actual available board/toolchain; a compiled bitstream is not a board measurement. Experimental work needs real apparatus, calibration and time and cannot be generated by an assistant.

### Analogue macro required for the full simulation-based PFE scope

Build one modest **five-transistor OTA** (differential input pair, current-mirror load, tail source) as a separate sensor-readout amplifier study in the locked primary PDK. Use external ideal biasing/ADC only where explicitly labelled; this is not a complete ADC or precision instrumentation amplifier. Choose input polarity/common-mode range from an operating-point study. First target a buffered/reference resistive-sensor divider within valid input common-mode limits, not a high-voltage heater terminal.

Derive load, common-mode, gain-bandwidth and settling needs from the declared sampled readout; declare illustrative requirements before sizing. Show DC operating points/headroom, gain/bandwidth, output swing, noise and supply current, and the effect of readout gain/offset/delay on inferred resistance. Use only supported model corners and statistical mismatch parameters; absent mismatch models must be stated. Implement Xschem schematic and native editable layout, DRC, extraction, Netgen/LVS or equivalent, and pre/post-layout simulation with parasitics. Archive circuit/netlist/testbench and genuine screenshots. Connect measured/simulated macro transfer/noise/latency back into the system model for a cross-layer ablation. Keep the macro separate unless top-level integration is truly verified.

An independent 3-D FEM cross-check or COMSOL comparison is optional and must use an available licensed/working solver. The 2-D model plus validation, real ASIC flow, analogue layout and documented co-design study form the achievable simulation-based PFE scope. Fabricating a custom membrane or ASIC requires a separate process, budget and schedule.

## 14. Token and runtime budget

Read this brief once, then use `docs/STATE.md` and phase-specific files. Keep source-of-truth equations/contracts in small dedicated files. Do not paste megabytes of simulator output into chat. Report a short outcome and relevant failure context; inspect full logs locally only as needed.

Benchmark one PDE job and one physical job before parallel runs. Set a RAM-aware job cap; do not run multiple place/route jobs on a small laptop. Prefer headless CLI runs for repeatability; use GUI only to inspect schematic/layout and capture evidence. Cache deterministic solves and do not regenerate unchanged figures. Freeze a small experiment set first; increase breadth only after the end-to-end flow is proven.

Commit meaningful real milestones with ordinary current timestamps: numerical model validated; controller/fault tests passing; routed core and reports; evaluated experiment dataset; documented release. Existing authentic earlier work may be referenced with attribution and its real history; do not rewrite that history to suggest the new project existed earlier.

If blocked, record exact stage, error, attempted fix and the narrow missing dependency. Continue independent work. Ask the user only for genuinely missing access, hardware, credentials or a decision that changes scope. Never handle credentials by printing or committing them.

## 15. Final delivery and application handoff

Finish with a compact pass/fail matrix, frozen commit/release URL, exact quickstart commands, best supported findings, negative results, all physical-verification limits and collaborator-invitation status. Check README images render and all local links resolve. Re-run the documented small reproduction from a clean checkout/environment within practical limits and report the actual scope of that rerun.

For the application, prepare facts rather than invented marketing: what was implemented, what was simulated, what was verified, one reproducible result and the next scientific question. Select **VLSI design / Nanoelectronics / Multiphysics simulations**. Research-fit candidates ESL, NanoLab and LSI require confirmation in the current E3 hosting database; see `SOURCES.md`. Both applicants submit independent accurate statements and explain their own contributions. Do not submit applications or contact professors without separate user instructions.

The purpose is strong, inspectable work the students can defend. No acceptance percentage is justified by this specification.
