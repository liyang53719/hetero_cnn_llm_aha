"""Read-only original seven-file byte closure; never executes the binary."""
import hashlib,json,pathlib,re
P=pathlib.Path
NAMES={'binary':'dut.bin','sv':'hardware.sv','driver':'driver.cpp','source_manifest':'source_manifest.json','tool_manifest':'tool_manifest.json','build_receipt':'build_receipt.json'}
CAP=4<<30

def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def regular(p,cap):
 p=P(p);need(p.is_absolute()and p==p.resolve()and all(not q.is_symlink()for q in(p,*p.parents))and p.is_file()and 0<p.stat().st_size<=cap,'canonical bounded regular payload');return p

def verify(root,identity,expected_manifest_sha=None):
 root=P(root);need(root.is_absolute()and root==root.resolve()and root.is_dir()and all(not q.is_symlink()for q in(root,*root.parents)),'canonical artifact root')
 need({p.name for p in root.iterdir()}==set(NAMES.values())|{'frozen_artifact.json'},'exact seven original files')
 mf=regular(root/'frozen_artifact.json',65536);mh=sha(mf)
 if expected_manifest_sha is not None:need(mh==expected_manifest_sha,'independent frozen manifest pin')
 d=json.loads(mf.read_text());need(d['schema']=='FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2'and d['profiles']==list(range(5))and all(type(x)is int for x in d['profiles'])and d['matrix_macs']==4096 and d['vector_lanes']==32 and d['artifact_identity']==identity,'one fixed builder identity/hardware')
 need(set(d['common'])=={'binary','sv','driver','source_manifest','build_receipt'},'exact common roles')
 rows={**d['common'],'tool_manifest':d['tool_manifest']};total=mf.stat().st_size;actual={}
 for role,name in NAMES.items():
  row=rows[role];need(set(row)=={'path','bytes','sha256'}and row['path']==name and type(row['bytes'])is int and isinstance(row['sha256'],str)and re.fullmatch('[0-9a-f]{64}',row['sha256']),'fixed file pin')
  p=regular(root/name,65536 if role=='build_receipt'else 32<<20 if role in('source_manifest','tool_manifest','driver')else CAP)
  need(row['bytes']==p.stat().st_size and sha(p)==row['sha256'],'exact payload bytes');total+=row['bytes'];actual[name]=dict(bytes=row['bytes'],sha256=row['sha256'])
 need(total<=CAP,'expanded artifact cap')
 r=json.loads((root/'build_receipt.json').read_text());need(r['status']=='BINARY_BUILD_ONLY_NO_NUMERICS'and r['scope']=='CHISEL_TEST_BACKEND_NOT_FINAL_RTL_REPLAY'and r['config_only']is False and r['software_arithmetic_substitution']is False,'real build-only scope')
 need(r['source_commit']==identity['source_commit']and r['launch_commit']==identity['launch_commit'],'source/launch identity')
 for k in ('binary','sv','driver','source_manifest','tool_manifest'):need(r[k+'_sha256']==rows[k]['sha256'],'build receipt payload binding')
 need([x['phase']for x in r['phases']]==['archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link'],'all original archive/link stages')
 need(all(type(x['native_exit'])is int and x['native_exit']==0 and re.fullmatch('[0-9a-f]{64}',x['supervisor_receipt_sha256'])and re.fullmatch('[0-9a-f]{64}',x['output_sha256'])for x in r['phases']),'actual native receipt pins')
 need(r['phases'][-1]['output_sha256']==rows['binary']['sha256'],'linked binary')
 with (root/'dut.bin').open('rb')as f:need(f.read(6)==b'\x7fELF\x02\x01','ELF64 little-endian bytes only')
 actual['frozen_artifact.json']=dict(bytes=mf.stat().st_size,sha256=mh)
 return dict(manifest_sha256=mh,expanded_bytes=total,files=actual,numerical_pass=False,final_rtl_replay=False)
