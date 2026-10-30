"""Reproduce one frozen v2 case from the recorded clean Git archive."""
from pathlib import Path
from datetime import datetime,timezone
import json,math,os,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    summary=json.loads((ROOT/'reports/reproduction/summary.json').read_text())
    study=json.loads((ROOT/'reports/rtl_study_v2.json').read_text())
    expected=next(r for r in study['evaluation'] if r['scenario_id']=='new52' and r['study_label']=='retuned')
    args=['python3','scripts/run_rtl_experiment.py','--case','new52','--kp-q14',str(expected['kp_q14']),'--ki-q14',str(expected['ki_per_sample_q14'])]
    setup='source /foss/tools/sak/sak-pdk-script.sh sky130A sky130_fd_sc_hd >/dev/null; cd '+shlex.quote(summary['runtime'])+'; exec '+shlex.join(args)
    docker=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker'
    run=subprocess.run([docker,'exec','-u','1000:1000','-e','IIC_OSIC_TOOLS_QUIET=1',summary['container'],'bash','-lc',setup],capture_output=True,text=True)
    log=ROOT/'reports/reproduction/rtl_v2_case.log';log.write_text(run.stdout+run.stderr,encoding='utf-8')
    if run.returncode:raise RuntimeError('Clean RTL case failed; see '+str(log))
    owned=next(line.partition('RTL-in-loop trace saved: ')[2] for line in run.stdout.splitlines() if line.startswith('RTL-in-loop trace saved: '))
    metric=json.loads(subprocess.check_output([docker,'exec',summary['container'],'cat',owned+'/metrics.json'],text=True))
    passed=all(math.isclose(metric[k],expected[k],rel_tol=1e-10,abs_tol=1e-12) for k in ['rmse_hold_c','energy_total_j','sensing_energy_j']) and metric['powered_fault_count']==0
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'source_commit':summary['source_commit'],'case':'new52','run_id':metric['run_id'],'rmse_hold_c':metric['rmse_hold_c'],'energy_total_j':metric['energy_total_j'],'comparison':'RMSE and energy against frozen v2 result; relative1e-10, absolute1e-12','pass':passed,'scope':'One actual RTL-in-loop case in fresh Git extraction; not a rerun of all46 training/evaluation runs'}
    (ROOT/'reports/reproduction/rtl_v2_case.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not passed:raise SystemExit(1)
if __name__=='__main__':main()
