"""One genuine cocotb RTL -> averaged RC -> divider ADC closed-loop trace."""
from __future__ import annotations

import csv
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.physics.rc import ThermalRC
from src.sensing import HeaterReadout, ReadoutConfig
from tb.rtl_plant_bridge import RTLPlantBridge


@cocotb.test()
async def rtl_ffpi_closed_loop_rc(dut):
    start = datetime.now(timezone.utc)
    run_id = os.environ.get('THERMO_RTL_RUN_ID', "rtl-" + start.strftime("%Y%m%dT%H%M%S%fZ"))
    out = ROOT / "results/raw/experiments" / run_id
    out.mkdir(parents=True, exist_ok=False)
    dut.reset_n.value = 0
    for name in ("adc_valid", "cfg_valid", "cfg_write", "cfg_addr", "cfg_wdata", "adc_code"):
        getattr(dut, name).value = 0
    cocotb.start_soon(Clock(dut.clk, 100, unit="ns").start())
    await Timer(1, unit="us")
    dut.reset_n.value = 1
    await Timer(1, unit="us")

    # Same nominal plant/readout assumptions as the RC reference case. The
    # register calibration is a linear two-point fit to the nonlinear divider.
    evaluation=json.loads((ROOT/"configs/evaluation_v1.json").read_text(encoding="utf-8"))
    base=evaluation["baseline"]; cycle=dict(evaluation["cycle"]); dt=evaluation["time_step_s"]
    training=os.environ.get('THERMO_RTL_TRAINING')=='1'
    if training: cycle['initial_setpoint_c']=50.0
    case=json.loads(os.environ.get('THERMO_RTL_CASE_JSON','{}'))
    for key in ('initial_setpoint_c','step_c'):
        if key in case:cycle[key]=case[key]
    base=dict(base,ambient_c=case.get('ambient_c',base['ambient_c']))
    plant = ThermalRC(r_th_k_per_w=base["r_th_k_per_w"],c_th_j_per_k=base["c_th_j_per_k"],ambient_c=base["ambient_c"],heater_v=base["heater_v"],heater_r_ohm=base["heater_r_ohm"],r_tcr_per_k=base["r_tcr_per_k"])
    # Explicit ideal differential front end centers the divider output before
    # amplification. It is external behavioural circuitry, not an on-chip OTA.
    readout = HeaterReadout(ReadoutConfig(r0_ohm=base["heater_r_ohm"],tcr_per_k=base["r_tcr_per_k"],reference_c=25.0,calibration_r0_ohm=base["heater_r_ohm"],calibration_tcr_per_k=base["r_tcr_per_k"],divider_reference_ohm=base["heater_r_ohm"],excitation_v=0.018,front_end_gain=800.0,front_end_reference_v=0.0086,adc_reference_v=1.8,valid_temperature_c=(20,350),delay_samples=0,noise_rms_v=0), seed=11)
    readout=HeaterReadout(replace(readout.config,noise_rms_v=case.get('noise_rms_v',0)),seed=case.get('seed',11))
    calibration=HeaterReadout(replace(readout.config,noise_rms_v=0),seed=0)
    lo_code = calibration.sample(40.0, 1.0).code
    hi_code = calibration.sample(80.0, 1.0).code
    gain_q14 = round((40.0 * 64.0 / (hi_code - lo_code)) * (1 << 14))
    offset_q6 = round(40.0*64.0 - lo_code * gain_q14 / (1 << 14))
    assert 0 < gain_q14 < (1 << 17) and -(1 << 15) <= offset_q6 < (1 << 15)
    bridge = RTLPlantBridge(dut)
    await bridge.write(bridge.REG_CTRL, 5)  # enable + lookup feedforward
    await bridge.write(bridge.REG_SETPOINT, round(cycle["initial_setpoint_c"] * 64))
    await bridge.write(bridge.REG_CAL_OFFSET, offset_q6)
    await bridge.write(bridge.REG_ADC_GAIN, gain_q14)
    # Gains selected in the separate training-only Python campaign. Ki is
    # scaled by dt because RTL integrates once per accepted control sample.
    tuning_paths=sorted((ROOT/"results/raw/experiments").glob("exp-*/training_tuning.json"))
    if not tuning_paths:
        raise RuntimeError("run the paired Python reference campaign first to select gains on training only")
    selected=json.loads(tuning_paths[-1].read_text(encoding="utf-8"))["selected"]["ffpi"]
    chosen=ROOT/'configs/rtl_tuned.json'
    quantized=json.loads(chosen.read_text()) if chosen.exists() else {}
    kp_q14=int(os.environ.get('THERMO_RTL_KP_Q14',quantized.get('kp_q14',round(selected['kp']*(1<<14)))))
    ki_q14=int(os.environ.get('THERMO_RTL_KI_Q14',quantized.get('ki_per_sample_q14',round(selected['ki']*dt*(1<<14)))))
    kp,ki=kp_q14/(1<<14),ki_q14/(1<<14)/dt
    await bridge.write(bridge.REG_KP, kp_q14)
    await bridge.write(bridge.REG_KI, ki_q14)
    await bridge.write(bridge.REG_LIMIT, 110 * 64)
    await bridge.write(bridge.REG_OUT_MIN, 0)
    await bridge.write(bridge.REG_OUT_MAX, 256)
    lut=json.loads((ROOT/"configs/feedforward_lut.json").read_text(encoding="utf-8"))["bins"]
    for index,entry in enumerate(lut):
        await bridge.write(0x40+4*index,entry["duty_q8"])
    await bridge.commit()

    nw, nh, nc = round(cycle["warmup_tau"]*plant.tau_s/dt), round(cycle["hold_tau"]*plant.tau_s/dt), round(cycle["cool_tau"]*plant.tau_s/dt)
    step_i, cool_i, total = nw+round(nh*cycle["step_at_hold_fraction"]), nw+nh, nw+nh+nc
    temp=plant.ambient_c; applied=1/256; latest_code=readout.sample(temp,applied).code
    trace=[]; energy={"warmup":0.0,"hold":0.0,"cooldown":0.0}; sensing_energy=0.0
    previous_q8=0
    for i in range(total):
        phase="warmup" if i<nw else "hold" if i<cool_i else "cooldown"
        target=cycle["initial_setpoint_c"]+(cycle["step_c"] if i>=step_i else 0)
        if i == step_i:
            await bridge.write(bridge.REG_SETPOINT,round((cycle["initial_setpoint_c"]+cycle["step_c"])*64))
            await bridge.commit(max_cycles=300)
        if i == cool_i:
            await bridge.write(bridge.REG_CTRL, 0)
            await bridge.commit(max_cycles=300)
        if phase == "cooldown":
            dut.adc_valid.value = 0
            await Timer(3200, unit="ns")
            result={"duty_q8":int(dut.duty_q8.value),"fault_cause":int(dut.fault_cause.value)}
            assert int(dut.pwm_out.value) == 0
        else:
            result=await bridge.next_sample(latest_code,max_cycles=300)
        if phase != "cooldown":
            assert result["fault_cause"]==0, f"RTL fault latched in powered loop at interval {i}: {result}"
        else:
            assert result["duty_q8"] == 0 and result["fault_cause"] in (0,4)
        previous_q8=result["duty_q8"]
        command=0.0 if phase=="cooldown" else previous_q8/256.0
        applied=max(command,1/256) if phase!="cooldown" and command==0.0 else command
        power=plant.power(applied,temp)
        energy[phase]+=power*dt
        trace.append({"t_s":i*dt,"temp_c":temp,"setpoint_c":target,"duty_q8":previous_q8,"applied_duty_including_measurement_pulse":applied,"heater_power_w":power,"sample_valid":int(phase!="cooldown"),"phase":phase,"fault_cause":result["fault_cause"]})
        temp=plant.step(temp,applied,dt)
        sample=readout.sample(temp,applied)
        assert sample.valid == (phase != "cooldown")
        sensing_energy += sample.sense_power_w*dt
        if sample.valid: latest_code=sample.code

    trace_path=out/"trace.csv"
    with trace_path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(trace[0])); w.writeheader(); w.writerows(trace)
    hold=trace[nw:cool_i]
    errors=[x["temp_c"]-x["setpoint_c"] for x in hold]
    summary={"run_id":run_id,"simulation_kind":"rtl_in_loop_cocotb_icarus","plant":"primary fitted RC ROM from spatial FVM; duty read from RTL at every sample; nonlinear divider ADC feeds next sample","arithmetic":"synthesizable RTL controller; Q14 KP/KI, Q6 calibration/setpoint, Q8 duty","paired_reference":"Python reference RC run in experiment metrics CSV; this accelerated trace is a separate subset","scenario_id":"E01_nominal","seed":11,"controller":"thermobridge_top feedforward plus PI with frozen spatial-FVM LUT","kp":kp,"ki_per_s":ki,"control_dt_s":dt,"control_div_clock_cycles":32,"rmse_hold_c":math.sqrt(sum(e*e for e in errors)/len(errors)),"energy_warmup_j":energy["warmup"],"energy_hold_j":energy["hold"],"energy_cooldown_j":energy["cooldown"],"energy_total_j":sum(energy.values()),"sensing_energy_j":sensing_energy,"sample_count":len(trace),"fault_count":0}
    summary.pop('fault_count')
    summary.update(training_only=training,scenario_id='train_50_to_60' if training else 'E01_nominal',kp_q14=kp_q14,ki_per_sample_q14=ki_q14,
        powered_fault_count=sum(bool(x['fault_cause']) for x in trace if x['phase']!='cooldown'),
        cooldown_stale_latched=any(x['fault_cause']==4 for x in trace if x['phase']=='cooldown'),
        paired_reference='Separate RTL subset with explicitly centered ideal external readout; not identical to Python front end',
        readout={'gain':800,'reference_v':.0086,'excitation_v':.018,'calibration_c':[40,80],'amplifier_power':'not modeled'})
    if case:
        summary.update(scenario_id=case['id'],seed=case['seed'],case=case,
            protocol='thermobridge-rtl-retuning-v2',previously_observed=case.get('previously_observed',False))
    summary['overshoot_hold_c']=max(0.0,max(errors))
    (out/"metrics.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    dut._log.info("RTL-in-loop experiment complete: %s",json.dumps(summary))
