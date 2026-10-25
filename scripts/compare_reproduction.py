"""Compare newly executed data in a clean snapshot with its archived baselines."""
from pathlib import Path
import csv,json,math,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    summary=json.loads((ROOT/'reports/reproduction/summary.json').read_text())
    code='''from pathlib import Path
import csv,json,math
root=Path(__import__('sys').argv[1]);base=root/'results/raw/experiments'
original=base/'exp-20261027T135345Z-7afca8'
fresh=max(base.glob('exp-*'),key=lambda p:p.name)
a=list(csv.DictReader((original/'metrics.csv').open()));b=list(csv.DictReader((fresh/'metrics.csv').open()))
assert fresh!=original and len(a)==len(b)==540
differences=[]
for i,(x,y) in enumerate(zip(a,b)):
    assert x.keys()==y.keys()
    for key in x:
        if x[key]==y[key]:continue
        try:equal=math.isclose(float(x[key]),float(y[key]),rel_tol=1e-10,abs_tol=1e-12)
        except ValueError:equal=False
        if not equal:differences.append([i,key,x[key],y[key]])
trials=[json.loads(p.read_text()) for p in base.glob('rtl-*/metrics.json')]
new=max((v for v in trials if not v.get('training_only')),key=lambda v:v['run_id'])
old=json.loads((base/'rtl-20261027T140947426703Z/metrics.json').read_text())
rtl_equal=all(math.isclose(new[k],old[k],rel_tol=1e-10,abs_tol=1e-12) for k in ['rmse_hold_c','energy_total_j','sensing_energy_j'])
print(json.dumps({'fresh_python_run':fresh.name,'paired_metric_rows':len(b),'different_metric_fields':differences,'fresh_rtl_run':new['run_id'],'rtl_rmse_c':new['rmse_hold_c'],'rtl_energy_j':new['energy_total_j'],'rtl_metrics_reproduced':rtl_equal,'pass':not differences and rtl_equal}))
'''
    docker=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker'
    raw=subprocess.check_output([docker,'exec','-u','1000:1000',summary['container'],'python3','-c',code,summary['runtime']],text=True)
    result=json.loads(raw);result['source_commit']=summary['source_commit']
    (ROOT/'reports/reproduction/numerical_comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['pass']:raise SystemExit(1)
if __name__=='__main__':main()
