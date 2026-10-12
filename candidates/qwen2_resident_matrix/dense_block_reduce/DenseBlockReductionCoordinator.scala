// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal control profile, never a new Host command or DDR representation. */
class DenseReductionRange extends Bundle {
  val begin=UInt(16.W);val end=UInt(16.W)
}
class DenseBlockReductionRequest extends Bundle {
  val job=new QwenOwnerJob;val identity=UInt(32.W)
  val kRanges=Vec(2,new DenseReductionRange);val pairReverse=Bool()
}
class DenseBlockReductionPort extends Bundle {
  val request=Flipped(Decoupled(new DenseBlockReductionRequest))
  val result=Decoupled(new QwenOwnerResult)
  val abort=Input(Bool());val busy=Output(Bool());val resetRequired=Output(Bool())
}

/** One full public Dense -> two raw FP32 partials -> Add -> actual DDR ACKs.
  * The same three physical tile slots, Matrix owner, vector loan, finalValue
  * and iDMA are borrowed. This module instantiates control plus the existing
  * tile-to-vector bridge: no FPU, SRAM, tensor array or result payload buffer.
  *
  * A fresh N window starts only after the previous drain terminal retires.
  * A one-cycle full-job handoff lets the existing parent change/flush iDMA
  * regions before the next request. The profile supplies TWO contiguous even
  * K ranges, not a universal 1024 split; every request retains original K/N.
  *
  * Integration must connect matrixDrained/dmaDrained to the real backend
  * retirement fences and grant these tile/vector ports exclusively while
  * sumBankGranted is asserted. dense.abort and backendReset must be independent
  * external events or registered indications; never connect the coordinator's
  * own combinational aggregate resetRequired back into either input.
  * All participating modules share coordinated
  * reset, including Host, banks, Matrix, vector and DMA. Local abort never
  * erases an accepted operation. Matching tags do not prove reset freshness.
  * A consumer MUST fence an unaccepted successful result with resetRequired
  * on its acceptance edge. A held result's payload remains stable under abort.
  */
