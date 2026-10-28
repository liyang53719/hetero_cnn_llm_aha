// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

object GdnElementwiseOp { val Add = 0; val SiluMul = 1; val SigmoidMul = 2 }

/** Internal decoded job, not a public Host command. All tensors are contiguous
  * BF16 [tokens,width], with 64-byte aligned, bus-rounded allocations. Add uses
  * hiddenWidth; SiluMul uses ffnWidth and interprets a as gate and b as up.
  * Opt-in SigmoidMul uses attentionWidth, a as preserved gate and b as context.
  */
class GdnElementwiseJob extends Bundle {
  val op = UInt(2.W)
  val tokens = UInt(16.W)
  val rowWidth = UInt(16.W)
  val a = UInt(64.W)
  val b = UInt(64.W)
  val output = UInt(64.W)
  val tag = UInt(32.W)
}

class GdnElementwiseResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
}

class GdnElementwiseOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnElementwiseJob))
  val done = Decoupled(new GdnElementwiseResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}

/** Qwen3.5 residual, MLP activation and optional attention gate owner with only an external shared FPU.
  * Pinned modeling_qwen3_5.py: residual additions at 896/902 and MLP at 826.
  * The official BF16 SiLU output is rounded BEFORE multiplication with up.
  * The shared exp polynomial is a frozen recipe, not native torch equality.
  * SiLU: e=exp(-abs(g)); inv=1/(1+e); sig=inv*(g.sign ? e : 1);
  * BF16(sig*g), then BF16(roundedSiLU*up). All multiplications explicitly use
  * MulIeeeRne, allowing gradual underflow; Add/Div errors are never masked.
  * Attention (pinned source line 808): BF16(sig), then BF16(context*roundedSig).
  * This path skips multiplication by the gate itself; it is not SiLU.
  * Mathematically legal negative gates <= -80 return Unsupported because the
  * shared exp service saturates there. They are never silently changed to zero.
  *
  * One 32-element beat is buffered. Padding is neither evaluated nor written.
  * Input allocations may overlap each other; output must be disjoint from both.
  * Partial staging writes never commit a failed result. Completion waits for the
  * final successful ACK. Failure locks until coordinated owner/service/transport
  * reset; reset alone cannot cancel an external transaction already in flight.
  */
