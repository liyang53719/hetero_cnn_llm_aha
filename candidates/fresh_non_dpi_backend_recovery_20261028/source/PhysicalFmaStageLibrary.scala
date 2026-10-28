// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import chisel3._
import firrtl2.{SystemVerilogEmitter}
import firrtl2.options.TargetDirAnnotation
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.nio.charset.StandardCharsets

/** Library carrier only. It is not the Host, and is never a full-block test. */
class PhysicalFmaStageLibrary extends RawModule {
  val pre = Module(new HeteroBF16FmaPre)
  val preIo = IO(chiselTypeOf(pre.io)); preIo <> pre.io; dontTouch(preIo)
  val mul = Module(new HeteroBF16FmaMul)
  val mulIo = IO(chiselTypeOf(mul.io)); mulIo <> mul.io; dontTouch(mulIo)
  val post = Module(new HeteroBF16FmaPost)
  val postIo = IO(chiselTypeOf(post.io)); postIo <> post.io; dontTouch(postIo)
  val round = Module(new HeteroBF16FmaRound)
  val roundIo = IO(chiselTypeOf(round.io)); roundIo <> round.io; dontTouch(roundIo)
}
object EmitPhysicalFmaStageLibrary {
  def main(args:Array[String]):Unit = {
    require(args.length == 1, "fresh library output directory only")
    val dir=Paths.get(args(0)); require(!Files.exists(dir),"preserve existing outputs")
    Files.createDirectories(dir)
    val (high,_) = Compiler.elaborate(()=>new PhysicalFmaStageLibrary,
      Seq(TargetDirAnnotation(dir.toString)),Seq.empty)
    val low=Compiler.toLowFirrtl(high)
    val expected=Set("HeteroBF16FmaPre","HeteroBF16FmaMul","HeteroBF16FmaPost","HeteroBF16FmaRound")
    require(expected.subsetOf(low.circuit.modules.map(_.name).toSet),"all original FMA stages present")
    require(!low.circuit.modules.exists(_.isInstanceOf[firrtl2.ir.ExtModule]),"no external arithmetic substitute")
    val writer=new java.io.StringWriter
    new SystemVerilogEmitter().emit(low,writer)
    Files.write(dir.resolve("PhysicalFmaStageLibrary.sv"),writer.toString.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW)
    Files.write(dir.resolve("SCOPE.txt"),"ORIGINAL_FOUR_HARDFLOAT_STAGE_LIBRARY_ONLY; NOT_HOST; NO_NUMERICAL_PASS\n".getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW)
  }
}
