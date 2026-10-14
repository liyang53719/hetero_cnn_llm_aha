// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** New H2048 same-bank ablation. No historical H1024 baseline claim. */
class GdnRmsNormFixedBankScalarBaselineSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  "GdnRmsNormFixedBankOwner" should "run same-bank H2048 with the production core Scalar and zero loans" in {
    test(new GdnRmsNormFixedBankArithmeticHarness(productionCore = true,
      useVectorEpilogue = false)).withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val (hidden, weight) = GdnRmsNormFixedBankReference.synthetic
      init(d)
      val report = run(d, hidden, weight, "same-bank-scalar-ablation-production-core-M1-H2048")
      report.output shouldBe GdnRmsNormFixedBankReference(hidden, weight).output
      for (fault <- Seq("read", "write", "abort-write", "wrong-tag-read")) {
        init(d); run(d, hidden, weight, "same-bank-scalar-" + fault, fault)
      }
      for (which <- 0 until 5) rejectBounds(d, which)
    }
  }
}
