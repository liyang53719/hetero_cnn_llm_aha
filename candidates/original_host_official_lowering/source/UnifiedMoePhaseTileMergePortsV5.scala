// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedMoePhaseTileMergeResultV5 extends Bundle {
  val identity=new MoeBf16TileIdentity;val allocationSequence=UInt(64.W)
  val data=UInt(512.W);val status=UInt(8.W);val drained=Bool()
  val accepted=UInt(6.W);val issued=UInt(6.W);val returned=UInt(6.W)
}

/** Concrete tile subtransaction within ONE retained whole-M merge owner.
  * Instantiates only the actual DDR reader/ordering controller and the existing
  * unchanged BF16 vector consumer. ZERO ALU, bank, formatter, divider, Matrix or
  * new physical top. One request offer buffer is added to preserve an already
  * accepted raw offer through fault; it is NOT a multi-outstanding II1 design.
  *
  * These RAW vector ports are private clients of the parent's one V3 resource
  * ledger. Parent must own the full phase/allocation/epoch, immutable group-
  * scope owner identity, 32bit operation serial and33bit resource counts, and
  * reject mismatched full tags BEFORE returning raw payload here. A raw policy
  * echo alone is not ownership. That parent V3 routing is not yet installed.
  *
  * This tile result is NOT a resource release or final block completion. The
  * parent keeps the whole-group lease, writes actual tile DDR data, checks its
  * matching ACK and advances its unique token/tile counter. Only the final
  * group writes + real global drain + sticky-fault fence may release anything.
  * Current fault must gate new offers and completion in that parent, including
  * a same-cycle late fault when an already-held result fires. Do not revoke or
  * mutate a held result to hide such a fault.
  */
