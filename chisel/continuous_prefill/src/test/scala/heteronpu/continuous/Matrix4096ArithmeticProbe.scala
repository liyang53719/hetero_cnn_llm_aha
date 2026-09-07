// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}

/** Test-only packed interface to the SAME eight real retained arithmetic slices.
  * No arithmetic is implemented here and no production HostBlockTop is changed.
  * The ordinary simulator supplies operands, never result data or leaf replies.
  */
class Matrix4096ArithmeticProbe extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new Bundle {
      val a=UInt(256.W); val b=UInt(4096.W); val mask=UInt(8.W)
      val clear=Bool(); val last=Bool(); val opcode=UInt(8.W)
    }))
    val result=Decoupled(new Bundle {val data=Vec(16,UInt(8192.W));val error=Bool()})
    val acceptedSteps=Output(UInt(64.W));val resetRequired=Output(Bool())
  })
  val matrix=Module(new ScalableMatrixTileAdapter(256))
  matrix.io.scanEnable:=false.B
  matrix.io.request.valid:=io.request.valid;io.request.ready:=matrix.io.request.ready
  matrix.io.request.bits.a:=io.request.bits.a.asTypeOf(matrix.io.request.bits.a)
  matrix.io.request.bits.b:=io.request.bits.b.asTypeOf(matrix.io.request.bits.b)
  matrix.io.request.bits.sliceMask:=io.request.bits.mask
  matrix.io.request.bits.clear:=io.request.bits.clear;matrix.io.request.bits.last:=io.request.bits.last
  matrix.io.request.bits.opcode:=io.request.bits.opcode
  io.result.valid:=matrix.io.result.valid;matrix.io.result.ready:=io.result.ready
  for(row<-0 until 16){io.result.bits.data(row):=matrix.io.result.bits.value(row).asUInt}
  io.result.bits.error:=matrix.io.result.bits.error
  io.acceptedSteps:=matrix.io.acceptedSteps;io.resetRequired:=matrix.io.resetRequired
}

/** Emit the retained RTL's original HardFloat ABI leaves in the same elaboration.
  * They remain ordinary synthesizable Chisel, not DPI/reference callbacks.
  */
class Matrix4096ProbeCollection extends Module {
  val probe=Module(new Matrix4096ArithmeticProbe)
  val port=IO(chiselTypeOf(probe.io));port<>probe.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val prePort=IO(chiselTypeOf(pre.io));prePort<>pre.io;dontTouch(prePort)
  val mul=Module(new HeteroBF16FmaMul);val mulPort=IO(chiselTypeOf(mul.io));mulPort<>mul.io;dontTouch(mulPort)
  val post=Module(new HeteroBF16FmaPost);val postPort=IO(chiselTypeOf(post.io));postPort<>post.io;dontTouch(postPort)
  val round=Module(new HeteroBF16FmaRound);val roundPort=IO(chiselTypeOf(round.io));roundPort<>round.io;dontTouch(roundPort)
}
object EmitMatrix4096ArithmeticProbe extends App {
  require(args.length==1,"absolute NEW output directory")
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve existing generated evidence")
  Files.createDirectories(out)
  val sv=ChiselStage.emitSystemVerilog(new Matrix4096ProbeCollection, firtoolOpts=Array("-disable-all-randomization","-strip-debug-info"))
  Files.writeString(out.resolve("Matrix4096ArithmeticProbe.sv"),sv)
}
