// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private expert-group command. Routed m is actual groupRows (1..128), not a
  * loop of complete block M1 calls. Shared expert256 covers all launch tokens.
  * Source weights must already have the pinned BF16 [K,N] byte layout. */
class UnifiedMoeExpertDenseCommandV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val expert=UInt(9.W);val stage=UInt(2.W) // 0 gate,1 up,2 down;3 rejected
  val groupRows=UInt(8.W);val firstOwnerSequence=UInt(32.W)
  val input=UInt(64.W);val weight=UInt(64.W);val output=UInt(64.W)
}
class UnifiedMoeDenseWritebackV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val expert=UInt(9.W);val stage=UInt(2.W);val groupRows=UInt(8.W)
  val output=UInt(64.W);val ownerSequence=UInt(32.W)
  val result=new QwenOwnerResult
  val successfulWriteback=Bool()
}
object UnifiedMoeExpertDenseCommandV2 {
  def decode(c:UnifiedMoeExpertDenseCommandV2):(QwenOwnerJob,Bool)={
    val j=WireDefault(0.U.asTypeOf(new QwenOwnerJob))
    val (p,known)=UnifiedRuntimeProfile.decode(c.context.host.profileId)
    val down=c.stage===2.U
    val k=Mux(down,p.expertFfn,p.hidden);val n=Mux(down,p.hidden,p.expertFfn)
    val rows=c.groupRows
    val aEnd=c.input.pad(96)+(rows.pad(96)*k<<1)
    val bEnd=c.weight.pad(96)+(k.pad(96)*n<<1)
    val dEnd=c.output.pad(96)+(rows.pad(96)*n<<1)
    val limit=(BigInt(1)<<56).U
    val aligned=Seq(c.input,c.weight,c.output).map(x=>x=/=0.U && x(5,0)===0.U).reduce(_&&_)
    val noAlias= !(c.input.pad(96)<dEnd && c.output.pad(96)<aEnd) &&
      !(c.weight.pad(96)<dEnd && c.output.pad(96)<bEnd)
    val legal=known && p.asUInt===c.context.profile.asUInt && p.mlp===1.U &&
      p.expertCount===256.U && p.expertsPerToken===8.U && p.expertFfn===512.U && p.sharedFfn===512.U &&
      c.context.version===HostMoePhaseContextV4.Version.U && c.context.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.context.host) &&
      c.context.tokens>=1.U && c.context.tokens<=128.U &&
      c.expert<=256.U && c.stage<3.U && rows>=1.U && rows<=c.context.tokens &&
      (c.expert=/=256.U || rows===c.context.tokens) &&
      c.firstOwnerSequence=/="hffffffff".U && aligned && noAlias &&
      Seq(aEnd,bEnd,dEnd).map(_<=limit).reduce(_&&_)
    j.kind:=QwenOwnerKind.Dense.U;j.m:=rows;j.n:=n;j.k:=k
    j.a:=c.input;j.b:=c.weight;j.dst:=c.output;j.tag:=c.firstOwnerSequence
    // Unified QwenOwnerJob ABI515389: BF16 storage, not FP32-storage materialization.
    j.materializeDenseOutput:=false.B
    j.activationBf16:=true.B;j.weightBf16:=true.B;j.outputBf16:=true.B
    j.writeBytes:=rows.pad(64)*n*2.U
    (j,legal)
  }
}

/** Completion provenance adapter for the ONE original StreamingDenseOwner.
  * No Matrix, feeder, SRAM or ALU is instantiated. Parent must mux this private
  * job/done pair into that actual owner, retaining the same owner until terminal
  * write ACK; arbitrary Host completion packets are forbidden.
  *
  * successfulWriteback is derived here from actual done.fire plus exact byte,
  * tag and non-poison checks. It is not an input Boolean. Only successful DOWN
  * receipts may authorize the downstream DDR reader; gate/up never do.
  */
class UnifiedMoeDenseWritebackFenceV2 extends Module {
  val io=IO(new Bundle {
    val command=Flipped(Decoupled(new UnifiedMoeExpertDenseCommandV2))
    val job=Decoupled(new QwenOwnerJob)
    val done=Flipped(Decoupled(new QwenOwnerResult))
    val denseResetRequired=Input(Bool())
    val writeback=Decoupled(new UnifiedMoeDenseWritebackV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val idle::offer::waitDone::report::locked::Nil=Enum(5)
  val state=RegInit(idle)
  val job=Reg(new QwenOwnerJob);val out=Reg(new UnifiedMoeDenseWritebackV2)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val (decoded,legal)=UnifiedMoeExpertDenseCommandV2.decode(io.command.bits)
  // Unknown completion observed before the accepted job must never acquire the
  // new pending identity. Once a job is offered it remains stable despite fault;
  // quarantine then forbids attributing ANY old response to that new obligation.
  val unknownDone=io.done.valid && state=/=waitDone
  when(unknownDone){poison:=true.B;quarantine:=true.B}
  when(io.denseResetRequired){poison:=true.B}
  io.command.ready:=state===idle && !poison && !io.denseResetRequired && !io.done.valid
  io.job.valid:=state===offer;io.job.bits:=job
  io.done.ready:=state===waitDone && !quarantine
  io.writeback.valid:=state===report;io.writeback.bits:=out
  io.resetRequired:=poison||quarantine||io.denseResetRequired||unknownDone
  io.contextReserved:=state=/=idle || io.command.valid
  when(io.command.fire){
    job:=decoded
    out:=0.U.asTypeOf(new UnifiedMoeDenseWritebackV2)
    out.context:=io.command.bits.context;out.expert:=io.command.bits.expert;out.stage:=io.command.bits.stage
    out.groupRows:=io.command.bits.groupRows;out.output:=io.command.bits.output
    out.ownerSequence:=io.command.bits.firstOwnerSequence;out.result.tag:=io.command.bits.firstOwnerSequence
    when(legal){state:=offer}.otherwise{out.result.status:=Status.Bounds.U;state:=report}
  }
  when(io.job.fire){state:=waitDone}
  when(io.done.fire){
    val matchTag=io.done.bits.tag===job.tag
    val committed=matchTag && io.done.bits.status===Status.Ok.U &&
      io.done.bits.writeBytes===job.writeBytes && !poison && !io.denseResetRequired
    out.result:=io.done.bits;out.successfulWriteback:=committed
    when(!committed){out.result.status:=Mux(!matchTag,Status.Protocol.U,
      Mux(io.done.bits.status=/=Status.Ok.U,io.done.bits.status,Status.Dependency.U));poison:=true.B}
    state:=report
  }
  when(io.writeback.fire){state:=Mux(poison||quarantine||io.denseResetRequired,locked,idle)}
  // A source that never returns its accepted job has no fabricated done/fence.
  // Full owner isolation/reset is required after quarantined unknown completion.
}
