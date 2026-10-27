"""Requalify unchanged routed geometry under an explicit tighter ADC interface.

The original 20 ns input-budget timing failure is retained. No timing checks
are waived. The external ADC contract changes to 15 ns; layout is unchanged.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='thermobridge_release_1793097512');a=p.parse_args()
    prior=ROOT/'release/flow/runs'/a.run
    if not prior.is_dir():raise SystemExit('Missing original routed run: '+str(prior))
    report=ROOT/'reports/asic';report.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'release/flow/config.json').read_text())
    config['VERILOG_FILES']=str(ROOT/'rtl/thermobridge_top.sv')
    config['PNR_SDC_FILE']=config['SIGNOFF_SDC_FILE']=str(ROOT/'flow/adc15.sdc')
    config_path=report/'adc15-config.json';config_path.write_text(json.dumps(config,indent=2)+'\n')
    run=ROOT/'build/timing-adc15';run.mkdir(parents=True,exist_ok=True)
    state=prior/'71-checker-lvs/state_out.json'
    command=['librelane','--manual-pdk','--pdk-root','/foss/pdks','--pdk','sky130A','--scl','sky130_fd_sc_hd','--jobs','2','--only','OpenROAD.STAPostPNR','--with-initial-state',str(state),'--force-run-dir',str(run),'--run-tag','adc15','--condensed',str(config_path)]
    start=datetime.datetime.now(datetime.timezone.utc)
    with (report/'timing-adc15.log').open('w') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((report/'timing-adc15.log').read_text(errors='replace').splitlines()[-20:]));raise SystemExit(result.returncode)
    metrics=json.loads((run/'final/metrics.json').read_text())
    original=json.loads((prior/'final/metrics.json').read_text())
    zeros=['route__drc_errors','magic__drc_error__count','klayout__drc_error__count','design__lvs_error__count','design__lvs_device_difference__count','design__lvs_net_difference__count','design__lvs_unmatched_device__count','design__lvs_unmatched_net__count','design__lvs_unmatched_pin__count']
    checks={k:original.get(k)==0 for k in zeros}
    checks.update(setup=metrics.get('timing__setup__ws',-1)>=0,hold=metrics.get('timing__hold__ws',-1)>=0,setup_count=metrics.get('timing__setup_vio__count')==0,hold_count=metrics.get('timing__hold_vio__count')==0)
    gds=next((prior/'final/mag_gds').glob('*.gds'))
    summary={'status':'PASS_CONDITIONAL_ADC15' if all(checks.values()) else 'INCOMPLETE_OR_FAIL','timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'duration_s':(datetime.datetime.now(datetime.timezone.utc)-start).total_seconds(),'clock_mhz':10,'adc_max_input_delay_ns':15,'other_input_delay_ns':20,'output_delay_ns':20,'original_adc20_setup_ws_ns':original.get('timing__setup__ws'),'original_run':str(prior),'timing_run':str(run),'checks':checks,'timing':{k:v for k,v in metrics.items() if k.startswith('timing__')},'physical':{k:v for k,v in original.items() if any(s in k for s in ['area','drc_error','lvs_','antenna'])},'gds_sha256':digest(gds),'rtl_sha256':digest(ROOT/'rtl/thermobridge_top.sv'),'sdc_sha256':digest(ROOT/'flow/adc15.sdc'),'command':command,'limits':['10 MHz qualification requires the declared external ADC timing contract; original 20 ns input-budget run failed.','Slew/capacitance warnings, if present, remain reported; not foundry-qualified signoff.','No padframe, ESD, analogue ADC or measured silicon.']}
    (report/'timing-adc15-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    (report/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    archive=ROOT/'results/asic';archive.mkdir(parents=True,exist_ok=True)
    for folder in ['gds','mag_gds','def','lef','nl','pnl','spef']:
        source=prior/'final'/folder
        if source.is_dir():shutil.copytree(source,archive/folder,dirs_exist_ok=True)
    shutil.copy2(ROOT/'flow/adc15.sdc',archive/'constraints.sdc')
    shutil.copytree(run/'final/sdc',archive/'sdc',dirs_exist_ok=True)
    print(json.dumps({'status':summary['status'],'setup_ws':metrics.get('timing__setup__ws'),'hold_ws':metrics.get('timing__hold__ws'),'checks':checks},indent=2))
    if not all(checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
