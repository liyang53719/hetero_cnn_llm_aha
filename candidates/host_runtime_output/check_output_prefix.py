#!/usr/bin/env python3
"""Bounded source checks only. Not Scala, Chisel, RTL or numeric DUT execution."""
from pathlib import Path
import hashlib,json,re
D=Path(__file__).resolve().parent/'source'
files={n:(D/n).read_text() for n in ('HostRuntimePrefixLeaseWiringV8.scala','UnifiedMoeSharedArithmeticProtocolV5.scala','UnifiedMoeSharedArithmeticAdapterV5.scala')}
checks={
'HostRuntimePrefixLeaseWiringV8.scala':{
 'actual_receipt_fields':['class HostRuntimeOutputStagedReceiptV15','val host=new HostCommandLaunchV4','val transactionId=UInt(64.W)','val job=new QwenOwnerJob','val result=new QwenOwnerResult'],
 'no_qkv_alias':['g.io.physicalJob.bits.qkRole=/=3.U && projectionProfile'],
 'actual_hidden_receipt':['tailPhysicalSuccess && normShape && logical.qkRole===0.U && leaseEventSubmitted && outputCountsExact','r.host:=host;r.transactionId:=transaction;r.job:=retainedPhysical;r.result:=g.io.physicalDone.bits'],
 'actual_gqa_receipt':['tailPhysicalSuccess && gqaShape && gqaEvent.valid && gqaTerminalExact','gqaGateJob:=normalizedJobs(0);gqaGateResult:=normalizedResults(0)'],
 'opaque_gate_provenance':['p.asUInt===gqaGateJob.asUInt && r.asUInt===gqaGateResult.asUInt','p.qkRole===0.U && p.c===q.a','r.accepted.asUInt===QkNormRuntimeJobV11.fromOwner(p).asUInt','r.outputAckBytes===p.writeBytes','p.writeBytes===(q.writeBytes<<1)'],
 'full_host_identity':['authority.transaction===r.transactionId && authority.launch.asUInt===r.host.asUInt','normalizedTransaction===c.transactionId && normalizedHost.asUInt===c.host.asUInt','x.transactionId===o.transactionId && x.host.asUInt===o.host.asUInt'],
 'logical_admission_not_fire':['val outputLogicalOfferBad=g.io.job.valid &&','denseOShape(offeredOutput) && denseOInputs(offeredOutput)','elementShape(offeredOutput) &&','gateInputs(offeredOutput),residualInputs(offeredOutput)'],
 'distinct_legacy_ops':['isOutputDense(j) && !j.materializeDenseOutput && outputCommon(j)','j.gdnElementwiseOp===GdnElementwiseOp.SigmoidMul.U','j.gdnElementwiseOp===GdnElementwiseOp.Add.U'],
 'output_physical_snapshot':['g.io.physicalJob.bits.asUInt===denseOExpected.asUInt','denseOSource.asUInt===mixedReceipt.asUInt','denseOSource.job.tag<g.io.physicalJob.bits.tag','elementInputB.job.tag<g.io.physicalJob.bits.tag','elementGateJob.tag<g.io.physicalJob.bits.tag','elementInputA.job.tag<g.io.physicalJob.bits.tag'],
 'source_replay':['p.tag>elementLastA(1) && c.job.tag>elementLastB(1)','x.job.tag>elementLastA(0) && o.job.tag>elementLastB(0)','r.job.tag>denseOLastProducer'],
 'actual_dense_ack':['when(denseOBusy && g.io.physicalDone.fire)','g.io.physicalDone.bits.writeBytes===denseOPending.writeBytes','g.io.physicalDone.bits.usefulMacs===(denseOPending.m.pad(64)*denseOPending.n.pad(64)*denseOPending.k.pad(64))(63,0)','denseOReceipt.result:=g.io.physicalDone.bits;denseOValid:=true.B'],
 'actual_input_residual':['x.job.a===q.a && x.job.m===q.m && x.job.n===q.n','isOutputDense(o.job) && o.job.dst===q.b'],
 'elementwise_counts':['elementwiseLanes*Mux(elementwiseSigmoid,5.U,1.U)','elementwiseLanes*Mux(elementwiseSigmoid,2.U,1.U)','(elementwiseLanes>>5)*3.U'],
 'independent_authority':['UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U','p.lease.identity.stage:=Mux(elementwiseShape,77.U','p.allocationValid:=false.B;p.allocationSequence:=0.U'],
 'full_leaf_terminal':['elementwiseEvent.bits.accepted.asUInt===elementwiseExpected.asUInt','elementwiseEvent.bits.outputCommitted && elementwiseEvent.bits.resourcesDrained','elementwiseEvent.bits.outputAckBytes===logical.writeBytes','elementwiseEvent.bits.scalarAccepted.pad(64)===elementwiseScalarOperations','elementwiseEvent.bits.formatAccepted.pad(64)===elementwiseFormatOperations','elementwiseEvent.bits.memoryAccepted.pad(64)===elementwiseMemoryOperations'],
 'real_shared_counts':['r.counts.accepted===leases(i).lease.expectedOperations.pad(33)','r.counts.issued===leases(i).lease.expectedOperations.pad(33)','r.counts.returned===leases(i).lease.expectedOperations.pad(33)'],
 'specialized_actual_fire':['when(elementwiseEvent.valid && (!owned || !elementwiseShape || !g.io.physicalDone.fire || !elementwiseTerminalExact))','(elementwiseShape && !elementwiseEvent.valid)'],
 'fault_veto':['!authority.currentFault && !g.io.localFault','outputLogicalOfferBad || denseOPhysicalBad','when(!tailCaptureClean || (denseOValid && !tailCurrent(denseOReceipt)))'],
 'physical_debt_not_receipt':['denseOWaiting || denseOBusy','!denseOWaiting && !denseOBusy'],
 'gqa_previous_evidence_preserved':['gqaQueryProducer.tag<g.io.physicalJob.bits.tag && gqaCacheProducer.job.tag<g.io.physicalJob.bits.tag','gqaEvent.bits.accepted.asUInt===gqaExpected.asUInt','gqaEvent.bits.outputCommitted && gqaEvent.bits.drained && gqaEvent.bits.attentionStatus===0.U'],
},
'UnifiedMoeSharedArithmeticProtocolV5.scala':{
 'new_kind_not_alias':['val OrdinaryGqa=8;val OrdinaryElementwise=9'],
 'same_slots':['val OrdinaryElementwiseScalar=8;val OrdinaryElementwiseFormat=9','val Count=11','val authorityKind=UInt(4.W)'],
 'separate_stage_caps':['val OrdinaryElementwiseStage=77','val OrdinaryElementwiseMaximumOperations=Seq(2621440,1048576)'],
},
'UnifiedMoeSharedArithmeticAdapterV5.scala':{
 'domain_explicit':['k===UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U','val ordinaryElementwise=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U'],
 'stage_caps_no_other_widen':['Mux(ordinaryElementwise,UnifiedMoeArithmeticClientV5.OrdinaryElementwiseStage.U','Mux(ordinaryElementwise,UnifiedMoeArithmeticClientV5.OrdinaryElementwiseMaximumOperations(i-8).U'],
 'no_vector_authority':['else if(i==10) ordinaryChunk','else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm && !ordinaryRope && !ordinaryGqa'],
}}
def validate(sources):
 errors=[]
 for fn,groups in checks.items():
  s=sources[fn]
  for group,parts in groups.items():
   for p in parts:
    if p not in s: errors.append(f'{fn}/{group}: missing {p}')
  for forbidden in ['new Matrix','new Scalar','transactionId=UInt(32.W)','elementInputA.job.tag(15,0)','elementInputB.job.tag(15,0)','denseOSource.job.tag(15,0)']:
   if forbidden in s:errors.append(f'{fn}: forbidden {forbidden}')
  lexical=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',s,flags=re.S)
  stack=[]
  for c in lexical:
   if c in '([{':stack.append(c)
   elif c in ')]}':
    if not stack or stack.pop()!={')':'(',']':'[','}':'{'}[c]:errors.append(f'{fn}: delimiter');break
  if stack:errors.append(f'{fn}: delimiter remainder')
 return errors
errors=validate(files)
if errors:raise SystemExit('\n'.join(errors))
n=0
for fn,groups in checks.items():
 for group,parts in groups.items():
  changed=dict(files);changed[fn]=changed[fn].replace(parts[0],parts[0]+'__MUTATION',1)
  # An appended token could retain the tested substring; remove its first char instead.
  changed[fn]=files[fn].replace(parts[0],'?'+parts[0][1:])
  if not validate(changed):raise SystemExit(f'uncaught mutation {fn}/{group}')
  n+=1
print(json.dumps({'status':'SOURCE_ASSERTIONS_ONLY_PASS','groups':n,'checks':sum(len(p) for g in checks.values() for p in g.values()),'mutation_tests':n,'sources':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()},'not_run':['Scala compiler','Chisel elaboration','RTL','DUT','numerical acceptance']},indent=2))
