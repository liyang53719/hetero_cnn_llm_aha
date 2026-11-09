// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import hardfloat._
import hardfloat.consts._
import gemmini.HeteroFP32Alu

/** exp(-abs(x)): range reduction plus degree-7 polynomial. |x|>=80 -> 0.
  * IEEE operations are actual HardFloat circuits, not simulation callbacks.
  * Optional Softplus7 uses this same ALU/divider and exp path; no log unit.
  * Stable softplus(x)=max(x,0)+log1p(exp(-abs(x))), threshold x>20 -> x.
  * log1p uses eight odd atanh terms through power15, each operation FP32 RNE.
  * Mathematically legal x<=-80 is unsupported because exp saturates; reject it.
  * The fixed shared V2 replacement enables Softplus for every runtime profile.
  * Policies1/2 implement an explicit approximate P7 recipe, not correctly
  * rounded exp/Torch equality. Policy0 retains the old primitive equations.
  * One operation in flight; latency depends on the
  * iterative divider and the selected branch; result stays held until fire.
  * Functional implementation; 800 MHz is a target, not a timing result. */
class BlockScalarFloatPolicyV2 extends Module {
  // One replacement primitive shared by all runtime profiles, not another SFU.
  // Policy0 is original BlockScalarFloat(enableSoftplus=true); no model elaboration.
  private val enableSoftplus = true
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new UnifiedScalarRequestV2))
    val result=Decoupled(new UnifiedScalarResultV2)
  })
  private val stateValues=Enum(24)
  val idle=stateValues(0)
  val normal=stateValues(1)
  val divIssue=stateValues(2)
  val divWait=stateValues(3)
  val expScale=stateValues(4)
  val expFloor=stateValues(5)
  val expFraction=stateValues(6)
  val expMul=stateValues(7)
  val expAdd=stateValues(8)
  val expFinish=stateValues(9)
  val softDenominator=stateValues(10)
  val softSquare=stateValues(11)
  val softMul=stateValues(12)
  val softAdd=stateValues(13)
  val softDouble=stateValues(14)
  val softLog=stateValues(15)
  val softFinish=stateValues(16)
  val decHi=stateValues(17)
  val decSubtractHi=stateValues(18)
  val decLo=stateValues(19)
  val decSubtractLo=stateValues(20)
  val decFraction=stateValues(21)
  val decSubnormal=stateValues(22)
  val done=stateValues(23)
  val policy=Reg(UInt(2.W));val reduced=Reg(UInt(32.W))
  val state=RegInit(idle);val op=Reg(UInt(3.W));val a=Reg(UInt(32.W));val b=Reg(UInt(32.W));val out=Reg(UInt(32.W))
  val err=RegInit(false.B);val k=Reg(UInt(8.W));val frac=Reg(UInt(32.W));val horner=Reg(UInt(32.W));val product=Reg(UInt(32.W));val index=Reg(UInt(3.W))
  val primitiveFlags=RegInit(0.U(5.W));val primitiveFlagsValid=RegInit(false.B)
  // Softplus reuses the existing ALU, exp path and divider; no second SFU.
  val softInput=Reg(UInt(32.W));val softE=Reg(UInt(32.W));val softY=Reg(UInt(32.W));val softZ=Reg(UInt(32.W))
  val softRom=VecInit((0 to 7).map(i=>F32.lit(1.0/(2*i+1))))
  val coeff=(0 to 7).map(i=>math.pow(-math.log(2.0),i)/(if(i==0)1.0 else (1 to i).map(_.toDouble).product))
  val rom=VecInit(coeff.map(F32.lit))
  val alu=Module(new HeteroFP32Alu);alu.io.op:=false.B;alu.io.x:=a;alu.io.y:=b
  val div=Module(new DivSqrtRecFN_small(8,24,0));div.io.inValid:=state===divIssue
  div.io.sqrtOp:=op===ScalarOp.Sqrt.U;div.io.a:=recFNFromFN(8,24,a);div.io.b:=recFNFromFN(8,24,b)
  div.io.roundingMode:=round_near_even;div.io.detectTininess:=tininess_afterRounding
  val conv=Module(new RecFNToIN(8,24,32));conv.io.in:=recFNFromFN(8,24,out);conv.io.roundingMode:=Mux(policy===0.U,round_minMag,round_near_even);conv.io.signedOut:=false.B
  val integer=Module(new INToRecFN(32,8,24));integer.io.signedIn:=false.B;integer.io.in:=k
  integer.io.roundingMode:=round_near_even;integer.io.detectTininess:=tininess_afterRounding
  io.request.ready:=state===idle;io.result.valid:=state===done;io.result.bits.value:=out;io.result.bits.error:=err;io.result.bits.policy:=policy
  io.result.bits.flags:=primitiveFlags;io.result.bits.primitiveFlagsValid:=state===done && primitiveFlagsValid
  switch(state) {
    is(idle){when(io.request.fire){policy:=io.request.bits.policy;a:=io.request.bits.payload.a;b:=io.request.bits.payload.b;op:=io.request.bits.payload.op;err:=false.B
      primitiveFlags:=0.U;primitiveFlagsValid:=false.B
      val p=io.request.bits.policy;val requestedOp=io.request.bits.payload.op
      val policyLegal=p===0.U || (p===1.U && requestedOp===ScalarOp.ExpNegative.U) ||
        (p===2.U && requestedOp===ScalarOp.Softplus.U)
      val decayInputLegal=p=/=1.U || io.request.bits.payload.a(31) || !io.request.bits.payload.a(30,0).orR
      when(!policyLegal || !decayInputLegal || !TensorMath.finite(io.request.bits.payload.a) || !TensorMath.finite(io.request.bits.payload.b) ||
        (io.request.bits.payload.op>ScalarOp.ExpNegative.U && io.request.bits.payload.op=/=ScalarOp.MulIeeeRne.U && (io.request.bits.payload.op=/=ScalarOp.Softplus.U || !enableSoftplus.B))){out:=0.U;err:=true.B;state:=done}
      .elsewhen(io.request.bits.payload.op===ScalarOp.Softplus.U){
        softInput:=io.request.bits.payload.a
        when(io.request.bits.payload.a(31) && io.request.bits.payload.a(30,0)>=F32.lit(80)){out:=0.U;err:=true.B;state:=done}
          .elsewhen(F32.less(F32.lit(20),io.request.bits.payload.a)){out:=io.request.bits.payload.a;state:=done}
          .otherwise{state:=expScale}
      }
      .elsewhen(io.request.bits.payload.op===ScalarOp.ExpNegative.U){state:=expScale}
      .elsewhen(io.request.bits.payload.op===ScalarOp.Div.U || io.request.bits.payload.op===ScalarOp.Sqrt.U){state:=divIssue}.otherwise{state:=normal}
    }}
    is(normal){
      alu.io.op:=op===ScalarOp.Mul.U || op===ScalarOp.MulIeeeRne.U
      out:=alu.io.out
      primitiveFlags:=alu.io.exceptionFlags;primitiveFlagsValid:=true.B
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
      when(policy===0.U){
        when(a(30,0)>=F32.lit(80)){out:=0.U;state:=done}.otherwise{state:=expFloor}
      }.otherwise{
        // exp(-104) is below half the minimum FP32 subnormal. The guard also
        // bounds conversion for all finite negative inputs; do not use z flags
        // on this short path (|a|*log2e may overflow before this selection).
        when(a(30,0)>="h42d00000".U){out:=0.U;state:=done}.otherwise{state:=expFloor}
      }}
    is(expFloor){k:=conv.io.out(7,0);horner:=rom(7);index:=6.U
      when(policy===0.U){a:=out;state:=expFraction}
        .otherwise{state:=decHi}
    }
    // New range reduction is literally separate FP32 RNE nodes, not an FMA:
    // k=RNE(|a|*log2e), r=(|a|-k*ln2_hi)-k*ln2_lo, fraction=r*log2e.
    is(decHi){alu.io.op:=true.B;alu.io.x:=fNFromRecFN(8,24,integer.io.out);alu.io.y:="h3f317200".U;product:=alu.io.out;state:=decSubtractHi}
    is(decSubtractHi){alu.io.x:=a & "h7fffffff".U;alu.io.y:=F32.neg(product);reduced:=alu.io.out;state:=decLo}
    is(decLo){alu.io.op:=true.B;alu.io.x:=fNFromRecFN(8,24,integer.io.out);alu.io.y:="h35bfbe8e".U;product:=alu.io.out;state:=decSubtractLo}
    is(decSubtractLo){alu.io.x:=reduced;alu.io.y:=F32.neg(product);reduced:=alu.io.out;state:=decFraction}
    is(decFraction){alu.io.op:=true.B;alu.io.x:=reduced;alu.io.y:="h3fb8aa3b".U;frac:=alu.io.out;state:=expMul}
    is(expFraction){alu.io.y:=F32.neg(fNFromRecFN(8,24,integer.io.out));frac:=alu.io.out;state:=expMul}
    is(expMul){alu.io.op:=true.B;alu.io.x:=horner;alu.io.y:=frac;product:=alu.io.out;state:=expAdd}
    is(expAdd){alu.io.x:=product;alu.io.y:=rom(index);horner:=alu.io.out
      when(index===0.U){state:=expFinish}.otherwise{index:=index-1.U;state:=expMul}}
    is(expFinish){alu.io.op:=true.B;alu.io.x:=horner
      alu.io.y:=Cat(0.U(1.W),Mux(policy=/=0.U && k>126.U,253.U(8.W)-k,127.U(8.W)-k),0.U(23.W))
      out:=alu.io.out
      when(policy=/=0.U && k>126.U){state:=decSubnormal}
        .elsewhen(op===ScalarOp.Softplus.U){softE:=alu.io.out;state:=softDenominator}.otherwise{state:=done}}
    is(decSubnormal){alu.io.op:=true.B;alu.io.x:=out;alu.io.y:="h00800000".U;out:=alu.io.out
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
  val decayAluStage=policy=/=0.U && ((state===expScale && a(30,0)<"h42d00000".U) ||
    state===decHi || state===decSubtractHi || state===decLo || state===decSubtractLo || state===decFraction ||
    state===expMul || state===expAdd || state===expFinish || state===decSubnormal)
  // Match candidate _node: accept gradual underflow/inexact; reject severe
  // exceptions and all nonfinite intermediates. Legacy policy equations stay.
  when((softAluStage || softExpAluStage || decayAluStage) && (alu.io.exceptionFlags(4,2).orR || !TensorMath.finite(alu.io.out))) {
    out:=alu.io.out;err:=true.B;state:=done
  }
}
