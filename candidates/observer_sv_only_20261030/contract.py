"""Exact source/identity/phase contracts for the isolated SV-only reconstruction."""
import hashlib,json,os,pathlib,re
D=pathlib.Path(__file__).resolve().parent
OLD_OVERLAY_SHA='f8cb8f64819e7f2dd4f3778cc6066e18d062ec1102832f53ef6eabfbcace4b39'
NEW_OVERLAY_SHA='9be7810a372572e87b40d86d0b30245140c31cd40cdd6cf2f9cacead459beda2'
CANONICAL={'old':'90464ff45917c1b853c7d1b36e67dd5e43b5503b7fa0583704ee615c08919533','new':'00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c'}
NORMALIZED={'old':'6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5','new':'ec70f91181b0422ca7cf2bc845a2a1f04c9d862f4f27d265c5a064a969058d72'}
STAGES=[('jdk',300,1),('jars',600,1)]+[(s+'_'+n,w,r)for s in ('old','new')for n,w,r in [('compile155',300,3),('helper_compile',300,3),('original_ir',600,6),('canonical',300,3),('emit_sv',900,6),('svscan',180,1)]]+[('projection',300,1)]
WHOLE=10800;EXECUTION=7710;WORKFLOW=1320

def need(x,m):
 if not x:raise ValueError(m)
def sha(p):
 with pathlib.Path(p).open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def unique(pairs):
 out={}
 for key,value in pairs:need(key not in out,'duplicate JSON key');out[key]=value
 return out
def read(path,cap=2<<20):
 path=pathlib.Path(path);need(path.is_file() and not any(p.is_symlink()for p in (path,*path.parents)) and 0<path.stat().st_size<=cap,'bounded regular non-symlink metadata')
 b=path.read_bytes();need(len(b)<=cap,'metadata read cap');return json.loads(b,object_pairs_hook=unique)
def write(path,value,cap=2<<20):
 b=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();need(len(b)<=cap,'metadata output cap')
 with pathlib.Path(path).open('xb')as stream:stream.write(b)
def validate_identity(x):
 from validate_launch import LAUNCH
 need(type(x)is dict and set(x)=={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'},'exact six-field identity')
 need(type(x['run_id'])is int and x['run_id']>0 and x['artifact_name']=='hetero-observer-sv-only-summary-'+str(x['run_id']),'run/artifact identity')
 need(all(type(x[k])is str and re.fullmatch('[0-9a-f]{40}',x[k])for k in ('source_commit','launch_commit','launch_manifest_blob_sha')) and x['source_commit']!=x['launch_commit'] and x['launch_manifest_path']==LAUNCH,'exact launch identity')
 return x
def closure(repo):
 rows=read(D/'SOURCE_PINS.json')['files'];pins={};seen=set()
 for row in rows:
  need(set(row)=={'path','bytes','sha256'},'source pin row')
  rel=pathlib.PurePosixPath(row['path']);need(not rel.is_absolute() and '..'not in rel.parts and str(rel)not in seen,'unique relative source pin');seen.add(str(rel))
  p=repo/rel;need(p.is_file() and not any(x.is_symlink()for x in (p,*p.parents)) and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'source closure pin')
  pins[str(p.resolve())]=row['sha256']
 pins[str(D/'SOURCE_PINS.json')]=sha(D/'SOURCE_PINS.json');return pins
def source_paths(repo,side,original):
 overlay=D/'OLD_FIXED_SOURCE_OVERLAY.json' if side=='old' else repo/'candidates/ci_frontend_materialization_r2_20261029/FIXED_SOURCE_OVERLAY_R2.json'
 need(sha(overlay)==(OLD_OVERLAY_SHA if side=='old' else NEW_OVERLAY_SHA),'independent old/new overlay hard pin')
 rows=read(overlay)['files'];old={pathlib.PurePosixPath(x['path']).name:x for x in original['sources']}
 need(len(rows)==len(old)==155 and len({x['name']for x in rows})==155 and {x['name']for x in rows}==set(old),'same exact155 names')
 changes={x['name']for x in rows if x['sha256']!=old[x['name']]['sha256']}
 expected={'HostBlockCommandsV4.scala'} if side=='old' else {'FfnResidentCoordinator.scala','FfnTileSiluBridge.scala','HostBlockCommandsV4.scala','HostBlockTopV4.scala','QwenOwnerProtocol.scala','UnifiedMoeRouterNumericalOwnerV2.scala','UnifiedMoeRouterPipelineBindingV2.scala','UnifiedMoeRuntimeExpertLoopV4.scala'}
 need(changes==expected,'exact fixed source differences')
 paths=[]
 for row in rows:
  rel=pathlib.PurePosixPath(row['repo_path']);need(not rel.is_absolute() and '..'not in rel.parts,'source path')
  p=repo/rel;need(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'155 exact bytes');paths.append(str(p.resolve()))
 return paths
def completed(r):
 return r.get('native_exit')==0 and r.get('errors')==[] and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and r.get('log_capture',{}).get('pipe_eof_observed')is True and r.get('log_capture',{}).get('gzip_finalized')is True
