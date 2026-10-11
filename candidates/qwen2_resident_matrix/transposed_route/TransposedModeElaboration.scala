// SPDX-License-Identifier: Apache-2.0
// Full existing service, exact retained BlackBox ABI, frontend only.
package heteronpu.continuous
import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class TransposedBundleShapeCheck(width:Int,enabled:Boolean) extends Module {
  val io=IO(Input(new MatrixStreamPort(width,enabled)))
  require(io.group.bits.elements.keySet==Set("opcode","sliceMask","tag")++
    (if(enabled)Set("transposedDense")else Set.empty[String]))
  require(io.group.bits.getWidth==48+(if(enabled)1 else 0))
  require(io.group.bits.transposedDense.isDefined==enabled)
  require(io.step.bits.getWidth==4359+width)
  require(io.result.bits.getWidth==131077+width)
  require(io.step.bits.a.length==16 && io.step.bits.b.length==256)
  require(io.step.bits.a.head.getWidth==16 && io.step.bits.b.head.getWidth==16)
  require(io.result.bits.value.length==16 && io.result.bits.value.head.length==256)
  require(io.result.bits.value.head.head.getWidth==32)
}

/** Exercise an ordinary producer fixing either group mode, including tags. */
class FixedModeMatrixPipeline(width:Int,transposed:Boolean) extends Module {
  val io=IO(new Bundle {
    val port=Flipped(new MatrixStreamPort(width))
    val resetRequired=Output(Bool())
  })
  val service=Module(new MatrixPipelineService(width,enableTransposedDense=true))
  service.io.port.group.valid:=io.port.group.valid
  io.port.group.ready:=service.io.port.group.ready
  service.io.port.group.bits.opcode:=io.port.group.bits.opcode
  service.io.port.group.bits.sliceMask:=io.port.group.bits.sliceMask
  service.io.port.group.bits.tag:=io.port.group.bits.tag
  service.io.port.group.bits.transposedDense.get:=transposed.B
  service.io.port.step<>io.port.step
  io.port.result<>service.io.port.result
  io.port.done<>service.io.port.done
  service.io.port.abort:=io.port.abort
  io.resetRequired:=service.io.resetRequired
}

object TransposedModeElaboration extends App {
  require(args.length==1)
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out));Files.createDirectories(out)
  def emit(name:String,module: => RawModule):Unit=
    Files.writeString(out.resolve(name+".fir"),ChiselStage.emitCHIRRTL(module))
  emit("fifo_default",new MatrixResultFifo)
  emit("service_default",new MatrixPipelineService)
  for(width<-Seq(0,1,16,32);enabled<-Seq(false,true)){
    val name=s"${width}_${if(enabled)"enabled"else"disabled"}"
    emit("bundle_"+name,new TransposedBundleShapeCheck(width,enabled))
    emit("service_"+name,new MatrixPipelineService(width,enabled))
  }
  emit("fixed_normal_16",new FixedModeMatrixPipeline(16,false))
  emit("fixed_transposed_16",new FixedModeMatrixPipeline(16,true))
  println("PASS: full service and fixed-mode clients emitted as CHIRRTL; no RTL or arithmetic executed")
}
