// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal exclusive ownership only. No payload FIFO, FPU, bank or DMA.
  * Original Host parser supplies validated public21 jobs. Ordinary arithmetic
  * and resident FFN remain in the original production kernel. Selection is
  * retained until the selected terminal handshake, including abort/drain.
  */
class Public21QkvReductionRouter extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val ordinaryJob=Decoupled(new QwenOwnerJob);val ordinaryDone=Flipped(Decoupled(new QwenOwnerResult))
    val residentHost=new FfnResidentPort;val resident=Flipped(new FfnResidentPort)
    val residentWindow=new FfnWindowPort(enableCounters=true)
    val residentDrain=new FfnDrainPort
    val residentTiles=new FfnTilePort(enableMatrixProducerOrder=true)
    val residentVector=new FfnSiluLoanPort
    val window=Flipped(new FfnWindowPort(enableCounters=true,enableKWindow=true))
    val drain=Flipped(new FfnDrainPort)
    val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder=true))
    val vector=Flipped(new FfnSiluLoanPort(enableBinaryAdd=true))
    val residentHandoff=Input(Valid(new QwenOwnerJob));val handoff=Output(Valid(new QwenOwnerJob))
    val matrixDrained=Input(Bool());val dmaDrained=Input(Bool())
    val backendReset=Input(Bool());val resetRequired=Output(Bool());val backendAbort=Output(Bool())
    val reductionOwns=Output(Bool())
  })
  val idle::ordinary::reducing::residentRun::Nil=Enum(4)
  val state=RegInit(idle);val fault=RegInit(false.B)
  val reduction=Module(new DenseBlockReductionCoordinator)
  val j=io.job.bits
  // Private semantic marker from the original Commands' validated official
  // profile0 Q/K/V roles. Guard remaps tag to a persistent physical sequence;
  // low tag bits are transport identity, never a public21 arithmetic selector.
  // Keep the original shape rejection and K-window/pair-reverse recipe below.
  // A matching shape alone does not select this route or create authority.
  val role=j.public21Reduction
  val shape=j.kind===QwenOwnerKind.Dense.U && j.k===1536.U &&
    (j.n===1536.U || j.n===256.U) && (j.m===16.U || j.m===128.U) &&
    j.weightBf16 && !j.activationBf16 && !j.outputBf16 && !j.materializeDenseOutput &&
    j.writeBytes===j.m.pad(64)*j.n*4.U && j.c===0.U
  val malformed=io.job.valid && role && !shape
  val stray=(io.ordinaryDone.valid && state=/=ordinary) ||
    (io.resident.result.valid && state=/=residentRun) ||
    (reduction.io.dense.result.valid && state=/=reducing)
  val bad=fault || io.backendReset || io.residentHost.abort || malformed || stray ||
    reduction.io.dense.resetRequired || io.resident.resetRequired
  when(bad){fault:=true.B}
  val canStart=state===idle && !bad && io.matrixDrained && io.dmaDrained &&
    io.tiles.drained && !io.tiles.leased && io.vector.drained && !io.window.busy && !io.drain.busy
  // Resident gets deterministic priority if both entrypoints are offered.
  val jobAllowed=canStart && !io.residentHost.request.valid
  io.ordinaryJob.valid:=io.job.valid && !role && jobAllowed
  io.ordinaryJob.bits:=j
  reduction.io.dense.request.valid:=io.job.valid && role && shape && jobAllowed
  reduction.io.dense.request.bits.job:=j
  reduction.io.dense.request.bits.identity:=j.tag+1.U
  reduction.io.dense.request.bits.kRanges(0).begin:=0.U
  reduction.io.dense.request.bits.kRanges(0).end:=1024.U
  reduction.io.dense.request.bits.kRanges(1).begin:=1024.U
  reduction.io.dense.request.bits.kRanges(1).end:=1536.U
  reduction.io.dense.request.bits.pairReverse:=true.B
  io.job.ready:=jobAllowed && Mux(role,reduction.io.dense.request.ready,io.ordinaryJob.ready)
  io.resident.request.valid:=io.residentHost.request.valid && canStart
  io.resident.request.bits:=io.residentHost.request.bits
  io.residentHost.request.ready:=canStart && io.resident.request.ready
  when(io.job.fire){state:=Mux(role,reducing,ordinary)}
  when(io.residentHost.request.fire){state:=residentRun}
  io.done.bits:=Mux(state===reducing,reduction.io.dense.result.bits,io.ordinaryDone.bits)
  // A terminal already offered by the selected owner must still retire after
  // a late fault. Keep its payload stable; the original Host parser consumes
  // resetRequired on this same handshake and converts success to Protocol.
  // Suppressing valid/ready here would strand Host waitDone indefinitely.
  io.done.valid:=Mux(state===reducing,reduction.io.dense.result.valid,
    state===ordinary && io.ordinaryDone.valid)
  io.ordinaryDone.ready:=state===ordinary && io.done.ready
  reduction.io.dense.result.ready:=state===reducing && io.done.ready
  io.residentHost.result.bits:=io.resident.result.bits
  val residentReturn=state===residentRun
  io.residentHost.result.valid:=residentReturn && io.resident.result.valid
  io.resident.result.ready:=residentReturn && io.residentHost.result.ready
  when(io.done.fire || io.residentHost.result.fire){state:=idle}
  io.residentHost.busy:=state=/=idle || io.resident.busy
  io.residentHost.resetRequired:=bad;io.resetRequired:=bad
  // Never feed the combinational aggregate back into abort. Sticky fault is
  // registered; external abort/backendReset are independent inputs.
  val cancel=fault || io.residentHost.abort || io.backendReset
  io.resident.abort:=cancel
  reduction.io.dense.abort:=cancel
  reduction.io.backendReset:=io.backendReset
  reduction.io.matrixDrained:=io.matrixDrained;reduction.io.dmaDrained:=io.dmaDrained
  io.backendAbort:=reduction.io.backendAbort
  val q=state===reducing;val r=state===residentRun
  io.reductionOwns:=q
  io.handoff.valid:=(q && reduction.io.handoff.valid) || (r && io.residentHandoff.valid)
  io.handoff.bits:=Mux(q,reduction.io.handoff.bits,io.residentHandoff.bits)

  // Shared services: response ownership stays selected through every stall.
  val w=io.window;val rw=io.residentWindow;val qw=reduction.io.window
  val residentRequest=WireDefault(0.U.asTypeOf(new FfnWindowRequest(enableKWindow=true)))
  for((name,field)<-rw.request.bits.elements){residentRequest.elements(name):=field}
  residentRequest.kWindow.get.enabled:=false.B
  w.request.valid:=Mux(q,qw.request.valid,r && rw.request.valid)
  w.request.bits:=Mux(q,qw.request.bits,residentRequest)
  qw.request.ready:=q && w.request.ready;rw.request.ready:=r && w.request.ready
  qw.result.valid:=q && w.result.valid;qw.result.bits:=w.result.bits
  rw.result.valid:=r && w.result.valid
  for((name,field)<-rw.result.bits.elements){field:=w.result.bits.elements(name)}
  w.result.ready:=Mux(q,qw.result.ready,r && rw.result.ready)
  w.invalidateLease:=Mux(q,qw.invalidateLease,r && rw.invalidateLease) || cancel
  for(p<-Seq(qw,rw)){p.busy:=w.busy;p.leaseValid:=w.leaseValid;p.resetRequired:=w.resetRequired}

  val d=io.drain;val rd=io.residentDrain;val qd=reduction.io.drain
  d.request.valid:=Mux(q,qd.request.valid,r && rd.request.valid)
  d.request.bits:=Mux(q,qd.request.bits,rd.request.bits)
  qd.request.ready:=q && d.request.ready;rd.request.ready:=r && d.request.ready
  qd.result.valid:=q && d.result.valid;rd.result.valid:=r && d.result.valid
  qd.result.bits:=d.result.bits;rd.result.bits:=d.result.bits
  d.result.ready:=Mux(q,qd.result.ready,r && rd.result.ready)
  d.abort:=Mux(q,qd.abort,r && rd.abort) || cancel
  for(p<-Seq(qd,rd)){p.busy:=d.busy;p.resetRequired:=d.resetRequired}

  val t=io.tiles;val rt=io.residentTiles;val qt=reduction.io.tiles
  def requests[T<:Data](out:DecoupledIO[T],left:DecoupledIO[T],right:DecoupledIO[T]):Unit={
    out.valid:=Mux(q,left.valid,r && right.valid);out.bits:=Mux(q,left.bits,right.bits)
    left.ready:=q && out.ready;right.ready:=r && out.ready
  }
  requests(t.control,qt.control,rt.control);requests(t.write,qt.write,rt.write);requests(t.read,qt.read,rt.read)
  qt.response.valid:=q && t.response.valid;rt.response.valid:=r && t.response.valid
  qt.response.bits:=t.response.bits;rt.response.bits:=t.response.bits
  t.response.ready:=Mux(q,qt.response.ready,r && rt.response.ready)
  t.abort:=Mux(q,qt.abort,r && rt.abort) || cancel
  for(p<-Seq(qt,rt)){p.busy:=t.busy;p.leased:=t.leased;p.drained:=t.drained;p.resetRequired:=t.resetRequired;p.state:=t.state}

  val v=io.vector;val rv=io.residentVector;val qv=reduction.io.vector
  v.request.valid:=Mux(q,qv.request.valid,r && rv.request.valid)
  v.request.bits.gate:=Mux(q,qv.request.bits.gate,rv.request.bits.gate)
  v.request.bits.up:=Mux(q,qv.request.bits.up,rv.request.bits.up)
  v.request.bits.binaryAdd.get:=Mux(q,qv.request.bits.binaryAdd.get,false.B)
  qv.request.ready:=q && v.request.ready;rv.request.ready:=r && v.request.ready
  qv.result.valid:=q && v.result.valid;rv.result.valid:=r && v.result.valid
  qv.result.bits:=v.result.bits;rv.result.bits:=v.result.bits
  v.result.ready:=Mux(q,qv.result.ready,r && rv.result.ready)
  v.abort:=Mux(q,qv.abort,r && rv.abort) || cancel
  for(p<-Seq(qv,rv)){p.busy:=v.busy;p.drained:=v.drained;p.resetRequired:=v.resetRequired}
  assert(!(io.job.fire && io.residentHost.request.fire))
  assert(!(q && r))
}
