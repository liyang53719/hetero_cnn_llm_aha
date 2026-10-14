// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Counter semantics: reply holding must not turn into ALU execution. */
class GdnRmsNormFixedBankObservationSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  "Original core service observations" should "separate extra held reply clocks from useful ALU execution" in {
    test(new GdnRmsNormFixedBankArithmeticHarness(productionCore=true))
      .withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val (hidden,weight)=GdnRmsNormFixedBankReference.synthetic
      init(d)
      val base=run(d,hidden,weight,"counter-base-M1")
      // 323 is a multiple of both loan request/result stall periods (17/19).
      // No Scalar request follows the first loan in this single-token case.
      val delayed=run(d,hidden,weight,"counter-extra-reply-hold-M1",extraFirstLoanHold=323)
      delayed.output shouldBe base.output
      delayed.launchToDoneFireCycles shouldBe base.launchToDoneFireCycles+323L
      delayed.arithmeticCycles("elem_service_busy") shouldBe base.arithmeticCycles("elem_service_busy")+323L
      delayed.arithmeticCycles("elem_reply_resident") shouldBe base.arithmeticCycles("elem_reply_resident")+323L
      delayed.arithmeticCycles("elem_result_held") shouldBe base.arithmeticCycles("elem_result_held")+323L
      for (metric<-Seq("elem_alu_execution_busy","elem_alu_attempt_lane","elem_alu_effective_lane",
        "elem_mul_effective_lane","elem_add_effective_lane","scalar_alu_execution_busy","scalar_divider_pending"))
        delayed.arithmeticCycles(metric) shouldBe base.arithmeticCycles(metric)
      println("H2048_OBSERVATION_HOLD_PASS extra_wall=323 extra_service_busy=323 extra_alu_execution=0 same_dut_without_reset=true")
    }
  }
}
