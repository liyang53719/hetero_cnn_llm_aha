// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE parent start after its real shared-FFN result.fire and full service
  * drain. The image is from actual role7v2 dual TypedTensorReader metadata.
  * Neither copied packets nor helper predicates are authority. */
class UnifiedMoeSharedGateRunV5 extends Bundle {
  val lease=new HostMoeRuntimePhaseLeaseV5
  val image=new HostMoeSharedGateImageV5
  val shared=new UnifiedMoeFfnGroupResultV3
}
class UnifiedMoeSharedSigmoidCommitV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val source=new HostMoeSharedGateCommitV5 // captured only at owned real Dense retirement
  val ownerSequence=UInt(32.W);val output=UInt(64.W);val rows=UInt(16.W)
  val acknowledgedWriteBytes=UInt(64.W)
  val scalarIssued=UInt(33.W);val scalarReturned=UInt(33.W)
  val formatIssued=UInt(33.W);val formatReturned=UInt(33.W)
  val memoryIssued=UInt(9.W);val memoryReturned=UInt(9.W)
  val status=UInt(8.W);val drained=Bool()
}

/** Actual original Dense[M,32,2048] acceptance/retirement -> row64B lane0 DDR
  * read -> exact candidate sigmoid nodes -> packed BF16 weight DDR write/ACK.
  * No synthetic Dense result or successfulWriteback/grant Boolean input.
  * No numerical engine is instantiated: Dense/Scalar/formatter/DDR are the
  * parent's unique services. The one logical32 child is control/registers only.
  *
  * Physical N1 output ACK=M*64, logical lane0 bytes=M*2 and effective MAC=M*2048.
  * The actual128KiB readonly padded weight view needs separate real permission
  * and accepted typed metadata. The original4KiB address is never expanded by
  * this module. Shared gate/up scratch is reused only after the parent proves
  * real shared FFN retirement and all service debts; sharedDown/routedDown stay.
  *
  * Parent V3 full owner/epoch/serial matching occurs BEFORE these raw responses;
  * no earlier-than-next-cycle responses. Registered sourceResetRequired avoids
  * faultNow feedback. Current fault still gates all new parent work/final fence.
  * These contracts and all numerical domains remain unqualified until actual
  * same-top integration/testing. This is not physical32-II1 implementation.
  */
