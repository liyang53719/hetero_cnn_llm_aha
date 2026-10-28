// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal typed job. Input/output are BF16 [tokens,width]; the original
  * zero-centered layernorm weight is BF16 [width]. The public decoder checks
  * dtype before creating this job. Output is a disjoint staging allocation.
  */
class GdnRmsNormJob extends Bundle {
  val tokens = UInt(16.W)
  val hiddenWidth = UInt(16.W)
  val input = UInt(64.W)
  val weight = UInt(64.W)
  val output = UInt(64.W)
  val tag = UInt(32.W)
}

class GdnRmsNormResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
}

class GdnRmsNormOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnRmsNormJob))
  val done = Decoupled(new GdnRmsNormResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}

/** Pinned Qwen3.5 input/post-attention RMSNorm, with external shared Scalar.
  * No arithmetic engine, Matrix or iDMA is instantiated by this owner.
  *
  * Official nodes: x.float(); x.pow(2).mean(-1)+1e-6; rsqrt; multiply by x;
  * multiply by (1+original BF16 weight.float()); cast once to BF16.
  * Frozen hardware recipe: individual FP32 IEEE-RNE squares, ascending FP32
  * additions from +0, FP32 multiply by 1/width, FP32 epsilon addition, FP32
  * sqrt then FP32 reciprocal, FP32 normalize, FP32 1+weight, FP32 multiply,
  * final BF16 RNE. No intermediate BF16 cast or fused operations are allowed.
  * Ascending reduction and sqrt+reciprocal are not claims of torch bit parity;
  * native same-input results are diagnostics without a stage-specific bound.
  *
  * One row and the shared weights are retained locally. The final write ACK
  * fences publication. Errors may leave staging bytes but never commit output,
  * and lock further jobs until reset. Reset must also reset/drain the external
  * shared Scalar and memory transport. There is no persistent model state.
  */
class GdnRmsNormOwner(width: Int = 1024, maxTokens: Int = 128) extends Module {
  require(width >= 32 && width <= 65535 && isPow2(width))
  require(maxTokens > 0 && maxTokens <= 65535)
  val io = IO(new GdnRmsNormOwnerPort)
  private val rowBeats = width / 32
  private val laneBits = log2Ceil(width)
  private val beatBits = math.max(1, log2Ceil(rowBeats))
  val idle :: readWeight :: waitWeight :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeOutput :: waitOutput :: finish :: locked :: Nil = Enum(11)
  val state = RegInit(idle)
  val square :: sum :: mean :: epsilon :: root :: inverse :: normalize :: offset :: weighted :: Nil = Enum(9)
  val operation = RegInit(square)
  val job = Reg(new GdnRmsNormJob)
  val weights = Reg(Vec(rowBeats, UInt(512.W)))
  val input = Reg(Vec(rowBeats, UInt(512.W)))
  val output = Reg(Vec(width, UInt(16.W)))
  val token = RegInit(0.U(16.W))
  val beat = RegInit(0.U(beatBits.W))
  val lane = RegInit(0.U(laneBits.W))
  val accumulator = RegInit(0.U(32.W))
  val value = Reg(UInt(32.W))
  val invRms = Reg(UInt(32.W))
  val normalized = Reg(UInt(32.W))
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

