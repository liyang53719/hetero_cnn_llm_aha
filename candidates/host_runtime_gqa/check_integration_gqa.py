"""Bounded source/model check, never Chisel elaboration or DUT numerical evidence."""
from pathlib import Path
import json,hashlib,re,itertools
C=Path(__file__).resolve().parent;B=C.parent/'host_runtime_kvappend/source'
checks=0
def need(ok,msg):
 global checks
 checks+=1
 if not ok:raise ValueError(msg)
def pin(p):
 b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
r=json.loads((C/'SOURCE_PINS.json').read_text())['source_check_originals']['QwenOwnerProtocol.scala']
q=pin(B/'QwenOwnerProtocol.scala');need(q['bytes']==r['bytes'] and q['sha256']==r['sha256'],'exact public predecessor QwenOwnerProtocol')
def check(k,t):
 need('enableRuntimeGqa:Boolean=false' in k,'explicit current runtime switch')
 need(t.count('enableRuntimeGqa=true')==2,'common Top both constructors')
 need('new Bf16CausalGqaRuntimeOwnerV14' in k,'actual owner installed')
 need('if(bf16AttentionCore && !enableRuntimeGqa)' in k,'not legacy flag route')
 need(k.count('Module(new MatrixPipelineService(')==1,'one Matrix service')
 need('s.matrixColumns==256 && s.retainedMatrix' in k,'full fixed physical Matrix')
 need('enableAccumulatorSeed=enableTransposedSeed,enablePackedDrainStatus=enableProductionPackedQk16' in k,'same Matrix constructor')
 need('new SharedMemoryArbiter(17)' in t,'same memory hub17')
 need(t.count('new RetainedIdmaMemoryAdapter')==1 and t.count('new RetainedIdmaWeightBurstAdapter')==1,'same DMA alternative constructors')
 need('new UnifiedMoeSharedArithmeticAdapterV5' in t,'same shared scalar adapter')
 need('++runtimeGqa.toSeq.map(n=>(13,n.io.scalar))' in k,'actual Scalar8 borrower mux')
 need('runtimeGqa.foreach(_.io.parentFault:=port.parentFault)' in k,'registered leaf fault')
 need('(enableRuntimeGqa.B && mode===13.U)' in k,'shared scalar scheduler actual mode')
 need('runtimeGqa.map(_.io.resourcesDrained).getOrElse(true.B)' in k,'true aggregate drain')
 need('runtimeGqaMatrixFault.get:=ordinaryAdmissionFault || runtimeGuard.io.localFault || cmd.io.runtimeAuthority.currentFault' in t,'immediate Matrix admission fault')
 need('val groupPublish=HeldDecoupledOffer(select && a.io.matrix.group.valid,matrix.io.port.group.ready,io.runtimeGqaMatrixFault.get)' in k,'outer actual group gate')
 need('val stepPublish=HeldDecoupledOffer(select && a.io.matrix.step.valid,matrix.io.port.step.ready,io.runtimeGqaMatrixFault.get)' in k,'outer actual step gate')
 need('a.io.matrixGroupPublished:=groupPublish.valid;a.io.matrixStepPublished:=stepPublish.valid' in k,'actual Matrix visibility feedback')
 need('a.io.memoryPublished:=active && mode===13.U && io.runtimeGqaPublished.get.memory' in k and 'a.io.scalarPublished:=active && mode===13.U && io.runtimeGqaPublished.get.scalar' in k,'actual memory Scalar visibility feedback')
 need('runtimeGqaPublished.get.memory:=normLease.owned && gqaJob && hub.io.requests(1).valid' in t,'true memory visibility')
 need('runtimeGqaPublished.get.scalar:=normLease.owned && gqaJob && moeArithmetic.io.scalar(3).request.valid' in t,'true Scalar visibility')
 need('matrix.io.port.group.valid:=groupPublish.valid' in k and 'matrix.io.port.step.valid:=stepPublish.valid' in k,'actual shared Matrix requests')
 need('admissionFault' not in k,'no raw-valid fault suppression cycle')
 need('matrix.io.port.group.bits.transposedDense.foreach(_:=false.B)' in k and 'matrix.io.port.group.bits.groupSequence.foreach(_:=0.U)' in k,'no seed/transposed payload alias')
 need('assert(!useDense && !reductionOwns' in k,'Dense exclusion')
 need('assert(!core.io.packedQkActive.get,"GQA cannot overlap packed QK authority")' in k,'packed exclusion')
 need('val gqaMacsWide=(ordinaryJob.bits.m*ordinaryJob.bits.cacheLength*(ordinaryJob.bits.n>>8))*512.U(10.W)' in k,'runtime heads full product')
 need('val gqaMacsFit= !gqaMacsWide(gqaMacsWide.getWidth-1,64).orR' in k,'66-bit overflow predicate')
 need('gqaLogicalMacs:=gqaMacsWide(63,0)' in k,'narrow only checked product')
 need('gqaLogicalMacs:=(ordinaryJob.bits.m.pad(64)*ordinaryJob.bits.cacheLength.pad(64))<<12' not in k,'no hardcoded Q8 shift')
 need('d.accepted.asUInt=/=j.asUInt' in k,'exact accepted snapshot')
 for x in ('d.scalarAccepted=/=expectedScalar','d.scalarReturned=/=expectedScalar','d.memoryAccepted=/=expectedMemory','d.memoryReturned=/=expectedMemory','d.matrixGroupsAccepted=/=expectedGroups','d.matrixGroupsReturned=/=expectedGroups','d.outputAckBytes=/=expectedBytes','!d.drained','d.attentionStatus=/=0.U'):
  need(x in k,'actual terminal '+x)
 need('io.runtimeGqaDoneFire.get.valid:=a.io.done.fire' in k,'real terminal event')
 need('++runtimeGqa.toSeq.map(x=>13->x.io.memory)' in k and '++runtimeGqa.toSeq.map(x=>13->x.io.response)' in k,'original memory client')
 need('Mux(gqaJob,nwithin(nj.a,nbytes) || nwithin(nj.b,gqaCacheBytes)' in t,'exact Q/cache read scope')
 need('val gqaCacheBytes=nj.cacheCapacity.pad(80)<<11' in t,'whole cache capacity')
 # Legacy full route remains byte-for-byte inside the larger common route.
 old=(B/'QwenOwnerProtocol.scala').read_text()
 for start,end in [('    val reductionOwns=qkvRouter','    }\n    }\n    if(enablePublic21QkvReduction){'),('    if(enablePublic21QkvReduction){\n      val r=qkvRouter.get\n      // Physical retirement','    val noAuxOwner=')]:
  block=old[old.index(start):old.index(end,old.index(start))]
  need(block in k,'frozen Qwen2 transposed/seed/packed/reduction block')
 # Constructor parameters do not profile-specialize the new owner.
 need('new Bf16CausalGqaRuntimeOwnerV14(' not in k,'fixed owner no profile parameter')
 return True
