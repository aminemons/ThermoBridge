"""Run the installed SKY130 LibreLane flow and archive real final evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_manifest import write_manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--synth-only',action='store_true')
    p.add_argument('--verify-only',action='store_true')
    a=p.parse_args()
    inputs=[ROOT/'rtl/thermobridge_top.sv',ROOT/'flow/config.json',ROOT/'flow/constraints.sdc']
    source=hashlib.sha256(b''.join(x.read_bytes() for x in inputs)).hexdigest()[:12]
    build=ROOT/'build/asic';build.mkdir(parents=True,exist_ok=True)
    reports=ROOT/'reports/asic';reports.mkdir(parents=True,exist_ok=True)
    destination=ROOT/'results/asic';destination.mkdir(parents=True,exist_ok=True)
    tag='core-'+source+('-synth' if a.synth_only else '')
    run=build/tag
    if a.verify_only:
        summary=json.loads((reports/'summary.json').read_text())
        if summary['source_hash']!=source: raise SystemExit('Physical report is stale for current RTL/config.')
        if not all(summary['gates'].values()): raise SystemExit('Required physical gate did not pass.')
        print(json.dumps(summary['gates'],indent=2));return
    command=['librelane','--manual-pdk','--pdk-root','/foss/pdks','--pdk','sky130A','--scl','sky130_fd_sc_hd','--jobs','2','--run-tag',tag,'--force-run-dir',str(run),'--condensed']
    run.mkdir(parents=True,exist_ok=True)
    if a.synth_only: command+=['--to','Yosys.Synthesis']
    command+=[str(ROOT/'flow/config.json')]
    started=datetime.now(timezone.utc)
    log=build/(tag+'.log')
    if not (run/'final/metrics.json').exists():
        with log.open('w') as out:
            result=subprocess.run(command,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-22:]))
            write_manifest(reports/'manifest.json',run_id=tag,command=command,input_paths=inputs,seed=0,started=started,status='failed',output_paths=[log])
            raise SystemExit(result.returncode)
    if a.synth_only:
        print('Synthesis stage complete; see',run);return
    final=run/'final'
    if not (final/'metrics.json').exists(): raise SystemExit('Missing final metrics: incomplete physical flow.')
    metrics=json.loads((final/'metrics.json').read_text())
    shutil.copy2(final/'metrics.json',reports/'metrics.json')
    formats={}
    for ext,folder in [('gds','gds'),('def','def'),('lef','lef'),('v','nl'),('pnl.v','pnl'),('sdc','sdc'),('spef','spef')]:
        files=list((final/folder).rglob('*')) if (final/folder).exists() else []
        files=[f for f in files if f.is_file()]
        if files:
            # Preserve corner names and every emitted signoff view.
            target=destination/folder;shutil.copytree(final/folder,target,dirs_exist_ok=True)
            formats[folder]=[str(f.relative_to(final)) for f in files]
    for entry in run.iterdir():
        if any(x in entry.name for x in ['netgen-lvs','magic-drc','klayout-drc','sta-postpnr','sta-final','yosys-synthesis']):
            for file in entry.rglob('*'):
                if file.is_file() and file.suffix in ['.log','.rpt','.json','.sdc']:
                    dest=reports/entry.name/file.relative_to(entry);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    drc_keys=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count']
    lvs_keys=['design__lvs_error__count','design__lvs_unmatched_device__count','design__lvs_unmatched_net__count','design__lvs_unmatched_pin__count']
    gates={'final_gds':bool(formats.get('gds')),'route_and_two_drc_decks':all(k in metrics and metrics[k]==0 for k in drc_keys),
           'netgen_lvs':all(k in metrics and metrics[k]==0 for k in lvs_keys),
           'setup_timing':metrics.get('timing__setup__ws',-1)>=0,'hold_timing':metrics.get('timing__hold__ws',-1)>=0}
    summary={'source_hash':source,'run_id':tag,'flow':'LibreLane classic','pdk':'sky130A','standard_cells':'sky130_fd_sc_hd','clock_mhz':10,
             'gates':gates,'metrics':{k:v for k,v in metrics.items() if any(s in k for s in ['drc_error','lvs_','timing__setup__ws','timing__hold__ws','area','unconstrained','antenna'])},
             'formats':formats,'power_status':'Flow vectorless estimates are not reported as workload-based power.'}
    (reports/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    write_manifest(reports/'manifest.json',run_id=tag,command=command,input_paths=inputs,seed=0,started=started,status='passed' if all(gates.values()) else 'failed',output_paths=[reports/'metrics.json',reports/'summary.json'],extra={'pdk':'sky130A','pdk_revision':'1689ac3f2dc763876eaf967227c7dfe831b031ae'})
    print(json.dumps({'run_id':tag,'gates':gates},indent=2))
    if not all(gates.values()): raise SystemExit(1)

if __name__=='__main__':main()