  val rowOffset = token.pad(64) * (width * 2).U
  val beatOffset = beat.pad(64) << 6
  io.memory.valid := state === readWeight || state === readInput || state === writeOutput
  io.memory.bits.write := state === writeOutput
  io.memory.bits.address := MuxLookup(state, job.input + rowOffset + beatOffset)(Seq(
    readWeight -> (job.weight + beatOffset), writeOutput -> (job.output + rowOffset + beatOffset)))
  val outputBeats = output.asUInt.asTypeOf(Vec(rowBeats, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeOutput, outputBeats(beat), 0.U)
  io.memory.bits.mask := Mux(state === writeOutput, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitWeight || state === waitInput || state === waitOutput

  // Packed aligned beats make each memory return one local write, avoiding
  // an accidental 32-write-port register array at the real 1024 geometry.
  val laneBeat = if (rowBeats == 1) 0.U else lane(laneBits - 1, 5)
  val inputLanes = input(laneBeat).asTypeOf(Vec(32, UInt(16.W)))
  val weightLanes = weights(laneBeat).asTypeOf(Vec(32, UInt(16.W)))
  val x = Cat(inputLanes(lane(4, 0)), 0.U(16.W))
  val w = Cat(weightLanes(lane(4, 0)), 0.U(16.W))
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    sum -> ScalarOp.Add.U, epsilon -> ScalarOp.Add.U, root -> ScalarOp.Sqrt.U,
    inverse -> ScalarOp.Div.U, offset -> ScalarOp.Add.U))
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    square -> x, sum -> accumulator, mean -> accumulator,
    inverse -> F32.lit(1), normalize -> x, offset -> F32.lit(1), weighted -> normalized))
  io.scalar.request.bits.b := MuxLookup(operation, value)(Seq(
    square -> x, mean -> F32.lit(1.0 / width), epsilon -> F32.lit(1e-6),
    root -> 0.U, normalize -> invRms, offset -> w))
  io.scalar.result.ready := state === scalarWait

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  when(io.job.fire) {
    job := io.job.bits; token := 0.U; beat := 0.U; lane := 0.U
    sequence := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val vectorBytes = j.tokens.pad(66) * (width * 2).U
    val weightBytes = (width * 2).U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, vectorBytes) || badSpan(j.weight, weightBytes) || badSpan(j.output, vectorBytes)
    val unsafeWrites = overlap(j.output, vectorBytes, j.input, vectorBytes) ||
      overlap(j.output, vectorBytes, j.weight, weightBytes)
    when(j.tokens === 0.U || j.tokens > maxTokens.U || j.hiddenWidth =/= width.U || badAddress || unsafeWrites) {
      fail(Status.Bounds.U)
    }.otherwise { state := readWeight }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitInput)(Seq(readWeight -> waitWeight, writeOutput -> waitOutput))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitWeight || state === waitInput) {
          val nonfinite = (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
          when(state === waitWeight) { weights(beat) := r.data }.otherwise { input(beat) := r.data }
          when(nonfinite) { fail(Status.Numerical.U) }
            .elsewhen(beat === (rowBeats - 1).U) {
              beat := 0.U
              when(state === waitWeight) { state := readInput }
                .otherwise { accumulator := 0.U; lane := 0.U; operation := square; state := scalarIssue }
            }.otherwise { beat := beat + 1.U; state := Mux(state === waitWeight, readWeight, readInput) }
        }
        when(state === waitOutput) {
          bytes := bytes + 64.U
          when(beat === (rowBeats - 1).U) {
            beat := 0.U
            when(token + 1.U === job.tokens) { state := finish }
              .otherwise { token := token + 1.U; state := readInput }
          }.otherwise { beat := beat + 1.U; state := writeOutput }
        }
      }
  }
  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        state := scalarIssue; value := r
        switch(operation) {
          is(square) { operation := sum }
          is(sum) {
            accumulator := r
            when(lane === (width - 1).U) { lane := 0.U; operation := mean }
              .otherwise { lane := lane + 1.U; operation := square }
          }
          is(mean) { operation := epsilon }
          is(epsilon) { operation := root }
          is(root) { operation := inverse }
          is(inverse) { invRms := r; operation := normalize }
          is(normalize) { normalized := r; operation := offset }
          is(offset) { operation := weighted }
          is(weighted) {
            val rounded = TensorMath.bf16Rne(r)
            output(lane) := rounded
            when(rounded(14, 7) === 255.U) { fail(Status.Numerical.U) }
              .elsewhen(lane === (width - 1).U) { beat := 0.U; state := writeOutput }
              .otherwise { lane := lane + 1.U; operation := normalize }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
