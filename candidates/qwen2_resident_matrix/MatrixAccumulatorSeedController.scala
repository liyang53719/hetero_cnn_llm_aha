// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** WORK-ONLY CANDIDATE, NOT INTEGRATED OR HARDWARE-VALIDATED.
  * One seed transaction at a time. Exactly 32 cluster writes per selected
  * 16x32 slice, ascending slice then cluster. All arithmetic is stopped while
  * this controller owns the existing accumulator write ports. No tile buffer,
  * accumulator, SFU, arithmetic lane, or alternative array is instantiated.
  *
  * leafBegin/leafCommit are broadcast transactions: the MatrixPipeline adapter
  * must AND all selected ready signals before driving valid to any leaf.
  * leafBeat is demultiplexed to exactly its selected slice. Each endpoint ACK
  * is emitted only after all 32 writes and its bank-valid commit have completed.
  */
class MatrixAccumulatorSeedController extends Module {
  val io=IO(new Bundle {
    val seed=Flipped(new MatrixAccumulatorSeedPort)
    val groupActive=Input(Bool())
    val groupTag=Input(UInt(32.W))
    val groupSequence=Input(UInt(32.W))
    val sliceMask=Input(UInt(8.W))
    val freeContexts=Input(UInt(5.W)) // !seen & !closed & !seeded this group
    val quiescent=Input(Bool()) // tags empty; all selected !busy && !out_valid
    val abort=Input(Bool())
    val leafBegin=Decoupled(new MatrixAccumulatorSeedRequest)
    val leafBeat=Decoupled(new MatrixAccumulatorSeedLeafBeat)
    val leafCommit=Decoupled(new MatrixAccumulatorSeedRequest)
    val leafAck=Flipped(Vec(8,Decoupled(new MatrixAccumulatorSeedAck)))
    val invalidate=Valid(new MatrixAccumulatorSeedRequest)
    val committed=Valid(new MatrixAccumulatorSeedRequest)
    val blockIssue=Output(Bool())
    val resetRequired=Output(Bool())
  })
  val idle::reserve::stream::commit::collect::reply::locked::Nil=Enum(7)
  val state=RegInit(idle)
  val req=Reg(new MatrixAccumulatorSeedRequest)
  val nextBeat=RegInit(0.U(9.W))
  val targetSlice=RegInit(0.U(3.W))
  val targetCluster=RegInit(0.U(5.W))
  val acknowledged=RegInit(0.U(8.W))
  val reserved=RegInit(false.B)
  val poison=RegInit(false.B)
  val responseError=RegInit(false.B)
  val totalBeats=PopCount(req.sliceMask).pad(9)<<5
  val sameGroup=io.groupActive && io.groupTag===req.groupTag &&
    io.groupSequence===req.groupSequence && io.sliceMask===req.sliceMask
  val anyLeafAck=io.leafAck.map(_.valid).reduce(_||_)
  // Leaf ACKs are registered AFTER leafCommit.fire, never combinational in
  // that handshake cycle. Early or late ACK presentation is a protocol fault,
  // including a duplicate held after the final collection handshake.
  val unexpectedAck=anyLeafAck && state=/=collect && state=/=locked
  def sameIdentity(a:MatrixAccumulatorSeedAck):Bool =
    a.groupTag===req.groupTag && a.groupSequence===req.groupSequence &&
      a.sourceGeneration===req.sourceGeneration && a.context===req.context
  def fail():Unit={poison:=true.B;responseError:=true.B;state:=reply}

  // begin is offered only after the producer has stopped new step issue and
  // drained in-flight work. A busy/live request is consumed as a terminal error,
  // never queued until that same context happens to become free later.
  io.seed.begin.ready:=state===idle && !poison && !io.abort && !anyLeafAck
  io.seed.beat.ready:=false.B
  io.seed.ack.valid:=state===reply
  io.seed.ack.bits.groupTag:=req.groupTag
  io.seed.ack.bits.groupSequence:=req.groupSequence
  io.seed.ack.bits.sourceGeneration:=req.sourceGeneration
  io.seed.ack.bits.context:=req.context
  io.seed.ack.bits.error:=responseError
  // A concurrent first step is blocked already on begin.valid, before the
  // reservation edge. This is required to avoid a quiescence check/use race.
  io.blockIssue:=state=/=idle || io.seed.begin.valid || anyLeafAck || poison
  io.resetRequired:=poison
  io.committed.valid:=io.seed.ack.fire && !poison && !responseError &&
    !io.abort && !unexpectedAck && sameGroup && io.quiescent
  io.committed.bits:=req
  io.invalidate.valid:=poison && reserved
  io.invalidate.bits:=req
  val active= !poison && !io.abort && !unexpectedAck && sameGroup && io.quiescent
  io.leafBegin.valid:=state===reserve && active
  io.leafBegin.bits:=req
  io.leafBeat.valid:=false.B
  io.leafBeat.bits.context:=req.context
  io.leafBeat.bits.slice:=targetSlice
  io.leafBeat.bits.cluster:=targetCluster
  io.leafBeat.bits.data:=io.seed.beat.bits.data
  io.leafCommit.valid:=state===commit && active
  io.leafCommit.bits:=req
  for(i<-0 until 8)io.leafAck(i).ready:=state===collect && active

