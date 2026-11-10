// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Runtime convolution keeps the original job/result ABI, with explicit scalar policy. */
class GdnRuntimeConv4OwnerRecoveredPortV7 extends Bundle {
  val job = Flipped(Decoupled(new GdnConv4Job))
  val currentGeneration = Input(UInt(32.W))
  val done = Decoupled(new GdnConv4Result)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new UnifiedScalarClientV2
  val formatRequest = Decoupled(new UnifiedRawFp32FormatRequestV3)
  val formatResult = Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
  val parentFault = Input(Bool())
  val resourcesDrained = Output(Bool())
  val resetRequired = Output(Bool())
}

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
/** Fixed common physical owner: original one32-channel group is reused for
  * runtime6144/8192 raw Q16/K16/V16|32 channels and tokens1..128. The retained
  * scheduler must derive channels from its accepted runtime profile. */
class GdnRuntimeConv4OwnerRecoveredV7 extends Module {
  val io = IO(new GdnRuntimeConv4OwnerRecoveredPortV7)

  val idle :: readWeight :: waitWeight :: readHistory :: waitHistory :: readInput :: waitInput :: scalarIssue :: scalarWait :: formatIssue :: formatWait :: writeOutput :: waitOutput :: writeHistory :: waitHistoryWrite :: finish :: report :: locked :: Nil = Enum(18)
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

  // NEW reconstruction identity: historical V6 source is unavailable. Original
  // arithmetic/cache retained; held service/drain contract follows GatedNormV10.
  val memoryAccepted = RegInit(0.U(32.W))
  val scalarAccepted = RegInit(0.U(32.W)); val scalarReturned = RegInit(0.U(32.W))
  val formatAccepted = RegInit(0.U(32.W)); val formatReturned = RegInit(0.U(32.W))
  val poison = RegInit(false.B); val quarantine = RegInit(false.B)
  val terminal = Reg(new GdnConv4Result)
  val elements = job.tokens.pad(64) * job.channels.pad(64)
  val expectedBytes = (elements << 1) + (job.channels.pad(64) << 3)
  val expectedScalar = (elements * 13.U)(31,0)
  val expectedFormat = (elements << 1)(31,0)
  val expectedMemory = ((job.channels.pad(64) >> 5) *
    (8.U + Mux(job.cold,0.U,4.U) + (job.tokens.pad(64) << 1)))(31,0)
  val memoryOffer = state === readWeight || state === readHistory || state === readInput ||
    state === writeOutput || state === writeHistory
  val memoryDebt = state === waitWeight || state === waitHistory || state === waitInput ||
    state === waitOutput || state === waitHistoryWrite
  val requestPolicy = UnifiedScalarPolicyV2.Legacy.U(2.W)
  val unknownMemory = io.response.valid && (!memoryDebt || io.response.bits.tag =/= Cat(job.tag,sequence))
  val unknownScalar = io.scalar.result.valid && (state =/= scalarWait || io.scalar.result.bits.policy =/= requestPolicy)
  val unknownFormat = io.formatResult.valid && state =/= formatWait
  val unknown = unknownMemory || unknownScalar || unknownFormat
  val currentFault = io.parentFault || unknown
  when(unknown) { quarantine := true.B }
  when(currentFault) { poison := true.B; when(state =/= report && status === Status.Ok.U) { status := Status.Protocol.U } }
  val quiet = !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid
  val noService = !memoryOffer && !memoryDebt && state =/= scalarIssue && state =/= scalarWait && state =/= formatIssue && state =/= formatWait
  io.resourcesDrained := noService && quiet && !quarantine && !unknown
  io.resetRequired := poison || quarantine || currentFault
  io.job.ready := state === idle && !poison && !currentFault && quiet
  io.done.valid := state === report
  io.done.bits := terminal

