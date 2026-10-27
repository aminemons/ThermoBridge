"""Check a Git archive in a new Linux directory using the existing installed image."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker'
CONTAINER=os.environ.get('THERMOBRIDGE_CONTAINER','iic-osic-tools')
def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    target='/foss/designs/thermobridge-clean-'+commit[:12]
    archive=subprocess.check_output(['git','archive','--format=tar',commit],cwd=ROOT)
    subprocess.run([DOCKER,'exec','-u','1000:1000',CONTAINER,'mkdir','-p',target],check=True)
    subprocess.run([DOCKER,'exec','-i','-u','1000:1000',CONTAINER,'tar','-xf','-','-C',target],input=archive,check=True)
    output=ROOT/'reports/reproduction';output.mkdir(parents=True,exist_ok=True)
    commands=[['make','test-physics','test-rtl'],['make','simulate'],['python3','scripts/release_check.py']]
    records=[]
    for index,command in enumerate(commands):
        setup='source /foss/tools/sak/sak-pdk-script.sh sky130A sky130_fd_sc_hd >/dev/null; cd '+shlex.quote(target)+'; exec '+shlex.join(command)
        run=subprocess.run([DOCKER,'exec','-u','1000:1000','-e','IIC_OSIC_TOOLS_QUIET=1','-e',f'THERMOBRIDGE_SOURCE_COMMIT={commit}','-e','THERMOBRIDGE_SOURCE_DIRTY=false',CONTAINER,'bash','-lc',setup],capture_output=True,text=True)
        log=output/f'{index+1}.log';log.write_text(run.stdout+run.stderr,encoding='utf-8')
        records.append({'command':command,'exit_code':run.returncode,'log':log.relative_to(ROOT).as_posix(),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        print(' '.join(command),'exit',run.returncode,flush=True)
        if run.returncode:print((run.stdout+run.stderr)[-1500:]);break
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'source_commit':commit,'source':'Git archive, excluding working-tree edits','runtime':target,'container':CONTAINER,'independent_image':False,'physical_rerun':False,'scope':'Fresh source extraction; Python tests, actual RTL tests, frozen Python campaign and actual RTL loop; archived physical evidence audit only. Existing installed toolchain reused.','commands':records,'pass':len(records)==len(commands) and all(r['exit_code']==0 for r in records)}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