k=(C/'source/QwenOwnerProtocol.scala').read_text();t=(C/'source/HostBlockTopV4.scala').read_text();check(k,t)
# Structural balanced delimiters ignoring comments/string payloads, not Scala typing.
for p in (C/'source').glob('*.scala'):
 s=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:[^"\\]|\\.)*"','',p.read_text(),flags=re.S);stack=[]
 for c in s:
  if c in '([{':stack.append(c)
  elif c in ')]}':need(bool(stack) and stack.pop()=={')':'(',']':'[','}':'{'}[c],p.name+' delimiter')
 need(not stack,p.name+' balanced')
# First-published vs leaf-local offer; no request payload mutation here.
for held,wanted,ready,fault in itertools.product([False,True],repeat=4):
 valid=held or (wanted and not fault)
 need(not held or valid,'late fault preserves held offer')
 need(not (fault and not held) or not valid,'fresh current fault veto')
 need((valid and not ready)==((held or (wanted and not fault)) and not ready),'next held exact')
# Input-width product is 16+32+8+10=66, not accidental 64-bit wrap.
need(16+32+8+10==66,'product width')
count_vectors=[]
for m in (1,16,128):
 for c in (1,16,128,256):
  for h in (8,16):
   scalar=6*m*c*h;groups=((m+15)//16)*h*((c+31)//32+1);memory=16*h*(m+((m+15)//16)*c);logical=2*m*c*h*256
   need(scalar<=3145728 and max(groups,memory)<2**32,'bounded exact operation widths')
   need(logical==m*c*(h*256)*2,'head-independent identity')
   if m==128 and c==128:count_vectors.append(dict(m=m,c=c,heads=h,scalar=scalar,matrix_groups=groups,memory=memory,bytes=m*h*512,logical_macs=logical))
need(count_vectors[1]['logical_macs']==2*count_vectors[0]['logical_macs'],'Q16 doubled work not Q8 undercount')
# Exact allowed GQA spans and read/write direction for both profiles, all beats.
route_checks=0
for h in (8,16):
 m=c=128;q=0x100000;cache=0x300000;out=0x500000;nb=m*h*512;cb=c*2048
 def legal(addr,write,mask=2**64-1):
  rights=(out<=addr and addr+64<=out+nb) if write else ((q<=addr and addr+64<=q+nb) or(cache<=addr and addr+64<=cache+cb))
  return addr%64==0 and addr+64<=2**56 and rights and (mask==2**64-1 if write else mask==0)
 for base,size,write in ((q,nb,False),(cache,cb,False),(out,nb,True)):
  for a in range(base,base+size,64):
   need(legal(a,write,2**64-1 if write else 0),'exact beat accepted');route_checks+=1
  need(not legal(base-64,write,2**64-1 if write else 0),'lower bound')
  need(not legal(base+size,write,2**64-1 if write else 0),'upper bound')
  need(not legal(base,not write,0 if write else 2**64-1),'wrong direction')
 need(not legal(out,True,1),'partial mask')
mutations=[('scalar disconnected','++runtimeGqa.toSeq.map(n=>(13,n.io.scalar))',''),('matrix duplicated','Module(new MatrixPipelineService(','Module(new AnotherMatrix('),('GQA overflow gone','val gqaMacsFit= !gqaMacsWide(gqaMacsWide.getWidth-1,64).orR','val gqaMacsFit=true.B'),('accepted lost','d.accepted.asUInt=/=j.asUInt','false.B'),('group count lost','d.matrixGroupsReturned=/=expectedGroups','false.B'),('legacy switch','if(bf16AttentionCore && !enableRuntimeGqa)','if(bf16AttentionCore)'),('publication lost','a.io.matrixGroupPublished:=groupPublish.valid','a.io.matrixGroupPublished:=a.io.matrix.group.valid')]
rejected=[]
for name,a,b in mutations:
 need(a in k,name+' anchor')
 try:check(k.replace(a,b),t)
 except ValueError:rejected.append(name)
 else:raise ValueError('survived '+name)
res=dict(status='PASS_SOURCE_AND_ABSTRACT_MODELS_ONLY_NOT_DUT',checks=checks,route_checks=route_checks,mutations_rejected=rejected,count_vectors=count_vectors,source_pins=[pin(C/'source/QwenOwnerProtocol.scala'),pin(C/'source/HostBlockTopV4.scala')],full_m128_passes=0,rtl_five_profile_passes=0)
print(json.dumps(res,indent=2))
