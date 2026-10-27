// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private accepted-scheduler role, not a Host command. postnorm/weight/output
  * regions and their lifetimes are allocated and authenticated by the parent.
  * This is router Dense [M,2048] x [2048,256], NOT an expert FFN stage.
  * Official captures for BOTH profiles have BF16 [M,256] logits. Softmax then
  * expands those stored values to FP32; materializeDenseOutput is NOT used to
  * silently change the DDR element width to four bytes. */
class UnifiedMoeRouterDenseCommandV2 extends Bundle {
  val context=new HostMoePhaseContextV4
  val postnorm=UInt(64.W);val weight=UInt(64.W);val output=UInt(64.W)
  val allocationEnd=UInt(64.W);val ownerSequence=UInt(32.W)
}
class UnifiedMoeRouterLogitCommitV2 extends Bundle {
  val command=new UnifiedMoeRouterDenseCommandV2
  val result=new QwenOwnerResult
  val successfulWriteback=Bool()
}
object UnifiedMoeRouterDenseCommandV2 {
  def decode(c:UnifiedMoeRouterDenseCommandV2):(QwenOwnerJob,Bool)={
    val j=WireDefault(0.U.asTypeOf(new QwenOwnerJob))
    val (p,known)=UnifiedRuntimeProfile.decode(c.context.host.profileId)
    val m=c.context.tokens
    val aEnd=c.postnorm.pad(96)+(m.pad(96)*2048.U<<1)
    val bEnd=c.weight.pad(96)+(2048*256*2).U
    val dEnd=c.output.pad(96)+(m.pad(96)*256.U<<1)
    val groups=(m.pad(65)+15.U)>>4
    val aligned=Seq(c.postnorm,c.weight,c.output).map(x=>x=/=0.U && x(5,0)===0.U).reduce(_&&_)
    val noAlias= !(c.output.pad(96)<aEnd && c.postnorm.pad(96)<dEnd) &&
      !(c.output.pad(96)<bEnd && c.weight.pad(96)<dEnd)
    val legal=known && p.asUInt===c.context.profile.asUInt && p.mlp===1.U &&
      p.hidden===2048.U && p.expertCount===256.U && p.expertsPerToken===8.U &&
      c.context.version===HostMoePhaseContextV4.Version.U && c.context.phase===HostMoePhaseContextV4.MoePhase.U && HostCommandLaunchV4.known(c.context.host) &&
      m>=1.U && m<=128.U && c.postnorm===c.context.input.address &&
      aEnd===c.context.input.paddedEnd.pad(96) && c.ownerSequence=/="hffffffff".U &&
      c.ownerSequence.pad(65)+groups<="hffffffff".U(65.W) && aligned && noAlias &&
      c.output>=c.context.host.regions(3).base && dEnd<=c.allocationEnd.pad(96) &&
      Seq(aEnd,bEnd,dEnd).map(_<=(BigInt(1)<<56).U).reduce(_&&_)
    j.kind:=QwenOwnerKind.Dense.U;j.m:=m;j.k:=2048.U;j.n:=256.U
    j.a:=c.postnorm;j.b:=c.weight;j.dst:=c.output;j.tag:=c.ownerSequence
    j.activationBf16:=true.B;j.weightBf16:=true.B;j.outputBf16:=true.B
    j.materializeDenseOutput:=false.B;j.writeBytes:=m.pad(64)*512.U
    (j,legal)
  }
}

/** Exactly one original Dense owner is borrowed. Its actual result.fire is the
  * ONLY source of this private commit. A matching tag alone is insufficient:
  * accepted full context, base, element width, expected bytes and sequence stay
  * in the retained command. Parent side ledger must prove the postnorm producer
  * and [K,N] weight transpose; this module cannot manufacture either provenance.
  * A late fault preserves an already offered commit; downstream admission must
  * also gate CURRENT resetRequired, not merely successfulWriteback. */
class UnifiedMoeRouterDenseFenceV2 extends Module {
  val io=IO(new Bundle {
    val command=Flipped(Decoupled(new UnifiedMoeRouterDenseCommandV2))
    val job=Decoupled(new QwenOwnerJob);val done=Flipped(Decoupled(new QwenOwnerResult))
    val denseResetRequired=Input(Bool())
    val commit=Decoupled(new UnifiedMoeRouterLogitCommitV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
  })
  val idle::offer::waiting::report::locked::Nil=Enum(5)
  val state=RegInit(idle);val job=Reg(new QwenOwnerJob);val out=Reg(new UnifiedMoeRouterLogitCommitV2)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val unknown=io.done.valid && state=/=waiting
  val (decoded,legal)=UnifiedMoeRouterDenseCommandV2.decode(io.command.bits)
  when(unknown){poison:=true.B;quarantine:=true.B}
  when(io.denseResetRequired){poison:=true.B}
  io.resetRequired:=poison||quarantine||unknown||io.denseResetRequired
  io.contextReserved:=state=/=idle || io.command.valid
  io.command.ready:=state===idle && !io.resetRequired
  io.job.valid:=state===offer;io.job.bits:=job
  io.done.ready:=state===waiting && !quarantine
  io.commit.valid:=state===report;io.commit.bits:=out
  when(io.command.fire){
    job:=decoded;out:=0.U.asTypeOf(new UnifiedMoeRouterLogitCommitV2)
    out.command:=io.command.bits;out.result.tag:=io.command.bits.ownerSequence
    when(legal){state:=offer}.otherwise{out.result.status:=Status.Bounds.U;state:=report}
  }
  when(io.job.fire){state:=waiting}
  when(io.done.fire){
    val good=io.done.bits.tag===job.tag && io.done.bits.status===Status.Ok.U &&
      io.done.bits.writeBytes===job.writeBytes && !poison && !io.denseResetRequired
    out.result:=io.done.bits;out.successfulWriteback:=good
    when(!good){
      out.result.status:=Mux(io.done.bits.tag=/=job.tag,Status.Protocol.U,
        Mux(io.done.bits.status=/=Status.Ok.U,io.done.bits.status,Status.Dependency.U))
      poison:=true.B
    }
    state:=report
  }
  when(io.commit.fire){state:=Mux(io.resetRequired,locked,idle)}
  // Unknown raw completions cannot be attached to a later accepted job. There
  // is no local clear/abort that pretends the original owner has drained.
}
