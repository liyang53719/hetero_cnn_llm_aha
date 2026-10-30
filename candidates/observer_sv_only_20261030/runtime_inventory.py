"""Narrow fresh JDK/Python identity inventory; no Verilator/compiler/provider acquisition."""
import argparse,hashlib,importlib,json,os,pathlib,platform,subprocess,sys,time
D=pathlib.Path(__file__).resolve().parent

def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inventory(repo,home,contract):
 sys.path.insert(0,str(repo/'candidates/ci_frontend_materialization_r2_20261029'))
 import fresh_host as f
 import inventory_runner_jdk as j
 f.validate_contract(contract);f.reject_injection(os.environ)
 need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64' and platform.system()=='Linux','Python3.12 Linux x86_64')
 os_release=platform.freedesktop_os_release();need(os_release.get('ID')=='ubuntu' and os_release.get('VERSION_ID')=='24.04' and os.environ.get('ImageOS')=='ubuntu24','Ubuntu24 fresh host')
 start=time.monotonic();home=home.resolve(strict=True);jdk=j.inventory(home,contract);pins={};aliases={};jdk_aliases=[];total=0
 def add(path,dependency=False):
  nonlocal total
  p=pathlib.Path(path);r=f.resolve_dependency(p) if dependency else p.resolve(strict=True)
  need(r.is_file() and not r.is_symlink(),'regular resolved dependency')
  if p!=r:aliases[str(p)]=str(r)
  if str(r)not in pins:
   total+=r.stat().st_size;need(total<=3*1024**3 and len(pins)<10000 and time.monotonic()-start<240,'bounded runtime inventory')
   pins[str(r)]=sha(r)
  return r
 for row in jdk['files']:
  p=home/row['path']
  if 'symlink'in row:
   need(p.is_symlink() and os.readlink(p)==row['symlink'] and str(p.resolve(strict=True))==row['resolved_target'],'JDK alias drift')
   jdk_aliases.append(dict(path=str(p),link=row['symlink'],target=row['resolved_target']))
   if 'external_dependency'in row:
    x=row['external_dependency'];need(x['resolved_target']=='/etc/ssl/certs/adoptium/cacerts' and sha(x['resolved_target'])==x['sha256'],'public truststore pin');add(x['resolved_target'])
  else:need(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'JDK byte drift');add(p)
 for name in ('argparse','hashlib','json','pathlib','platform','subprocess','tempfile','resource','stat','shutil','urllib.request','ssl','zipfile','gzip','bz2','lzma','ctypes','encodings.utf_8','encodings.ascii'):importlib.import_module(name)
 native=[];python_root=pathlib.Path(sys.base_prefix).resolve()
 for module in list(sys.modules.values()):
  name=getattr(module,'__file__',None)
  if not name:continue
  p=pathlib.Path(name)
  if p.is_file() and p.resolve().is_relative_to(python_root) and 'site-packages'not in p.parts and 'dist-packages'not in p.parts:
   p=add(p)
   if p.suffix=='.so':native.append(p)
 targets=[pathlib.Path(sys.executable),pathlib.Path('/bin/sh'),pathlib.Path('/bin/bash'),pathlib.Path('/usr/bin/readelf'),pathlib.Path('/usr/bin/ldd'),pathlib.Path('/usr/bin/git'),home/'bin/java']+list(home.rglob('*.so'))+native
 context=f.jdk_query_context(home);deps={};classes={}
 def query(argv,extra=None,strict=False):
  env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'};env.update(extra or {})
  r=subprocess.run(list(map(str,argv)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=15)
  need(r.returncode==0 and len(r.stdout)+len(r.stderr)<131072 and (not strict or not r.stderr),'bounded native dependency query');return r.stdout.decode('utf-8','strict')
 for path in targets:
  p=add(path)
  with p.open('rb')as stream:elf=stream.read(4)==b'\x7fELF'
  if not elf:continue
  is_python=p in native;role='PYTHON_EXTENSION' if is_python else 'JDK_LIBRARY' if p.is_relative_to(home) and p.suffix=='.so' else 'JDK_EXECUTABLE' if p==home/'bin/java' else 'SYSTEM_TOOL'
  dynamic=query(['/usr/bin/readelf','-d',p],strict=is_python)
  if 'There is no dynamic section in this file.'in dynamic:deps[str(p)]=[];continue
  output=query(['/usr/bin/ldd',p],context if role=='JDK_LIBRARY' else {},strict=is_python)
  if is_python and output.strip()=='statically linked':
   classes[pins[str(p)]]=f.loaded_python_zero_needed_class(role,True,dynamic,query(['/usr/bin/readelf','-W','-h',p],strict=True),query(['/usr/bin/readelf','-W','-l',p],strict=True),output);deps[str(p)]=[];continue
  paths=f.dependency_paths(output);deps[str(p)]=paths
  for dep in paths:add(dep,True)
 for alias,target in aliases.items():need(str(pathlib.Path(alias).resolve(strict=True))==target,'runtime alias drift')
 for row in jdk_aliases:
  p=pathlib.Path(row['path']);need(p.is_symlink() and os.readlink(p)==row['link'] and str(p.resolve(strict=True))==row['target'],'JDK alias post drift')
 for p,h in pins.items():need(sha(p)==h,'runtime post pin drift')
 need(time.monotonic()-start<270,'inventory retains stage cleanup reserve')
 return dict(schema='SV_ONLY_JDK_PYTHON_IDENTITY_V1',scope='IDENTITY_ONLY_NO_RUNTIME_CPU_OR_NUMERICAL_QUALIFICATION',contract=contract,jdk=jdk,pins=pins,aliases=aliases,jdk_aliases=jdk_aliases,dependencies=deps,python_zero_needed_classes_by_sha256=classes,hashed_bytes=total,old_pass_transfer=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo',type=pathlib.Path,required=True);a.add_argument('--java-home',type=pathlib.Path,required=True);a.add_argument('--contract',type=pathlib.Path,required=True);a.add_argument('--contract-sha256',required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args()
 need(v.contract.is_file() and not v.contract.is_symlink() and v.contract.stat().st_size<4096 and sha(v.contract)==v.contract_sha256,'bounded contract pin')
 r=inventory(v.repo.resolve(),v.java_home,json.loads(v.contract.read_text()));b=(json.dumps(r,sort_keys=True,indent=2)+'\n').encode();need(len(b)<=2<<20,'inventory metadata cap')
 with v.output.open('xb')as stream:stream.write(b)
