"""Deterministic paired closed-loop experiments on the spatial-model-fitted RC plant.

The heater/ADC/power switch are behavioural/external. This is NOT an RTL-in-loop
co-simulation: the original cocotb testbench checks the separate digital RTL.
Alternatives with different arithmetic widths are Python-only evaluations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LUT = [0,14,28,43,59,74,91,108,125,143,161,180,199,218,239,256]
DT = 0.001
STEPS = 460
# 0-180 ms 65 C; 180-360 ms 80 C; 360-460 ms unpowered cooldown.
CTRL_NAMES = ('bangbang', 'pi_float', 'pi_fixed', 'ffpi_fixed', 'pi_compact', 'pi_wide')


def rounded_even_div(num: int, den: int) -> int:
    if den <= 0:
        raise ValueError('denominator must be positive')
    sign = -1 if num < 0 else 1
    quotient, remainder = divmod(abs(num), den)
    if 2 * remainder > den or (2 * remainder == den and (quotient & 1)):
        quotient += 1
    return sign * quotient


def sat(x: int, bits: int) -> int:
    return max(-(1 << (bits-1)), min((1 << (bits-1))-1, int(x)))


def qconvert(value: float, fraction_bits: int, total_bits: int) -> int:
    return sat(round(value * (1 << fraction_bits)), total_bits)


@dataclass(frozen=True)
class Scenario:
    number: int
    seed: int
    ambient_c: float
    rth_multiplier: float
    resistance_multiplier: float
    tcr_multiplier: float
    noise_sigma_c: float
    delay_samples: int


def scenarios(count: int = 24, seed: int = 270102) -> list[Scenario]:
    if count < 20:
        raise ValueError('at least 20 independent cases required for main experiment')
    rng = random.Random(seed)
    cases = [Scenario(0, seed, 25., 1., 1., 1., 0., 0)]
    for i in range(1, count):
        cases.append(Scenario(i, rng.randrange(1, 2**31),
                              round(rng.uniform(20, 30), 4),
                              round(rng.uniform(.8, 1.2), 6),
                              round(rng.uniform(.85, 1.15), 6),
                              round(rng.uniform(.75, 1.25), 6),
                              (0., .15, .3)[i % 3], i % 3))
    return cases


def setpoint_at(step: int) -> float | None:
    if step < 180:
        return 65.
    if step < 360:
        return 80.
    return None


def feedforward_duty(temp_c: float) -> int:
    if temp_c < 25:
        return 0
    return DEFAULT_LUT[max(0, min(15, int((temp_c - 25.) // 5.)))]


class Controller:
    def __init__(self, mode: str):
        self.mode = mode
        self.i_q8 = 0
        self.i_float = 0.
        self.last_duty = 0.
        # Nominal continuous per-sample PI gains in Q8 duty per degree C.
        # Exact fixed arithmetic gain scales: round(k * 2^frac / 2^(8-temp_frac)).
        self.kp_duty_per_c = 5.0
        self.ki_duty_per_c = .4

    def update(self, measured: float, setpoint: float | None) -> float:
        if setpoint is None:
            self.i_q8 = 0
            self.i_float = 0.
            self.last_duty = 0.
            return 0.
        error = setpoint - measured
        if self.mode == 'bangbang':
            if error > .5:
                self.last_duty = 256.
            elif error < -.5:
                self.last_duty = 0.
            return self.last_duty
        if self.mode == 'pi_float':
            p = self.kp_duty_per_c * error
            proposed = p + self.i_float
            delta = self.ki_duty_per_c * error
            if not ((proposed >= 256 and error > 0) or (proposed <= 0 and error < 0)):
                self.i_float = min(2**23-1., max(-2**23, self.i_float + delta))
            self.last_duty = min(256., max(0., proposed + delta))
            return self.last_duty

        temp_bits, frac, coeff_bits, coeff_frac = {
            'pi_fixed': (16, 6, 18, 14),
            'ffpi_fixed': (16, 6, 18, 14),
            'pi_compact': (14, 4, 16, 12),
            'pi_wide': (20, 8, 20, 16),
        }[self.mode]
        # ADC is 12-bit, with 16 codes/C (nominal); in silicon the primary
        # calibration uses 18-bit Q14 gain=65536 -> 4 Q6 units/code.
        measured_q = qconvert(measured, frac, temp_bits)
        setpoint_q = qconvert(setpoint, frac, temp_bits)
        err_q = sat(setpoint_q - measured_q, temp_bits)
        # Duty_Q8 = (gain_coeff * error_q) / 2^(coeff_frac + frac - 8).
        kp = qconvert(self.kp_duty_per_c / 256., coeff_frac, coeff_bits)
        ki = qconvert(self.ki_duty_per_c / 256., coeff_frac, coeff_bits)
        shift = coeff_frac + frac - 8
        p = sat(rounded_even_div(kp * err_q, 1 << shift), 24)
        di = sat(rounded_even_div(ki * err_q, 1 << shift), 24)
        ff = feedforward_duty(setpoint) if self.mode == 'ffpi_fixed' else 0
        before = p + self.i_q8 + ff
        if not ((before >= 256 and err_q > 0) or (before <= 0 and err_q < 0)):
            self.i_q8 = sat(self.i_q8 + di, 24)
        self.last_duty = float(max(0, min(256, before + di)))
        return self.last_duty


def run_case(scenario: Scenario, controller: str, fit: dict, heater: dict) -> tuple[dict, list[dict]]:
    rng = random.Random(scenario.seed)
    rth = float(fit['r_th_k_per_w']) * scenario.rth_multiplier
    cth = float(fit['c_th_j_per_k'])
    p0 = float(heater['full_on_power_w']) / scenario.resistance_multiplier
    tcr = .0032 * scenario.tcr_multiplier  # illustrative platinum-like TCR
    temperature = scenario.ambient_c
    plant_step = math.exp(-DT / (rth * cth))
    ctrl = Controller(controller)
    past = [temperature]
    data = []
    total_energy_j = 0.
    errors = []
    peak_excess = [0., 0.]
    for step in range(STEPS):
        setpoint = setpoint_at(step)
        observed = past[max(0, len(past) - 1 - scenario.delay_samples)] + rng.gauss(0, scenario.noise_sigma_c)
        # Round-trip through a 12-bit ADC for hardware-style controllers.
        if controller in ('pi_fixed', 'ffpi_fixed', 'pi_compact', 'pi_wide'):
            adc_code = max(1, min(4094, round(observed * 16)))
            observed = adc_code / 16.
        duty_q8 = ctrl.update(observed, setpoint)
        duty = duty_q8 / 256.
        resistance_factor = 1 + tcr * (temperature - 25.)
        if resistance_factor <= 0:
            raise ValueError('heater TCR model invalid')
        power_w = duty * p0 / resistance_factor
        eq_c = scenario.ambient_c + rth * power_w
        next_temperature = eq_c + (temperature - eq_c) * plant_step
        energy_step = power_w * DT
        total_energy_j += energy_step
        if setpoint is not None:
            errors.append(temperature - setpoint)
            window = 0 if step < 180 else 1
            peak_excess[window] = max(peak_excess[window], temperature - setpoint)
        data.append({'scenario': scenario.number, 'controller': controller,
                     'time_s': step * DT, 'temperature_c': temperature,
                     'measured_c': observed, 'setpoint_c': setpoint if setpoint is not None else '',
                     'duty_q8': duty_q8, 'heater_power_w': power_w,
                     'heater_energy_j': total_energy_j})
        temperature = next_temperature
        past.append(temperature)
    hold_errors = [x['temperature_c'] - float(x['setpoint_c']) for x in data
                   if (110 <= round(x['time_s']/DT) < 180) or (290 <= round(x['time_s']/DT) < 360)]
    metrics = {
        'scenario': scenario.number, 'controller': controller,
        'heater_energy_mj': total_energy_j * 1000,
        'active_rmse_c': math.sqrt(sum(x*x for x in errors)/len(errors)),
        'hold_rmse_c': math.sqrt(sum(x*x for x in hold_errors)/len(hold_errors)),
        'active_max_abs_c': max(map(abs, errors)),
        'overshoot_c': max(peak_excess),
        'final_c': temperature,
        'faults_modelled': False,
    }
    return metrics, data


def evaluate(root: Path = ROOT, count: int = 24, seed: int = 270102) -> dict:
    validation_file = root/'outputs'/'physics'/'validation.json'
    if not validation_file.is_file():
        raise FileNotFoundError(f'{validation_file} missing; first run scripts/run_physics.py')
    validation = json.loads(validation_file.read_text(encoding='utf-8'))
    if not all(validation.get('gates', {}).values()):
        raise RuntimeError('physics validation contains failed gate(s); do not use fit as verified')
    fit = validation['compact_model']
    heater = validation['primary_heater_at_ambient']
    cases = scenarios(count, seed)
    out = root/'release_out'/'experiments'; out.mkdir(parents=True, exist_ok=True)
    results = []
    path = out/'traces.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['scenario','controller','time_s','temperature_c','measured_c','setpoint_c','duty_q8','heater_power_w','heater_energy_j'])
        writer.writeheader()
        for scenario in cases:
            for name in CTRL_NAMES:
                result, trace = run_case(scenario, name, fit, heater)
                results.append(result)
                writer.writerows(trace)
    metrics_path = out/'metrics.csv'
    with metrics_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader(); writer.writerows(results)
    (out/'scenarios.json').write_text(json.dumps([s.__dict__ for s in cases], indent=2)+'\n', encoding='utf-8')
    nominal = {x['controller']: x for x in results if x['scenario'] == 0}
    paired = {}
    baseline = {x['scenario']: x for x in results if x['controller'] == 'pi_fixed'}
    for name in CTRL_NAMES:
        selected = [x for x in results if x['controller'] == name]
        deltas = [x['heater_energy_mj'] - baseline[x['scenario']]['heater_energy_mj'] for x in selected]
        paired[name] = {'mean_energy_delta_mj_vs_pi_fixed': statistics.mean(deltas),
                        'mean_hold_rmse_c': statistics.mean(x['hold_rmse_c'] for x in selected),
                        'worst_hold_rmse_c': max(x['hold_rmse_c'] for x in selected)}
    summary = {'schema': 'thermobridge-closedloop-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
               'plant': 'one-node RC compact fit from previously validated spatial FVM (assumed parameters)',
               'digital_status': 'Python behavioural simulation only; RTL validation is separate',
               'noise_status': 'illustrative Gaussian noise and delayed ADC readings, not measurements',
               'thermal_fit': {x:fit[x] for x in ('r_th_k_per_w','c_th_j_per_k','heldout_rmse_c')},
               'scenario_count': len(cases), 'seed': seed, 'step_s': DT, 'time_s': STEPS*DT,
               'controllers': list(CTRL_NAMES), 'nominal_metrics': nominal,
               'paired_results': paired,
               'data_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,metrics_path,out/'scenarios.json')},
               'limitations': ['one-node ROM not full transient spatial FVM in loop',
                               'no fault/recovery dynamics', 'alternative widths Python-only',
                               'no measured plant', 'float and fixed compare behavioural algorithms, not cycle-accurate RTL'],
               'gates': {'scenario_count_at_least_20': len(cases)>=20,
                         'all_metrics_finite': all(math.isfinite(v) for x in results for k,v in x.items() if isinstance(v, float))}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=24)
    parser.add_argument('--seed', type=int, default=270102)
    args = parser.parse_args()
    s = evaluate(count=args.count,seed=args.seed)
    print(json.dumps({'scenario_count':s['scenario_count'],'nominal_metrics':s['nominal_metrics'],
                      'paired_results':s['paired_results']},indent=2))

if __name__ == '__main__':
    main()
