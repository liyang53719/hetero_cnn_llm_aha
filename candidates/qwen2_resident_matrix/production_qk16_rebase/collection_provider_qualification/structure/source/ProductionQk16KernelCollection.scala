package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}
/** Emission namespace only. The qualification top remains ProductionQk16KernelBench.
  * The four sibling instances retain the real external lane-provider definitions;
  * they are not additional arithmetic in the selected Bench hierarchy.
  */
class ProductionQk16KernelCollection extends Module {
  val top=Module(new ProductionQk16KernelBench(selected=true))
  val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitProductionQk16KernelCollection extends App {
  require(args.length==1,"fresh output directory required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  println("KERNEL_COLLECTION_CHIRRTL_BEGIN selected=1 actual_job=none")
  val ir=ChiselStage.emitCHIRRTL(new ProductionQk16KernelCollection)
  val bytes=ir.getBytes(java.nio.charset.StandardCharsets.UTF_8)
  val modules="(?m)^  module ".r.findAllMatchIn(ir).length
  val ext="(?m)^  extmodule ".r.findAllMatchIn(ir).length
  println(s"KERNEL_COLLECTION_CHIRRTL_SIZE bytes=${bytes.length} modules=$modules extmodules=$ext")
  require(bytes.length<=48*1024*1024,"48MiB CHIRRTL cap")
  Files.write(out.resolve("ProductionQk16KernelCollection.fir"),bytes)
  println("KERNEL_COLLECTION_CHIRRTL_WRITTEN")
}
