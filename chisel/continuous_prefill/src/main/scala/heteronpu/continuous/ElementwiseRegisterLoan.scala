// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import heteronpu.p0.LocalSramConfig

/** Internal register transaction; never a public Command128 encoding. */
object ElementwiseLoanOp {
  val Add = 1; val Mul = 2; val MulIeeeRne = 6; val RmsEpilogue = 7
  val Aborted = 10
}
class ElementwiseLoanRequest extends Bundle {
  val tag = UInt(32.W); val op = UInt(3.W)
  val a = UInt(512.W); val b = UInt(512.W); val inverse = UInt(32.W)
}
class ElementwiseLoanResult extends Bundle {
  val tag = UInt(32.W); val status = UInt(8.W); val value = UInt(512.W)
}
class ElementwiseLoanPort extends Bundle {
  val request = Flipped(Decoupled(new ElementwiseLoanRequest))
  val result = Decoupled(new ElementwiseLoanResult)
  val abort = Input(Bool()); val resetLoan = Input(Bool())
  val busy = Output(Bool()); val resetRequired = Output(Bool())
}

/** Control extension of the real DDR engine, using its SAME sixteen ALUs,
  * a/b/value/raw registers and SRAM. No arithmetic module or wide register is
  * created here. The original engine and all existing instantiations stay intact.
  *
  * A register transaction is admitted only while the DDR engine is idle/drained;
  * an offered DDR job wins arbitration. An RMS epilogue retains the loan across
  * all three FP32 operations. Its final BF16 conversion belongs to its caller.
  * Global module reset still requires coordinated external DDR drain.
  * resetLoan cannot erase a held terminal or unlock a DDR-originated error.
  */
class ElementwiseRegisterLoan(c: ChainConfig = ChainConfig(),
                             sram: LocalSramConfig = LocalSramConfig())
    extends ElementwiseMemoryEngine(c, sram) {
  val loan = IO(new ElementwiseLoanPort)
  val lIdle :: lPrimitive :: lIeee :: lNormalize :: lGamma :: lWeighted :: lReply :: lLocked :: Nil = Enum(8)
  val loanState = RegInit(lIdle)
  val loanPoison = RegInit(false.B)
  val active = loanState =/= lIdle && loanState =/= lLocked
  val drained = state === idle && !io.memory.valid && !io.response.valid

  io.job.ready := state === idle && !poison && loanState === lIdle && !loanPoison
  loan.request.ready := drained && !poison && !loanPoison && loanState === lIdle &&
    !io.job.valid && !loan.abort && !loan.resetLoan
  loan.result.valid := loanState === lReply && !loan.abort && !loan.resetLoan
  loan.result.bits.tag := job.tag
  loan.result.bits.status := status
  loan.result.bits.value := Mux(status === Status.Ok.U, value, 0.U)
  loan.busy := active
  loan.resetRequired := loanPoison
  io.resetRequired := poison || loanPoison

  def loanFail(code: UInt): Unit = {
    status := code; value := 0.U; loanPoison := true.B; loanState := lReply
  }
  // Parent aluBad implements the original Add/Mul flags[4:1] contract.
  // For the *multiply-only* IEEE branch, HardFloat RNE NV/OF produce NaN/Inf;
  // MulRecFN cannot raise DZ. Therefore finite(out) is precisely flags[4:2]
  // plus finite checking, while accepting UF/NX. No rounding/datapath is changed.
  val ieeeBad = VecInit((0 until 16).map(i => !TensorMath.finite(aluResults(i)))).asUInt.orR
  val strictBad = aluBad.asUInt.orR

  when(loan.request.fire) {
    val r = loan.request.bits
    job.tag := r.tag; job.op := Mux(r.op === ElementwiseLoanOp.Add.U, ElemOp.Add.U, ElemOp.Mul.U)
    a := r.a
    b := Mux(r.op === ElementwiseLoanOp.RmsEpilogue.U, Fill(16, r.inverse), r.b)
    raw := r.b // RMS weight survives normalize in the parent's existing raw register.
    tile := 16.U; calcIndex := 0.U; status := Status.Ok.U
    cycles := 0.U; reads := 0.U; writes := 0.U; elementCount := 0.U
    when(r.op === ElementwiseLoanOp.RmsEpilogue.U) { loanState := lNormalize }
      .elsewhen(r.op === ElementwiseLoanOp.MulIeeeRne.U) { loanState := lIeee }
      .elsewhen(r.op === ElementwiseLoanOp.Add.U || r.op === ElementwiseLoanOp.Mul.U) { loanState := lPrimitive }
      .otherwise { loanFail(Status.Unsupported.U) }
  }
  when(active) { cycles := cycles + 1.U }
  when(loanState === lPrimitive || loanState === lIeee) {
    when(Mux(loanState === lIeee, ieeeBad, strictBad)) { loanFail(Status.Numerical.U) }
      .otherwise { value := aluResults.asUInt; elementCount := 16.U; loanState := lReply }
  }
  when(loanState === lNormalize) {
    when(ieeeBad) { loanFail(Status.Numerical.U) }.otherwise {
      value := aluResults.asUInt
      a := Fill(16, "h3f800000".U(32.W)); b := raw; job.op := ElemOp.Add.U
      loanState := lGamma
    }
  }
  when(loanState === lGamma) {
    when(strictBad) { loanFail(Status.Numerical.U) }.otherwise {
      b := aluResults.asUInt; a := value; job.op := ElemOp.Mul.U
      loanState := lWeighted
    }
  }
  when(loanState === lWeighted) {
    when(ieeeBad) { loanFail(Status.Numerical.U) }.otherwise {
      value := aluResults.asUInt; elementCount := 16.U; loanState := lReply
    }
  }
  when(loan.result.fire) { loanState := Mux(loanPoison, lLocked, lIdle) }
  // Abort/reset wins over computation and a held-success retirement on this edge.
  when(active && (loan.abort || loan.resetLoan)) { loanFail(ElementwiseLoanOp.Aborted.U) }
  when(loanState === lLocked && loan.resetLoan && drained && !poison) {
    loanPoison := false.B; status := Status.Ok.U; loanState := lIdle
  }
  assert(!(loan.request.fire && io.job.fire), "one borrower at a time")
  when(active || loanState === lLocked) {
    assert(!io.job.fire && !io.memory.valid && !io.response.ready,
      "register loan cannot overlap DDR transport")
  }
}
