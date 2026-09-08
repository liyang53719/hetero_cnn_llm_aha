// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation

/** Actual decoder DUT, fixed real16 two-layer native-weight descriptors.
  * Only metadata service and owner completions are driven by the test;
  * numerical arithmetic is validated by the separate real-iDMA gates.
  */
class HostBlockCommandsNativeWeightsSpec extends HostBlockCommandsSpec {
  require(manifest("weight_storage").str == "bf16")
  require(integer("tokens") == 16 && integer("commands") == 42)
  override def dut = new HostBlockCommands(QwenBlockShape(), bf16Weights=true) {
    when(io.job.valid) {
      chisel3.assert(io.job.bits.weightBf16 === (io.job.bits.kind === QwenOwnerKind.Dense.U),
        "Native storage must be bound only to Dense B operands")
    }
  }
  it should "reject native B at the first GEMM when the capability is not enabled" in {
    test(new HostBlockCommands(QwenBlockShape(), bf16Weights=false))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
        initialize(d)
        val result=run(d)
        result._1 should not be 0
        result._2 shouldBe 1
        result._3 shouldBe 1
      }
  }
  it should "reject BF16 activations rather than changing the output precision contract" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      initialize(d)
      val root=((commands.head >> 80) & 0xffffff).toInt
      val payloadShift=56+52
      val invalid=descriptors.updated(root,
        (descriptors(root) & ~(BigInt(15)<<payloadShift)) | (BigInt(5)<<payloadShift))
      val result=run(d,ds=invalid)
      result._1 should not be 0
      result._2 shouldBe 0
      result._3 shouldBe 0
    }
  }
}
