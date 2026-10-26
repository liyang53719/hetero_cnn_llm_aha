// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class Qwen2Public21BoundaryV2Harness extends Module {
  val io = IO(new Bundle {
    val profileId = Input(UInt(3.W))
    val tokens = Input(UInt(16.W))
    val pc = Input(UInt(5.W))
    val corruptProfile = Input(Bool())
    val transactionId = Input(UInt(64.W))
    val boundary = Output(new Qwen2Public21BoundaryV2)
  })
  val context = WireDefault(0.U.asTypeOf(new UnifiedBlockDispatchV1))
  val (profile, _) = UnifiedRuntimeProfile.decode(io.profileId)
  context.profile := profile
  when(io.corruptProfile) { context.profile.hidden := 32.U }
  context.transactionId := io.transactionId
  context.launch.version := 1.U
  context.launch.profileId := io.profileId
  context.launch.tokens := io.tokens
  io.boundary := Qwen2Public21BoundaryV2.decode(context, io.pc)
}

/** Control-only: same DUT covers all five IDs. No arithmetic/numeric PASS. */
class Qwen2Public21BoundaryV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "Original Qwen2 public21 runtime numerical boundaries"
  it should "retain QKV ordered FP32 reductions and late BF16 materialization" in {
    test(new Qwen2Public21BoundaryV2Harness) { d =>
      d.io.corruptProfile.poke(false.B); d.io.transactionId.poke(1.U)
      for (profile <- 0 until 5; tokens <- Seq(1,16,128); pc <- 0 until 22) {
        d.io.profileId.poke(profile.U); d.io.tokens.poke(tokens.U); d.io.pc.poke(pc.U)
        val valid = profile == 0 && tokens != 1 && pc < 21
        val qkv = valid && Set(1,4,7)(pc)
        val rounded = valid && Set(13,16,17,19)(pc)
        d.io.boundary.valid.expect(valid.B)
        d.io.boundary.dense.expect((qkv || rounded).B)
        d.io.boundary.virtualAttentionStage.expect((valid && Set(10,11)(pc)).B)
        d.io.boundary.activationBf16Storage.expect(false.B)
        d.io.boundary.outputBf16Storage.expect(false.B)
        d.io.boundary.weightBf16Storage.expect((qkv || rounded).B)
        d.io.boundary.materializeDenseOutput.expect(rounded.B)
        d.io.boundary.requiresOrderedQkvReduction.expect(qkv.B)
        d.io.boundary.pairReverse.expect(qkv.B)
        d.io.boundary.firstKEnd.expect((if(qkv)1024 else 0).U)
        d.io.boundary.secondKBegin.expect((if(qkv)1024 else 0).U)
        d.io.boundary.secondKEnd.expect((if(qkv)1536 else 0).U)
        d.io.boundary.inputBytesPerElement.expect((if(valid)4 else 0).U)
        d.io.boundary.outputBytesPerElement.expect((if(valid)4 else 0).U)
      }
      d.io.profileId.poke(0.U); d.io.tokens.poke(128.U); d.io.pc.poke(1.U)
      d.io.corruptProfile.poke(true.B); d.io.boundary.valid.expect(false.B)
      d.io.corruptProfile.poke(false.B); d.io.transactionId.poke(0.U)
      d.io.boundary.valid.expect(false.B)
    }
  }
}
