// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal M1 producer bridge, not a public Host descriptor. The three inputs
  * are separate pointers into Conv4's BF16 [Q heads, K heads, V heads] row.
  * AB is the single Dense32 BF16 beat [A0..A15,B0..B15], dtBias is
  * BF16 [heads], and ALog is original FP32 [heads]. These three spans must
  * each have a readable 64-byte beat (dtBias padded).
  * Output vectors are FP32 [heads,128], gates are 64 bytes/head: {g,beta,0x14}.
  * All four outputs are unpublished, disjoint staging allocations.
  * recurrentMode is true ONLY for an existing-cache single-token decode; cold
  * M1 uses the chunk path. This owner does not implement an M128 prefill path.
  */
class GdnInputPrepJob extends Bundle {
  val tokens = UInt(16.W)
  val heads = UInt(16.W)
  val queryIn = UInt(64.W)
  val keyIn = UInt(64.W)
  val valueIn = UInt(64.W)
  val ab = UInt(64.W)
  val aLog = UInt(64.W)
  val dtBias = UInt(64.W)
  val query = UInt(64.W)
  val key = UInt(64.W)
  val value = UInt(64.W)
  val gates = UInt(64.W)
  val recurrentMode = Bool()
  val tag = UInt(32.W)
}
class GdnInputPrepResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
}
class GdnInputPrepOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new GdnInputPrepJob))
  val done = Decoupled(new GdnInputPrepResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}

/** No arithmetic service is instantiated here: every operation is sent to the
  * one external shared BlockScalarFloat. Softplus is shared opcode 7; the
  * owner intentionally fails closed if the service does not implement it.
  *
  * Q/K: BF16 expand, separate FP32 squares and ascending sum, +1e-6, sqrt,
  * reciprocal, multiply. Q then multiplies FP32(128^-0.5) on the chunk path or
  * divides by FP32(sqrt(128)) on the recurrent path. This fixed hardware recipe
  * is separately checked against official torch rsqrt/reduction semantics.
  * V only widens. Beta uses sigmoid followed by BF16 RNE THEN FP32 expansion.
  * g = -exp(original FP32 A_log) * softplus(FP32(a) + FP32(BF16 dt_bias)).
  * exp(A_log) uses the shared exp(-abs(x)) and reciprocal for positive x.
  * The accepted exp domain is |A_log|<80, b>-80, and -80<g<=0. No domain
  * saturation or quantization of the raw recurrent state is hidden here.
  *
  * Tags, memory and scalar requests and completion are stable under stalls.
  * Output publication waits for the last gate ACK. Any failure locks until
  * reset; reset must also reset/drain the shared service and transport.
  */
class GdnInputPrepOwner(heads: Int = 16) extends Module {
  require(heads > 0 && heads <= 16)
  val io = IO(new GdnInputPrepOwnerPort)
  val idle :: readParam :: waitParam :: readVector :: waitVector :: issue :: waitScalar :: writeVector :: waitWrite :: writeGate :: waitGate :: finish :: locked :: Nil = Enum(13)
  val square :: sum :: epsilon :: root :: inverse :: normalize :: scaleQuery :: biasAdd :: softplus :: aExp :: aInverse :: logDecay :: betaExp :: betaDenominator :: betaInverse :: betaSign :: Nil = Enum(16)
  val state = RegInit(idle)
  val operation = RegInit(square)
  val job = Reg(new GdnInputPrepJob)
  val parameters = Reg(Vec(4, Vec(16, UInt(32.W))))
  val input = Reg(Vec(128, UInt(16.W)))
  val output = Reg(Vec(128, UInt(32.W)))
  val param = RegInit(0.U(2.W))
  val role = RegInit(0.U(2.W)) // Q, K, V
  val head = RegInit(0.U(4.W))
  val beat = RegInit(0.U(3.W))
  val lane = RegInit(0.U(7.W))
  val sequence = RegInit(0.U(32.W))
  val accumulator = RegInit(0.U(32.W))
  val temporary = Reg(UInt(32.W))
  val inverseNorm = Reg(UInt(32.W))
  val positive = Reg(UInt(32.W))
  val exponential = Reg(UInt(32.W))
  val g = Reg(UInt(32.W))
  val beta = Reg(UInt(32.W))
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

