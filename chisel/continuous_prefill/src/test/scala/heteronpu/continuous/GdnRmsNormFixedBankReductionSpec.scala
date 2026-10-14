// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}

/** Local core-service candidate. No full-kernel or physical banking claim. */
class GdnRmsNormFixedBankReductionSpec extends AnyFlatSpec with ChiselScalatestTester
    with Matchers with GdnRmsNormFixedBankTestSupport {
  "Fixed-bank vector reduction" should "drain a real wrong-tag loan and accepted write abort then reuse without reset" in {
    val (hidden,weight)=GdnRmsNormFixedBankReference.synthetic
    test(new GdnRmsNormFixedBankArithmeticHarness(productionCore=true,useVectorReduction=true))
      .withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d)
      def recover():Unit={
        d.io.job.ready.expect(false.B);d.io.drained.expect(true.B)
        d.io.clear.poke(true.B);d.clock.step();d.io.clear.poke(false.B)
        var wait=0
        while(!d.io.job.ready.peek().litToBoolean && wait<20){d.clock.step();wait+=1}
        assert(wait<20,"drained clear must recover the existing services")
        d.io.resetRequired.expect(false.B);d.io.locked.expect(false.B);d.io.drained.expect(true.B)
      }
      run(d,hidden,weight,"vector-reduction-wrong-tag-loan",fault="wrong-tag-loan")
      recover()
      run(d,hidden,weight,"vector-reduction-accepted-write-abort",fault="abort-write")
      recover()
      run(d,hidden,weight,"vector-reduction-same-dut-reuse")
    }
  }

  it should "retain the same bank registers and configured core arithmetic with the reduction lease enabled" in {
    val out=Paths.get("../../work/h2048_reduction_inventory");Files.createDirectories(out)
    def emit(enabled:Boolean):String=circt.stage.ChiselStage.emitCHIRRTL(
      new GdnRmsNormFixedBankArithmeticHarness(productionCore=true,useVectorReduction=enabled))
    val baseline=emit(false);val candidate=emit(true)
    Files.writeString(out.resolve("baseline.fir"),baseline);Files.writeString(out.resolve("candidate.fir"),candidate)
    def module(s:String,name:String):String=s.split("(?m)^  module ").find(_.startsWith(name+" :")).get
    def declarations(s:String,prefix:String):Seq[String]=s.linesIterator.filter(_.trim.startsWith(prefix))
      .map(_.trim.takeWhile(_!='@').trim).toSeq.sorted
    def instances(s:String,name:String):Int=("(?m)^    inst [^\\n]+ of "+name+"(?:_[0-9]+)?(?: |$)").r.findAllIn(s).length
    for(s<-Seq(baseline,candidate)){
      instances(s,"GdnRmsNormFixedBankOwner") shouldBe 1
      instances(s,"Qwen2ContinuousBlock") shouldBe 1
      instances(s,"BlockScalarFloat") shouldBe 1
      instances(s,"ElementwiseRegisterLoan") shouldBe 1
      instances(s,"HeteroFP32Alu") shouldBe 33
      val owner=module(s,"GdnRmsNormFixedBankOwner")
      owner.linesIterator.count(x=>x.trim.startsWith("reg ")&&x.contains("UInt<512>[32]")) shouldBe 3
    }
    for(prefix<-Seq("reg ","regreset ")){
      val a=declarations(module(baseline,"GdnRmsNormFixedBankOwner"),prefix)
      a.nonEmpty shouldBe true
      a shouldBe declarations(module(candidate,"GdnRmsNormFixedBankOwner"),prefix)
    }
    declarations(baseline,"smem ") shouldBe declarations(candidate,"smem ")
    println("H2048_VECTOR_REDUCTION_INVENTORY_PASS borrower_bytes=6144 weight_scratch_lease_bytes=128 output_residue_bytes=128 scalar_services=1 elem_services=1 fp32_alu_instances=33 unchanged_owner_registers=true unchanged_memory_declarations=true physical_ppa=false")
  }
}
