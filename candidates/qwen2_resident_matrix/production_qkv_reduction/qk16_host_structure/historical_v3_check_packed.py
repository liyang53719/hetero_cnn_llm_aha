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
   m=re.match(r'\s*connect ([\w.]+), (.+?)(?: @\[.*)?$',line)
   if m:connections.append((m[1],m[2],tuple(x[1] for x in guards)))
  return nodes,connections
 # Unsupported invalidate/assignment forms on routing-critical modules fail closed.
 for body in [kernel,blocks['Qwen2ContinuousBlock']]:
  need(not re.search(r'^\s*(?:invalidate\s|.*\bis invalid\b|(?:partialconnect|attach)\s)',body,re.M),'unsupported assignment/invalidation in packed routing module')
 nodes,rows=records(kernel);select=core+'.io.packedQkActive';p=core+'.io.packedQk';mp=matrix+'.io.port'
 def resolve(x,seen=()):
  if x not in nodes:return x
  need(x not in seen,'node cycle');return resolve(nodes[x],seen+(x,))
 evidence=[]
 def overlap(a,b):return a==b or a.startswith(b+'.') or b.startswith(a+'.')
 def exact(target,value,guard=(),last=True):
  matches=[(i,r) for i,r in enumerate(rows) if r[0]==target and resolve(r[1])==value and tuple(resolve(g) for g in r[2])==guard]
  need(len(matches)==1,'packed connection '+target+' = '+value);i,row=matches[0]
  if last:need(not any(overlap(x[0],target) for x in rows[i+1:]),'later override '+target)
  evidence.append(dict(target=target,value=value,guards=list(guard),last_connect_checked=last))
 exact(core+'.io.packedQkStepsDrained',matrix+'.io.packedStepsDrained')
 for leaf in ['group.ready','step.ready','result.valid','done.valid']:
  exact(p+'.'+leaf,'and('+select+', '+mp+'.'+leaf+')')
 for leaf in ['result.bits','done.bits']:exact(p+'.'+leaf,mp+'.'+leaf)
 for target in [legacy+'.io.port',dense+'.io.matrix']:
  for leaf in ['group.ready','step.ready','result.valid','done.valid']:exact(target+'.'+leaf,'UInt<1>(0h0)',(select,),True)
 for leaf in ['group.valid','group.bits.opcode','group.bits.sliceMask','group.bits.tag','step.valid','step.bits','result.ready','done.ready']:
  exact(mp+'.'+leaf,p+'.'+leaf,(select,),True)
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
 return dict(scope='PACKED_QK_ROUTE_STRUCTURE_ONLY',packed_client_instances=1,connections=evidence,assertion_diagnostics_emitted=2,mutual_exclusion_dynamically_proved=False,source_bound_active_m_limit=128,capacity_tokens=1024,source_pins_required=True)
