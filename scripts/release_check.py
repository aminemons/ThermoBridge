"""Check research-snapshot evidence; --strict also enforces unmet target gates."""
from pathlib import Path
import argparse,hashlib,json,re
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--strict',action='store_true');p.add_argument('--physical-only',action='store_true');a=p.parse_args()
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
print(json.dumps({'status':'PASS: conditional research snapshot, not all aspirational targets','engineering_targets':snapshot['engineering_targets'],'limitations':'docs/LIMITATIONS.md'},indent=2))
if a.strict and not all(snapshot['engineering_targets'].values()):raise SystemExit(1)
