// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import heteronpu.experimental.StrictFp32MatrixLane
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class RetainedBackendLaneCrosscheckSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  it should "cross-check finite BF16 FMA bits and flags against the original HardFloat lane" in {
    test(new StrictFp32MatrixLane).withAnnotations(Seq(TreadleBackendAnnotation)) { d =>
      d.io.request.valid.poke(false.B); d.io.result.ready.poke(false.B)
      d.reset.poke(true.B); d.clock.step(2); d.reset.poke(false.B)
      for ((v, n) <- EndpointFmaFixture.all.zipWithIndex) {
        d.io.request.ready.expect(true.B)
        d.io.request.bits.tag.poke(n.U); d.io.request.bits.mode.poke(0.U)
        d.io.request.bits.a.poke(v.a.U); d.io.request.bits.b.poke(v.b.U); d.io.request.bits.acc.poke(v.c.U)
        d.io.request.valid.poke(true.B); d.clock.step(); d.io.request.valid.poke(false.B)
        for (_ <- 0 until 4) { d.io.result.valid.expect(false.B); d.clock.step() }
        d.io.result.valid.expect(true.B)
        val calculated = FiniteFp32Backend.fma(v.a.toLong << 16, v.b.toLong << 16, v.c)
        calculated shouldBe FiniteFp32Backend.Rounded(v.value, v.flags)
        d.io.result.bits.value.expect(BigInt(calculated.value).U)
        d.io.result.bits.fmaFlags.expect(calculated.flags.U)
        d.io.result.bits.status.expect(0.U); d.io.result.bits.fmaFlagsValid.expect(true.B)
        d.io.result.bits.accCommit.expect(true.B)
        d.clock.step(2)
        d.io.result.bits.value.expect(BigInt(calculated.value).U)
        d.io.result.ready.poke(true.B); d.clock.step(); d.io.result.ready.poke(false.B)
      }
    }
  }
}
