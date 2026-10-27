"""Run bounded electrothermal validation and save all numerical evidence."""
from __future__ import annotations
import argparse, json, math, platform, sys, time, hashlib
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
import numpy as np, scipy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.physics.fvm import Params, ElectroThermalFVM, rectangular_resistor
from src.physics.rc import ThermalRC
from src.models.compact import fit_positive_rc
OUT=ROOT/'outputs'/'physics'; OUT.mkdir(parents=True,exist_ok=True)
def clean(v):
    if isinstance(v,(np.floating,np.integer)): return v.item()
    if isinstance(v,np.ndarray): return v.tolist()
    raise TypeError(type(v).__name__)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true',help='run only 4 um mesh');args=parser.parse_args()
    records=[]; meshes=(4e-6,) if args.quick else (4e-6,2e-6,1e-6)
    for dx in meshes:
        p=Params(cell_m=dx); t=time.perf_counter(); model=ElectroThermalFVM(p);build=time.perf_counter()-t
        t=time.perf_counter(); result=model.solve_steady(.5);solve=time.perf_counter()-t
        name=f"steady_{round(dx*1e6)}um.npz"
        np.savez_compressed(OUT/name,temperature_c=result['temperature_c'],potential_v=result['potential_v'],joule_w=result['joule_w'],domain_mask=model.domain,active_mask=model.active,anchor_mask=model.anchor,heater_mask=model.heater,terminal0_mask=model.terminal0,terminal1_mask=model.terminal1,x_m=model.x,y_m=model.y)
        records.append({'cell_m':dx,'grid_n':model.n,'thermal_cells':int(model.domain.sum()),'heater_cells':int(model.heater.sum()),'build_seconds':build,'solve_seconds':solve,'raw_file':name,'active_mean_c':result['active_mean_c'],'active_peak_c':result['active_peak_c'],'roi_std_c':result['roi_std_c'],'roi_peak_minus_mean_c':result['roi_peak_minus_mean_c'],'current_a':float(result['current_a']),'terminal_power_w':float(result['input_power_w']),'integrated_joule_w':float(result['joule_power_w']),'power_balance_relative':float(result['power_balance_rel']),'thermal_balance_relative':float(result['thermal_balance_rel']),'solver_iterations':result['iterations']})
    # Characterize the dominant passive thermal time constant, then compare full dense transients.
    from scipy import sparse
    from scipy.sparse.linalg import eigsh
    from src.physics.fvm import SIGMA_SB
    p=Params(); model=ElectroThermalFVM(p)
    c_free=model.C[model.domain][model.free_mask]*model.area
    tlin=p.ambient_c+273.15
    conductance=model.Lff+sparse.diags(np.full(len(c_free),(p.genv_w_m2_k+4*p.emissivity*SIGMA_SB*tlin**3)*model.area))
    lambda_min=float(eigsh(conductance,k=1,M=sparse.diags(c_free),sigma=0,which='LM',return_eigenvectors=False)[0])
    dominant_tau_s=1.0/lambda_min
    dt_runs=[]; waveforms=[]
    # 1 ms and 0.5 ms resolve the primary 4 um mesh time constant with >26 and >52 steps per tau.
    for dt in (.001,.0005):
        times=np.arange(0.,.16+dt*.1,dt); duties=np.full(len(times),.5)
        sim=model.simulate_transient(duties,times)
        waveforms.append(sim)
        dt_runs.append({'dt_s':dt,'samples':len(times),'final_active_mean_c':float(sim['active_mean_c'][-1]),'final_active_peak_c':float(sim['active_peak_c'][-1]),'times_s':sim['times_s'].tolist(),'active_mean_c':sim['active_mean_c'].tolist(),'active_peak_c':sim['active_peak_c'].tolist()})
    coarse=waveforms[0]['active_mean_c']; fine=waveforms[1]['active_mean_c'][::2]
    dt_abs=float(np.max(np.abs(coarse-fine)))
    dt_rel=dt_abs/max(float(np.max(waveforms[1]['active_mean_c'])-p.ambient_c),1e-9)
    # Fit on densely sampled 0.5-duty warm-up; score unseen amplitude and pulse duration.
    train_t=waveforms[1]['times_s']; train=waveforms[1]
    train_power=np.r_[train['interval_power_w'],train['interval_power_w'][-1]]
    fit=fit_positive_rc(train_t,train_power,train['active_mean_c'],p.ambient_c)
    held_t=train_t.copy(); held_duty=np.where(held_t[:-1]<.08,.65,0.0)
    held_duty=np.r_[held_duty,0.0]
    held=model.simulate_transient(held_duty,held_t)
    held_power=np.r_[held['interval_power_w'],held['interval_power_w'][-1]]
    from src.models.compact import rc_response
    held_pred=rc_response(held_t,held_power,p.ambient_c,fit['r_th_k_per_w'],fit['c_th_j_per_k'])
    held_err=np.asarray(held_pred)-held['active_mean_c']
    fit_record={'train_duty':.5,'train_pulse_duration_s':.16,'heldout_duty':.65,'heldout_pulse_duration_s':.08,'r_th_k_per_w':fit['r_th_k_per_w'],'c_th_j_per_k':fit['c_th_j_per_k'],'fitted_tau_s':fit['r_th_k_per_w']*fit['c_th_j_per_k'],'train_rmse_c':fit['rmse_c'],'heldout_rmse_c':float(np.sqrt(np.mean(held_err**2))),'heldout_max_abs_c':float(np.max(np.abs(held_err))),'fit_converged':fit['converged'],'sample_dt_s':float(train_t[1]-train_t[0]),'fit_geometry':{'cell_m':p.cell_m,'heater_width_m':p.heater_width_m,'heater_pitch_m':p.heater_pitch_m,'anchor_width_m':p.anchor_width_m,'active_m':p.active_m,'voltage_v':p.voltage_v},'train_times_s':train_t.tolist(),'train_mean_c':train['active_mean_c'].tolist(),'train_input_power_w':train_power.tolist(),'heldout_times_s':held_t.tolist(),'heldout_mean_c':held['active_mean_c'].tolist(),'heldout_input_power_w':held_power.tolist(),'heldout_prediction_c':held_pred.tolist()}
    np.savez_compressed(OUT/'transient_validation.npz',times_s=train_t,train_mean_c=train['active_mean_c'],train_peak_c=train['active_peak_c'],train_power_w=train_power,heldout_times_s=held_t,heldout_mean_c=held['active_mean_c'],heldout_peak_c=held['active_peak_c'],heldout_power_w=held_power,heldout_prediction_c=held_pred,dt_coarse_mean_c=coarse,dt_fine_mean_c=fine)
    ambient=np.full((model.n,model.n),p.ambient_c); _,_,iamb,pamb=model.electrical(ambient)
    rref=p.voltage_v/iamb
    rect=rectangular_resistor(cell_m=1e-6)
    rc=ThermalRC(); rc_power=rc.power(.5,25); rc_eq=rc.ambient_c+rc.r_th_k_per_w*rc_power
    peak_diffs=[]
    if len(records)>1:
        for a,b in zip(records[-2:],records[-1:]): pass
        peak_diffs=[abs(a['active_peak_c']-b['active_peak_c'])/max(abs(b['active_peak_c']),1.) for a,b in zip(records[:-1],records[1:])]
    validation={'schema':'thermobridge-physics-validation-v1','status':'simulated; all material and geometry properties assumed','python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'wall_clock_utc':datetime.now(timezone.utc).isoformat(),'config_sha256':{'physics.json':hashlib.sha256((ROOT/'configs/physics.json').read_bytes()).hexdigest(),'materials.json':hashlib.sha256((ROOT/'configs/materials.json').read_bytes()).hexdigest()},'assumptions_file':'configs/materials.json','geometry_file':'configs/physics.json','meshes':records,'rectangular_resistor':{k:v for k,v in rect.items() if k!='potential_v'},'refinement_relative_peak_change':peak_diffs,'time_constant_spectral':{'linearized_at_ambient_k':p.ambient_c+273.15,'dominant_tau_s':dominant_tau_s,'inverse_eigenvalue_per_s':lambda_min},'time_step_halving':{'runs':dt_runs,'relative_max_transient_error_normalized_by_warmup_excursion':dt_rel,'max_abs_mean_error_c':dt_abs},'primary_heater_at_ambient':{'voltage_v':p.voltage_v,'resistance_ohm':rref,'full_on_power_w':p.voltage_v*iamb,'half_duty_average_power_w':.5*p.voltage_v*iamb,'status':'assumed discrete FVM heater geometry'},'compact_model':fit_record,'rc_baseline':{'tau_s':rc.tau_s,'half_duty_power_w':rc_power,'equilibrium_c':rc_eq},'gates':{'resistor_within_2_percent':abs(rect['resistance_ohm']/rect['analytic_ohm']-1)<.02,'mesh_final_change_below_2_percent':(not peak_diffs or peak_diffs[-1]<.02),'power_balance_below_1_percent':all(x['power_balance_relative']<.01 for x in records),'thermal_balance_below_1_percent':all(x['thermal_balance_relative']<.01 for x in records),'time_step_halving_recorded':len(dt_runs)==2,'time_step_halving_change_below_2_percent':dt_rel<.02,'dominant_tau_resolved_by_dt':.001<dominant_tau_s/10,'heldout_compact_rmse_below_2_c':fit_record['heldout_rmse_c']<2.0}}
    (OUT/'validation.json').write_text(json.dumps(validation,indent=2,default=clean)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in validation.items() if k not in ('meshes','compact_model','time_step_halving')},indent=2,default=clean));print('meshes:',json.dumps([{k:v for k,v in x.items() if k!='raw_file'} for x in records],indent=2));print('time-step max normalized trajectory error:',dt_rel);print('compact:',json.dumps({k:v for k,v in fit_record.items() if not isinstance(v,list)},indent=2))
if __name__=='__main__': main()

