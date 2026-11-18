# Working rules

Read `START_HERE.md`, then the current phase in `docs/DESKTOP_CODEX_BRIEF.md`. Implement the project, not another plan. Follow the user's authorization and any applicable higher-priority instructions.

Use `docs/STATE.md` for the current checkpoint, `docs/MILESTONES.md` for the remaining exit gates, and `docs/REPRODUCE.md` for commands. Project workflows live under `.agents/skills/`.

## Working in the codebase

- For architecture questions, start with `graphify query "<question>"` when `graphify-out/graph.json` is available. Check named relationships against the source before changing code.
- Preserve frozen protocols under `configs/` and their evidence. For a new evaluation, version the protocol and freeze thresholds, the training/evaluation split and seeds before running it.
- Use `make test-physics test-rtl` for the host simulation baseline. `make verify-layout` audits archived digital evidence. A new physical run needs the recorded SKY130A toolchain and an isolated workspace.
- Use `python scripts/release_check.py --operating-point` to audit the 0.18 V candidate. Keep its result scoped to the protocol and the original 0.15 V gate visible.

## Evidence and history

- Use actual commit dates and the authenticated author's identity. Do not fabricate contributions, experiments, institutional affiliations, acceptance odds, or measurements.
- Start by inspecting repository status and the installed toolchain. Preserve existing user work. No force pushes or destructive resets.
- Distinguish proposed, implemented, simulated, extracted, routed, FPGA-tested and silicon-measured results.
- Every published number must resolve to a run, configuration, tool version, log and raw output. Failed results remain visible in the experiment table.
- No fake plots, decorative chip layouts, broken image links, blanket DRC waivers, or placeholder success scripts.

## Efficient execution

- Keep `docs/STATE.md` short: current phase, passing gates, blocker, next three actions, relevant paths and last validated commit.
- Read scoped files with `rg` and line ranges; do not repeatedly dump this repository, PDKs or long logs into context.
- Run headless jobs, cache immutable inputs, capture complete logs to disk, and show a short failure tail plus relevant context.
- Complete a small end-to-end path first. Start physical-flow smoke testing on day one.
- Use fixed seeds, bounded experiment counts and restartable jobs. Never launch unbounded hyperparameter searches.
- Update the user at meaningful milestones with outcome, evidence and next action. Do not stop after routine reversible steps to ask permission already implied by the task.
- Commit coherent, verified milestones; do not generate empty commits or simulated development activity.
- No subagents unless the user explicitly asks for them. Independent tool jobs can run concurrently within the machine's measured resource budget.

## Completion

Use the acceptance gates in the brief. A target is not a passing result. A failed external dependency is a documented blocker, not a successful stage. Preserve partial progress and continue other independent work. Never replace verification with screenshots.
