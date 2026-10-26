// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini._

class UnifiedTaggedMoeRouteV2 extends Bundle {
  val identity=new MoeBf16TileIdentity;val payload=new HeteroMoeRoute(10,32)
}
class UnifiedTaggedMoeDispatchV2 extends Bundle {
  val identity=new MoeBf16TileIdentity;val payload=new HeteroMoeDispatchEntry(32,10,32,4)
}
class UnifiedTaggedMoeReturnV2 extends Bundle {
  val identity=new MoeBf16TileIdentity;val payload=new HeteroMoeResult(512,4)
}

/** Real producer binding, not a host-supplied drained Boolean. Reuses exactly
  * the fixed shared order controller, including its issued/result-valid state.
  * Wrong epochs never enter its routeTag-only return cache. Local counters are
  * observations of actual handshakes, not a second route/result payload table.
  */
class UnifiedMoeProducerBindingV2 extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new UnifiedScalarTileLeaseV2))
    val route=Flipped(Decoupled(new UnifiedTaggedMoeRouteV2))
    val dispatch=Decoupled(new UnifiedTaggedMoeDispatchV2)
    val returned=Flipped(Decoupled(new UnifiedTaggedMoeReturnV2))
    val contribution=Decoupled(new MoeBf16TileContribution)
    val drained=Decoupled(new UnifiedProducerDrainedV2)
    val poisonLatched=Output(Bool());val faultEvent=Output(Bool());val resetRequired=Output(Bool())
    val active=Output(Bool());val observedContributions=Output(UInt(5.W))
  })
  val order=Module(new HeteroRuntimeMoeMerge)
  val active=RegInit(false.B);val lease=Reg(new UnifiedScalarTileLeaseV2)
  val receiptHeld=RegInit(false.B);val receipt=Reg(new UnifiedProducerDrainedV2)
  val routes=RegInit(0.U(5.W));val sharedRoutes=RegInit(0.U(5.W));val sharedTag=Reg(UInt(4.W))
  val dispatches=RegInit(0.U(5.W));val contributions=RegInit(0.U(5.W))
  val poison=RegInit(false.B)
  val (decoded,known)=UnifiedRuntimeProfile.decode(io.start.bits.context.launch.profileId)
  val startLegal=known && decoded.asUInt===io.start.bits.context.profile.asUInt && decoded.mlp===1.U &&
    decoded.expertCount===256.U && decoded.expertsPerToken===8.U && decoded.sharedFfn===512.U &&
    io.start.bits.context.launch.version===1.U && io.start.bits.context.launch.opcode===0.U &&
    io.start.bits.context.launch.tokens>=1.U && io.start.bits.context.launch.tokens<=128.U &&
    io.start.bits.identity.transactionId===io.start.bits.context.transactionId &&
    io.start.bits.identity.token<io.start.bits.context.launch.tokens && decoded.hidden(4,0)===0.U &&
    io.start.bits.identity.tileOrdinal<(decoded.hidden>>5)
  io.start.ready:= !active && !receiptHeld && !poison && order.io.startReady && startLegal
  order.io.clear:=reset.asBool // No host clear or busy abort.
  order.io.start:=io.start.fire
  order.io.token:=io.start.bits.identity.token
  order.io.routeCount:=9.U
  order.io.expertCount:=io.start.bits.context.profile.expertCount
  order.io.mergeByExpert:=io.start.bits.context.profile.mlp===1.U
  when(io.start.fire){
    lease:=io.start.bits;active:=true.B;routes:=0.U;sharedRoutes:=0.U;dispatches:=0.U;contributions:=0.U
  }
  val routeIdentity=io.route.bits.identity.asUInt===lease.identity.asUInt
  order.io.routeIn.valid:=active && routeIdentity && io.route.valid
  order.io.routeIn.bits:=io.route.bits.payload
  // Route offers may wait for the private start; never consume future load
  // data before owner grant/producer launch. Active wrong epochs are dropped.
  io.route.ready:=active && Mux(routeIdentity,order.io.routeIn.ready,true.B)
  val badRoute=io.route.fire && (!active || !routeIdentity)
  when(order.io.routeIn.fire){
    routes:=routes+1.U
    when(io.route.bits.payload.shared){sharedRoutes:=sharedRoutes+1.U;sharedTag:=routes(3,0)}
  }
  io.dispatch.valid:=active && order.io.dispatchOut.valid
  io.dispatch.bits.identity:=lease.identity;io.dispatch.bits.payload:=order.io.dispatchOut.bits
  order.io.dispatchOut.ready:=active && io.dispatch.ready
  when(io.dispatch.fire){dispatches:=dispatches+1.U}
  val returnIdentity=io.returned.bits.identity.asUInt===lease.identity.asUInt
  order.io.resultIn.valid:=active && returnIdentity && io.returned.valid
  order.io.resultIn.bits:=io.returned.bits.payload
  io.returned.ready:=Mux(active && returnIdentity,order.io.resultIn.ready,true.B)
  val badReturn=io.returned.fire && (!active || !returnIdentity)
  io.contribution.valid:=active && order.io.mergeOut.valid
  io.contribution.bits.identity:=lease.identity
  io.contribution.bits.routeTag:=order.io.mergeOut.bits.routeTag
  io.contribution.bits.weight:=order.io.mergeOut.bits.weight
  io.contribution.bits.data:=order.io.mergeOut.bits.data
  io.contribution.bits.first:=order.io.mergeOut.bits.first
  io.contribution.bits.last:=order.io.mergeOut.bits.last
  order.io.mergeOut.ready:=active && io.contribution.ready
  when(io.contribution.fire){contributions:=contributions+1.U}

  val afterContribution=contributions +& io.contribution.fire.asUInt
  val successWitness=routes===9.U && sharedRoutes===1.U && dispatches===9.U &&
    afterContribution===9.U && io.contribution.fire && io.contribution.bits.last &&
    io.contribution.bits.routeTag===sharedTag
  // In the original controller a failed load issues zero dispatches; a return
  // protocol error reaches done only after all9 otherwise valid issued results
  // have really retired. Its actual issued/resultValid state is the authority.
  val errorWitness=routes===9.U && (dispatches===0.U || dispatches===9.U) && contributions===0.U
  val doneWitness=Mux(order.io.protocolError,errorWitness,successWitness)
  val badDone=order.io.done && (!active || !doneWitness || receiptHeld)
  val faultNow=badRoute || badReturn || badDone || (io.start.valid && !startLegal)
  when(faultNow){poison:=true.B}
  when(order.io.done && active){
    receipt.identity:=lease.identity
    receipt.status:=Mux(order.io.protocolError || poison || faultNow,Status.Protocol.U,Status.Ok.U)
    receipt.drained:=doneWitness && !receiptHeld
    receiptHeld:=true.B;active:=false.B
  }
  io.drained.valid:=receiptHeld;io.drained.bits:=receipt
  when(io.drained.fire){receiptHeld:=false.B}
  io.poisonLatched:=poison;io.faultEvent:=faultNow;io.resetRequired:=poison||faultNow
  io.active:=active||receiptHeld;io.observedContributions:=contributions
  // A bad witness never becomes a true drained receipt. That fault requires
  // isolation/reset; no fake numeric output or fabricated producer completion.
}
