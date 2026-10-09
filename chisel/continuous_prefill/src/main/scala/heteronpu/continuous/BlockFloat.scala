// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._
import gemmini.HeteroFP32Alu
object F32 {
  def bits(x:Double):BigInt=BigInt(java.lang.Float.floatToRawIntBits(x.toFloat).toLong & 0xffffffffL)
  def lit(x:Double):UInt=bits(x).U(32.W)
  def neg(x:UInt):UInt=x ^ "h80000000".U
  def bf(x:UInt):UInt=Cat(TensorMath.bf16Rne(x),0.U(16.W))
  def less(a:UInt,b:UInt):Bool=Mux(a(31)=/=b(31),a(31)&&(a(30,0).orR||b(30,0).orR),Mux(a(31),a(30,0)>b(30,0),a(30,0)<b(30,0)))
}
class ScalarRequest extends Bundle {val op=UInt(3.W);val a=UInt(32.W);val b=UInt(32.W)}
object ScalarOp {
  val Add=0;val Mul=1;val Div=2;val Sqrt=3;val ExpNegative=4
  // Explicit per-request IEEE RNE multiplication policy for GDN convolution.
  // Keep opcode 5 unsupported and preserve legacy Mul's underflow rejection.
  val MulIeeeRne=6
  val Softplus=7
}
/** exp(-abs(x)): range reduction plus degree-7 polynomial. |x|>=80 -> 0.
  * IEEE operations are actual HardFloat circuits, not simulation callbacks.
  * Optional Softplus7 uses this same ALU/divider and exp path; no log unit.
  * Stable softplus(x)=max(x,0)+log1p(exp(-abs(x))), threshold x>20 -> x.
  * log1p uses eight odd atanh terms through power15, each operation FP32 RNE.
  * Mathematically legal x<=-80 is unsupported because exp saturates; reject it.
  * Default remains disabled. One operation in flight; latency depends on the
  * iterative divider and the selected branch; result stays held until fire.
  * Functional implementation; 800 MHz is a target, not a timing result. */
