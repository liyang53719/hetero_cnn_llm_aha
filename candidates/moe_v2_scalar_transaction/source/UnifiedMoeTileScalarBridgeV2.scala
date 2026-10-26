// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** NEXT INTERNAL fabric protocol draft. These are not the frozen V1 physical
  * fabric ports, and this file is not evidence of an integrated block. */
class UnifiedScalarOperationTagV2 extends Bundle {
  val tile = new MoeBf16TileIdentity
  val operationSerial = UInt(16.W)
}
class UnifiedScalarTileLeaseV2 extends Bundle {
  val context = new UnifiedBlockDispatchV1
  val identity = new MoeBf16TileIdentity
}
class UnifiedOwnedScalarRequestV2 extends Bundle {
  val tag = new UnifiedScalarOperationTagV2
  val payload = new ScalarRequest
}
class UnifiedOwnedScalarResultV2 extends Bundle {
  val tag = new UnifiedScalarOperationTagV2
  val payload = new UnifiedScalarResult
}
class UnifiedProducerDrainedV2 extends Bundle {
  val identity = new MoeBf16TileIdentity
  val status = UInt(8.W)
  val drained = Bool()
}
class UnifiedScalarTileReleaseIntentV2 extends Bundle {
  val identity = new MoeBf16TileIdentity
  val status = UInt(8.W)
  val issuedOperations = UInt(17.W)
  val completedOperations = UInt(17.W)
  val drained = Bool()
}
class UnifiedScalarTileReleaseAckV2 extends Bundle {
  val identity = new MoeBf16TileIdentity
  val status = UInt(8.W)
  val drained = Bool()
  val resetRequired = Bool()
}

/** Fixed single MoE-reduce client. No ALU/MAC instance or model constructor.
  * A future shared arbiter must retain one owner lease across all scalar ops;
  * this cannot connect directly to V1's single-operation-per-lease interface.
  * The arbiter latches each full operation tag at the original scalar's
  * request.fire and returns that exact tag with its response. It validates
  * release against its own pending/held-result state, not a host success flag.
  *
  * Complete MoE profile reduction is eight routed experts plus shared: nine
  * contributions. The old generic consumer and its routed-only unit test are
  * unchanged; eight is not accepted as a complete MoE tile here.
  * Token is block-local; tileOrdinal is a32-lane tile within hidden dimension.
  * These identities must never be reused within one admission transaction.
  * No abort/clear: reset requires simultaneous parent/arbiter/primitive and
  * upstream-response isolation; merely clearing tags cannot cancel real work.
  */
