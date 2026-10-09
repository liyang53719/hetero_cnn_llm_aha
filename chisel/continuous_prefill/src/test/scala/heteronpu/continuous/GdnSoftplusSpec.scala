// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Shared-resource opcode, never an independent Softplus hardware block. */
class GdnSoftplusSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnInputPrepSupport {
  "Shared FP32 Softplus7" should "match separate RNE recipe across its explicit supported domain and preserve transaction ownership" in {
    test(new BlockScalarFloat(enableSoftplus = true)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      d.io.request.valid.poke(false.B); d.io.result.ready.poke(false.B)
      d.io.request.bits.op.poke(0.U); d.io.request.bits.a.poke(0.U); d.io.request.bits.b.poke(0.U)
      d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
      val supported = Seq(-79.999f, -79f, -60f, -40f, -20f, -5f, -1f, -1e-7f, -0f, 0f, 1e-7f, 1f, 5f,
        java.lang.Math.nextDown(20f), 20f, java.lang.Math.nextUp(20f), 40f, 80f, 100f, Float.MaxValue)
      for ((x, index) <- supported.zipWithIndex) {
        d.io.request.ready.expect(true.B); d.io.request.bits.op.poke(ScalarOp.Softplus.U)
        d.io.request.bits.a.poke(bits(x).U); d.io.request.bits.b.poke(0.U); d.io.request.valid.poke(true.B)
        d.clock.step(); d.io.request.valid.poke(false.B)
        // Accepted operands and policy must remain latched despite bus changes.
        d.io.request.bits.op.poke(0.U); d.io.request.bits.a.poke(bits(Float.NaN).U); d.io.request.bits.b.poke(bits(Float.PositiveInfinity).U)
        var latency = 0
        while (!d.io.result.valid.peek().litToBoolean && latency < 200) { d.io.request.ready.expect(false.B); d.clock.step(); latency += 1 }
        assert(latency < 200); d.io.error.expect(false.B); d.io.result.bits.expect(bits(softplus(x)).U)
        val expected = d.io.result.bits.peek().litValue
        d.clock.step(index % 7 + 1); d.io.result.valid.expect(true.B); d.io.error.expect(false.B); d.io.result.bits.expect(expected.U); d.io.request.ready.expect(false.B)
        println(s"GDN_SOFTPLUS_RTL x=$x raw=0x${expected.toString(16)} latency=$latency")
        d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
      }
      // Finite x<=-80 is mathematically legal, but unsupported by this service's
      // exp range. Inf and NaN follow the existing fail-closed Scalar policy.
      for (x <- Seq(-80f, -100f, -Float.MaxValue, Float.NegativeInfinity, Float.PositiveInfinity, Float.NaN)) {
        d.io.request.bits.op.poke(ScalarOp.Softplus.U); d.io.request.bits.a.poke(bits(x).U); d.io.request.bits.b.poke(0.U)
        d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
        d.io.result.valid.expect(true.B); d.io.error.expect(true.B)
        d.clock.step(9); d.io.error.expect(true.B); d.io.result.valid.expect(true.B)
        d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
      }
      d.io.request.bits.op.poke(ScalarOp.Softplus.U); d.io.request.bits.a.poke(bits(0f).U); d.io.request.bits.b.poke(0.U)
      d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B); d.clock.step(7)
      d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
      d.io.result.valid.expect(false.B); d.io.request.ready.expect(true.B)
      d.io.request.bits.op.poke(ScalarOp.Add.U); d.io.request.bits.a.poke(bits(1f).U); d.io.request.bits.b.poke(bits(2f).U)
      d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
      while (!d.io.result.valid.peek().litToBoolean) d.clock.step()
      d.io.error.expect(false.B); d.io.result.bits.expect(bits(3f).U)
    }
  }
  it should "remain disabled by default for legacy callers" in {
    test(new BlockScalarFloat).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      d.io.request.valid.poke(false.B); d.io.result.ready.poke(false.B)
      d.io.request.bits.op.poke(ScalarOp.Softplus.U); d.io.request.bits.a.poke(0.U); d.io.request.bits.b.poke(0.U)
      d.reset.poke(true.B); d.clock.step(3); d.reset.poke(false.B); d.clock.step()
      d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
      d.io.result.valid.expect(true.B); d.io.error.expect(true.B); d.io.result.bits.expect(0.U)
    }
  }
}
