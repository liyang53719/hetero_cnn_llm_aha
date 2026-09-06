// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}

/** Retained upstream project RTL, not an embedded replacement implementation.
  * File identity is pinned by the execution script before compilation. */
class RetainedMatrixEndpoint extends BlackBox {
  override def desiredName="qwen2_matrix_command_endpoint"
  val io=IO(new Bundle {
    val clk_i=Input(Clock());val rst_ni=Input(Bool());val cmd_valid_i=Input(Bool());val cmd_ready_o=Output(Bool());val cmd_i=Input(UInt(128.W))
    val step_valid_i=Input(Bool());val step_ready_o=Output(Bool());val step_context_i=Input(UInt(3.W));val step_clear_i=Input(Bool());val step_last_i=Input(Bool());val command_last_tile_i=Input(Bool())
    val step_a_i=Input(UInt(256.W));val step_b_i=Input(UInt(512.W));val out_valid_o=Output(Bool());val out_ready_i=Input(Bool());val out_context_o=Output(UInt(3.W));val out_last_o=Output(Bool());val out_acc_o=Output(UInt(16384.W))
    val completion_valid_o=Output(Bool());val completion_ready_i=Input(Bool());val completion_data_o=Output(UInt(56.W));val protocol_error_o=Output(Bool())
  })
}
class Matrix16Request extends Bundle {
  val a=Vec(16,UInt(32.W));val b=Vec(16,UInt(32.W));val clear=Bool();val last=Bool();val diagonal=Bool()
}
class Matrix16Result extends Bundle {val value=Vec(16,UInt(32.W));val error=Bool()}
/** Correctness-first binding to the existing 16x32 Revision8B endpoint.
  * Dense/PV use row0, columns0..15. QK selects diagonal i,i. Other products are
  * discarded, not counted as useful MACs. This deliberately does NOT claim
  * 512-lane utilization or replace the canonical array's performance schedule.
  * The array owns all partial sums, clear/last and command completion. */
class RetainedMatrix16Adapter extends Module {
  val io=IO(new Bundle {val request=Flipped(Decoupled(new Matrix16Request));val result=Decoupled(new Matrix16Result)})
  val idle::command::issue::output::completion::reply::locked::Nil=Enum(7)
  val state=RegInit(idle);val req=Reg(new Matrix16Request);val result=Reg(new Matrix16Result)
  val active=RegInit(false.B);val poisoned=RegInit(false.B);val event=RegInit(0.U(16.W))
  val ep=Module(new RetainedMatrixEndpoint);val e=ep.io
  e.clk_i:=clock;e.rst_ni:= !reset.asBool
  e.cmd_valid_i:=state===command
  // Explicit command construction: opcode bits7:0, owner10:8, event55:40.
  e.cmd_i:=(event.pad(128)<<40)|"h220".U(128.W)
  e.step_valid_i:=state===issue;e.step_context_i:=0.U;e.step_clear_i:=req.clear;e.step_last_i:=req.last;e.command_last_tile_i:=true.B
  e.step_a_i:=VecInit((0 until 16).map(i=>Mux(req.diagonal|| (i==0).B,TensorMath.bf16Rne(req.a(i)),0.U(16.W)))).asUInt
  e.step_b_i:=Cat(0.U(256.W),VecInit(req.b.map(TensorMath.bf16Rne)).asUInt)
  e.out_ready_i:=state===output;e.completion_ready_i:=state===completion
  io.request.ready:=state===idle;io.result.valid:=state===reply;io.result.bits:=result
  def bad():Unit={result.error:=true.B;poisoned:=true.B;state:=reply}
  switch(state){
    is(idle){when(io.request.fire){req:=io.request.bits;result.error:=false.B
      when(io.request.bits.clear===active){bad()}.otherwise{
        when(io.request.bits.clear){event:=event+1.U;state:=command}.otherwise{state:=issue}
      }
    }}
    is(command){when(e.cmd_ready_o){active:=true.B;state:=issue}}
    is(issue){when(e.step_ready_o){state:=output}}
    is(output){when(e.out_valid_o){
      for(i<-0 until 16)result.value(i):=Mux(req.diagonal,e.out_acc_o((i*32+i)*32+31,(i*32+i)*32),e.out_acc_o(i*32+31,i*32))
      when(e.out_context_o=/=0.U||e.out_last_o=/=req.last){bad()}
        .elsewhen(req.last){state:=completion}.otherwise{state:=reply}
    }}
    is(completion){when(e.completion_valid_o){active:=false.B
      when(e.completion_data_o(55,40)=/=event||e.completion_data_o(39,32)=/=0.U){bad()}.otherwise{state:=reply}
    }}
    is(reply){when(io.result.fire){state:=Mux(poisoned,locked,idle)}}
    is(locked){}
  }
  when(e.protocol_error_o&&state=/=idle&&state=/=reply&&state=/=locked){bad()}
}
/** One Chisel elaboration avoids duplicate HardFloat helper names. The four
  * ABI leaf roots are emitted unmodified for the retained array to instantiate. */
class RetainedBlockCollection(s:QwenBlockShape,axi:Boolean) extends Module {
  if(axi){val block=Module(new Qwen2BlockAxiTop(s));val port=IO(chiselTypeOf(block.io));port<>block.io;dontTouch(port)}
  else{val block=Module(new Qwen2ContinuousBlock(s));val port=IO(chiselTypeOf(block.io));port<>block.io;dontTouch(port)}
  val pre=Module(new HeteroBF16FmaPre);val prePort=IO(chiselTypeOf(pre.io));prePort<>pre.io;dontTouch(prePort)
  val mul=Module(new HeteroBF16FmaMul);val mulPort=IO(chiselTypeOf(mul.io));mulPort<>mul.io;dontTouch(mulPort)
  val post=Module(new HeteroBF16FmaPost);val postPort=IO(chiselTypeOf(post.io));postPort<>post.io;dontTouch(postPort)
  val round=Module(new HeteroBF16FmaRound);val roundPort=IO(chiselTypeOf(round.io));roundPort<>round.io;dontTouch(roundPort)
}
