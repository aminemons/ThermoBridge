"""Bounded actual-geometry FVM screen, whole-geometry holdout and refinement."""
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import replace
import csv,itertools,json,platform,sys,time
import scipy
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.physics.fvm import Params,ElectroThermalFVM
from scripts.run_manifest import write_manifest
def features(geometry,duty):
    x=np.array([geometry['heater_width_um']/12,geometry['heater_pitch_um']/40,geometry['anchor_width_um']/12,duty/.5])
    return np.r_[1,x,[x[i]*x[j] for i in range(4) for j in range(i,4)]]
def pareto(rows):
    return [r for r in rows if not any(all(s[k]<=r[k] for k in ['estimated_power_w','estimated_roi_std_c']) and any(s[k]<r[k] for k in ['estimated_power_w','estimated_roi_std_c']) for s in rows if s is not r)]
def main():
    started=datetime.now(timezone.utc);protocol=ROOT/'configs/geometry_study_v1.json';cfg=json.loads(protocol.read_text())
    run='geometry-'+started.strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results/geometry'/run;out.mkdir(parents=True,exist_ok=False)
    keys=['heater_width_um','heater_pitch_um','anchor_width_um']
    geometries=[dict(zip(keys,values),id=f'G{i:02d}') for i,values in enumerate(itertools.product(*(cfg[k] for k in keys)))]
    order=np.random.default_rng(cfg['seed']).permutation(len(geometries));heldout={geometries[i]['id'] for i in order[:cfg['heldout_geometry_count']]}
    split={'protocol':cfg,'geometry_ids':[g['id'] for g in geometries],'heldout_ids':sorted(heldout),'selection_policy':'Use training geometries only; heldout data used solely for surrogate scoring'}
    (out/'split.json').write_text(json.dumps(split,indent=2)+'\n')
    rows=[];failures=[];baseline=Params.from_json(ROOT/'configs/physics.json')
    for g in geometries:
        p=replace(baseline,cell_m=cfg['coarse_cell_um']*1e-6,heater_width_m=g['heater_width_um']*1e-6,heater_pitch_m=g['heater_pitch_um']*1e-6,anchor_width_m=g['anchor_width_um']*1e-6)
        for duty in cfg['duty_conditions']:
            clock=time.perf_counter()
            try:
                model=ElectroThermalFVM(p);r=model.solve_steady(duty)
                row={**g,'duty':duty,'split':'test' if g['id'] in heldout else 'train','mean_c':r['active_mean_c'],'peak_c':r['active_peak_c'],'roi_std_c':r['roi_std_c'],'power_w':float(r['input_power_w']),'power_balance_rel':float(r['power_balance_rel']),'thermal_balance_rel':float(r['thermal_balance_rel']),'solve_s':time.perf_counter()-clock}
                rows.append(row)
                np.savez_compressed(out/f"{g['id']}-d{duty:.2f}.npz",temperature_c=r['temperature_c'],heater_mask=model.heater,domain_mask=model.domain,x_m=model.x,y_m=model.y)
            except (ValueError,RuntimeError) as exc:failures.append({**g,'duty':duty,'error':str(exc)})
        print(g['id'],'solved',len(rows),'failures',len(failures),flush=True)
    with (out/'steady.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    training=[r for r in rows if r['split']=='train'];test=[r for r in rows if r['split']=='test']
    names=['mean_c','roi_std_c','power_w']
    x=np.asarray([features(r,r['duty']) for r in training]);y=np.asarray([[r[k] for k in names] for r in training])
    coef=np.linalg.solve(x.T@x+1e-6*np.eye(x.shape[1]),x.T@y)
    errors=np.abs(np.asarray([features(r,r['duty'])@coef for r in test])-np.asarray([[r[k] for k in names] for r in test]))
    surrogate={name:{'median_abs_error':float(np.median(errors[:,i])),'worst_abs_error':float(np.max(errors[:,i]))} for i,name in enumerate(names)}
    np.savez(out/'surrogate.npz',coefficients=coef)
    candidates=[];target=cfg['selection_target_c']
    for g in geometries:
        if g['id'] in heldout:continue
        group=sorted([r for r in training if r['id']==g['id']],key=lambda r:r['mean_c'])
        if len(group)!=3 or not group[0]['mean_c']<=target<=group[-1]['mean_c']:continue
        candidate=dict(g)
        for dest,source in [('estimated_power_w','power_w'),('estimated_roi_std_c','roi_std_c')]:candidate[dest]=float(np.interp(target,[r['mean_c'] for r in group],[r[source] for r in group]))
        candidates.append(candidate)
    front=sorted(pareto(candidates),key=lambda r:r['estimated_power_w'])
    # At most three observed training-front points, spanning the discrete front.
    indices=sorted(set(np.linspace(0,len(front)-1,min(cfg['candidate_count'],len(front))).astype(int)))
    selected=[front[i] for i in indices];refinement=[]
    (out/'selection.json').write_text(json.dumps({'training_front':front,'selected':selected},indent=2)+'\n')
    for g in selected:
        p=replace(baseline,cell_m=cfg['validation_cell_um']*1e-6,heater_width_m=g['heater_width_um']*1e-6,heater_pitch_m=g['heater_pitch_um']*1e-6,anchor_width_m=g['anchor_width_um']*1e-6)
        model=ElectroThermalFVM(p);lo,hi=0.,1.
        if model.solve_steady(1.)['active_mean_c']<target:
            refinement.append({**g,'status':'target_unreachable'});continue
        for _ in range(11):
            duty=(lo+hi)/2;r=model.solve_steady(duty)
            if r['active_mean_c']<target:lo=duty
            else:hi=duty
        duty=(lo+hi)/2;r=model.solve_steady(duty)
        times=np.arange(0,.1601,.001);sim=model.simulate_transient(np.full(len(times),duty),times)
        hits=np.flatnonzero(sim['active_mean_c']>=target-1)
        warmup=float(times[hits[0]]) if len(hits) else None
        energy=float(np.sum(sim['interval_power_w'])*.001)
        np.savez_compressed(out/f"{g['id']}-refined.npz",times_s=times,temperature_mean_c=sim['active_mean_c'],temperature_peak_c=sim['active_peak_c'],power_w=sim['interval_power_w'],steady_temperature_c=r['temperature_c'],x_m=model.x,y_m=model.y)
        refinement.append({**g,'status':'solved','cell_um':cfg['validation_cell_um'],'duty':duty,'mean_c':r['active_mean_c'],'roi_std_c':r['roi_std_c'],'power_w':float(r['input_power_w']),'warmup_to_target_minus_1c_s':warmup,'energy_first_160ms_j':energy})
        print('REFINED',g['id'],round(r['active_mean_c'],3),flush=True)
    summary={'run_id':run,'geometry_count':len(geometries),'operating_points':len(rows),'training_geometries':len(geometries)-len(heldout),'test_geometries':len(heldout),'failures':failures,'surrogate':surrogate,'refined_candidates':refinement,'max_power_balance_rel':max(r['power_balance_rel'] for r in rows),'max_thermal_balance_rel':max(r['thermal_balance_rel'] for r in rows),'scope':cfg['scope'],'runtime_s':(datetime.now(timezone.utc)-started).total_seconds()}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    write_manifest(out/'manifest.json',run_id=run,command=[sys.executable,'scripts/run_geometry_study.py'],input_paths=[protocol,ROOT/'configs/physics.json',ROOT/'configs/materials.json',ROOT/'src/physics/fvm.py'],seed=cfg['seed'],started=started,status='complete' if not failures else 'completed_with_failures',output_paths=[out/'steady.csv',out/'summary.json',out/'selection.json',out/'split.json'],extra={'geometry_split_unit':'whole geometry','execution_python':sys.version,'execution_platform':platform.platform(),'tool_versions':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},'environment_manifest_sha256':None})
    (ROOT/'reports/geometry_study.json').write_text(json.dumps({'run':out.relative_to(ROOT).as_posix(),**summary},indent=2)+'\n')
    print('Completed',out,flush=True)
    if failures or summary['max_power_balance_rel']>.01 or summary['max_thermal_balance_rel']>.01:raise SystemExit(1)
if __name__=='__main__':main()
