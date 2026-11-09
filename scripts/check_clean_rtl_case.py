"""Reproduce a frozen RTL case from the recorded clean Git archive."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=Path('reports/rtl_study_v2.json'))
    parser.add_argument('--case')
    options = parser.parse_args()
    reproduction = json.loads((ROOT / 'reports/reproduction/summary.json').read_text())
    study = json.loads((ROOT / options.report).read_text())
    expected = next(
        run for run in study['evaluation']
        if run['study_label'] == 'retuned'
        and (run['scenario_id'] == options.case if options.case else not run['previously_observed'])
    )
    command = [
        'python3', 'scripts/run_rtl_experiment.py',
        '--protocol', 'configs/' + options.report.name,
        '--case', expected['scenario_id'],
        '--kp-q14', str(expected['kp_q14']),
        '--ki-q14', str(expected['ki_per_sample_q14']),
        '--calibration-c', *map(str, expected['readout']['calibration_c']),
    ]
    if 'heater_voltage_v' in expected:
        command.extend(['--heater-v', str(expected['heater_voltage_v'])])
    setup = (
        'source /foss/tools/sak/sak-pdk-script.sh sky130A sky130_fd_sc_hd >/dev/null; '
        'cd ' + shlex.quote(reproduction['runtime']) + '; exec ' + shlex.join(command)
    )
    docker = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker'
    result = subprocess.run(
        [docker, 'exec', '-u', '1000:1000', '-e', 'IIC_OSIC_TOOLS_QUIET=1',
         reproduction['container'], 'bash', '-lc', setup],
        capture_output=True, text=True,
    )
    suffix = options.report.stem.rsplit('_', 1)[-1]
    log = ROOT / f'reports/reproduction/rtl_{suffix}_case.log'
    log.write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Clean RTL case failed. Inspect ' + str(log))
    marker = 'RTL-in-loop trace saved: '
    owned = next(line[len(marker):] for line in result.stdout.splitlines() if line.startswith(marker))
    metric = json.loads(subprocess.check_output(
        [docker, 'exec', reproduction['container'], 'cat', owned + '/metrics.json'], text=True,
    ))
    passed = all(
        math.isclose(metric[key], expected[key], rel_tol=1e-10, abs_tol=1e-12)
        for key in ['rmse_hold_c', 'energy_total_j', 'sensing_energy_j']
    ) and metric['powered_fault_count'] == 0
    report = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'source_commit': reproduction['source_commit'],
        'case': metric['scenario_id'], 'run_id': metric['run_id'],
        'heater_voltage_v': metric.get('heater_voltage_v', .15),
        'rmse_hold_c': metric['rmse_hold_c'], 'energy_total_j': metric['energy_total_j'],
        'comparison': 'Frozen RMSE and energy, relative tolerance1e-10 and absolute tolerance1e-12',
        'pass': passed, 'scope': 'One actual RTL feedback case in the recorded fresh Git extraction',
    }
    (ROOT / f'reports/reproduction/rtl_{suffix}_case.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
