// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Candidate complete-public21 control binding. Jobs originate only from the
  * real metadata parser. Reduction uses the actual existing coordinator/bridge;
  * all arithmetic/storage service ports remain explicit external boundaries.
  * No backend result or tile value is numerical acceptance in a control test.
  */
class Public21DispatchHarness extends Module {
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
    val reductionAccepted=Output(Valid(new DenseBlockReductionRequest))
    val reductionReturned=Output(Valid(new QwenOwnerResult))
    val reductionResultHeld=Input(Bool())
    val reductionOffered=Output(Valid(new QwenOwnerResult))
    val sumBankGranted=Output(Bool());val handoff=Output(Valid(new QwenOwnerJob))
  })
  val shape=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
  val cmd=Module(new HostBlockCommands(shape,eventSlots=32,maxCommands=21,bf16Weights=true,
    enableTransposedDown=true,enableResidentFfn=true,numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2))
  val reduction=Module(new DenseBlockReductionCoordinator)
  val active=RegInit(false.B);val reductionRoute=RegInit(false.B)
  val residentActive=RegInit(false.B)
  val fault=RegInit(false.B)
  val unexpectedOrdinary=io.ordinaryDone.valid && (!active || reductionRoute)
  val unexpectedReduction=reduction.io.dense.result.valid && (!active || !reductionRoute)
  val unexpectedResident=io.resident.result.valid && !residentActive
  val externalFault=io.abort || io.backendReset || reduction.io.dense.resetRequired || io.resident.resetRequired
  val unavailable=fault || externalFault || unexpectedOrdinary || unexpectedReduction || unexpectedResident
  when(externalFault || unexpectedOrdinary || unexpectedReduction || unexpectedResident){fault:=true.B}
  io.launch.ready:=cmd.io.launch.ready && !unavailable
  cmd.io.launch.valid:=io.launch.valid && !unavailable;cmd.io.launch.bits:=io.launch.bits
  io.result<>cmd.io.result;io.completion<>cmd.io.completion;io.memory<>cmd.io.memory;cmd.io.response<>io.response
  io.pc:=cmd.io.pc;io.issuedJobs:=cmd.io.issuedJobs
  io.prefixWorkspace:=cmd.io.prefixWorkspace.get
  val residentPort=cmd.io.resident.get
  io.resident.request.valid:=residentPort.request.valid && !unavailable && !active && !residentActive
  io.resident.request.bits:=residentPort.request.bits
  residentPort.request.ready:=io.resident.request.ready && !unavailable && !active && !residentActive
  residentPort.result.valid:=io.resident.result.valid && residentActive
  residentPort.result.bits:=io.resident.result.bits
  io.resident.result.ready:=residentPort.result.ready && residentActive
  residentPort.busy:=io.resident.busy
  io.resident.abort:=residentPort.abort || fault || io.abort || io.backendReset
  when(io.resident.request.fire){residentActive:=true.B}
  when(io.resident.result.fire){residentActive:=false.B}
  // The combinational aggregate only fences acceptance. Abort feedback uses
  // independent external signals or the registered fault, never this aggregate.
  cmd.io.resident.get.resetRequired:=unavailable
  io.resetRequired:=cmd.io.resetRequired || unavailable
  val j=cmd.io.job.bits
  val qkvRole=j.tag(15,0)===1.U || j.tag(15,0)===4.U || j.tag(15,0)===7.U
  val qkvShape=j.kind===QwenOwnerKind.Dense.U && j.k===1536.U &&
    (j.n===1536.U || j.n===256.U) && (j.m===16.U || j.m===128.U) &&
    j.weightBf16 && !j.activationBf16 && !j.outputBf16 && !j.materializeDenseOutput &&
    j.writeBytes===j.m.pad(64)*j.n*4.U && j.c===0.U
  // The enabled parser has already checked all21 official public opcodes and
  // typed producer roles. Both role and full internal contract select Q/K/V.
  val chooseReduction=qkvRole && qkvShape
  val malformedRoute=cmd.io.job.valid && qkvRole && !qkvShape
  when(malformedRoute){fault:=true.B}
  val canIssue= !active && !residentActive && !unavailable && !malformedRoute
  reduction.io.dense.request.valid:=cmd.io.job.valid && chooseReduction && canIssue
  reduction.io.dense.request.bits.job:=j
  reduction.io.dense.request.bits.identity:=j.tag+1.U
  reduction.io.dense.request.bits.kRanges(0).begin:=0.U
  reduction.io.dense.request.bits.kRanges(0).end:=1024.U
  reduction.io.dense.request.bits.kRanges(1).begin:=1024.U
  reduction.io.dense.request.bits.kRanges(1).end:=1536.U
  reduction.io.dense.request.bits.pairReverse:=true.B
  io.ordinaryJob.valid:=cmd.io.job.valid && !chooseReduction && canIssue;io.ordinaryJob.bits:=j
  cmd.io.job.ready:=canIssue && Mux(chooseReduction,reduction.io.dense.request.ready,io.ordinaryJob.ready)
  when(cmd.io.job.fire){active:=true.B;reductionRoute:=chooseReduction}
  val reductionValid=reduction.io.dense.result.valid && !io.reductionResultHeld
  cmd.io.done.valid:=active && Mux(reductionRoute,reductionValid,io.ordinaryDone.valid)
  cmd.io.done.bits:=Mux(reductionRoute,reduction.io.dense.result.bits,io.ordinaryDone.bits)
  reduction.io.dense.result.ready:=active && reductionRoute && cmd.io.done.ready && !io.reductionResultHeld
  io.ordinaryDone.ready:=active && !reductionRoute && cmd.io.done.ready
  when(cmd.io.done.fire){active:=false.B}
  // The accepted request fixes the return route through all backpressure.
  assert(!(reduction.io.dense.request.fire && io.ordinaryJob.fire))
  reduction.io.dense.abort:=io.abort || fault;reduction.io.backendReset:=io.backendReset
  reduction.io.matrixDrained:=io.matrixDrained;reduction.io.dmaDrained:=io.dmaDrained
  io.window<>reduction.io.window;io.drain<>reduction.io.drain
  io.tiles<>reduction.io.tiles;io.vector<>reduction.io.vector
  io.sumBankGranted:=reduction.io.sumBankGranted;io.handoff:=reduction.io.handoff
  io.reductionAccepted.valid:=reduction.io.dense.request.fire;io.reductionAccepted.bits:=reduction.io.dense.request.bits
  io.reductionOffered.valid:=reduction.io.dense.result.valid;io.reductionOffered.bits:=reduction.io.dense.result.bits
  io.reductionReturned.valid:=reduction.io.dense.result.fire;io.reductionReturned.bits:=reduction.io.dense.result.bits
}
