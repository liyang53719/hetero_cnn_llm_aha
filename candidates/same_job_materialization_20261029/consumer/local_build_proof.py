"""Same-job retained build result consistency; NEVER a GitHub download proof.
Caller must obtain expected result SHA/run/commits from its owning reviewed job,
not from this document itself. This does not authenticate arbitrary local files.
"""
import hashlib,json,pathlib
P=pathlib.Path
def need(v,s):
 if not v: raise ValueError(s)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(result_path,result_sha,manifest,manifest_sha,frozen,run_id,launch_commit,source_commit):
 result_path=P(result_path);manifest=P(manifest)
 need(result_path.is_absolute() and result_path.is_file() and not result_path.is_symlink(),'retained regular absolute build result')
 need(result_path.stat().st_size<=65536 and sha(result_path)==result_sha,'separately pinned retained build result')
 need(manifest.is_absolute() and manifest.resolve()==result_path.parent.resolve()/'frozen_artifact/frozen_artifact.json','same build output tree; no imported artifact')
 need(manifest.is_file() and not manifest.is_symlink() and sha(manifest)==manifest_sha,'same job frozen manifest')
 i=frozen['artifact_identity']
 need(type(run_id)is int and run_id>0 and i['run_id']==run_id,'owning job run id')
 need(i['launch_commit']==launch_commit and i['source_commit']==source_commit and launch_commit!=source_commit,'owning job launch/source identity')
 result=json.loads(result_path.read_text())
 need(result['status']=='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS','actual build-only terminal result')
 need(result['scope']=='CHISEL_TEST_BACKEND_PREPARATION_NOT_FINAL_RTL_REPLAY','build scope')
 artifact=result['artifact'];p=artifact['manifest']
 need(P(p['path'])==manifest and p['sha256']==manifest_sha and p['bytes']==manifest.stat().st_size,'producer returned exact manifest pin')
 need(artifact['scope']=='ONE_SHARED_BINARY_FROZEN_NOT_UPLOADED_NOT_EXECUTED' and artifact['files']==7,'local build artifact scope')
 expected={manifest.name,frozen['tool_manifest']['path']}|{p['path'] for p in frozen['common'].values()}
 need(len(expected)==7 and all(P(x).name==x for x in expected),'flat seven-file producer layout')
 children=list(manifest.parent.iterdir())
 need({p.name for p in children}==expected and all(p.is_file() and not p.is_symlink() for p in children),'actual seven regular producer files')
 need(sum(p.stat().st_size for p in children)==artifact['expanded_bytes'],'local artifact size ledger')
 return dict(status='SAME_JOB_RETAINED_BUILD_RESULT_CONSISTENT',build_result_sha256=result_sha,run_id=run_id,launch_commit=launch_commit,source_commit=source_commit,remote_api_verified=False,artifact_uploaded=False,downloaded_artifact_id=None)
