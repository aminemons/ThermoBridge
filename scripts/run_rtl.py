#!/usr/bin/env python3
"""Compile and run the real RTL testbench with Icarus and cocotb."""
from pathlib import Path
import os

from cocotb_tools.runner import get_runner


ROOT = Path(__file__).resolve().parents[1]
runner = get_runner("icarus")
runner.build(
    sources=[ROOT / "rtl" / "thermobridge_top.sv"],
    hdl_toplevel="thermobridge_top",
    build_dir=ROOT / "build" / "rtl-cocotb",
    parameters={"CONTROL_DIV": 32},
    always=True,
)
runner.test(
    hdl_toplevel="thermobridge_top",
    test_module="test_thermobridge",
    test_dir=ROOT / "tb",
    build_dir=ROOT / "build" / "rtl-cocotb",
    extra_env={"PYTHONPATH": str(ROOT) + os.pathsep + str(ROOT / "tb")},
)
