// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class GdnRmsNormFixedBankScalarEpilogueCancellationSpec extends AnyFlatSpec
    with ChiselScalatestTester with Matchers with GdnRmsNormFixedBankScalarEpilogueSupport {
  "Same-bank production-core Scalar epilogue" should
    "drain normalize gamma weighted cancellation and explicitly recover without reset" in {
    test(new GdnRmsNormFixedBankScalarEpilogueHarness)
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
      val (hidden, weight) = GdnRmsNormFixedBankReference.synthetic
      init(d) // The only global reset in the complete twelve-case sequence.
      for (phase <- 0 until 3; (point, clearOnly) <- Seq(
        ("offer", false), ("accepted", false), ("held", false), ("held", true))) {
        val cut = Cut(phase, point, clearOnly = clearOnly)
        val label = s"${cut.phaseName}-$point-${if (clearOnly) "clear" else "abort"}"
        runScalarPrefix(d, hidden, weight, label, cut)
        clearScalarFailure(d, label)
        // The next iteration must really accept and execute its full reduction
        // on these same physical services, with no intervening global reset.
      }
      val recovered = run(d, hidden, weight, "scalar-epilogue-full-reuse-after-twelve-cancellations")
      recovered.output shouldBe GdnRmsNormFixedBankReference(hidden, weight, useVectorEpilogue = false).output
      recovered.scalarRequests shouldBe 10412; recovered.scalarResults shouldBe 10412
      recovered.loans shouldBe 0; recovered.writeAcks shouldBe 64
    }
  }
}
