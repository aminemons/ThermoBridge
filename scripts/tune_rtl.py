"""Bounded actual-RTL tuning on a separate 50-to-60 C training schedule."""
from pathlib import Path
import json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
logs=ROOT/'build/rtl-training';logs.mkdir(parents=True,exist_ok=True)
rows=[]
for kp in [492,819,1147]:
    for ki in [1,4]:
        env=dict(os.environ,THERMO_RTL_TRAINING='1',THERMO_RTL_KP_Q14=str(kp),THERMO_RTL_KI_Q14=str(ki))
        with (logs/f'{kp}-{ki}.log').open('w') as out:
            r=subprocess.run([sys.executable,'scripts/run_rtl_experiment.py'],cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT)
        if r.returncode: raise SystemExit('Training run failed; see '+str(logs/f'{kp}-{ki}.log'))
        latest=max((ROOT/'results/raw/experiments').glob('rtl-*/metrics.json'),key=lambda p:p.stat().st_mtime)
        row=json.loads(latest.read_text());assert row['training_only'];rows.append(row)
best=min(rows,key=lambda r:r['rmse_hold_c'])
chosen={'training_only':True,'training_schedule':'50-to-60 C; distinct from held-out 55-to-65 C','kp_q14':best['kp_q14'],'ki_per_sample_q14':best['ki_per_sample_q14'],'candidate_count':len(rows),'training_hold_rmse_c':best['rmse_hold_c'],'selected_run':best['run_id']}
(ROOT/'configs/rtl_tuned.json').write_text(json.dumps(chosen,indent=2)+'\n')
(ROOT/'reports/rtl_training.json').write_text(json.dumps({'selected':chosen,'candidates':rows},indent=2)+'\n')
print(json.dumps(chosen))
