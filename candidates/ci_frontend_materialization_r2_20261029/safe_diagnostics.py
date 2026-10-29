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
