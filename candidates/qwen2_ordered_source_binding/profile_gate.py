"""Exact manifest/profile path and content gate, not a general-purpose sandbox."""
import hashlib,json,sys,sysconfig
from pathlib import Path

def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def validate(config,here):
    here=Path(here).resolve(strict=True);m=json.loads((here/'MANIFEST.json').read_text())
    keys={'source_root','numpy_root','observer_root','buffer_source','source_files','runtime_files','extra_files','manifest_sha256'}
    need(set(config)==keys,'exact config keys required')
    need(config['manifest_sha256']==sha(here/'MANIFEST.json') and config['source_files']==m['source_files'],'profile manifest mismatch')
    roots={'python_executable':Path(sys.executable).resolve(strict=True),'python_stdlib':Path(sysconfig.get_path('stdlib')).resolve(strict=True),'numpy_root':Path(config['numpy_root']).resolve(strict=True),'system':Path('/')}
    expected={}
    for key,pin in m['runtime_files'].items():
        kind,rel=key.split('/',1);path=roots[kind]/rel if rel else roots[kind];expected[str(path)]=pin
    need(config['runtime_files']==expected,'exact runtime paths and pins required')
    owner=Path(config['observer_root']).resolve(strict=True);buffer=Path(config['buffer_source']).resolve(strict=True)
    extras={str(owner/name):pin for name,pin in m['observer_files'].items()};extras[str(buffer)]=m['buffer']
    script=here/'check_binding.py';extras[str(script)]={'bytes':script.stat().st_size,'sha256':sha(script)}
    need(config['extra_files']==extras,'exact observer/buffer/worker extras required')
    need(Path(config['source_root']).resolve(strict=True)==Path(config['source_root']),'canonical source root required')
    return m
