// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One owner-master for the complete MoE-reduce typed stage. NOT a per-model
  * bank, NOT the all-operator scalar scheduler. The physical scalar is external
  * and unique; no Scalar/ALU instance is created here.
  *
  * Operation completion never releases an owner. Only a valid stable release
  * intent plus this arbiter's own real primitive/return drain can commit the
  * owner fence. Its acknowledgment is registered and held unchanged.
  * Reset must isolate this arbiter, primitive, master and all response paths.
  */
class UnifiedScalarOwnerArbiterV2 extends Module {
  val io=IO(new Bundle {
    val ownerAcquire=Flipped(Decoupled(new UnifiedScalarTileLeaseV2))
    val request=Flipped(Decoupled(new UnifiedOwnedScalarRequestV2))
    val result=Decoupled(new UnifiedOwnedScalarResultV2)
    val releaseIntent=Flipped(Decoupled(new UnifiedScalarTileReleaseIntentV2))
    val releaseAck=Decoupled(new UnifiedScalarTileReleaseAckV2)
    val ownerFault=Flipped(Valid(new MoeBf16TileIdentity))
    val externalPoison=Input(Bool()) // Error-only sideband, never a drain proof.
    val primitiveRequest=Decoupled(new ScalarRequest)
    val primitiveResult=Flipped(Decoupled(new UnifiedScalarResult))
    val poisonLatched=Output(Bool());val faultEvent=Output(Bool())
    val resetRequired=Output(Bool());val active=Output(Bool())
    val responseQuarantined=Output(Bool())
    val issuedOperations=Output(UInt(17.W));val completedOperations=Output(UInt(17.W))
  })
  val idle::running::acknowledging::Nil=Enum(3)
  val state=RegInit(idle);val owner=Reg(new UnifiedScalarTileLeaseV2)
  val previousOwnerValid=RegInit(false.B)
  val issued=RegInit(0.U(17.W));val completed=RegInit(0.U(17.W))
  val offerHeld=RegInit(false.B);val offer=Reg(new UnifiedOwnedScalarRequestV2)
  val pending=RegInit(false.B);val pendingTag=Reg(new UnifiedScalarOperationTagV2)
  val quarantine=RegInit(false.B) // Unknown untagged data destroys correlation until isolated reset.
  val responseHeld=RegInit(false.B);val response=Reg(new UnifiedOwnedScalarResultV2)
  val ack=Reg(new UnifiedScalarTileReleaseAckV2)
  val poison=RegInit(false.B)
  val incoming=io.ownerAcquire.bits
  val (decoded,known)=UnifiedRuntimeProfile.decode(incoming.context.launch.profileId)
  val sameTransaction=incoming.identity.transactionId===owner.identity.transactionId
  val laterTile=incoming.identity.token>owner.identity.token ||
    (incoming.identity.token===owner.identity.token && incoming.identity.tileOrdinal>owner.identity.tileOrdinal)
  // Fixed typed-stage schedule: strictly increasing (transaction,token,tile).
  // This rejects nonconsecutive reuse without a per-tile bitmap/cache.
  val freshOwner= !previousOwnerValid || incoming.identity.transactionId>owner.identity.transactionId ||
    (sameTransaction && laterTile && incoming.context.asUInt===owner.context.asUInt)
  val acquireLegal=known && decoded.asUInt===incoming.context.profile.asUInt && decoded.mlp===1.U &&
    decoded.expertCount===256.U && decoded.expertsPerToken===8.U && decoded.sharedFfn===512.U &&
    incoming.context.launch.version===1.U && incoming.context.launch.opcode===0.U &&
    incoming.context.launch.tokens>=1.U && incoming.context.launch.tokens<=128.U &&
    incoming.identity.transactionId===incoming.context.transactionId &&
    incoming.identity.token<incoming.context.launch.tokens && decoded.hidden(4,0)===0.U &&
    incoming.identity.tileOrdinal<(decoded.hidden>>5) && freshOwner
  val opIdentity=io.request.bits.tag.tile.asUInt===owner.identity.asUInt
  val opSerial=issued<65536.U && io.request.bits.tag.operationSerial===issued(15,0)
  val operationLegal=state===running && opIdentity && opSerial
  val intentIdentity=io.releaseIntent.bits.identity.asUInt===owner.identity.asUInt
  val intentStatusLegal=io.releaseIntent.bits.status===Status.Ok.U ||
    (io.releaseIntent.bits.status>=Status.Malformed.U && io.releaseIntent.bits.status<=Status.Permission.U)
  val intentLegal=state===running && intentIdentity && intentStatusLegal && io.releaseIntent.bits.drained &&
    io.releaseIntent.bits.issuedOperations===issued && io.releaseIntent.bits.completedOperations===completed
  val badAcquire=state===idle && io.ownerAcquire.valid && !acquireLegal
  val badRequest=io.request.valid && !operationLegal
  val badIntent=io.releaseIntent.valid && !intentLegal
  val concurrentOpAndIntent=state===running && (io.request.valid || offerHeld) && io.releaseIntent.valid
  // Untagged primitive data without a captured actual request has no owner.
  // Never consume or attach the next owner tag to that unknown response.
  val unknownPrimitiveResult=io.primitiveResult.valid && !pending
  when(unknownPrimitiveResult){quarantine:=true.B}
  io.responseQuarantined:=quarantine || unknownPrimitiveResult
  val faults=badAcquire || badRequest || badIntent || concurrentOpAndIntent ||
    unknownPrimitiveResult || io.ownerFault.valid || io.externalPoison
  val poisoned=poison || faults
  when(faults){poison:=true.B}
  io.poisonLatched:=poison;io.faultEvent:=faults;io.resetRequired:=poisoned
  io.active:=state=/=idle;io.issuedOperations:=issued;io.completedOperations:=completed
  io.ownerAcquire.ready:=state===idle && !poisoned && acquireLegal &&
    !offerHeld && !pending && !responseHeld && !quarantine && !io.primitiveResult.valid && io.primitiveRequest.ready
  when(io.ownerAcquire.fire){
    owner:=incoming;previousOwnerValid:=true.B;issued:=0.U;completed:=0.U;state:=running
  }