  val vectorOffset = ((token.pad(64) * job.channels) + group.pad(64)) << 1
  val historyOffset = (group.pad(64) << 3) + (beat.pad(64) << 6)
  val memoryHeld = HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || quarantine)
  io.memory.valid := memoryHeld.valid
  io.memory.bits.write := state === writeOutput || state === writeHistory
  io.memory.bits.address := MuxLookup(state, job.input + vectorOffset)(Seq(
    readWeight -> (job.weight + historyOffset), readHistory -> (job.historyIn + historyOffset),
    writeOutput -> (job.output + vectorOffset), writeHistory -> (job.historyOut + historyOffset)))
  val historyBeats = history.asUInt.asTypeOf(Vec(4, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeHistory, historyBeats(beat), Mux(state === writeOutput, output.asUInt, 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := memoryDebt && !quarantine && !unknownMemory

  val sample = Mux(tap === 3.U, raw(lane), history(lane)((tap + 1.U)(1, 0)))
  io.scalar.request.bits.policy := requestPolicy
  val scalarHeld = HeldDecoupledOffer(state === scalarIssue,io.scalar.request.ready,poison || currentFault || quarantine)
  io.scalar.request.valid := scalarHeld.valid
  io.scalar.request.bits.payload.op := MuxLookup(operation, ScalarOp.Mul.U)(Seq(
    mul -> ScalarOp.MulIeeeRne.U,
    add -> ScalarOp.Add.U, exp -> ScalarOp.ExpNegative.U,
    denom -> ScalarOp.Add.U, inverse -> ScalarOp.Div.U))
  io.scalar.request.bits.payload.a := MuxLookup(operation, value)(Seq(
    mul -> Cat(sample, 0.U(16.W)), add -> accumulator, exp -> conv,
    denom -> F32.lit(1), inverse -> F32.lit(1)))
  io.scalar.request.bits.payload.b := MuxLookup(operation, conv)(Seq(
    mul -> Cat(weights(lane)(tap), 0.U(16.W)), add -> product, exp -> 0.U,
    denom -> probability, inverse -> value,
    sign -> Mux(conv(31), probability, F32.lit(1))))
  io.scalar.result.ready := state === scalarWait && !quarantine && !unknownScalar
  val formatHeld = HeldDecoupledOffer(state === formatIssue,io.formatRequest.ready,poison || currentFault || quarantine)
  io.formatRequest.valid := formatHeld.valid
  io.formatRequest.bits.value := value
  io.formatResult.ready := state === formatWait && !quarantine && !unknownFormat
  when((poison || currentFault) && !quarantine) {
    when(memoryOffer && !memoryHeld.held && !io.memory.fire) { state := finish }
    when(state === scalarIssue && !scalarHeld.held && !io.scalar.request.fire) { state := finish }
    when(state === formatIssue && !formatHeld.held && !io.formatRequest.fire) { state := finish }
  }

  when(state =/= idle && state =/= report && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { when(status === Status.Ok.U) { status := code }; poison := true.B; state := finish }
  def beginCompute(): Unit = {
    lane := 0.U; tap := 0.U; accumulator := 0.U; operation := mul; state := scalarIssue
  }

  when(io.job.fire) {
    job := io.job.bits; group := 0.U; token := 0.U; beat := 0.U
    sequence := 0.U; status := Status.Ok.U; cycles := 0.U; bytes := 0.U
    memoryAccepted := 0.U; scalarAccepted := 0.U; scalarReturned := 0.U
    formatAccepted := 0.U; formatReturned := 0.U
    val j = io.job.bits
    val vectorBytes = (j.tokens * j.channels).pad(66) << 1
    val stateBytes = j.channels.pad(66) << 3
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
      .elsewhen(j.tokens === 0.U || j.tokens > 128.U || (j.channels =/= 6144.U && j.channels =/= 8192.U) ||
        j.expectedGeneration === "hffffffff".U || badAddress || unsafeWrites) { fail(Status.Bounds.U) }
      .elsewhen(io.response.valid || io.scalar.result.valid) { fail(Status.Protocol.U) }
      .otherwise { state := readWeight }
  }

  when(io.memory.fire) {
    memoryAccepted := memoryAccepted + 1.U
    state := MuxLookup(state, waitInput)(Seq(readWeight -> waitWeight,
      readHistory -> waitHistory, writeOutput -> waitOutput, writeHistory -> waitHistoryWrite))
  }
  when(io.response.fire) {
    val r = io.response.bits
    sequence := sequence + 1.U
    when((state === waitOutput || state === waitHistoryWrite) && !r.error) { bytes := bytes + 64.U }
    when(sequence === "hffffffff".U) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .elsewhen(poison || currentFault) { state := finish }
      .otherwise {
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
          // State stores raw QKV, never convolved/activated values.
          for (i <- 0 until 32) {
            for (t <- 0 until 3) history(i)(t) := history(i)(t + 1)
            history(i)(3) := raw(i)
          }
          when(token + 1.U === job.tokens) { beat := 0.U; state := writeHistory }
            .otherwise { token := token + 1.U; state := readInput }
        }
        when(state === waitHistoryWrite) {
          when(beat === 3.U) {
            when(group + 32.U === job.channels) { state := finish }
              .otherwise { group := group + 32.U; token := 0.U; beat := 0.U; state := readWeight }
          }.otherwise { beat := beat + 1.U; state := writeHistory }
        }
      }
  }

  when(io.scalar.request.fire) { scalarAccepted := scalarAccepted + 1.U; state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits.value
    scalarReturned := scalarReturned + 1.U
    when(io.scalar.result.bits.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .elsewhen(poison || currentFault) { state := finish }
      .otherwise {
        state := scalarIssue
        switch(operation) {
          is(mul) { product := r; operation := add }
          is(add) {
            accumulator := r
            when(tap === 3.U) {
              value := r; state := formatIssue
            }.otherwise { tap := tap + 1.U; operation := mul }
          }
          is(exp) { probability := r; operation := denom }
          is(denom) { value := r; operation := inverse }
          is(inverse) { value := r; operation := sign }
          is(sign) { value := r; operation := activate }
          is(activate) {
            value := r; state := formatIssue
          }
        }
      }
  }
  when(io.formatRequest.fire) { formatAccepted := formatAccepted + 1.U; state := formatWait }
  when(io.formatResult.fire) {
    val r = io.formatResult.bits
    formatReturned := formatReturned + 1.U
    when(r.error || r.value(14,7) === 255.U) { fail(Status.Numerical.U) }
      .elsewhen(poison || currentFault) { state := finish }
      .elsewhen(operation === add) {
        val rounded = Cat(r.value,0.U(16.W))
        conv := rounded; operation := exp; state := scalarIssue
        when(rounded(31) && rounded(30,0) >= F32.lit(80)) { fail(Status.Numerical.U) }
      }.elsewhen(operation === activate) {
        output(lane) := r.value
        when(lane === 31.U) { state := writeOutput }
          .otherwise { lane := lane + 1.U; tap := 0.U; accumulator := 0.U; operation := mul; state := scalarIssue }
      }.otherwise { fail(Status.Protocol.U) }
  }
  when(state === finish && io.resourcesDrained) {
    val exact = bytes === expectedBytes && memoryAccepted === expectedMemory && sequence === expectedMemory &&
      scalarAccepted === expectedScalar && scalarReturned === expectedScalar &&
      formatAccepted === expectedFormat && formatReturned === expectedFormat
    val complete = status === Status.Ok.U && !poison && !currentFault && exact
    terminal.tag := job.tag; terminal.writeBytes := bytes; terminal.cycles := cycles
    terminal.status := Mux(status === Status.Ok.U && (!exact || poison || currentFault),Status.Protocol.U,status)
    terminal.historyCommitted := complete
    terminal.generation := job.expectedGeneration + Mux(complete,1.U,0.U)
    when(status === Status.Ok.U && !exact) { poison := true.B }
    state := report
  }
  when(io.done.fire) { state := Mux(io.resetRequired || terminal.status =/= Status.Ok.U,locked,idle) }
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid,io.formatRequest.valid)) <= 1.U)
}
