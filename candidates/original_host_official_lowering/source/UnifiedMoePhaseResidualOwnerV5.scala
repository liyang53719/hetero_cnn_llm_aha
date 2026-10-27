// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedMoePhaseResidualRunV5 extends Bundle {
  val lease=new HostMoeRuntimePhaseLeaseV5
  val merge=new UnifiedMoePhaseMergeCommitV5
}
class UnifiedMoePhaseResidualCommitV5 extends Bundle {
  val context=new HostMoePhaseContextV4;val allocationSequence=UInt(64.W)
  val ownerSequence=UInt(32.W);val output=UInt(64.W)
  val completedTokens=UInt(16.W);val completedTiles=UInt(14.W)
  val acknowledgedWriteBytes=UInt(64.W)
  val vectorIssued=UInt(33.W);val vectorReturned=UInt(33.W)
  val memoryIssued=UInt(15.W);val memoryReturned=UInt(15.W)
  val primitiveFlags=UInt(5.W);val status=UInt(8.W);val drained=Bool()
}
object UnifiedMoePhaseMergeReceiptV5 {
  /** Pure structural check of an ACTUAL merge.done.fire. Never a permission or
    * fabricated source of that event; parent must retain this same full lease. */
  def matches(l:HostMoeRuntimePhaseLeaseV5,r:UnifiedMoePhaseMergeCommitV5):Bool={
    val m=l.context.tokens;val tiles=m.pad(33)<<6
    r.context.asUInt===l.context.asUInt && r.allocationSequence===l.allocationSequence &&
      r.ownerSequence.pad(33)===l.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Merge.U &&
      r.output===l.mergedOutput && r.completedTokens===m && r.completedTiles===tiles &&
      r.acknowledgedWriteBytes===(m.pad(64)<<12) && r.status===Status.Ok.U && r.drained &&
      r.vectorIssued===tiles*36.U && r.vectorReturned===r.vectorIssued &&
      r.metadataIssued===m.pad(11)*9.U && r.metadataReturned===r.metadataIssued &&
      r.dataIssued===tiles*9.U && r.dataReturned===r.dataIssued &&
      r.writerIssued===tiles+((m.pad(33)+31.U)>>5) && r.writerReturned===r.writerIssued
  }
}

/** Final phase residual consumer. Reads actual BF16 postmixer residual and
  * actual merged DDR output, in that operand order; requests two16-lane
  * Bf16AddRne operations per32-element tile, then writes/ACKs64 bytes at real
  * context.output. No new ALU/formatter/vector bank/Scalar is instantiated.
  * This is the existing16-lane RAW interface, not a physical32-II1 design.
  * The sole shared bank owns FP32 Add and the BF16 RNE boundary. This candidate
  * is finite-domain/source-only, not a Torch/full-IEEE numerical qualification.
  *
  * Whole-M owner1288 is parent V3 full-tag/epoch/serial bound. Raw result policy
  * is additionally checked, never substituted for full ownership. Wrong policy
  * does NOT retire vector credit. Services return no earlier than next cycle.
  * Parent creates begin only at actual same-lease merge.done.fire + current clean
  * global fault and true predecessor drain. This module's final DDR ACK does NOT
  * bypass Guard/allocator release, global poison or original block completion.
  */