class UnifiedMoeSharedGateSigmoidOwnerV5 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoeSharedGateRunV5))
    val denseJob=Decoupled(new QwenOwnerJob)
    val denseResult=Flipped(Decoupled(new QwenOwnerResult))
    val denseResetRequired=Input(Bool())
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val sourceResetRequired=Input(Bool())
    val done=Decoupled(new UnifiedMoeSharedSigmoidCommitV5)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val scalarOrdinal=Output(UInt(33.W));val formatOrdinal=Output(UInt(33.W))
    val row=Output(UInt(8.W));val arithmeticLane=Output(UInt(5.W));val arithmeticNode=Output(UInt(2.W))
  })
  val core=Module(new UnifiedMoeLogical32SigmoidConsumerV5)
  io.scalar.request<>core.io.scalar.request;core.io.scalar.result<>io.scalar.result
  io.formatRequest<>core.io.formatRequest;core.io.formatResult<>io.formatResult
  val states=Enum(11)
  val idle=states(0);val offerDense=states(1);val waitDense=states(2);val prepareRead=states(3)
  val offerMemory=states(4);val waitMemory=states(5);val startCore=states(6);val waitCore=states(7)
  val prepareWrite=states(8);val report=states(9);val locked=states(10)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeSharedGateRunV5)
  val denseOffer=Reg(new QwenOwnerJob);val acceptedDense=Reg(new QwenOwnerJob)
  val row=Reg(UInt(8.W));val lane=Reg(UInt(5.W));val bucket=Reg(UInt(2.W));val activeLanes=Reg(UInt(6.W))
  val inputWords=Reg(Vec(32,UInt(16.W)));val writeData=Reg(UInt(512.W))
  val mem=Reg(new MemoryRequest);val pendingTag=Reg(UInt(64.W));val sequence=RegInit(0.U(64.W))
  val writeKind=Reg(Bool());val out=Reg(new UnifiedMoeSharedSigmoidCommitV5)
  val scalarBefore=Reg(UInt(33.W));val formatBefore=Reg(UInt(33.W))
  val haveLast=RegInit(false.B);val lastTransaction=Reg(UInt(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknownDense=io.denseResult.valid && state=/=waitDense
  val unknownMemory=io.response.valid && state=/=waitMemory
  val unknownCore=core.io.result.valid && state=/=waitCore
  when(unknownDense||unknownMemory||unknownCore||io.memoryResetRequired||io.denseResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.sourceResetRequired){poison:=true.B}
  core.io.externalPoison:=poison||io.sourceResetRequired||io.memoryResetRequired||io.denseResetRequired
  val fault=poison||quarantine||unknownDense||unknownMemory||unknownCore||io.memoryResetRequired||
    io.denseResetRequired||io.sourceResetRequired||core.io.resetRequired
  io.resetRequired:=fault;io.contextReserved:=state=/=idle||io.begin.valid||core.io.busy
  io.scalarOrdinal:=out.scalarIssued;io.formatOrdinal:=out.formatIssued
  io.row:=row;io.arithmeticLane:=core.io.lane;io.arithmeticNode:=core.io.node
  io.begin.ready:=state===idle && !fault && !core.io.busy
  io.denseJob.valid:=state===offerDense;io.denseJob.bits:=denseOffer
  io.denseResult.ready:=state===waitDense && !quarantine && !io.denseResetRequired
  io.memory.valid:=state===offerMemory;io.memory.bits:=mem
  io.response.ready:=state===waitMemory && !quarantine && !io.memoryResetRequired
  core.io.begin.valid:=state===startCore && !fault
  core.io.begin.bits.data:=inputWords.asUInt;core.io.begin.bits.activeLanes:=activeLanes
  core.io.result.ready:=state===waitCore && !quarantine
  io.done.valid:=state===report;io.done.bits:=out
  // All helper wires are constructed OUTSIDE when. A structural true alone
  // never captures source: only actual owned Dense job.fire and result.fire do.
  val in=io.begin.bits;val l=in.lease;val c=l.context
  val (proposedDense,n1Geometry)=HostMoeSharedGatePlanV5.decode(l,in.image)
  val (actualCommit,actualStructure)=HostMoeSharedGatePlanV5.fromActualDense(job.lease,job.image,acceptedDense,io.denseResult.bits)
  val outputPaddedBytes=((c.tokens.pad(96)+31.U)>>5)<<6
  val outputEnd=l.upOutput.pad(96)+outputPaddedBytes
  val outputGeometry=l.upOutput=/=0.U && l.upOutput(5,0)===0.U && l.upOutput>=l.allocationBase &&
    outputEnd<=l.allocationEnd.pad(96) && outputEnd<=(BigInt(1)<<56).U
  val memoryBudget=c.tokens.pad(65)+((c.tokens.pad(65)+31.U)>>5)
  val legal=UnifiedMoeRuntimeLeaseGeometryV4.legal(l) && UnifiedMoeSharedFfnPlanV5.completed(l,in.shared) &&
    n1Geometry && outputGeometry && sequence.pad(65)+memoryBudget<=(BigInt(1)<<64).U-1.U &&
    (!haveLast || c.transactionId>lastTransaction)
  def fail(status:UInt,drained:Bool):Unit={
    poison:=true.B;out.status:=status;out.drained:=drained;state:=report
  }
  val cleanLocal= !quarantine && !unknownDense && !unknownMemory && !unknownCore &&
    !io.memoryResetRequired && !io.denseResetRequired && !core.io.quarantine
  when(io.begin.fire){
    job:=in;denseOffer:=proposedDense;row:=0.U;lane:=0.U;bucket:=0.U
    activeLanes:=Mux(c.tokens>=32.U,32.U,c.tokens);inputWords.foreach(_:=0.U)
    out:=0.U.asTypeOf(new UnifiedMoeSharedSigmoidCommitV5)
    out.context:=c;out.allocationSequence:=l.allocationSequence
    out.ownerSequence:=l.firstOwnerSequence+HostMoeOwnerRangeV5.SharedSigmoid.U
    out.output:=l.upOutput;out.rows:=c.tokens
    when(legal){haveLast:=true.B;lastTransaction:=c.transactionId;state:=offerDense}
    .otherwise{fail(Status.Dependency.U,true.B)}
  }
  when(io.denseJob.fire){acceptedDense:=io.denseJob.bits;state:=waitDense}
  when(io.denseResult.fire){
    when(!actualStructure){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
    .elsewhen(fault){fail(Status.Dependency.U,cleanLocal)}
    .otherwise{
      // Real event, exact accepted full job, clean current fault: only here is
      // the authoritative source packet captured; helper success is not fire.
      out.source:=actualCommit;state:=prepareRead
    }
  }
  when(state===prepareRead || state===prepareWrite){
    when(fault){fail(Status.Dependency.U,cleanLocal && !core.io.busy)}.otherwise{
      mem:=0.U.asTypeOf(new MemoryRequest);mem.tag:=sequence
      mem.address:=Mux(state===prepareRead,acceptedDense.dst+(row.pad(64)<<6),job.lease.upOutput+(bucket.pad(64)<<6))
      mem.write:=state===prepareWrite;mem.data:=Mux(state===prepareWrite,writeData,0.U)
      val mask=((1.U(65.W)<<(activeLanes.pad(7)<<1))-1.U)(63,0)
      mem.mask:=Mux(state===prepareWrite,mask,0.U)
      writeKind:=state===prepareWrite;state:=offerMemory
    }
  }
  when(io.memory.fire){pendingTag:=mem.tag;sequence:=sequence+1.U;out.memoryIssued:=out.memoryIssued+1.U;state:=waitMemory}
  when(io.response.fire){
    when(io.response.bits.tag=/=pendingTag || io.response.bits.error){
      quarantine:=true.B;fail(Status.Protocol.U,false.B)
    }.otherwise{
      out.memoryReturned:=out.memoryReturned+1.U
      when(writeKind){out.acknowledgedWriteBytes:=out.acknowledgedWriteBytes+(activeLanes.pad(64)<<1)}
      when(fault){fail(Status.Dependency.U,cleanLocal && !core.io.busy)}
      .elsewhen(!writeKind){
        val value=io.response.bits.data(15,0) // ONLY logical lane0, not dummy columns.
        when(value(14,7)==="hff".U){fail(Status.Numerical.U,true.B)}.otherwise{
          inputWords(lane):=value
          when(lane.pad(6)+1.U===activeLanes){state:=startCore}
          .otherwise{lane:=lane+1.U;row:=row+1.U;state:=prepareRead}
        }
      }.otherwise{
        when(row.pad(9)+1.U===job.lease.context.tokens){
          val rows=job.lease.context.tokens
          val expectedMem=rows.pad(9)+((rows.pad(9)+31.U)>>5)
          val exact=out.acknowledgedWriteBytes+(activeLanes.pad(64)<<1)===(rows.pad(64)<<1) &&
            out.scalarIssued===(rows.pad(33)<<2) && out.scalarReturned===out.scalarIssued &&
            out.formatIssued===rows && out.formatReturned===rows &&
            out.memoryIssued===expectedMem && out.memoryReturned+1.U===expectedMem
          out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=exact
          when(!exact){poison:=true.B};state:=report
        }.otherwise{
          val remaining=job.lease.context.tokens-(row.pad(16)+1.U)
          row:=row+1.U;lane:=0.U;bucket:=bucket+1.U;inputWords.foreach(_:=0.U)
          activeLanes:=Mux(remaining>=32.U,32.U,remaining);state:=prepareRead
        }
      }
    }
  }
  when(state===startCore && fault){fail(Status.Dependency.U,cleanLocal && !core.io.busy)}
  when(core.io.begin.fire){scalarBefore:=out.scalarIssued;formatBefore:=out.formatIssued;state:=waitCore}
  when(io.scalar.request.fire){out.scalarIssued:=out.scalarIssued+1.U}
  when(io.formatRequest.fire){out.formatIssued:=out.formatIssued+1.U}
  when(core.io.result.fire){
    val r=core.io.result.bits
    out.scalarReturned:=out.scalarReturned+r.scalarReturned;out.formatReturned:=out.formatReturned+r.formatReturned
    val receiptExact=r.activeLanes===activeLanes && r.scalarIssued.pad(33)===out.scalarIssued-scalarBefore &&
      r.formatIssued.pad(33)===out.formatIssued-formatBefore &&
      r.scalarReturned===r.scalarIssued && r.formatReturned===r.formatIssued
    val exact=receiptExact && r.scalarIssued===(activeLanes.pad(9)<<2) && r.formatIssued===activeLanes
    when(!r.drained || !receiptExact){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
    .elsewhen(r.status=/=Status.Ok.U || fault){fail(Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U),cleanLocal)}
    .elsewhen(!exact){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
    .otherwise{writeData:=r.data;state:=prepareWrite}
  }
  when(io.done.fire){state:=Mux(fault|| !out.drained,locked,idle)}
  // New admission is history/poison gated; failure never rolls history back.
  // Unknown/missing debt cannot be faked closed. Already held physical offers
  // remain stable and may need externally isolated reset. A held commit is
  // immutable; parent current fault veto remains necessary even after its fire.
}
