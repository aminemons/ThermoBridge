"""Record the installed container toolchain, PDK and writable project contract."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def probe(argv, timeout=20):
    try:
        run=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
        lines=(run.stdout+'\n'+run.stderr).strip().splitlines()
        return {'path':shutil.which(argv[0]),'command':argv,'exit_code':run.returncode,'version':next((x for x in lines if x and not x.startswith('*')),''),'output':lines[:8]}
    except Exception as exc:
        return {'path':shutil.which(argv[0]),'error':str(exc)}

def main():
    checks={}
    for name,args in {'yosys':['-V'],'iverilog':['-V'],'verilator':['--version'],'openroad':['-version'],'librelane':['--version'],'klayout':['-v'],'ngspice':['-v'],'xschem':['--version'],'magic':['--version'],'netgen':['-batch','help']}.items():
        checks[name]=probe([name,*args])
    build=ROOT/'build';build.mkdir(exist_ok=True)
    marker=build/'.write-test';marker.write_text('actual container user write check');marker.unlink()
    pdk=Path('/foss/pdks/sky130A')
    pdk_sources=(pdk/'SOURCES').read_text().strip()
    output={'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'platform':platform.platform(),'python':platform.python_version(),'cpu_count':os.cpu_count(),'uid':os.getuid(),'gid':os.getgid(),'project_writable':True,'project_path':'/foss/designs/thermobridge','memory_kib':{line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:'))},'disk_free_bytes':shutil.disk_usage(ROOT).free,'tools':checks,'python_packages':{name:importlib.metadata.version(name) for name in ['numpy','scipy','matplotlib','pytest','cocotb','librelane']},'pdk':{'name':'sky130A','standard_cells':'sky130_fd_sc_hd','core_voltage_V':1.8,'sources':pdk_sources,'resolved_directory':str(pdk.resolve()),'source_lock_sha256':hashlib.sha256(pdk_sources.encode()).hexdigest()},'image':os.environ.get('THERMOBRIDGE_IMAGE','hpretl/iic-osic-tools:2026.10'),'image_digest':os.environ.get('THERMOBRIDGE_IMAGE_DIGEST','sha256:9201d2ebe74a406cf6af850ca2c646ac0462f3b2cea94cd98cb6580d8ceef800')}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/environment.json').write_text(json.dumps(output,indent=2)+'\n')
    missing=[name for name,value in checks.items() if not value.get('path')]
    print(json.dumps({'uid':output['uid'],'project_writable':True,'pdk':pdk_sources,'missing_tools':missing},indent=2))
    if missing: raise SystemExit(1)

if __name__=='__main__':main()
