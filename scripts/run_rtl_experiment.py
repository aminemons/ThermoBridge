"""Run the dedicated cocotb closed-loop experiment, independently of unit tests."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

from cocotb_tools.runner import get_runner
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_manifest import write_manifest
started=datetime.now(timezone.utc)
runner=get_runner("icarus")
build=ROOT/"build/rtl-experiment"
runner.build(sources=[ROOT/"rtl/thermobridge_top.sv"],hdl_toplevel="thermobridge_top",build_dir=build,parameters={"CONTROL_DIV":32},always=True)
runner.test(hdl_toplevel="thermobridge_top",test_module="test_experiment_bridge",test_dir=ROOT/"tb",build_dir=build,extra_env={"PYTHONPATH":str(ROOT)+":"+str(ROOT/"tb")})
test_results=ET.parse(ROOT/'tb/results.xml').getroot()
cases=test_results.findall('.//testcase')
if not cases or test_results.findall('.//failure') or test_results.findall('.//error'):
    raise SystemExit('RTL-in-loop cocotb test failed; no successful experiment manifest was written.')
run_dirs=sorted((ROOT/"results/raw/experiments").glob("rtl-*"))
if not run_dirs:
    raise RuntimeError("cocotb test did not emit a run directory")
out=run_dirs[-1]
log=out/"run.log"
log.write_text("Cocotb/Icarus completed successfully. The plant duty was consumed from the RTL duty_q8 output at each sampled update; ADC codes came from the nonlinear divider model. CONTROL_DIV=32 is a simulation acceleration.\n",encoding="utf-8")
write_manifest(out/"manifest.json",run_id=out.name,command=[sys.executable,"scripts/run_rtl_experiment.py"],input_paths=[ROOT/"rtl/thermobridge_top.sv",ROOT/"tb/test_experiment_bridge.py",ROOT/"tb/rtl_plant_bridge.py",ROOT/"src/physics/rc.py",ROOT/"src/sensing/readout.py"],seed=11,started=started,status="complete",output_paths=[out/"trace.csv",out/"metrics.json",log],extra={"simulation_kind":"RTL-in-the-loop using Icarus/cocotb; not Python duty replay","accelerated_control_div":32})
print(f"RTL-in-loop trace saved: {out}")
