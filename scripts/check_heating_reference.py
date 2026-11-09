"""Compute an ideal no-preheating reference for the declared sampled RC plant."""
from dataclasses import replace
from datetime import datetime, timezone
import csv
import json
import math
import platform
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.physics.rc import ThermalRC
from scripts.run_manifest import write_manifest


def main():
    started = datetime.now(timezone.utc)
    baseline = json.loads((ROOT / 'configs/evaluation_v1.json').read_text())
    protocol_path = ROOT / 'configs/rtl_study_v3.json'
    protocol = json.loads(protocol_path.read_text())
    values = baseline['baseline']
    model = ThermalRC(**{key: values[key] for key in [
        'r_th_k_per_w', 'c_th_j_per_k', 'ambient_c', 'heater_v',
        'heater_r_ohm', 'r_tcr_per_k',
    ]})
    dt = baseline['time_step_s']
    count = round(baseline['cycle']['hold_tau'] * model.tau_s / dt)
    step = round(count * baseline['cycle']['step_at_hold_fraction'])
    output = ROOT / 'results/heating_reference' / started.strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    metrics = []
    for case in protocol['evaluation']:
        if case['previously_observed']:
            continue
        for voltage in [.15, .18]:
            plant = replace(model, ambient_c=case['ambient_c'], heater_v=voltage)
            temperature = case['initial_setpoint_c']
            trace = []
            for index in range(count):
                target = case['initial_setpoint_c'] + (case['step_c'] if index >= step else 0)
                next_off = plant.step(temperature, 0, dt)
                next_on = plant.step(temperature, 1, dt)
                duty = min(1., max(0., (target - next_off) / (next_on - next_off)))
                trace.append({'t_s': index * dt, 'temp_c': temperature, 'setpoint_c': target, 'duty': duty})
                temperature = plant.step(temperature, duty, dt)
            with (output / f"{case['id']}-{voltage}.csv").open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(trace[0]))
                writer.writeheader()
                writer.writerows(trace)
            rmse = math.sqrt(sum((row['temp_c'] - row['setpoint_c'])**2 for row in trace) / count)
            metrics.append({'case': case['id'], 'heater_v': voltage, 'rmse_hold_c': rmse})
    report = {
        'run': output.relative_to(ROOT).as_posix(), 'metrics': metrics,
        'assumptions': 'Exact initial tracking, perfect readout, continuous duty, full heating after an unanticipated step, no preheating. Actual controllers may have a different temperature at the step.',
        'scope': 'Conditional no-preheating reference. It does not optimize anticipatory trajectories or certify a global tracking lower bound.',
    }
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    write_manifest(
        output / 'manifest.json', run_id=output.name,
        command=[sys.executable, 'scripts/check_heating_reference.py'],
        input_paths=[protocol_path, ROOT / 'configs/evaluation_v1.json', ROOT / 'src/physics/rc.py'],
        seed=None, started=started, status='complete',
        output_paths=list(output.glob('*.csv')) + [output / 'summary.json'],
        extra={'tool_versions': {'python': platform.python_version()}, 'execution_platform': platform.platform(), 'environment_manifest_sha256': None},
    )
    (ROOT / 'reports/heating_reference.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(metrics, indent=2))


if __name__ == '__main__':
    main()
