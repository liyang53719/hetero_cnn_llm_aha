// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class GdnRmsNormFixedBankScalarEpilogueNumericalSpec extends AnyFlatSpec
    with ChiselScalatestTester with Matchers with GdnRmsNormFixedBankScalarEpilogueSupport {
  import GdnRmsNormFixedBankScalarEpilogueFixtures._
  "Same-bank production-core Scalar epilogue" should
    "retain finite BF16 signed zero subnormal ties and reject real weighted overflows" in {
    checkFixtures() // Only validates host expectations; it supplies no DUT result.
    test(new GdnRmsNormFixedBankScalarEpilogueHarness)
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      init(d) // No further global reset, including after numerical failures.
      val finite = run(d, finiteHidden, finiteWeight, "scalar-epilogue-signed-zero-subnormal-rne-ties")
      finite.output.take(18) shouldBe finitePrefix
      finite.scalarRequests shouldBe 10412; finite.scalarResults shouldBe 10412
      finite.loans shouldBe 0; finite.writeAcks shouldBe 64
      for (nonfinite <- Seq(false, true)) {
        val label = if (nonfinite) "weighted-fp32-nonfinite" else "weighted-finite-fp32-bf16-overflow"
        val expected = BigInt(if (nonfinite) "7f800000" else "7f7ffbc0", 16)
        runScalarPrefix(d, overflowHidden, overflowWeight(nonfinite), label,
          Cut(2, "held", numerical = true, targetBits = Some(expected), targetError = nonfinite))
        clearScalarFailure(d, label)
      }
      val reused = run(d, finiteHidden, finiteWeight, "scalar-epilogue-finite-reuse-after-numerical-clear")
      reused.output shouldBe finite.output
      reused.scalarRequests shouldBe 10412; reused.scalarResults shouldBe 10412
      reused.loans shouldBe 0; reused.writeAcks shouldBe 64
    }
  }
}
