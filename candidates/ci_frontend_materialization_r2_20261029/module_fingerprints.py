"""Diagnostic-only fingerprints of canonical emitter module blocks.
Full-file scanner remains acceptance gate. Unknown boundaries fail this diagnostic.
No generated SV is retained or uploaded; one bounded temporary module is removed.
"""
import tempfile,re,hashlib,pathlib,json,time,argparse
from sv_comment_only_identity import digest
START=re.compile(rb'module ([A-Za-z_][A-Za-z0-9_$]*)\(')
END=re.compile(rb'endmodule(?:\s|$)')
def fingerprints(path):
 rows=[];name=None;block=None;n=0
 try:
  with pathlib.Path(path).open('rb') as f:
   for line in iter(lambda:f.readline(65537),b''):
    if len(line)>65536:raise ValueError('module diagnostic line bound')
    m=START.match(line)
    if m:
     if name is not None:raise ValueError('nested module diagnostic boundary')
     name=m[1].decode()
     if len(name)>128:raise ValueError('module name bound')
     block=tempfile.TemporaryFile();n=0
    if name is not None:
     n+=len(line)
     if n>512*1024**2:raise ValueError('module bound')
     block.write(line)
    if END.match(line):
     if name is None:raise ValueError('endmodule diagnostic boundary')
     block.seek(0);raw=hashlib.file_digest(block,'sha256').hexdigest();block.seek(0);counts={};norm=digest(block,counts);rows.append({'module':name,'bytes':n,'raw_sha256':raw,'normalized_sha256':norm,'sourceinfo_count':counts.get('recognized_sourceinfo_comments',0)});block.close();block=None;name=None
     if len(rows)>2048:raise ValueError('module count bound')
  if name is not None or not rows or len({r['module'] for r in rows})!=len(rows) or sum(r['bytes'] for r in rows)!=pathlib.Path(path).stat().st_size:raise ValueError('module inventory incomplete')
  return rows
 finally:
  if block is not None:block.close()
if __name__=='__main__':
 D=pathlib.Path(__file__).resolve().parent;a=argparse.ArgumentParser();a.add_argument('--sv',type=pathlib.Path,required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args();p=v.sv;t=time.monotonic()
 if v.output.exists():raise ValueError('fresh baseline output required')
 with p.open('rb') as f:raw=hashlib.file_digest(f,'sha256').hexdigest()
 if raw!='c7e9d25c128004bdfc90405171eead8a4441ba20e52e829d95de4bf1122e5d96':raise ValueError('approved original')
 rows=fingerprints(p);r={'scope':'DIAGNOSTIC_MODULE_HASHES_NOT_ALTERNATIVE_ACCEPTANCE','raw_sha256':raw,'scanner_sha256':hashlib.sha256((D/'sv_comment_only_identity.py').read_bytes()).hexdigest(),'modules':rows,'seconds':time.monotonic()-t}
 with v.output.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
 print(len(rows),r['seconds'])
