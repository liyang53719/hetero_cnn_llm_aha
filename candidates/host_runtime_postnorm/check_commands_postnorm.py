"""Commands postNorm source-contract/mutation audit only; not compiler/RTL/DUT evidence."""
from pathlib import Path
import difflib,hashlib,json,re
C=Path(__file__).resolve().parent
BASE=C.parent/'host_runtime_output/source/HostBlockCommandsV4.scala'
SOURCE=C/'source/HostBlockCommandsV4.scala'
BASE_SHA='1ae8d1e3e9f11ad302897105e9be75f0d1f301e28b16f5dd7fcf6b63ea7458e5'
def need(v,m):
 if not v:raise ValueError(m)
def block(s,a,b):
 need(s.count(a)==1,'unique start '+a);need(b in s.split(a,1)[1],'end '+b)
 return s.split(a,1)[1].split(b,1)[0]
REQUIRED=[
'val runtimePostnormReceipt=Input(Valid(new HostRuntimePostnormStagedReceiptV16))',
'val postnormDonePending=RegInit(false.B)',
'val boundPostnormHost=Reg(new HostCommandLaunchV4);val boundPostnormTransaction=Reg(UInt(64.W))',
'val boundPostnormGamma=Reg(new DecodedTensor);val boundPostnormOutput=Reg(new DecodedTensor)',
'val postnormPhysicalReceipt=Reg(new HostRuntimePostnormStagedReceiptV16)',
'val postnormCurrent=runtimeAccepted && runtimeTransaction===postnormTransaction',
'cfg.asUInt===postnormHost.asUInt',
'val moeGraphFields=postnormCurrent && postnormCommitValid',
'val rnResidual=txResidual1Valid && sameAllocation(a,txResidual1Tensor) && readwrite(a)',
'val rnAttentionResidual=attentionBlockValid(4) && sameAllocation(a,attentionBlockValues(4))',
'val rnPostProducer=enableRuntimeOutput.B && rnRole===1.U && !txPostNormValid &&',
'!postnormDonePending && !postnormCommitValid && rnCold && rnGeneration===0.U &&',
'!rnCheckpointValid && rnSameContext && rnResidual &&',
'Mux(runtimeGdnProfile,true.B,rnAttentionResidual)',
'val rnGammaIdentity= !sourceValid(rnWeightRole) || sameAllocation(b,sourceTensor(rnWeightRole))',
'val rnLive=live(a) && live(b) && readonly(b) && sourceAllowed(b,rnWeightRole) && rnGammaIdentity &&',
'boundPostnormHost:=cfg;boundPostnormTransaction:=runtimeTransaction',
'boundPostnormGamma:=b;boundPostnormOutput:=d',
'bound.qkRole:=Mux(rnRole===1.U,3.U,0.U)',
'bound.cold:=rnCold;bound.expectedGeneration:=rnGeneration;bound.currentGeneration:=0.U',
'val runtimePostnormIdentity=runtimeAccepted && runtimeTransaction===boundPostnormTransaction &&',
'cfg.asUInt===boundPostnormHost.asUInt && bound.qkRole===3.U && bound.cold &&',
'bound.expectedGeneration===0.U && bound.currentGeneration===0.U &&',
'boundInputTensor.asUInt===tensors(0).asUInt && boundPostnormGamma.asUInt===tensors(1).asUInt &&',
'boundPostnormOutput.asUInt===tensors(2).asUInt && bound.a===boundInputTensor.address &&',
'bound.b===boundPostnormGamma.address && bound.dst===boundPostnormOutput.address &&',
'bound.writeBytes===boundPostnormOutput.payloadBytes',
'val postnormExpectedPhysical=WireDefault(bound);postnormExpectedPhysical.tag:=postnormProof.job.tag',
'val runtimePostnormProof=io.runtimePostnormReceipt.valid &&',
'postnormProof.transactionId===runtimeTransaction && postnormProof.host.asUInt===cfg.asUInt &&',
'postnormProof.logicalJob.asUInt===bound.asUInt &&',
'postnormProof.job.asUInt===postnormExpectedPhysical.asUInt && postnormProof.job.tag=/="hffffffff".U &&',
'postnormProof.result.tag===postnormProof.job.tag && postnormProof.result.status===Status.Ok.U &&',
'postnormProof.result.writeBytes===bound.writeBytes && postnormProof.result.outputCommitted &&',
'postnormProof.result.outputAckBytes===bound.writeBytes && postnormProof.result.resourcesDrained &&',
'postnormProof.residual.transactionId===runtimeTransaction && postnormProof.residual.host.asUInt===cfg.asUInt &&',
'postnormProof.residual.job.kind===QwenOwnerKind.GdnElementwise.U &&',
'postnormProof.residual.job.gdnElementwiseOp===GdnElementwiseOp.Add.U &&',
'postnormProof.residual.job.dst===bound.a && postnormProof.residual.job.m===bound.m &&',
'postnormProof.residual.job.n===bound.n && postnormProof.residual.job.writeBytes===bound.writeBytes &&',
'postnormProof.residual.job.tag<postnormProof.job.tag && postnormProof.residual.job.tag=/="hffffffff".U &&',
'postnormProof.residual.result.tag===postnormProof.residual.job.tag &&',
'postnormProof.residual.result.status===Status.Ok.U && postnormProof.residual.result.writeBytes===bound.writeBytes',
'(!boundRuntimePrefix || (runtimePostnormIdentity && runtimePostnormProof &&',
'postnormProof.result.cycles===io.done.bits.cycles && !io.runtimeAuthority.currentFault))',
'postnormCommitValid:= !boundRuntimePrefix;postnormDonePending:=boundRuntimePrefix;postnormJob:=bound',
'when(boundRuntimePrefix){postnormPhysicalReceipt:=postnormProof}',
'val runtimePostnormPendingExact=postnormDonePending && postnormCurrent && runtimePostnormIdentity &&',
'postnormJob.asUInt===bound.asUInt && postnormResidual.asUInt===boundInputTensor.asUInt &&',
'postnormOutputTensor.asUInt===boundPostnormOutput.asUInt && postnormResult.tag===bound.tag &&',
'postnormResult.status===Status.Ok.U && postnormResult.writeBytes===bound.writeBytes &&',
'runtimePostnormProof && postnormPhysicalReceipt.asUInt===postnormProof.asUInt',
'when(postnormCommitValid && !postnormCurrent)',
'def badRuntimePostnormAck(r:QwenOwnerResult):Bool=boundRuntimePrefix && boundPostnorm &&',
'(!runtimePostnormIdentity || !runtimePostnormProof || postnormProof.result.cycles=/=r.cycles ||',
'.elsewhen(r.writeBytes=/=bound.writeBytes || badRuntimeGqaMacs(r) || badRuntimePostnormAck(r)){fail(Status.Protocol.U)}',
'when(io.runtimeAuthority.currentFault || (boundPostnorm && !runtimePostnormPendingExact))',
'bound.kind===QwenOwnerKind.GdnRmsNorm.U && bound.qkRole===0.U && !boundPostnorm',
'bound.kind===QwenOwnerKind.GdnRmsNorm.U && bound.qkRole===3.U && boundPostnorm',
'(!boundRuntimePrefix || runtimePostnormIdentity)',
'io.runtimeAuthority.postnormCommitValid:=postnormCurrent && postnormCommitValid && !io.runtimeAuthority.currentFault',
'.elsewhen(envelopeAccepted && !(l.profileId===0.U && officialBf16.B))'
]
PRESERVED=[
('    when(!headerOK)','  when(state===fetch'),
('  when(state===fetch','  // Original parser remains'),
('    val rn=policy(1);','    val rnCheckpointValid='),
('    val rnFresh=','    // First three real GDN'),
('    // First three real GDN','    val runtimePrefix='),
('    val nativeWeight=','    val nativeQkNorm='),
('    val nativeQkNorm=','    val attentionAppend='),
('    val attentionAppend=','    val nativeAttention='),
('    val nativeAttention=','    // Runtime RMS validation'),
('      // Qwen2 numerical BF16-in-FP32','      when(runtimeNorm){'),
('      when(runtimeConv){','  // Epoch + 1'),
('    .elsewhen(boundMoePhase){','  if(enableResidentFfn){when(state===complete'),
('  io.job.valid:=','  if(enableResidentFfn){'),
]
def contract(s):
 for x in REQUIRED:need(x in s,'required '+x)
 for a,b in PRESERVED:need(block(s,a,b)==block(BASE.read_text(),a,b),'preserved '+a)
 done_handlers=block(s,'  // Width is explicit before multiplication.','  when(io.completion.fire)')
 need(done_handlers.count(' || badRuntimePostnormAck(r)')==2,'both actual done handlers reject bad physical proof')
 helper='''  // A known-bad physical proof cannot first expose a successful completion.
  // This only changes registered parser state/status after the real done fire.
  def badRuntimePostnormAck(r:QwenOwnerResult):Bool=boundRuntimePrefix && boundPostnorm &&
    (!runtimePostnormIdentity || !runtimePostnormProof || postnormProof.result.cycles=/=r.cycles ||
      io.runtimeAuthority.currentFault)
'''
 need(helper in done_handlers,'exact new done predicate')
 need(done_handlers.replace(helper,'').replace(' || badRuntimePostnormAck(r)','')==block(BASE.read_text(),'  // Width is explicit before multiplication.','  when(io.completion.fire)'),'all other original done handlers unchanged')
 done=block(s,'  when(ordinaryPostnormAck && !residentFault){','  val runtimePostnormPendingExact=')
 need('postnormCommitValid:=true.B' not in done,'runtime done must not publish FFN input')
 fault=block(s,'\n  when(io.runtimeAuthority.currentFault){','  when(postnormCommitValid && !postnormCurrent)')
 need('postnormCommitValid:=' not in fault,'late fault must preserve held MoE structural intent')
 pub=block(s,'    .elsewhen(boundRuntimePrefix){','    .elsewhen(boundMoePhase){')
 need(pub.index('!runtimePostnormPendingExact')<pub.index('postnormCommitValid:=true.B'),'completion veto before publication')
 for x in ('attentionCacheValid:=','attentionCache:=','attentionContext:=','attentionLength:=','attentionGeneration:=','stateValid:=','currentGeneration:=','currentStateAddress:=','currentHistoryAddress:='):
  need(x not in pub,'no final root '+x)
 need(s.count('Module(new')==BASE.read_text().count('Module(new'),'no new modules')
 clean=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
 stack=[];pairs={')':'(',']':'[','}':'{'}
 for c in clean:
  if c in '([{':stack.append(c)
  elif c in ')]}':need(bool(stack) and stack.pop()==pairs[c],'balanced Scala delimiters')
 need(not stack,'closed Scala delimiters')
 return len(REQUIRED)+len(PRESERVED)+14

def main():
 need(hashlib.sha256(BASE.read_bytes()).hexdigest()==BASE_SHA,'frozen latest output source SHA')
 s=SOURCE.read_text();checks=contract(s)
 # Remove each independent defense, then require source-contract rejection.
 for x in REQUIRED:
  try:contract(s.replace(x,'/* deliberately removed postnorm defense */'))
  except ValueError:pass
  else:raise ValueError('escaped mutation '+x)
 result=dict(status='PASS_SOURCE_CONTRACT_MUTATIONS_ONLY_NOT_SCALA_OR_DUT',required_defenses=len(REQUIRED),preserved_regions=len(PRESERVED),mutation_rejections=len(REQUIRED),checks=checks,source=dict(path=str(SOURCE),bytes=SOURCE.stat().st_size,sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest()),base=dict(path=str(BASE),bytes=BASE.stat().st_size,sha256=BASE_SHA),new_modules=0,private_port_only=True,full_m128_passes=0,rtl_five_profile_passes=0)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
