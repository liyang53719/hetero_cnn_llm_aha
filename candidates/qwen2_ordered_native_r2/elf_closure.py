"""Static ELF closure: readelf only. Never dlopen/ldd/import NumPy/run roots.

Pinned x86_64 Linux resolver: empty LD_LIBRARY_PATH, explicit system link
search dirs, ORIGIN RPATH/RUNPATH, inherited RPATH and PT_INTERP. Unknown
locations/tokens fail closed rather than scanning all system libraries.
"""
from pathlib import Path
import hashlib,json,os,re,subprocess
SYSTEM_DIRS=('/lib/x86_64-linux-gnu','/usr/lib/x86_64-linux-gnu','/lib64','/usr/lib64','/lib','/usr/lib')
READELF='/usr/bin/readelf'
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()
def inspect(path):
 path=Path(path).resolve(strict=True)
 raw=path.open('rb').read(20)
 if raw[:6]!=b'\x7fELF\x02\x01' or raw[18:20]!=b'\x3e\x00':raise ValueError('expected ELF64 little-endian x86_64: '+str(path))
 def output(flag):
  r=subprocess.run([READELF,flag,str(path)],capture_output=True,text=True,timeout=10,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
  if r.returncode:raise ValueError('readelf failed: '+r.stderr)
  return r.stdout
 dynamic=output('-d');program=output('-l')
 tags={tag:re.findall(r'\('+tag+r'\).*?\[([^\]]+)\]',dynamic) for tag in ('NEEDED','SONAME','RPATH','RUNPATH')}
 interp=re.findall(r'Requesting program interpreter: ([^\]]+)\]',program)
 return {'needed':tags['NEEDED'],'soname':tags['SONAME'][0] if tags['SONAME'] else None,'rpath':':'.join(tags['RPATH']).split(':') if tags['RPATH'] else [],'runpath':':'.join(tags['RUNPATH']).split(':') if tags['RUNPATH'] else [],'interpreter':interp[0] if interp else None}
def expand(paths,origin):
 result=[]
 for p in paths:
  p=p.replace('${ORIGIN}',str(origin)).replace('$ORIGIN',str(origin))
  if '$' in p or not p.startswith('/'):raise ValueError('unresolved or relative ELF search path: '+p)
  result.append(p)
 return result
def generate(roots,reader=inspect,system_dirs=SYSTEM_DIRS):
 if os.environ.get('LD_LIBRARY_PATH') or os.environ.get('LD_PRELOAD'):raise ValueError('loader environment override forbidden')
 roots=[str(Path(p).resolve(strict=True)) for p in roots]
 queue=[(p,()) for p in roots];seen=set();files={};edges=[]
 while queue:
  path,inherited=queue.pop(0);key=(path,inherited)
  if key in seen:continue
  seen.add(key);p=Path(path);meta=reader(p)
  files[path]={'bytes':p.stat().st_size,'sha256':digest(p),**meta}
  own=expand(meta['rpath'],p.parent) if not meta['runpath'] else []
  run=expand(meta['runpath'],p.parent)
  search=own+list(inherited)+run+list(system_dirs)
  next_inherited=tuple(own+list(inherited))
  for needed in meta['needed']:
   if '/' in needed:raise ValueError('non-SONAME NEEDED unsupported: '+needed)
   link=next((Path(d)/needed for d in search if (Path(d)/needed).is_file()),None)
   if link is None:raise ValueError('unresolved NEEDED '+needed+' from '+path)
   target=str(link.resolve(strict=True));target_meta=reader(Path(target))
   if target_meta['soname'] not in (needed,None):raise ValueError('SONAME mismatch '+needed)
   edge={'from':path,'needed':needed,'link':str(link),'target':target,'kind':'needed'}
   if edge not in edges:edges.append(edge)
   queue.append((target,next_inherited))
  if meta['interpreter']:
   link=Path(meta['interpreter']);target=str(link.resolve(strict=True));edge={'from':path,'needed':meta['interpreter'],'link':str(link),'target':target,'kind':'interpreter'}
   if edge not in edges:edges.append(edge)
   queue.append((target,()))
 return {'schema':1,'status':'STATIC_NEEDED_CLOSURE_ONLY_NOT_LOADED','roots':roots,'files':files,'edges':edges,'system_dirs':list(system_dirs),'readelf':{'path':str(Path(READELF).resolve()),'sha256':digest(READELF)},'loader_environment':{'LD_LIBRARY_PATH':'','LD_PRELOAD':''},'compiled':False,'native_loaded':False}
def check(manifest,reader=inspect):
 """Re-derive, then compare full files+edges. Missing libz/pcre cannot pass."""
 current=generate(manifest['roots'],reader,tuple(manifest['system_dirs']))
 for key in ('roots','files','edges','readelf','loader_environment'):
  if current[key]!=manifest[key]:raise ValueError('ELF closure drift: '+key)
 return True
if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--roots-json',required=True,type=Path);a.add_argument('--output',required=True,type=Path);args=a.parse_args()
 if args.output.exists():raise ValueError('fresh closure output required')
 roots=json.loads(args.roots_json.read_text())['roots'];r=generate(roots);args.output.write_text(json.dumps(r,indent=2)+'\n');print(len(r['roots']),len(r['files']),len(r['edges']))
