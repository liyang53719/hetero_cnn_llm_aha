// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import gemmini.HeteroFP32Alu

/** Source-only candidate: one fixed bank, 32 AddRecFN + 32 MulRecFN,
  * 32 existing integer BF16-RNE formatters, and one tagged elastic result.
  * No FMA, divider, sqrt, exp, cache, lease ledger, or model parameter.
  * One-cycle registered response; source-level II1 only when result.ready.
  * Ready is combinational: registering it requires a separately sized skid.
  */
class UnifiedVectorElement32BankV4 extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new UnifiedVectorElement32RequestV4))
    val result = Decoupled(new UnifiedVectorElement32ResultV4)
  })

  val full = RegInit(false.B)
  val out = Reg(new UnifiedVectorElement32ResultV4)
  val alus = Seq.fill(32)(Module(new HeteroFP32Alu))
  val request = io.request.bits.payload
  val policy = request.policy
  val legacy = policy === UnifiedVectorElement32PolicyV4.LegacyRaw.U
  val bfMul = policy === UnifiedVectorElement32PolicyV4.Bf16MulRne.U
  val bfAdd = policy === UnifiedVectorElement32PolicyV4.Bf16AddRne.U
  val gradual = policy === UnifiedVectorElement32PolicyV4.RawFp32FiniteGradual.U
  val format = policy === UnifiedVectorElement32PolicyV4.RawFp32ToBf16Rne.U
  val rawMulBf16 = policy === UnifiedVectorElement32PolicyV4.RawFp32MulBf16Rne.U
  val arithmetic = legacy || bfMul || bfAdd || gradual || rawMulBf16
  val legacyPolicyLegal = legacy || (bfMul && request.multiply) || (bfAdd && !request.multiply)
  val laneErrors = Wire(Vec(32, Bool()))
  val values = Wire(Vec(32, UInt(32.W)))
  val flags = Wire(Vec(32, UInt(5.W)))

  for (i <- 0 until 32) {
    val a = request.a(i)
    val b = request.b(i)
    alus(i).io.op := request.multiply
    alus(i).io.x := a
    alus(i).io.y := b
    val raw = alus(i).io.out
    val arithmeticFlags = alus(i).io.exceptionFlags
    val expandedFinite = a(15, 0) === 0.U && b(15, 0) === 0.U &&
      TensorMath.finite(a) && TensorMath.finite(b)
    // Reuse THIS lane's formatter for arithmetic or in-place raw formatting.
    // Format ignores b/multiply; no scalar lane0 arbiter or extra FP32 ALU.
    val rounded = TensorMath.bf16Rne(Mux(format, a, raw))
    val roundedFinite = rounded(14, 7) =/= "hff".U
    val bf16Expanded = Cat(rounded, 0.U(16.W))
    // Exact V2/V3 arithmetic error policy; gradual underflow is not flushed.
    val badFlags = Mux(bfMul, arithmeticFlags(4, 2).orR, arithmeticFlags(4, 1).orR)
    val legacyPoliciesError = !legacyPolicyLegal || (!legacy && !expandedFinite) ||
      badFlags || !TensorMath.finite(raw) || (!legacy && !roundedFinite)
    val gradualError = !TensorMath.finite(a) || !TensorMath.finite(b) ||
      arithmeticFlags(4, 2).orR || !TensorMath.finite(raw)
    // Same raw-format finite/rounded-overflow policy as V3. No ALU flags.
    val formatError = !TensorMath.finite(a) || !roundedFinite
    // Literally policy3-Mul followed by policy4 on its rounded FP32 result.
    // No FMA, no direct exact-product-to-BF16 rounding, no recipe substitution.
    val rawMulBf16Error = !request.multiply || gradualError || !roundedFinite
    laneErrors(i) := Mux(format, formatError,
      Mux(rawMulBf16, rawMulBf16Error,
        Mux(gradual, gradualError, Mux(arithmetic, legacyPoliciesError, true.B))))
    values(i) := Mux(format, bf16Expanded,
      Mux(arithmetic, Mux(legacy || gradual, raw, bf16Expanded), 0.U))
    flags(i) := Mux(arithmetic, arithmeticFlags, 0.U)
  }

  io.result.valid := full
  io.result.bits := out
  io.request.ready := !full || io.result.ready

  // Push wins simultaneous pop: every edge either holds, fills, drains,
  // or atomically replaces the complete payload AND complete identity.
  // An error is held like any other result, never sticky bank poison.
  when(io.request.fire) {
    out.identity := io.request.bits.identity
    out.payload.policy := policy
    out.payload.value := values
    out.payload.arithFlags := flags
    out.payload.arithFlagsValid := arithmetic
    out.payload.formatFlagsValid := false.B
    out.payload.error := laneErrors.reduce(_ || _)
    full := true.B
  }.elsewhen(io.result.fire) {
    full := false.B
  }
  // Isolated reset clears validity only. External owner must first isolate
  // outstanding debt; this bank does not create epochs or terminal cancels.
}
