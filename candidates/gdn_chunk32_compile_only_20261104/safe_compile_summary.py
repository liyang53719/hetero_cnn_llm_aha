"""Finite typed diagnostics. Never emit raw messages, snippets or absolute paths."""
import gzip,hashlib,re
from pathlib import Path
PHASES={'JDK_INVENTORY','HOST_INVENTORY','DEPENDENCIES','SCALA_COMPILE'}
SIGNATURES={'JAVA_OUT_OF_MEMORY':b'java.lang.OutOfMemoryError','JVM_HEAP_RESERVATION':b'Could not reserve enough space','DISK_NO_SPACE':b'No space left on device','SCALA_COMPILE_ERROR':b'error: '}
def error_kind(message):
 if message.startswith('type mismatch'):return 'TYPE_MISMATCH'
 if message.startswith('not found:'):return 'SYMBOL_NOT_FOUND'
 if ' is not a member of ' in message:return 'MEMBER_NOT_FOUND'
 if ' is already defined' in message:return 'DUPLICATE_SYMBOL'
 if 'ambiguous' in message:return 'AMBIGUOUS_REFERENCE'
 if 'not enough arguments' in message:return 'MISSING_ARGUMENT'
 if 'too many arguments' in message:return 'EXCESS_ARGUMENT'
 if 'type arguments' in message:return 'TYPE_ARGUMENT_ERROR'
 if 'expected but' in message or 'unclosed' in message:return 'SYNTAX_ERROR'
 return 'OTHER_SCALA_ERROR'
def safe_sources(source_map):
 out={}
 for actual,relative in source_map.items():
  if not isinstance(actual,str)or not Path(actual).is_absolute()or not isinstance(relative,str):continue
  p=Path(relative)
  if p.is_absolute() or '..' in p.parts or not re.fullmatch(r'[A-Za-z0-9_./-]{1,240}\.scala',relative):continue
  out[actual]=relative
 return out
def scan(log,source_map):
 p=Path(log);mapped=safe_sources(source_map);rows=[];seen=set();total=0;digest=hashlib.sha256();status='COMPLETE';signatures=set();tail=b''
 if not p.is_file()or p.is_symlink():return dict(log_status='UNAVAILABLE',compiler_errors=[],observed_signatures=[])
 if p.stat().st_size>8<<20:return dict(log_status='COMPRESSED_CAP',compiler_errors=[],observed_signatures=[])
 try:
  with gzip.open(p,'rb')as f:
   pending=b''
   while total<=8<<20:
    data=f.read(min(65536,(8<<20)-total+1))
    if not data:break
    total+=len(data)
    if total>8<<20:status='RAW_SCAN_CAP';break
    digest.update(data);window=tail+data
    for code,pattern in SIGNATURES.items():
     if pattern in window:signatures.add(code)
    tail=window[-128:];pending+=data
    lines=pending.split(b'\n');pending=lines.pop()
    for raw in lines:
     if len(raw)>4096:continue
     m=re.fullmatch(r'(.+\.scala):(\d{1,8})(?::(\d{1,6}))?: error: (.*)',raw.decode('utf-8','replace'))
     if not m or m[1]not in mapped or not 1<=int(m[2])<=10000000:continue
     row=(mapped[m[1]],int(m[2]),int(m[3])if m[3]else None,error_kind(m[4]))
     if row not in seen and len(rows)<8:
      seen.add(row);rows.append(dict(source=row[0],line=row[1],column=row[2],kind=row[3]))
    # Bound malformed no-newline log lines without retaining their contents.
    if len(pending)>4096:pending=b'!OVERSIZED_LINE!'
 except (OSError,EOFError):status='UNREADABLE'
 return dict(log_status=status,scanned_bytes=min(total,8<<20),scanned_sha256=digest.hexdigest(),compiler_errors=rows,observed_signatures=sorted(signatures))
def summarize_stage(phase,receipt,log,source_map):
 if phase not in PHASES:phase='SCALA_COMPILE'
 result=scan(log,source_map);codes=[]
 for text in receipt.get('errors',[])[:32]:
  if not isinstance(text,str):continue
  code='SUPERVISOR_ERROR'
  for fragment,label in [('wall cap','WALL_CAP'),('CPU cap','CPU_CAP'),('RSS cap','RSS_CAP'),('memory gate','MEMORY_GATE'),('disk gate','DISK_GATE'),('disk reserve','DISK_RESERVE'),('log cap','LOG_CAP'),('log EOF','LOG_EOF'),('pin','PIN_DRIFT'),('alias','ALIAS_DRIFT'),('cleanup','CLEANUP_ERROR')]:
   if fragment in text:code=label;break
  if code not in codes:codes.append(code)
 result.update(phase=phase,native_exit=receipt.get('native_exit')if type(receipt.get('native_exit'))is int else None,supervisor_codes=codes,cleanup_proven=receipt.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' if isinstance(receipt.get('cleanup_proof'),dict)else False,root_cause='NOT_ESTABLISHED')
 return result
