"""Classify only four named-port labels on the fixed existing banks instance.
Nothing is deleted or normalized. Unknown syntax returns no exemptions. Signal
expressions, hierarchical/member accesses and every other occurrence remain live.
"""
import re
MODULE=b'TransposedDenseDownOwner'
TYPE=b'TransposedDownDenseBanks'
FIELDS=(b'identity',b'slot',b'ng',b'index')
LABELS={b'io_tiles_response_bits_key_'+f:b'banks_io_tiles_response_bits_key_'+f for f in FIELDS}
START=re.compile(rb'(?m)^[ \t]*TransposedDownDenseBanks[ \t]+banks[ \t]*\([ \t]*\r?\n')
END=re.compile(rb'(?m)^[ \t]*\);[ \t]*(?://[^\r\n]*)?\r?\n')

def label_offsets(data,module,unconditional_code_starts,lex):
 if module!=MODULE.decode():return set()
 candidates=list(START.finditer(data))
 if len(candidates)!=1:return set()
 start=candidates[0];code=start.start()+len(start.group())-len(start.group().lstrip(b' \t'))
 if code not in unconditional_code_starts:return set()
 close=END.search(data,start.end())
 if close is None or close.end()-start.start()>2*1024**2:return set()
 block=data[start.start():close.end()];items=[];pos=0
 for m in lex.finditer(block):
  if m.start()!=pos:return set()
  pos=m.end()
  if m.lastgroup in ('space','line','block'):continue
  items.append((m.group(),start.start()+m.start(),m.lastgroup))
  if len(items)>200000:return set()
 if pos!=len(block)or [x[0]for x in items[:3]]!=[TYPE,b'banks',b'(']:return set()
 i=3;seen=set();labels=set();ports=0
 while i<len(items):
  # Exhaustive named connection list; no positional/wildcard/parameter syntax.
  if i+3>=len(items)or items[i][0]!=b'.'or items[i+1][2]!='ident'or items[i+2][0]!=b'(':return set()
  name=items[i+1][0];offset=items[i+1][1]
  if name in seen:return set()
  seen.add(name);ports+=1
  if ports>4096:return set()
  i+=3;begin=i;stack=[b')']
  while i<len(items)and stack:
   token,_,kind=items[i]
   if kind not in ('string','escape'):
    if token in (b'`',b';'):return set()
    if token in (b'(',b'[',b'{'):stack.append({b'(':b')',b'[':b']',b'{':b'}'}[token])
    elif token in (b')',b']',b'}'):
     if token!=stack[-1]:return set()
     stack.pop()
     if not stack:break
   i+=1
  if stack or i>=len(items):return set()
  expr=items[begin:i]
  if name in LABELS:
   # Only label token is exempt; the actual connection signal remains scanned.
   if len(expr)!=1 or expr[0][2]!='ident'or expr[0][0]!=LABELS[name]:return set()
   labels.add(offset)
  i+=1
  if i>=len(items):return set()
  if items[i][0]==b',':i+=1;continue
  if [x[0]for x in items[i:]]!=[b')',b';']:return set()
  return labels if len(labels)==4 else set()
 return set()
