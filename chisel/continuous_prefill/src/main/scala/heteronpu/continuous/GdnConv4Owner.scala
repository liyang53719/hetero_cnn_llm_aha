// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Qwen3.5 depthwise causal convolution + SiLU, using the shared FP32 service.
  * No Matrix, iDMA, or floating-point arithmetic instance is created here.
  *
  * Frozen arithmetic policy: four separately rounded FP32 multiplies and
  * left-to-right FP32 adds starting at +0; BF16 RNE at the convolution boundary;
  * existing ScalarOp.ExpNegative/FP32 sigmoid recipe; BF16 RNE at output.
  * Convolution products explicitly request MulIeeeRne: real checkpoint values
  * can underflow to signed zero. The shared service preserves IEEE RNE gradual
  * underflow while still rejecting invalid/overflow/nonfinite results.
  * The pinned source establishes the BF16 boundaries, not its internal sum
  * tree or exp implementation. Official producer agreement is a separate gate.
  * The shared exp service saturates exp(-abs(x)) to zero at abs(x)>=80.
  * Negative convolved inputs in that range are rejected, since their official
  * BF16 SiLU may still be nonzero; no silent saturation is committed.
  *
  * One 32-channel group is retained at a time. Its weights are loaded once;
  * raw history advances locally across tokens and is staged only after the
  * group's final output ACK. Only the final history write ACK allows commit.
  * This is the convolution prefix, not the recurrent/gated-norm GDN block.
  */
class GdnConv4Owner(channels: Int = 6144, maxTokens: Int = 128) extends Module {
  require(channels > 0 && channels <= 65535 && channels % 32 == 0)
  require(maxTokens > 0 && maxTokens <= 65535)
  val io = IO(new GdnConv4OwnerPort)

