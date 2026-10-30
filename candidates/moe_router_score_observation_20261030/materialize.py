"""Reconstruct isolated exact-hash sources only; never edit the base repository."""
from pathlib import Path
import argparse,hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parent

def require(condition,message):
 if not condition:raise ValueError(message)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def apply_exact(text,patch):
 old=text.splitlines(keepends=True);out=[];pos=0;lines=patch.splitlines(keepends=True);i=0
 while i<len(lines):
  if not lines[i].startswith('@@ '):i+=1;continue
  m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i]);require(m is not None,'invalid hunk')
  start=int(m[1])-1;require(start>=pos,'overlapping patch hunk');out+=old[pos:start];pos=start;i+=1
  while i<len(lines) and not lines[i].startswith('@@ '):
   l=lines[i]
   if l.startswith((' ','-')):
    require(pos<len(old) and old[pos]==l[1:],'patch base context mismatch')
    if l[0]==' ':out.append(old[pos])
    pos+=1
   elif l.startswith('+'):out.append(l[1:])
   else:raise ValueError('unsupported patch line')
   i+=1
 out+=old[pos:];return ''.join(out)

def main():
 a=argparse.ArgumentParser();a.add_argument('--repo',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();require(not v.output.exists() and not v.output.is_symlink(),'fresh output required')
 pin=json.loads((ROOT/'BASE_AND_RESULT_PINS.json').read_text());prepared={}
 for r in pin['files']:
  b=v.repo/r['base_repo_path'];require(b.is_file() and not b.is_symlink() and sha(b)==r['base_sha256'],'missing or drifted published base '+r['base_repo_path'])
  data=apply_exact(b.read_text(),(ROOT/r['patch']).read_text()).encode() if 'patch'in r else (ROOT/r['name']).read_bytes()
  require(hashlib.sha256(data).hexdigest()==r['result_sha256'],'result pin '+r['name']);prepared[r['name']]=data
 p0=v.repo/'candidates/p0_resident_observation_20261030/driver/resident_observation.hpp';require(p0.is_file() and not p0.is_symlink() and sha(p0)=='88185df7e27f3c0ffa7f3fd857e40f4a31fd72a69c876602519be2e3b0a69721','missing or drifted P0 header')
 shutil.copytree(ROOT,v.output)
 for n,data in prepared.items():
  p=v.output/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 shutil.copyfile(p0,v.output/'driver/resident_observation.hpp')
 consumer_base=next(r for r in pin['files'] if r['name']=='numeric/consumer_owned.py')
 shutil.copyfile(v.repo/consumer_base['base_repo_path'],v.output/'BASE_consumer_owned.py')
 shutil.copyfile(ROOT/'router_local_observer.py',v.output/'tests/router_local_observer.py')
 print('RECONSTRUCTED_INACTIVE_SOURCE_ONLY_NO_HARDWARE_OR_REFERENCE_EXECUTION')
if __name__=='__main__':main()
