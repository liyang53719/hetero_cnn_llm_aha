"""One invocation of the unchanged lexical scanner per complete LF-ended module.

Equivalence boundary: digest starts in code; successful digest rejects final block
or string state. A final LF exits line-comment and escaped-identifier states, hence
successful LF-ended blocks finish in code. Exact exhaustive concatenation therefore
preserves the whole scanner's lexical state, including SourceInfo-at-EOF behavior.
The original scanner bytes, normalization grammar and hash updates are unchanged.
Unknown layout fails closed rather than switching to a permissive parser.
"""
import hashlib,pathlib,re,tempfile,types
START=re.compile(rb'module ([A-Za-z_][A-Za-z0-9_$]*)\(')
END=re.compile(rb'endmodule(?:\s|$)')

def inventory(path,scanner):
 path=pathlib.Path(path);before=path.stat()
 if path.is_symlink() or not path.is_file() or not 0<before.st_size<=512*1024**2:raise ValueError('SV input bound')
 whole=hashlib.sha256();raw_whole=hashlib.sha256();counts={};rows=[];name=None;block=None;size=0;total=0;names=set()
 try:
  with path.open('rb')as source:
   for line in iter(lambda:source.readline(65537),b''):
    if len(line)>65536:raise ValueError('module diagnostic line bound')
    total+=len(line);raw_whole.update(line);match=START.match(line)
    if match:
     if name is not None:raise ValueError('nested module diagnostic boundary')
     name=match[1].decode()
     if len(name)>128 or name in names:raise ValueError('module name bound or duplicate')
     names.add(name);block=tempfile.TemporaryFile();size=0;raw=hashlib.sha256()
    if name is None:raise ValueError('module inventory nonexhaustive gap')
    size+=len(line)
    if size>512*1024**2:raise ValueError('module bound')
    block.write(line);raw.update(line)
    if END.match(line):
     # This condition plus successful original digest is the terminal-code proof.
     if not line.endswith(b'\n'):raise ValueError('module terminal LF required for lexical continuity')
     block.seek(0);local_counts={};original_hashlib=scanner.hashlib
     class TeeHasher:
      def __init__(self):self.h=hashlib.sha256()
      def update(self,data):self.h.update(data);whole.update(data)
      def hexdigest(self):return self.h.hexdigest()
     try:
      scanner.hashlib=types.SimpleNamespace(sha256=TeeHasher)
      normalized=scanner.digest(block,local_counts)
     finally:scanner.hashlib=original_hashlib
     for k,v in local_counts.items():counts[k]=counts.get(k,0)+v
     rows.append(dict(module=name,bytes=size,raw_sha256=raw.hexdigest(),normalized_sha256=normalized,sourceinfo_count=local_counts.get('recognized_sourceinfo_comments',0)))
     block.close();block=None;name=None
     if len(rows)>2048:raise ValueError('module count bound')
  after=path.stat()
  if name is not None or not rows or total!=before.st_size or sum(r['bytes']for r in rows)!=total:raise ValueError('module inventory incomplete')
  if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('SV input mutated during observation')
  return dict(raw_sha256=raw_whole.hexdigest(),normalized_sha256=whole.hexdigest(),bytes=total,counts=counts,modules=rows)
 finally:
  if block is not None:block.close()
