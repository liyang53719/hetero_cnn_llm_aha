// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** A single logical Matrix owner. Each selected 16x32 arithmetic slice consumes
  * the SAME increasing-K step; no split-K or independent Host command stream.
  * Masked slices are clock-idle and do not count as executed MACs. */
class WideMatrixStep(val columns:Int) extends Bundle {
  require(columns>=32 && columns%32==0)
  val a=Vec(16,UInt(16.W));val b=Vec(columns,UInt(16.W))
  val clear=Bool();val last=Bool();val opcode=UInt(8.W)
  val sliceMask=UInt((columns/32).W)
}
class WideMatrixResult(val columns:Int) extends Bundle {
  val value=Vec(16,Vec(columns,UInt(32.W)));val error=Bool()
}

/** Register-based fanout/join. Each slice sees one handshake and can return in
  * any order. Errors are collected only after every selected reply is drained.
  * Results and request operands remain stable under independent backpressure.
  * Slice interfaces are exposed here solely to permit focused protocol tests;
  * ScalableMatrixTileAdapter binds ALL of them to the real retained arithmetic. */
class MatrixSliceJoin(val columns:Int=256) extends Module {
  require(columns>=32 && columns%32==0 && columns<=256)
  val slices=columns/32
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new WideMatrixStep(columns)))
    val result=Decoupled(new WideMatrixResult(columns))
    val sliceRequest=Vec(slices,Decoupled(new MatrixTileStep))
    val sliceResult=Flipped(Vec(slices,Decoupled(new MatrixTileResult)))
    val resetRequired=Output(Bool())
  })
  val active=RegInit(false.B);val complete=RegInit(false.B);val poison=RegInit(false.B)
  val req=Reg(new WideMatrixStep(columns));val result=Reg(new WideMatrixResult(columns))
  val sent=RegInit(0.U(slices.W));val received=RegInit(0.U(slices.W))
  val dotActive=RegInit(false.B);val dotMask=Reg(UInt(slices.W));val dotOpcode=Reg(UInt(8.W))
  io.request.ready:= !active && !poison
  io.result.valid:=active && complete;io.result.bits:=result;io.resetRequired:=poison
  val sentNow=Wire(Vec(slices,Bool()));val gotNow=Wire(Vec(slices,Bool()))
  val errorNow=Wire(Vec(slices,Bool()))
  for(i<-0 until slices){
    io.sliceRequest(i).valid:=active && !complete && req.sliceMask(i) && !sent(i)
    io.sliceRequest(i).bits.a:=req.a
    io.sliceRequest(i).bits.b:=VecInit((0 until 32).map(j=>req.b(i*32+j)))
    io.sliceRequest(i).bits.clear:=req.clear;io.sliceRequest(i).bits.last:=req.last
    io.sliceRequest(i).bits.opcode:=req.opcode
    io.sliceResult(i).ready:=active && !complete && sent(i) && !received(i)
    sentNow(i):=io.sliceRequest(i).fire;gotNow(i):=io.sliceResult(i).fire
    errorNow(i):=gotNow(i) && io.sliceResult(i).bits.error
    when(gotNow(i)){
      for(row<-0 until 16;col<-0 until 32){result.value(row)(32*i+col):=io.sliceResult(i).bits.value(row)(col)}
    }
  }
  when(active && !complete){
    sent:=sent|sentNow.asUInt;received:=received|gotNow.asUInt
    when(errorNow.asUInt.orR){result.error:=true.B;poison:=true.B}
    when((received|gotNow.asUInt)===req.sliceMask){complete:=true.B}
  }
  when(io.request.fire){
    val x=io.request.bits
    req:=x;active:=true.B;complete:=false.B;sent:=0.U;received:=0.U
    result.error:=false.B;result.value:=0.U.asTypeOf(result.value)
    val validOp=x.opcode===0x20.U||x.opcode===0x21.U||x.opcode===0x23.U||x.opcode===0x24.U
    when(!x.sliceMask.orR|| !validOp||x.clear===dotActive||
         (dotActive&&(x.sliceMask=/=dotMask||x.opcode=/=dotOpcode))){
      complete:=true.B;poison:=true.B;result.error:=true.B
    }.otherwise{
      dotActive:= !x.last
      when(x.clear){dotMask:=x.sliceMask;dotOpcode:=x.opcode}
    }
  }
  when(io.result.fire){active:=false.B;complete:=false.B}
}

/** Exactly one host-facing Matrix engine, with 1 or 8 physical 512-MAC slices.
  * The 32-column compatibility path has no extra join latency; 256 columns use
  * a registered shared fanout/join. The original arithmetic RTL is unchanged.
  * acceptedSteps counts ACTUAL 512-MAC slice issues, including padded lanes,
  * not peak capacity or accepted wide requests. The block converts it to MACs. */
class ScalableMatrixTileAdapter(val columns:Int=256) extends Module {
  require(columns==32||columns==256)
  val slices=columns/32
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new WideMatrixStep(columns)))
    val result=Decoupled(new WideMatrixResult(columns));val scanEnable=Input(Bool())
    val acceptedSteps=Output(UInt(64.W));val resetRequired=Output(Bool())
  })
  if(columns==32){
    val leaf=Module(new RetainedMatrixTileAdapter)
    leaf.io.scanEnable:=io.scanEnable
    leaf.io.request.valid:=io.request.valid;io.request.ready:=leaf.io.request.ready
    leaf.io.request.bits.a:=io.request.bits.a;leaf.io.request.bits.b:=io.request.bits.b
    leaf.io.request.bits.clear:=io.request.bits.clear;leaf.io.request.bits.last:=io.request.bits.last
    leaf.io.request.bits.opcode:=io.request.bits.opcode
    io.result.valid:=leaf.io.result.valid;leaf.io.result.ready:=io.result.ready
    io.result.bits.value:=leaf.io.result.bits.value;io.result.bits.error:=leaf.io.result.bits.error
    io.acceptedSteps:=leaf.io.acceptedSteps;io.resetRequired:=leaf.io.resetRequired
    when(io.request.fire){assert(io.request.bits.sliceMask===1.U,"32-column slice mask must be one")}
  }else{
    val join=Module(new MatrixSliceJoin(columns));join.io.request<>io.request;io.result<>join.io.result
    val leaves=Seq.fill(slices)(Module(new RetainedMatrixTileAdapter))
    for(i<-0 until slices){
      leaves(i).io.scanEnable:=io.scanEnable
      leaves(i).io.request<>join.io.sliceRequest(i);join.io.sliceResult(i)<>leaves(i).io.result
    }
    io.acceptedSteps:=leaves.map(_.io.acceptedSteps).reduce(_+_)
    io.resetRequired:=join.io.resetRequired||leaves.map(_.io.resetRequired).reduce(_||_)
  }
}
