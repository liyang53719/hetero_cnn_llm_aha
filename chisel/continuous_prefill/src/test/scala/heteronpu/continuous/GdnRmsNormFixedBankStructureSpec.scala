// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}

/** Elaboration inventory only; not synthesis or complete kernel execution. */
class GdnRmsNormFixedBankStructureSpec extends AnyFlatSpec with Matchers {
  def module(text:String,name:String):String = text.split("(?m)^  module ").find(_.startsWith(name+" :"))
    .getOrElse(throw new IllegalArgumentException("missing module "+name))
  def instances(text:String,name:String):Int=("(?m)^    inst [^\\n]+ of "+name+"(?:_[0-9]+)?(?: |$)").r.findAllIn(text).length
  def memories(text:String):Seq[String]=text.linesIterator.filter(_.trim.startsWith("smem "))
    .map(_.trim.takeWhile(_!='@').trim).toSeq.sorted
  "H2048 borrower integration" should "statically replace one original RMS and elem while preserving default resource inventory" in {
    val out=Paths.get("../../work/h2048_borrower_structure");Files.createDirectories(out)
    def emit(enabled:Boolean):String=circt.stage.ChiselStage.emitCHIRRTL(new QwenOwnerKernel(
      QwenBlockShape.qwen35Gdn(1),pipelined=true,bf16Gdn=true,bf16GdnCore=true,bf16GdnBlock=true,
      enableH2048RmsBorrower=enabled))
    val base=emit(false);Files.writeString(out.resolve("default_kernel.fir"),base)
    val loan=emit(true);Files.writeString(out.resolve("borrower_kernel.fir"),loan)
    instances(base,"GdnRmsNormOwner") shouldBe 1
    instances(base,"GdnRmsNormFixedBankOwner") shouldBe 0
    instances(loan,"GdnRmsNormOwner") shouldBe 0
    instances(loan,"GdnRmsNormFixedBankOwner") shouldBe 1
    val baseCore=module(base,"Qwen2ContinuousBlock");val loanCore=module(loan,"Qwen2ContinuousBlock")
    instances(baseCore,"ElementwiseMemoryEngine") shouldBe 1
    instances(baseCore,"ElementwiseRegisterLoan") shouldBe 0
    instances(loanCore,"ElementwiseMemoryEngine") shouldBe 0
    instances(loanCore,"ElementwiseRegisterLoan") shouldBe 1
    instances(baseCore,"BlockScalarFloat") shouldBe 1
    instances(loanCore,"BlockScalarFloat") shouldBe 1
    instances(baseCore,"HeteroFP32Alu") shouldBe 16
    instances(loanCore,"HeteroFP32Alu") shouldBe 16
    instances(base,"HeteroFP32Alu") shouldBe instances(loan,"HeteroFP32Alu")
    memories(loan) shouldBe memories(base)
    val borrower=module(loan,"GdnRmsNormFixedBankOwner")
    for(name<-Seq("input","weights","output"))
      borrower should include ("reg "+name+" : UInt<512>[32]")
    borrower.linesIterator.count(x=>x.trim.startsWith("reg ")&&x.contains("UInt<512>[32]")) shouldBe 3
    instances(borrower,"HeteroFP32Alu") shouldBe 0
    instances(borrower,"BlockScalarFloat") shouldBe 0
    instances(borrower,"ElementwiseRegisterLoan") shouldBe 0
    println("H2048_BORROWER_STRUCTURE_PASS default_h1024=true bank_bytes=6144 extra_scalar=0 extra_elementwise=0 legacy_vout16_retained=true full_kernel_simulated=false ppa=false")
  }
}
