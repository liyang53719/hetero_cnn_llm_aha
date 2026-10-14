// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Production core services at a small legacy core shape, not a full block run. */
class GdnRmsNormFixedBankCoreSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  "GdnRmsNormFixedBankOwner" should "borrow the original production core elementwise and Scalar instances" in {
    test(new GdnRmsNormFixedBankArithmeticHarness(productionCore = true))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
        val (hidden, weight) = GdnRmsNormFixedBankReference.synthetic
        init(d); run(d, hidden, weight, "production-core-M1-H2048")
        for (fault <- Seq("abort-write", "wrong-tag-read", "wrong-tag-loan")) {
          init(d); run(d, hidden, weight, "production-core-" + fault, fault)
        }
      }
  }
}
