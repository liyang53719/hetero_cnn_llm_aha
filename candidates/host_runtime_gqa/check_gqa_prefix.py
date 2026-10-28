#!/usr/bin/env python3
"""Bounded source assertions; never Scala compilation, RTL, or DUT evidence."""
from pathlib import Path
import hashlib, json, re
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'source/HostRuntimePrefixLeaseWiringV8.scala'
S=SOURCE.read_text()
CHECKS={
 'full_q_snapshot':['val rotatedQJob=Reg(new QwenOwnerJob)','val rotatedQResult=Reg(new PartialRopeRuntimeResultV12)','val rotatedQHost=Reg(new HostCommandLaunchV4)','val rotatedQTransaction=Reg(UInt(64.W))'],
 'full_q_current':['authority.transaction===rotatedQTransaction','authority.launch.asUInt===rotatedQHost.asUInt'],
 'real_q_ack_capture':['ropeEvent.valid && owned && ropeShape && terminalExact && g.io.physicalDone.fire','ropeTerminalExact && ropeEvent.bits.status===Status.Ok.U && logical.qkRole===0.U','rotatedQJob:=retainedPhysical;rotatedQResult:=ropeEvent.bits'],
 'two_real_producers':['gqaQueryProducer:=p;gqaQueryResult:=d;gqaCacheProducer:=kvReceipt','!rotatedQValid || !rotatedQCurrent || !ropeQCommitted || !kvReceiptValid || !kvReceiptCurrent'],
 'whole_host_transaction':['rotatedQTransaction=/=kvReceipt.transactionId || rotatedQHost.asUInt=/=kvReceipt.host.asUInt','gqaCacheProducer.transactionId===transaction && gqaCacheProducer.host.asUInt===host.asUInt'],
 'accepted_q_job':['d.accepted.asUInt=/=PartialRopeRuntimeJobV12.fromOwner(p).asUInt'],
 'accepted_cache_job':['r.accepted.asUInt=/=Bf16KvAppendRuntimeJobV13.fromOwner(c).asUInt'],
 'both_strict_producers':['gqaQueryProducer.tag<g.io.physicalJob.bits.tag && gqaCacheProducer.job.tag<g.io.physicalJob.bits.tag','gqaQueryProducer.tag=/="hffffffff".U && gqaCacheProducer.job.tag=/="hffffffff".U'],
 'physical_snapshot_exact':['gqaQueryProducer.asUInt===rotatedQJob.asUInt && gqaQueryResult.asUInt===rotatedQResult.asUInt','gqaCacheProducer.asUInt===kvReceipt.asUInt'],
 'independent_replay':['p.tag<=gqaLastQuery || c.tag<=gqaLastCache','kvReceipt.transactionId<gqaLastTransaction','gqaLastQuery:=gqaQueryProducer.tag;gqaLastCache:=gqaCacheProducer.job.tag'],
 'cold_shape':['logical.m===128.U','logical.cacheCapacity===128.U && logical.cacheLength===128.U','logical.cold && logical.queryStart===0.U && logical.expectedCacheLength===0.U','logical.expectedGeneration===0.U && logical.currentGeneration===0.U'],
 'runtime_q8_q16':['logical.n===Mux(host.profileId===2.U,2048.U,4096.U) && logical.k===256.U','logical.qkRole===0.U && logical.qkNormPolicy===1.U'],
 'exact_policy_lease':['p.authorityKind:=Mux(gqaShape,UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U','p.lease.identity.stage:=Mux(gqaShape,76.U','p.allocationValid:=false.B;p.allocationSequence:=0.U'],
 'six_scalar_full_width':['val gqaScalarOperations=(logical.m*logical.cacheLength*(logical.n>>8)*6.U).pad(64)','gqaScalarOperations<=UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U'],
 'scalar_only':['acquirePending && !qkShape && !ropeShape && !gqaShape','retirePending && !qkShape && !ropeShape && !gqaShape'],
 'exact_scalar_counts':['a.io.status(8).counts.accepted===leases(0).lease.expectedOperations.pad(33)','a.io.status(8).counts.issued===leases(0).lease.expectedOperations.pad(33)','a.io.status(8).counts.returned===leases(0).lease.expectedOperations.pad(33)'],
 'exact_leaf_counts':['gqaEvent.bits.scalarAccepted.pad(64)===gqaScalarOperations','gqaEvent.bits.scalarReturned.pad(64)===gqaScalarOperations','gqaEvent.bits.memoryAccepted.pad(64)===gqaMemoryOperations','gqaEvent.bits.matrixGroupsAccepted.pad(64)===gqaMatrixGroups'],
 'exact_terminals':['gqaEvent.bits.accepted.asUInt===gqaExpected.asUInt','gqaEvent.bits.outputCommitted && gqaEvent.bits.drained && gqaEvent.bits.attentionStatus===0.U','gqaEvent.bits.outputAckBytes===logical.writeBytes','(!gqaShape || gqaTerminalExact)','(gqaShape && !gqaEvent.valid)'],
 'terminal_real_fire':['when(gqaEvent.valid && (!owned || !gqaShape || !g.io.physicalDone.fire || !gqaTerminalExact))'],
 'held_path_preserved':['HeldDecoupledOffer(scalar.request.valid,scalarPort.request.ready,firstFault)','scalar.result<>scalarPort.result','retirePending:=leaseEventSubmitted'],
 'proposal_private':['private staging provenance, never published roots','val kvReceipt=Valid(new HostRuntimeKvStagedReceiptV13)'],
}
def validate(source):
 errors=[]
 for name,parts in CHECKS.items():
  for x in parts:
   if x not in source: errors.append(name+': '+x)
 for forbidden in ['gqaQueryProducer.tag(15,0)','gqaCacheProducer.job.tag(15,0)','gqaLastTransaction=Reg(UInt(32.W))','new Scalar','new Matrix','new RetainedIdma']:
  if forbidden in source: errors.append('forbidden '+forbidden)
 # Delimiter test is lexical only; actual Scala typecheck remains separate.
 lexical=re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"','',source,flags=re.S)
 stack=[]
 for c in lexical:
  if c in '([{': stack.append(c)
  elif c in ')]}':
   if not stack or stack.pop()!={')':'(',']':'[','}':'{'}[c]: errors.append('unbalanced delimiters');break
 if stack: errors.append('unterminated delimiters')
 return errors
errors=validate(S)
if errors: raise SystemExit('\n'.join(errors))
mutations=0
for parts in CHECKS.values():
 for part in parts[:1]:
  bad=S.replace(part,part.replace(part[:1],'~',1))
  if not validate(bad): raise SystemExit('mutation not caught '+part)
  mutations+=1
out={'status':'SOURCE_ASSERTIONS_ONLY_PASS','checks':sum(map(len,CHECKS.values())),'check_groups':len(CHECKS),'mutation_tests':mutations,'source_sha256':hashlib.sha256(S.encode()).hexdigest(),'not_run':['Scala typecompile','Chisel elaboration','RTL','DUT','numerical acceptance']}
print(json.dumps(out,ensure_ascii=False,indent=2))
