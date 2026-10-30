"""Bounded v2 actual-RTL training, followed by paired evaluation with frozen gains."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    protocol=json.loads((ROOT/'configs/rtl_study_v2.json').read_text())
    run='rtl-study-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results/rtl_study'/run;out.mkdir(parents=True,exist_ok=False)
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    def trial(case,kp,ki,label):
        args=[sys.executable,'scripts/run_rtl_experiment.py','--case',case['id'],'--kp-q14',str(kp),'--ki-q14',str(ki)]
        log=out/f'{label}-{case["id"]}-{kp}-{ki}.log'
        with log.open('w') as stream:r=subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        if r.returncode:raise RuntimeError('RTL failed; inspect '+str(log))
        # Wrapper prints the owned run path only after XML and all outputs pass.
        owned=next(line.partition('RTL-in-loop trace saved: ')[2] for line in log.read_text().splitlines() if line.startswith('RTL-in-loop trace saved: '))
        metric=json.loads((Path(owned)/'metrics.json').read_text())
        metric['study_label']=label
        return metric
    training=[]
    for kp in protocol['candidate_kp_q14']:
        for ki in protocol['candidate_ki_per_sample_q14']:
            scores=[trial(case,kp,ki,'training') for case in protocol['training']]
            row={'kp_q14':kp,'ki_per_sample_q14':ki,'mean_training_rmse_c':sum(x['rmse_hold_c'] for x in scores)/len(scores),'runs':scores}
            training.append(row)
            print('TRAIN',kp,ki,round(row['mean_training_rmse_c'],4),flush=True)
    best=min(training,key=lambda row:row['mean_training_rmse_c'])
    selected={k:best[k] for k in ['kp_q14','ki_per_sample_q14','mean_training_rmse_c']}
    # Selection file exists before any evaluation case is executed.
    (out/'selection.json').write_text(json.dumps(selected,indent=2)+'\n')
    evaluation=[]
    for case in protocol['evaluation']:
        for label,gains in [('baseline',protocol['baseline']),('retuned',selected)]:
            evaluation.append(trial(case,gains['kp_q14'],gains['ki_per_sample_q14'],label))
        print('TEST',case['id'],*[round(x['rmse_hold_c'],4) for x in evaluation[-2:]],flush=True)
    summary={'protocol':protocol['protocol'],'run_id':run,'selected':selected,'training':training,'evaluation':evaluation,'rtl_modified':False,'baseline_result_retained':True}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (ROOT/'reports/rtl_study_v2.json').write_text(json.dumps({'run':out.relative_to(ROOT).as_posix(),'selected':selected,'evaluation':evaluation,'scope':protocol['scope']},indent=2)+'\n')
    print('Completed',out,flush=True)
if __name__=='__main__':main()
