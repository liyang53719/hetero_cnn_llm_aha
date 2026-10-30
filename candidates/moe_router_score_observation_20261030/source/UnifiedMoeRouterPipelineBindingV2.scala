// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private scheduler packet. Neither allocation nor postnorm provenance is a
  * host assertion: the parent must bind its allocator and actual norm ledger. */
class UnifiedMoeRouterPipelineCommandV2 extends Bundle {
  val dense=new UnifiedMoeRouterDenseCommandV2
  val allocation=new UnifiedMoeRouteAllocationV2
}
/** Local retirement only. It is NOT the common resource lease release, block
  * completion, or proof that an untagged physical service has drained. */
class UnifiedMoeRouterPipelineRetirementV2 extends Bundle {
  val command=new UnifiedMoeRouterPipelineCommandV2
  val dense=new QwenOwnerResult
  val reader=new UnifiedMoeRouterReadResultV2
  val numeric=new UnifiedMoeRouterNumericResultV2
  val map=new UnifiedMoeRouteCommitV2
  val status=UInt(8.W);val childrenStarted=Bool();val localDrained=Bool()
}

object UnifiedMoeRouterPipelineCommandV2 {
  def legal(c:UnifiedMoeRouterPipelineCommandV2):Bool={
    val (_,denseLegal)=UnifiedMoeRouterDenseCommandV2.decode(c.dense)
    val d=c.dense;val a=c.allocation
    val mapEnd=a.metadataBase.pad(96)+UnifiedMoeRouteLayoutV2.Bytes.U
    val logitsEnd=d.output.pad(96)+(d.context.tokens.pad(96)*512.U)
    val normEnd=d.postnorm.pad(96)+(d.context.tokens.pad(96)*4096.U)
    val weightsEnd=d.weight.pad(96)+(2048*256*2).U
    def overlap(b:UInt,e:UInt):Bool=a.metadataBase.pad(96)<e && b.pad(96)<mapEnd
    denseLegal && a.context.asUInt===d.context.asUInt && a.allocationSequence=/=0.U &&
      a.metadataBase=/=0.U && a.metadataBase(5,0)===0.U &&
      a.metadataBase>=d.context.host.regions(3).base && mapEnd<=a.allocationEnd.pad(96) &&
      mapEnd<=(BigInt(1)<<56).U && !overlap(d.output,logitsEnd) &&
      !overlap(d.postnorm,normEnd) && !overlap(d.weight,weightsEnd)
  }
}

/** Bind the real original Dense completion, BF16 DDR stream, all256 arithmetic
  * owner and route-map ACK producer. This is an internal controller submodule,
  * not another resource top. It instantiates ZERO floating arithmetic, TopK,
  * SRAM, formatters or Matrix engines. All services below are borrowed from
  * the ONE common fixed hardware, under parent V3 full-identity leases.
  *
  * Shared selector's existing tie policy is unchanged. Until the explicit tie
  * contract/reference decision and arithmetic qualification are resolved this
  * source must NOT enable a production block profile or claim numeric PASS.
  *
  * Children start atomically only after the real Dense result.fire succeeds.
  * This private ready-qualified start is Decoupled, not general Irrevocable.
  * All physical offers already made remain owned by their original children.
  * Cross-child fault feedback is registered; outward poison is immediate.
  * A fault can leave a child waiting for missing input/transport. Such a job
  * stays reserved with visible poison until genuine retirement or externally
  * isolated reset/watchdog; it is never promoted to a fabricated drained done.
  */
