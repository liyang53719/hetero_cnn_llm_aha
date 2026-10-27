// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import firrtl2.ir._
import firrtl2.annotations.UnrecognizedAnnotation
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.{MatrixFifoSamplingProbe,MatrixResultFifoMemoryLowering}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest

/** One unchanged original full-capacity probe, the SAME strict storage
  * transform, and official declaration/form check only. No low/PrepareAst,
  * Treadle construction, clock, numerical input or equivalence assertion. */
object MatrixFifoHighFormDiagnostic {
  private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def fifo(c:Circuit):Module={val m=c.modules.collect{case x:Module if x.name=="MatrixResultFifo"=>x};require(m.size==1);m.head}
  def main(args:Array[String]):Unit={
    require(args.isEmpty,"fixed no-design-input official high-form diagnostic")
    val dir=Paths.get("fifo-formcheck");Files.createDirectories(dir)
    def write(name:String,b:Array[Byte]):Unit=Files.write(dir.resolve(name),b,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
    println("FIFO_FORM elaborate.begin")
    val(h,_)=Compiler.elaborate(()=>new MatrixFifoSamplingProbe,Seq(TargetDirAnnotation(dir.toString)),Seq.empty)
    println("FIFO_FORM elaborate.end")
    require(!h.annotations.exists(x=>x.isInstanceOf[UnsupportedAnnotation] || x.isInstanceOf[UnrecognizedAnnotation]),"uninterpreted annotation")
    require(h.annotations.forall(_.getTargets.isEmpty),"no silently discarded targeted annotation")
    require(!h.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),"no second circuit annotation")
    val original=fifo(h.circuit);val originalBytes=original.serialize.getBytes(UTF_8)
    write("ORIGINAL_MODULE.serialize.fir",originalBytes)
    val changed=MatrixResultFifoMemoryLowering(h.circuit)
    val transformed=fifo(changed);val transformedBytes=transformed.serialize.getBytes(UTF_8)
    write("TRANSFORMED_MODULE.serialize.fir",transformedBytes)
    require(original.ports==transformed.ports,"complete original FIFO ABI unchanged")
    val identity=s"originalBytes=${originalBytes.length}\noriginalSha256=${sha(originalBytes)}\ntransformedBytes=${transformedBytes.length}\ntransformedSha256=${sha(transformedBytes)}\nexpectedOriginal=${MatrixResultFifoMemoryLowering.ExpectedOriginalSha256}\n"
    write("IDENTITY.txt",identity.getBytes(UTF_8))
    println("FIFO_FORM exact_transform.end")
    // Fixed official Pass.run; never trim/parse/repair serialized IR, bypass
    // declaration checking, or continue to expensive lowering after failure.
    firrtl2.passes.CheckHighForm.run(h.circuit)
    println("FIFO_FORM original.CheckHighForm.end")
    firrtl2.passes.CheckHighForm.run(changed)
    println("FIFO_FORM transformed.CheckHighForm.end")
    write("FORMCHECK_PASSED.txt","officialCheckHighFormOriginal=true\nofficialCheckHighFormTransformed=true\nlow=false\nprepare=false\nTreadle=false\nequivalence=false\n".getBytes(UTF_8))
    println("FIFO_FORM PASS_HIGHFORM_ONLY low=false prepare=false Treadle=false equivalence=false")
  }
}
