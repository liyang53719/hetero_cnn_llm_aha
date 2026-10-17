"""Rebuild the pinned 92-source tree, no compiler or download."""
import argparse,hashlib,json,shutil,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_source import compose
HERE=Path(__file__).resolve().parent

def rebuild(production,qk16,hardfloat_scala,output):
    if output.exists() or output.is_symlink():raise ValueError('fresh output required')
    pins=json.loads((HERE/'PLANNED_SOURCE_PINS.json').read_text())
    prefix='hardfloat_snapshot/hardfloat/src/main/scala/'
    with tempfile.TemporaryDirectory() as tmp:
        overlay=Path(tmp)/'overlay';compose(production,qk16,overlay)
        selected={}
        for rel,h in pins.items():
            src=overlay/rel if (overlay/rel).is_file() else (hardfloat_scala/rel[len(prefix):] if rel.startswith(prefix) else production/rel)
            if src.is_symlink() or hashlib.sha256(src.read_bytes()).hexdigest()!=h:raise ValueError('source mismatch: '+rel)
            selected[rel]=src
        if len(selected)!=92:raise ValueError('exactly92 sources')
        output.mkdir(parents=True,exist_ok=False)
        for rel,src in selected.items():
            target=output/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
        if {str(f.relative_to(output)):hashlib.sha256(f.read_bytes()).hexdigest() for f in output.rglob('*.scala')}!=pins:raise ValueError('rebuild output drift')
    return dict(source_count=92,compiler_started=False)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('production-source','qk16-source','hardfloat-scala','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();print(json.dumps(rebuild(a.production_source,a.qk16_source,a.hardfloat_scala,a.output)))
