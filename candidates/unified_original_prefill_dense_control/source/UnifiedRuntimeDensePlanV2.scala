// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Private scheduler roles, not a new Host command or an entire block. Bias,
  * normalization, attention/GDN and MoE expert routing remain separate stages. */
object UnifiedDenseRoleV2 {
  val MixerInput=0; val AttentionKey=1; val AttentionValue=2; val MixerOutput=3
  val DenseGate=4; val DenseUp=5; val DenseDown=6; val GdnZ=7; val GdnAB=8
}
object UnifiedDenseRouteV2 {val StreamingBf16=0;val Qwen2Public21=1}
class UnifiedRuntimeDenseCommandV2 extends Bundle {
  val context=new UnifiedBlockDispatchV1
  val role=UInt(4.W)
  val input=UInt(64.W); val weight=UInt(64.W); val output=UInt(64.W)
  // Reserved by the one scheduler for this feeder's sequence of Matrix groups.
  val firstOwnerSequence=UInt(32.W)
}
class UnifiedRuntimeDensePlanV2 extends Bundle {
  val context=new UnifiedBlockDispatchV1; val role=UInt(4.W)
  val firstOwnerSequence=UInt(32.W); val job=new QwenOwnerJob
  val route=UInt(2.W)
  val publicPc=UInt(5.W);val qwen2Boundary=new Qwen2Public21BoundaryV2
  // Conservative original streaming groups; route1's numerical router must
  // reserve its own K-window groups and may not interpret zero as free credit.
  val maximumMatrixGroups=UInt(32.W)
  val valid=Bool()
}
object UnifiedRuntimeDensePlanV2 {
  /** Fixed decode, NOT a claim that geometric equality preserves reduction.
    * Qwen2 uses its existing public21 numerical route and FP32 containers;
    * QKV must retain its K-window/pair-reverse/fold and post-bias rounding.
    * The other profiles' streaming route uses BF16 storage and K-major [K,N]
    * weights. A [N,K] source requires a separately pinned byte transpose.
    * Neither route authorizes a Host-produced intermediate tensor. */
  def decode(c:UnifiedRuntimeDenseCommandV2):UnifiedRuntimeDensePlanV2={
    val p=WireDefault(0.U.asTypeOf(new UnifiedRuntimeDensePlanV2))
    p.context:=c.context; p.role:=c.role; p.firstOwnerSequence:=c.firstOwnerSequence
    val (shape,known)=UnifiedRuntimeProfile.decode(c.context.launch.profileId)
    val same=known && shape.asUInt===c.context.profile.asUInt
    val qwen2=shape.profileId===UnifiedProfileId.Qwen2Attention.U
    p.route:=Mux(qwen2,UnifiedDenseRouteV2.Qwen2Public21.U,UnifiedDenseRouteV2.StreamingBf16.U)
    val pc=MuxLookup(c.role,31.U(5.W))(Seq(0.U->1.U,1.U->4.U,2.U->7.U,3.U->13.U,4.U->16.U,5.U->17.U,6.U->19.U))
    val boundary=Qwen2Public21BoundaryV2.decode(c.context,pc)
    p.publicPc:=pc;p.qwen2Boundary:=boundary
    val q=shape.attentionHeads*shape.headDim
    val kv=shape.kvHeads*shape.headDim
    val gv=shape.gdnValueHeads*shape.gdnValueDim
    val gqk=shape.gdnKeyHeads*shape.gdnKeyDim
    val k=WireDefault(shape.hidden); val n=WireDefault(0.U(16.W))
    val roleOK=WireDefault(false.B)
    switch(c.role){
      is(UnifiedDenseRoleV2.MixerInput.U){
        n:=Mux(shape.mixer===1.U,(gqk<<1)+gv,
          Mux(shape.profileId===UnifiedProfileId.Qwen2Attention.U,q,q<<1))
        roleOK:=true.B
      }
      is(UnifiedDenseRoleV2.AttentionKey.U){n:=kv;roleOK:=shape.mixer===0.U}
      is(UnifiedDenseRoleV2.AttentionValue.U){n:=kv;roleOK:=shape.mixer===0.U}
      is(UnifiedDenseRoleV2.MixerOutput.U){k:=Mux(shape.mixer===1.U,gv,q);n:=shape.hidden;roleOK:=true.B}
      is(UnifiedDenseRoleV2.DenseGate.U){n:=shape.ffn;roleOK:=shape.mlp===0.U}
      is(UnifiedDenseRoleV2.DenseUp.U){n:=shape.ffn;roleOK:=shape.mlp===0.U}
      is(UnifiedDenseRoleV2.DenseDown.U){k:=shape.ffn;n:=shape.hidden;roleOK:=shape.mlp===0.U}
      is(UnifiedDenseRoleV2.GdnZ.U){n:=gv;roleOK:=shape.mixer===1.U}
      is(UnifiedDenseRoleV2.GdnAB.U){n:=shape.gdnValueHeads<<1;roleOK:=shape.mixer===1.U}
    }
    val m=c.context.launch.tokens
    val groups=((m.pad(32)+15.U)>>4)*((n.pad(32)+255.U)>>8)
    p.maximumMatrixGroups:=Mux(qwen2,0.U,groups)
    // Every streaming group covers >=one16-row/256-column tile (with tails).
    // Preserve one non-wrapping sequence for every possible group, not merely
    // the first. The all-ones value is never acquired by the parent controller.
    val sequenceReserved=qwen2 || (c.firstOwnerSequence.pad(65)+groups)<="hffffffff".U(65.W)
    val elementBytes=Mux(qwen2,boundary.inputBytesPerElement,2.U(3.W))
    val aEnd=c.input.pad(96)+m.pad(96)*k*elementBytes
    val bEnd=c.weight.pad(96)+(k.pad(96)*n<<1)
    val dEnd=c.output.pad(96)+m.pad(96)*n*elementBytes
    val limit=(BigInt(1)<<56).U
    val aligned=Seq(c.input,c.weight,c.output).map(x=>x=/=0.U && x(5,0)===0.U).reduce(_&&_)
    val noAlias= !(c.input.pad(96)<dEnd && c.output.pad(96)<aEnd) &&
      !(c.weight.pad(96)<dEnd && c.output.pad(96)<bEnd)
    p.valid:=same && c.context.transactionId=/=0.U && c.context.launch.version===1.U &&
      c.context.launch.opcode===0.U && m>0.U && m<=128.U && roleOK && (!qwen2 || boundary.dense) &&
      k>0.U && k<=8960.U && n>0.U && n<=8960.U && k(4,0)===0.U && n(4,0)===0.U &&
      c.firstOwnerSequence=/="hffffffff".U && sequenceReserved && aligned && noAlias &&
      Seq(aEnd,bEnd,dEnd).map(_<=limit).reduce(_&&_)
    p.job.kind:=QwenOwnerKind.Dense.U; p.job.m:=m; p.job.n:=n; p.job.k:=k
    p.job.a:=c.input; p.job.b:=c.weight; p.job.dst:=c.output
    p.job.tag:=c.firstOwnerSequence
    p.job.activationBf16:=Mux(qwen2,boundary.activationBf16Storage,true.B)
    p.job.weightBf16:=Mux(qwen2,boundary.weightBf16Storage,true.B)
    p.job.outputBf16:=Mux(qwen2,boundary.outputBf16Storage,true.B)
    p.job.materializeDenseOutput:=qwen2 && boundary.materializeDenseOutput
    p.job.writeBytes:=m.pad(64)*n*elementBytes
    p
  }
}