class BlockScalarFloat(enableSoftplus: Boolean = false) extends Module {
  val io=IO(new Bundle {val request=Flipped(Decoupled(new ScalarRequest));val result=Decoupled(UInt(32.W));val error=Output(Bool())})
  val idle::normal::divIssue::divWait::expScale::expFloor::expFraction::expMul::expAdd::expFinish::softDenominator::softSquare::softMul::softAdd::softDouble::softLog::softFinish::done::Nil=Enum(18)
  val state=RegInit(idle);val op=Reg(UInt(3.W));val a=Reg(UInt(32.W));val b=Reg(UInt(32.W));val out=Reg(UInt(32.W))
  val err=RegInit(false.B);val k=Reg(UInt(8.W));val frac=Reg(UInt(32.W));val horner=Reg(UInt(32.W));val product=Reg(UInt(32.W));val index=Reg(UInt(3.W))
  // Softplus reuses the existing ALU, exp path and divider; no second SFU.
  val softInput=Reg(UInt(32.W));val softE=Reg(UInt(32.W));val softY=Reg(UInt(32.W));val softZ=Reg(UInt(32.W))
  val softRom=VecInit((0 to 7).map(i=>F32.lit(1.0/(2*i+1))))
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
    is(idle){when(io.request.fire){a:=io.request.bits.a;b:=io.request.bits.b;op:=io.request.bits.op;err:=false.B
      when(!TensorMath.finite(io.request.bits.a) || !TensorMath.finite(io.request.bits.b) ||
        (io.request.bits.op>ScalarOp.ExpNegative.U && io.request.bits.op=/=ScalarOp.MulIeeeRne.U && (io.request.bits.op=/=ScalarOp.Softplus.U || !enableSoftplus.B))){out:=0.U;err:=true.B;state:=done}
      .elsewhen(io.request.bits.op===ScalarOp.Softplus.U){
        softInput:=io.request.bits.a
        when(io.request.bits.a(31) && io.request.bits.a(30,0)>=F32.lit(80)){out:=0.U;err:=true.B;state:=done}
          .elsewhen(F32.less(F32.lit(20),io.request.bits.a)){out:=io.request.bits.a;state:=done}
          .otherwise{state:=expScale}
      }
      .elsewhen(io.request.bits.op===ScalarOp.ExpNegative.U){state:=expScale}
      .elsewhen(io.request.bits.op===ScalarOp.Div.U || io.request.bits.op===ScalarOp.Sqrt.U){state:=divIssue}.otherwise{state:=normal}
    }}
    is(normal){
      alu.io.op:=op===ScalarOp.Mul.U || op===ScalarOp.MulIeeeRne.U
      out:=alu.io.out
      // HardFloat still computes the same rounded bits, including signed zero
      // and gradual subnormals. Only the explicit GDN multiply policy accepts
      // underflow/inexact; invalid, divide-by-zero, overflow and nonfinite
      // results remain fatal. All existing opcodes keep their prior policy.
      err:=alu.io.exceptionFlags(4,2).orR ||
        (alu.io.exceptionFlags(1) && op=/=ScalarOp.MulIeeeRne.U) || !TensorMath.finite(alu.io.out)
      state:=done
    }
    is(divIssue){when(div.io.inReady){state:=divWait}}
    is(divWait){when(div.io.outValid_div||div.io.outValid_sqrt){
      val r=fNFromRecFN(8,24,div.io.out);val invalid=div.io.exceptionFlags(4,2).orR ||
        (div.io.exceptionFlags(1) && op=/=ScalarOp.Softplus.U) || !TensorMath.finite(r)
      out:=r;err:=invalid
      when(op===ScalarOp.Softplus.U && !invalid){softY:=r;state:=softSquare}.otherwise{state:=done}
    }}
    is(expScale){alu.io.op:=true.B;alu.io.x:=a & "h7fffffff".U;alu.io.y:=F32.lit(1.0/math.log(2.0));out:=alu.io.out
      when(a(30,0)>=F32.lit(80)){out:=0.U;state:=done}.otherwise{state:=expFloor}}
    is(expFloor){k:=conv.io.out(7,0);a:=out;horner:=rom(7);index:=6.U;state:=expFraction}
    is(expFraction){alu.io.y:=F32.neg(fNFromRecFN(8,24,integer.io.out));frac:=alu.io.out;state:=expMul}
    is(expMul){alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=frac;product:=alu.io.out;state:=expAdd}
    is(expAdd){alu.io.x:=product;alu.io.y:=rom(index);horner:=alu.io.out
      when(index===0.U){state:=expFinish}.otherwise{index:=index-1.U;state:=expMul}}
    is(expFinish){alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=Cat(0.U(1.W),(127.U(8.W)-k),0.U(23.W));out:=alu.io.out
      when(op===ScalarOp.Softplus.U){softE:=alu.io.out;state:=softDenominator}.otherwise{state:=done}}
    is(softDenominator){alu.io.x:=F32.lit(2);alu.io.y:=softE;a:=softE;b:=alu.io.out;state:=divIssue}
    is(softSquare){alu.io.op:=true.B;alu.io.x:=softY;alu.io.y:=softY;softZ:=alu.io.out;horner:=softRom(7);index:=6.U;state:=softMul}
    is(softMul){alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=softZ;product:=alu.io.out;state:=softAdd}
    is(softAdd){alu.io.x:=product;alu.io.y:=softRom(index);horner:=alu.io.out
      when(index===0.U){state:=softDouble}.otherwise{index:=index-1.U;state:=softMul}}
    is(softDouble){alu.io.op:=true.B;alu.io.x:=F32.lit(2);alu.io.y:=softY;product:=alu.io.out;state:=softLog}
    is(softLog){alu.io.op:=true.B;alu.io.x:=product;alu.io.y:=horner;out:=alu.io.out;state:=softFinish}
    is(softFinish){alu.io.x:=Mux(softInput(31),0.U,softInput);alu.io.y:=out;out:=alu.io.out
      err:=alu.io.exceptionFlags(4,2).orR || !TensorMath.finite(alu.io.out);state:=done}
    is(done){when(io.result.fire){state:=idle}}
  }
  val softAluStage = state===softDenominator || state===softSquare || state===softMul ||
    state===softAdd || state===softDouble || state===softLog || state===softFinish
  val softExpAluStage = op===ScalarOp.Softplus.U && (state===expScale || state===expFraction ||
    state===expMul || state===expAdd || state===expFinish)
  when((softAluStage || softExpAluStage) && (alu.io.exceptionFlags(4,2).orR || !TensorMath.finite(alu.io.out))) {
    out:=alu.io.out;err:=true.B;state:=done
  }
}
