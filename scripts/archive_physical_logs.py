"""Preserve original flow logs/check reports without duplicating bulky intermediates."""
from pathlib import Path
import gzip, hashlib, json, shutil
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'release/flow/runs/thermobridge_release_1793097512'
OUT=ROOT/'reports/asic/original'
def main():
    if not SOURCE.is_dir():
        assert OUT.is_dir(),'Original runtime flow directory or existing local archive required'
        compress();return
    selected=[]
    for path in SOURCE.rglob('*'):
        if not path.is_file():continue
        if path.suffix in {'.log','.rpt','.txt','.xml','.drc','.lvs'} or path.name in {'or_metrics_out.json','yosys.stat.json','metrics.json'}:
            if 'tmp' in path.relative_to(SOURCE).parts:continue
            relative=path.relative_to(SOURCE);destination=OUT/relative
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
            selected.append({'path':relative.as_posix(),'bytes':path.stat().st_size})
    for name in ['audit.json','input_hashes.json','metrics.json']:
        old=ROOT/'release_out/physical'/name
        if old.exists():shutil.copy2(old,OUT/name)
    (OUT/'archive.json').write_text(json.dumps({'source':str(SOURCE),'files':selected,'note':'Original20ns ADC timing failure retained. Conditional15ns recheck is separate.'},indent=2)+'\n')
    print('Archived',len(selected),'log/report files; bytes',sum(x['bytes'] for x in selected))
    compress()
def compress():
    inventory=[];ignored=[]
    for path in OUT.rglob('*'):
        if not path.is_file() or path.suffix=='.gz' or path.name in {'.gitignore','compressed_inventory.json'}:continue
        if path.stat().st_size>1_000_000:
            compressed=path.with_name(path.name+'.gz')
            with path.open('rb') as src,gzip.open(compressed,'wb',compresslevel=6) as dst:shutil.copyfileobj(src,dst)
            relative=path.relative_to(OUT).as_posix();ignored.append('/'+relative)
            inventory.append({'original':relative,'uncompressed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'gzip':compressed.relative_to(OUT).as_posix(),'uncompressed_bytes':path.stat().st_size,'gzip_bytes':compressed.stat().st_size})
    (OUT/'.gitignore').write_text('\n'.join(ignored)+'\n')
    (OUT/'compressed_inventory.json').write_text(json.dumps({'note':'Large reports are published losslessly compressed. Original files also retained locally.','files':inventory},indent=2)+'\n')
    print('Losslessly compressed',len(inventory),'large reports; archive bytes',sum(x['gzip_bytes'] for x in inventory))
if __name__=='__main__':main()
