"""Strict byte identity normalizing ONLY Chisel source-location directory prefixes.
Preserves all other comment bytes (including tool pragmas), whitespace, strings, escaped identifiers,
macros and directives. Conservative: noncomment formatting drift fails too.
Not an SV parser or numerical qualification. Stream bounded, no whole SV loading.
"""
import argparse,hashlib,pathlib,io,re
class Stream:
 def __init__(self,f):self.f=f;self.buf=b'';self.i=0
 def get(self):
  if self.i==len(self.buf):self.buf=self.f.read(65536);self.i=0
  if not self.buf:return None
  c=self.buf[self.i];self.i+=1;return c
 def peek(self):
  if self.i==len(self.buf):self.buf=self.f.read(65536);self.i=0
  return self.buf[self.i] if self.buf else None
def digest(f):
 s=Stream(f);h=hashlib.sha256();out=bytearray();state='code';escaped=False;comment=bytearray()
 def emit(c):
  out.append(c)
  if len(out)>=65536:h.update(out);out.clear()
 while True:
  c=s.get()
  if c is None:break
  if state=='line':
   if c in (10,13):
    body=bytes(comment)
    # Only Chisel/FIRRTL source-location line comments. Keep basename and
    # line:column; normalize directory prefix only. All other comments survive.
    loc=rb' ([A-Za-z0-9_./-]+\.scala) ([0-9]+:[0-9]+)'
    if re.fullmatch(rb' @\[(?:[A-Za-z0-9_./-]+\.scala [0-9]+:[0-9]+)(?: [A-Za-z0-9_./-]+\.scala [0-9]+:[0-9]+)*\]',body):
     body=re.sub(rb'([A-Za-z0-9_./-]+\.scala)',lambda m:m[1].split(b'/')[-1],body)
    for x in body:emit(x)
    comment.clear();emit(c);state='code'
   else:
    comment.append(c)
    if len(comment)>65536:raise ValueError('bounded line comment')
  elif state=='block':
   emit(c)
   if c==42 and s.peek()==47:emit(s.get());state='code'
  elif state=='identifier':
   emit(c)
   if c in b' \t\r\n\f':state='code'
  elif state=='string':
   emit(c)
   if escaped:escaped=False
   elif c==92:escaped=True
   elif c==34:state='code'
  elif c==47 and s.peek() in (47,42):
   n=s.get();emit(47);emit(n);state='line' if n==47 else 'block'
  else:
   emit(c)
   if c==34:state='string'
   elif c==92:state='identifier'
 if state in ('block','string'):raise ValueError('unterminated lexical token/comment')
 if state=='line':
  for x in comment:emit(x) # conservative EOF comment unchanged
 h.update(out);return h.hexdigest()
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('approved',type=pathlib.Path);a.add_argument('candidate',type=pathlib.Path);v=a.parse_args()
 with v.approved.open('rb') as x,v.candidate.open('rb') as y:old,new=digest(x),digest(y)
 if old!=new:raise SystemExit('FAIL_NONCOMMENT_BYTE_DRIFT_REQUIRES_AUDIT')
 print('PASS_COMMENT_ONLY_BYTE_IDENTITY_NOT_NUMERICAL '+old)
