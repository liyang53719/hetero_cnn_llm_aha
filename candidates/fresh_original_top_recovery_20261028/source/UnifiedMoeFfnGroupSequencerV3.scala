// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE accepted group plan from the common scheduler, never host authority.
  * Routed input requires the actual Gather commit; expert256 input requires the
  * actual postnorm commit. Parent binds accepted dst/fullcontext/ownerSequence,
  * weight identity, allocation permissions/lifetime and the current poison gate.
  * Four consecutive nonreused owner sequences are reserved before job.fire.
  */
class UnifiedMoeFfnGroupJobV3 extends Bundle {
  val context=new HostMoePhaseContextV4
  val expert=UInt(9.W);val groupRows=UInt(8.W);val firstOwnerSequence=UInt(32.W)
  val input=UInt(64.W)
  val gateWeight=UInt(64.W);val upWeight=UInt(64.W);val downWeight=UInt(64.W)
  val gateOutput=UInt(64.W);val upOutput=UInt(64.W)
  val activationOutput=UInt(64.W);val downOutput=UInt(64.W)
  val allocationEnd=UInt(64.W)
}
class UnifiedMoeFfnGroupResultV3 extends Bundle {
  val down=new UnifiedMoeDenseWritebackV2
  val activation=new UnifiedMoeActivationGroupCommitV3
  val status=UInt(8.W);val drained=Bool();val downCommitted=Bool()
  val completedStages=UInt(3.W)
}

object UnifiedMoeFfnGroupPlanV3 {
  def decode(in:UnifiedMoeFfnGroupJobV3):
      (UnifiedMoeExpertDenseCommandV2,UnifiedMoeExpertDenseCommandV2,UnifiedMoeExpertDenseCommandV2,Bool)={
    def command(stage:Int,src:UInt,weight:UInt,dst:UInt,offset:Int):UnifiedMoeExpertDenseCommandV2={
      val c=WireDefault(0.U.asTypeOf(new UnifiedMoeExpertDenseCommandV2))
      c.context:=in.context;c.expert:=in.expert;c.groupRows:=in.groupRows;c.stage:=stage.U
      c.input:=src;c.weight:=weight;c.output:=dst;c.firstOwnerSequence:=in.firstOwnerSequence+offset.U
      c
    }
    val gate=command(0,in.input,in.gateWeight,in.gateOutput,0)
    val up=command(1,in.input,in.upWeight,in.upOutput,1)
    val down=command(2,in.activationOutput,in.downWeight,in.downOutput,3)
    val (_,gLegal)=UnifiedMoeExpertDenseCommandV2.decode(gate)
    val (_,uLegal)=UnifiedMoeExpertDenseCommandV2.decode(up)
    val (_,dLegal)=UnifiedMoeExpertDenseCommandV2.decode(down)
    val hiddenBytes=in.groupRows.pad(96)*2048.U*2.U
    val ffnBytes=in.groupRows.pad(96)*512.U*2.U
    val weightBytes=(2048*512*2).U(96.W)
    val writeRanges=Seq((in.gateOutput,ffnBytes),(in.upOutput,ffnBytes),
      (in.activationOutput,ffnBytes),(in.downOutput,hiddenBytes))
    val readRanges=Seq((in.input,hiddenBytes),(in.gateWeight,weightBytes),
      (in.upWeight,weightBytes),(in.downWeight,weightBytes))
    def noAlias(a:(UInt,UInt),b:(UInt,UInt)):Bool=
      !(a._1.pad(96)<b._1.pad(96)+b._2 && b._1.pad(96)<a._1.pad(96)+a._2)
    val writableDisjoint=(for(i<-writeRanges.indices;j<-0 until i)yield noAlias(writeRanges(i),writeRanges(j))).reduce(_ && _)
    val readOnlyDisjoint=(for(w<-writeRanges;r<-readRanges)yield noAlias(w,r)).reduce(_ && _)
    val writeBounds=writeRanges.map{case(base,size)=>base=/=0.U && base(5,0)===0.U &&
      base>=in.context.host.regions(3).base && base.pad(96)+size<=in.allocationEnd.pad(96) &&
      base.pad(96)+size<=(BigInt(1)<<56).U}.reduce(_ && _)
    // Last used sequence is base+3; all-ones remains reserved, no wrap/reuse.
    val sequenceRoom=in.firstOwnerSequence.pad(33)+3.U<"hffffffff".U(33.W)
    (gate,up,down,gLegal&&uLegal&&dLegal&&writeBounds&&writableDisjoint&&readOnlyDisjoint&&sequenceRoom)
  }
}

