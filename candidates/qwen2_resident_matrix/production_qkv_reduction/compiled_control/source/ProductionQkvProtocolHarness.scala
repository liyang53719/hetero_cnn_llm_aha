// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Candidate complete-public21 control binding. Jobs originate only from the
  * real metadata parser. Reduction uses the actual existing coordinator/bridge;
  * all arithmetic/storage service ports remain explicit external boundaries.
  * No backend result or tile value is numerical acceptance in a control test.
  */
class ProductionQkvProtocolHarness extends Module {
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunch));val result=Decoupled(new HostCommandResult)
    val completion=Decoupled(UInt(56.W));val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val ordinaryJob=Decoupled(new QwenOwnerJob);val ordinaryDone=Flipped(Decoupled(new QwenOwnerResult))
    val resident=Flipped(new FfnResidentPort)
    val window=Flipped(new FfnWindowPort(enableCounters=true,enableKWindow=true))
    val drain=Flipped(new FfnDrainPort);val tiles=Flipped(new FfnTilePort(enableMatrixProducerOrder=true))
    val vector=Flipped(new FfnSiluLoanPort(enableBinaryAdd=true))
    val matrixDrained=Input(Bool());val dmaDrained=Input(Bool())
    val backendReset=Input(Bool());val abort=Input(Bool())
    val prefixWorkspace=Output(new TransposedPrefixWorkspace(2560))
    val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W));val resetRequired=Output(Bool())
    val reductionAccepted=Output(Valid(new QwenOwnerJob))
    val reductionReturned=Output(Valid(new QwenOwnerResult))
    val reductionResultHeld=Input(Bool())
    val reductionOffered=Output(Valid(new QwenOwnerResult))
    val handoff=Output(Valid(new QwenOwnerJob))
  })
  val shape=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
  val cmd=Module(new HostBlockCommands(shape,eventSlots=32,maxCommands=21,bf16Weights=true,
    enableTransposedDown=true,enableResidentFfn=true,numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2))
  val router=Module(new Public21QkvReductionRouter)
  // Actual production classes, but this is a service-boundary test harness,
  // NOT QwenOwnerKernel. No production debt register is instantiated here.
  val unavailable=router.io.resetRequired || cmd.io.resetRequired
  cmd.io.launch.valid:=io.launch.valid && !unavailable
  cmd.io.launch.bits:=io.launch.bits;io.launch.ready:=cmd.io.launch.ready && !unavailable
  io.result<>cmd.io.result;io.completion<>cmd.io.completion
  io.memory<>cmd.io.memory;cmd.io.response<>io.response
  io.pc:=cmd.io.pc;io.issuedJobs:=cmd.io.issuedJobs
  io.prefixWorkspace:=cmd.io.prefixWorkspace.get;io.resetRequired:=unavailable
  router.io.job<>cmd.io.job
  // TEST-ONLY transport backpressure. It never changes router terminal payload.
  val hold=io.reductionResultHeld && router.io.reductionOwns
  cmd.io.done.valid:=router.io.done.valid && !hold
  cmd.io.done.bits:=router.io.done.bits
  router.io.done.ready:=cmd.io.done.ready && !hold
  val rp=cmd.io.resident.get;val rh=router.io.residentHost
  rh.request<>rp.request;rp.result<>rh.result;rp.busy:=rh.busy
  rp.resetRequired:=rh.resetRequired;rh.abort:=rp.abort || io.abort
  io.resident<>router.io.resident
  io.ordinaryJob<>router.io.ordinaryJob;router.io.ordinaryDone<>io.ordinaryDone
  io.window<>router.io.window;io.drain<>router.io.drain
  io.tiles<>router.io.tiles;io.vector<>router.io.vector
  router.io.matrixDrained:=io.matrixDrained;router.io.dmaDrained:=io.dmaDrained
  router.io.backendReset:=io.backendReset
  // Resident service traffic is explicitly absent in this first harness.
  // The externally scripted resident terminal tests ownership only.
  val w=router.io.residentWindow
  w.request.valid:=false.B;w.request.bits:=0.U.asTypeOf(w.request.bits)
  w.result.ready:=true.B;w.invalidateLease:=false.B
  val dr=router.io.residentDrain
  dr.request.valid:=false.B;dr.request.bits:=0.U.asTypeOf(dr.request.bits)
  dr.result.ready:=true.B;dr.abort:=false.B
  val t=router.io.residentTiles
  t.control.valid:=false.B;t.control.bits:=0.U.asTypeOf(t.control.bits)
  t.read.valid:=false.B;t.read.bits:=0.U.asTypeOf(t.read.bits)
  t.write.valid:=false.B;t.write.bits:=0.U.asTypeOf(t.write.bits)
  t.response.ready:=true.B;t.abort:=false.B
  val v=router.io.residentVector
  v.request.valid:=false.B;v.request.bits:=0.U.asTypeOf(v.request.bits)
  v.result.ready:=true.B;v.abort:=false.B
  router.io.residentHandoff.valid:=false.B
  router.io.residentHandoff.bits:=0.U.asTypeOf(router.io.residentHandoff.bits)
  io.handoff:=router.io.handoff
  val role=cmd.io.job.bits.tag(15,0)===1.U || cmd.io.job.bits.tag(15,0)===4.U || cmd.io.job.bits.tag(15,0)===7.U
  io.reductionAccepted.valid:=router.io.job.fire && role
  io.reductionAccepted.bits:=router.io.job.bits
  io.reductionOffered.valid:=router.io.done.valid && router.io.reductionOwns
  io.reductionOffered.bits:=router.io.done.bits
  io.reductionReturned.valid:=router.io.done.fire && router.io.reductionOwns
  io.reductionReturned.bits:=router.io.done.bits
}
