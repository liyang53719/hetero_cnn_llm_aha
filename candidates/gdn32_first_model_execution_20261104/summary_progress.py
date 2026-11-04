"""Post-cleanup local log observations, not numerical or full-block utilization proof."""
import hashlib,json,math,pathlib,re,sys
P=pathlib.Path
KEYS=tuple('cycles active_cycles pc completions read_bursts read_beats read_acks write_bursts write_beats write_acks write_ack_bytes pipeline_issues pipeline_stalls idma_transfers idma_cache_hits idma_streamed_read_beats idma_streamed_write_beats owner_jobs useful_macs executed_macs host_write_bytes memory_accepted_0 memory_returned_0 memory_accepted_1 memory_returned_1 reset_required'.split())
PHASES={'reset','running','completion','terminal'}
def need(v):
 if not v:raise ValueError('invalid bounded progress evidence')
def regular(p,root,limit):
 need(p.is_relative_to(root) and all(not x.is_symlink() for x in (p,*p.parents)))
 need(p.is_file() and p.stat().st_size<=limit)
def document(p,root):
 regular(p,root,16<<20);return json.loads(p.read_text())
FULL_LOG_HELPER_SHA256='8573562ad287b9849bbe2da2a8a604fece8dd5a447bbc91db1b66991828f80fc'
def full_log_module():
 import importlib.util
 path=P(__file__).resolve().parent/'numeric/full_log.py'
 regular(path,path.parent,1<<20);need(hashlib.sha256(path.read_bytes()).hexdigest()==FULL_LOG_HELPER_SHA256)
 spec=importlib.util.spec_from_file_location('progress_full_log',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def parse_log(path,root,capture=None):
 digest=hashlib.sha256();count=0;first=last=None;total=0;seen_active=False;reset_after_start=False
 if capture is None:
  regular(path,root,64<<20)
  def raw_lines():
   with path.open('rb') as f:
    while True:
     raw=f.readline(8193)
     if not raw:break
     yield raw
  source=raw_lines();limit=64<<20
 else:
  helper=full_log_module();archive,_=helper.paths(path);regular(archive,root,helper.policy(capture['policy'])['compressed_bytes'])
  source=helper.lines(path,capture,require_complete=False);limit=capture['policy']['raw_bytes']
 for raw in source:
  total+=len(raw);need(total<=limit and len(raw)<=8192);digest.update(raw)
  if not raw.startswith(b'HOST_PROGRESS '):continue
  need(raw.endswith(b'\n'));parts=raw.decode('ascii').split();need(len(parts)==len(KEYS)+2 and parts[1] in PHASES)
  values={}
  for item in parts[2:]:
   k,sep,v=item.partition('=');need(sep and k in KEYS and k not in values and v.isascii() and v.isdecimal() and len(v)<=20)
   n=int(v);need(0<=n<=2**64-1);values[k]=n
  need(set(values)==set(KEYS) and values['active_cycles']<=values['cycles'] and values['reset_required'] in (0,1))
  if last:need(values['cycles']>=last['cycles'] and values['active_cycles']>=last['active_cycles'] and values['completions']>=last['completions'])
  reset_after_start=reset_after_start or values['reset_required']==1 or (seen_active and parts[1]=='reset')
  seen_active=seen_active or values['active_cycles']>0
  values['phase']=parts[1];first=first or values;last=values;count+=1
  if capture is None:need(count<=100000)
 if capture is None:need(path.stat().st_size==total)
 result=dict(log_sha256=digest.hexdigest(),log_bytes=total,sample_count=count,first=first,last=last,observed_reset_after_start=reset_after_start)
 if capture is not None:
  reason=capture['termination_reason'];rc=capture['native_exit']
  classification='TIMEOUT_INCOMPLETE' if reason=='WALL_TIMEOUT' else 'CAPTURE_INCOMPLETE' if not capture['complete'] else 'NATIVE_SIGNAL' if rc<0 else 'RESET_REQUIRED' if last and last['reset_required']==1 else 'NATIVE_FAILED' if rc else 'NATIVE_EXIT_ZERO_NOT_NUMERICAL_PASS'
  result.update(log_storage_schema=capture['schema'],gzip_bytes=capture['gzip_bytes'],gzip_sha256=capture['gzip_sha256'],raw_crc32=capture['raw_crc32'],pipe_eof_observed=capture['pipe_eof_observed'],gzip_finalized=capture['gzip_finalized'],log_complete=capture['complete'],native_dut_exit=rc,log_termination_reason=reason,process_classification=classification)
 return result
def project(work,identity,numeric_dir=None,*,expected_log_policies=None,expected_outer_seconds=None,profile_ids=None):
 work=P(work);root=work/'materials/numeric';numeric_dir=P(numeric_dir) if numeric_dir else P(__file__).parent/'numeric'
 sys.path.insert(0,str(numeric_dir));import dut_evidence as evidence
 if profile_ids is not None:need(type(profile_ids) in (list,tuple) and len(set(profile_ids))==len(profile_ids) and all(type(i) is int and 0<=i<5 for i in profile_ids))
 rows=[];common=None
 for i in range(5):
  row=dict(profile=i,status='UNAVAILABLE',first=None,last=None,sample_count=0,outer_elapsed_seconds=None,observed_cycles_per_outer_second=None,full_block_total_cycles=None,full_block_remaining_seconds=None,full_block_mac_utilization=None)
  rows.append(row)
  if profile_ids is not None and i not in profile_ids:continue
  try:
   out=root/f'profile{i}/material/dut_result';outer=root/f'runs/p{i}_dut/RESULT.json'
   report=document(out/'RESULT.json',work);started=document(out/f'profile{i}.started.json',work);native=document(outer,work)
   expected={k:identity[k] for k in ('run_id','source_commit','launch_commit')}
   need(type(expected['run_id']) is int and expected['run_id']>0)
   need(all(isinstance(expected[k],str) and re.fullmatch('[0-9a-f]{40}',expected[k]) for k in ('source_commit','launch_commit')))
   need(all(isinstance(started.get(k),str) and re.fullmatch('[0-9a-f]{64}',started[k]) for k in ('binary_sha256','runtime_sha256')))
   need(all(report['artifact_identity'].get(k)==v for k,v in expected.items()))
   expected_policy=expected_log_policies[str(i)] if expected_log_policies is not None else None
   if expected_policy is not None:
    import signal
    need(signal.getitimer(signal.ITIMER_REAL)[0]>0 and signal.getitimer(signal.ITIMER_PROF)[0]>0)
   kwargs={'expected_log_policy':expected_policy} if expected_policy is not None else {}
   verified=evidence.verify(out,i,report['artifact_manifest_sha256'],report['runtime_bundle_sha256'],started['binary_sha256'],started['runtime_sha256'],evidence.pin(outer),**kwargs)
   actual=verified['common_artifact_identity']
   if common is None:common=actual
   need(actual==common)
   capture=verified.get('log_capture')
   parsed=parse_log(out/f'profile{i}.log',work,capture)
   elapsed_limit=21000 if capture is None else expected_outer_seconds.get(str(i),0) if type(expected_outer_seconds) is dict else 0
   need(type(elapsed_limit) is int and elapsed_limit>=0)
   elapsed=native.get('elapsed_seconds');elapsed=elapsed if type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<elapsed<=elapsed_limit else None
   row.update(parsed,status='OBSERVED_PARTIAL_NOT_NUMERICAL_PASS' if parsed['sample_count'] else 'NO_PROGRESS_LINES',outer_elapsed_seconds=elapsed,source_commit=expected['source_commit'],binary_sha256=started['binary_sha256'],runtime_sha256=started['runtime_sha256'],report_sha256=verified['report']['sha256'],startup_sha256=verified['startup']['sha256'],outer_sha256=verified['outer']['sha256'])
   if parsed['last'] and parsed['last']['active_cycles']==0:row['status']='NO_ACTIVE_PROGRESS_SAMPLE'
   if elapsed and parsed['last'] and parsed['last']['active_cycles']>0:
    rate=parsed['last']['active_cycles']/elapsed
    row['observed_cycles_per_outer_second']=rate if math.isfinite(rate)else None
  except (OSError,ValueError,KeyError,TypeError,AttributeError,UnicodeError):pass
 return dict(running_trace_clock_check_interval_active_cycles=64,running_trace_minimum_wall_seconds=1,first_running_sample='FIRST_SUCCESSFUL_WHILE_STEP',forced_process_termination_final_snapshot_guaranteed=False,additional_trace_phases=['reset','completion','terminal'],scope='POST_CLEANUP_SAME_JOB_LOCAL_LOG_OBSERVATIONS_ONLY',numerical_pass=False,rate_basis='LAST_RECORDED_ACTIVE_CYCLES_DIVIDED_BY_ENCLOSING_CONSUMER_STAGE_ELAPSED_NOT_INSTANTANEOUS_SIMULATION_RATE',total_cycle_prediction='UNKNOWN_NO_FULL_BLOCK_DENOMINATOR',log_binding='FIXED_POPEN_OUTPUT_PATH_AFTER_VERIFIED_OWNER_CLEANUP_HASHED_AT_PROJECTION_NOT_PREEXISTING_LOG_PIN',profiles=rows)


def first_meaningful_projection(row):
 """Only called on the owning-job verified local progress projection. Never PASS."""
 last=row.get('last');valid=row.get('status')=='OBSERVED_PARTIAL_NOT_NUMERICAL_PASS' and type(last)is dict
 reached=bool(valid and last.get('pc',0)>=7 and last.get('completions',0)>=7 and row.get('observed_reset_after_start')is False)
 timeout=row.get('log_termination_reason')=='WALL_TIMEOUT'
 return dict(schema='GDN32_FIRST_MEANINGFUL_TARGET_V1',profile=1,target_status='TARGET_REACHED_NOT_FULL'if reached else'TARGET_NOT_REACHED',attempt_status='INCOMPLETE_TIMEOUT'if timeout else'REQUIRES_ORIGINAL_NUMERICAL_QUALIFICATION',necessary_active_cycles=21516288,observed_pc=last.get('pc')if valid else None,observed_completions=last.get('completions')if valid else None,full_program_commands=17,tokens=128,numerical_pass=False,final_rtl_acceptance=False,completion_guaranteed=False)
