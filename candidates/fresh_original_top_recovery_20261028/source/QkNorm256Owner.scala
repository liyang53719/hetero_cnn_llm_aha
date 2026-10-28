// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Q is [token,qHead,Q256+gate256], K is [token,kvHead,K256].
  * Original BF16 weights [256] are shared across heads. Output and the separate
  * Q gate output are contiguous [token,head,256] BF16 staging allocations.
  */
class QkNorm256Job extends Bundle {
  val tokens = UInt(16.W)
  val role = UInt(2.W)
  val headDim = UInt(16.W)
  val policy = UInt(8.W)
  val epsilon = UInt(32.W)
  val input = UInt(64.W)
  val weight = UInt(64.W)
  val output = UInt(64.W)
  val gateOutput = UInt(64.W)
  val tag = UInt(32.W)
}

class QkNorm256Result extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
  // Frozen candidate statuses: 0 OK, 1 descriptor, 2 nonfinite operand,
  // 3 unsupported finite operand range, 4 arithmetic/domain failure.
  // A transport failure is carried by status and leaves normStatus unchanged.
  val normStatus = UInt(4.W)
  val exceptionFlags = UInt(5.W)
  val lastMeanEps = UInt(32.W)
  val lastInverse = UInt(32.W)
}

class QkNorm256OwnerPort extends Bundle {
  val job = Flipped(Decoupled(new QkNorm256Job))
  val done = Decoupled(new QkNorm256Result)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  // Raw flags of the same accepted Add0/Mul1 result, stable with that result.
  val scalarFlags = Input(UInt(5.W))
  val scalarFlagsValid = Input(Bool())
  val resetRequired = Output(Bool())
}

/** Serialized owner of the frozen qk_norm256_bf16_candidate recipe.
  * It instantiates no Scalar, Matrix, SFU or DMA arithmetic. Each square, tree
  * edge, running addition, mean/epsilon, PWL/Newton node and output node is one
  * request to the existing shared BlockScalarFloat, using only Add0 and Mul1.
  *
  * The 16 squares of each chunk feed its balanced 8/4/2/1 addition tree; the
  * 16 roots are accumulated in chunk order from +0. The rsqrt ROM and eight
  * individually rounded nodes below are literal fp32_rsqrt_nr.sv semantics.
  * No sqrt, divide, FMA, reassociation, intermediate BF16 cast or new threshold
  * is substituted. Gamma is FP32(1 + original BF16 weight).
  *
  * Only signed zeros and BF16 exponents 95..158 are arithmetic operands.
  * Nonfinite rejection takes priority over finite range rejection per head,
  * including its weights. Q gates are opaque 16-bit payloads, never operands.
  * Actual Scalar flags and destination BF16 conversion flags are ORed for the
  * job. A runtime fault retains observed flags and uncommitted staging writes.
  * All norm AND gate write ACKs fence commit. Any failure locks until the same
  * reset also resets/drains the shared Scalar and memory transport.
  */
