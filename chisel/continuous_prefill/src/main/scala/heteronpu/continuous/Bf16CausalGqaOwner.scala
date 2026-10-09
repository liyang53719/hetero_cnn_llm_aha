// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal attention core job; no public Host encoding. Q/output are BF16
  * [tokens,8,256]. Combined cache is BF16 [2,capacityTokens,512], K then V.
  * Host supplies trusted staged cache metadata and owns whole-block publish.
  */
class Bf16CausalGqaJob extends Bundle {
  val tokens = UInt(16.W)
  val queryHeads = UInt(16.W)
  val kvHeads = UInt(16.W)
  val headDim = UInt(16.W)
  val queryInput = UInt(64.W)
  val cacheBase = UInt(64.W)
  val output = UInt(64.W)
  val queryStart = UInt(32.W)
  val cacheLength = UInt(32.W)
  val capacityTokens = UInt(32.W)
  val tag = UInt(32.W)
}
class Bf16CausalGqaResult extends Bundle {
  val tag = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val outputCommitted = Bool()
  // 0 none; 1 nonfinite; 2 scalar/probability domain; 3 unsupported
  // unmasked score difference <= -80; 4 fully masked row.
  val attentionStatus = UInt(4.W)
}
class Bf16CausalGqaOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new Bf16CausalGqaJob))
  val done = Decoupled(new Bf16CausalGqaResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val matrix = new MatrixStreamPort
  val scalar = new GdnScalarClient
  val resetRequired = Output(Bool())
}

/** Bounded 16-query x32-key QK tiles and 16-query x256-column PV tiles.
  * Q:8 KiB, K:16 KiB, score/exp/prob:16 KiB at maxCacheTokens=256,
  * QK BF16 memory:1 KiB, PV BF16 memory:8 KiB, V vector:512 B.
  * Thirty-two terminal BF16 converters are reused per 64-byte output beat.
  * Q/K are banks of eight 512-bit words, not a full attention matrix.
  * No Matrix arithmetic, SFU, Scalar or iDMA instance is created here.
  *
  * QK: opcode0x23/slice0, increasing d0..255 FP32 FMA, terminal BF16 RNE.
  * Scale1/16 separately rounds FP32 then BF16. Softmax uses FP32 max,
  * subtract, shared degree7 ExpNegative, increasing-key sum/div, terminal
  * BF16 probabilities. Unmasked differences <= -80 are unsupported; the
  * shared exp truncation is never silently called native equality. PV:
  * opcode0x24/all8 slices, increasing key0..cacheLength-1 including masked
  * probability zero, terminal BF16. Query head h maps to KV head floor(h/4).
  * Fixed-order bit equality is distinct from official eager/native accuracy.
  *
  * Whole Q/cache/output allocations must be disjoint, aligned and legal in
  * the retained 56-bit aperture, including unused cache capacity. Successful
  * done follows every Matrix terminal done and every actual output write ACK.
  * Faults drain accepted memory/scalar work, abort/drain Matrix and poison
  * until joint reset of owner, services and transport. Reset alone cannot
  * cancel external work or roll back physical staging writes.
  */
