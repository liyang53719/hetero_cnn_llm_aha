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
def parse_log(path,root):
 regular(path,root,64<<20);digest=hashlib.sha256();count=0;first=last=None;total=0
 with path.open('rb') as f:
  while True:
   raw=f.readline(8193)
   if not raw:break
   total+=len(raw);need(total<=64<<20 and len(raw)<=8192);digest.update(raw)
   if not raw.startswith(b'HOST_PROGRESS '):continue
   need(raw.endswith(b'\n'));parts=raw.decode('ascii').split();need(len(parts)==len(KEYS)+2 and parts[1] in PHASES)
   values={}
   for item in parts[2:]:
    k,sep,v=item.partition('=');need(sep and k in KEYS and k not in values and v.isascii() and v.isdecimal() and len(v)<=20)
    n=int(v);need(0<=n<=2**64-1);values[k]=n
   need(set(values)==set(KEYS) and values['active_cycles']<=values['cycles'] and values['reset_required'] in (0,1))
   if last:need(values['cycles']>=last['cycles'] and values['active_cycles']>=last['active_cycles'] and values['completions']>=last['completions'])
   values['phase']=parts[1];first=first or values;last=values;count+=1;need(count<=100000)
 need(path.stat().st_size==total)
 return dict(log_sha256=digest.hexdigest(),log_bytes=total,sample_count=count,first=first,last=last)
def project(work,identity,numeric_dir=None):
 work=P(work);root=work/'materials/numeric';numeric_dir=P(numeric_dir) if numeric_dir else P(__file__).parent/'numeric'
 sys.path.insert(0,str(numeric_dir));import dut_evidence as evidence
 rows=[];common=None
 for i in range(5):
  row=dict(profile=i,status='UNAVAILABLE',first=None,last=None,sample_count=0,outer_elapsed_seconds=None,observed_cycles_per_outer_second=None,full_block_total_cycles=None,full_block_remaining_seconds=None,full_block_mac_utilization=None)
  rows.append(row)
  try:
   out=root/f'profile{i}/material/dut_result';outer=root/f'runs/p{i}_dut/RESULT.json'
   report=document(out/'RESULT.json',work);started=document(out/f'profile{i}.started.json',work);native=document(outer,work)
   expected={k:identity[k] for k in ('run_id','source_commit','launch_commit')}
   need(type(expected['run_id']) is int and expected['run_id']>0)
   need(all(isinstance(expected[k],str) and re.fullmatch('[0-9a-f]{40}',expected[k]) for k in ('source_commit','launch_commit')))
   need(all(isinstance(started.get(k),str) and re.fullmatch('[0-9a-f]{64}',started[k]) for k in ('binary_sha256','runtime_sha256')))
   need(all(report['artifact_identity'].get(k)==v for k,v in expected.items()))
   verified=evidence.verify(out,i,report['artifact_manifest_sha256'],report['runtime_bundle_sha256'],started['binary_sha256'],started['runtime_sha256'],evidence.pin(outer))
   actual=verified['common_artifact_identity']
   if common is None:common=actual
   need(actual==common)
   parsed=parse_log(out/f'profile{i}.log',work)
   elapsed=native.get('elapsed_seconds');elapsed=elapsed if type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<elapsed<=21000 else None
   row.update(parsed,status='OBSERVED_PARTIAL_NOT_NUMERICAL_PASS' if parsed['sample_count'] else 'NO_PROGRESS_LINES',outer_elapsed_seconds=elapsed,source_commit=expected['source_commit'],binary_sha256=started['binary_sha256'],runtime_sha256=started['runtime_sha256'],report_sha256=verified['report']['sha256'],startup_sha256=verified['startup']['sha256'],outer_sha256=verified['outer']['sha256'])
   if parsed['last'] and parsed['last']['active_cycles']==0:row['status']='NO_ACTIVE_PROGRESS_SAMPLE'
   if elapsed and parsed['last'] and parsed['last']['active_cycles']>0:
    rate=parsed['last']['active_cycles']/elapsed
    row['observed_cycles_per_outer_second']=rate if math.isfinite(rate)else None
  except (OSError,ValueError,KeyError,TypeError,AttributeError,UnicodeError):pass
 return dict(running_trace_clock_check_interval_active_cycles=64,running_trace_minimum_wall_seconds=1,first_running_sample='FIRST_SUCCESSFUL_WHILE_STEP',forced_process_termination_final_snapshot_guaranteed=False,additional_trace_phases=['reset','completion','terminal'],scope='POST_CLEANUP_SAME_JOB_LOCAL_LOG_OBSERVATIONS_ONLY',numerical_pass=False,rate_basis='LAST_RECORDED_ACTIVE_CYCLES_DIVIDED_BY_ENCLOSING_CONSUMER_STAGE_ELAPSED_NOT_INSTANTANEOUS_SIMULATION_RATE',total_cycle_prediction='UNKNOWN_NO_FULL_BLOCK_DENOMINATOR',log_binding='FIXED_POPEN_OUTPUT_PATH_AFTER_VERIFIED_OWNER_CLEANUP_HASHED_AT_PROJECTION_NOT_PREEXISTING_LOG_PIN',profiles=rows)