  // Capture a stable one-entry offer before exposing primitive valid. Once
  // offered, valid/payload cannot be withdrawn by a later intent/fault. Client
  // acceptance and actual primitive issue are distinct, individually tracked
  // boundaries; an unissued buffered offer also prevents owner release.
  val canCapture=state===running && !offerHeld && !pending && !responseHeld &&
    !quarantine && !unknownPrimitiveResult && !io.releaseIntent.valid
  io.request.ready:=canCapture && operationLegal
  when(io.request.fire){offer:=io.request.bits;offerHeld:=true.B}
  io.primitiveRequest.valid:=offerHeld
  io.primitiveRequest.bits:=offer.payload
  when(io.primitiveRequest.fire){
    offerHeld:=false.B;pending:=true.B;pendingTag:=offer.tag;issued:=issued+1.U
  }
  // If unknown data appears after an offer is already irrevocably held, that
  // offer may still fire. Correlation is nevertheless permanently quarantined:
  // neither the old held data nor any later data may retire the new pending.
  // No producer receipt/poison/valid drop can clear this; isolate+reset all peers.
  io.primitiveResult.ready:=state===running && pending && !responseHeld &&
    !quarantine && !unknownPrimitiveResult
  when(io.primitiveResult.fire){
    response.tag:=pendingTag;response.payload:=io.primitiveResult.bits
    pending:=false.B;responseHeld:=true.B
  }
  io.result.valid:=responseHeld;io.result.bits:=response
  when(io.result.fire){responseHeld:=false.B;completed:=completed+1.U}

  val ownDrained= !offerHeld && !pending && !responseHeld && !quarantine && issued===completed &&
    !io.primitiveResult.valid && io.primitiveRequest.ready
  io.releaseIntent.ready:=state===running && intentLegal && ownDrained
  when(io.releaseIntent.fire){
    ack.identity:=owner.identity
    ack.status:=Mux(poisoned,Status.Protocol.U,io.releaseIntent.bits.status)
    ack.drained:=true.B;ack.resetRequired:=poisoned
    state:=acknowledging
  }
  io.releaseAck.valid:=state===acknowledging;io.releaseAck.bits:=ack
  when(io.releaseAck.fire){state:=idle}
  // Late faults cannot mutate held ack/result. Sticky global poison prevents
  // the next acquisition and must be consulted by the final block fence.
}
