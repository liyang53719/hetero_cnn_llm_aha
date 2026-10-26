// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Concrete private producer/consumer/owner wiring. The sole existing physical
  * scalar must be connected to primitiveRequest/primitiveResult by a future
  * fixed-fabric successor. This module creates ZERO Scalar/ALU/Matrix objects.
  * It is not the full4096 top or a replacement for the final DDR/block fence.
  */
class UnifiedMoeSharedScalarClientV2 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedScalarTileLeaseV2))
    val route=Flipped(Decoupled(new UnifiedTaggedMoeRouteV2))
    val dispatch=Decoupled(new UnifiedTaggedMoeDispatchV2)
    val returned=Flipped(Decoupled(new UnifiedTaggedMoeReturnV2))
    val result=Decoupled(new MoeBf16TileResult)
    val primitiveRequest=Decoupled(new ScalarRequest)
    val primitiveResult=Flipped(Decoupled(new UnifiedScalarResult))
    val resetRequired=Output(Bool())
    val issuedOperations=Output(UInt(17.W));val completedOperations=Output(UInt(17.W))
  })
  val client=Module(new UnifiedMoeTileScalarBridgeV2)
  val producer=Module(new UnifiedMoeProducerBindingV2)
  val arbiter=Module(new UnifiedScalarOwnerArbiterV2)
  val globalPoison=client.io.resetRequired || producer.io.resetRequired || arbiter.io.resetRequired
  io.resetRequired:=globalPoison
  io.begin.ready:=client.io.begin.ready && !globalPoison
  client.io.begin.valid:=io.begin.valid && !globalPoison;client.io.begin.bits:=io.begin.bits
  // Registered cross-module error state avoids a combinational poison loop.
  // Immediate producer faults still reach the arbiter's commit-edge decision.
  client.io.externalProtocolFault:=producer.io.poisonLatched || arbiter.io.poisonLatched
  arbiter.io.externalPoison:=producer.io.resetRequired || client.io.resetRequired
  arbiter.io.ownerAcquire<>client.io.ownerAcquire
  arbiter.io.request<>client.io.scalarRequest;client.io.scalarResult<>arbiter.io.result
  arbiter.io.releaseIntent<>client.io.releaseIntent;client.io.releaseAck<>arbiter.io.releaseAck
  arbiter.io.ownerFault<>client.io.ownerFault
  client.io.producerReady:=producer.io.start.ready
  producer.io.start.valid:=client.io.producerStart;producer.io.start.bits:=client.io.producerContext
  client.io.contribution<>producer.io.contribution
  client.io.producerDrained<>producer.io.drained
  producer.io.route<>io.route;io.dispatch<>producer.io.dispatch;producer.io.returned<>io.returned
  io.result<>client.io.result
  io.primitiveRequest<>arbiter.io.primitiveRequest
  arbiter.io.primitiveResult<>io.primitiveResult
  io.issuedOperations:=arbiter.io.issuedOperations;io.completedOperations:=arbiter.io.completedOperations
}
