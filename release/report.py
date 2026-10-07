"""Generate a traceable text report from completed, local evidence only."""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'release_out'


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_report(root: Path = ROOT) -> Path:
    out = root/'release_out'
    data_file = out/'experiments'/'summary.json'
    phy_file = root/'outputs'/'physics'/'validation.json'
    if not data_file.is_file() or not phy_file.is_file():
        raise FileNotFoundError('Run physics validation and closed-loop evaluation before report')
    experiments = json.loads(data_file.read_text(encoding='utf-8'))
    physics = json.loads(phy_file.read_text(encoding='utf-8'))
    physical_file = out/'physical'/'audit.json'
    physical = json.loads(physical_file.read_text(encoding='utf-8')) if physical_file.is_file() else None
    f = lambda x: f'{x:.4g}' if isinstance(x, (int,float)) else str(x)
    lines = [
        '# ThermoBridge — measured computational evidence',
        '', f'Generated (UTC): {datetime.now(timezone.utc).isoformat()}',
        '', '> **Scope:** numerical electrothermal model, behavioural closed-loop simulations',
        '> and digital standard-cell design. All geometry and physical parameters are',
        '> assumed illustrations, not device measurements or certified safety tests.',
        '', '## 1. Physical system and boundaries', '',
        'A suspended thin-film membrane, resistive heater, power switch and ADC are',
        'off-chip. The synthesizable chip is a controller with synchronous ADC input,',
        'register interface, PI/feedforward operation, pulse-width modulation and',
        'latched faults. This does not include fabrication, an analogue readout or pads.',
        '', '## 2. Numerical model', '',
        f"Finite-volume validation: {'all gates passed' if all(physics['gates'].values()) else 'failed or incomplete gates'}.",
        'A two-dimensional thin-film electrothermal solver generated the reference data.',
        'The response of a fitted one-node passive thermal model is then used as the',
        'evaluation plant, with a separately reported fit error.',
        '', '| Recorded quantity | Value |', '|---|---:|',
        f"| Positive-parameter thermal resistance (K/W) | {f(physics['compact_model']['r_th_k_per_w'])} |",
        f"| Thermal capacitance (J/K) | {f(physics['compact_model']['c_th_j_per_k'])} |",
        f"| Held-out compact-model RMSE (°C) | {f(physics['compact_model']['heldout_rmse_c'])} |",
    ]
    for m in physics['meshes']:
        lines.append(f"| Peak model T on {m['cell_m']*1e6:g} µm mesh (°C) | {f(m['active_peak_c'])} |")
    lines += ['', 'Sources: `outputs/physics/validation.json`, matching raw `steady_*um.npz`,',
              '`configs/physics.json`, `configs/materials.json`, and solver source.',
              '', '## 3. Paired closed-loop results', '',
              f"Scenarios: {experiments['scenario_count']}; numerical sample time: {f(experiments['step_s']*1e3)} ms;",
              f"cycle duration: {f(experiments['time_s'])} s. Cases use deterministic seeds.",
              'Heater energy is integrated as duty × terminal power × sample time.',
              'Performance statistics do **not** include digital chip energy.',
              '', '| Controller | Mean hold RMSE (°C) | Worst hold RMSE (°C) | Mean Δheater energy vs primary fixed PI (mJ) |',
              '|---|---:|---:|---:|']
    for name, x in experiments['paired_results'].items():
        lines.append(f"| {name} | {f(x['mean_hold_rmse_c'])} | {f(x['worst_hold_rmse_c'])} | {f(x['mean_energy_delta_mj_vs_pi_fixed'])} |")
    lines += ['', 'Primary PI/feedforward variants are model-level comparisons:',
              'the behavioural plant is not clock-accurate RTL-in-loop. The 14/16/20-bit',
              'arithmetic alternatives have **not** been physically implemented.',
              '', '## 4. Physical implementation', '']
    if physical is None:
        lines += ['The controller flow has not produced an auditable result in this run.',
                  'Do not claim a verified GDS until the physical stage succeeds.']
    else:
        lines += [f"Status: **{physical['status']}**. LibreLane SKY130A standard-cell core,",
                  '100 ns constraint (10 MHz), no IO padframe.', '',
                  '| Physical audit gate | Result |', '|---|---|']
        for name, value in physical.get('checks',{}).items():
            lines.append(f"| {name} | {'PASS' if value else 'FAIL / MISSING'} |")
        lines += ['', '| Implementation metric | Value |', '|---|---:|']
        for name, value in physical.get('metrics',{}).items():
            if value is not None:
                lines.append(f'| `{name}` | {value} |')
        lines += ['', 'Full evidence: `release_out/physical/audit.json`, tool logs,',
                  'and any copied GDS/DEF/netlist under `release_out/physical/`.']
    lines += ['', '## 5. Reproduction and review', '',
              'Run `python3 -m release.runner` from the existing tools container',
              'after synchronizing the unchanged parent project and loading SKY130A.',
              'The PowerShell launcher `release/Run-ThermoBridge.ps1` automates this.',
              'Logs, status and checksums are preserved in `release_out/`.',
              '', '## 6. Limitations', '',
              '- All input material properties, dimensions and environment distributions are assumed.',
              '- Spatial-FVM validation is numerical, not experimental or an independent FEM cross-check.',
              '- Real RTL verification is through Icarus/cocotb tests; paired temperature traces use Python model controllers.',
              '- Experimental gas-sensor response, FPGA proof, calibration and chip measurements are absent.',
              '- A routed standard-cell core is not a manufacturable stand-alone sensor ASIC.',
              '- No authored results were backdated; each run has its real UTC timestamp.', '',
              '### Traceability', '',
              f'- Electrothermal validation SHA256: `{file_hash(phy_file)}`',
              f'- Closed-loop summary SHA256: `{file_hash(data_file)}`',
              '']
    path = out/'REPORT.md'
    path.write_text('\n'.join(lines),encoding='utf-8')
    return path

if __name__=='__main__':
    print(write_report())