class UnifiedMoeTileScalarBridgeV2 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedScalarTileLeaseV2))
    val externalProtocolFault=Input(Bool()) // Sticky error input, never drain or abort.
    val ownerAcquire=Decoupled(new UnifiedScalarTileLeaseV2)
    val releaseIntent=Decoupled(new UnifiedScalarTileReleaseIntentV2)
    val releaseAck=Flipped(Decoupled(new UnifiedScalarTileReleaseAckV2))
    val ownerFault=Valid(new MoeBf16TileIdentity)
    val producerReady=Input(Bool())
    val producerStart=Output(Bool())
    val producerContext=Output(new UnifiedScalarTileLeaseV2)
    val contribution=Flipped(Decoupled(new MoeBf16TileContribution))
    val producerDrained=Flipped(Decoupled(new UnifiedProducerDrainedV2))
    val scalarRequest=Decoupled(new UnifiedOwnedScalarRequestV2)
    val scalarResult=Flipped(Decoupled(new UnifiedOwnedScalarResultV2))
    val result=Decoupled(new MoeBf16TileResult)
    val rejectedScalarResponse=Output(Bool())
    val rejectedProducerReceipt=Output(Bool())
    val lateContributionRejected=Output(Bool())
    val busy=Output(Bool())
    val protocolFaultBits=Output(UInt(6.W))
    val resetRequired=Output(Bool())
    val locallyQuiescent=Output(Bool()) // Not a global reset fence.
  })
  val consumer=Module(new MoeBf16ScalarConsumer)
  val idle::acquire::launch::active::held::release::awaitAck::publish::Nil=Enum(8)
  val state=RegInit(idle)
  val lease=Reg(new UnifiedScalarTileLeaseV2)
  val output=Reg(new MoeBf16TileResult)
  val intent=Reg(new UnifiedScalarTileReleaseIntentV2)
  val backendResetRequired=RegInit(false.B)
  val ownerHeld=RegInit(false.B)
  val producerSeen=RegInit(false.B);val producerStatus=RegInit(Status.Ok.U(8.W))
  val pending=RegInit(false.B);val pendingTag=Reg(new UnifiedScalarOperationTagV2)
  // Extended counter cannot silently wrap the16-bit operationSerial.
  val issued=RegInit(0.U(17.W));val completed=RegInit(0.U(17.W))
  // Sticky visible fault metadata; only system isolation/reset clears this.
  // It never itself retires pending work or manufactures a drained fence.
  val faultBits=RegInit(0.U(6.W));val faultNow=WireDefault(0.U(6.W))
  val faultAny=(faultBits|faultNow).orR
  faultBits:=faultBits|faultNow
  io.protocolFaultBits:=faultBits|faultNow
  io.resetRequired:=faultAny||backendResetRequired
  io.ownerFault.valid:=ownerHeld && (faultAny||backendResetRequired)
  io.ownerFault.bits:=lease.identity
  val (decoded,known)=UnifiedRuntimeProfile.decode(io.begin.bits.context.launch.profileId)
  val beginIdentity=io.begin.bits.identity
  val beginContext=io.begin.bits.context
  val legal=known && decoded.asUInt===beginContext.profile.asUInt && decoded.mlp===1.U &&
    decoded.expertCount===256.U && decoded.expertsPerToken===8.U && decoded.sharedFfn===512.U &&
    beginContext.launch.version===1.U && beginContext.launch.opcode===0.U &&
    beginContext.launch.tokens>=1.U && beginContext.launch.tokens<=128.U &&
    beginIdentity.transactionId===beginContext.transactionId &&
    beginIdentity.token<beginContext.launch.tokens &&
    decoded.hidden(4,0)===0.U && beginIdentity.tileOrdinal<(decoded.hidden>>5)
  io.begin.ready:=state===idle && !io.resetRequired
  io.busy:=state=/=idle
  io.locallyQuiescent:=state===idle && !pending && !ownerHeld
  io.ownerAcquire.valid:=state===acquire;io.ownerAcquire.bits:=lease
  io.producerContext:=lease
  consumer.io.job.valid:=state===launch && io.producerReady && !faultAny
  consumer.io.job.bits.identity:=lease.identity
  consumer.io.job.bits.contributionCount:=9.U
  io.producerStart:=consumer.io.job.fire
  // Parent binds producerStart to the one order controller's start and supplies
  // its real startReady. No route/producer launch occurs at begin alone.
  when(io.begin.fire){
    lease:=io.begin.bits;pending:=false.B;issued:=0.U;completed:=0.U
    producerSeen:=false.B;producerStatus:=Status.Ok.U
    output:=0.U.asTypeOf(new MoeBf16TileResult);output.identity:=io.begin.bits.identity
    when(legal){state:=acquire}.otherwise{output.status:=Status.Malformed.U;state:=publish}
  }
  when(io.ownerAcquire.fire){ownerHeld:=true.B;state:=launch}
  when(consumer.io.job.fire){state:=active}

  consumer.io.contribution.valid:=state===active && !producerSeen && io.contribution.valid
  consumer.io.contribution.bits:=io.contribution.bits
  io.contribution.ready:=Mux(state===active && !producerSeen,consumer.io.contribution.ready,true.B)
  io.lateContributionRejected:=io.contribution.fire && (state=/=active || producerSeen)
  val producerIdentity=io.producerDrained.bits.identity.asUInt===lease.identity.asUInt
  val producerStatusLegal=io.producerDrained.bits.status===Status.Ok.U ||
    (io.producerDrained.bits.status>=Status.Malformed.U && io.producerDrained.bits.status<=Status.Permission.U)
  val acceptProducer=(state===active || state===held) && producerIdentity &&
    io.producerDrained.bits.drained && producerStatusLegal && !producerSeen
  io.producerDrained.ready:=true.B
  io.rejectedProducerReceipt:=io.producerDrained.fire && !acceptProducer
  when(io.producerDrained.fire && acceptProducer){producerSeen:=true.B;producerStatus:=io.producerDrained.bits.status}
  consumer.io.sourceFailure.valid:=state===active && producerSeen && producerStatus=/=Status.Ok.U
  consumer.io.sourceFailure.bits.identity:=lease.identity
  consumer.io.sourceFailure.bits.status:=producerStatus
  consumer.io.sourceFailure.bits.drained:=true.B

  val serialAvailable=issued<65536.U
  io.scalarRequest.valid:=state===active && !pending && serialAvailable && consumer.io.scalarRequest.valid
  io.scalarRequest.bits.tag.tile:=lease.identity
  io.scalarRequest.bits.tag.operationSerial:=issued(15,0)
  io.scalarRequest.bits.payload:=consumer.io.scalarRequest.bits
  consumer.io.scalarRequest.ready:=state===active && !pending && serialAvailable && io.scalarRequest.ready
  when(io.scalarRequest.fire){pending:=true.B;pendingTag:=io.scalarRequest.bits.tag;issued:=issued+1.U}
  val responseIdentity=pending && io.scalarResult.bits.tag.asUInt===pendingTag.asUInt
  consumer.io.scalarResult.valid:=state===active && responseIdentity && io.scalarResult.valid
  consumer.io.scalarResult.bits:=io.scalarResult.bits.payload.value
  consumer.io.scalarError:=io.scalarResult.bits.payload.error
  // Wrong/stale/duplicate replies are dropped visibly, never retire pending or
  // change the child numerical status. Outer tile status is Protocol with
  // resetRequired for such faults before result linearization. Later faults
  // remain global poison and cannot mutate an already-held result.
  // A missing authentic response requires the
  // parent watchdog+physical isolation; a producer receipt cannot clear it.
  io.scalarResult.ready:=Mux(state===active && responseIdentity,consumer.io.scalarResult.ready,true.B)
  io.rejectedScalarResponse:=io.scalarResult.fire && !responseIdentity
  when(consumer.io.scalarResult.fire){pending:=false.B;completed:=completed+1.U}
  consumer.io.result.ready:=state===active && !pending
  when(consumer.io.result.fire){output:=consumer.io.result.bits;state:=held}

  // Release intent is an immutable offer, not proof that the arbiter has
  // released anything. A late fault travels on a separate sticky sideband.
  // The arbiter samples that sideband at its real intent.fire commit point
  // and returns a matching held acknowledgment. No live signal rewrites an
  // already-valid acquisition, intent, acknowledgment or tile output.
  val ackStatusLegal=io.releaseAck.bits.status===Status.Ok.U ||
    (io.releaseAck.bits.status>=Status.Malformed.U && io.releaseAck.bits.status<=Status.Permission.U)
  val ackIdentity=io.releaseAck.bits.identity.asUInt===lease.identity.asUInt
  // Backend acknowledgment is registered: offered no earlier than the cycle
  // following intent.fire. An early acknowledgment is a protocol fault.
  val ackAccept=state===awaitAck && ownerHeld && ackIdentity && io.releaseAck.bits.drained && ackStatusLegal
  io.releaseAck.ready:=true.B // wrong/stale/undrained receipts are visible drops, never credit
  val badAck=io.releaseAck.fire && !ackAccept
  faultNow:=Cat(io.externalProtocolFault,badAck,consumer.io.staleContributionRejected,io.lateContributionRejected,
    io.rejectedProducerReceipt,io.rejectedScalarResponse)
  // Once acquisition is offered it cannot be withdrawn. If a fault arrives
  // before grant, wait for that same grant and return a proven-empty owner.
  // In launch no child fired; suppress child start and take only that local
  // zero-obligation path. This cannot stand in for a started producer's drain.
  when(faultAny && state===launch){
    output.status:=Status.Protocol.U;producerSeen:=true.B;producerStatus:=Status.Protocol.U;state:=held
  }
  val beforeOfferStatus=Mux(faultAny,Status.Protocol.U,
    Mux(output.status=/=Status.Ok.U,output.status,producerStatus))
  when(state===held && producerSeen && !pending && issued===completed && !io.scalarResult.valid){
    intent.identity:=lease.identity
    intent.status:=beforeOfferStatus
    intent.issuedOperations:=issued;intent.completedOperations:=completed
    intent.drained:=true.B
    state:=release
  }
  io.releaseIntent.valid:=state===release;io.releaseIntent.bits:=intent
  when(io.releaseIntent.fire){state:=awaitAck}
  when(io.releaseAck.fire && ackAccept){
    // The backend must not upgrade a non-Ok diagnostic intent to Ok. A genuine
    // drained acknowledgment can still be consumed, but that violation poisons
    // the transaction and invalidates output instead of pretending success.
    val upgrade=intent.status=/=Status.Ok.U && io.releaseAck.bits.status===Status.Ok.U
    val resetFault=io.releaseAck.bits.resetRequired
    val unsafe=faultAny || upgrade || resetFault
    val acknowledgedStatus=Mux(unsafe,Status.Protocol.U,
      Mux(io.releaseAck.bits.status=/=Status.Ok.U,io.releaseAck.bits.status,intent.status))
    output.status:=acknowledgedStatus
    when(acknowledgedStatus=/=Status.Ok.U){output.data:=0.U}
    when(upgrade || resetFault){backendResetRequired:=true.B}
    ownerHeld:=false.B;state:=publish
  }
  io.result.valid:=state===publish;io.result.bits:=output
  when(io.result.fire){state:=idle}
  // Faults arriving after acknowledgment/result linearization are global
  // poison, not permission to mutate held payload or reverse retired credit.
  // The future block-completion fence must sample sticky resetRequired even
  // if a previously completed tile result was Ok. That fence is not here.
  // A release is a private tile-owner fence, never a UnifiedBlockCompletionV1.
  // Publishing successful tile bytes still requires parent destination/DDR ACK
  // rules; this module writes no output memory and emits no block completion.
}
