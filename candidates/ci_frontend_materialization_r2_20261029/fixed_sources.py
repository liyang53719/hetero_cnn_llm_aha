"""NEW R2 manifest selecting existing 7a22 source blobs (corrected diagnostic cap). Read/check only unless explicit source copy.
No compile, no dependency download, no mutation of checked-out source.
"""
import argparse,hashlib,json,pathlib,subprocess
OVERLAY_SHA='f8cb8f64819e7f2dd4f3778cc6066e18d062ec1102832f53ef6eabfbcace4b39'
FIXED_SHA='8cea5e8863e47ca14978871d23b7f80639e43ae3192c3e6c0ccf372b1c73a20f'
COMMIT='7a22ccc14d6d269262ecf5756488c81e8e4ccfc4'
def need(v,msg):
 if not v:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def validate_overlay(raw,original):
 need(sha(raw)==OVERLAY_SHA,'fixed reviewed overlay hash (old155/tamper rejected)')
 d=json.loads(raw);old={pathlib.PurePosixPath(x['path']).name:x for x in original['sources']}
 need(d['source_count']==155 and len(d['files'])==155 and len(old)==155,'exact155')
 names=[x['name'] for x in d['files']];need(len(set(names))==155 and set(names)==set(old),'same155 source names')
 changed=[]
 for x in d['files']:
  path=pathlib.PurePosixPath(x['repo_path']);need(not path.is_absolute() and '..' not in path.parts,'relative source')
  if x['sha256']!=old[x['name']]['sha256']:changed.append(x['name'])
 need(changed==['HostBlockCommandsV4.scala'],'only approved carry fix')
 fixed=next(x for x in d['files'] if x['name']==changed[0]);need(fixed['sha256']==FIXED_SHA,'fixed source')
 return d['files']
def checked_paths(repo,overlay,original):
 rows=validate_overlay(pathlib.Path(overlay).read_bytes(),original);paths=[]
 for x in rows:
  p=pathlib.Path(repo)/x['repo_path'];need(p.is_file() and not p.is_symlink() and p.stat().st_size==x['bytes'] and sha(p.read_bytes())==x['sha256'],'fixed source bytes '+x['name']);paths.append(str(p.resolve()))
 return paths
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--repo',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path);a.add_argument('--from-verified-git',action='store_true');v=a.parse_args()
 def read(rel):
  if v.from_verified_git:return subprocess.check_output(['git','-C',str(v.repo),'show',COMMIT+':'+rel])
  return (v.repo/rel).read_bytes()
 original=json.loads(read('candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json'))
 raw=pathlib.Path(__file__).with_name('FIXED_SOURCE_OVERLAY_R2.json').read_bytes();rows=validate_overlay(raw,original)
 if v.output:need(not v.output.exists(),'fresh source-only destination');v.output.mkdir()
 for x in rows:
  b=read(x['repo_path']);need(len(b)==x['bytes'] and sha(b)==x['sha256'],'source byte drift '+x['name'])
  if v.output:(v.output/x['name']).write_bytes(b)
 print('PASS_FIXED155_SOURCE_BYTES_ONLY_NO_COMPILE_NO_CANONICAL_PASS')