class UnifiedMoePhaseTileMergePortsV5 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoeNineDownReadJobV5))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val vectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    val memoryResetRequired=Input(Bool())
    val externalPoison=Input(Bool()) // parent's registered sticky state, not a faultNow loop
    val result=Decoupled(new UnifiedMoePhaseTileMergeResultV5)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val accepted=Output(UInt(6.W));val issued=Output(UInt(6.W));val returned=Output(UInt(6.W))
  })
  val reader=Module(new UnifiedMoeDownTileReaderV5)
  val producer=Module(new UnifiedMoeProducerBindingV5)
  val consumer=Module(new MoeBf16VectorConsumerV2)
  val idle::launch::active::publish::locked::Nil=Enum(5)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeNineDownReadJobV5)
  val output=Reg(new UnifiedMoePhaseTileMergeResultV5)
  val numeric=Reg(new MoeBf16TileResult);val numericSeen=RegInit(false.B)
  val readerSeen=RegInit(false.B);val producerSeen=RegInit(false.B)
  val readerStatus=Reg(UInt(8.W));val producerStatus=Reg(UInt(8.W))
  val offerHeld=RegInit(false.B);val offerBits=Reg(new UnifiedVectorRequestV2)
  val pending=RegInit(false.B);val pendingPolicy=Reg(UInt(2.W))
  val accepted=RegInit(0.U(6.W));val issued=RegInit(0.U(6.W));val returned=RegInit(0.U(6.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val badReaderReceipt=WireDefault(false.B);val badProducerReceipt=WireDefault(false.B);val badNumeric=WireDefault(false.B)
  val unownedMemory=io.response.valid && !reader.io.response.ready
  val unknownVector=io.vectorResult.valid && !pending
  val policyMismatch=io.vectorResult.valid && pending && io.vectorResult.bits.policy=/=pendingPolicy
  when(unknownVector||policyMismatch||unownedMemory||io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.externalPoison){poison:=true.B}
  // Break feedback through producer.start.valid: only poisonLatched feeds the
  // local launch gate. Its immediate faultEvent is outward-only notification.
  val fault=poison||quarantine||unknownVector||policyMismatch||unownedMemory||io.memoryResetRequired||
    badReaderReceipt||badProducerReceipt||badNumeric||io.externalPoison||
    reader.io.resetRequired||producer.io.poisonLatched||consumer.io.staleContributionRejected||consumer.io.rejectedFailure
  io.resetRequired:=fault||producer.io.faultEvent
  io.contextReserved:=state=/=idle||io.begin.valid||offerHeld||pending||reader.io.contextReserved||producer.io.active||consumer.io.busy
  io.accepted:=accepted;io.issued:=issued;io.returned:=returned
  io.begin.ready:=state===idle && !fault && !producer.io.faultEvent
  val candidate=Mux(state===idle,io.begin.bits,job)
  reader.io.job.bits:=candidate
  producer.io.start.bits.context:=candidate.context
  producer.io.start.bits.allocationSequence:=candidate.allocationSequence
  producer.io.start.bits.identity:=candidate.identity
  consumer.io.job.bits.identity:=candidate.identity;consumer.io.job.bits.contributionCount:=9.U
  val launchSafe=state===launch && !fault
  reader.io.job.valid:=launchSafe && producer.io.start.ready && consumer.io.job.ready
  producer.io.start.valid:=launchSafe && reader.io.job.ready && consumer.io.job.ready
  consumer.io.job.valid:=launchSafe && producer.io.start.ready && reader.io.job.ready
  when(io.begin.fire){
    job:=io.begin.bits;accepted:=0.U;issued:=0.U;returned:=0.U
    numericSeen:=false.B;readerSeen:=false.B;producerSeen:=false.B
    readerStatus:=Status.Ok.U;producerStatus:=Status.Ok.U
    output:=0.U.asTypeOf(new UnifiedMoePhaseTileMergeResultV5)
    output.identity:=io.begin.bits.identity;output.allocationSequence:=io.begin.bits.allocationSequence
    when(reader.io.jobLegal){state:=launch}.otherwise{
      output.status:=Status.Bounds.U;output.drained:=true.B;state:=publish
    }
  }
  when(reader.io.job.fire){state:=active}
  when(state===launch && fault){
    // No child start fires on this edge. If an unknown raw result exists, it
    // is NOT an empty-drain proof even though this tile did not issue work.
    output.status:=Status.Protocol.U;output.data:=0.U
    output.drained:= !quarantine && !unknownVector && !policyMismatch && !unownedMemory && !io.memoryResetRequired &&
      !badReaderReceipt && !badProducerReceipt && !badNumeric && !reader.io.resetRequired
    state:=publish
  }
  producer.io.route<>reader.io.route;reader.io.dispatch<>producer.io.dispatch
  producer.io.returned<>reader.io.returned
  io.memory<>reader.io.memory;reader.io.response<>io.response
  reader.io.memoryResetRequired:=io.memoryResetRequired
  reader.io.currentFault:=poison||io.externalPoison // registered local feedback only
  consumer.io.contribution<>producer.io.contribution

  val rd=reader.io.done.bits
  val rdMatches=state===active && !readerSeen && rd.identity.asUInt===job.identity.asUInt &&
    rd.allocationSequence===job.allocationSequence && rd.drained && rd.returned===9.U &&
    (rd.status===Status.Ok.U || (rd.status>=Status.Malformed.U && rd.status<=Status.Permission.U))
  reader.io.done.ready:=true.B
  badReaderReceipt:=reader.io.done.fire && !rdMatches
  when(reader.io.done.fire){
    when(rdMatches){readerSeen:=true.B;readerStatus:=rd.status}
    .otherwise{poison:=true.B;quarantine:=true.B}
  }
  val pd=producer.io.drained.bits
  val pdMatches=state===active && !producerSeen && pd.identity.asUInt===job.identity.asUInt &&
    pd.allocationSequence===job.allocationSequence && pd.drained &&
    (pd.status===Status.Ok.U || (pd.status>=Status.Malformed.U && pd.status<=Status.Permission.U))
  producer.io.drained.ready:=true.B
  badProducerReceipt:=producer.io.drained.fire && !pdMatches
  when(producer.io.drained.fire){
    when(pdMatches){producerSeen:=true.B;producerStatus:=pd.status}
    .otherwise{poison:=true.B;quarantine:=true.B}
  }
  consumer.io.sourceFailure.valid:=state===active && producerSeen && producerStatus=/=Status.Ok.U
  consumer.io.sourceFailure.bits.identity:=job.identity
  consumer.io.sourceFailure.bits.status:=producerStatus;consumer.io.sourceFailure.bits.drained:=true.B

  // The consumer's accepted request becomes one stable offer. A newly seen
  // unknown response stops NEW accepts; it cannot retract a prior held offer.
  consumer.io.vectorRequest.ready:=state===active && !offerHeld && !pending &&
    !quarantine && !unknownVector && !policyMismatch && accepted<36.U
  when(consumer.io.vectorRequest.fire){offerHeld:=true.B;offerBits:=consumer.io.vectorRequest.bits;accepted:=accepted+1.U}
  io.vectorRequest.valid:=offerHeld;io.vectorRequest.bits:=offerBits
  when(io.vectorRequest.fire){offerHeld:=false.B;pending:=true.B;pendingPolicy:=offerBits.policy;issued:=issued+1.U}
  consumer.io.vectorResult.valid:=state===active && pending && !quarantine && !policyMismatch && io.vectorResult.valid
  consumer.io.vectorResult.bits:=io.vectorResult.bits
  io.vectorResult.ready:=state===active && pending && !quarantine &&
    Mux(policyMismatch,true.B,consumer.io.vectorResult.ready)
  when(consumer.io.vectorResult.fire){pending:=false.B;returned:=returned+1.U}
  // A wrong-policy packet is discarded, but does NOT retire pending/returned.
  // Unknown-before-pending remains held and quarantined, never relabeled.
  consumer.io.result.ready:=state===active && !numericSeen && !pending && !offerHeld
  badNumeric:=consumer.io.result.fire && consumer.io.result.bits.identity.asUInt=/=job.identity.asUInt
  when(consumer.io.result.fire){
    when(consumer.io.result.bits.identity.asUInt===job.identity.asUInt){numeric:=consumer.io.result.bits;numericSeen:=true.B}
    .otherwise{poison:=true.B;quarantine:=true.B}
  }
  when(state===active && numericSeen && readerSeen && producerSeen && !pending && !offerHeld &&
      accepted===issued && issued===returned && !quarantine && !unknownVector && !policyMismatch && !unownedMemory &&
      !io.memoryResetRequired && !badReaderReceipt && !badProducerReceipt && !badNumeric){
    val ok=numeric.status===Status.Ok.U && readerStatus===Status.Ok.U && producerStatus===Status.Ok.U &&
      !fault && !producer.io.faultEvent && issued===36.U
    val status=Mux(ok,Status.Ok.U,Mux(numeric.status=/=Status.Ok.U,numeric.status,Status.Protocol.U))
    output.data:=Mux(ok,numeric.data,0.U);output.status:=status;output.drained:=true.B
    output.accepted:=accepted;output.issued:=issued;output.returned:=returned;state:=publish
  }
  io.result.valid:=state===publish;io.result.bits:=output
  when(io.result.fire){state:=Mux(io.resetRequired|| !output.drained,locked,idle)}
  // Missing/wrong-attribution service responses may leave real debt forever:
  // expose sticky resetRequired; only the parent watchdog + isolated reset can
  // reopen. No arbitrary cancellation, fake producer receipt or owner release.
}
