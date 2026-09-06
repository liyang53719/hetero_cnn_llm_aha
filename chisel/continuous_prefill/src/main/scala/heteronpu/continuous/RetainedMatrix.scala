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
  val io=IO(new Bundle {val request=Flipped(Decoupled(new Matrix16Request));val result=Decoupled(new Matrix16Result);val acceptedSteps=Output(UInt(64.W))})
  val idle::command::issue::output::completion::reply::locked::Nil=Enum(7)
  val state=RegInit(idle);val req=Reg(new Matrix16Request);val result=Reg(new Matrix16Result)
  val issued=RegInit(0.U(64.W));io.acceptedSteps:=issued
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
  when(e.step_valid_i && e.step_ready_o){issued:=issued+1.U}
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
  if(axi){val block=Module(new Qwen2AxiBlockTop(s));val port=IO(chiselTypeOf(block.io));port<>block.io;dontTouch(port)}
  else{val block=Module(new Qwen2ContinuousBlock(s));val port=IO(chiselTypeOf(block.io));port<>block.io;dontTouch(port)}
  val pre=Module(new HeteroBF16FmaPre);val prePort=IO(chiselTypeOf(pre.io));prePort<>pre.io;dontTouch(prePort)
  val mul=Module(new HeteroBF16FmaMul);val mulPort=IO(chiselTypeOf(mul.io));mulPort<>mul.io;dontTouch(mulPort)
  val post=Module(new HeteroBF16FmaPost);val postPort=IO(chiselTypeOf(post.io));postPort<>post.io;dontTouch(postPort)
  val round=Module(new HeteroBF16FmaRound);val roundPort=IO(chiselTypeOf(round.io));roundPort<>round.io;dontTouch(roundPort)
}

/** One accepted outer-product step of the retained 16x32 array.
  * BF16 encoding is explicit. The producer owns clear/last and must not change
  * the opcode during a dot product. All 512 accumulator values are returned.
  */
class MatrixTileStep extends Bundle {
  val a=Vec(16,UInt(16.W)); val b=Vec(32,UInt(16.W))
  val clear=Bool(); val last=Bool(); val opcode=UInt(8.W)
}
class MatrixTileResult extends Bundle {
  val value=Vec(16,Vec(32,UInt(32.W))); val error=Bool()
}
/** Shared correctness-first adapter. A single retained endpoint serves Dense,
  * QK and PV. This is NOT a replacement FMA implementation. Commands use the
  * existing Command128 opcode/owner/event fields; descriptor lowering remains
  * upstream. Only one step is outstanding; performance interleaving is separate.
  */
/** Pinned tech_cells_generic latch-based ICG. Never gate a clock with a raw
  * combinational AND. Scan integration and technology ICG mapping are separate
  * physical gates. Enabling only an active endpoint preserves its accumulator
  * while the block executes memory/SFU work; no numerical lane is substituted.
  */
class RetainedMatrixClockGate extends BlackBox {
  override def desiredName="tc_clk_gating"
  val io=IO(new Bundle {val clk_i=Input(Clock());val en_i=Input(Bool());val test_en_i=Input(Bool());val clk_o=Output(Clock())})
}
class RetainedMatrixTileAdapter(gateClock:Boolean=true) extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new MatrixTileStep)); val scanEnable=Input(Bool())
    val result=Decoupled(new MatrixTileResult)
    val acceptedSteps=Output(UInt(64.W)); val acceptedCommands=Output(UInt(64.W))
    val completedCommands=Output(UInt(64.W)); val resetRequired=Output(Bool())
  })
  val idle::command::issue::output::completion::reply::locked::Nil=Enum(7)
  val state=RegInit(idle); val req=Reg(new MatrixTileStep)
  val result=Reg(new MatrixTileResult); val active=RegInit(false.B)
  val poison=RegInit(false.B); val event=RegInit(0.U(16.W)); val opcode=Reg(UInt(8.W))
  val steps=RegInit(0.U(64.W)); val commands=RegInit(0.U(64.W)); val completions=RegInit(0.U(64.W))
  io.acceptedSteps:=steps;io.acceptedCommands:=commands;io.completedCommands:=completions;io.resetRequired:=poison
  val ep=Module(new RetainedMatrixEndpoint); val e=ep.io
  if(gateClock){
    val gate=Module(new RetainedMatrixClockGate)
    gate.io.clk_i:=clock;gate.io.test_en_i:=io.scanEnable
    gate.io.en_i:=state===command||state===issue||state===output||state===completion
    e.clk_i:=gate.io.clk_o
  }else{e.clk_i:=clock}
  e.rst_ni:= !reset.asBool
  // Preserve the published envelope, without pretending roots were fetched.
  // No host Command128 frontend is claimed by this internal array adapter.
  e.cmd_i:=Cat(0.U(72.W),event,0.U(16.W),0.U(13.W),2.U(3.W),opcode)
  e.cmd_valid_i:=state===command
  e.step_valid_i:=state===issue;e.step_context_i:=0.U
  e.step_clear_i:=req.clear;e.step_last_i:=req.last;e.command_last_tile_i:=true.B
  e.step_a_i:=req.a.asUInt;e.step_b_i:=req.b.asUInt
  e.out_ready_i:=state===output;e.completion_ready_i:=state===completion
  io.request.ready:=state===idle && !poison
  io.result.valid:=state===reply;io.result.bits:=result
  def fail():Unit={result.error:=true.B;poison:=true.B;state:=reply}
  when(io.request.fire){
    req:=io.request.bits;result.error:=false.B
    val op=io.request.bits.opcode
    val validOp=op===0x20.U||op===0x21.U||op===0x23.U||op===0x24.U
    when(!validOp || io.request.bits.clear===active || (active&&op=/=opcode)){fail()}
    .otherwise{
      when(io.request.bits.clear){event:=event+1.U;opcode:=op;state:=command}
      .otherwise{state:=issue}
    }
  }
  when(state===command&&e.cmd_ready_o){active:=true.B;commands:=commands+1.U;state:=issue}
  when(state===issue&&e.step_ready_o){steps:=steps+1.U;state:=output}
  when(state===output&&e.out_valid_o){
    result.value:=e.out_acc_o.asTypeOf(result.value)
    when(e.out_context_o=/=0.U||e.out_last_o=/=req.last){fail()}
    .elsewhen(req.last){state:=completion}.otherwise{state:=reply}
  }
  when(state===completion&&e.completion_valid_o){
    active:=false.B;completions:=completions+1.U
    when(e.completion_data_o(55,40)=/=event||e.completion_data_o(39,32)=/=0.U||e.completion_data_o(31,29)=/=2.U){fail()}
    .otherwise{state:=reply}
  }
  when(state===reply&&io.result.fire){state:=Mux(poison,locked,idle)}
  when(e.protocol_error_o&&state=/=idle&&state=/=reply&&state=/=locked){fail()}
}