class DenseBlockReductionCoordinator extends Module {
  val io=IO(new Bundle {
    val dense=new DenseBlockReductionPort
    val window=Flipped(new FfnWindowPort(enableCounters=true,enableKWindow=true))
    val drain=Flipped(new FfnDrainPort)
    val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder=true))
    val vector=Flipped(new FfnSiluLoanPort(enableBinaryAdd=true))
    val matrixDrained=Input(Bool());val dmaDrained=Input(Bool())
    // Independent/registered backend fault, excluding our outgoing abort's
    // combinational reflection through owner.resetRequired.
    val backendReset=Input(Bool())
    val handoff=Output(Valid(new QwenOwnerJob))
    val sumBankGranted=Output(Bool());val backendAbort=Output(Bool())
  })
  val idle::partialFlush::partialIssue::partialWait::sumIssue::sumWait::drainFlush::drainIssue::drainWait::invalidate::retire::draining::reply::locked::Nil=Enum(14)
  val state=RegInit(idle);val call=Reg(new DenseBlockReductionRequest)
  val ng=RegInit(0.U(16.W));val block=RegInit(false.B)
  val poison=RegInit(false.B);val status=RegInit(0.U(8.W))
  val bytes=RegInit(0.U(64.W));val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W))
  // A physical clock counter when this source is instantiated, not a claim
  // that Python event ticks are hardware cycles or that RTL was exercised.
  val cycles=RegInit(0.U(64.W))
  val windowPending=RegInit(false.B);val drainPending=RegInit(false.B);val sumPending=RegInit(false.B)
  val bridge=Module(new DenseTileSumBridge(enableMatrixProducerOrder=true))
  io.tiles<>bridge.io.tiles;io.vector<>bridge.io.vector
  val serviceError=io.window.resetRequired || io.drain.resetRequired || io.tiles.resetRequired ||
    io.vector.resetRequired || bridge.io.resetRequired || io.backendReset
  // Owner resetRequired combinationally reflects d.abort / tiles.abort.
  // Current serviceError may fence this coordinator, but must cross a local
  // poison register before it propagates back into any backend abort wire.
  val cancel=poison || io.dense.abort
  val bad=cancel || serviceError
  val live=state=/=idle && state=/=reply && state=/=locked
  val ownerRetired= !io.window.busy && !io.drain.busy && io.matrixDrained && io.dmaDrained
  val retired=ownerRetired && io.tiles.drained && io.vector.drained && !bridge.io.busy
  val remaining=call.job.n-ng
  val cols=Mux(remaining>160.U,160.U(8.W),remaining(7,0))
  val expected=(call.job.m>>4)*cols
  val range=call.kRanges(block.asUInt)

  io.dense.request.ready:=state===idle && !bad && retired && !io.tiles.leased
  io.dense.busy:=state=/=idle && state=/=locked
  io.dense.resetRequired:=bad
  // The same metadata/counter registers hold the result; no second result
  // register or tensor storage is needed. Nothing changes them in reply.
  io.dense.result.valid:=state===reply
  io.dense.result.bits.tag:=call.job.tag;io.dense.result.bits.status:=status
  io.dense.result.bits.writeBytes:=bytes;io.dense.result.bits.usefulMacs:=useful
  io.dense.result.bits.executedMacs:=executed;io.dense.result.bits.cycles:=cycles
  io.handoff.valid:= !bad && (state===partialFlush || state===drainFlush)
  io.handoff.bits:=call.job
  io.backendAbort:=cancel;io.drain.abort:=cancel;bridge.io.abort:=cancel
  io.window.invalidateLease:=bad || state===invalidate || state===retire
  io.window.request.valid:= !bad && state===partialIssue
  io.window.request.bits.job:=call.job
  io.window.request.bits.identity:=call.identity;io.window.request.bits.ng:=ng
  io.window.request.bits.cols:=cols;io.window.request.bits.slot:=block.asUInt
  io.window.request.bits.reuseA:=block || ng=/=0.U
  val kp=io.window.request.bits.kWindow.get
  kp.enabled:=true.B;kp.begin:=range.begin;kp.end:=range.end
  kp.blockId:=Mux(block,2.U,1.U);kp.pairReverse:=call.pairReverse
  io.window.result.ready:=state===partialWait || state===draining
  io.sumBankGranted:=ownerRetired && (state===sumIssue || state===sumWait || state===draining)
  bridge.io.bankGranted:=io.sumBankGranted
  bridge.io.start.valid:= !bad && state===sumIssue && io.sumBankGranted
  bridge.io.start.bits.identity:=call.identity;bridge.io.start.bits.ng:=ng
  bridge.io.start.bits.rows:=call.job.m;bridge.io.start.bits.cols:=cols
  bridge.io.start.bits.lhsSlot:=0.U;bridge.io.start.bits.rhsSlot:=1.U;bridge.io.start.bits.outputSlot:=2.U
  io.drain.request.valid:= !bad && state===drainIssue
  io.drain.request.bits.job:=call.job;io.drain.request.bits.identity:=call.identity
  io.drain.request.bits.ng:=ng;io.drain.request.bits.cols:=cols
  io.drain.result.ready:=state===drainWait || state===draining

  def shape(r:DenseBlockReductionRequest):Bool={
    val j=r.job;val a=r.kRanges(0);val b=r.kRanges(1)
    val aEnd=j.a.pad(66)+j.m.pad(66)*j.k*Mux(j.activationBf16,2.U(3.W),4.U(3.W))
    val bEnd=j.b.pad(66)+j.k.pad(66)*j.n*Mux(j.weightBf16,2.U(3.W),4.U(3.W))
    val size=j.m.pad(66)*j.n*4.U;val dEnd=j.dst.pad(66)+size
    val spans=Seq((j.a,aEnd),(j.b,bEnd),(j.dst,dEnd))
    val disjoint=(for(i<-spans.indices;k<-i+1 until spans.size)yield
      !(spans(i)._1.pad(66)<spans(k)._2 && spans(k)._1.pad(66)<spans(i)._2)).reduce(_&&_)
    r.identity=/=0.U && j.kind===QwenOwnerKind.Dense.U && (j.m===16.U || j.m===128.U) &&
      j.m<=j.k && j.k<=1536.U && j.n>0.U && j.n<=j.k && j.n(4,0)===0.U &&
      j.k(3,0)===0.U && (!j.activationBf16 || j.k(4,0)===0.U) &&
      !j.outputBf16 && !j.materializeDenseOutput && j.writeBytes===size && disjoint &&
      spans.map{case(base,end)=>base(5,0)===0.U && end<=(BigInt(1)<<56).U}.reduce(_&&_) &&
      a.begin===0.U && a.end===b.begin && b.end===j.k && a.begin<a.end && b.begin<b.end &&
      !a.begin(0) && !a.end(0) && !b.begin(0) && !b.end(0)
  }
  def fail(code:UInt):Unit={
    poison:=true.B
    when(status===0.U){status:=Mux(code===0.U,Status.Protocol.U,code)}
    state:=draining
  }
  when(io.dense.request.fire){
    call:=io.dense.request.bits;ng:=0.U;block:=false.B
    bytes:=0.U;useful:=0.U;executed:=0.U;cycles:=0.U;status:=0.U
    when(shape(io.dense.request.bits)){state:=partialFlush}.otherwise{fail(Status.Malformed.U)}
  }
  when(live){cycles:=cycles+1.U}
  when(state===partialFlush && !bad){state:=partialIssue}
  when(state===drainFlush && !bad){state:=drainIssue}
  when(io.window.request.fire){windowPending:=true.B;state:=partialWait}
  when(io.window.result.fire){
    val r=io.window.result.bits;val k=r.kWindow.get
    windowPending:=false.B
    // Real accepted terminals only. A K partial cannot credit DDR traffic.
    when(windowPending && r.ddrWriteBytes===0.U){
      useful:=useful+r.usefulMacs.get;executed:=executed+r.executedMacs.get
    }
    val exact=r.tag===call.job.tag && r.identity===call.identity && r.ng===ng &&
      r.rows===call.job.m && r.cols===cols && r.slot===block.asUInt &&
      k.enabled && k.begin===range.begin && k.end===range.end &&
      k.blockId===Mux(block,2.U,1.U) && k.pairReverse===call.pairReverse &&
      r.committed && r.producedBeats===expected && r.ddrWriteBytes===0.U && io.window.leaseValid
    when(!windowPending || !io.window.busy || io.drain.result.fire || r.status=/=0.U || !exact || bad){fail(r.status)}
      .elsewhen(state===partialWait){
        when(block){state:=sumIssue}.otherwise{block:=true.B;state:=partialFlush}
      }
  }
  when(bridge.io.start.fire){sumPending:=true.B;state:=sumWait}
  when(bridge.io.complete){
    when(state=/=sumWait || !sumPending || bad || !io.tiles.drained || !io.vector.drained || !ownerRetired){
      fail(Status.Protocol.U)
    }.otherwise{sumPending:=false.B;state:=drainFlush}
  }
  when(io.drain.request.fire){drainPending:=true.B;state:=drainWait}
  when(io.drain.result.fire){
    val r=io.drain.result.bits
    drainPending:=false.B
    when(drainPending){
      bytes:=bytes+r.ddrWriteBytes;useful:=useful+r.usefulMacs;executed:=executed+r.executedMacs
    }
    val exact=r.tag===call.job.tag && r.identity===call.identity && r.ng===ng &&
      r.rows===call.job.m && r.cols===cols && r.committed && r.consumedBeats===expected &&
      r.ddrWriteBytes===call.job.m.pad(64)*cols*4.U && !io.tiles.leased && io.tiles.drained
    when(!drainPending || !io.drain.busy || io.window.result.fire || r.status=/=0.U || !exact || bad){fail(r.status)}
      .elsewhen(state===drainWait){
        when(ng+cols===call.job.n){
          when(bytes+r.ddrWriteBytes===call.job.writeBytes){state:=invalidate}.otherwise{fail(Status.Protocol.U)}
        }.otherwise{ng:=ng+cols;block:=false.B;state:=partialFlush}
      }
  }
  when(state===invalidate && !bad){state:=retire}
  when(state===retire && !bad && retired && !io.tiles.leased && !io.window.leaseValid &&
      !windowPending && !drainPending && !sumPending){state:=reply}
  val unsolicited=(io.window.result.valid && !io.window.result.ready) ||
    (io.drain.result.valid && !io.drain.result.ready)
  io.dense.resetRequired:=bad || unsolicited
  when(unsolicited){
    when(live){fail(Status.Protocol.U)}.otherwise{poison:=true.B}
  }
  val explicitError=(io.window.result.fire && io.window.result.bits.status=/=0.U) ||
    (io.drain.result.fire && io.drain.result.bits.status=/=0.U)
  when(bad && live && !explicitError){fail(Status.Protocol.U)}
  when(io.dense.abort || serviceError){poison:=true.B}
  when((poison || bad) && sumPending && !bridge.io.busy && io.vector.drained && io.tiles.drained){sumPending:=false.B}
  // Quarantined live tiles need not release after an error. Every accepted
  // operation still retires before the failed public terminal can be offered.
  when(state===draining && retired && !windowPending && !drainPending && !sumPending){
    when(status===0.U){status:=Status.Protocol.U};state:=reply
  }
  when(io.dense.result.fire){state:=Mux(poison || bad || unsolicited,locked,idle)}
}