class QkNorm256Owner(qHeads: Int = 8, kvHeads: Int = 2, maxTokens: Int = 128) extends Module {
  require(qHeads > 0 && qHeads <= 65535 && kvHeads > 0 && kvHeads <= 65535)
  require(maxTokens > 0 && maxTokens <= 65535)
  val io = IO(new QkNorm256OwnerPort)
  val idle :: readWeight :: waitWeight :: readInput :: waitInput :: scalarIssue :: scalarWait :: writeNorm :: waitNorm :: writeGate :: waitGate :: finish :: locked :: Nil = Enum(13)
  val state = RegInit(idle)
  val square :: tree :: running :: mean :: epsilon :: slope :: intercept :: seedSquare :: normProduct :: half :: correction :: newton :: rescale :: gamma :: normalize :: weighted :: Nil = Enum(16)
  val operation = RegInit(square)
  val job = Reg(new QkNorm256Job)
  val weights = Reg(Vec(8, UInt(512.W)))
  val input = Reg(Vec(8, UInt(512.W)))
  val gates = Reg(Vec(8, UInt(512.W)))
  val output = Reg(Vec(256, UInt(16.W)))
  val treeValues = Reg(Vec(16, UInt(32.W)))
  val treeIndex = RegInit(0.U(4.W))
  val treeCount = RegInit(8.U(4.W))
  val token = RegInit(0.U(16.W))
  val head = RegInit(0.U(16.W))
  val beat = RegInit(0.U(4.W))
  val lane = RegInit(0.U(8.W))
  val accumulator = RegInit(0.U(32.W))
  val value = Reg(UInt(32.W))
  val seed = Reg(UInt(32.W))
  val norm = Reg(UInt(32.W))
  val scale = Reg(UInt(32.W))
  val coefficient = Reg(UInt(64.W))
  val invRms = Reg(UInt(32.W))
  val laneGamma = Reg(UInt(32.W))
  val weightNonfinite = RegInit(false.B)
  val weightRange = RegInit(false.B)
  val headNonfinite = RegInit(false.B)
  val headRange = RegInit(false.B)
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val normStatus = RegInit(0.U(4.W))
  val exceptionFlags = RegInit(0.U(5.W))
  val lastMeanEps = RegInit(0.U(32.W))
  val lastInverse = RegInit(0.U(32.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U
  io.done.bits.normStatus := normStatus
  io.done.bits.exceptionFlags := exceptionFlags
  io.done.bits.lastMeanEps := lastMeanEps
  io.done.bits.lastInverse := lastInverse
  io.resetRequired := status =/= Status.Ok.U

  val heads = Mux(job.role === 0.U, qHeads.U(16.W), kvHeads.U(16.W))
  val row = token.pad(64) * heads + head
  val normOffset = row << 9
  val inputOffset = Mux(job.role === 0.U, row << 10, normOffset)
  val beatOffset = beat.pad(64) << 6
  io.memory.valid := state === readWeight || state === readInput || state === writeNorm || state === writeGate
  io.memory.bits.write := state === writeNorm || state === writeGate
  io.memory.bits.address := MuxLookup(state, job.input + inputOffset + beatOffset)(Seq(
    readWeight -> (job.weight + beatOffset),
    writeNorm -> (job.output + normOffset + beatOffset),
    writeGate -> (job.gateOutput + normOffset + beatOffset)))
  val outputBeats = output.asUInt.asTypeOf(Vec(8, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeNorm, outputBeats(beat(2, 0)), Mux(state === writeGate, gates(beat(2, 0)), 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitWeight || state === waitInput || state === waitNorm || state === waitGate

  val inputLanes = input(lane(7, 5)).asTypeOf(Vec(32, UInt(16.W)))
  val weightLanes = weights(lane(7, 5)).asTypeOf(Vec(32, UInt(16.W)))
  val x = Cat(inputLanes(lane(4, 0)), 0.U(16.W))
  val w = Cat(weightLanes(lane(4, 0)), 0.U(16.W))
  val treeLeft = Cat(treeIndex(2, 0), 0.U(1.W))
  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := Mux(operation === tree || operation === running || operation === epsilon ||
    operation === intercept || operation === correction || operation === gamma, ScalarOp.Add.U, ScalarOp.Mul.U)
  io.scalar.request.bits.a := MuxLookup(operation, value)(Seq(
    square -> x, tree -> treeValues(treeLeft), running -> accumulator, mean -> accumulator,
    slope -> coefficient(63, 32), normProduct -> norm, half -> "h3f000000".U,
    correction -> "h3fc00000".U, newton -> seed, gamma -> "h3f800000".U,
    normalize -> x))
  io.scalar.request.bits.b := MuxLookup(operation, value)(Seq(
    square -> x, tree -> treeValues(treeLeft + 1.U), mean -> "h3b800000".U,
    epsilon -> "h358637bd".U, slope -> norm, intercept -> coefficient(31, 0),
    correction -> (value ^ "h80000000".U), rescale -> scale, gamma -> w,
    normalize -> invRms, weighted -> laneGamma))
  io.scalar.result.ready := state === scalarWait

  val rsqrtCoefficients = VecInit(Seq(
    "bef497b73fbd25ee", "bedfea6b3fb7a7e6", "becdff353fb29dbe", "bebe58e33fadf85e",
    "beb0956f3fa9ab4a", "bea4671b3fa5ac16", "be998f8e3fa1f1fe", "be8fdc3f3f9e758d",
    "be8723d63f9b3066", "be7e88713f981d0c", "be7042093f9536bf", "be6344ec3f92795b",
    "be5769013f8fe140", "be4c8c3f3f8d6b3c", "be42919b3f8b147d", "be3960253f88da83",
    "be2cf3ff3f85bf79", "be1e55123f81dd42", "be11a96c3f7c99f7", "be0698873f7607ef",
    "bdf9ba233f6ff2c6", "bde880283f6a4bc0", "bdd92aee3f650674", "bdcb73013f60185b",
    "bdbf1de73f5b7871", "bdb3fb643f571ef6", "bda9e3563f530530", "bda0b4203f4f2545",
    "bd9851683f4b7a15", "bd90a31d3f47ff1b", "bd8994b63f44b05a", "bd8314903f418a48"
  ).map(h => BigInt(h, 16).U(64.W)))

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  def rejectNorm(code: UInt): Unit = { normStatus := code; fail(Status.Numerical.U) }
  when(io.job.fire) {
    job := io.job.bits; token := 0.U; head := 0.U; beat := 0.U; lane := 0.U
    sequence := 0.U; status := Status.Ok.U; normStatus := 0.U; bytes := 0.U; cycles := 0.U
    exceptionFlags := 0.U; lastMeanEps := 0.U; lastInverse := 0.U
    weightNonfinite := false.B; weightRange := false.B; headNonfinite := false.B; headRange := false.B
    val j = io.job.bits
    val count = Mux(j.role === 0.U, qHeads.U, kvHeads.U)
    val vectorBytes = (j.tokens.pad(66) * count) << 9
    val inputBytes = Mux(j.role === 0.U, vectorBytes << 1, vectorBytes)
    val weightBytes = 512.U(66.W)
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(66) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = badSpan(j.input, inputBytes) || badSpan(j.weight, weightBytes) || badSpan(j.output, vectorBytes) ||
      Mux(j.role === 0.U, badSpan(j.gateOutput, vectorBytes), j.gateOutput =/= 0.U)
    val unsafeNorm = overlap(j.output, vectorBytes, j.input, inputBytes) || overlap(j.output, vectorBytes, j.weight, weightBytes)
    val unsafeGate = j.role === 0.U && (overlap(j.gateOutput, vectorBytes, j.input, inputBytes) ||
      overlap(j.gateOutput, vectorBytes, j.weight, weightBytes) || overlap(j.gateOutput, vectorBytes, j.output, vectorBytes))
    when(j.tokens === 0.U || j.tokens > maxTokens.U || j.role > 1.U || j.headDim =/= 256.U ||
      j.policy =/= "hc1".U || j.epsilon =/= "h358637bd".U || badAddress || unsafeNorm || unsafeGate) {
      normStatus := 1.U; fail(Status.Bounds.U)
    }.otherwise { state := readWeight }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitInput)(Seq(readWeight -> waitWeight, writeNorm -> waitNorm, writeGate -> waitGate))
  }
  def nextHead(): Unit = {
    beat := 0.U
    when(head + 1.U === heads) {
      head := 0.U
      when(token + 1.U === job.tokens) { state := finish }
        .otherwise { token := token + 1.U; state := readInput }
    }.otherwise { head := head + 1.U; state := readInput }
    headNonfinite := weightNonfinite; headRange := weightRange
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        val arithmeticBeat = state === waitWeight || (state === waitInput && !beat(3))
        val nonfinite = arithmeticBeat && (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
        val outOfRange = arithmeticBeat && (0 until 32).map { i =>
          val v = r.data(i * 16 + 15, i * 16)
          v(14, 0) =/= 0.U && (v(14, 7) < 95.U || v(14, 7) > 158.U)
        }.reduce(_ || _)
        when(state === waitWeight) {
          weights(beat(2, 0)) := r.data
          weightNonfinite := weightNonfinite || nonfinite; weightRange := weightRange || outOfRange
          when(beat === 7.U) {
            beat := 0.U; state := readInput
            headNonfinite := weightNonfinite || nonfinite; headRange := weightRange || outOfRange
          }.otherwise { beat := beat + 1.U; state := readWeight }
        }
        when(state === waitInput) {
          when(beat(3)) { gates(beat(2, 0)) := r.data }.otherwise { input(beat(2, 0)) := r.data }
          headNonfinite := headNonfinite || nonfinite; headRange := headRange || outOfRange
          when(beat === Mux(job.role === 0.U, 15.U, 7.U)) {
            beat := 0.U
            when(headNonfinite || nonfinite) { rejectNorm(2.U) }
              .elsewhen(headRange || outOfRange) { rejectNorm(3.U) }
              .otherwise { accumulator := 0.U; lane := 0.U; operation := square; state := scalarIssue }
          }.otherwise { beat := beat + 1.U; state := readInput }
        }
        when(state === waitNorm || state === waitGate) {
          bytes := bytes + 64.U
          when(beat === 7.U) {
            when(state === waitNorm && job.role === 0.U) { beat := 0.U; state := writeGate }
              .otherwise { nextHead() }
          }.otherwise { beat := beat + 1.U; state := Mux(state === waitNorm, writeNorm, writeGate) }
        }
      }
  }
  when(io.scalar.request.fire) { state := scalarWait }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits
    when(!io.scalarFlagsValid) { fail(Status.Protocol.U) }
      .otherwise {
        exceptionFlags := exceptionFlags | io.scalarFlags
        when(io.scalar.error || io.scalarFlags(4, 1).orR || !TensorMath.finite(r)) { rejectNorm(4.U) }
          .otherwise {
            state := scalarIssue; value := r
            switch(operation) {
              is(square) {
                treeValues(lane(3, 0)) := r
                when(lane(3, 0) === 15.U) { treeIndex := 0.U; treeCount := 8.U; operation := tree }
                  .otherwise { lane := lane + 1.U }
              }
              is(tree) {
                treeValues(treeIndex) := r
                when(treeIndex + 1.U === treeCount) {
                  treeIndex := 0.U; treeCount := treeCount >> 1
                  when(treeCount === 1.U) { operation := running }
                }.otherwise { treeIndex := treeIndex + 1.U }
              }
              is(running) {
                accumulator := r
                when(lane === 255.U) { lane := 0.U; operation := mean }
                  .otherwise { lane := lane + 1.U; operation := square }
              }
              is(mean) { operation := epsilon }
              is(epsilon) {
                lastMeanEps := r
                when(r(31) || r(30, 23) < 2.U || r(30, 23) > 253.U) { rejectNorm(4.U) }
                  .otherwise {
                    val exponent = r(30, 23).zext - 127.S(10.W)
                    val odd = exponent(0)
                    val evenExponent = exponent - odd.asUInt.zext
                    val scaleExponent = 127.S(10.W) - (evenExponent >> 1)
                    norm := Cat(0.U(1.W), Mux(odd, 128.U(8.W), 127.U(8.W)), r(22, 0))
                    scale := Cat(0.U(1.W), scaleExponent.asUInt(7, 0), 0.U(23.W))
                    coefficient := rsqrtCoefficients(Cat(odd, r(22, 19)))
                    operation := slope
                  }
              }
              is(slope) { operation := intercept }
              is(intercept) { seed := r; operation := seedSquare }
              is(seedSquare) { operation := normProduct }
              is(normProduct) { operation := half }
              is(half) { operation := correction }
              is(correction) { operation := newton }
              is(newton) { operation := rescale }
              is(rescale) {
                lastInverse := r; invRms := r; operation := gamma
                when(r(31) || r(30, 23) === 0.U || r(30, 23) === 255.U) { rejectNorm(4.U) }
              }
              is(gamma) { laneGamma := r; operation := normalize }
              is(normalize) { operation := weighted }
              is(weighted) {
                // Exact fp32_to_bf16_rne_candidate finite-input conversion.
                val discarded = r(15, 0).orR
                val increment = r(15) && (r(14, 0).orR || r(16))
                val rounded = r(31, 16) + increment
                val overflow = rounded(14, 7) === 255.U
                val underflow = discarded && rounded(14, 7) === 0.U
                val conversionFlags = Cat(0.U(2.W), overflow, underflow && !overflow, discarded || overflow)
                exceptionFlags := exceptionFlags | io.scalarFlags | conversionFlags
                output(lane) := rounded
                when(overflow || underflow) { rejectNorm(4.U) }
                  .elsewhen(lane === 255.U) { beat := 0.U; state := writeNorm }
                  .otherwise { lane := lane + 1.U; operation := gamma }
              }
            }
          }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
