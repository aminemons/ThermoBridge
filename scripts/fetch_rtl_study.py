"""Fetch only raw runs referenced by the completed study, preserving other data."""
from pathlib import Path
import io,json,os,subprocess,tarfile
ROOT=Path(__file__).resolve().parents[1]
def main():
    report=json.loads((ROOT/'reports/rtl_study_v2.json').read_text())
    summary=json.loads((ROOT/report['run']/'summary.json').read_text())
    runs=[r['run_id'] for candidate in summary['training'] for r in candidate['runs']]+[r['run_id'] for r in summary['evaluation']]
    paths=['results/raw/experiments/'+r for r in runs]
    docker=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker'
    raw=subprocess.check_output([docker,'exec','-u','1000:1000',os.environ.get('THERMOBRIDGE_CONTAINER','iic-osic-tools'),'tar','-cf','-','-C','/foss/designs/thermobridge',*paths])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(ROOT,filter='data')
    print('Fetched',len(runs),'owned RTL runs;',len(raw),'archive bytes')
if __name__=='__main__':main()
