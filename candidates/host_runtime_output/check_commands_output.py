"""Source contract + mutation checks only. Never a Scala/Chisel/RTL/DUT substitute."""
from pathlib import Path
import argparse,hashlib,json,re,difflib
C=Path(__file__).resolve().parent
B=C.parent/'host_runtime_gqa/source/HostBlockCommandsV4.scala'
P=C/'source/HostBlockCommandsV4.scala'
parser=argparse.ArgumentParser()
parser.add_argument('--guard-source',type=Path,required=True)
G=parser.parse_args().guard_source
s=P.read_text();base=B.read_text();checks=0

def need(v,msg):
 global checks
 checks+=1
 if not v:raise ValueError(msg)
def block(v,a,b):return v.split(a,1)[1].split(b,1)[0]
required=[
'enableRuntimeOutput:Boolean=false',
'require(!enableRuntimeOutput || enableRuntimeGqa',
'val runtimeAttentionOutputPolicy=RegInit(false.B)',
'extendedProjection:=false.B;attentionBlockMatrix:=false.B;runtimeAttentionOutputPolicy:=false.B;state:=tensorIssue',
'runtimeNormCommand && policySlot===1.U && r.data(7,0)===0x24.U)',
'runtimeAttentionOutputPolicy:=true.B',
'(enableRuntimeOutput.B && runtimeGdnProfile && r.data(71,64)===9.U)',
'val outputWidth=Mux(runtimeGdnProfile,gatedWidth,runtimeProfile.attentionHeads.pad(16)<<8)',
'val outputRows=Mux(runtimeGdnProfile,m===16.U || m===128.U,m===128.U)',
'val outputContext=txCold && txGeneration===0.U && !rnCheckpointValid && sourceValid(0)',
'sourceTensor(0).dims(0)===m && sourceTensor(0).dims(1)===runtimeNormHidden',
'policy(0)(127,56)===(m.pad(72)|(runtimeNormHidden.pad(72)<<16)|(outputWidth.pad(72)<<32))',
'rd(79,72)===0.U && rd(80) && !rd(81) && rdRole===3.U && rd(87,85)===0.U',
'roMatrix && roPolicy && outputRows && shape2(a,m,outputWidth)',
'shape2(b,outputWidth,runtimeNormHidden) && shape2(d,m,runtimeNormHidden)',
'val roLive=outputContext && !txOValid && live(a) && live(b) && readonly(b)',
'sourceAllowed(b,Mux(runtimeGdnProfile,11.U,8.U))',
'txNormValid && sameAllocation(a,runtimeGatedNormTensor)',
'attentionBlockValid(2) && sameAllocation(a,attentionBlockValues(2))',
'finishRecord(rn,0x21.U) && rn(63,56)===3.U && rn(71,64)===9.U',
'rn(79,72)===0.U && rnCold && !rn(81) && rnRole===0.U',
'cp(63,56)===3.U && attentionOp===7.U && attentionBase===0.U && attentionCount===128.U',
'cp(115,108)===0.U && attentionBlockRole<=1.U && cp(127,119)===0.U',
'attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U',
'attentionExpectedGeneration===0.U && attentionQueryStart===0.U',
'val reWidth=Mux(attentionBlockRole===0.U,outputWidth,runtimeNormHidden)',
'val runtimeAttentionElement=enableRuntimeOutput.B && runtimeAttentionProfile && runtimeAttentionOutputPolicy',
'val rePending=outputContext && pendingAttentionValid && pendingGqaValid && pendingAttentionCold',
'pendingAttentionCount===128.U && pendingAttentionLength===128.U && pendingAttentionCache.dims(1)===128.U',
'val reGateLive=rePending && attentionBlockValid(1) && !attentionBlockValid(2)',
'sameAllocation(a,attentionBlockValues(1)) && sameAllocation(b,pendingAttentionContext) && live(a) && live(b)',
'val reResidualLive=outputContext && txOValid && !txResidual1Valid',
'sameAllocation(a,sourceTensor(0)) && sameAllocation(b,runtimeOTensor) && live(a) && live(b)',
'val runtimeElementwise=runtimeGdnResidual || runtimeAttentionElement',
'Mux(attentionBlockRole===0.U,reGateLive,rePending && reResidualLive)',
'runtimeGqa || runtimeDenseO || runtimeElementwise',
'.elsewhen(runtimeDenseO && !rdDistinct){fail(Status.Malformed.U)}',
'.elsewhen(runtimeDenseO && !roLive){fail(Status.Dependency.U)}',
'.elsewhen(runtimeDenseO && !rdFresh){fail(Status.Permission.U)}',
'.elsewhen(runtimeElementwise && !reDistinct){fail(Status.Malformed.U)}',
'.elsewhen(runtimeElementwise && !reLive){fail(Status.Dependency.U)}',
'.elsewhen(runtimeElementwise && !rdFresh){fail(Status.Permission.U)}',
'bound.kind:=QwenOwnerKind.Dense.U;bound.m:=m;bound.n:=runtimeNormHidden;bound.k:=outputWidth',
'bound.qkRole:=3.U // private common discriminator',
'bound.kind:=QwenOwnerKind.GdnElementwise.U;bound.m:=m;bound.n:=d.dims(1);bound.k:=d.dims(1)',
'bound.gdnElementwiseOp:=Mux(runtimeAttentionElement && attentionBlockRole===0.U,2.U,0.U)',
'bound.qkRole:=Mux(rnRole===1.U,3.U,0.U)',
'bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U',
'bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B',
'bound.materializeDenseOutput:=officialMaterializeDense && dense && !runtimeDenseProjection && !runtimeDenseO',
'val downActivationBf16=nativeProjection || gdnProjection || attentionBlockDense || runtimeDenseProjection || runtimeDenseO',
'.elsewhen(bound.kind===QwenOwnerKind.GdnElementwise.U)',
'attentionBlockValues(2):=tensors(2);attentionBlockValid(2):=true.B',
'.elsewhen(bound.kind===QwenOwnerKind.Dense.U && bound.qkRole===3.U)',
'txOValid:=true.B;txO:=bound.dst;runtimeOTensor:=tensors(2)',
'.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))'
]
def contract(v):
 for x in required:
  if x not in v:raise ValueError('missing '+x)
 pub=block(v,'.elsewhen(boundRuntimePrefix){','.elsewhen(boundMoePhase){')
 for x in ('attentionCacheValid:=','attentionCache:=','attentionContext:=','attentionLength:=','attentionGeneration:=','stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:='):
  if x in pub:raise ValueError('premature global publication '+x)
 if pub.index('when(io.runtimeAuthority.currentFault)')>pub.index('txOValid:=true.B'):raise ValueError('late-fault bypass')
 if pub.index('Dense.U && bound.qkRole===3.U')>pub.index('.elsewhen(bound.kind===QwenOwnerKind.Dense.U){'):raise ValueError('O captured as QKV')
 if pub.index('GdnElementwise.U')>pub.index('.elsewhen(policy(1)(84,82)===0.U)'):raise ValueError('element captured as RMS')
