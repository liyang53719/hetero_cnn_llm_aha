"""Bounded post-run complete-capture C++/link errors, no execution cap changes."""
import gzip,hashlib,json,pathlib,re,time,zlib
from collections import deque
RAW_CAP=1024**3
COMPRESSED_CAP=150*1024**2
LINE_CAP=1024**2
CXX_ERROR=re.compile(br'(?:^|: )(?:fatal )?error:|undefined reference to|^collect2:|^(?:ValueError|FileNotFoundError|PermissionError|OSError|KeyError|TypeError):|^make(?:\[\d+\])?: \*\*\*')
SECRET=re.compile(r'(?i)(gh[pousr]_[A-Za-z0-9]|github_pat_|bearer\s|authorization\s*[:=]|\b(?:token|password|secret)\s*[=:])')
PATH=re.compile(r'(?:[A-Za-z]:[\\/]|/)[^\s\'\"<>():,;]*')
def sample(line,number):
 raw=line.rstrip(b'\r\n');entry={'line_number':number,'line_sha256':hashlib.sha256(raw).hexdigest(),'line_bytes':len(raw)}
 text=raw.decode('utf-8','replace')
 if SECRET.search(text) or any(ord(c)<32 for c in text):
  entry['text_status']='REDACTED_UNSAFE';return entry
 text=PATH.sub(lambda m:'<path>/'+re.split(r'[/\\]',m[0])[-1],text)
 # Only error line itself, never source snippets or arbitrary following log lines.
 text=text.encode('utf-8')[:320].decode('utf-8','ignore')
 entry.update(text_status='SANITIZED',error_text=text,text_truncated=len(text.encode())<len(raw))
 return entry

def full_build_errors(receipt,path):
 result={'status':'INCOMPLETE','scope':'CAPTURED_COMPILER_LINK_ERROR_DIAGNOSTICS_ONLY','samples':[]}
 c=receipt.get('log_capture',{})
 if not isinstance(c,dict):return dict(result,reason='CAPTURE_METADATA_INVALID')
 for k in ('raw_sha256','compressed_sha256'):
  if not isinstance(c.get(k),str) or not re.fullmatch('[0-9a-f]{64}',c[k]):return dict(result,reason='CAPTURE_METADATA_INVALID')
 for k,cap in [('raw_bytes',RAW_CAP),('compressed_bytes',COMPRESSED_CAP),('lines',RAW_CAP),('error_lines',RAW_CAP)]:
  if type(c.get(k))is not int or not 0<=c[k]<=cap:return dict(result,reason='CAPTURE_METADATA_INVALID')
 if c.get('pipe_eof_observed')is not True or c.get('gzip_finalized')is not True or c.get('capture_cap_hit')is not False:return dict(result,reason='CAPTURE_NOT_COMPLETE')
 p=pathlib.Path(path);started=time.monotonic();total=lines=errors=matched=0;digest=hashlib.sha256();first=[];last=deque(maxlen=4)
 try:
  before=p.lstat()
  if p.is_symlink() or not p.is_file() or before.st_size!=c['compressed_bytes']:raise ValueError('FILE_BOUND')
  compressed=hashlib.sha256();compressed_bytes=0
  with p.open('rb') as f:
   while True:
    chunk=f.read(65536)
    if not chunk:break
    compressed_bytes+=len(chunk)
    if compressed_bytes>COMPRESSED_CAP:raise ValueError('COMPRESSED_BOUND')
    compressed.update(chunk)
    if time.monotonic()-started>90:raise ValueError('SCAN_TIME_BOUND')
  if compressed.hexdigest()!=c['compressed_sha256']:raise ValueError('COMPRESSED_HASH_MISMATCH')
  with gzip.open(p,'rb') as f:
   while True:
    line=f.readline(LINE_CAP+1)
    if not line:break
    if len(line)>LINE_CAP:raise ValueError('LINE_BOUND')
    total+=len(line)
    if total>RAW_CAP:raise ValueError('RAW_BOUND')
    digest.update(line);lines+=1
    if line.startswith(b'%Error'):errors+=1
    if line.startswith(b'%Error') or CXX_ERROR.search(line):
     matched+=1;x=sample(line,lines)
     if len(first)<4:first.append(x)
     else:last.append(x)
    if time.monotonic()-started>90:raise ValueError('SCAN_TIME_BOUND')
  after=p.lstat()
  if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('FILE_CHANGED')
  if (total,lines,errors,digest.hexdigest())!=(c['raw_bytes'],c['lines'],c['error_lines'],c['raw_sha256']):raise ValueError('RAW_CENSUS_MISMATCH')
  samples=first+list(last)
  # Hash/count fields survive even when message detail needs an extra envelope bound.
  while len(json.dumps(samples,ensure_ascii=True).encode())>4096:
   for x in samples:
    if 'error_text'in x:x.pop('error_text');x['text_status']='ENVELOPE_REDACTED';x['text_truncated']=True;break
   else:raise ValueError('SAMPLE_ENVELOPE_BOUND')
  result.update(status='VERIFIED_COMPLETE_CAPTURE',reason='NONE',samples=samples,samples_truncated=matched>8)
 except (OSError,EOFError,ValueError,zlib.error) as e:
  allowed={'FILE_BOUND','COMPRESSED_BOUND','SCAN_TIME_BOUND','COMPRESSED_HASH_MISMATCH','LINE_BOUND','RAW_BOUND','FILE_CHANGED','RAW_CENSUS_MISMATCH','SAMPLE_ENVELOPE_BOUND'}
  result['reason']=str(e) if str(e)in allowed else 'UNREADABLE_CAPTURE'
 result.update(scanned_raw_bytes=total,scanned_lines=lines,scanned_error_lines=errors,matched_compiler_link_lines=matched,scanned_raw_sha256=digest.hexdigest())
 return result
