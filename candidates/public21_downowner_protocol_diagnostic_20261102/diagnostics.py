"""Closed-log finite projection: never emits raw error, path, payload or source text."""
import gzip,json,re,hashlib
FIELDS={
'B_EMIT_ONLY_AFTER_ELAB':{'backend_started','native_loaded'},
'B_EMIT_ONLY_AFTER_LOW':{'backend_started','native_loaded'},
'B_EMIT_ONLY_AFTER_INFO':{'name_matches','low_exists','backend_started','native_loaded'},
'B_EMIT_ONLY_BEFORE_ELAB':{'backend_started','native_loaded'},
'B_EMIT_ONLY_LOW_AND_HARNESS_DONE':{'backend_started'},
'B_EMIT_ONLY_COMPLETE':{'backend_started','native_loaded','protocol_executed'},
'B_SIM_READY':{'control_only','actual_banks','mock_matrix'},
'B_FAULT_BEFORE_ASSERT':{'tick','windows','group','steps','reset','status','firstStatus','state','bankReset','firstBankReset','terminalIssued','captured','written','ng','ownerGroupSequence'},
'B_BOUNDED_PROGRESS':{'tick','windows','group','steps','reset','status','firstStatus','state','bankReset','firstBankReset','terminalIssued','captured','written','ng','ownerGroupSequence'},
'B_WINDOW_ACCEPTED':{'ordinal','tick','ng','slot'},
'B_WINDOW_TERMINAL':{'ordinal','tick','group','issued','captured','written','status','mock_matrix'},
'B_PROTOCOL_BOUNDARY_ONLY':{'windows','drains','reads','ticks','numerical','full_block','matrix_endpoint_mock'},
'B_DIRECT_BEFORE_NATIVE_LOAD':{'protocol_only','re_elaboration'},
'B_DIRECT_DRIVER_RETURNED_PROTOCOL_ONLY':{'numerical'},
}
def parse(line):
 parts=line.strip().split(' ')
 if not parts or parts[0] not in FIELDS:return None
 out={}
 for word in parts[1:]:
  if word.count('=')!=1:return None
  k,v=word.split('=')
  if k in out:return None
  if v in ('true','false'):out[k]=v=='true'
  elif re.fullmatch('[0-9]{1,16}',v) and int(v)<2**53:out[k]=int(v)
  else:return None
 if set(out)!=FIELDS[parts[0]]:return None
 return dict(kind=parts[0],values=out)
def failure(line):
 prefix='B_EMIT_ONLY_FAILURE '
 if not line.startswith(prefix) or len(line.encode())>2048:return None
 try:
  def unique(items):
   d={}
   for k,v in items:
    if k in d:raise ValueError()
    d[k]=v
   return d
  d=json.loads(line[len(prefix):],object_pairs_hook=unique)
  if set(d)!={'schema','phase','exception_kind','frames','backend_started','native_loaded'}:return None
  if d['schema']!='B_EMIT_PHASE_FAILURE_V1' or d['phase'] not in {'ENTRY','VALIDATE_OUTPUT','ELABORATE','LOWER','TOP_INFO','HARNESS','SV','COMPLETE'}:return None
  if d['exception_kind'] not in {'ILLEGAL_ARGUMENT','ASSERTION_ERROR','OUT_OF_MEMORY','LINKAGE_ERROR','OTHER'}:return None
  if d['backend_started'] is not False or d['native_loaded'] is not False:return None
  if type(d['frames']) is not list or len(d['frames'])>8:return None
  allowed={'Public21DownOwnerEmitOnly.scala','Public21DownOwnerProtocolHarness.scala','Public21DownOwnerCrossWindowProtocolOnlySpec.scala','DirectJnaAdapter.scala','DirectBContextFactory.scala','Public21DownOwnerDirectDriver.scala'}
  for f in d['frames']:
   if type(f) is not dict or set(f)!={'source','line'} or f['source'] not in allowed or type(f['line']) is not int or not 0<f['line']<=1000000:return None
  return d
 except (ValueError,TypeError,KeyError):return None
def project(path,receipt,source_basenames=()):
 cap=32<<20;total=0;h=hashlib.sha256();records=[];progress=[];reasons=set();source_errors=[];source_frames=[];emit_failure=None
 allowed=set(source_basenames)
 if any(not re.fullmatch(r"[A-Za-z0-9_]+\.scala",x) for x in allowed):allowed=set()
 try:
  if not receipt.get('log_capture',{}).get('pipe_eof_observed') or not receipt['log_capture'].get('gzip_finalized'):raise ValueError()
  with path.open('rb') as f:compressed=hashlib.file_digest(f,'sha256').hexdigest()
  if compressed!=receipt['log_capture']['compressed_sha256']:raise ValueError()
  with gzip.open(path,'rb') as f:
   while True:
    line=f.readline(65537)
    if not line:break
    total+=len(line);h.update(line)
    if len(line)>65536 or total>cap:raise ValueError()
    text=line.decode('utf-8','replace').strip()
    finite_failure=failure(text)
    if finite_failure is not None:emit_failure=finite_failure
    row=parse(text)
    if row:
     if row['kind']=='B_BOUNDED_PROGRESS':progress=(progress+[row])[-6:]
     else:records=(records+[row])[-16:]
    if 'java.lang.OutOfMemoryError: Java heap space' in text:reasons.add('JAVA_HEAP_SPACE')
    match=re.search(r'(?:^|/)([A-Za-z0-9_]+\.scala):([0-9]{1,7}): error: (.*)$',text)
    if match:
     reasons.add('SCALA_COMPILE_ERROR');name,line,detail=match.groups()
     code='NOT_FOUND_TYPE' if 'not found: type ' in detail else 'NOT_FOUND_VALUE' if 'not found: value ' in detail else 'TYPE_MISMATCH' if 'type mismatch' in detail else 'OTHER'
     if name in allowed and 0<int(line)<=1000000:source_errors=(source_errors+[dict(source=name,line=int(line),code=code)])[-12:]
    frame=re.fullmatch(r'at [A-Za-z0-9_.$/]+\(([A-Za-z0-9_]+\.scala):([0-9]{1,7})\)',text)
    if frame and frame[1] in allowed and 0<int(frame[2])<=1000000:
     item=dict(source=frame[1],line=int(frame[2]))
     if item not in source_frames and len(source_frames)<8:source_frames.append(item)
    for marker,code in [('java.lang.NoClassDefFoundError','NO_CLASS_DEF_FOUND'),('java.lang.UnsatisfiedLinkError','UNSATISFIED_LINK'),('java.lang.IllegalArgumentException','ILLEGAL_ARGUMENT')]:
     if marker in text:reasons.add(code)
    if 'AssertionError' in text or 'TestFailedException' in text:reasons.add('TEST_ASSERTION_FAILURE')
    if 'requirement failed:' in text:reasons.add('REQUIREMENT_FAILURE')
  if total!=receipt['log_capture']['raw_bytes'] or h.hexdigest()!=receipt['log_capture']['raw_sha256']:raise ValueError()
  out={'schema':'PUBLIC21_B_FINITE_CLOSED_LOG_V1','status':'VERIFIED_CLOSED_PREFIX_PROJECTION','reasons':sorted(reasons),'source_errors':source_errors,'source_frames':source_frames,'emit_failure':emit_failure,'checkpoints':records,'latest_progress':progress,'numerical_pass':False}
  if len(json.dumps(out,separators=(',',':')).encode())>8192:raise ValueError()
  return out
 except Exception:return {'schema':'PUBLIC21_B_FINITE_CLOSED_LOG_V1','status':'UNAVAILABLE','numerical_pass':False}