  val inputBase = MuxLookup(role, job.queryIn)(Seq(1.U -> job.keyIn, 2.U -> job.valueIn))
  val outputBase = MuxLookup(role, job.query)(Seq(1.U -> job.key, 2.U -> job.value))
  val paramBase = MuxLookup(param, job.ab)(Seq(1.U -> job.aLog, 2.U -> job.dtBias))
  io.memory.valid := state === readParam || state === readVector || state === writeVector || state === writeGate
  io.memory.bits.write := state === writeVector || state === writeGate
  io.memory.bits.address := MuxLookup(state, inputBase + (head.pad(64) << 8) + (beat.pad(64) << 6))(Seq(
    readParam -> paramBase,
    writeVector -> (outputBase + (head.pad(64) << 9) + (beat.pad(64) << 6)),
    writeGate -> (job.gates + (head.pad(64) << 6))))
  val outputBeats = output.asUInt.asTypeOf(Vec(8, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeGate, Cat(0.U(448.W), beta, g), Mux(state === writeVector, outputBeats(beat), 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitParam || state === waitVector || state === waitWrite || state === waitGate

  val x = Cat(input(lane), 0.U(16.W))
  val a = parameters(0)(head)
  val b = parameters(1)(head)
  val aLog = parameters(2)(head)
  val bias = parameters(3)(head)
  io.scalar.request.valid := state === issue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    sum -> ScalarOp.Add.U, epsilon -> ScalarOp.Add.U, root -> ScalarOp.Sqrt.U,
    inverse -> ScalarOp.Div.U, scaleQuery -> Mux(job.recurrentMode, ScalarOp.Div.U, ScalarOp.MulIeeeRne.U),
    biasAdd -> ScalarOp.Add.U, softplus -> ScalarOp.Softplus.U, aExp -> ScalarOp.ExpNegative.U,
    aInverse -> ScalarOp.Div.U, betaExp -> ScalarOp.ExpNegative.U,
    betaDenominator -> ScalarOp.Add.U, betaInverse -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, temporary)(Seq(
    square -> x, sum -> accumulator, inverse -> F32.lit(1), normalize -> x,
    biasAdd -> a, aExp -> aLog, aInverse -> F32.lit(1),
    logDecay -> F32.neg(temporary), betaExp -> b, betaDenominator -> F32.lit(1), betaInverse -> F32.lit(1)))
  io.scalar.request.bits.b := MuxLookup(operation, temporary)(Seq(
    square -> x, epsilon -> F32.lit(1e-6), root -> 0.U, normalize -> inverseNorm,
    scaleQuery -> Mux(job.recurrentMode, F32.lit(math.sqrt(128)), F32.lit(1 / math.sqrt(128))),
    biasAdd -> bias, softplus -> 0.U, aExp -> 0.U, logDecay -> positive,
    betaExp -> 0.U, betaDenominator -> exponential, betaSign -> Mux(b(31), exponential, F32.lit(1))))
  io.scalar.result.ready := state === waitScalar
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }

  when(io.job.fire) {
    job := io.job.bits; param := 0.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U
    sequence := 0.U; accumulator := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val reads = Seq((j.queryIn, heads * 256), (j.keyIn, heads * 256), (j.valueIn, heads * 256),
      (j.ab, 64), (j.aLog, 64), (j.dtBias, 64))
    val writes = Seq((j.query, heads * 512), (j.key, heads * 512), (j.value, heads * 512), (j.gates, heads * 64))
    def overlap(a: (UInt, Int), b: (UInt, Int)): Bool =
      a._1.pad(66) < b._1.pad(66) + b._2.U && b._1.pad(66) < a._1.pad(66) + a._2.U
    val badAddress = (reads ++ writes).map { case (base, size) =>
      base(5, 0) =/= 0.U || base.pad(66) + size.U > (BigInt(1) << 56).U }.reduce(_ || _)
    val badOverlap = (for (w <- writes; r <- reads) yield overlap(w, r)).reduce(_ || _) ||
      (for (i <- writes.indices; k <- 0 until i) yield overlap(writes(i), writes(k))).reduce(_ || _)
    when(j.tokens =/= 1.U || j.heads =/= heads.U || badAddress || badOverlap) { fail(Status.Bounds.U) }
      .otherwise { state := readParam }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitVector)(Seq(readParam -> waitParam, writeVector -> waitWrite, writeGate -> waitGate))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitParam) {
          for (i <- 0 until 16) {
            when(param === 0.U) {
              parameters(0)(i) := Cat(r.data((i + 1) * 16 - 1, i * 16), 0.U(16.W))
              parameters(1)(i) := Cat(r.data((i + 17) * 16 - 1, (i + 16) * 16), 0.U(16.W))
            }.elsewhen(param === 1.U) { parameters(2)(i) := r.data((i + 1) * 32 - 1, i * 32) }
              .otherwise { parameters(3)(i) := Cat(r.data((i + 1) * 16 - 1, i * 16), 0.U(16.W)) }
          }
          when(param === 2.U) { beat := 0.U; state := readVector }
            .otherwise { param := param + 1.U; state := readParam }
        }
        when(state === waitVector) {
          val invalid = Wire(Vec(32, Bool()))
          for (i <- 0 until 32) {
            val v = r.data((i + 1) * 16 - 1, i * 16)
            input(Cat(beat(1, 0), i.U(5.W))) := v
            when(role === 2.U) { output(Cat(beat(1, 0), i.U(5.W))) := Cat(v, 0.U(16.W)) }
            invalid(i) := v(14, 7) === 255.U
          }
          when(invalid.asUInt.orR) { fail(Status.Numerical.U) }
            .elsewhen(beat === 3.U) {
              beat := 0.U; lane := 0.U; accumulator := 0.U; operation := square
              state := Mux(role === 2.U, writeVector, issue)
            }.otherwise { beat := beat + 1.U; state := readVector }
        }
        when(state === waitWrite) {
          bytes := bytes + 64.U
          when(beat === 7.U) {
            beat := 0.U
            when(role === 2.U) {
              when(!TensorMath.finite(aLog) || aLog(30, 0) >= F32.lit(80) ||
                !TensorMath.finite(b) || (b(31) && b(30, 0) >= F32.lit(80))) { fail(Status.Numerical.U) }
                .otherwise { operation := biasAdd; state := issue }
            }.otherwise { role := role + 1.U; state := readVector }
          }.otherwise { beat := beat + 1.U; state := writeVector }
        }
        when(state === waitGate) {
          bytes := bytes + 64.U
          when(head === (heads - 1).U) { state := finish }
            .otherwise { head := head + 1.U; role := 0.U; beat := 0.U; state := readVector }
        }
      }
  }
  when(io.scalar.request.fire) { state := waitScalar }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(io.scalar.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
      .otherwise {
        temporary := r; state := issue
        switch(operation) {
          is(square) { operation := sum }
          is(sum) {
            accumulator := r
            when(lane === 127.U) { lane := 0.U; operation := epsilon }
              .otherwise { lane := lane + 1.U; operation := square }
          }
          is(epsilon) { operation := root }
          is(root) { operation := inverse }
          is(inverse) { inverseNorm := r; operation := normalize }
          is(normalize) {
            when(role === 0.U) { operation := scaleQuery }
              .otherwise {
                output(lane) := r
                when(lane === 127.U) { beat := 0.U; state := writeVector }
                  .otherwise { lane := lane + 1.U; operation := normalize }
              }
          }
          is(scaleQuery) {
            output(lane) := r
            when(lane === 127.U) { beat := 0.U; state := writeVector }
              .otherwise { lane := lane + 1.U; operation := normalize }
          }
          is(biasAdd) { operation := softplus }
          is(softplus) {
            when(r(31)) { fail(Status.Numerical.U) }
              .otherwise { positive := r; operation := aExp }
          }
          is(aExp) { operation := Mux(aLog(31), logDecay, aInverse) }
          is(aInverse) { operation := logDecay }
          is(logDecay) {
            when((!r(31) && r(30, 0).orR) || r(30, 0) >= F32.lit(80)) { fail(Status.Numerical.U) }
              .otherwise { g := r; operation := betaExp }
          }
          is(betaExp) { exponential := r; operation := betaDenominator }
          is(betaDenominator) { operation := betaInverse }
          is(betaInverse) { operation := betaSign }
          is(betaSign) {
            beta := F32.bf(r)
            when(r(31) || F32.less(F32.lit(1), r)) { fail(Status.Numerical.U) }
              .otherwise { state := writeGate }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