class Bf16CausalGqaOwner(maxTokens: Int = 128, maxCacheTokens: Int = 256) extends Module {
  require(maxTokens >= 1 && maxTokens <= 128)
  require(maxCacheTokens >= 1 && maxCacheTokens <= 256)
  val io = IO(new Bf16CausalGqaOwnerPort)
  private val states = Enum(25)
  val idle = states(0)
  val readQ = states(1)
  val waitQ = states(2)
  val readK = states(3)
  val waitK = states(4)
  val groupQk = states(5)
  val stepQk = states(6)
  val resultQk = states(7)
  val doneQk = states(8)
  val scalarIssue = states(9)
  val scalarWait = states(10)
  val softBegin = states(11)
  val softExp = states(12)
  val softNorm = states(13)
  val groupPv = states(14)
  val readV = states(15)
  val waitV = states(16)
  val stepPv = states(17)
  val resultPv = states(18)
  val donePv = states(19)
  val writeOut = states(20)
  val waitOut = states(21)
  val drain = states(22)
  val finish = states(23)
  val locked = states(24)
  val state = RegInit(idle)
  val scaleScore :: difference :: exponential :: sumExp :: divide :: Nil = Enum(5)
  val operation = RegInit(scaleScore)
  val job = Reg(new Bf16CausalGqaJob)
  val qTile = RegInit(0.U(16.W))
  val head = RegInit(0.U(3.W))
  val row = RegInit(0.U(4.W))
  val beat = RegInit(0.U(3.W))
  val kTile = RegInit(0.U(9.W))
  val kLane = RegInit(0.U(5.W))
  val dimension = RegInit(0.U(8.W))
  val key = RegInit(0.U(9.W))
  val query = Seq.fill(16)(Mem(8, UInt(512.W)))
  val keys = Seq.fill(32)(Mem(8, UInt(512.W)))
  val scores = Seq.fill(16)(Mem(maxCacheTokens, UInt(32.W)))
  val qk = Mem(16, UInt(512.W))
  val output = Seq.fill(16)(Mem(8, UInt(512.W)))
  val collecting = RegInit(false.B)
  val value = Reg(Vec(8, UInt(512.W)))
  val maximum = Reg(Vec(16, UInt(32.W)))
  val seen = RegInit(VecInit(Seq.fill(16)(false.B)))
  val scalarValue = Reg(UInt(32.W))
  val sum = RegInit(0.U(32.W))
  val sequence = RegInit(0.U(32.W))
  val matrixTag = RegInit(0.U(32.W))
  val matrixActive = RegInit(false.B)
  val memoryPending = RegInit(false.B)
  val scalarPending = RegInit(false.B)
  val status = RegInit(Status.Ok.U(8.W))
  val attentionStatus = RegInit(0.U(4.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val rows = Mux(job.tokens - qTile >= 16.U, 16.U(5.W), (job.tokens - qTile)(4, 0))
  val columns = Mux(job.cacheLength - kTile >= 32.U, 32.U(6.W), (job.cacheLength - kTile)(5, 0))
  val causalEnd = job.queryStart.pad(33) + qTile.pad(33) + row.pad(33)
  val allowed = key.pad(33) <= causalEnd
  val scoreAddress = key(log2Ceil(maxCacheTokens).max(1) - 1, 0)
  val scoreReads = VecInit(scores.map(_.read(scoreAddress)))
  val score = scoreReads(row)

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U
  io.done.bits.attentionStatus := attentionStatus
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := drain }
  def numerical(reason: Int): Unit = { attentionStatus := reason.U; fail(Status.Numerical.U) }
  val scoreWrite = WireDefault(false.B)
  val scoreWriteData = WireDefault(0.U(32.W))
  for (r <- 0 until 16) {
    when(scoreWrite && row === r.U) { scores(r).write(scoreAddress, scoreWriteData) }
  }
  def storeScore(data: UInt): Unit = { scoreWrite := true.B; scoreWriteData := data }
  def nextSoftKey(): Unit = {
    when(key +& 1.U === job.cacheLength) { key := 0.U; state := softNorm }
      .otherwise { key := key + 1.U; state := softExp }
  }

  val qOffset = ((qTile.pad(65) + row.pad(65)) << 12) + (head.pad(65) << 9) + (beat.pad(65) << 6)
  val kOffset = ((kTile.pad(65) + kLane.pad(65)) << 10) + (head(2, 2).pad(65) << 9) + (beat.pad(65) << 6)
  val vOffset = (job.capacityTokens.pad(65) << 10) + (key.pad(65) << 10) +
    (head(2, 2).pad(65) << 9) + (beat.pad(65) << 6)
  io.memory.valid := state === readQ || state === readK || state === readV || state === writeOut
  io.memory.bits.write := state === writeOut
  io.memory.bits.address := MuxLookup(state, job.queryInput.pad(65) + qOffset)(Seq(
    readK -> (job.cacheBase.pad(65) + kOffset), readV -> (job.cacheBase.pad(65) + vOffset),
    writeOut -> (job.output.pad(65) + qOffset)))
  io.memory.bits.data := Mux(state === writeOut, VecInit(output.map(_.read(beat)))(row), 0.U)
  io.memory.bits.mask := Mux(state === writeOut, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := memoryPending

  io.matrix.group.valid := state === groupQk || state === groupPv
  io.matrix.group.bits.opcode := Mux(state === groupPv, 0x24.U, 0x23.U)
  io.matrix.group.bits.sliceMask := Mux(state === groupPv, 255.U, 1.U)
  io.matrix.group.bits.tag := matrixTag
  io.matrix.step.valid := state === stepQk || state === stepPv
  io.matrix.step.bits.context := 0.U
  io.matrix.step.bits.clear := Mux(state === stepPv, key === 0.U, dimension === 0.U)
  val lastStep = Mux(state === stepPv, key +& 1.U === job.cacheLength, dimension === 255.U)
  io.matrix.step.bits.last := lastStep
  io.matrix.step.bits.finish := lastStep
  io.matrix.step.bits.emit := lastStep
  for (r <- 0 until 16) {
    val q = query(r).read(dimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(dimension(4, 0))
    io.matrix.step.bits.a(r) := Mux(r.U < rows, Mux(state === stepPv, scoreReads(r)(31, 16), q), 0.U)
  }
  for (c <- 0 until 256) {
    val k = if (c < 32) keys(c).read(dimension(7, 5)).asTypeOf(Vec(32, UInt(16.W)))(dimension(4, 0)) else 0.U
    val v = value(c / 32)(16 * (c % 32) + 15, 16 * (c % 32))
    io.matrix.step.bits.b(c) := Mux(state === stepPv, v, Mux(c.U < columns, k, 0.U))
  }
  val collectingResult = state === resultQk || state === resultPv
  val finalResultBeat = row +& 1.U === rows && (state === resultQk || beat === 7.U)
  // MatrixResultFifo holds valid/bits stable until fire. Collect provisional
  // beats under backpressure; only the final beat accepts the whole result.
  io.matrix.result.ready := state === drain || (collectingResult && finalResultBeat)
  val awaitingMatrixDone = state === doneQk || state === donePv
  io.matrix.done.ready := matrixActive && (awaitingMatrixDone || state === drain)
  io.matrix.abort := state === drain && matrixActive

  io.scalar.request.valid := state === scalarIssue
  io.scalar.request.bits.op := MuxLookup(operation, ScalarOp.Add.U)(Seq(
    scaleScore -> ScalarOp.MulIeeeRne.U, exponential -> ScalarOp.ExpNegative.U, divide -> ScalarOp.Div.U))
  io.scalar.request.bits.a := MuxLookup(operation, scalarValue)(Seq(
    scaleScore -> Cat(qk.read(row).asTypeOf(Vec(32, UInt(16.W)))(kLane), 0.U(16.W)), difference -> score, sumExp -> sum, divide -> score))
  io.scalar.request.bits.b := MuxLookup(operation, 0.U)(Seq(
    scaleScore -> "h3d800000".U, difference -> F32.neg(maximum(row)), sumExp -> scalarValue, divide -> sum))
  io.scalar.result.ready := scalarPending

  when(io.job.fire) {
    val j = io.job.bits
    job := j; qTile := 0.U; head := 0.U; row := 0.U; beat := 0.U; kTile := 0.U; kLane := 0.U
    dimension := 0.U; key := 0.U; sequence := 0.U; matrixTag := j.tag
    matrixActive := false.B; memoryPending := false.B; scalarPending := false.B; collecting := false.B
    status := Status.Ok.U; attentionStatus := 0.U; bytes := 0.U; cycles := 0.U
    seen.foreach(_ := false.B)
    val vectorBytes = j.tokens.pad(65) << 12
    val cacheBytes = j.capacityTokens.pad(65) << 11
    def badSpan(base: UInt, size: UInt): Bool = base(5, 0) =/= 0.U || base.pad(65) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(65) < b.pad(65) + nb && b.pad(65) < a.pad(65) + na
    val badAddress = badSpan(j.queryInput, vectorBytes) || badSpan(j.output, vectorBytes) || badSpan(j.cacheBase, cacheBytes)
    val alias = overlap(j.queryInput, vectorBytes, j.output, vectorBytes) ||
      overlap(j.queryInput, vectorBytes, j.cacheBase, cacheBytes) || overlap(j.output, vectorBytes, j.cacheBase, cacheBytes)
    when(j.tokens === 0.U || j.tokens > maxTokens.U || j.queryHeads =/= 8.U || j.kvHeads =/= 2.U || j.headDim =/= 256.U ||
      j.cacheLength === 0.U || j.capacityTokens === 0.U || j.capacityTokens > maxCacheTokens.U ||
      j.cacheLength > j.capacityTokens || badAddress || alias) { fail(Status.Bounds.U) }
      .elsewhen(j.queryStart.pad(33) + j.tokens.pad(33) =/= j.cacheLength.pad(33)) { fail(Status.Dependency.U) }
      .otherwise { state := readQ }
  }
  when(io.memory.fire) {
    memoryPending := true.B
    state := MuxLookup(state, waitQ)(Seq(readK -> waitK, readV -> waitV, writeOut -> waitOut))
  }
  when(io.response.fire) {
    memoryPending := false.B; sequence := sequence + 1.U
    when(state =/= drain) {
      val r = io.response.bits
      val badNumber = (0 until 32).map(i => r.data(i * 16 + 14, i * 16 + 7) === 255.U).reduce(_ || _)
      when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
        .elsewhen(r.error) { fail(Status.Memory.U) }
        .elsewhen(state =/= waitOut && badNumber) { numerical(1) }
        .otherwise {
          when(state === waitQ) {
            for (i <- 0 until 16) { when(row === i.U) { query(i).write(beat, r.data) } }
            when(beat === 7.U) {
              beat := 0.U
              when(row +& 1.U === rows) { row := 0.U; kLane := 0.U; kTile := 0.U; state := readK }
                .otherwise { row := row + 1.U; state := readQ }
            }.otherwise { beat := beat + 1.U; state := readQ }
          }
          when(state === waitK) {
            for (i <- 0 until 32) { when(kLane === i.U) { keys(i).write(beat, r.data) } }
            when(beat === 7.U) {
              beat := 0.U
              when(kLane +& 1.U === columns) { kLane := 0.U; dimension := 0.U; state := groupQk }
                .otherwise { kLane := kLane + 1.U; state := readK }
            }.otherwise { beat := beat + 1.U; state := readK }
          }
          when(state === waitV) {
            value(beat) := r.data
            when(beat === 7.U) { beat := 0.U; state := stepPv }
              .otherwise { beat := beat + 1.U; state := readV }
          }
          when(state === waitOut) {
            bytes := bytes + 64.U
            when(beat === 7.U) {
              beat := 0.U
              when(row +& 1.U === rows) {
                row := 0.U; seen.foreach(_ := false.B)
                when(head === 7.U) {
                  head := 0.U
                  when(qTile +& rows === job.tokens) { state := finish }
                    .otherwise { qTile := qTile + 16.U; state := readQ }
                }.otherwise { head := head + 1.U; state := readQ }
              }.otherwise { row := row + 1.U; state := writeOut }
            }.otherwise { beat := beat + 1.U; state := writeOut }
          }
        }
    }
  }
  when(io.matrix.group.fire) { matrixActive := true.B; state := Mux(state === groupQk, stepQk, readV) }
  when(io.matrix.step.fire) {
    when(state === stepQk) {
      when(dimension === 255.U) { row := 0.U; beat := 0.U; collecting := false.B; state := resultQk }.otherwise { dimension := dimension + 1.U }
    }.otherwise {
      when(key +& 1.U === job.cacheLength) { row := 0.U; beat := 0.U; collecting := false.B; state := resultPv }
        .otherwise { key := key + 1.U; state := readV }
    }
  }
  val incomingRows = VecInit(io.matrix.result.bits.value.map(_.asUInt))
  val incomingBeat = incomingRows(row).asTypeOf(Vec(8, UInt(1024.W)))(Mux(state === resultQk, 0.U, beat))
  val incomingFloats = incomingBeat.asTypeOf(Vec(32, UInt(32.W)))
  val converted = VecInit(incomingFloats.map(TensorMath.bf16Rne))
  val badConversion = VecInit((0 until 32).map { c =>
    (state === resultPv || c.U < columns) &&
      (!TensorMath.finite(incomingFloats(c)) || converted(c)(14, 7) === 255.U)
  }).asUInt.orR
  when(collectingResult && io.matrix.result.valid) {
    val m = io.matrix.result.bits
    when(m.error || m.context =/= 0.U || !m.last) { fail(Status.Protocol.U) }
      .elsewhen(badConversion) { numerical(1) }
      .otherwise {
        collecting := true.B
        when(state === resultQk) { qk.write(row, converted.asUInt) }
          .otherwise {
            for (r <- 0 until 16) { when(row === r.U) { output(r).write(beat, converted.asUInt) } }
          }
        when(finalResultBeat) {
          // This transition coincides with result.fire. No scalar or output
          // store can observe these staging memories until terminal done.
          collecting := false.B; row := 0.U; beat := 0.U
          state := Mux(state === resultQk, doneQk, donePv)
        }.elsewhen(state === resultQk || beat === 7.U) { row := row + 1.U; beat := 0.U }
          .otherwise { beat := beat + 1.U }
      }
  }
  when(collectingResult && collecting && !io.matrix.result.valid) { fail(Status.Protocol.U) }
  when(io.matrix.done.fire) {
    matrixActive := false.B; matrixTag := matrixTag + 1.U
    when(state =/= drain) {
      when(io.matrix.done.bits.tag =/= matrixTag || io.matrix.done.bits.error ||
        !(state === doneQk || state === donePv)) { fail(Status.Protocol.U) }
        .otherwise {
          row := 0.U; beat := 0.U
          when(state === doneQk) { kLane := 0.U; key := kTile; operation := scaleScore; state := scalarIssue }
            .otherwise { state := writeOut }
        }
    }
  }
  when(state === softBegin) {
    sum := 0.U; key := 0.U
    when(!seen(row)) { numerical(4) }.otherwise { state := softExp }
  }
  when(state === softExp) {
    when(!allowed) { storeScore(0.U); nextSoftKey() }
      .otherwise { operation := difference; state := scalarIssue }
  }
  when(state === softNorm) {
    when(sum(31) || sum(30, 0) === 0.U || !TensorMath.finite(sum)) { numerical(2) }
      .elsewhen(!allowed) {
        storeScore(0.U)
        when(key +& 1.U === job.cacheLength) {
          key := 0.U
          when(row +& 1.U === rows) { row := 0.U; beat := 0.U; state := groupPv }
            .otherwise { row := row + 1.U; state := softBegin }
        }.otherwise { key := key + 1.U }
      }.otherwise { operation := divide; state := scalarIssue }
  }
  when(io.scalar.request.fire) { scalarPending := true.B; state := scalarWait }
  when(io.scalar.result.fire) {
    scalarPending := false.B
    when(state =/= drain) {
      val r = io.scalar.result.bits
      val bf = TensorMath.bf16Rne(r)
      when(io.scalar.error || !TensorMath.finite(r)) { numerical(2) }
        .otherwise {
          scalarValue := r; state := scalarIssue
          switch(operation) {
            is(scaleScore) {
              when(bf(14, 7) === 255.U) { numerical(1) }
                .otherwise {
                  val rounded = Cat(bf, 0.U(16.W))
                  storeScore(rounded)
                  when(allowed && (!seen(row) || F32.less(maximum(row), rounded))) { maximum(row) := rounded; seen(row) := true.B }
                  when(kLane +& 1.U === columns) {
                    kLane := 0.U; key := kTile
                    when(row +& 1.U === rows) {
                      row := 0.U
                      when(kTile +& columns === job.cacheLength) { state := softBegin }
                        .otherwise { kTile := kTile + 32.U; beat := 0.U; state := readK }
                    }.otherwise { row := row + 1.U }
                  }.otherwise { kLane := kLane + 1.U; key := key + 1.U }
                }
            }
            is(difference) {
              when(!r(31) && r(30, 0).orR) { numerical(2) }
                .elsewhen(r(30, 0) >= "h42a00000".U) { attentionStatus := 3.U; fail(Status.Unsupported.U) }
                .otherwise { operation := exponential }
            }
            is(exponential) {
              when(r(31) || r(30, 0) === 0.U || F32.less("h3f800000".U, r)) { numerical(2) }
                .otherwise { storeScore(r); operation := sumExp }
            }
            is(sumExp) { sum := r; nextSoftKey() }
            is(divide) {
              when(r(31) || F32.less("h3f800000".U, r) || bf(14, 7) === 255.U) { numerical(2) }
                .otherwise {
                  storeScore(Cat(bf, 0.U(16.W)))
                  when(key +& 1.U === job.cacheLength) {
                    key := 0.U
                    when(row +& 1.U === rows) { row := 0.U; beat := 0.U; state := groupPv }
                      .otherwise { row := row + 1.U; state := softBegin }
                  }.otherwise { key := key + 1.U; state := softNorm }
                }
            }
          }
        }
    }
  }
  // Finish only after pending flags clear and the actual Matrix done arrives.
  when(state === drain && !memoryPending && !scalarPending && !matrixActive) { state := finish }
  // Early terminal valid is a protocol fault. Consume it only in drain;
  // accepted memory/scalar work still must return before owner completion.
  when(matrixActive && io.matrix.done.valid && !awaitingMatrixDone && state =/= drain) { fail(Status.Protocol.U) }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
