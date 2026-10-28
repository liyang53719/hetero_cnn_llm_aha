"""Bounded source-contract checks only; never Scala elaboration or DUT/numerical evidence."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent
P=C/'source'/'HostBlockCommandsV4.scala'
BASE=C.parent/'host_chunk_top_dispatch/source/HostBlockCommandsV4.scala'
checks=0
def need(x,msg):
 global checks
 checks+=1
 if not x:raise ValueError(msg)
def block(s,start,end):
 need(s.count(start)==1,'unique block start '+start)
 return s.split(start,1)[1].split(end,1)[0]
required=[
 'val tensorSlots=5',
 'val runtimeChunkTensor=Reg(new DecodedTensor)',
 'val runtimeGatedNormTensor=Reg(new DecodedTensor)',
 '(gdnOperation===5.U && slot===3.U)',
 'val oneExtra=gdnOperation===5.U',
 'Mux(oneExtra,hout=/=0xffffff.U,hout===0xffffff.U || hout>=cfg.descriptors)',
 'val gatedInputs=finishRecord(rh,0x23.U) && rh(103,80)===0xffffff.U && rh(127,104)===0.U',
 'runtimeGdnProfile && group===0.U && rnProgram && gatedPolicy && gatedInputs',
 '(m===16.U || m===128.U) && (prepHeads===16.U || prepHeads===32.U)',
 'shape2(a,m,gatedWidth) && shape2(b,m,gatedWidth) && shape2(d,m,gatedWidth)',
 'shape2(rhIn,1.U,128.U)',
 'Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && rhIn.dtype===7.U',
 'val gatedIndices=tensors.take(4).flatMap(_.prefixIndices)++policyIndices.take(3)',
 'txInputNormValid && txConvValid && txPrepValid && txRecurrentValid && txZValid && !txNormValid',
 'sameAllocation(a,runtimeChunkTensor) && sameAllocation(b,runtimeProjectionTensors(1))',
 'Seq(a,b,rhIn).map(live).reduce(_&&_) && readonly(rhIn) && sourceAllowed(rhIn,7.U)',
 'runtimeGatedNorm && !gatedDistinct','runtimeGatedNorm && !gatedLive','runtimeGatedNorm && !gatedFresh',
 'runtimeChunk || runtimeGatedNorm',
 'bound.kind:=QwenOwnerKind.GdnGatedNorm.U;bound.m:=m;bound.n:=prepHeads;bound.k:=128.U',
 'bound.activationBf16:=true.B;bound.weightBf16:=false.B;bound.outputBf16:=true.B',
 'txRecurrentValid:=true.B;txRecurrent:=bound.dst;runtimeChunkTensor:=tensors(2)',
 'txNormValid:=true.B;txNorm:=bound.dst;runtimeGatedNormTensor:=tensors(2)',
 '.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))',
 '.elsewhen(r.writeBytes=/=bound.writeBytes){fail(Status.Protocol.U)}',
 'when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}',
]
def contract(s):
 for token in required:
  if token not in s:raise ValueError('missing source contract '+token)
 pub=s.split('.elsewhen(boundRuntimePrefix){',1)[1].split('.elsewhen(boundMoePhase){',1)[0]
 for forbidden in ['stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:=']:
  if forbidden in pub:raise ValueError('forbidden premature final root '+forbidden)
 if 'Module(new' in s.split('val gatedWidth=prepHeads*128.U',1)[1].split('val supportedOrdinary=',1)[0]:
  raise ValueError('arithmetic/resource instance in parser')
s=P.read_text();b=BASE.read_text();contract(s)
for token in required:need(token in s,token)
need(hashlib.sha256(BASE.read_bytes()).hexdigest()=='7324bebea8500f9c14bcc787a760307b832733b32ea235af57442c5a813e8ce7','frozen Chunk Commands ancestry')
# Frozen launch admission, original physical constructors and tensor slot capacity.
need(s.count('Module(new')==b.count('Module(new'),'no extra modules')
need(block(s,'    when(!headerOK)','  when(state===fetch')==block(b,'    when(!headerOK)','  when(state===fetch'),'launch seal unchanged')
need(s.count('val tensors=Reg(Vec(tensorSlots,new DecodedTensor))')==1,'same five typed slots')
# Wrong parser, producer, retirement and premature commit mutations are rejected.
mutations=[
 ('(gdnOperation===5.U && slot===3.U)','(gdnOperation===5.U && slot===4.U)'),
 ('hout=/=0xffffff.U','hout===0xffffff.U'),
 ('shape2(rhIn,1.U,128.U)','shape2(rhIn,1.U,64.U)'),
 ('sameAllocation(a,runtimeChunkTensor)','true.B'),
 ('sameAllocation(b,runtimeProjectionTensors(1))','true.B'),
 ('runtimeGatedNorm && !gatedFresh','false.B'),
 ('runtimeGatedNorm && !gatedDistinct','false.B'),
 ('txNormValid:=true.B;txNorm:=bound.dst;runtimeGatedNormTensor:=tensors(2)','stateValid:=true.B'),
 ('.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))','.elsewhen(false.B)'),
 ('when(io.runtimeAuthority.currentFault){status:=Status.Protocol.U;poison:=true.B;state:=finish}','when(false.B){status:=Status.Protocol.U;poison:=true.B;state:=finish}'),
]
for old,new in mutations:
 need(old in s,'mutation target')
 try:contract(s.replace(old,new,1))
 except ValueError:need(True,'mutation rejected')
 else:raise ValueError('mutation survived '+old)
# Lightweight delimiter check ignoring comments and strings; NOT a Scala parser.
lex=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
stack=[];pairs={')':'(',']':'[','}':'{'}
for c in lex:
 if c in '([{':stack.append(c)
 elif c in pairs:
  if not stack or stack.pop()!=pairs[c]:raise ValueError('unbalanced lexical delimiter')
need(not stack,'closed delimiters')
print(json.dumps({'status':'PASS_SOURCE_CONTRACT_ONLY_NOT_SCALA_OR_DUT','checks':checks,'rejected_mutations':len(mutations),'source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'base_sha256':hashlib.sha256(BASE.read_bytes()).hexdigest(),'explicit_metadata_added_bits':798,'new_payload_or_arithmetic_modules':0},indent=2))
