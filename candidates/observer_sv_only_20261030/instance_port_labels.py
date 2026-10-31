"""Classify only four named-port labels on the fixed existing banks instance.
Nothing is deleted or normalized. Unknown syntax returns no exemptions. Signal
expressions, hierarchical/member accesses and every other occurrence remain live.
"""
import re
MODULE=b'TransposedDenseDownOwner'
TYPE=b'TransposedDownDenseBanks'
FIELDS=(b'identity',b'slot',b'ng',b'index')
LABELS={b'io_tiles_response_bits_key_'+f:b'banks_io_tiles_response_bits_key_'+f for f in FIELDS}
START=re.compile(rb'(?m)^[ \t]*TransposedDownDenseBanks[ \t]+banks[ \t]*\([ \t]*(?://(?P<info>[^\r\n]*))?\r?\n')
END=re.compile(rb'(?m)^[ \t]*\);[ \t]*(?://[^\r\n]*)?\r?\n')

REASONS=frozenset(('OTHER_MODULE','START_COUNT','START_NOT_UNCONDITIONAL','START_COMMENT_NOT_SOURCEINFO','END_MISSING','BLOCK_BYTES_CAP','LEXICAL_GAP','TOKEN_CAP','INSTANCE_PREFIX','NAMED_PORT_SYNTAX','DUPLICATE_PORT','PORT_CAP','EXPRESSION_FORBIDDEN_TOKEN','EXPRESSION_UNBALANCED','KEY_EXPRESSION_NOT_EXACT','LIST_SUFFIX','KEY_LABEL_COUNT','EXACT_FOUR_LABELS'))

def label_offsets(data,module,unconditional_code_starts,lex,sourceinfo=None,diagnostic=None):
 counts={'start_count':0,'block_bytes':0,'tokens':0,'ports':0,'key_labels':0}
 def done(reason,result=None):
  if diagnostic is not None:diagnostic(reason,dict(counts))
  return set() if result is None else result
 if module!=MODULE.decode():return done('OTHER_MODULE')
 candidates=list(START.finditer(data))
 counts['start_count']=len(candidates)
 if len(candidates)!=1:return done('START_COUNT')
 start=candidates[0];code=start.start()+len(start.group())-len(start.group().lstrip(b' \t'))
 if code not in unconditional_code_starts:return done('START_NOT_UNCONDITIONAL')
 if start['info'] is not None and (sourceinfo is None or sourceinfo.fullmatch(start['info']) is None):return done('START_COMMENT_NOT_SOURCEINFO')
 close=END.search(data,start.end())
 if close is None:return done('END_MISSING')
 counts['block_bytes']=close.end()-start.start()
 if counts['block_bytes']>2*1024**2:return done('BLOCK_BYTES_CAP')
 block=data[start.start():close.end()];items=[];pos=0
 for m in lex.finditer(block):
  if m.start()!=pos:return done('LEXICAL_GAP')
  pos=m.end()
  if m.lastgroup in ('space','line','block'):continue
  items.append((m.group(),start.start()+m.start(),m.lastgroup))
  counts['tokens']=len(items)
  if len(items)>200000:return done('TOKEN_CAP')
 if pos!=len(block)or [x[0]for x in items[:3]]!=[TYPE,b'banks',b'(']:return done('INSTANCE_PREFIX')
 i=3;seen=set();labels=set();ports=0
 while i<len(items):
  # Exhaustive named connection list; no positional/wildcard/parameter syntax.
  if i+3>=len(items)or items[i][0]!=b'.'or items[i+1][2]!='ident'or items[i+2][0]!=b'(':return done('NAMED_PORT_SYNTAX')
  name=items[i+1][0];offset=items[i+1][1]
  if name in seen:return done('DUPLICATE_PORT')
  seen.add(name);ports+=1
  counts['ports']=ports
  if ports>4096:return done('PORT_CAP')
  i+=3;begin=i;stack=[b')']
  while i<len(items)and stack:
   token,_,kind=items[i]
   if kind not in ('string','escape'):
    if token in (b'`',b';'):return done('EXPRESSION_FORBIDDEN_TOKEN')
    if token in (b'(',b'[',b'{'):stack.append({b'(':b')',b'[':b']',b'{':b'}'}[token])
    elif token in (b')',b']',b'}'):
     if token!=stack[-1]:return done('EXPRESSION_UNBALANCED')
     stack.pop()
     if not stack:break
   i+=1
  if stack or i>=len(items):return done('EXPRESSION_UNBALANCED')
  expr=items[begin:i]
  if name in LABELS:
   # Only label token is exempt; the actual connection signal remains scanned.
   if len(expr)!=1 or expr[0][2]!='ident'or expr[0][0]!=LABELS[name]:return done('KEY_EXPRESSION_NOT_EXACT')
   labels.add(offset);counts['key_labels']=len(labels)
  i+=1
  if i>=len(items):return done('LIST_SUFFIX')
  if items[i][0]==b',':i+=1;continue
  if [x[0]for x in items[i:]]!=[b')',b';']:return done('LIST_SUFFIX')
  return done('EXACT_FOUR_LABELS',labels) if len(labels)==4 else done('KEY_LABEL_COUNT')
 return done('LIST_SUFFIX')
