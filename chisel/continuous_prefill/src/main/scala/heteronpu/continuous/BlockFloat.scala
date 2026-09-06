// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._
import gemmini.HeteroFP32Alu

object F32 {
  def bits(x: Double): BigInt = BigInt(java.lang.Float.floatToRawIntBits(x.toFloat).toLong & 0xffffffffL)
  def lit(x: Double): UInt = bits(x).U(32.W)
  def neg(x: UInt): UInt = x ^ "h80000000".U
  def bf(x: UInt): UInt = Cat(TensorMath.bf16Rne(x),0.U(16.W))
  def less(a: UInt,b: UInt): Bool = Mux(a(31)=/=b(31),a(31) && (a(30,0).orR||b(30,0).orR),Mux(a(31),a(30,0)>b(30,0),a(30,0)<b(30,0)))
}

/** Shared scalar IEEE unit. expNegative computes exp(-abs(x)), with a recorded
  * degree-7 range-reduced polynomial; |x| >= 80 returns zero. Constants are
  * elaboration-time ROM data, never simulator callbacks. No hidden host math.
  * Physical timing is NOT signed off by these functional simulations. */
class ScalarRequest extends Bundle {val op=UInt(3.W);val a=UInt(32.W);val b=UInt(32.W)}
object ScalarOp {val Add=0;val Mul=1;val Div=2;val Sqrt=3;val ExpNegative=4}
class BlockScalarFloat extends Module {
  val io=IO(new Bundle {val request=Flipped(Decoupled(new ScalarRequest));val result=Decoupled(UInt(32.W));val error=Output(Bool())})
  val idle::normal::divIssue::divWait::expScale::expFraction::expMul::expAdd::expFinish::done::Nil=Enum(10)
  val state=RegInit(idle);val op=Reg(UInt(3.W));val a=Reg(UInt(32.W));val b=Reg(UInt(32.W));val out=Reg(UInt(32.W))
  val err=RegInit(false.B);val k=Reg(UInt(8.W));val frac=Reg(UInt(32.W));val horner=Reg(UInt(32.W));val product=Reg(UInt(32.W));val index=Reg(UInt(3.W))
  val coeff=(0 to 7).map(i=>math.pow(-math.log(2.0),i)/(if(i==0)1.0 else (1 to i).map(_.toDouble).product))
  val rom=VecInit(coeff.map(F32.lit))
  val alu=Module(new HeteroFP32Alu);alu.io.op:=false.B;alu.io.x:=a;alu.io.y:=b
  val div=Module(new DivSqrtRecFN_small(8,24,0));div.io.inValid:=state===divIssue
  div.io.sqrtOp:=op===ScalarOp.Sqrt.U;div.io.a:=recFNFromFN(8,24,a);div.io.b:=recFNFromFN(8,24,b)
  div.io.roundingMode:=round_near_even;div.io.detectTininess:=tininess_afterRounding
  val conv=Module(new RecFNToIN(8,24,32));conv.io.in:=recFNFromFN(8,24,out);conv.io.roundingMode:=round_minMag;conv.io.signedOut:=false.B
  val integer=Module(new INToRecFN(32,8,24));integer.io.signedIn:=false.B;integer.io.in:=k
  integer.io.roundingMode:=round_near_even;integer.io.detectTininess:=tininess_afterRounding
  io.request.ready:=state===idle;io.result.valid:=state===done;io.result.bits:=out;io.error:=err
  switch(state) {
    is(idle) {when(io.request.fire) {a:=io.request.bits.a;b:=io.request.bits.b;op:=io.request.bits.op;err:=false.B
      when(!TensorMath.finite(io.request.bits.a)|| !TensorMath.finite(io.request.bits.b)||io.request.bits.op>ScalarOp.ExpNegative.U){out:=0.U;err:=true.B;state:=done}
      .elsewhen(io.request.bits.op===ScalarOp.ExpNegative.U){state:=expScale}
      .elsewhen(io.request.bits.op>=ScalarOp.Div.U){state:=divIssue}
      .otherwise{state:=normal}
    }}
    is(normal){alu.io.op:=op===ScalarOp.Mul.U;out:=alu.io.out;err:=alu.io.exceptionFlags(4,1).orR|| !TensorMath.finite(alu.io.out);state:=done}
    is(divIssue){when(div.io.inReady){state:=divWait}}
    is(divWait){when(div.io.outValid_div||div.io.outValid_sqrt){val result=fNFromRecFN(8,24,div.io.out);out:=result;err:=div.io.exceptionFlags(4,1).orR|| !TensorMath.finite(result);state:=done}}
    is(expScale){alu.io.op:=true.B;alu.io.x:=a & "h7fffffff".U;alu.io.y:=F32.lit(1.0/math.log(2.0));out:=alu.io.out
      when(a(30,0)>=F32.lit(80.0)){out:=0.U;state:=done}.otherwise{state:=expFraction}}
    is(expFraction){k:=conv.io.out(7,0);state:=expMul;horner:=rom(7);index:=6.U
      // out holds abs(x)*log2(e); the integer conversion is completed here.
      a:=out
    }
    is(expMul){
      when(index===6.U){alu.io.x:=a;alu.io.y:=F32.neg(fNFromRecFN(8,24,integer.io.out));frac:=alu.io.out;product:=0.U;state:=expAdd}
      .otherwise{alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=frac;product:=alu.io.out;state:=expAdd}
    }
    is(expAdd){
      // Separate first multiply because the fractional register was just set.
      when(index===6.U){alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=frac;product:=alu.io.out;index:=5.U;state:=expFinish}
      .otherwise{alu.io.x:=product;alu.io.y:=rom(index);horner:=alu.io.out;when(index===0.U){state:=normal;op:=ScalarOp.Mul.U;a:=alu.io.out;b:=Cat(0.U(1.W),(127.U(8.W)-k),0.U(23.W))}.otherwise{index:=index-1.U;state:=expMul}}
    }
    is(expFinish){alu.io.x:=product;alu.io.y:=rom(6);horner:=alu.io.out;state:=expMul}
    is(done){when(io.result.fire){state:=idle}}
  }
}
