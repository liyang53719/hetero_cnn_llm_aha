#!/usr/bin/env python3
"""Rebuild the original public iDMA export without an expired Actions artifact.

All downloaded code stays in a new work directory. Upstream/dependency commits
and archive/tool hashes are pinned. Generation uses upstream's unmodified lock
and Makefile; the historical production backend/typedef must match exactly.
Generated files are local build inputs, never Git deliverables.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

import yaml

PIN='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'
ARCHIVES={
 'idma.tar.gz':(f'https://codeload.github.com/pulp-platform/iDMA/tar.gz/{PIN}',
  '4deb3646da91a3d48a48377c9e63496336e8327383b5a810075155ee02080905'),
 'bender.tar.xz':('https://github.com/pulp-platform/bender/releases/download/v0.32.0/bender-x86_64-unknown-linux-gnu.tar.xz',
  '05c2c9c82ddc0b3f45141a1e30dbcfba3b9a98a7d2ad0f9003651c0655c7a2fe'),
 'bc.deb':('https://deb.debian.org/debian/pool/main/b/bc/bc_1.07.1-3+b1_amd64.deb',
  'baaa4e935c5e3bcd57d4f2f4e7a1ddc67bd4eb8629d98f97a696548849ae01ac'),
}
COMMITS={'idma':PIN,'apb':'6ae8bf8d5eab5dc70d032231c01ab95e1c5774b9',
 'axi':'0ccc838fe06aeeb857eb83c6be9a915c4bf99566','axi_stream':'ce1547861f99ab3d8834d04aa36d2d4184a28df7',
 'common_cells':'63b7c50d43e462b59506f69d341ff1e40202866d',
 'common_verification':'fb1885f48ea46164a10568aeff51884389f67ae3',
 'obi':'b69af4aa00630efd14b1c5cbf9bac977f23ce840','tech_cells_generic':'3a3de73632a06826b1bd9c65a0a2e92b32016845'}
PRODUCTION={'idma/target/rtl/idma_backend_rw_axi.sv':'6913ac4c8ff41e96091a22d07c8c13d15b0fb3fc14c18f36cbb9aac065951fdc',
 'idma/src/include/idma/typedef.svh':'732786fd6d1fd76ca257ec36488dbf57b9179377abd3a3296fb9d118b77ad5b3'}

def need(ok,why):
 if not ok:raise ValueError(why)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def extract(archive,destination,*,strip_root=None):
 with tarfile.open(archive) as tf:
  for entry in tf.getmembers():
   parts=Path(entry.name).parts
   if strip_root:
    need(parts and parts[0]==strip_root,'archive root drift')
    if len(parts)==1:continue
    entry.name=str(Path(*parts[1:]))
   tf.extract(entry,destination,filter='data')

def run(output:Path,python:str)->dict:
 output=output.resolve();need(not output.exists(),'output must be new; preserve failed attempts')
 need(sys.platform=='linux' and platform.machine()=='x86_64','portable tools require Linux x86_64')
 for tool in ('curl','git','make','dpkg-deb','uv'):
  need(shutil.which(tool) is not None,'missing public build tool: '+tool)
 output.mkdir(parents=True);downloads=output/'downloads';downloads.mkdir();tools=output/'tools';tools.mkdir()
 def call(args,*,cwd=None,env=None,log=None):
  if log:
   with (output/log).open('w') as f:return subprocess.run([str(x) for x in args],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=1800)
  return subprocess.check_output([str(x) for x in args],cwd=cwd,env=env,text=True,timeout=1800).strip()
 for name,(url,digest) in ARCHIVES.items():
  path=downloads/name
  call(['curl','--fail','--location','--retry','2','--connect-timeout','30',url,'-o',path],log=name+'.download.log')
  need(sha(path)==digest,'download SHA mismatch: '+name)
 src=output/'idma';src.mkdir();extract(downloads/'idma.tar.gz',src,strip_root='iDMA-'+PIN)
 extract(downloads/'bender.tar.xz',tools)
 call(['dpkg-deb','-x',downloads/'bc.deb',tools/'bc'])
 bender=tools/'bender-x86_64-unknown-linux-gnu/bender'
 need(call([bender,'--version'])=='bender 0.32.0','Bender version drift')
 lock_path=src/'Bender.lock';lock_sha=sha(lock_path)
 lock=yaml.safe_load(lock_path.read_text())['packages']
 need({'idma':PIN,**{k:v['revision'] for k,v in lock.items()}}==COMMITS,'upstream dependency lock drift')
 deps={}
 for name,entry in lock.items():
  dep=Path(call([bender,'path',name],cwd=src));deps[name]=dep
  need(call(['git','-C',dep,'rev-parse','HEAD'])==entry['revision'],'dependency revision drift: '+name)
  need(not call(['git','-C',dep,'status','--porcelain']),'modified dependency: '+name)
 env=os.environ.copy();env.update(UV_CACHE_DIR=str(output/'uv-cache'),UV_PROJECT_ENVIRONMENT=str(src/'.venv'),
  UV_PYTHON_DOWNLOADS='never',UV_SYSTEM_CERTS='true',UV_PYTHON=str(Path(python).resolve()),
  PATH=str(tools/'bc/usr/bin')+os.pathsep+env.get('PATH',''))
 call(['make','-j1','BENDER='+str(bender),'target/rtl/idma_generated.sv','target/rtl/include/idma/compute.svh'],cwd=src,env=env,log='generate.log')
 filelist=call([bender,'script','verilator','-t','rtl','-t','asic'],cwd=src)+'\n'
 need(sha(lock_path)==lock_sha,'upstream lock changed during generation')
 out=output/'idma_export';(out/'idma').mkdir(parents=True);(out/'deps').mkdir()
 extract(downloads/'idma.tar.gz',out/'idma',strip_root='iDMA-'+PIN)
 shutil.copytree(src/'target/rtl',out/'idma/target/rtl',dirs_exist_ok=True)
 replacements={str(src):'@ROOT@/idma'}
 for name,dep in deps.items():
  target=out/'deps'/name;target.mkdir()
  with subprocess.Popen(['git','-C',str(dep),'archive','HEAD'],stdout=subprocess.PIPE) as p:
   subprocess.run(['tar','-x','-C',str(target)],stdin=p.stdout,check=True);p.stdout.close();need(p.wait()==0,'dependency archive failed')
  replacements[str(dep)]='@ROOT@/deps/'+name
 for old,new in sorted(replacements.items(),key=lambda x:-len(x[0])):filelist=filelist.replace(old,new)
 need(str(output) not in filelist,'unrelocated filelist path')
 (out/'idma.f.in').write_text(filelist);(out/'COMMITS.json').write_text(json.dumps(COMMITS,indent=2)+'\n')
 manifest={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
 for name,digest in PRODUCTION.items():need(manifest.get(name)==digest,'production source changed: '+name)
 (out/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
 from prepare_idma_export import verify
 checked=verify(out,output/'verified')
 result={'schema_version':1,'status':'PASS_PINNED_PUBLIC_IDMA_REBUILT','export':str(out),
  'source_sha256':sha(__file__),'archive_sha256':{k:v[1] for k,v in ARCHIVES.items()},
  'upstream_lock_sha256':lock_sha,'production_sha256':PRODUCTION,'verification':checked,
  'tools':{'bender':call([bender,'--version']),'python':call([src/'.venv/bin/python','--version']),
           'uv':call(['uv','--version']),'bc':call([tools/'bc/usr/bin/bc','--version']).splitlines()[0]},
  'scope':'Rebuilt public source dependency only; not arithmetic, transport or model signoff'}
 (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--python',default=sys.executable,help='Existing Python>=3.11; no interpreter download')
 a=p.parse_args()
 try:print(json.dumps(run(a.output,a.python),indent=2))
 except (ValueError,OSError,subprocess.SubprocessError) as e:raise SystemExit('PINNED_IDMA_REBUILD_FAILED: '+str(e))
