"""Strict local success projection; no raw log/IR/classes/weights in upload path."""
import argparse,json,os,pathlib,time
from seven_files import need,sha,regular,verify
from prepare_build import source_pins,WHOLE_SECONDS
from validate_launch import ACCEPTED_TRANSFER_APPROVAL_SHA256
P=pathlib.Path
PREP=('jdk','compile_tools','jars','verilator','idma','matrix','fresh_host','binding')
STAGES=('compile155','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend','frontend_native_Vbf16_context_lane_cluster16_rev8b_b_candidate_d','frontend_native_Vqwen2_matrix_command_endpoint_0','frontend_native_VTransposedDenseDownOwner','frontend_native_VHostBlockTopV4','archive_bf16_context_lane_cluster16_rev8b_b_candidate_d','archive_qwen2_matrix_command_endpoint_0','archive_TransposedDenseDownOwner','host_archive','host_link')
def strict(path):
 r=json.loads(regular(path,8<<20).read_text())
 need(type(r.get('native_exit'))is int and r['native_exit']==0 and r.get('errors')==[]and(r.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(r.get('log_capture')or{}).get('pipe_eof_observed')is True and(r.get('log_capture')or{}).get('gzip_finalized')is True,'strict original stage completion')
 return dict(receipt_sha256=sha(path),native_exit=0,strict_cleanup_eof=True)
def run(a):
 identity=json.loads(regular(a.identity,65536).read_text());inv=json.loads(regular(a.work/'BUILD_INVOCATION.json',65536).read_text())
 need(inv['artifact_identity']==identity and inv['source_pins_sha256']==source_pins(a.repo),'unchanged builder invocation/source')
 need(str(identity['run_id'])==os.environ['GITHUB_RUN_ID']and identity['launch_commit']==os.environ['GITHUB_SHA']and os.environ['GITHUB_RUN_ATTEMPT']=='1','actual original run')
 need(0<=time.monotonic()-inv['job_started_monotonic']<WHOLE_SECONDS,'original whole deadline')
 need(ACCEPTED_TRANSFER_APPROVAL_SHA256 is not None,'SEVEN_FILE_TRANSFER_APPROVAL_PENDING')
 build=a.work/'shared/build';front=build/'frontend';rows={}
 for name in PREP:rows['prep_'+name]=strict(build/('stage_'+name)/'RESULT.json')
 exits=json.loads(regular(front/'stage_exits.json',65536).read_text());need([x['name']for x in exits]==list(STAGES),'exact complete production stage sequence')
 for name in STAGES:rows[name]=strict(front/name/'RESULT.json')
 result=json.loads(regular(front/'BUILD_ONLY_RESULT.json',65536).read_text());need(result['status']=='PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS','actual completed build')
 artifact=front/'frozen_artifact';payload=verify(artifact,identity,result['artifact']['manifest']['sha256']);need(result['artifact']['expanded_bytes']==payload['expanded_bytes'],'packed complete byte count')
 output=dict(schema='SPLIT_BUILD_SEVEN_FILE_EXPORT_V1',status='BUILD_BYTES_ONLY_NO_NUMERICAL_PASS',artifact_identity=identity,source_pins_sha256=inv['source_pins_sha256'],payload=payload,stages=rows,transfer_approval_sha256=ACCEPTED_TRANSFER_APPROVAL_SHA256,numerical_pass=False,final_rtl_replay=False)
 raw=json.dumps(output,sort_keys=True,indent=2)+'\n';need(len(raw.encode())<=65536,'bounded safe summary')
 with a.output.open('x')as f:f.write(raw)
 with open(os.environ['GITHUB_OUTPUT'],'a')as f:f.write('artifact_dir='+str(artifact)+'\nartifact_name='+identity['artifact_name']+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for n in('repo','work','identity','output'):p.add_argument('--'+n,type=P,required=True)
 run(p.parse_args())
