"""Bounded nonblocking lossless gzip capture; raw SHA and diagnostic census."""
import os,hashlib,zlib,re
from collections import Counter
class Capture:
 def __init__(self,pipe,out,raw_cap,compressed_cap):
  self.pipe=pipe;self.out=out;self.raw_cap=raw_cap;self.compressed_cap=compressed_cap
  os.set_blocking(pipe.fileno(),False);self.compressor=zlib.compressobj(1,zlib.DEFLATED,31)
  self.raw_hash=hashlib.sha256();self.compressed_hash=hashlib.sha256();self.raw_bytes=0;self.compressed_bytes=0;self.lines=0;self.pending=b'';self.warnings=Counter();self.errors=0;self.eof=False;self.finished=False;self.capped=False
 def write(self,b):
  if b:self.out.write(b);self.out.flush();self.compressed_hash.update(b);self.compressed_bytes+=len(b)
  if self.compressed_bytes>self.compressed_cap:self.capped=True;raise ValueError('compressed log cap')
 def count_line(self,line):
  self.lines+=1
  m=re.match(br'%Warning-([^: ]+)',line)
  if m:self.warnings[m.group(1).decode('ascii','replace')]+=1
  if line.startswith(b'%Error'):self.errors+=1
 def drain(self):
  if self.capped or self.finished:return False
  got=False
  for _ in range(16):
   try:b=os.read(self.pipe.fileno(),65536)
   except BlockingIOError:break
   if not b:self.eof=True;break
   got=True;self.raw_bytes+=len(b);self.raw_hash.update(b)
   lines=(self.pending+b).split(b'\n');self.pending=lines.pop()
   for line in lines:self.count_line(line)
   self.write(self.compressor.compress(b))
   if len(self.pending)>1024*1024:self.capped=True;raise ValueError('diagnostic line1MiB cap')
   if self.raw_bytes>self.raw_cap:self.capped=True;raise ValueError('uncompressed log cap')
  return got
 def finish(self):
  if self.finished:return
  self.finished=True
  if self.pending:self.count_line(self.pending);self.pending=b''
  self.write(self.compressor.flush(zlib.Z_FINISH))
 def receipt(self):
  return {'format':'gzip-lossless','raw_bytes':self.raw_bytes,'compressed_bytes':self.compressed_bytes,'raw_sha256':self.raw_hash.hexdigest(),'compressed_sha256':self.compressed_hash.hexdigest(),'lines':self.lines,'warning_histogram':dict(self.warnings),'error_lines':self.errors,'pipe_eof_observed':self.eof,'gzip_finalized':self.finished,'capture_cap_hit':self.capped,'scope':'Exact captured prefix; full process completion additionally requires native exit and normal supervisor result. Raw cap overshoot bounded by one64KiB read.'}