class GdnElementwiseOwner(hiddenWidth: Int = 1024, ffnWidth: Int = 3584,
                          maxTokens: Int = 128, attentionWidth: Int = 2048,
                          enableAttentionSigmoidMul: Boolean = false) extends Module {
  require(hiddenWidth > 0 && hiddenWidth <= 65535)
  require(ffnWidth > 0 && ffnWidth <= 65535)
  require(maxTokens > 0 && maxTokens <= 65535)
  require(attentionWidth > 0 && attentionWidth <= 65535)
  val io = IO(new GdnElementwiseOwnerPort)
  val idle :: readA :: waitA :: readB :: waitB :: checkLane :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: finish :: locked :: Nil = Enum(12)
  val state = RegInit(idle)
  val add :: exp :: denominator :: inverse :: sign :: activate :: multiply :: Nil = Enum(7)
  val operation = RegInit(add)
  val job = Reg(new GdnElementwiseJob)
  val inputA = Reg(Vec(32, UInt(16.W)))
  val inputB = Reg(Vec(32, UInt(16.W)))
  val output = Reg(Vec(32, UInt(16.W)))
  val remaining = Reg(UInt(32.W))
  val offset = RegInit(0.U(64.W))
  val lane = RegInit(0.U(5.W))
  val value = Reg(UInt(32.W))
  val exponential = Reg(UInt(32.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val activeLanes = Mux(remaining >= 32.U, 32.U(6.W), remaining(5, 0))
  val x = Cat(inputA(lane), 0.U(16.W))
  val y = Cat(inputB(lane), 0.U(16.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U
  io.resetRequired := status =/= Status.Ok.U
  io.memory.valid := state === readA || state === readB || state === writeOutput
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := Mux(state === writeOutput, job.output, Mux(state === readB, job.b, job.a)) + offset
  // Zero inactive data too, so masked bytes cannot leak a preceding job.
  io.memory.bits.data := Mux(state === writeOutput,
    Cat((0 until 32).reverse.map(i => Mux(i.U < activeLanes, output(i), 0.U(16.W)))), 0.U)
  io.memory.bits.mask := Mux(state === writeOutput,
    Cat((0 until 32).reverse.map(i => Fill(2, i.U < activeLanes))), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitA || state === waitB || state === waitOutput
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    add -> ScalarOp.Add.U, exp -> ScalarOp.ExpNegative.U,
    denominator -> ScalarOp.Add.U, inverse -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    add -> x, exp -> x, denominator -> F32.lit(1), inverse -> F32.lit(1)))
  io.scalar.request.bits.b := MuxLookup(operation, value)(Seq(
    add -> y, exp -> 0.U, denominator -> exponential,
    sign -> Mux(x(31), exponential, F32.lit(1)), activate -> x, multiply -> y))
  io.scalar.result.ready := state === scalarWait

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  when(io.job.fire) {
    val j = io.job.bits
    job := j; remaining := j.tokens * j.rowWidth
    offset := 0.U; lane := 0.U; sequence := 0.U
    status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val payload = (j.tokens * j.rowWidth).pad(66) << 1
    val span = ((payload + 63.U) >> 6) << 6
    def badSpan(base: UInt): Bool = base(5, 0) =/= 0.U || base.pad(66) + span > (BigInt(1) << 56).U
    def overlap(a: UInt, b: UInt): Bool = a.pad(66) < b.pad(66) + span && b.pad(66) < a.pad(66) + span
    val validOp = j.op === GdnElementwiseOp.Add.U || j.op === GdnElementwiseOp.SiluMul.U ||
      (enableAttentionSigmoidMul.B && j.op === GdnElementwiseOp.SigmoidMul.U)
    val expectedWidth = MuxLookup(j.op, hiddenWidth.U)(Seq(
      GdnElementwiseOp.SiluMul.U -> ffnWidth.U, GdnElementwiseOp.SigmoidMul.U -> attentionWidth.U))
    when(!validOp || j.tokens === 0.U || j.tokens > maxTokens.U || j.rowWidth =/= expectedWidth ||
      badSpan(j.a) || badSpan(j.b) || badSpan(j.output) || overlap(j.output, j.a) || overlap(j.output, j.b)) {
      fail(Status.Bounds.U)
    }.otherwise { state := readA }
  }
  when(io.memory.fire) {
    state := Mux(state === readA, waitA, Mux(state === readB, waitB, waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitA || state === waitB) {
          for (i <- 0 until 32) {
            when(state === waitA) { inputA(i) := r.data((i + 1) * 16 - 1, i * 16) }
              .otherwise { inputB(i) := r.data((i + 1) * 16 - 1, i * 16) }
          }
          when(state === waitA) { state := readB }
            .otherwise { lane := 0.U; state := checkLane }
        }
        when(state === waitOutput) {
          bytes := bytes + (activeLanes << 1)
          when(remaining <= 32.U) { state := finish }
            .otherwise { remaining := remaining - 32.U; offset := offset + 64.U; state := readA }
        }
      }
  }
  when(state === checkLane) {
    when(!TensorMath.finite(x) || !TensorMath.finite(y)) { fail(Status.Numerical.U) }
      .elsewhen((job.op === GdnElementwiseOp.SiluMul.U || job.op === GdnElementwiseOp.SigmoidMul.U) && x(31) && x(30, 0) >= F32.lit(80)) {
        fail(Status.Unsupported.U)
      }.otherwise {
        operation := Mux(job.op === GdnElementwiseOp.Add.U, add, exp)
        state := scalarIssue
      }
  }
  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    val rounded = TensorMath.bf16Rne(r)
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        value := r; state := scalarIssue
        switch(operation) {
          is(exp) { exponential := r; operation := denominator }
          is(denominator) { operation := inverse }
          is(inverse) { operation := sign }
          is(sign) {
            when(job.op === GdnElementwiseOp.SigmoidMul.U) {
              value := Cat(rounded, 0.U(16.W)); operation := multiply
              when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
            }.otherwise { operation := activate }
          }
          is(activate) {
            value := Cat(rounded, 0.U(16.W)); operation := multiply
            when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
          }
        }
        when(operation === add || operation === multiply) {
          output(lane) := rounded
          when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
            .elsewhen(lane +& 1.U === activeLanes) { state := writeOutput }
            .otherwise { lane := lane + 1.U; state := checkLane }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
