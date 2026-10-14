// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class GdnRmsNormFixedBankCoreCancellationSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankCancellationTestSupport {
  "GdnRmsNormFixedBankOwner" should "cancel and recover the original production core services without module reset" in {
    test(new GdnRmsNormFixedBankCancellationHarness(productionCore = true))
      .withAnnotations(Seq(VerilatorBackendAnnotation)) { d =>
        exerciseCancellationPaths(d, "production-core-cancellation")
      }
  }
}
