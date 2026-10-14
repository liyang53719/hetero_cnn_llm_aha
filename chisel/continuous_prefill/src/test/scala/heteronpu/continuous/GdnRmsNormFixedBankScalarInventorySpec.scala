// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}

/** Pre-optimization CHIRRTL inventory, never mapped-area or timing evidence. */
class GdnRmsNormFixedBankScalarInventorySpec extends AnyFlatSpec with Matchers {
  def module(text:String,name:String):String=text.split("(?m)^  module ").find(_.startsWith(name+" :")).get
  def instances(text:String,name:String):Int=("(?m)^    inst [^\\n]+ of "+name+"(?:_[0-9]+)?(?: |$)").r.findAllIn(text).length
  def declarations(text:String,prefix:String):Seq[String]=text.linesIterator.filter(_.trim.startsWith(prefix))
    .map(_.trim.takeWhile(_!='@').trim).toSeq.sorted
  "Same-bank Scalar ablation" should "preserve all borrower registers and configured core arithmetic and memories" in {
    val out=Paths.get("../../work/h2048_same_bank_inventory");Files.createDirectories(out)
    def emit(vector:Boolean):String=circt.stage.ChiselStage.emitCHIRRTL(
      new GdnRmsNormFixedBankArithmeticHarness(productionCore=true,useVectorEpilogue=vector))
    val vector=emit(true);Files.writeString(out.resolve("vector.fir"),vector)
    val scalar=emit(false);Files.writeString(out.resolve("scalar.fir"),scalar)
    for(text<-Seq(vector,scalar)) {
      instances(text,"GdnRmsNormFixedBankOwner") shouldBe 1
      instances(text,"Qwen2ContinuousBlock") shouldBe 1
      instances(text,"BlockScalarFloat") shouldBe 1
      instances(text,"ElementwiseRegisterLoan") shouldBe 1
      instances(text,"HeteroFP32Alu") shouldBe 33
      val borrower=module(text,"GdnRmsNormFixedBankOwner")
      borrower.linesIterator.count(x=>x.trim.startsWith("reg ")&&x.contains("UInt<512>[32]")) shouldBe 3
      instances(borrower,"BlockScalarFloat") shouldBe 0
      instances(borrower,"ElementwiseRegisterLoan") shouldBe 0
    }
    for(prefix <- Seq("reg ", "regreset ")) {
      val vectorRegisters = declarations(module(vector,"GdnRmsNormFixedBankOwner"),prefix)
      val scalarRegisters = declarations(module(scalar,"GdnRmsNormFixedBankOwner"),prefix)
      vectorRegisters.nonEmpty shouldBe true
      vectorRegisters shouldBe scalarRegisters
    }
    declarations(vector,"smem ") shouldBe declarations(scalar,"smem ")
    println("H2048_SAME_BANK_INVENTORY_PASS borrower_bytes=6144 core_elem_sram_bytes=12288 scalar_services=1 elem_services=1 fp32_alu_instances=33 equal_owner_registers=true equal_memory_declarations=true physical_ppa=false")
  }
}