contract(s)
need(hashlib.sha256(B.read_bytes()).hexdigest()=='c2715a549acbb04e1def9811e22ddefeb10af6362fdf3789ace4f2ab322c7fc8','frozen base SHA')
for x in required:need(x in s,x)
for a,b in [
 ('    when(!headerOK)','  when(state===fetch'),
 ('    .elsewhen(qkCommandPolicy){','    .elsewhen(runtimeProjectionCommand){'),
 ('    .elsewhen(runtimeProjectionCommand){','    .elsewhen(runtimeNormCommand){'),
 ('    val nativeQkNorm=','    val attentionAppend='),
 ('    val attentionAppend=','    val nativeAttention='),
 ('    val runtimeNorm=','    // First three real GDN'),
 ('    // First three real GDN','    // Real output continuation:'),
 ('  val ordinaryPostnormAck=','  when(io.completion.fire)'),
 ('    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete'),
 ('  io.runtimeAuthority.accepted:=','  when(io.result.fire)'),
 ('    val nativeWeight=','    val nativeQkNorm='),
 ('      when(rope){','    if(enableTransposedDown){')]:
 # New insertion is immediately before prior runtimeQkNorm; compare the entire existing block before it.
 if b=='    // Real output continuation:':need(block(s,a,b)==block(base,a,'    val runtimeQkNorm='),'preserved '+a)
 else:need(block(s,a,b)==block(base,a,b),'preserved '+a)
