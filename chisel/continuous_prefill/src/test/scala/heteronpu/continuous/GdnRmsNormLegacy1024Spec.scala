// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class GdnRmsNormLegacy1024Spec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormTestSupport {
  "Default GdnRmsNormOwner" should "retain the original H1024 Scalar-only path and exact BF16 output" in {
    test(new GdnRmsNormArithmeticHarness(1024)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val (allHidden,allWeight)=GdnRmsNormFixedBankReference.synthetic
      val hidden=allHidden.take(1024);val weight=allWeight.take(1024)
      init(d);val result=run(d,hidden,weight,"legacy-H1024-synthetic",trace=true)
      result shouldBe reference(hidden,weight)._1
    }
  }
}
