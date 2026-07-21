"""Small Windows/host bridge into the existing IIC-OSIC-TOOLS container.

python scripts/container.py sync [relative paths ...]
python scripts/container.py run python3 -m pytest tests -q
python scripts/container.py fetch reports results docs/figures
Only source paths are synchronized by default. Existing unrelated designs stay intact.
"""
import argparse
import io
import os
from pathlib import Path
import shlex
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = os.environ.get('THERMOBRIDGE_CONTAINER', 'iic-osic-tools')
REMOTE = '/foss/designs/thermobridge'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['sync','run','fetch'])
    p.add_argument('paths', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.action == 'sync':
        paths = a.paths or ['src','rtl','tb','tests','configs','scripts','flow','Makefile','requirements.txt','docs/STATE.md']
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w') as archive:
            for item in paths:
                path = ROOT / item
                if not path.exists():
                    continue
                assert path.resolve().is_relative_to(ROOT.resolve())
                archive.add(path, arcname=item, filter=lambda member: None if any(x in member.name.split('/') for x in ['__pycache__','.pytest_cache','.git','.venv']) else member)
        subprocess.run([DOCKER,'exec','-u','1000:1000',CONTAINER,'mkdir','-p',REMOTE], check=True)
        subprocess.run([DOCKER,'exec','-i','-u','1000:1000',CONTAINER,'tar','-xf','-','-C',REMOTE],input=data.getvalue(),check=True)
        print('Synced',len(data.getvalue()),'bytes to',REMOTE)
    elif a.action == 'run':
        command = a.paths[1:] if a.paths[:1] == ['--'] else a.paths
        if not command:
            p.error('run requires a command')
        setup = 'source /foss/tools/sak/sak-pdk-script.sh sky130A sky130_fd_sc_hd >/dev/null; cd '+REMOTE+'; exec '+shlex.join(command)
        commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
        dirty=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True).stdout.strip())
        result = subprocess.run([DOCKER,'exec','-i','-u','1000:1000','-e','IIC_OSIC_TOOLS_QUIET=1','-e',f'THERMOBRIDGE_SOURCE_COMMIT={commit}','-e',f'THERMOBRIDGE_SOURCE_DIRTY={str(dirty).lower()}','-w',REMOTE,CONTAINER,'bash','-lc',setup])
        raise SystemExit(result.returncode)
    else:
        for item in a.paths:
            destination = ROOT / item
            assert destination.resolve().is_relative_to(ROOT.resolve())
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_dir():
                source = f'{CONTAINER}:{REMOTE}/{item}/.'
            else:
                source = f'{CONTAINER}:{REMOTE}/{item}'
            subprocess.run([DOCKER,'cp',source,str(destination)],check=True)

if __name__ == '__main__':
    main()
