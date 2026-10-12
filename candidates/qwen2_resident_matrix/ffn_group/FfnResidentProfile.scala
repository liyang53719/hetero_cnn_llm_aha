// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

/** Explicit opt-in execution contract. Ordinary emitters/drivers are unchanged.
  * Normal Command128 Dense/Dense/Activation are admitted by public descriptors
  * and policies. Gate/Up D are virtual FULL allocations for this profile; the
  * Host preflight rejects every outside reference before resident execution.
  * There is no numerical or performance acceptance implied by this emitter.
  */
object EmitHostResidentFfn extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  val s=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(s,16,true,burst,false,false,enableTransposedDown=true,enableResidentFfn=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"resident_ffn":true,"default_enabled":false,"public_opcodes":[32,32,53],"virtual_gate_up":true,"whole_launch_root_preflight":true,"m":[16,128],"k":1536,"n":8960,"tile_n":160,"groups":56,"act_ddr_ack_required":true,"down_uses_act_ddr":true,"silu_lanes":16,"matrix_macs":4096,"sram_bytes":786432,"idma_instances":1,"burst_writes":${burst},"native_arithmetic_accepted":false,"fp32_final_accepted":false,"numeric_policy_approved":false}\n""")
}
