// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}
/** Packed test ports only; every multiply-add executes in retained RTL. */
class MatrixPipelineProbe extends Module {
  val io=IO(new Bundle {
    val group=Flipped(Decoupled(new MatrixStreamGroup))
    val step=Flipped(Decoupled(new Bundle {val a=UInt(256.W);val b=UInt(4096.W);val context=UInt(3.W);val clear=Bool();val last=Bool();val finish=Bool();val emit=Bool()}))
    val result=Decoupled(new Bundle {val data=Vec(16,UInt(8192.W));val context=UInt(3.W);val last=Bool();val error=Bool()})
    val done=Decoupled(new MatrixStreamDone);val abort=Input(Bool())
    val acceptedSteps=Output(UInt(64.W));val wideSteps=Output(UInt(64.W));val resetRequired=Output(Bool())
  })
  val dut=Module(new MatrixPipelineService)
  dut.io.port.group<>io.group;dut.io.port.done<>io.done;dut.io.port.abort:=io.abort
  dut.io.port.step.valid:=io.step.valid;io.step.ready:=dut.io.port.step.ready
  dut.io.port.step.bits.a:=io.step.bits.a.asTypeOf(Vec(16,UInt(16.W)))
  dut.io.port.step.bits.b:=io.step.bits.b.asTypeOf(Vec(256,UInt(16.W)))
  dut.io.port.step.bits.context:=io.step.bits.context;dut.io.port.step.bits.clear:=io.step.bits.clear
  dut.io.port.step.bits.last:=io.step.bits.last;dut.io.port.step.bits.finish:=io.step.bits.finish;dut.io.port.step.bits.emit:=io.step.bits.emit
  io.result.valid:=dut.io.port.result.valid;dut.io.port.result.ready:=io.result.ready
  for(i<-0 until 16){io.result.bits.data(i):=dut.io.port.result.bits.value(i).asUInt};io.result.bits.context:=dut.io.port.result.bits.context
  io.result.bits.last:=dut.io.port.result.bits.last;io.result.bits.error:=dut.io.port.result.bits.error
  io.acceptedSteps:=dut.io.acceptedSteps;io.wideSteps:=dut.io.wideSteps;io.resetRequired:=dut.io.resetRequired
  dontTouch(io)
}
class MatrixPipelineCollection extends Module {
  val top=Module(new MatrixPipelineProbe);val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitMatrixPipelineProbe extends App {
  val p=Paths.get(args(0));require(p.isAbsolute && !Files.exists(p));Files.createDirectories(p)
  Files.writeString(p.resolve("MatrixPipelineProbe.sv"),ChiselStage.emitSystemVerilog(new MatrixPipelineCollection,firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
