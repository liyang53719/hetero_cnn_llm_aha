"""Require real consumer report and actual successful Popen evidence, never rc2 alone."""
import hashlib,json,pathlib
P=pathlib.Path
def need(v,m):
 if not v:raise ValueError(m)
def pin(p):
 p=P(p);need(p.is_file()and not p.is_symlink()and p.stat().st_size<=16<<20,'bounded regular diagnostic report')
 return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def verify(out,profile,artifact_sha,bundle_sha,binary_sha,runtime_sha,outer_pin):
 out=P(out);outer_path=P(outer_pin['path']);need(pin(outer_path)==outer_pin,'actual stage supervisor receipt pin');outer=json.loads(outer_path.read_text())
 need(outer.get('worker_started')is True and outer.get('native_exit')==2 and outer.get('errors')==[],'actual supervised diagnostic exit2')
 cleanup=outer.get('cleanup_proof')or{};capture=outer.get('log_capture')or{}
 need(cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and capture.get('pipe_eof_observed')is True and capture.get('gzip_finalized')is True,'complete actual outer cleanup/log')
 leader=outer.get('owner_identity');need(isinstance(leader,dict)and cleanup.get('owner_identity')==leader,'same cleanup leader identity')
 report=out/'RESULT.json';rp=pin(report);r=json.loads(report.read_text())
 need(r['status']=='INCOMPLETE'and r['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND'and r['final_rtl_executed']is False,'diagnostic scope')
 need(r['artifact_manifest_sha256']==artifact_sha and r['runtime_bundle_sha256']==bundle_sha,'same artifact/bundle')
 need(len(r['profiles'])==1 and r['profiles'][0]['profile']==profile,'one exact diagnostic profile')
 row=r['profiles'][0];started=out/f'profile{profile}.started.json';sp=pin(started);start=json.loads(started.read_text())
 need(start['schema']=='ACTUAL_DUT_POPEN_V1'and start['binary_sha256']==binary_sha and start['runtime_sha256']==runtime_sha,'actual pinned DUT Popen identity')
 need(type(start['pid'])is int and start['pid']>0 and type(start['consumer_pid'])is int and start['consumer_pid']>0 and start['pid']!=start['consumer_pid'],'actual child PID')
 need(start['consumer_pid']==leader['pid']and start['consumer_start_tick']==leader['start']and start['inherited_group']==leader['group']and start['inherited_session']==cleanup['session'],'same actual outer PID/start/group/session')
 if row.get('error_class')=='TimeoutError':state='STARTED_TIMEOUT_INCOMPLETE'
 elif row.get('exit_code')is not None and row['exit_code']!=0:state='STARTED_NATIVE_FAILED'
 elif row.get('status')in ('BITWISE_MATCH_DIAGNOSTIC','BITWISE_MISMATCH_DIAGNOSTIC')and row.get('exit_code')==0:state='COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS'
 else:state='STARTED_OBSERVATION_INCOMPLETE'
 return dict(profile=profile,state=state,report=rp,startup=sp,outer=outer_pin,numerical_pass=False)