  val b=io.seed.beat.bits
  val finite=(0 until 16).map(i=>b.data(i*32+30,i*32+23)=/=255.U).reduce(_&&_)
  val legalBeat=b.groupTag===req.groupTag && b.groupSequence===req.groupSequence &&
    b.sourceGeneration===req.sourceGeneration && b.context===req.context &&
    b.index===nextBeat && b.last===(nextBeat+1.U===totalBeats) && !b.error && finite
  when(state===stream && active){
    // Bad beats are consumed but never presented to a bank write port.
    io.seed.beat.ready:=Mux(legalBeat,io.leafBeat.ready,true.B)
    io.leafBeat.valid:=io.seed.beat.valid && legalBeat
  }
  when(io.seed.begin.fire){
    req:=io.seed.begin.bits;nextBeat:=0.U;targetCluster:=0.U
    targetSlice:=PriorityEncoder(io.seed.begin.bits.sliceMask)
    acknowledged:=0.U;reserved:=false.B;responseError:=false.B
    val x=io.seed.begin.bits
    val validContext=x.context<5.U && io.freeContexts(x.context)
    val legal=io.groupActive && io.quiescent && validContext &&
      x.groupTag===io.groupTag && x.groupSequence===io.groupSequence &&
      x.sliceMask.orR && x.sliceMask===io.sliceMask
    when(legal){state:=reserve}.otherwise{fail()}
  }
  when(io.leafBegin.fire){reserved:=true.B;state:=stream}
  when(io.seed.beat.fire){
    when(!legalBeat){fail()}.otherwise{
      nextBeat:=nextBeat+1.U
      when(b.last){state:=commit}.elsewhen(targetCluster===31.U){
        val remaining=VecInit((0 until 8).map(i=>req.sliceMask(i) && i.U>targetSlice)).asUInt
        targetSlice:=PriorityEncoder(remaining);targetCluster:=0.U
      }.otherwise{targetCluster:=targetCluster+1.U}
    }
  }
  when(io.leafCommit.fire){state:=collect}
  val ackFires=VecInit(io.leafAck.map(_.fire)).asUInt
  val badAck=(0 until 8).map(i=>io.leafAck(i).fire &&
    (!req.sliceMask(i)||acknowledged(i)|| !sameIdentity(io.leafAck(i).bits)||io.leafAck(i).bits.error)).reduce(_||_)
  when(state===collect){
    acknowledged:=acknowledged|ackFires
    when(badAck){fail()}.elsewhen((acknowledged|ackFires)===req.sliceMask){state:=reply}
  }
  when(io.seed.ack.fire){
    val terminalFault=poison||io.abort||unexpectedAck|| !sameGroup|| !io.quiescent
    state:=Mux(terminalFault,locked,idle)
    when(terminalFault){poison:=true.B}.otherwise{reserved:=false.B}
  }
  // No controller-only cancellation/retry. Partial physical writes and late
  // source/leaf responses stay quarantined until coordinated owner/array reset.
  when(state=/=idle && state=/=locked && state=/=reply &&
    (io.abort||unexpectedAck|| !sameGroup|| !io.quiescent)){fail()}
  // A terminal ACK already offered under backpressure is immutable. A later
  // group abort poisons the group and suppresses committed even when that held
  // ACK says the seed transfer itself succeeded. resetRequired dominates ACK.
  when(state===reply && (io.abort||unexpectedAck|| !sameGroup|| !io.quiescent)){poison:=true.B}
  // No accepted begin exists in idle, so an unsolicited ACK produces only
  // resetRequired, never an invented terminal seed response.
  when(state===idle && anyLeafAck){poison:=true.B;state:=locked}
}
