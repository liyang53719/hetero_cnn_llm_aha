"""Source/negative controls, not a compiler or DUT. No Python assert dependency."""
from pathlib import Path
import hashlib,json,re
C=Path(__file__).resolve().parent
NAMES=['HostRuntimePrefixLeaseWiringV8.scala','QwenOwnerProtocol.scala','HostBlockTopV4.scala']
def need(x,m):
 if not x:raise ValueError(m)
def check(s):
 need('class HostRuntimeFfnStagedReceiptV17 extends Bundle' in s,'actual physical receipt type')
 need('val ffnStages=Reg(Vec(5,new HostRuntimeFfnStagedReceiptV17))' in s,'fixed five stage ledger')
 need('j.runtimeFfnPhase===0.U &&\n      j.activationBf16' in s,'DenseO cannot capture FFN')
 need('!j.public21Reduction' in s,'FFN cannot borrow public21')
 need('j.n===3584.U && j.k===1024.U' in s and 'j.n===1024.U && j.k===3584.U' in s,'runtime H1024 F3584')
 body=s.split('def ffnNormInputs',1)[1].split('def ffnInputs',1)[0]
 need('authority.postnormCommitValid' not in body and 'currentFault' not in body,'structural provenance cannot depend on reflected fault')
 need('postnormValid && postnormCurrent' in body and 'r.logicalJob.asUInt===authority.postnormJob.asUInt' in body,'actual postnorm body')
 need('r.result.outputCommitted && r.result.resourcesDrained' in body and 'r.result.outputAckBytes===r.job.writeBytes' in body,'real postnorm ACK')
 need('q.runtimeFfnPhase>=1.U && q.runtimeFfnPhase<=5.U && !ffnIssued(q.runtimeFfnPhase-1.U)' in s,'bounded nonreplay phase')
 need('g.io.acceptedTransaction===ffnDenseTransaction && g.io.physicalJob.bits.asUInt===ffnDenseExpected.asUInt' in s,'physical full job')
 need('ffnNormSource.job.tag<g.io.physicalJob.bits.tag' in s,'postnorm strict P<C')
 need('ffnSourceB.job.tag<g.io.physicalJob.bits.tag' in s,'up strict P<C')
 need('ffnSourceA.job.tag<g.io.physicalJob.bits.tag' in s,'gate/down strict P<C')
 need('elementInputA.job.tag<g.io.physicalJob.bits.tag' in s,'residual1 strict P<C')
 need('ffnDensePending:=g.io.physicalJob.bits;ffnDenseWaiting:=false.B;ffnDenseBusy:=true.B' in s,'physical debt retains actual acceptance')
 need('ffnDenseBusy && g.io.physicalDone.fire' in s,'real Dense terminal only')
 need('g.io.physicalDone.bits.usefulMacs===(ffnDensePending.m.pad(64)*ffnDensePending.n.pad(64)*ffnDensePending.k.pad(64))(63,0)' in s,'actual Dense MAC count')
 need('Mux(elementwiseSilu,6.U,Mux(elementwiseSigmoid,5.U,1.U))' in s,'exact SiLU scalar graph')
 need('Mux(elementwiseSigmoid || elementwiseSilu,2.U,1.U)' in s,'exact BF16 boundary count')
 need('elementwiseEvent.bits.accepted.asUInt===elementwiseExpected.asUInt' in s,'specialized accepted payload')
 need('r.counts.issued===leases(i).lease.expectedOperations.pad(33)' in s and 'r.resourcesDrained' in s,'actual service issues/debt')
 need('when((elementLogical && !isFfn(g.io.job.bits)) || denseOLogicalStart' in s,'keep residual/postnorm provenance through FFN')
 need('ffnReceiptValid && ffnCurrent(ffnReceipt) && !receiptFault' in s,'fault masks eligibility only')
 need('|| ffnDenseWaiting || ffnDenseBusy' in s and '!ffnDenseWaiting && !ffnDenseBusy' in s,'real pending included retirement')
 # No local numerical module or replacement scheduler was added in this metadata wiring.
 need('Module(new' not in s,'no additional numerical resource')
 clean=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
 stack=[]
 for c in clean:
  if c in '({[':stack.append(c)
  elif c in ')}]':need(bool(stack) and stack.pop()=='({['[')}]'.index(c)],'balanced Scala delimiters')
 need(not stack,'balanced Scala end')
 return True

def run():
 s=(C/'source'/NAMES[0]).read_text();check(s)
 mutations={
  'fault_reflection':('postnormValid && postnormCurrent && r.job.qkRole','postnormValid && postnormCurrent && authority.postnormCommitValid && r.job.qkRole'),
  'weak_physical_sequence':('ffnNormSource.job.tag<g.io.physicalJob.bits.tag','ffnNormSource.job.tag<=g.io.physicalJob.bits.tag'),
  'fake_public21':('!j.public21Reduction','true.B'),
  'repeat_phase':('!ffnIssued(q.runtimeFfnPhase-1.U)','true.B'),
  'short_ack':('r.result.outputAckBytes===r.job.writeBytes','r.result.outputAckBytes<=r.job.writeBytes'),
  'silu_round_wrong_count':('Mux(elementwiseSilu,6.U,Mux(elementwiseSigmoid,5.U,1.U))','Mux(elementwiseSilu,5.U,Mux(elementwiseSigmoid,5.U,1.U))'),
  'no_physical_retirement':('ffnDenseBusy && g.io.physicalDone.fire','ffnDenseBusy && g.io.physicalDone.valid')}
 rejected=[]
 for name,(old,new) in mutations.items():
  need(old in s,'mutation exists '+name)
  try:check(s.replace(old,new))
  except ValueError:rejected.append(name)
  else:raise ValueError('mutation escaped '+name)
 kernel=(C/'source'/NAMES[1]).read_text();top=(C/'source'/NAMES[2]).read_text()
 need('val runtimeFfnPhase=UInt(3.W)' in kernel and 'val public21Reduction=Bool()' in kernel,'private metadata fields')
 need('ordinaryJob.bits.gdnElementwiseOp===GdnElementwiseOp.SiluMul.U && ordinaryJob.bits.n===3584.U && ordinaryJob.bits.runtimeFfnPhase===3.U' in kernel,'real child route')
 need('cmd.io.runtimeFfnReceipt:=normLease.ffnReceipt' in top,'actual original parent receipt wire')
 for name in ['new SharedMemoryArbiter(17)','val moeLoop=Module(new UnifiedMoeRuntimeExpertLoopV4)','owner.io.job<>runtimeGuard.io.physicalJob']:
  need(name in top,'same original hardware route '+name)
 return {'status':'PASS_SOURCE_AND_NEGATIVE_CONTROLS_NOT_DUT','checks':31,'rejected_mutations':rejected,'sources':[{'path':str(C/'source'/n),'bytes':(C/'source'/n).stat().st_size,'sha256':hashlib.sha256((C/'source'/n).read_bytes()).hexdigest()} for n in NAMES],'hardware_elaboration':False,'full_m128_profiles_passed':0,'same_rtl_profiles_passed':0}
if __name__=='__main__':print(json.dumps(run(),indent=2))
