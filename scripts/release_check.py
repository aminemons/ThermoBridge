"""Check research-snapshot evidence; --strict also enforces unmet target gates."""
from pathlib import Path
import argparse,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--strict',action='store_true');p.add_argument('--physical-only',action='store_true');p.add_argument('--operating-point',action='store_true');a=p.parse_args()

def verify_manifest_outputs(path):
    value = json.loads(path.read_text())
    assert value['status'] == 'complete', 'Incomplete run: ' + str(path)
    for name, digest in value['outputs'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, 'Changed run output: ' + name
physical=json.loads((ROOT/'reports/asic/summary.json').read_text())
assert all(physical['checks'].values()),'Physical evidence includes failed gates'
assert hashlib.sha256((ROOT/'rtl/thermobridge_top.sv').read_bytes()).hexdigest()==physical['rtl_sha256'],'RTL differs from physically implemented source'
assert hashlib.sha256((ROOT/'flow/adc15.sdc').read_bytes()).hexdigest()==physical['sdc_sha256'],'Timing constraints differ'
assert hashlib.sha256((ROOT/'results/asic/mag_gds/thermobridge_top.magic.gds').read_bytes()).hexdigest()==physical['gds_sha256'],'GDS differs from verified geometry'
if a.physical_only:
    print('PASS: unchanged routed geometry DRC/LVS; timing conditional on ADC15 contract.');raise SystemExit(0)
snapshot=json.loads((ROOT/'reports/release_snapshot.json').read_text())
assert all(snapshot['physics_gates'].values())
for path,digest in snapshot['evidence_sha256'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Stale/missing evidence: '+path
assert snapshot['rtl_in_loop']['powered_fault_count']==0
assert json.loads((ROOT/'reports/pwm_validation.json').read_text())['pass']
assert (ROOT/'reports/technical_report.pdf').is_file()
readme=(ROOT/'README.md').read_text(encoding='utf-8')
for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',readme):
    assert (ROOT/target).is_file(),'Broken README image: '+target
for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',readme):
    if target.startswith(('https://','http://','#')):continue
    assert (ROOT/target.split('#')[0]).exists(),'Broken README link: '+target
article=ROOT/'reports/article_manifest.json'
if article.exists():
    manifest=json.loads(article.read_text(encoding='utf-8'))
    for group in ['inputs','outputs']:
        for path,digest in manifest[group].items():
            assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,'Stale article evidence: '+path
    study=json.loads((ROOT/'reports/rtl_study_v2.json').read_text())
    full=json.loads((ROOT/study['run']/'summary.json').read_text())
    assert len(full['training'])==12 and sum(len(c['runs']) for c in full['training'])==36
    assert len(study['evaluation'])==10 and all(r['powered_fault_count']==0 for r in study['evaluation'])
    assert study['selected']==json.loads((ROOT/study['run']/'selection.json').read_text())
    assert study['selected']['mean_training_rmse_c']==min(c['mean_training_rmse_c'] for c in full['training'])
    runs=[r for c in full['training'] for r in c['runs']]+study['evaluation']
    for run in runs:
        path=ROOT/'results/raw/experiments'/run['run_id']/'manifest.json';value=json.loads(path.read_text())
        assert value['status']=='complete'
        for output,digest in value['outputs'].items():
            assert hashlib.sha256((ROOT/output).read_bytes()).hexdigest()==digest,'Changed RTL run output: '+output
    geometry=json.loads((ROOT/'reports/geometry_study.json').read_text())
    assert geometry['geometry_count']==27 and geometry['operating_points']==81 and not geometry['failures']
    assert geometry['max_power_balance_rel']<.01 and geometry['max_thermal_balance_rel']<.01
    assert all(r['status']=='solved' and abs(r['mean_c']-55)<.05 for r in geometry['refined_candidates'])
    directory=ROOT/geometry['run'];gm=json.loads((directory/'manifest.json').read_text())
    for output,digest in gm['outputs'].items():
        assert hashlib.sha256((ROOT/output).read_bytes()).hexdigest()==digest,'Changed spatial evidence: '+output
    assert hashlib.sha256((directory/'source/fvm.py').read_bytes()).hexdigest()==gm['input_sha256']['src/physics/fvm.py']
operating_targets = None
if (ROOT / 'reports/rtl_study_v4.json').exists():
    for name, training_count, evaluation_count in [('rtl_study_v3.json', 36, 16), ('rtl_study_v4.json', 3, 16)]:
        report = json.loads((ROOT / 'reports' / name).read_text())
        folder = ROOT / report['run']
        summary = json.loads((folder / 'summary.json').read_text())
        protocol = json.loads((folder / 'protocol.json').read_text())
        training_runs = [run for candidate in summary['training'] for run in candidate['runs']]
        assert len(training_runs) == training_count and len(report['evaluation']) == evaluation_count
        assert report['selected'] == json.loads((folder / 'selection.json').read_text())
        assert report['selected']['mean_training_rmse_c'] == min(candidate['mean_training_rmse_c'] for candidate in summary['training'])
        assert not ({case['id'] for case in protocol['training']} & {case['id'] for case in protocol['evaluation']})
        verify_manifest_outputs(folder / 'manifest.json')
        for run in training_runs + report['evaluation']:
            assert run['powered_fault_count'] == 0
            verify_manifest_outputs(ROOT / 'results/raw/experiments' / run['run_id'] / 'manifest.json')
    validation = json.loads((ROOT / 'reports/operating_point_validation.json').read_text())
    assert all(validation['checks'].values())
    verify_manifest_outputs(ROOT / validation['run'] / 'manifest.json')
    reference = json.loads((ROOT / 'reports/heating_reference.json').read_text())
    verify_manifest_outputs(ROOT / reference['run'] / 'manifest.json')
    fresh = [run for run in report['evaluation'] if run['study_label'] == 'retuned' and not run['previously_observed']]
    assert len(fresh) == 6
    assert all(run['heater_voltage_v'] == .18 for run in fresh)
    operating_targets = {
        'six_fresh_cases_rmse_le_2_c': all(run['rmse_hold_c'] <= 2 for run in fresh),
        'six_fresh_cases_overshoot_le_5_c': all(run['overshoot_hold_c'] <= 5 for run in fresh),
        'spatial_validation': all(validation['checks'].values()),
    }
    for run in fresh:
        baseline = next(item for item in report['evaluation'] if item['scenario_id'] == run['scenario_id'] and item['study_label'] == 'baseline')
        assert baseline['heater_voltage_v'] == .15
        assert (baseline['kp_q14'], baseline['ki_per_sample_q14'], baseline['readout']) == (run['kp_q14'], run['ki_per_sample_q14'], run['readout'])
if a.operating_point:
    assert operating_targets and all(operating_targets.values()), 'Operating-point targets are unmet or missing'
print(json.dumps({'status':'PASS: conditional research snapshot','legacy_0p15v_targets':snapshot['engineering_targets'],'operating_0p18v_targets':operating_targets,'limitations':'docs/LIMITATIONS.md'},indent=2))
if a.strict and not all(snapshot['engineering_targets'].values()):raise SystemExit(1)