class UnifiedMoePhaseResidualOwnerV5 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoePhaseResidualRunV5))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val memoryResetRequired=Input(Bool());val externalPoison=Input(Bool()) // registered sticky
    val vectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    val done=Decoupled(new UnifiedMoePhaseResidualCommitV5)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    val token=Output(UInt(8.W));val tileOrdinal=Output(UInt(6.W));val vectorOrdinal=Output(UInt(33.W))
  })
  val states=Enum(10)
  val idle=states(0);val prepareRead=states(1);val offerMemory=states(2);val waitMemory=states(3)
  val prepareVector=states(4);val offerVector=states(5);val waitVector=states(6)
  val prepareWrite=states(7);val report=states(8);val locked=states(9)
  val state=RegInit(idle);val job=Reg(new UnifiedMoePhaseResidualRunV5)
  val token=Reg(UInt(8.W));val tile=Reg(UInt(6.W));val readSecond=Reg(Bool());val half=Reg(Bool())
  val residualData=Reg(UInt(512.W));val mergeData=Reg(UInt(512.W))
  val firstHalf=Reg(UInt(256.W));val writeData=Reg(UInt(512.W))
  val request=Reg(new UnifiedVectorRequestV2);val mem=Reg(new MemoryRequest)
  val sequence=RegInit(0.U(64.W));val tag=Reg(UInt(64.W));val writeKind=Reg(Bool())
  val out=Reg(new UnifiedMoePhaseResidualCommitV5)
  val haveLast=RegInit(false.B);val lastTransaction=Reg(UInt(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknownMemory=io.response.valid && state=/=waitMemory
  val unknownVector=io.vectorResult.valid && state=/=waitVector
  when(unknownMemory||unknownVector||io.memoryResetRequired){poison:=true.B;quarantine:=true.B}
  when(io.externalPoison){poison:=true.B}
  val fault=poison||quarantine||unknownMemory||unknownVector||io.memoryResetRequired||io.externalPoison
  val cleanLocal= !quarantine && !unknownMemory && !unknownVector && !io.memoryResetRequired
  io.resetRequired:=fault;io.contextReserved:=state=/=idle||io.begin.valid
  io.begin.ready:=state===idle && !fault
  io.memory.valid:=state===offerMemory;io.memory.bits:=mem
  io.response.ready:=state===waitMemory && !quarantine && !io.memoryResetRequired
  io.vectorRequest.valid:=state===offerVector;io.vectorRequest.bits:=request
  io.vectorResult.ready:=state===waitVector && !quarantine
  io.done.valid:=state===report;io.done.bits:=out
  io.token:=token;io.tileOrdinal:=tile;io.vectorOrdinal:=out.vectorIssued
  val in=io.begin.bits;val l=in.lease;val c=l.context;val dst=c.output
  def overlap(a:UInt,e:UInt,b:UInt,f:UInt):Bool=a<f && b<e
  val outputWritable=c.host.regions.map(r=>r.write && dst.address>=r.base && dst.paddedEnd<=r.limit).reduce(_||_)
  val preserve=(Seq(c.input,c.residual)++l.weights).map(t=>
    !overlap(dst.address,dst.paddedEnd,t.address,t.paddedEnd)).reduce(_&&_) &&
    !overlap(dst.address,dst.paddedEnd,c.host.commandBase,c.host.commandLimit) &&
    !overlap(dst.address,dst.paddedEnd,c.host.descriptorBase,c.host.descriptorLimit)
  val tiles=c.tokens.pad(65)<<6
  val legal=UnifiedMoeRuntimeLeaseGeometryV4.legal(l) && UnifiedMoePhaseMergeReceiptV5.matches(l,in.merge) &&
    outputWritable && preserve && l.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W) &&
    sequence.pad(65)+tiles*3.U<=(BigInt(1)<<64).U-1.U && (!haveLast || c.transactionId>lastTransaction)
  val completedHalf=Cat((0 until 16).reverse.map(i=>io.vectorResult.bits.value(i)(31,16)))
  def fail(status:UInt,drained:Bool):Unit={poison:=true.B;out.status:=status;out.drained:=drained;state:=report}
  when(io.begin.fire){
    job:=in;token:=0.U;tile:=0.U;readSecond:=false.B;half:=false.B
    out:=0.U.asTypeOf(new UnifiedMoePhaseResidualCommitV5)
    out.context:=c;out.allocationSequence:=l.allocationSequence
    out.ownerSequence:=l.firstOwnerSequence+HostMoeOwnerRangeV5.Residual.U;out.output:=c.output.address
    when(legal){haveLast:=true.B;lastTransaction:=c.transactionId;state:=prepareRead}
    .otherwise{fail(Status.Dependency.U,true.B)}
  }
  when(state===prepareRead || state===prepareWrite){
    when(fault){fail(Status.Dependency.U,cleanLocal)}.otherwise{
      val base=Mux(state===prepareWrite,job.lease.context.output.address,
        Mux(readSecond,job.lease.mergedOutput,job.lease.context.residual.address))
      mem:=0.U.asTypeOf(new MemoryRequest);mem.tag:=sequence
      mem.address:=base+(token.pad(64)<<12)+(tile.pad(64)<<6)
      mem.write:=state===prepareWrite;mem.data:=Mux(state===prepareWrite,writeData,0.U)
      mem.mask:=Mux(state===prepareWrite,"hffffffffffffffff".U,0.U)
      writeKind:=state===prepareWrite;state:=offerMemory
    }
  }
  when(io.memory.fire){tag:=mem.tag;sequence:=sequence+1.U;out.memoryIssued:=out.memoryIssued+1.U;state:=waitMemory}
  when(io.response.fire){
    when(io.response.bits.tag=/=tag || io.response.bits.error){quarantine:=true.B;fail(Status.Protocol.U,false.B)}
    .otherwise{
      out.memoryReturned:=out.memoryReturned+1.U
      when(writeKind){out.acknowledgedWriteBytes:=out.acknowledgedWriteBytes+64.U}
      when(fault){fail(Status.Dependency.U,cleanLocal)}
      .elsewhen(!writeKind){
        val finite=(0 until 32).map(i=>io.response.bits.data(i*16+14,i*16+7)=/="hff".U).reduce(_&&_)
        when(!finite){fail(Status.Numerical.U,true.B)}
        .elsewhen(!readSecond){residualData:=io.response.bits.data;readSecond:=true.B;state:=prepareRead}
        .otherwise{mergeData:=io.response.bits.data;readSecond:=false.B;half:=false.B;state:=prepareVector}
      }.otherwise{
        out.completedTiles:=out.completedTiles+1.U
        when(tile===63.U){
          out.completedTokens:=out.completedTokens+1.U
          when(token.pad(16)+1.U===job.lease.context.tokens){
            val m=job.lease.context.tokens;val count=m.pad(33)<<6
            val exact=out.completedTokens+1.U===m && out.completedTiles.pad(33)+1.U===count &&
              out.acknowledgedWriteBytes+64.U===(m.pad(64)<<12) &&
              out.vectorIssued===(count<<1) && out.vectorReturned===out.vectorIssued &&
              out.memoryIssued===count*3.U && out.memoryReturned+1.U===out.memoryIssued
            out.status:=Mux(exact,Status.Ok.U,Status.Protocol.U);out.drained:=exact
            when(!exact){poison:=true.B};state:=report
          }.otherwise{token:=token+1.U;tile:=0.U;state:=prepareRead}
        }.otherwise{tile:=tile+1.U;state:=prepareRead}
      }
    }
  }
  when(state===prepareVector){
    when(fault){fail(Status.Dependency.U,cleanLocal)}.otherwise{
      request:=0.U.asTypeOf(new UnifiedVectorRequestV2)
      request.policy:=UnifiedVectorPolicyV2.Bf16AddRne.U;request.multiply:=false.B
      for(i<-0 until 16){
        val a=Mux(half,residualData((i+16)*16+15,(i+16)*16),residualData(i*16+15,i*16))
        val b=Mux(half,mergeData((i+16)*16+15,(i+16)*16),mergeData(i*16+15,i*16))
        request.a(i):=Cat(a,0.U(16.W));request.b(i):=Cat(b,0.U(16.W))
      }
      state:=offerVector
    }
  }
  when(io.vectorRequest.fire){out.vectorIssued:=out.vectorIssued+1.U;state:=waitVector}
  when(io.vectorResult.fire){
    val r=io.vectorResult.bits
    when(r.policy=/=request.policy){quarantine:=true.B;fail(Status.Protocol.U,false.B)}.otherwise{
      out.vectorReturned:=out.vectorReturned+1.U
      out.primitiveFlags:=out.primitiveFlags|r.flags.reduce(_|_)
      val finiteExpanded=r.value.map(v=>v(15,0)===0.U && v(30,23)=/="hff".U).reduce(_&&_)
      val flagsOk=r.flags.map(f=>f(4,1)===0.U).reduce(_&&_)
      when(fault){fail(Status.Dependency.U,cleanLocal)}
      .elsewhen(r.error || !finiteExpanded || !flagsOk){fail(Status.Numerical.U,true.B)}
      .elsewhen(!half){firstHalf:=completedHalf;half:=true.B;state:=prepareVector}
      .otherwise{writeData:=Cat(completedHalf,firstHalf);state:=prepareWrite}
    }
  }
  when(io.done.fire){state:=Mux(fault|| !out.drained,locked,idle)}
  // Held physical offers and held terminal packet do not retract or mutate on
  // late fault. Parent current-fault + actual global drained checks must precede
  // the independent Guard/allocator release and eventual whole-block success.
}
