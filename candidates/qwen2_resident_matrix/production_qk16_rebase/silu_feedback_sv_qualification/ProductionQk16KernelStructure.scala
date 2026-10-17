package heteronpu.continuous
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
/** Selected=true only, original full production resources, no job launch. */
object ProductionQk16KernelStructure extends App {
  require(args.length==1,"fresh output required")
  val out=Paths.get(args(0));require(!Files.exists(out));Files.createDirectories(out)
  println("KERNEL_CHIRRTL_BEGIN selected=1 actual_job=none")
  val ir=ChiselStage.emitCHIRRTL(new ProductionQk16KernelBench(selected=true))
  val bytes=ir.getBytes(java.nio.charset.StandardCharsets.UTF_8)
  val modules="(?m)^  module ".r.findAllMatchIn(ir).length
  val ext="(?m)^  extmodule ".r.findAllMatchIn(ir).length
  println(s"KERNEL_CHIRRTL_SIZE bytes=${bytes.length} modules=$modules extmodules=$ext")
  require(bytes.length<=48*1024*1024,"48MiB CHIRRTL cap")
  Files.write(out.resolve("ProductionQk16KernelBench.fir"),bytes)
  println("KERNEL_CHIRRTL_WRITTEN")
}
