"""Create a bounded PWM averaging validation and a traceable release snapshot."""
from pathlib import Path
import csv,hashlib,json,math,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.physics.rc import ThermalRC

def main():
    cfg=json.loads((ROOT/'configs/evaluation_v1.json').read_text())['baseline']
    model=ThermalRC(r_th_k_per_w=cfg['r_th_k_per_w'],c_th_j_per_k=cfg['c_th_j_per_k'],ambient_c=cfg['ambient_c'],heater_v=cfg['heater_v'],heater_r_ohm=cfg['heater_r_ohm'],r_tcr_per_k=cfg['r_tcr_per_k'])
    period=256/10_000_000
    rows=[]
    for duty in [.25,.5,.75]:
        switched=averaged=model.ambient_c;maximum=0.;ripple=0.
        for i in range(800):
            on=model.step(switched,1,period*duty)
            switched=model.step(on,0,period*(1-duty))
            averaged=model.step(averaged,duty,period)
            maximum=max(maximum,abs(switched-averaged));ripple=max(ripple,abs(on-switched))
        rows.append({'duty':duty,'cycles':800,'duration_s':800*period,'final_switched_c':switched,'final_averaged_c':averaged,'max_endpoint_difference_c':maximum,'max_intra_period_ripple_c':ripple})
    (ROOT/'reports/pwm_validation.json').write_text(json.dumps({'timestamp_utc':datetime.now(timezone.utc).isoformat(),'method':'separate on/off analytic RC phases with TCR updated per phase; compared with averaged duty*V^2/R over each period','pwm_hz':1/period,'cases':rows,'max_allowed_difference_c':.1,'pass':max(r['max_endpoint_difference_c'] for r in rows)<.1},indent=2)+'\n')
    # Correctly retain aborted historical cosim runs as failures.
    for path in (ROOT/'results/raw/experiments').glob('rtl-*/manifest.json'):
        if not (path.parent/'metrics.json').exists() or not (path.parent/'trace.csv').exists():
            value=json.loads(path.read_text());value['status']='failed';value['correction']='The original wrapper did not inspect cocotb XML; required experiment outputs are missing.';path.write_text(json.dumps(value,indent=2)+'\n')
    physical=json.loads((ROOT/'reports/asic/summary.json').read_text())
    phy=json.loads((ROOT/'outputs/physics/validation.json').read_text())
    trials=list((ROOT/'results/raw/experiments').glob('rtl-*/metrics.json'))
    rtl=max((json.loads(p.read_text()) for p in trials if not json.loads(p.read_text()).get('training_only',False)),key=lambda x:x['run_id'])
    experiment='exp-20261027T135345Z-7afca8'
    summary=ROOT/f'results/processed/experiment_summary_{experiment}.csv'
    evidence={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'rtl/thermobridge_top.sv',ROOT/'flow/adc15.sdc',ROOT/'reports/asic/summary.json',ROOT/'outputs/physics/validation.json',ROOT/'reports/pwm_validation.json',summary]}
    snapshot={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'CONDITIONAL_RESEARCH_SNAPSHOT','physics_gates':phy['gates'],'physical_gates':physical['checks'],'physical_qualification':'10 MHz only with external ADC code/valid arrival <=15ns; other I/O20ns; original20ns failure retained','primary_experiment_run':experiment,'scenario_count':20,'seeds_per_scenario':3,'controller_arithmetic_trials':540,'rtl_in_loop':rtl,'engineering_targets':{'nominal_hold_rmse_le_2_c':rtl['rmse_hold_c']<=2},'limitations_file':'docs/LIMITATIONS.md','evidence_sha256':evidence}
    (ROOT/'reports/release_snapshot.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    print(json.dumps({'status':snapshot['status'],'rtl_rmse_c':rtl['rmse_hold_c'],'pwm_average_validation':all(r['max_endpoint_difference_c']<.1 for r in rows),'max_pwm_delta_c':max(r['max_endpoint_difference_c'] for r in rows)}))

if __name__=='__main__':main()
