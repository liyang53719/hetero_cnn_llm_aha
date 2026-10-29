"""Fixed-code diagnostics only: no log excerpts, environment, argv or exception text.
Signatures are observations, not a root-cause conclusion. Unknowns stay UNKNOWN.
"""
import gzip,hashlib,pathlib
SIGNATURES={
 'PYTHON_TIMEOUT_EXPIRED':b'subprocess.TimeoutExpired:',
 'PYTHON_CALLED_PROCESS_ERROR':b'subprocess.CalledProcessError:',
 'PYTHON_IMPORT_ERROR':b'ModuleNotFoundError:',
 'JVM_HEAP_RESERVATION_FAILURE':b'Could not reserve enough space',
 'JVM_NATIVE_ALLOCATION_FAILURE':b'Native memory allocation (malloc) failed',
 'JVM_INITIALIZATION_FAILURE':b'Error occurred during initialization of VM',
 'DISK_NO_SPACE':b'No space left on device',
 'JAVA_OUT_OF_MEMORY':b'java.lang.OutOfMemoryError',
 'SCALA_COMPILE_ERROR':b'error: ',
}
def log_diagnostics(path):
 p=pathlib.Path(path)
 if not p.is_file() or p.is_symlink():return {'log_status':'UNAVAILABLE','observed_signatures':[]}
 if p.stat().st_size>64*1024*1024:return {'log_status':'COMPRESSED_CAP_EXCEEDED','observed_signatures':[]}
 seen=set();total=0;tail=b'';digest=hashlib.sha256();status='COMPLETE'
 try:
  with gzip.open(p,'rb') as f:
   while True:
    chunk=f.read(min(65536,8*1024*1024-total+1))
    if not chunk:break
    total+=len(chunk)
    if total>8*1024*1024:status='RAW_PREFIX_CAP';break
    digest.update(chunk);window=tail+chunk
    for code,pattern in SIGNATURES.items():
     if pattern in window:seen.add(code)
    tail=window[-256:]
 except (OSError,EOFError):status='UNREADABLE'
 return {'log_status':status,'scanned_bytes':min(total,8*1024*1024),'scanned_sha256':digest.hexdigest(),'observed_signatures':sorted(seen)}
def stage_diagnostics(receipt,log):
 d=log_diagnostics(log);codes=[]
 if receipt.get('native_exit') not in (None,0):codes.append('CHILD_NONZERO_EXIT')
 if receipt.get('native_exit') is None:codes.append('CHILD_EXIT_UNAVAILABLE')
 if receipt.get('errors'):codes.append('SUPERVISOR_REPORTED_ERROR')
 if not receipt.get('cleanup_proof'):codes.append('CLEANUP_NOT_PROVEN')
 d['failure_codes']=codes
 d['root_cause']='NOT_ESTABLISHED' if codes else 'NO_FAILURE_RECORDED'
 return d

def compiler_errors(receipt,log):
 """Only exact compiler-owned .scala argv paths; no bootstrap/token stage logs.
 Capture at most 8 error groups / 4KiB. Header path becomes source basename.
 No traceback, command/environment dump, arbitrary log tail or secret-like text.
 """
 import re,json
 sources={str(x) for x in receipt.get('argv',[]) if isinstance(x,str) and x.endswith('.scala') and pathlib.Path(x).is_absolute()}
 p=pathlib.Path(log)
 if not sources or not p.is_file() or p.is_symlink() or p.stat().st_size>64*1024**2:return []
 try:
  with gzip.open(p,'rb') as f:raw=f.read(65537)
 except (OSError,EOFError):return []
 lines=raw[:65536].decode('utf-8','replace').splitlines();groups=[];budget=4096;i=0
 forbidden=re.compile(r'(?i)(gh[pousr]_[A-Za-z0-9]|github_pat_|bearer\s|authorization\s*[:=]|(?:token|password|secret)\s*[=:])')
 while i<len(lines) and len(groups)<8:
  m=re.fullmatch(r'(.+\.scala):(\d+): error: (.*)',lines[i]);i+=1
  if not m or m[1] not in sources:continue
  text=[m[3]]
  for line in lines[i:i+2]:
   if re.match(r'.+\.scala:\d+:',line):break
   text.append(line)
  body='\n'.join(text)
  if forbidden.search(body) or re.search(r'(?<![\w])/(?:[\w.-]+/)*[\w.-]+|[A-Za-z]:[\\/]',body) or len(body.encode('utf-8'))>1000 or any(ord(c)<32 and c not in '\n\t' for c in body):continue
  group={'source_basename':pathlib.Path(m[1]).name,'line':int(m[2]),'compiler_error':body}
  size=len(json.dumps(group,ensure_ascii=True).encode('utf-8'))+2
  if size>budget:break
  groups.append(group);budget-=size
 return groups
