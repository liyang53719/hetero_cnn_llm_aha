// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Decoded internal job, not the public Host command encoding. Core, gate and
  * output are packed BF16 [tokens, heads, 128]. Weight is FP32 [128], shared by
  * every head. Output must be a separate unpublished staging allocation.
  */
class GdnGatedNormJob extends Bundle {
  val tokens = UInt(16.W)
  val heads = UInt(16.W)
  val core = UInt(64.W)
  val gate = UInt(64.W)
  val weight = UInt(64.W)
  val output = UInt(64.W)
  val tag = UInt(32.W)
}

class GdnGatedNormResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
}

class GdnGatedNormOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnGatedNormJob))
  val done = Decoupled(new GdnGatedNormResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}

/** Qwen3.5-0.8B RMSNormGated, using the external shared BlockScalarFloat only.
  * No Matrix, iDMA, ALU or SFU is instantiated by this owner.
  *
  * The pinned official source casts recurrent output back to BF16 while keeping
  * recurrent state FP32. This owner's input is that BF16 producer boundary.
  * Norm: FP32 squares / ascending sum / multiply by 1/128 / add 1e-6 / sqrt /
  * reciprocal / multiply by input, THEN BF16 RNE. Multiply the rounded norm by
  * original FP32 gamma (no 1+gamma), then FP32 SiLU(gate), THEN BF16 RNE.
  * Sqrt+reciprocal and the existing exp polynomial are the frozen hardware
  * recipe, not claims of bit-identical torch rsqrt or CPU reduction order.
  * Official numerical agreement is checked independently of recipe agreement.
  * All multiplies request IEEE-RNE gradual underflow, including signed zero;
  * no service error is masked. Negative gates <= -80 fail closed because the
  * shared exp(-abs(x)) saturates there. Positive gates >= 80 are safe to round
  * to sigmoid=1 in FP32. Reset must reset/drain the shared service/transport.
  *
  * A 128-element head is retained locally, and weights are read once per job.
  * The final output ACK is mandatory before outputCommitted. An error may
  * leave partial staging writes but cannot publish any output, and locks this
  * owner until reset. Done and all decoupled requests are stable under stalls.
  */
class GdnGatedNormOwner(heads: Int = 16, maxTokens: Int = 128) extends Module {
  require(heads > 0 && heads <= 65535)
  require(maxTokens > 0 && maxTokens <= 65535)
  val io = IO(new GdnGatedNormOwnerPort)

  val idle :: readWeight :: waitWeight :: readCore :: waitCore :: readGate :: waitGate :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: finish :: locked :: Nil = Enum(13)
  val state = RegInit(idle)
  val square :: sum :: mean :: epsilon :: root :: inverse :: normalize :: weight :: exp :: denominator :: sigmoidInverse :: sigmoidSign :: activate :: gated :: Nil = Enum(14)
  val operation = RegInit(square)
  val job = Reg(new GdnGatedNormJob)
  val weights = Reg(Vec(128, UInt(32.W)))
  val core = Reg(Vec(128, UInt(16.W)))
  val gate = Reg(Vec(128, UInt(16.W)))
  val output = Reg(Vec(128, UInt(16.W)))
  val head = RegInit(0.U(16.W))
  val token = RegInit(0.U(16.W))
  val beat = RegInit(0.U(3.W))
  val lane = RegInit(0.U(7.W))
  val accumulator = RegInit(0.U(32.W))
  val value = Reg(UInt(32.W))
  val invRms = Reg(UInt(32.W))
  val weighted = Reg(UInt(32.W))
  val exponential = Reg(UInt(32.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U
  io.resetRequired := status =/= Status.Ok.U

  val rowOffset = ((token.pad(64) * heads.U) + head.pad(64)) << 8
  val beatOffset = beat.pad(64) << 6
  io.memory.valid := state === readWeight || state === readCore || state === readGate || state === writeOutput
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.core + rowOffset + beatOffset)(Seq(
    readWeight -> (job.weight + beatOffset), readGate -> (job.gate + rowOffset + beatOffset),
    writeOutput -> (job.output + rowOffset + beatOffset)))
  val outputBeats = output.asUInt.asTypeOf(Vec(4, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeOutput, outputBeats(beat(1, 0)), 0.U)
  io.memory.bits.mask := Mux(state === writeOutput, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitWeight || state === waitCore || state === waitGate || state === waitOutput

  val x = Cat(core(lane), 0.U(16.W))
  val z = Cat(gate(lane), 0.U(16.W))
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    sum -> ScalarOp.Add.U, epsilon -> ScalarOp.Add.U, root -> ScalarOp.Sqrt.U,
    inverse -> ScalarOp.Div.U, exp -> ScalarOp.ExpNegative.U,
    denominator -> ScalarOp.Add.U, sigmoidInverse -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    square -> x, sum -> accumulator, mean -> accumulator,
    inverse -> F32.lit(1), normalize -> x, weight -> weights(lane), exp -> z,
    denominator -> F32.lit(1), sigmoidInverse -> F32.lit(1), gated -> weighted))
  io.scalar.request.bits.b := MuxLookup(operation, value)(Seq(
    square -> x, mean -> F32.lit(1.0 / 128), epsilon -> F32.lit(1e-6),
    root -> 0.U, normalize -> invRms, exp -> 0.U, denominator -> exponential,
    sigmoidSign -> Mux(z(31), exponential, F32.lit(1)), activate -> z))
  io.scalar.result.ready := state === scalarWait

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }

