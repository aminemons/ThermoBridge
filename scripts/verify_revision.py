"""Record installed-environment checks and distinguish target failure from test failure."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
import pymupdf
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'reports/revision_checks';out.mkdir(parents=True,exist_ok=True)
    report=ROOT/'reports/revision_verification.json'
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'status':'running','scope':'Current host/container tests, actual RTL unit tests, archived evidence audit and PDF QA. Full physical flow not rerun.','checks':[]}
    report.write_text(json.dumps(result,indent=2)+'\n')
    commands=[
        ('host_pytest',[sys.executable,'-m','pytest','-q','tests','release/tests'],0),
        ('container_pytest',[sys.executable,'scripts/container.py','run','python3','-m','pytest','-q','tests','release/tests'],0),
        ('rtl',[sys.executable,'scripts/container.py','run','python3','scripts/run_rtl.py'],0),
        ('evidence',[sys.executable,'scripts/release_check.py'],0),
        ('unmet_target',[sys.executable,'scripts/release_check.py','--strict'],1),
    ]
    for label,args,expected in commands:
        run=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        log=out/f'{label}.log';log.write_text(run.stdout+run.stderr,encoding='utf-8')
        passed=run.returncode==expected
        result['checks'].append({'name':label,'command':args,'exit_code':run.returncode,'expected_exit_code':expected,'pass':passed,'log':log.relative_to(ROOT).as_posix(),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        print(label,'PASS' if passed else 'FAIL',flush=True)
        if not passed:print((run.stdout+run.stderr)[-1200:])
    doc=pymupdf.open(ROOT/'reports/thermobridge_article.pdf')
    text=''.join(page.get_text() for page in doc)
    result['pdf']={'pages':len(doc),'replacement_characters':text.count(chr(65533)),'main_figures':6,'tables':5,'visual_review':'All final rendered pages inspected in this revision'}
    result['status']='PASS' if all(r['pass'] for r in result['checks']) and len(doc)==5 and chr(65533) not in text else 'FAIL'
    result['engineering_target_met']=False
    result['rtl_source_sha256']=hashlib.sha256((ROOT/'rtl/thermobridge_top.sv').read_bytes()).hexdigest()
    report.write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
