// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation

/** Real Qwen2 dimensions and a two-layer Host graph, CONTROL-ONLY gate.
  * The decoder is the actual Chisel DUT. The test services metadata and owner
  * completions; it does not simulate the Matrix arithmetic or the iDMA backend.
  * Inherited tests keep the same descriptor, event, backpressure and reset
  * checks used by the tiny gate, now with 42 commands and 430 descriptors.
  */
class HostBlockCommandsRealLayersSpec extends HostBlockCommandsSpec {
  private val shape = manifest("shape")
  require(shape("H").num.toInt == 1536 && shape("F").num.toInt == 8960,
    "real Qwen2 hidden/FFN dimensions required")
  require(shape("HEADS").num.toInt == 12 && shape("KVHEADS").num.toInt == 2 &&
    shape("HD").num.toInt == 128, "real Qwen2 attention dimensions required")
  require(integer("tokens") == 16 && integer("layers") == 2 &&
    integer("commands") == 42 && integer("descriptors") == 430,
    "fixed real16 two-layer public command graph required")

  override def dut: HostBlockCommands =
    new HostBlockCommands(QwenBlockShape(retainedMatrix = true))

  it should "reject a failed second-layer InputNorm without publishing event 22" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      initialize(d)
      val result = run(d, failJob = 21, doneError = 3)
      result._1 should not be 0
      result._2 shouldBe 20 // 19 physical jobs in layer 0, then layer-1 Norm.
      result._3 shouldBe 21 // Only the complete first layer is visible.
      d.io.resetRequired.expect(true.B)
    }
  }

  it should "reject a short final second-layer writeback without publishing event 42" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      initialize(d)
      val result = run(d, failJob = 41, short = true)
      result._1 should not be 0
      result._2 shouldBe 38
      result._3 shouldBe 41
      d.io.resetRequired.expect(true.B)
    }
  }
}