need(s.count('Module(new')==base.count('Module(new'),'same existing metadata modules')
need(s.count('val reader=Module(new Record128Reader)')==1,'one original record reader')
need(s.count('val tensor=Module(new TypedTensorReader)')==1,'one original tensor reader')
clean=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S);stack=[];pairs={')':'(',']':'[','}':'{'}
for c in clean:
 if c in '([{':stack.append(c)
 elif c in ')]}':need(bool(stack) and stack.pop()==pairs[c],'balanced Scala delimiters')
need(not stack,'closed Scala delimiters')
# Existing sole Guard remains the source of full-identity and physical-order evidence.
r=json.loads((C/'SOURCE_PINS.json').read_text())['original_guard']
need(len(G.read_bytes())==r['bytes'] and hashlib.sha256(G.read_bytes()).hexdigest()==r['sha256'],'exact external Guard pin')
g=G.read_text()
for x in ('io.job.bits.asUInt===io.authority.ownerJob.asUInt','io.authority.transaction===heldTransaction','io.authority.launch.asUInt===heldLaunch.asUInt','val nextSequence=RegInit(0.U(32.W))','io.physicalJob.bits.tag:=heldPhysicalSequence','io.retired.bits.logicalJob:=heldJob;io.retired.bits.logicalResult:=heldResult'):
 need(x in g,'existing actual Guard '+x)
mutations=[
 ('officialMaterializeDense && dense && !runtimeDenseProjection && !runtimeDenseO','officialMaterializeDense && dense'),
 ('runtimeAttentionOutputPolicy:=false.B;state:=tensorIssue','state:=tensorIssue'),
 ('outputRows=Mux(runtimeGdnProfile,m===16.U || m===128.U,m===128.U)','outputRows=true.B'),
 ('val outputContext=txCold && txGeneration===0.U && !rnCheckpointValid && sourceValid(0)','val outputContext=true.B'),
 ('rdRole===3.U','rdRole<=3.U'),
 ('shape2(b,outputWidth,runtimeNormHidden)','shape2(b,runtimeNormHidden,outputWidth)'),
 ('txNormValid && sameAllocation(a,runtimeGatedNormTensor)','live(a)'),
 ('attentionBlockValid(2) && sameAllocation(a,attentionBlockValues(2))','live(a)'),
 ('attentionBlockRole<=1.U','attentionBlockRole<=3.U'),
 ('pendingAttentionValid && pendingGqaValid','pendingAttentionValid'),
 ('attentionBlockValid(1) && !attentionBlockValid(2)','true.B'),
 ('sameAllocation(a,attentionBlockValues(1))','live(a)'),
 ('sameAllocation(b,pendingAttentionContext)','live(b)'),
 ('val reResidualLive=outputContext && txOValid && !txResidual1Valid','val reResidualLive=outputContext'),
 ('sameAllocation(a,sourceTensor(0))','live(a)'),
 ('sameAllocation(b,runtimeOTensor)','live(b)'),
 ('runtimeDenseO && !roLive','runtimeDenseO && false.B'),
 ('runtimeElementwise && !rdFresh','runtimeElementwise && false.B'),
 ('bound.qkRole:=3.U // private common discriminator','bound.qkRole:=0.U // private common discriminator'),
 ('attentionBlockRole===0.U,2.U,0.U','attentionBlockRole===0.U,1.U,0.U'),
 ('txOValid:=true.B;txO:=bound.dst;runtimeOTensor:=tensors(2)','stateValid:=true.B;txOValid:=true.B;txO:=bound.dst;runtimeOTensor:=tensors(2)'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)')]
for a,b in mutations:
 need(a in s,'mutation location '+a)
 try:contract(s.replace(a,b))
 except ValueError:continue
 raise ValueError('escaped mutation '+a)
result=dict(status='SOURCE_CONTRACT_ONLY_NOT_SCALA_OR_DUT',checks=checks,mutations_rejected=len(mutations),source_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),base_sha256=hashlib.sha256(B.read_bytes()).hexdigest(),guard_path=str(G),guard_sha256=hashlib.sha256(G.read_bytes()).hexdigest(),guard_unchanged=True,new_metadata_modules=0,launch_seal_preserved=True,full_m128_passes=0,rtl_five_profile_passes=0)
print(json.dumps(result,indent=2))
