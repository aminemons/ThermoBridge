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
for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',(ROOT/'README.md').read_text()):
    assert (ROOT/target).is_file(),'Broken README image: '+target
for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',(ROOT/'README.md').read_text()):
    if target.startswith(('https://','http://','#')):continue
    assert (ROOT/target.split('#')[0]).exists(),'Broken README link: '+target
print(json.dumps({'status':'PASS: conditional research snapshot, not all aspirational targets','engineering_targets':snapshot['engineering_targets'],'limitations':'docs/LIMITATIONS.md'},indent=2))
if a.strict and not all(snapshot['engineering_targets'].values()):raise SystemExit(1)
