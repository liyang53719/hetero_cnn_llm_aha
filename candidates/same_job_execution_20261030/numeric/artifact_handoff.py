"""Read-only split builder -> cloud executor admission. No download/extract/execute.
Expected handoff SHA must come from the owning reviewed controller after remote
source/run/artifact verification. A self-authored JSON is NOT authentication.
Caller validates/verifies the live executor separately before calling verify.
Original seven bytes stay unchanged; no same-job result is manufactured.
"""
import hashlib,json,pathlib,re
P=pathlib.Path
NAMES={'binary':'dut.bin','sv':'hardware.sv','driver':'driver.cpp','source_manifest':'source_manifest.json','tool_manifest':'tool_manifest.json','build_receipt':'build_receipt.json'}
FIELDS={'run_id','artifact_name','source_commit','launch_commit','launch_manifest_path','launch_manifest_blob_sha'}
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def hex64(v):return isinstance(v,str)and re.fullmatch('[0-9a-f]{64}',v)is not None
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'bounded canonical regular handoff file');return p
def read_pin(p,h,cap=65536):
 p=regular(p,cap);need(hex64(h)and sha(p)==h,'independently pinned handoff bytes');return json.loads(p.read_text())
def builder_identity(i):
 need(type(i)is dict and set(i)==FIELDS,'builder six-field identity')
 need(type(i['run_id'])is int and i['run_id']>0,'actual builder run id')
 need(isinstance(i['artifact_name'],str)and re.fullmatch('[A-Za-z0-9_.-]{1,128}',i['artifact_name']),'builder artifact name')
 need(all(isinstance(i[k],str)and re.fullmatch('[0-9a-f]{40}',i[k])for k in('source_commit','launch_commit','launch_manifest_blob_sha')),'builder git identity')
 need(i['source_commit']!=i['launch_commit']and re.fullmatch(r'ci_launch/[A-Za-z0-9_.-]+\.json',i['launch_manifest_path']),'builder launch/source')
 return i

def verify(handoff_path,handoff_sha,manifest,manifest_sha,frozen,executor_identity):
 h=read_pin(handoff_path,handoff_sha)
 need(set(h)=={'schema','scope','builder_identity','source_pins_sha256','artifact_manifest_sha256','artifact_expanded_bytes','remote_receipt','numerical_pass','final_rtl_executed'},'exact handoff fields')
 need(h['schema']=='VERIFIED_SEVEN_FILE_BUILD_HANDOFF_V1'and h['scope']=='BUILD_BYTES_ONLY_REVALIDATE_EXECUTOR_ABI_AND_NUMERICS','handoff scope')
 need(h['numerical_pass']is False and h['final_rtl_executed']is False,'no imported numerical result')
 i=builder_identity(h['builder_identity']);need(i==frozen['artifact_identity'],'same actual builder identity')
 need(executor_identity['source_commit']==i['source_commit'],'separate exact executor, identical source commit')
 need(hex64(h['source_pins_sha256'])and h['artifact_manifest_sha256']==manifest_sha,'reviewed source and artifact pins')
 r=h['remote_receipt'];need(type(r)is dict and set(r)=={'artifact_id','archive_sha256','verified_api_receipt_sha256','source_commit','run_id'},'exact remotely verified receipt')
 need(type(r['artifact_id'])is int and r['artifact_id']>0 and hex64(r['archive_sha256'])and hex64(r['verified_api_receipt_sha256']),'independent actual remote receipt pins')
 need(type(r['run_id'])is int and r['source_commit']==i['source_commit']and r['run_id']==i['run_id'],'artifact exact build run/source')
 manifest=regular(manifest,65536);need(manifest.name=='frozen_artifact.json'and sha(manifest)==manifest_sha,'actual frozen manifest')
 need(json.loads(manifest.read_text())==frozen,'caller manifest bytes')
 root=manifest.parent;need({p.name for p in root.iterdir()}==set(NAMES.values())|{'frozen_artifact.json'},'only original seven-file artifact')
 need(frozen['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'and frozen['profiles']==list(range(5))and all(type(v)is int for v in frozen['profiles'])and frozen['matrix_macs']==4096 and frozen['vector_lanes']==32,'one fixed five-profile hardware')
 need(set(frozen['common'])=={'binary','sv','driver','source_manifest','build_receipt'},'exact common files')
 rows={**frozen['common'],'tool_manifest':frozen['tool_manifest']};total=manifest.stat().st_size
 for k,name in NAMES.items():
  row=rows[k];need(set(row)=={'path','bytes','sha256'}and row['path']==name,'fixed artifact file mapping')
  p=regular(root/name,65536 if k=='build_receipt' else 32<<20 if k in ('source_manifest','tool_manifest','driver') else 4<<30);need(type(row['bytes'])is int and p.stat().st_size==row['bytes']and hex64(row['sha256'])and sha(p)==row['sha256'],'artifact payload pin');total+=row['bytes']
 need(type(h['artifact_expanded_bytes'])is int and total==h['artifact_expanded_bytes']and total<=4<<30,'artifact complete bounded size')
 receipt=json.loads((root/'build_receipt.json').read_text())
 need(receipt['status']=='BINARY_BUILD_ONLY_NO_NUMERICS'and receipt['scope']=='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY','real build-only receipt')
 need(receipt['config_only']is False and receipt['software_arithmetic_substitution']is False,'no software substituted hardware')
 need(receipt['source_commit']==i['source_commit']and receipt['launch_commit']==i['launch_commit'],'build receipt identity')
 for k in ('binary','sv','driver','source_manifest','tool_manifest'):need(receipt[k+'_sha256']==rows[k]['sha256'],'actual build receipt pin')
 phases=receipt['phases'];need(type(phases)is list and [p['phase']for p in phases]==['archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link'],'exact full archive/link chain')
 need(all(type(p['native_exit'])is int and p['native_exit']==0 and hex64(p['output_sha256'])and hex64(p['supervisor_receipt_sha256'])for p in phases),'build native receipt identities')
 need(phases[-1]['output_sha256']==rows['binary']['sha256'],'actual linked binary')
 return dict(status='VERIFIED_IMPORTED_BUILD_BYTES_NOT_NUMERICAL',builder_identity=i,executor_identity=executor_identity,handoff_sha256=handoff_sha,artifact_manifest_sha256=manifest_sha,source_pins_sha256=h['source_pins_sha256'],remote_receipt=r,numerical_pass=False,final_rtl_executed=False)
