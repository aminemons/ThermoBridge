"""Single-command reproducible controller/thermal-model release runner."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'release_out'


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args)->str:
    try:
        p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,timeout=15)
        return p.stdout.strip() if p.returncode==0 else 'unavailable'
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable'


def execute(name:str,command:list[str],stage:dict)->bool:
    log_dir=OUT/'logs';log_dir.mkdir(parents=True,exist_ok=True)
    dest=log_dir/(name+'.log')
    start=time.monotonic()
    with dest.open('w',encoding='utf-8',errors='replace') as f:
        f.write('command: '+' '.join(command)+'\n');f.flush()
        try:
            proc=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
            success=proc.returncode==0
            error=None
        except Exception as exc:
            success=False;error=repr(exc);f.write('ERROR: '+error+'\n')
    stage[name]={'pass':success,'exit_code':proc.returncode if error is None else None,
                 'elapsed_s':round(time.monotonic()-start,3),'log':str(dest.relative_to(ROOT)),
                 'error':error}
    print(f'[{"PASS" if success else "FAIL"}] {name}: {dest}')
    if not success:
        print('\n'.join(dest.read_text(errors='replace').splitlines()[-7:]))
    return success


def python_step(name:str,module:str,stages:dict)->bool:
    return execute(name,[sys.executable,'-m',module],stages)


def run(skip_physical:bool=False)->dict:
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[ROOT/p for p in ['rtl/thermobridge_top.sv','release/flow/config.json',
                               'release/flow/constraints.sdc','release/closed_loop.py',
                               'release/physical.py','configs/physics.json','configs/materials.json']]
    started=datetime.now(timezone.utc)
    manifest={'schema':'thermobridge-release-manifest-v1','started_utc':started.isoformat(),
              'platform':platform.platform(),'python':sys.version.split()[0],
              'source_commit':git('rev-parse','HEAD'),
              'git_dirty':git('status','--porcelain')!='',
              'file_hashes':{str(p.relative_to(ROOT)):sha(p) if p.is_file() else None for p in sources},
              'stages':{},'status':'RUNNING',
              'scope':'experimental digital macro and behavioural external heater/readout; never tapeout ready'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    stage=manifest['stages']
    execute('doctor',[sys.executable,'scripts/doctor.py'],stage)
    execute('physics_tests',[sys.executable,'-m','pytest','-q','tests/test_physics.py'],stage)
    execute('controller_and_release_tests',[sys.executable,'-m','pytest','-q','tests/test_rtl_reference.py','release/tests'],stage)
    execute('rtl_cocotb',[sys.executable,'scripts/run_rtl.py'],stage)
    physics=ROOT/'outputs'/'physics'/'validation.json'
    valid=False
    if physics.is_file():
        try:
            j=json.loads(physics.read_text())
            hashes=j.get('config_sha256',{})
            valid=all(j.get('gates',{}).values()) and all(hashes.get(p.name)==sha(p)
                    for p in (ROOT/'configs'/'physics.json',ROOT/'configs'/'materials.json'))
        except Exception:
            valid=False
    if not valid:
        execute('physics_full',[sys.executable,'scripts/run_physics.py'],stage)
    else:
        stage['physics_full']={'pass':True,'reused':True,'evidence':'outputs/physics/validation.json',
                               'reason':'input hashes and gates checked'}
        print('[PASS] physics_full: reused validated physics with matching input hashes')
    python_step('closed_loop','release.closed_loop',stage)
    if stage['closed_loop']['pass']:
        python_step('figures','release.plots',stage)
    else:
        stage['figures']={'pass':False,'blocked_by':'closed_loop'}
    if skip_physical:
        stage['physical']={'pass':False,'skipped_by_user':True}
    else:
        python_step('physical','release.physical',stage)
    if stage['closed_loop']['pass']:
        python_step('technical_report','release.report',stage)
    else:
        stage['technical_report']={'pass':False,'blocked_by':'closed_loop'}
    mandatory=('doctor','physics_tests','controller_and_release_tests','rtl_cocotb',
               'physics_full','closed_loop','figures','physical','technical_report')
    manifest['status']='PASS' if all(stage[k]['pass'] for k in mandatory) else 'INCOMPLETE_OR_FAIL'
    manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
    manifest['elapsed_s']=(datetime.now(timezone.utc)-started).total_seconds()
    manifest['checks']={k:bool(stage[k]['pass']) for k in mandatory}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    lines=['# ThermoBridge execution result','',f'UTC: {manifest["finished_utc"]}',
           f'Source SHA: `{manifest["source_commit"]}`',
           f'Project dirty at start: `{manifest["git_dirty"]}`','',
           f'**Overall: {manifest["status"]}**','','## Recorded gates','',
           '| Gate | Status | Evidence |','|---|---|---|']
    for name in mandatory:
        status=stage[name]
        lines.append('| '+name+' | '+('PASS' if status['pass'] else 'FAIL / INCOMPLETE')+
                     ' | '+status.get('log',status.get('evidence','not generated'))+' |')
    lines += ['', 'Source and generated data are simulation-only unless a recorded test or layout audit says otherwise.',
              'The physical artifact is a padless SKY130 standard-cell digital core, not a complete ASIC.',
              'The README of the initial repository may be stale; use this receipt for the run result.',
              'No chip photograph or measured gas-sensor specifications are claimed.', '']
    (OUT/'RELEASE_STATUS.md').write_text('\n'.join(lines),encoding='utf-8')
    print('\nOVERALL:',manifest['status'],'\nReport:',OUT/'RELEASE_STATUS.md')
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--skip-physical',action='store_true')
    args=p.parse_args()
    result=run(skip_physical=args.skip_physical)
    if result['status']!='PASS':
        raise SystemExit(1)

if __name__=='__main__':main()
