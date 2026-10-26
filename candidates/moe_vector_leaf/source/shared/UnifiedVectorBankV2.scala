// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.HeteroFP32Alu

/** Exactly sixteen original FP32 ALUs. Shared16lane integer BF16 formatting
  * is explicit new logic, NOT16 extra FP32 arithmetic units. One value register
  * per lane holds either legacy rawFP32 or the formatted BF16-expanded value.
  * This version deliberately keeps original !full admission (source II2).
  * No elastic-refill throughput claim or per-model construction parameter.
  */
class UnifiedVectorBankV2 extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new UnifiedVectorRequestV2))
    val result=Decoupled(new UnifiedVectorResultV2)
  })
  val full=RegInit(false.B);val out=Reg(new UnifiedVectorResultV2)
  val alus=Seq.fill(16)(Module(new HeteroFP32Alu))
  val policy=io.request.bits.policy
  val legacy=policy===UnifiedVectorPolicyV2.LegacyRaw.U
  val bfMul=policy===UnifiedVectorPolicyV2.Bf16MulRne.U
  val bfAdd=policy===UnifiedVectorPolicyV2.Bf16AddRne.U
  val policyLegal=legacy || (bfMul && io.request.bits.multiply) || (bfAdd && !io.request.bits.multiply)
  val laneErrors=Wire(Vec(16,Bool()));val values=Wire(Vec(16,UInt(32.W)))
  for(i<-0 until 16){
    val a=io.request.bits.a(i);val b=io.request.bits.b(i)
    alus(i).io.op:=io.request.bits.multiply;alus(i).io.x:=a;alus(i).io.y:=b
    val raw=alus(i).io.out;val flags=alus(i).io.exceptionFlags
    val expandedFinite=a(15,0)===0.U && b(15,0)===0.U && TensorMath.finite(a) && TensorMath.finite(b)
    val rounded=TensorMath.bf16Rne(raw)
    val roundedFinite=rounded(14,7)=/="hff".U
    val badFlags=Mux(bfMul,flags(4,2).orR,flags(4,1).orR)
    laneErrors(i):= !policyLegal || (!legacy && !expandedFinite) || badFlags || !TensorMath.finite(raw) || (!legacy && !roundedFinite)
    values(i):=Mux(legacy,raw,Cat(rounded,0.U(16.W)))
  }
  io.request.ready:= !full;io.result.valid:=full;io.result.bits:=out
  when(io.request.fire){
    out.policy:=policy;out.value:=values;out.flags:=VecInit(alus.map(_.io.exceptionFlags))
    out.error:=laneErrors.reduce(_||_);full:=true.B
  }
  when(io.result.fire){full:=false.B}
}
