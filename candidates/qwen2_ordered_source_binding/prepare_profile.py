"""Resolve frozen relative pins without downloading or creating a source overlay."""
import argparse,hashlib,json,sys,sysconfig
from pathlib import Path
p=argparse.ArgumentParser()
for name in ('source-root','observer-root','buffer-source','numpy-root','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();here=Path(__file__).resolve(strict=True).parent;m=json.loads((here/'MANIFEST.json').read_text())
def pin(path,expected):
    data=path.read_bytes()
    if len(data)!=expected['bytes'] or hashlib.sha256(data).hexdigest()!=expected['sha256']:raise ValueError('pinned source/tool drift: '+path.name)
    return expected
roots={'python_executable':Path(sys.executable).resolve(strict=True),'python_stdlib':Path(sysconfig.get_path('stdlib')).resolve(strict=True),'numpy_root':a.numpy_root.resolve(strict=True),'system':Path('/')}
runtime={}
for key,expected in m['runtime_files'].items():
    kind,rel=key.split('/',1);path=roots[kind]/rel if rel else roots[kind];runtime[str(path)]=pin(path,expected)
source=a.source_root.resolve(strict=True);observer=a.observer_root.resolve(strict=True);buffer=a.buffer_source.resolve(strict=True)
for rel,expected in m['source_files'].items():pin(source/rel,expected)
extras={str(observer/name):pin(observer/name,expected) for name,expected in m['observer_files'].items()};extras[str(buffer)]=pin(buffer,m['buffer'])
script=here/'check_binding.py';data=script.read_bytes();extras[str(script)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
config=dict(source_root=str(source),numpy_root=str(roots['numpy_root']),observer_root=str(observer),buffer_source=str(buffer),source_files=m['source_files'],runtime_files=runtime,extra_files=extras,manifest_sha256=hashlib.sha256((here/'MANIFEST.json').read_bytes()).hexdigest())
with a.output.open('x') as f:json.dump(config,f,indent=2);f.write('\n')