class UnifiedMoeRouterPipelineBindingV2 extends Module {
  val io=IO(new Bundle {
    val rawScoreObservation=Output(Valid(new UnifiedMoeRouterScoreObservationV1))
    val begin=Flipped(Decoupled(new UnifiedMoeRouterPipelineCommandV2))
    val denseJob=Decoupled(new QwenOwnerJob)
    val denseDone=Flipped(Decoupled(new QwenOwnerResult))
    val denseResetRequired=Input(Bool())
    val readMemory=Decoupled(new MemoryRequest)
    val readResponse=Flipped(Decoupled(new MemoryResponse))
    val readMemoryResetRequired=Input(Bool())
    val mapMemory=Decoupled(new MemoryRequest)
    val mapResponse=Flipped(Decoupled(new MemoryResponse))
    val mapMemoryResetRequired=Input(Bool())
    val scalar=new UnifiedScalarClientV2
    val selection=new UnifiedMoeRouterSelectionClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val group=Decoupled(new UnifiedMoeExpertGroupV2)
    val retirement=Decoupled(new UnifiedMoeRouterPipelineRetirementV2)
    val externalPoison=Input(Bool()) // parent registered sticky state, not a faultNow loop
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val scalarOperationOrdinal=Output(UInt(32.W));val arithmeticToken=Output(UInt(32.W))
    val arithmeticPhase=Output(UInt(5.W))
  })
  val dense=Module(new UnifiedMoeRouterDenseFenceV2)
  val reader=Module(new UnifiedMoeRouterLogitReaderV2)
  val numeric=Module(new UnifiedMoeRouterNumericalOwnerV2)
  io.rawScoreObservation:=numeric.io.rawScoreObservation
  val routeMap=Module(new UnifiedMoeRouteGroupV2)
  val idle::denseOffer::denseWait::startChildren::running::report::locked::Nil=Enum(7)
  val state=RegInit(idle);val command=Reg(new UnifiedMoeRouterPipelineCommandV2)
  val commit=Reg(new UnifiedMoeRouterLogitCommitV2)
  val result=Reg(new UnifiedMoeRouterPipelineRetirementV2)
  val poison=RegInit(false.B);val lastTransaction=RegInit(0.U(64.W))
  val haveLastTransaction=RegInit(false.B) // first accepted block transaction may be0
  val readerSeen=RegInit(false.B);val numericSeen=RegInit(false.B);val mapSeen=RegInit(false.B)
  val unknownDone=(dense.io.commit.valid && state=/=denseWait) ||
    (reader.io.done.valid && state=/=running) || (numeric.io.done.valid && state=/=running) ||
    (routeMap.io.done.valid && state=/=running)
  val faultNow=io.externalPoison || unknownDone || dense.io.resetRequired ||
    reader.io.resetRequired || numeric.io.resetRequired || routeMap.io.resetRequired
  when(faultNow){poison:=true.B}
  io.resetRequired:=poison || faultNow
  io.contextReserved:=state=/=idle || io.begin.valid
  io.begin.ready:=state===idle && !io.resetRequired
  io.retirement.valid:=state===report;io.retirement.bits:=result

  dense.io.command.valid:=state===denseOffer
  dense.io.command.bits:=command.dense
  io.denseJob<>dense.io.job;dense.io.done<>io.denseDone
  dense.io.denseResetRequired:=io.denseResetRequired
  dense.io.commit.ready:=state===denseWait
  io.readMemory<>reader.io.memory;reader.io.response<>io.readResponse
  reader.io.memoryResetRequired:=io.readMemoryResetRequired
  reader.io.sourceResetRequired:=poison
  io.mapMemory<>routeMap.io.memory;routeMap.io.response<>io.mapResponse
  routeMap.io.memoryResetRequired:=io.mapMemoryResetRequired
  numeric.io.sourceResetRequired:=poison
  numeric.io.logits<>reader.io.logits
  io.scalar<>numeric.io.scalar;io.selection<>numeric.io.selection
  io.formatRequest.valid:=numeric.io.format.request.valid
  io.formatRequest.bits.value:=numeric.io.format.request.bits.value
  numeric.io.format.request.ready:=io.formatRequest.ready
  numeric.io.format.result.valid:=io.formatResult.valid
  numeric.io.format.result.bits.value:=io.formatResult.bits.value
  numeric.io.format.result.bits.error:=io.formatResult.bits.error
  io.formatResult.ready:=numeric.io.format.result.ready
  io.scalarOperationOrdinal:=numeric.io.scalarOperationOrdinal
  io.arithmeticToken:=numeric.io.arithmeticToken;io.arithmeticPhase:=numeric.io.arithmeticPhase
  routeMap.io.route<>numeric.io.route
  io.group<>routeMap.io.group