/** One whole routed/shared FFN GROUP, not a completeblock M1 loop.
  * Owns only controllers/registers: ONE provenance fence to the parent's ONE
  * original Dense, and the frozen zeroALU activation owner. No physical Dense,
  * Matrix, Scalar, Vector, formatter, divider, top or per-model resource clone.
  * Gate/up final writeACKs -> activation DDR/compute/writeACKs -> down Dense.
  * Success down receipt is suitable for the existing real-down reader, subject
  * to the parent's current sticky poison and exact accepted-group side ledger.
  *
  * Internal DispatchV1 still requires its version1 ABI. The public Host version8
  * adapter must explicitly produce that accepted internal record; no blind cast.
  */
class UnifiedMoeFfnGroupSequencerV3 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new UnifiedMoeFfnGroupJobV3))
    val denseJob=Decoupled(new QwenOwnerJob)
    val denseResult=Flipped(Decoupled(new QwenOwnerResult))
    val denseResetRequired=Input(Bool());val memoryResetRequired=Input(Bool())
    val sourceResetRequired=Input(Bool())
    val scalar=new UnifiedScalarClientV2
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val result=Decoupled(new UnifiedMoeFfnGroupResultV3)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val dense=Module(new UnifiedMoeDenseWritebackFenceV2)
  val activation=Module(new UnifiedMoeActivationGroupOwnerV3)
  io.denseJob<>dense.io.job;dense.io.done<>io.denseResult
  io.scalar.request<>activation.io.scalar.request;activation.io.scalar.result<>io.scalar.result
  io.formatRequest<>activation.io.formatRequest;activation.io.formatResult<>io.formatResult
  io.memory<>activation.io.memory;activation.io.response<>io.response
  val idle::offerGate::waitGate::offerUp::waitUp::offerActivation::waitActivation::offerDown::waitDown::report::locked::Nil=Enum(11)
  val state=RegInit(idle);val job=Reg(new UnifiedMoeFfnGroupJobV3)
  val gateCmd=Reg(new UnifiedMoeExpertDenseCommandV2);val upCmd=Reg(new UnifiedMoeExpertDenseCommandV2)
  val downCmd=Reg(new UnifiedMoeExpertDenseCommandV2)
  val activationJob=Reg(new UnifiedMoeActivationGroupJobV3)
  val out=Reg(new UnifiedMoeFfnGroupResultV3)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val waitingDense=state===waitGate||state===waitUp||state===waitDown
  val unknownDense=dense.io.writeback.valid && !waitingDense
  val unknownActivation=activation.io.done.valid && state=/=waitActivation
  when(unknownDense||unknownActivation){poison:=true.B;quarantine:=true.B}
  when(io.sourceResetRequired||io.denseResetRequired||io.memoryResetRequired){poison:=true.B}
  // Registered local poison only: no resetRequired -> child -> faultNow loop.
  dense.io.denseResetRequired:=io.denseResetRequired||io.sourceResetRequired||poison
  activation.io.sourceResetRequired:=io.sourceResetRequired||poison
  activation.io.memoryResetRequired:=io.memoryResetRequired
  val fault=poison||quarantine||unknownDense||unknownActivation||io.sourceResetRequired||
    io.denseResetRequired||io.memoryResetRequired||dense.io.resetRequired||activation.io.resetRequired
  io.resetRequired:=fault
  io.contextReserved:=state=/=idle||io.job.valid||dense.io.contextReserved||activation.io.contextReserved
  io.job.ready:=state===idle && !fault && !dense.io.contextReserved && !activation.io.contextReserved
  // These PRIVATE Decoupled child starts may be suppressed before their fire.
  // Once accepted, actual physical Dense/memory/scalar offers remain the child's
  // stable responsibility; a new fault cannot retract or fake-retire them.
  dense.io.command.valid:=(state===offerGate||state===offerUp||state===offerDown) && !fault
  dense.io.command.bits:=Mux(state===offerGate,gateCmd,Mux(state===offerUp,upCmd,downCmd))
  dense.io.writeback.ready:=waitingDense && !quarantine
  activation.io.job.valid:=state===offerActivation && !fault
  activation.io.job.bits:=activationJob
  activation.io.done.ready:=state===waitActivation && !quarantine
  io.result.valid:=state===report;io.result.bits:=out
  val (plannedGate,plannedUp,plannedDown,legal)=UnifiedMoeFfnGroupPlanV3.decode(io.job.bits)
  def fail(status:UInt,drained:Bool):Unit={
    out.status:=status;out.drained:=drained;out.downCommitted:=false.B
    poison:=true.B;state:=report
  }
  when(io.job.fire){
    job:=io.job.bits;gateCmd:=plannedGate;upCmd:=plannedUp;downCmd:=plannedDown
    activationJob:=0.U.asTypeOf(new UnifiedMoeActivationGroupJobV3)
    activationJob.output:=io.job.bits.activationOutput;activationJob.allocationEnd:=io.job.bits.allocationEnd
    activationJob.ownerSequence:=io.job.bits.firstOwnerSequence+2.U
    out:=0.U.asTypeOf(new UnifiedMoeFfnGroupResultV3)
    out.down.context:=io.job.bits.context;out.down.expert:=io.job.bits.expert;out.down.stage:=2.U
    out.down.groupRows:=io.job.bits.groupRows;out.down.output:=io.job.bits.downOutput
    out.down.ownerSequence:=io.job.bits.firstOwnerSequence+3.U
    when(legal){state:=offerGate}.otherwise{fail(Status.Bounds.U,true.B)}
  }
  when((state===offerGate||state===offerUp||state===offerActivation||state===offerDown) && fault){
    // No new child start fires under fault. Local prior stages had explicit
    // successful retirement; unknown/raw-resource faults do NOT prove drain.
    val quiet= !quarantine && !unknownDense && !unknownActivation &&
      !dense.io.contextReserved && !activation.io.contextReserved &&
      !dense.io.resetRequired && !activation.io.resetRequired &&
      !io.denseResetRequired && !io.memoryResetRequired
    fail(Status.Dependency.U,quiet)
  }
  when(dense.io.command.fire){
    state:=Mux(state===offerGate,waitGate,Mux(state===offerUp,waitUp,waitDown))
  }
  when(dense.io.writeback.fire){
    val r=dense.io.writeback.bits
    val expected=Mux(state===waitGate,gateCmd,Mux(state===waitUp,upCmd,downCmd))
    val bytes=expected.groupRows.pad(64)*Mux(expected.stage===2.U,2048.U,512.U)*2.U
    val expectedCompleted=Mux(state===waitGate,0.U,Mux(state===waitUp,1.U,3.U))
    val exact=out.completedStages===expectedCompleted && r.context.asUInt===expected.context.asUInt && r.expert===expected.expert &&
      r.stage===expected.stage && r.groupRows===expected.groupRows && r.output===expected.output &&
      r.ownerSequence===expected.firstOwnerSequence && r.result.tag===expected.firstOwnerSequence &&
      r.result.writeBytes===bytes && r.result.status===Status.Ok.U && r.successfulWriteback
    when(!exact||fault){
      // QwenOwnerResult has no drained field. Its non-Ok or unknown provenance
      // cannot be promoted to a drained fence just because a terminal arrived.
      fail(Mux(!exact,Status.Dependency.U,Status.Protocol.U),false.B)
    }.otherwise{
      out.completedStages:=out.completedStages+1.U
      when(state===waitGate){activationJob.gate:=r;state:=offerUp}
      .elsewhen(state===waitUp){activationJob.up:=r;state:=offerActivation}
      .otherwise{
        out.down:=r;out.downCommitted:=true.B;out.status:=Status.Ok.U;out.drained:=true.B;state:=report
      }
    }
  }
  when(activation.io.job.fire){state:=waitActivation}
  when(activation.io.done.fire){
    val r=activation.io.done.bits
    out.activation:=r
    val (decoded,eligible)=UnifiedMoeActivationDownPlanV3.decode(r,job.downWeight,job.downOutput,
      job.firstOwnerSequence+3.U,fault)
    val exact=out.completedStages===2.U && r.context.asUInt===job.context.asUInt && r.expert===job.expert && r.groupRows===job.groupRows &&
      r.output===job.activationOutput && r.ownerSequence===job.firstOwnerSequence+2.U
    when(!exact|| !eligible){
      val locallyDrained=exact && r.drained && !quarantine && !unknownDense && !unknownActivation &&
        !dense.io.contextReserved && !dense.io.resetRequired && !activation.io.resetRequired
      fail(Mux(!exact,Status.Protocol.U,Mux(r.status=/=Status.Ok.U,r.status,Status.Dependency.U)),locallyDrained)
    }.otherwise{
      downCmd:=decoded;out.completedStages:=out.completedStages+1.U;state:=offerDown
    }
  }
  when(io.result.fire){state:=Mux(fault|| !out.drained,locked,idle)}
  // Held result bytes are never rewritten by late poison. The common parent
  // MUST check current resetRequired before a new down-reader offer and before
  // final block success; contextReserved also gates context end on both sides.
  // Error/undrained result is observable but does NOT release the owner lease.
  // No watchdog/reset occurs here: external isolation must prove stale-return
  // exclusion before reopening any private owner identity or resource credit.
}
