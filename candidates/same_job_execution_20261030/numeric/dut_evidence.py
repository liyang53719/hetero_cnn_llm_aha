"""Require real consumer report and actual successful Popen evidence, never rc2 alone."""
import hashlib,json,pathlib,math
import required_acceptance
P=pathlib.Path
def need(v,m):
 if not v:raise ValueError(m)
def pin(p):
 p=P(p);need(p.is_file()and not p.is_symlink()and p.stat().st_size<=16<<20,'bounded regular diagnostic report')
 return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
FULL_LOG_HELPER_SHA256='8573562ad287b9849bbe2da2a8a604fece8dd5a447bbc91db1b66991828f80fc'
def verified_full_log(out,profile,report,row,start,expected_log_policy=None):
 import importlib.util
 admission=report.get('execution_admission',{})
 if expected_log_policy is None:
  need('log_capture' not in row and 'budget_version' not in admission and 'log_policy' not in admission,'legacy evidence cannot claim full V2 capture')
  return None
 need(type(admission.get('budget_version')) is int and admission['budget_version'] in (2,3) and admission.get('log_policy')==expected_log_policy,'trusted full V2 cannot downgrade capture policy')
 need(admission.get('execution_mode')=='FULL_BLOCK_ACCEPTANCE' and report.get('candidate_scope')=='MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL','full streaming only reviewed model V2')
 helper=P(__file__).resolve().with_name('full_log.py');need(helper.is_file() and not helper.is_symlink() and hashlib.sha256(helper.read_bytes()).hexdigest()==FULL_LOG_HELPER_SHA256,'reviewed full log verifier')
 spec=importlib.util.spec_from_file_location('evidence_full_log',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 capture=module.read_capture(P(out)/f'profile{profile}.log',expected_log_policy)
 need(capture==row.get('log_capture'),'actual full log report binding')
 need(capture['pid']==start['pid'] and capture['consumer_pid']==start['consumer_pid'],'same actual pipe process')
 # A timeout or cap is diagnostic evidence only; preserve its actual native
 # status and bytes, and never promote a prefix to complete evidence.
 for chunk in module.chunks(P(out)/f'profile{profile}.log',capture,require_complete=False):pass
 if capture['termination_reason']=='WALL_TIMEOUT':need(row.get('error_class')=='TimeoutError','exact timeout classification')
 elif capture['complete']:need(row.get('exit_code')==capture['native_exit'],'exact native exit correspondence')
 else:need(bool(row.get('error_class')),'incomplete capture fails consumer')
 if row.get('execution_evidence'):
  need(capture['complete'] and capture['native_exit']==0,'clean full stream before execution qualification')
  limits=admission.get('postprocess_limits');observed=row.get('postprocess_observed')
  need(type(limits) is dict and set(limits)=={'wall_seconds','cpu_seconds'} and all(type(v) is int and 0<v<=3600 for v in limits.values()) and limits['cpu_seconds']<=limits['wall_seconds'],'exact finite postprocess limits')
  need(type(observed) is dict and set(observed)=={'wall_seconds','cpu_seconds','budget_exceeded'} and observed['budget_exceeded'] is False,'postprocess completed within budget')
  need(all(type(observed[k]) in (int,float) and 0<=observed[k]<=limits[k] and math.isfinite(observed[k]) for k in limits),'postprocess measured wall/CPU within limits')
 return capture

def verify(out,profile,artifact_sha,bundle_sha,binary_sha,runtime_sha,outer_pin,*,expected_log_policy=None):
 out=P(out);outer_path=P(outer_pin['path']);need(pin(outer_path)==outer_pin,'actual stage supervisor receipt pin');outer=json.loads(outer_path.read_text())
 need(outer.get('worker_started')is True and outer.get('native_exit') in (1,2) and outer.get('errors')==[],'actual supervised consumer exit1/2')
 cleanup=outer.get('cleanup_proof')or{};capture=outer.get('log_capture')or{}
 need(cleanup.get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and capture.get('pipe_eof_observed')is True and capture.get('gzip_finalized')is True,'complete actual outer cleanup/log')
 leader=outer.get('owner_identity');need(isinstance(leader,dict)and cleanup.get('owner_identity')==leader,'same cleanup leader identity')
 report=out/'RESULT.json';rp=pin(report);r=json.loads(report.read_text())
 need(r['status'] in ('INCOMPLETE','FAIL_EXACT_REFERENCE')and r['layer']=='CHISEL_EMITTED_SV_NUMERICAL_BACKEND'and r['final_rtl_executed']is False,'diagnostic scope')
 need(r['artifact_manifest_sha256']==artifact_sha and r['runtime_bundle_sha256']==bundle_sha,'same artifact/bundle')
 need(len(r['profiles'])==1 and r['profiles'][0]['profile']==profile,'one exact diagnostic profile')
 row=r['profiles'][0];started=out/f'profile{profile}.started.json';sp=pin(started);start=json.loads(started.read_text())
 need(start['schema']=='ACTUAL_DUT_POPEN_V1'and start['binary_sha256']==binary_sha and start['runtime_sha256']==runtime_sha,'actual pinned DUT Popen identity')
 need(type(start['pid'])is int and start['pid']>0 and type(start['consumer_pid'])is int and start['consumer_pid']>0 and start['pid']!=start['consumer_pid'],'actual child PID')
 need(start['consumer_pid']==leader['pid']and start['consumer_start_tick']==leader['start']and start['inherited_group']==leader['group']and start['inherited_session']==cleanup['session'],'same actual outer PID/start/group/session')
 log_capture=verified_full_log(out,profile,r,row,start,expected_log_policy)
 if row.get('error_class')=='TimeoutError':state='STARTED_TIMEOUT_INCOMPLETE'
 elif row.get('exit_code')is not None and row['exit_code']!=0:state='STARTED_NATIVE_FAILED'
 elif row.get('status')in ('BITWISE_MATCH_DIAGNOSTIC','BITWISE_MISMATCH_DIAGNOSTIC')and row.get('exit_code')==0:state='COMPLETE_TERMINAL_DIAGNOSTIC_NOT_PASS'
 else:state='STARTED_OBSERVATION_INCOMPLETE'
 qualification=required_acceptance.evaluate(row,outer_verified=True)
 need(outer['native_exit']==(1 if r['status']=='FAIL_EXACT_REFERENCE' else 2),'native consumer result/status correspondence')
 inner=required_acceptance.evaluate(row)
 need(row.get('qualification')==inner,'recomputed inner necessary predicate')
 need(row.get('status')==r['status']==inner['status'],'inner/report status must agree with recomputed evidence')
 need(row.get('numerical_pass') is False and r.get('numerical_pass') is False,'inner cannot claim outer cleanup in advance')
 if qualification['numerical_pass']:state='COMPLETE_FULL128_EXACT_REFERENCE_NOT_FINAL_RTL'
 elif qualification['failed']:state='COMPLETE_EXACT_REFERENCE_FAILED'
 common=r['common']
 need(common['binary']['sha256']==binary_sha,'same binary common artifact')
 identity=dict(layer=r['layer'],matrix_macs=4096,vector_lanes=32,artifact_manifest_sha256=artifact_sha,**{name+'_sha256':common[name]['sha256'] for name in ('binary','sv','source_manifest','driver')})
 # Resources were checked against the pinned frozen artifact by consumer main;
 # preserve its explicit values rather than infer them from a profile name.
 need(r.get('matrix_macs')==4096 and r.get('vector_lanes')==32,'verified fixed hardware resources')
 result=dict(profile=profile,state=state,report=rp,startup=sp,outer=outer_pin,qualification=qualification,common_artifact_identity=identity,numerical_pass=qualification['numerical_pass'])
 if log_capture is not None:result['log_capture']=log_capture
 return result