  val idle :: readWeight :: waitWeight :: readHistory :: waitHistory :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: writeHistory :: waitHistoryWrite :: finish :: locked :: Nil = Enum(15)
  val state = RegInit(idle)
  val job = Reg(new GdnConv4Job)
  val group = RegInit(0.U(16.W)) // channel index, always a multiple of 32
  val token = RegInit(0.U(16.W))
  val beat = RegInit(0.U(2.W))
  val lane = RegInit(0.U(5.W))
  val tap = RegInit(0.U(2.W))
  val mul :: add :: exp :: denom :: inverse :: sign :: activate :: Nil = Enum(7)
  val operation = RegInit(mul)
  val weights = Reg(Vec(32, Vec(4, UInt(16.W))))
  val history = Reg(Vec(32, Vec(4, UInt(16.W))))
  val raw = Reg(Vec(32, UInt(16.W)))
  val output = Reg(Vec(32, UInt(16.W)))
  val accumulator = RegInit(0.U(32.W))
  val product = Reg(UInt(32.W))
  val conv = Reg(UInt(32.W))
  val probability = Reg(UInt(32.W))
  val value = Reg(UInt(32.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val cycles = RegInit(0.U(64.W))
  val bytes = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.historyCommitted := state === finish && status === Status.Ok.U
  io.done.bits.generation := job.expectedGeneration + Mux(io.done.bits.historyCommitted, 1.U, 0.U)
  io.resetRequired := status =/= Status.Ok.U

  val vectorOffset = ((token.pad(64) * channels.U) + group.pad(64)) << 1
  val historyOffset = (group.pad(64) << 3) + (beat.pad(64) << 6)
  io.memory.valid := state === readWeight || state === readHistory || state === readInput ||
    state === writeOutput || state === writeHistory
  io.memory.bits.write := state === writeOutput || state === writeHistory
  io.memory.bits.address := MuxLookup(state, job.input + vectorOffset)(Seq(
    readWeight -> (job.weight + historyOffset), readHistory -> (job.historyIn + historyOffset),
    writeOutput -> (job.output + vectorOffset), writeHistory -> (job.historyOut + historyOffset)))
  val historyBeats = history.asUInt.asTypeOf(Vec(4, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeHistory, historyBeats(beat), Mux(state === writeOutput, output.asUInt, 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitWeight || state === waitHistory || state === waitInput ||
    state === waitOutput || state === waitHistoryWrite

  val sample = Mux(tap === 3.U, raw(lane), history(lane)((tap + 1.U)(1, 0)))
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.Mul.U)(Seq(
    mul -> ScalarOp.MulIeeeRne.U,
    add -> ScalarOp.Add.U, exp -> ScalarOp.ExpNegative.U,
    denom -> ScalarOp.Add.U, inverse -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    mul -> Cat(sample, 0.U(16.W)), add -> accumulator, exp -> conv,
    denom -> F32.lit(1), inverse -> F32.lit(1)))
  io.scalar.request.bits.b := MuxLookup(operation, conv)(Seq(
    mul -> Cat(weights(lane)(tap), 0.U(16.W)), add -> product, exp -> 0.U,
    denom -> probability, inverse -> value,
    sign -> Mux(conv(31), probability, F32.lit(1))))
  io.scalar.result.ready := state === scalarWait

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  def beginCompute(): Unit = {
    lane := 0.U; tap := 0.U; accumulator := 0.U; operation := mul; state := scalarIssue
  }

  when(io.job.fire) {
    job := io.job.bits; group := 0.U; token := 0.U; beat := 0.U
    sequence := 0.U; status := Status.Ok.U; cycles := 0.U; bytes := 0.U
    val j = io.job.bits
    val vectorBytes = j.tokens.pad(66) * (channels * 2).U
    val stateBytes = (channels * 8).U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, vectorBytes) || badSpan(j.output, vectorBytes) ||
      badSpan(j.weight, stateBytes) || badSpan(j.historyOut, stateBytes) ||
      badSpan(j.historyIn, stateBytes)
    val oldOverlap = overlap(j.historyOut, stateBytes, j.historyIn, stateBytes) ||
      overlap(j.output, vectorBytes, j.historyIn, stateBytes)
    val unsafeWrites = overlap(j.output, vectorBytes, j.input, vectorBytes) ||
      overlap(j.output, vectorBytes, j.weight, stateBytes) ||
      overlap(j.historyOut, stateBytes, j.input, vectorBytes) ||
      overlap(j.historyOut, stateBytes, j.weight, stateBytes) ||
      overlap(j.historyOut, stateBytes, j.output, vectorBytes) || oldOverlap
    when(j.expectedGeneration =/= io.currentGeneration || (j.cold && j.expectedGeneration =/= 0.U)) { fail(Status.Dependency.U) }
      .elsewhen(j.tokens === 0.U || j.tokens > maxTokens.U || j.channels =/= channels.U ||
        j.expectedGeneration === "hffffffff".U || badAddress || unsafeWrites) { fail(Status.Bounds.U) }
      .otherwise { state := readWeight }
  }

  when(io.memory.fire) {
    state := MuxLookup(state, waitInput)(Seq(readWeight -> waitWeight,
      readHistory -> waitHistory, writeOutput -> waitOutput, writeHistory -> waitHistoryWrite))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitWeight || state === waitHistory) {
          for (i <- 0 until 8; t <- 0 until 4) {
            val v = r.data((i * 4 + t + 1) * 16 - 1, (i * 4 + t) * 16)
            when(state === waitWeight) { weights(Cat(beat, i.U(3.W)))(t) := v }
              .otherwise { history(Cat(beat, i.U(3.W)))(t) := v }
          }
          when(beat === 3.U) {
            beat := 0.U
            when(state === waitWeight && !job.cold) { state := readHistory }
              .otherwise {
                when(state === waitWeight) { history := 0.U.asTypeOf(history) }
                state := readInput
              }
          }.otherwise { beat := beat + 1.U; state := Mux(state === waitWeight, readWeight, readHistory) }
        }
        when(state === waitInput) { raw := r.data.asTypeOf(raw); beginCompute() }
        when(state === waitOutput) {
          bytes := bytes + 64.U
          // State stores raw QKV, never convolved/activated values.
          for (i <- 0 until 32) {
            for (t <- 0 until 3) history(i)(t) := history(i)(t + 1)
            history(i)(3) := raw(i)
          }
          when(token + 1.U === job.tokens) { beat := 0.U; state := writeHistory }
            .otherwise { token := token + 1.U; state := readInput }
        }
        when(state === waitHistoryWrite) {
          bytes := bytes + 64.U
          when(beat === 3.U) {
            when(group + 32.U === channels.U) { state := finish }
              .otherwise { group := group + 32.U; token := 0.U; beat := 0.U; state := readWeight }
          }.otherwise { beat := beat + 1.U; state := writeHistory }
        }
      }
  }

  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        state := scalarIssue
        switch(operation) {
          is(mul) { product := r; operation := add }
          is(add) {
            accumulator := r
            when(tap === 3.U) {
              val rounded = F32.bf(r)
              conv := rounded; operation := exp
              when(!TensorMath.finite(rounded) || (rounded(31) && rounded(30, 0) >= F32.lit(80))) {
                fail(Status.Numerical.U)
              }
            }.otherwise { tap := tap + 1.U; operation := mul }
          }
          is(exp) { probability := r; operation := denom }
          is(denom) { value := r; operation := inverse }
          is(inverse) { value := r; operation := sign }
          is(sign) { value := r; operation := activate }
          is(activate) {
            val rounded = TensorMath.bf16Rne(r)
            output(lane) := rounded
            when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
              .elsewhen(lane === 31.U) { state := writeOutput }
              .otherwise { lane := lane + 1.U; tap := 0.U; accumulator := 0.U; operation := mul }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