  val allStartReady=reader.io.commit.ready && numeric.io.begin.ready && routeMap.io.allocation.ready
  val start=state===startChildren && !io.resetRequired && allStartReady
  reader.io.commit.valid:=start;reader.io.commit.bits:=commit
  numeric.io.begin.valid:=start;numeric.io.begin.bits:=commit
  routeMap.io.allocation.valid:=start;routeMap.io.allocation.bits:=command.allocation
  reader.io.done.ready:=state===running && !readerSeen
  numeric.io.done.ready:=state===running && !numericSeen
  routeMap.io.done.ready:=state===running && !mapSeen

  when(io.begin.fire){
    command:=io.begin.bits;result:=0.U.asTypeOf(new UnifiedMoeRouterPipelineRetirementV2)
    result.command:=io.begin.bits;readerSeen:=false.B;numericSeen:=false.B;mapSeen:=false.B
    val legal=UnifiedMoeRouterPipelineCommandV2.legal(io.begin.bits) &&
      (!haveLastTransaction || io.begin.bits.dense.context.transactionId>lastTransaction)
    when(legal){lastTransaction:=io.begin.bits.dense.context.transactionId;haveLastTransaction:=true.B;state:=denseOffer}
    .otherwise{result.status:=Status.Bounds.U;result.localDrained:=true.B;state:=report}
  }
  when(dense.io.command.fire){state:=denseWait}
  when(dense.io.commit.fire){
    commit:=dense.io.commit.bits;result.dense:=dense.io.commit.bits.result
    when(dense.io.commit.bits.successfulWriteback && !io.resetRequired){state:=startChildren}
    .otherwise{
      result.status:=Mux(dense.io.commit.bits.result.status===Status.Ok.U,Status.Dependency.U,dense.io.commit.bits.result.status)
      // Only this Dense owner actually completed; no downstream child started.
      result.localDrained:=true.B;state:=report
    }
  }
  when(state===startChildren && io.resetRequired){
    result.status:=Status.Dependency.U;result.localDrained:=true.B;state:=report
  }
  when(start){
    assert(reader.io.commit.fire && numeric.io.begin.fire && routeMap.io.allocation.fire)
    result.childrenStarted:=true.B;state:=running
  }
  when(reader.io.done.fire){result.reader:=reader.io.done.bits;readerSeen:=true.B}
  when(numeric.io.done.fire){result.numeric:=numeric.io.done.bits;numericSeen:=true.B}
  when(routeMap.io.done.fire){result.map:=routeMap.io.done.bits;mapSeen:=true.B}
  when(state===running && readerSeen && numericSeen && mapSeen){
    val tx=command.dense.context.transactionId;val seq=command.dense.ownerSequence
    val m=command.dense.context.tokens
    val identities=result.reader.transactionId===tx && result.reader.ownerSequence===seq &&
      result.numeric.transactionId===tx && result.numeric.ownerSequence===seq &&
      result.map.transactionId===tx && result.map.allocationSequence===command.allocation.allocationSequence &&
      result.map.metadataBase===command.allocation.metadataBase
    val counts=result.reader.readBytes===m*512.U && result.numeric.rows===m &&
      result.numeric.emittedRoutes===(m<<3) && result.map.routes===(m<<3) &&
      result.map.acknowledgedWriteBytes===m*128.U &&
      result.numeric.expectedScalarOperations===m*1040.U &&
      result.numeric.scalarIssued===result.numeric.expectedScalarOperations &&
      result.numeric.scalarReturned===result.numeric.scalarIssued
    val drained=result.reader.drained && result.numeric.drained && result.map.drained
    val good=result.reader.status===Status.Ok.U && result.numeric.status===Status.Ok.U &&
      result.map.status===Status.Ok.U && identities && counts && drained && !io.resetRequired
    result.status:=Mux(good,Status.Ok.U,Mux(!identities || !counts,Status.Protocol.U,Status.Dependency.U))
    result.localDrained:=drained;when(!good){poison:=true.B};state:=report
  }
  when(io.retirement.fire){state:=Mux(io.resetRequired || !result.localDrained,locked,idle)}
  // A late fault never rewrites held result payload or claims a resource release.
  // Parent must gate NEW gather/Dense offers using CURRENT resetRequired, and
  // join actual V3 service lease drains before releasing allocator/block context.
}