  when(io.job.fire) {
    job := io.job.bits; head := 0.U; token := 0.U; beat := 0.U; lane := 0.U
    sequence := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val vectorBytes = j.tokens.pad(66) * (heads * 256).U
    val weightBytes = 512.U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.core, vectorBytes) || badSpan(j.gate, vectorBytes) ||
      badSpan(j.weight, weightBytes) || badSpan(j.output, vectorBytes)
    val unsafeWrites = overlap(j.output, vectorBytes, j.core, vectorBytes) ||
      overlap(j.output, vectorBytes, j.gate, vectorBytes) || overlap(j.output, vectorBytes, j.weight, weightBytes)
    when(j.tokens === 0.U || j.tokens > maxTokens.U || j.heads =/= heads.U || badAddress || unsafeWrites) {
      fail(Status.Bounds.U)
    }.otherwise { state := readWeight }
  }

  when(io.memory.fire) {
    state := MuxLookup(state, waitCore)(Seq(readWeight -> waitWeight, readGate -> waitGate, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitWeight) {
          for (i <- 0 until 16) weights(Cat(beat, i.U(4.W))) := r.data((i + 1) * 32 - 1, i * 32)
          when(beat === 7.U) { beat := 0.U; state := readCore }
            .otherwise { beat := beat + 1.U; state := readWeight }
        }
        when(state === waitCore || state === waitGate) {
          for (i <- 0 until 32) {
            val v = r.data((i + 1) * 16 - 1, i * 16)
            when(state === waitCore) { core(Cat(beat(1, 0), i.U(5.W))) := v }
              .otherwise { gate(Cat(beat(1, 0), i.U(5.W))) := v }
          }
          when(beat === 3.U) {
            beat := 0.U
            when(state === waitCore) { state := readGate }
              .otherwise { accumulator := 0.U; lane := 0.U; operation := square; state := scalarIssue }
          }.otherwise { beat := beat + 1.U; state := Mux(state === waitCore, readCore, readGate) }
        }
        when(state === waitOutput) {
          bytes := bytes + 64.U
          when(beat === 3.U) {
            beat := 0.U
            when(head + 1.U === heads.U) {
              head := 0.U
              when(token + 1.U === job.tokens) { state := finish }
                .otherwise { token := token + 1.U; state := readCore }
            }.otherwise { head := head + 1.U; state := readCore }
          }.otherwise { beat := beat + 1.U; state := writeOutput }
        }
      }
  }

  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        state := scalarIssue
        value := r
        switch(operation) {
          is(square) { operation := sum }
          is(sum) {
            accumulator := r
            when(lane === 127.U) { lane := 0.U; operation := mean }
              .otherwise { lane := lane + 1.U; operation := square }
          }
          is(mean) { operation := epsilon }
          is(epsilon) { operation := root }
          is(root) { operation := inverse }
          is(inverse) { invRms := r; operation := normalize }
          is(normalize) {
            val rounded = F32.bf(r)
            value := rounded; operation := weight
            when(!TensorMath.finite(rounded)) { fail(Status.Numerical.U) }
          }
          is(weight) {
            weighted := r; operation := exp
            when(!TensorMath.finite(z) || (z(31) && z(30, 0) >= F32.lit(80))) { fail(Status.Numerical.U) }
          }
          is(exp) { exponential := r; operation := denominator }
          is(denominator) { operation := sigmoidInverse }
          is(sigmoidInverse) { operation := sigmoidSign }
          is(sigmoidSign) { operation := activate }
          is(activate) { operation := gated }
          is(gated) {
            val rounded = TensorMath.bf16Rne(r)
            output(lane) := rounded
            when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
              .elsewhen(lane === 127.U) { beat := 0.U; state := writeOutput }
              .otherwise { lane := lane + 1.U; operation := normalize }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
