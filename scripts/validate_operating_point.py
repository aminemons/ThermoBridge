"""Validate the proposed heater operating point against the spatial model."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.physics.fvm import ElectroThermalFVM, Params
from src.physics.rc import ThermalRC
from scripts.run_manifest import write_manifest


def main():
    started = datetime.now(timezone.utc)
    protocol_path = ROOT / 'configs/operating_point_validation_v1.json'
    protocol = json.loads(protocol_path.read_text())
    baseline = json.loads((ROOT / 'configs/evaluation_v1.json').read_text())['baseline']
    parameters = replace(
        Params.from_json(ROOT / 'configs/physics.json'),
        voltage_v=protocol['heater_voltage_v'],
    )
    model = ElectroThermalFVM(parameters)
    compact = ThermalRC(
        r_th_k_per_w=baseline['r_th_k_per_w'],
        c_th_j_per_k=baseline['c_th_j_per_k'],
        ambient_c=baseline['ambient_c'],
        heater_v=protocol['heater_voltage_v'],
        heater_r_ohm=baseline['heater_r_ohm'],
        r_tcr_per_k=baseline['r_tcr_per_k'],
    )
    output = ROOT / 'results/operating_point' / started.strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    simulations = []
    for dt in protocol['time_steps_s']:
        times = np.arange(round(protocol['duration_s'] / dt) + 1) * dt
        duties = np.where(times < protocol['pulse_duration_s'], 1., 0.)
        simulation = model.simulate_transient(duties, times)
        prediction = [compact.ambient_c]
        for duty in duties[:-1]:
            prediction.append(compact.step(prediction[-1], float(duty), dt))
        error = np.asarray(prediction) - simulation['active_mean_c']
        peak_index = int(np.argmax(simulation['active_peak_c']))
        filename = output / f'pulse-{dt}.npz'
        np.savez_compressed(
            filename, times_s=times, duty=duties,
            spatial_mean_c=simulation['active_mean_c'],
            spatial_peak_c=simulation['active_peak_c'], compact_c=prediction,
            spatial_peak_map_c=simulation['temperature_c'][peak_index],
            domain_mask=model.domain, x_m=model.x, y_m=model.y,
        )
        simulations.append({
            'dt_s': dt, 'rmse_c': float(np.sqrt(np.mean(error**2))),
            'max_abs_error_c': float(np.max(np.abs(error))),
            'max_spatial_temperature_c': float(np.max(simulation['active_peak_c'])),
            'samples': len(times),
        })
        print('SPATIAL', dt, simulations[-1], flush=True)

    coarse = np.load(output / f"pulse-{protocol['time_steps_s'][0]}.npz")
    fine = np.load(output / f"pulse-{protocol['time_steps_s'][1]}.npz")
    interpolated = np.interp(coarse['times_s'], fine['times_s'], fine['spatial_mean_c'])
    change = float(np.max(np.abs(coarse['spatial_mean_c'] - interpolated)))
    relative = change / float(np.max(fine['spatial_mean_c']) - parameters.ambient_c)
    checks = {
        'compact_rmse': all(s['rmse_c'] <= protocol['compact_rmse_limit_c'] for s in simulations),
        'time_step_refinement': relative <= protocol['refinement_relative_limit'],
        'material_temperature_range': all(
            parameters.valid_min_c <= s['max_spatial_temperature_c'] <= parameters.valid_max_c
            for s in simulations
        ),
    }
    summary = {
        'run': output.relative_to(ROOT).as_posix(), 'protocol': protocol,
        'simulations': simulations, 'max_refinement_change_c': change,
        'refinement_relative': relative, 'checks': checks,
        'compact_parameters_refitted': False,
    }
    path = output / 'summary.json'
    path.write_text(json.dumps(summary, indent=2) + '\n')
    write_manifest(
        output / 'manifest.json', run_id=output.name,
        command=[sys.executable, 'scripts/validate_operating_point.py'],
        input_paths=[protocol_path, ROOT / 'configs/evaluation_v1.json', ROOT / 'configs/physics.json', ROOT / 'configs/materials.json', ROOT / 'src/physics/fvm.py', ROOT / 'src/physics/rc.py'],
        seed=None, started=started, status='complete' if all(checks.values()) else 'failed',
        output_paths=[path, *output.glob('*.npz')],
        extra={'tool_versions': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__}},
    )
    (ROOT / 'reports/operating_point_validation.json').write_text(json.dumps(summary, indent=2) + '\n')
    if not all(checks.values()):
        raise SystemExit('Operating point validation failed; inspect the recorded checks')


if __name__ == '__main__':
    main()
