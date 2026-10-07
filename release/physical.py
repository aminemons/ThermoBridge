"""LibreLane SKY130A end-to-end flow with strict, evidence-based signoff audit.

Runs in the *existing* IIC-OSIC-TOOLS Linux container. Never silently skips DRC,
LVS, area, timing, or output presence checks, and never labels this tapeout-ready.
"""
from __future__ import annotations
import argparse
import json
import hashlib
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'release_out'/'physical'
TAG = 'thermobridge_release'
REQUIRED_ZERO = (
    'route__drc_errors', 'magic__drc_error__count', 'klayout__drc_error__count',
    'design__lvs_error__count', 'design__lvs_device_difference__count',
    'design__lvs_net_difference__count', 'design__lvs_unmatched_device__count',
    'design__lvs_unmatched_net__count', 'design__lvs_unmatched_pin__count',
    'timing__hold_vio__count', 'timing__setup_vio__count',
)


def locate_run() -> Path | None:
    """Find latest controller run only, not previous smoke or other designs."""
    candidates = []
    for base in [ROOT/'release'/'flow'/'runs', ROOT/'runs', ROOT/'release'/'runs']:
        if base.exists():
            candidates.extend(x for x in base.iterdir() if x.is_dir() and TAG in x.name)
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _metrics_path(run: Path | None) -> Path | None:
    if run is None:
        return None
    candidates = [run/'final'/'metrics.json',run/'metrics.json']
    candidates.extend(run.glob('final/**/metrics.json'))
    return next((p for p in candidates if p.is_file()), None)


def audit(run: Path | None) -> dict:
    checks = {}
    metrics_file = _metrics_path(run)
    metrics = json.loads(metrics_file.read_text()) if metrics_file else {}
    for key in REQUIRED_ZERO:
        checks[key] = metrics.get(key) == 0
    setup = metrics.get('timing__setup__ws')
    hold = metrics.get('timing__hold__ws')
    checks['setup_slack_nonnegative'] = isinstance(setup,(int,float)) and setup >= 0
    checks['hold_slack_nonnegative'] = isinstance(hold,(int,float)) and hold >= 0
    checks['stdcell_area_available'] = isinstance(metrics.get('design__instance__area__stdcell'),(int,float)) and metrics['design__instance__area__stdcell'] > 0
    final = (run/'final') if run else None
    artifacts = {}
    if final and final.is_dir():
        for typ, pattern in {'gds':'*.gds','def':'*.def','netlist':'*.nl.v','lef':'*.lef','sdc':'*.sdc','spef':'*.spef'}.items():
            found = list(final.rglob(pattern))
            if typ=='netlist' and not found:
                found = list(final.rglob('*.v'))
            artifacts[typ] = str(found[0]) if found else None
    checks['gds_exists'] = bool(artifacts.get('gds'))
    checks['def_exists'] = bool(artifacts.get('def'))
    checks['netlist_exists'] = bool(artifacts.get('netlist'))
    # SDC, LEF and SPEF are archived when present, but no blanket completeness
    # claim is made if versions/tool paths differ.
    result = {
        'checked_utc':datetime.now(timezone.utc).isoformat(),
        'flow':'LibreLane Classic, SKY130A / sky130_fd_sc_hd, 10 MHz, digital CORE ONLY',
        'run_path':str(run) if run else None,
        'metrics_path':str(metrics_file) if metrics_file else None,
        'status':'PASS' if all(checks.values()) else 'INCOMPLETE_OR_FAIL',
        'checks':checks,
        'metrics':{k:metrics.get(k) for k in sorted(set(REQUIRED_ZERO + ('design__instance__area__stdcell','design__core__area','design__instance__area','timing__setup__ws','timing__hold__ws','antenna__violating__pins','antenna__violating__nets')))},
        'artifacts':artifacts,
        'limitations':['not a padframe, ESD, packaged ASIC or fabricated silicon',
                       'PDK flow checks, not foundry-qualified signoff',
                       'no integrated MEMS membrane or analogue sensor readout',
                       'reported GDS only valid when the actual flow completes']}
    return result


def run_physical(jobs:int=2) -> dict:
    OUT.mkdir(parents=True,exist_ok=True)
    if shutil.which('librelane') is None:
        raise RuntimeError('librelane missing inside container; do not pip install or pull another image automatically')
    if not (ROOT/'rtl'/'thermobridge_top.sv').is_file():
        raise FileNotFoundError('Missing original controller RTL')
    config=ROOT/'release'/'flow'/'config.json'
    if not config.is_file(): raise FileNotFoundError(config)
    run = locate_run()
    # Deterministic retry: reuse a previously completed run only if audited PASS
    # and the input RTL and config hashes still match a saved receipt.
    inputs = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (config,ROOT/'release'/'flow'/'constraints.sdc',ROOT/'rtl'/'thermobridge_top.sv')}
    receipt=OUT/'input_hashes.json'
    if run and receipt.is_file():
        cached=json.loads(receipt.read_text())
        cached_audit=audit(run)
        if cached == inputs and cached_audit['status']=='PASS':
            print('Reusing audited completed controller flow with identical inputs')
            materialize(cached_audit)
            return cached_audit
    cmd=['librelane','--flow','Classic','--jobs',str(max(1,min(2,jobs))),
         '--run-tag',TAG+'_'+str(int(time.time())),str(config)]
    logfile=OUT/'librelane.log'
    with logfile.open('w', encoding='utf-8', errors='replace') as stream:
        stream.write('COMMAND: '+' '.join(cmd)+'\n'); stream.flush()
        proc=subprocess.run(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,check=False)
    actual=locate_run()
    result=audit(actual)
    result['returncode']=proc.returncode
    if proc.returncode != 0:
        result['status']='INCOMPLETE_OR_FAIL'
    (OUT/'input_hashes.json').write_text(json.dumps(inputs,indent=2)+'\n')
    materialize(result)
    if result['status']!='PASS':
        print('LibreLane output did not meet all signoff gates. Read release_out/physical/librelane.log')
    return result


def materialize(result:dict)->None:
    OUT.mkdir(parents=True,exist_ok=True)
    for typ,path in result.get('artifacts',{}).items():
        if path and Path(path).is_file():
            source=Path(path)
            dest=OUT/(typ+source.suffix)
            shutil.copy2(source,dest)
            result.setdefault('artifact_hashes',{})[dest.name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    source=Path(result['metrics_path']) if result.get('metrics_path') else None
    if source and source.is_file():
        shutil.copy2(source,OUT/'metrics.json')
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--jobs',type=int,default=2)
    args=parser.parse_args()
    result=audit(locate_run()) if args.audit_only else run_physical(args.jobs)
    if args.audit_only:materialize(result)
    print(json.dumps({'status':result['status'],'checks':result['checks'],
                      'artifacts':result['artifacts']},indent=2))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
