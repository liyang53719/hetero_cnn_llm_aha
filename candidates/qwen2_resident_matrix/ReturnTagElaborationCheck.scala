// SPDX-License-Identifier: Apache-2.0
// Candidate-only frontend check. Never invokes firtool or generates RTL.
package heteronpu.continuous

import chisel3._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}

class ReturnTagBundleShapeCheck(width:Int) extends Module {
  val io=IO(Input(new Bundle {
    val step=new MatrixStreamStep(width)
    val result=new MatrixStreamResult(width)
    val port=new MatrixStreamPort(width)
  }))
  val oldStep=Set("a","b","context","clear","last","finish","emit")
  val oldResult=Set("value","context","last","error")
  val extra=if(width==0)Set.empty[String]else Set("returnTag")
  require(io.step.elements.keySet==oldStep++extra)
  require(io.result.elements.keySet==oldResult++extra)
  require(io.port.elements.keySet==Set("group","step","result","done","abort"))
  require(io.step.getWidth==4359+width)
  require(io.result.getWidth==131077+width)
  require(io.step.returnTag.isDefined==(width>0))
  require(io.result.returnTag.isDefined==(width>0))
  require(io.port.step.bits.returnTag.isDefined==(width>0))
  require(io.port.result.bits.returnTag.isDefined==(width>0))
  io.step.returnTag.foreach(tag=>require(tag.getWidth==width))
  io.result.returnTag.foreach(tag=>require(tag.getWidth==width))
}

object ReturnTagElaborationCheck extends App {
  require(args.length==1,"provide a new output directory for frontend-only artifacts")
  val output=Paths.get(args(0))
  require(output.isAbsolute && !Files.exists(output))
  Files.createDirectories(output)
  for(width<-Seq(0,1,16,32)){
    Files.writeString(output.resolve(s"bundle_$width.fir"),ChiselStage.emitCHIRRTL(new ReturnTagBundleShapeCheck(width)))
    Files.writeString(output.resolve(s"fifo_$width.fir"),ChiselStage.emitCHIRRTL(new MatrixResultFifo(width)))
    Files.writeString(output.resolve(s"service_$width.fir"),ChiselStage.emitCHIRRTL(new MatrixPipelineService(width)))
  }
  // Exercise existing constructor syntax as well as explicit width zero.
  Files.writeString(output.resolve("fifo_default.fir"),ChiselStage.emitCHIRRTL(new MatrixResultFifo))
  Files.writeString(output.resolve("service_default.fir"),ChiselStage.emitCHIRRTL(new MatrixPipelineService))
  for(width<-Seq(-1,33)){
    var rejected=false
    try { ChiselStage.emitCHIRRTL(new ReturnTagBundleShapeCheck(width)) }
    catch { case e:IllegalArgumentException if e.getMessage.contains("returnTagBits must be in 0..32") => rejected=true }
    require(rejected,s"invalid returnTagBits=$width was not rejected")
  }
  println("PASS: candidate Chisel frontend elaboration and bundle shapes; no RTL simulation or arithmetic executed")
}
