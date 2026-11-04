"""On failure only: typed role, trusted relative label, expected/actual hashes.
Never weaken the supervisor pin gate or print arbitrary paths/error strings.
"""
import hashlib,re
from pathlib import Path
ROLES={'REVIEWED_SOURCE','REVIEWED_TOOL','JDK_FILE','HOST_RUNTIME','JAR','JOB_IDENTITY','UNKNOWN_PIN'}
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def roles(pins,repo,jdk_home,host_pins=()):
 repo=Path(repo);jdk_home=Path(jdk_home);out={}
 for raw in pins:
  p=Path(raw);label=None
  if p.is_relative_to(repo):
   label=str(p.relative_to(repo));role='REVIEWED_SOURCE'if p.suffix=='.scala'else 'JAR'if p.suffix=='.jar'else 'REVIEWED_TOOL'
  elif p.is_relative_to(jdk_home):role='JDK_FILE';label=str(p.relative_to(jdk_home))
  elif raw in host_pins:role='HOST_RUNTIME'
  else:role='JOB_IDENTITY'
  out[raw]={'role':role,'label':label}
 return out
def pin_failures(receipt,pins,labels):
 result=[];seen=set()
 for error in receipt.get('errors',[])[:32]:
  if not isinstance(error,str):continue
  path=None;kind=None
  for prefix,code in [('ValueError: input pin mismatch ','HASH_MISMATCH'),('ValueError: missing file ','MISSING'),('ValueError: symlink path ','SYMLINK_REJECTED')]:
   if error.startswith(prefix):path=error[len(prefix):];kind=code;break
  if path not in pins or path in seen or len(result)>=8:continue
  expected=pins[path]
  if not isinstance(expected,str)or not re.fullmatch('[0-9a-f]{64}',expected):continue
  seen.add(path);p=Path(path);meta=labels.get(path,{});role=meta.get('role');role=role if role in ROLES else 'UNKNOWN_PIN';label=meta.get('label')
  if not isinstance(label,str)or Path(label).is_absolute()or '..'in Path(label).parts or not re.fullmatch(r'[A-Za-z0-9_./+-]{1,240}',label):label=None
  row=dict(role=role,pin_id=hashlib.sha256(path.encode()).hexdigest(),label=label,kind=kind,expected_sha256=expected,actual_sha256=None,actual_bytes=None)
  try:
   if any(q.is_symlink()for q in(p,*p.parents)):row['kind']='SYMLINK_REJECTED'
   elif p.is_file():row.update(actual_sha256=sha(p),actual_bytes=p.stat().st_size)
   else:row['kind']='MISSING'
  except OSError:row['kind']='READ_FAILED'
  result.append(row)
 return result
