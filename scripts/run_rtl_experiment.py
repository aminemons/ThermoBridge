"""Run a dedicated cocotb loop; accept only this invocation's verified output."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,json,os,sys,xml.etree.ElementTree as ET
from cocotb_tools.runner import get_runner
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_manifest import write_manifest
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case');parser.add_argument('--kp-q14',type=int);parser.add_argument('--ki-q14',type=int)
    parser.add_argument('--protocol', type=Path, default=ROOT/'configs/rtl_study_v2.json')
    parser.add_argument('--calibration-c', type=float, nargs=2, metavar=('LOW', 'HIGH'))
    parser.add_argument('--heater-v', type=float)
    args=parser.parse_args();started=datetime.now(timezone.utc)
    run_prefix = 'rtl-'
    extra={'PYTHONPATH':str(ROOT)+os.pathsep+str(ROOT/'tb')}
    inputs=[ROOT/p for p in ['rtl/thermobridge_top.sv','tb/test_experiment_bridge.py','tb/rtl_plant_bridge.py','src/physics/rc.py','src/sensing/readout.py','src/sensing/calibration.py','configs/evaluation_v1.json','configs/feedforward_lut.json','configs/rtl_tuned.json']]
    if args.case:
        path=args.protocol.resolve();protocol=json.loads(path.read_text());inputs.append(path)
        cases=protocol['training']+protocol['evaluation']
        case=next((c for c in cases if c['id']==args.case),None)
        if case is None:parser.error('unknown frozen study case')
        extra.update(THERMO_RTL_CASE_JSON=json.dumps(case),THERMO_RTL_TRAINING=str(int(case in protocol['training'])))
        extra['THERMO_RTL_PROTOCOL'] = protocol['protocol']
        suffix = protocol['protocol'].rsplit('-', 1)[-1]
        run_prefix = {'v3':'rtl3-', 'v4':'rtl4-'}.get(suffix, 'rtl2-')
    if args.calibration_c is not None:
        low, high = args.calibration_c
        if not 20 <= low < high <= 350:
            parser.error('Calibration bounds must increase within 20 to 350 C')
        extra['THERMO_RTL_CALIBRATION_C'] = json.dumps(args.calibration_c)
    if args.heater_v is not None:
        if not 0 < args.heater_v <= 1.8:
            parser.error('External heater voltage must be positive and at most 1.8 V')
        extra['THERMO_RTL_HEATER_V'] = str(args.heater_v)
    run_id = run_prefix + started.strftime('%Y%m%dT%H%M%S%fZ')
    extra['THERMO_RTL_RUN_ID'] = run_id
    for name,value in [('THERMO_RTL_KP_Q14',args.kp_q14),('THERMO_RTL_KI_Q14',args.ki_q14)]:
        if value is not None:extra[name]=str(value)
    runner=get_runner('icarus');build=ROOT/'build/rtl-experiment'/run_id
    runner.build(sources=[ROOT/'rtl/thermobridge_top.sv'],hdl_toplevel='thermobridge_top',build_dir=build,parameters={'CONTROL_DIV':32},always=True)
    result_xml = runner.test(hdl_toplevel='thermobridge_top',test_module='tb.test_experiment_bridge',test_dir=build,build_dir=build,extra_env=extra)
    xml=ET.parse(result_xml).getroot()
    if not xml.findall('.//testcase') or xml.findall('.//failure') or xml.findall('.//error'):
        raise SystemExit('RTL-in-loop failed; no successful manifest was written.')
    out=ROOT/'results/raw/experiments'/run_id
    if not all((out/name).is_file() for name in ['trace.csv','metrics.json']):
        raise SystemExit('This invocation did not produce required experiment outputs.')
    log=out/'run.log';log.write_text('Icarus/cocotb passed. RTL duty drives the RC plant; nonlinear ADC supplies feedback. CONTROL_DIV=32 accelerates the declared 1 ms plant interval.\n')
    write_manifest(out/'manifest.json',run_id=run_id,command=[sys.executable,'scripts/run_rtl_experiment.py',*sys.argv[1:]],input_paths=inputs,seed=json.loads((out/'metrics.json').read_text())['seed'],started=started,status='complete',output_paths=[out/'trace.csv',out/'metrics.json',log],extra={'simulation_kind':'Actual RTL-in-loop; accelerated control divider32'})
    print('RTL-in-loop trace saved: '+str(out))
if __name__=='__main__':main()
