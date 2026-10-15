// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}
import java.nio.file.{Files,Paths}

/** Real Matrix arithmetic: the external testbench supplies operands and SRAM
  * ACKs only. The tap observes the SAME accepted Matrix return, never injects it.
  * This test wrapper adds no arithmetic and does not connect a Host owner. */
class QkNumericProbe extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(new QkProfileStart))
    val operand=Flipped(Decoupled(new Bundle {
      val tag=UInt(32.W);val epoch=UInt(32.W);val stripe=UInt(4.W);val step=UInt(3.W)
      val a=UInt(256.W);val b=UInt(4096.W)
    }))
    val write=Decoupled(new QkProfileWrite)
    val ack=Flipped(Decoupled(new QkProfileWriteAck))
    val done=Decoupled(new QkProfileFence)
    val release=Flipped(Decoupled(new QkProfileFence));val abort=Input(Bool())
    val tap=Valid(new Bundle {
      val data=Vec(16,UInt(8192.W));val context=UInt(3.W);val last=Bool();val error=Bool()
    })
    val slots=Output(UInt(5.W));val poisoned=Output(Bool())
    val returned=Output(UInt(8.W));val committed=Output(UInt(12.W))
    val wideSteps=Output(UInt(64.W));val sliceSteps=Output(UInt(64.W))
  })
  val profile=Module(new QkRectangularProfile(enabled=true))
  val matrix=Module(new MatrixPipelineProbe) // unchanged real service and 8 retained endpoints
  profile.io.oldOwnersIdle:=true.B;profile.io.abort:=io.abort
  profile.io.start<>io.start;profile.io.write<>io.write;profile.io.writeAck<>io.ack
  profile.io.done<>io.done;profile.io.release<>io.release
  profile.io.operand.valid:=io.operand.valid;io.operand.ready:=profile.io.operand.ready
  profile.io.operand.bits.tag:=io.operand.bits.tag;profile.io.operand.bits.epoch:=io.operand.bits.epoch
  profile.io.operand.bits.stripe:=io.operand.bits.stripe;profile.io.operand.bits.step:=io.operand.bits.step
  profile.io.operand.bits.a:=io.operand.bits.a.asTypeOf(Vec(16,UInt(16.W)))
  profile.io.operand.bits.b:=io.operand.bits.b.asTypeOf(Vec(256,UInt(16.W)))
  matrix.io.group<>profile.io.matrix.group;profile.io.matrix.done<>matrix.io.done
  matrix.io.abort:=profile.io.matrix.abort
  matrix.io.step.valid:=profile.io.matrix.step.valid;profile.io.matrix.step.ready:=matrix.io.step.ready
  matrix.io.step.bits.a:=profile.io.matrix.step.bits.a.asUInt;matrix.io.step.bits.b:=profile.io.matrix.step.bits.b.asUInt
  matrix.io.step.bits.context:=profile.io.matrix.step.bits.context
  matrix.io.step.bits.clear:=profile.io.matrix.step.bits.clear;matrix.io.step.bits.last:=profile.io.matrix.step.bits.last
  matrix.io.step.bits.finish:=profile.io.matrix.step.bits.finish;matrix.io.step.bits.emit:=profile.io.matrix.step.bits.emit
  profile.io.matrix.result.valid:=matrix.io.result.valid;matrix.io.result.ready:=profile.io.matrix.result.ready
  for(r<-0 until 16)profile.io.matrix.result.bits.value(r):=matrix.io.result.bits.data(r).asTypeOf(Vec(256,UInt(32.W)))
  profile.io.matrix.result.bits.context:=matrix.io.result.bits.context
  profile.io.matrix.result.bits.last:=matrix.io.result.bits.last;profile.io.matrix.result.bits.error:=matrix.io.result.bits.error
  io.tap.valid:=matrix.io.result.fire;io.tap.bits.data:=matrix.io.result.bits.data
  io.tap.bits.context:=matrix.io.result.bits.context;io.tap.bits.last:=matrix.io.result.bits.last;io.tap.bits.error:=matrix.io.result.bits.error
  io.slots:=profile.io.slotValid;io.poisoned:=profile.io.resetRequired||matrix.io.resetRequired
  io.returned:=profile.io.returnedSteps;io.committed:=profile.io.committedWords
  io.wideSteps:=matrix.io.wideSteps;io.sliceSteps:=matrix.io.acceptedSteps
  dontTouch(io)
}
class QkNumericCollection extends Module {
  val probe=Module(new QkNumericProbe);val port=IO(chiselTypeOf(probe.io));port<>probe.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitQkNumericProbe extends App {
  require(args.length==1,"absolute NEW output directory")
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve previous evidence")
  Files.createDirectories(out)
  Files.writeString(out.resolve("QkNumericProbe.sv"),ChiselStage.emitSystemVerilog(new QkNumericCollection,
    firtoolOpts=Array("-disable-all-randomization","-strip-debug-info")))
}
