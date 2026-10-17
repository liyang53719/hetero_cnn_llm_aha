"""Conservative emitted packed routing checks; not a dynamic mutual exclusion proof."""
import re
from pathlib import Path
from check_structure import need

def check_packed(path):
 text=Path(path).read_text();ms=list(re.finditer(r'^  (module|extmodule) (\w+)\s*:',text,re.M));need(len({m[2] for m in ms})==len(ms),'duplicate module')
 blocks={m[2]:text[m.end():ms[i+1].start() if i+1<len(ms) else len(text)] for i,m in enumerate(ms)}
 def instance(body,kind):
  a=re.findall(r'^\s+inst (\w+) of '+re.escape(kind)+r'\s',body,re.M);need(len(a)==1,'unique '+kind);return a[0]
 kernel=blocks['QwenOwnerKernel'];core=instance(kernel,'Qwen2ContinuousBlock');matrix=instance(kernel,'MatrixPipelineService');dense=instance(kernel,'TransposedDenseDownOwner');legacy=instance(kernel,'LegacyMatrixStreamClient')
 client=instance(blocks['Qwen2ContinuousBlock'],'PackedAttentionStreamClient')
 need(sum(len(re.findall(r'^\s+inst \w+ of PackedAttentionStreamClient(?:_\d+)?\s',b,re.M)) for b in blocks.values())==1,'one packed client in module graph')
 def records(body):
  nodes={};connections=[];guards=[]
  for line in body.splitlines():
   indent=len(line)-len(line.lstrip())
   while guards and guards[-1][0]>=indent:guards.pop()
   m=re.match(r'\s*when (.+?)\s*:',line)
   if m:guards.append((indent,m[1]))
   m=re.match(r'\s*node (\w+) = (.+?)(?: @\[.*)?$',line)
   if m:need(m[1] not in nodes,'duplicate packed node');nodes[m[1]]=m[2]
   m=re.match(r'\s*connect ([\w.\[\]]+), (.+?)(?: @\[.*)?$',line)
   if m:connections.append((m[1],m[2],tuple(x[1] for x in guards)))
  return nodes,connections
 # Only these two actual memory address defaults are allowed. Each is
 # unconditionally overwritten by key before the read-address node uses it.
 invalidation_evidence=[]
 for name,body in [('QwenOwnerKernel',kernel),('Qwen2ContinuousBlock',blocks['Qwen2ContinuousBlock'])]:
  need(not re.search(r'^\s*(?:.*\bis invalid\b|(?:partialconnect|attach)\s)',body,re.M),'unknown assignment form')
  inv=re.findall(r'^\s*invalidate ([\w.\[\]]+)(?: @\[.*)?$',body,re.M)
  allowed={'_scoreOut_WIRE','_probOut_WIRE'} if name=='Qwen2ContinuousBlock' else set()
  need(set(inv)<=allowed and len(inv)==len(set(inv)),'unadmitted routing invalidation')
  for wire in inv:
   stem=wire.replace('_WIRE','');port=stem[1:];memory='scores' if port=='scoreOut' else 'probs'
   pattern=(r'^    invalidate '+wire+r' @\[.*\]\n'
    r'    when '+stem+r'_T : @\[.*\]\n'
    r'      connect '+wire+r', key @\[.*\]\n'
    r'      node '+stem+r'_T_1 = bits\('+wire+r', 9, 0\) @\[.*\]\n'
    r'      read mport '+port+r' = '+memory+r'\['+stem+r'_T_1\], clock @\[.*\]$')
   need(re.search(pattern,body,re.M),'memory address must be assigned within its read-enable branch')
   mentions=[line for line in body.splitlines() if re.search(r'\b'+wire+r'\b',line)]
   need(len(mentions)==4,'memory default unexpected alias or writer')
   invalidation_evidence.append(dict(module=name,wire=wire,read_enable_guard=stem+'_T',source_before_read='key',routing_target_alias=False))
 nodes,rows=records(kernel);select=core+'.io.packedQkActive';p=core+'.io.packedQk';mp=matrix+'.io.port'
 def resolve(x,seen=()):
  if x not in nodes:return x
  need(x not in seen,'node cycle');return resolve(nodes[x],seen+(x,))
 evidence=[]
 def ancestors(t):return [t[:m.start()] for m in re.finditer(r'[.\[]',t)]+[t]
 indexed={};descendant_last={}
 for i,row in enumerate(rows):
  indexed.setdefault(row[0],[]).append((i,row))
  for ancestor in ancestors(row[0]):descendant_last[ancestor]=i
 def overlap(a,b):return a==b or a.startswith(b+'.') or b.startswith(a+'.') or a.startswith(b+'[') or b.startswith(a+'[')
 def exact(target,value,guard=(),last=True):
  matches=[(i,r) for i,r in indexed.get(target,[]) if resolve(r[1])==value and tuple(resolve(g) for g in r[2])==guard]
  need(len(matches)==1,'packed connection '+target+' = '+value);i,row=matches[0]
  if last:need(max([descendant_last.get(target,-1)]+[indexed[a][-1][0] for a in ancestors(target) if a in indexed])==i,'later override '+target)
  evidence.append(dict(target=target,value=value,guards=list(guard),last_connect_checked=last))
 exact(core+'.io.packedQkStepsDrained',matrix+'.io.packedStepsDrained')
 for leaf in ['group.ready','step.ready','result.valid','done.valid']:
  exact(p+'.'+leaf,'and('+select+', '+mp+'.'+leaf+')')
 for leaf in ['result.bits.error','result.bits.last','result.bits.context','done.bits.error','done.bits.tag']+[f'result.bits.value[{i}][{j}]' for i in range(16) for j in range(256)]:exact(p+'.'+leaf,mp+'.'+leaf)
 for target in [legacy+'.io.port',dense+'.io.matrix']:
  for leaf in ['group.ready','step.ready','result.valid','done.valid']:exact(target+'.'+leaf,'UInt<1>(0h0)',(select,),True)
 for leaf in ['group.valid','group.bits.opcode','group.bits.sliceMask','group.bits.tag','step.valid','result.ready','done.ready']:
  exact(mp+'.'+leaf,p+'.'+leaf,(select,),True)
 for leaf in ['emit','finish','last','clear','context']+[f'a[{i}]' for i in range(16)]+[f'b[{i}]' for i in range(256)]:
  exact(mp+'.step.bits.'+leaf,p+'.step.bits.'+leaf,(select,),True)
 exact(mp+'.abort',p+'.abort',(select,),False) # QKV's existing final abort override remains
 exact(mp+'.group.bits.transposedDense','UInt<1>(0h0)',(select,),True)
 # groupSequence literal may have an explicit inferred width; require numerical zero only.
 seq=[r for r in rows if r[0]==mp+'.group.bits.groupSequence' and tuple(resolve(g) for g in r[2])==(select,)]
 need(len(seq)==1 and re.fullmatch(r'UInt<\d+>\(0h0\)',resolve(seq[0][1])),'packed groupSequence zero')
 exact(mp+'.group.bits.groupSequence',resolve(seq[0][1]),(select,),True)
 for target in [mp+'.seed.begin.valid',mp+'.seed.beat.valid',mp+'.seed.ack.ready',dense+'.io.matrix.seed.begin.ready',dense+'.io.matrix.seed.beat.ready',dense+'.io.matrix.seed.ack.valid']:
  exact(target,'UInt<1>(0h0)',(select,),True)
 core_nodes,core_rows=records(blocks['Qwen2ContinuousBlock'])
 for target,value in [('io.packedQkActive','packedOwned'),(client+'.io.stepsDrained','io.packedQkStepsDrained')]:
  selected=[r for r in core_rows if overlap(r[0],target)]
  need(selected==[(target,value,())],'unique final core packed connection '+target)
 for msg,line in [('packed QK lease belongs only to the original core',523),('QKV reduction and packed QK cannot share the Matrix lease',570)]:
  printf_rows=[x for x in kernel.splitlines() if re.match(r'\s*printf\(',x) and msg in x]
  need(len(printf_rows)==1,'missing/duplicate mutual exclusion diagnostic')
  location='QwenOwnerProtocol.scala '+str(line)+':'
  need(location in printf_rows[0],'assert diagnostic source location')
  assertion_rows=[x for x in kernel.splitlines() if re.match(r'\s*assert\(',x) and location in x]
  need(len(assertion_rows)==1,'diagnostic without same-source emitted assert')
 need('regreset packedOwned : UInt<1>' in blocks['Qwen2ContinuousBlock'],'owner state missing')
 return dict(scope='PACKED_QK_ROUTE_STRUCTURE_ONLY',packed_client_instances=1,connections=evidence,invalidation_evidence=invalidation_evidence,assertion_diagnostics_emitted=2,mutual_exclusion_dynamically_proved=False,source_bound_active_m_limit=128,capacity_tokens=1024,source_pins_required=True)
