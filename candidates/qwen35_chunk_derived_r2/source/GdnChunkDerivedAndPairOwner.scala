// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Private scheduler wrapper, NOT a new public producer ABI. phase1Context is
  * the scheduler's retained accepted context, not a field claimed to exist in
  * the original LoadPrep result. All roots/source matrices remain exclusively
  * owned and stable through this job and held done. Receipt provenance remains
  * the scheduler's responsibility; this owner does not authenticate it.
  */
class GdnChunkDerivedAndPairJob extends Bundle {
  val context = new GdnChunkJob
  val head = UInt(16.W)
  val chunk = UInt(16.W)
  val phase1Context = new GdnChunkJob
  val phase1Ready = new GdnChunkLoadPrepResult
}

/** Kept privately by the scheduler until SAME-context/head/chunk phase15.
  * No persistent-root publication, generation advance, or new exp policy.
  * valid is only asserted with a complete successful phase2 held result.
  */
class GdnChunkPrivateDecay extends Bundle {
  val context = new GdnChunkJob
  val head = UInt(4.W)
  val chunk = UInt(1.W)
  val value = UInt(32.W)
  val valid = Bool()
}

class GdnChunkDerivedAndPairResult extends Bundle {
  val receipt = new GdnChunkStageReceipt
  val decay = new GdnChunkPrivateDecay
  val readBytes = UInt(64.W)
  val expRequests = UInt(12.W)
  val expResults = UInt(12.W)
  val addRequests = UInt(12.W)
  val addResults = UInt(12.W)
  val mulRequests = UInt(12.W)
  val mulResults = UInt(12.W)
  val cycles = UInt(64.W)
  val stageComplete = Bool()
}

class GdnChunkDerivedAndPairPort extends Bundle {
  val job = Flipped(Decoupled(new GdnChunkDerivedAndPairJob))
  val committed = Input(new GdnChunkCommittedState)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val loan = Flipped(new ElementwiseLoanPort)
  val done = Decoupled(new GdnChunkDerivedAndPairResult)
  val resetRequired = Output(Bool())
}

/** Complete chunk64 phase2 only: original ordered derived vectors and causal
  * pair decays. Uses existing Scalar ExpNegative4 and Loan Add1/Mul2. No Module
  * is instantiated here; no new ALU, exp/SFU, SRAM, public entry or top route.
  *
  * Four 512-bit payload registers (256 B), plus explicitly separate scalar,
  * context/counter/control registers. K=A,Q=B,KB=C,KBG=D; QG replaces B and
  * KE replaces A. ALL four products finish before writes C,D,B,A. V/VB/pair
  * reuse A. No premature spill changes the original tuple failure boundary.
  *
  * Scalar has no tag/raw flags; MemoryResponse has no nbytes. One memory OR
  * scalar OR loan request outstanding, with exclusive shared services and no
  * stale responses. Tags check the current transaction, not cross-job replay.
  * Responses offered on an issue cycle must remain held until wait.ready.
  *
  * Loan abort/resetLoan stay LOW: either high suppresses loan.result.valid.
  * An error result is retired with them low, then the loan may be lLocked.
  * Error done retirement locks this owner until coordinated GLOBAL reset.
  * There is no local clear, no resetRequired-to-abort feedback, no rollback,
  * and no claim that owner reset alone drains memory/scalar/loan. External
  * recovery must retire any held loan error before using its lLocked/drained/
  * no-DDR-poison resetLoan path, or coordinate reset of the complete fabric.
  */
class GdnChunkDerivedAndPairOwner extends Module {
  import GdnChunkGeometry._
  private val stateBytes = GdnChunkAddressPlan.PerHeadStateBytes
  private val chunkBytes = GdnChunkAddressPlan.PerHeadChunkBytes
  private val stride16 = stateBytes + chunkBytes
  private val stride128 = stateBytes + 2 * chunkBytes
  private val phaseBytes = 180224
  private val phaseReadBytes = 235584 // original 3680 reads + one gates[63] read
  require(Heads == 16 && KeyDim == 128 && ValueDim == 128 && ChunkRows == 64 && BeatBytes == 64)
  require(stateBytes == 65536 && chunkBytes == 806912 && stride16 == 872448 && stride128 == 1679360)
  private val matrixOffsets = Map("gates" -> 0, "q" -> 4096, "k" -> 36864, "v" -> 69632,
    "kb" -> 102400, "vb" -> 135168, "kbg" -> 167936, "qg" -> 200704, "ke" -> 233472, "pair" -> 331776)
  matrixOffsets.foreach { case (name, offset) =>
    val index = GdnChunkAddressPlan.Shapes.indexWhere(_.name == name)
    require(index >= 0 && GdnChunkAddressPlan.Shapes.take(index).map(_.bytes).sum == offset)
  }
  require(GdnChunkAddressPlan.Phases(1).writes.map(n =>
    GdnChunkAddressPlan.Shapes.find(_.name == n).get.bytes).sum == phaseBytes)

  val io = IO(new GdnChunkDerivedAndPairPort)
  val idle :: issueRead :: waitRead :: issueLoan :: waitLoan :: issueExp :: waitExp :: issueWrite :: waitWrite :: finish :: locked :: Nil = Enum(11)
  val state = RegInit(idle)
  private val microSteps = Enum(23)
  val finalGate = microSteps(0)
  val chunkExp = microSteps(1)
  val rowGate = microSteps(2)
  val rowExp = microSteps(3)
  val remainingAdd = microSteps(4)
  val remainingExp = microSteps(5)
  val readK = microSteps(6)
  val readQ = microSteps(7)
  val mulKb = microSteps(8)
  val mulKbg = microSteps(9)
  val mulQg = microSteps(10)
  val mulKe = microSteps(11)
  val writeKb = microSteps(12)
  val writeKbg = microSteps(13)
  val writeQg = microSteps(14)
  val writeKe = microSteps(15)
  val readV = microSteps(16)
  val mulVb = microSteps(17)
  val writeVb = microSteps(18)
  val pairRead = microSteps(19)
  val pairAdd = microSteps(20)
  val pairExp = microSteps(21)
  val pairWrite = microSteps(22)
  val step = RegInit(finalGate)
  val context = RegInit(0.U.asTypeOf(new GdnChunkJob))
  val head = RegInit(0.U(4.W))
  val chunk = RegInit(0.U(1.W))
  val chunkBase = RegInit(0.U(64.W))
  val row = RegInit(0.U(6.W))
  val beat = RegInit(0.U(3.W))
  val pairBeat = RegInit(0.U(2.W))
  val lane = RegInit(0.U(4.W))
  val memorySequence = RegInit(0.U(32.W))
  val loanSequence = RegInit(0.U(32.W))
  val payload = RegInit(VecInit(Seq.fill(4)(0.U(512.W)))) // EXACTLY 256 B payload
  val finalCumulative = RegInit(0.U(32.W))
  val cumulative = RegInit(0.U(32.W))
  val beta = RegInit(0.U(32.W))
  val earlierCumulative = RegInit(0.U(32.W))
  val difference = RegInit(0.U(32.W))
  val expG = RegInit(0.U(32.W))
  val expRemaining = RegInit(0.U(32.W))
  val chunkDecay = RegInit(0.U(32.W))
  val memoryOutstanding = RegInit(false.B)
  val scalarOutstanding = RegInit(false.B)
  val loanOutstanding = RegInit(false.B)
  val status = RegInit(Status.Ok.U(8.W))
  val readBytes = RegInit(0.U(64.W))
  val writeBytes = RegInit(0.U(64.W))
  val expRequests = RegInit(0.U(12.W)); val expResults = RegInit(0.U(12.W))
  val addRequests = RegInit(0.U(12.W)); val addResults = RegInit(0.U(12.W))
  val mulRequests = RegInit(0.U(12.W)); val mulResults = RegInit(0.U(12.W))
  val cycles = RegInit(0.U(64.W))
  def finite(word: UInt): Bool = word(30, 23) =/= "hff".U
  def finiteBeat(words: UInt): Bool = (0 until 16).map(i => finite(words(32*i+31, 32*i))).reduce(_ && _)
  def expDomain(word: UInt): Bool = finite(word) && (word(31) || word(30, 0) === 0.U)
  def fail(code: UInt): Unit = { status := code; state := finish }

  val earlierRow = Cat(pairBeat, lane)
  val rowVectorOffset = (row.pad(66) << 9) + (beat.pad(66) << 6)
  val readOffset = MuxLookup(step, 0.U(66.W))(Seq(
    finalGate -> (63 * BeatBytes).U(66.W), rowGate -> (row.pad(66) << 6),
    readK -> (36864.U + rowVectorOffset), readQ -> (4096.U + rowVectorOffset),
    readV -> (69632.U + rowVectorOffset), pairRead -> (earlierRow.pad(66) << 6)))
  val writeOffset = MuxLookup(step, 0.U(66.W))(Seq(
    writeKb -> (102400.U + rowVectorOffset), writeKbg -> (167936.U + rowVectorOffset),
    writeQg -> (200704.U + rowVectorOffset), writeKe -> (233472.U + rowVectorOffset),
    writeVb -> (135168.U + rowVectorOffset),
    pairWrite -> (331776.U + (row.pad(66) << 8) + (pairBeat.pad(66) << 6))))
  val readAddress = chunkBase.pad(66) + readOffset
  val writeAddress = chunkBase.pad(66) + writeOffset
  val writePayload = MuxLookup(step, payload(0))(Seq(writeKb -> payload(2), writeKbg -> payload(3), writeQg -> payload(1)))
  val isAdd = step === remainingAdd || step === pairAdd
  val singleA = Mux(step === remainingAdd, finalCumulative, cumulative)
  val singleB = Mux(step === remainingAdd, cumulative, earlierCumulative) ^ "h80000000".U
  val multiplyA = MuxLookup(step, payload(0))(Seq(mulKbg -> payload(2), mulQg -> payload(1)))
  val multiplyB = MuxLookup(step, beta)(Seq(mulKbg -> expG, mulQg -> expG, mulKe -> expRemaining))
  val expArgument = MuxLookup(step, difference)(Seq(chunkExp -> finalCumulative, rowExp -> cumulative))
  val currentLoanTag = context.tag ^ loanSequence

  io.job.ready := state === idle
  io.memory.valid := state === issueRead || state === issueWrite
  io.memory.bits.write := state === issueWrite
  io.memory.bits.address := Mux(state === issueWrite, writeAddress(63, 0), readAddress(63, 0))
  io.memory.bits.data := Mux(state === issueWrite, writePayload, 0.U(512.W))
  io.memory.bits.mask := Mux(state === issueWrite, Fill(64, 1.U(1.W)), 0.U(64.W))
  io.memory.bits.tag := Cat(context.tag, memorySequence)
  io.response.ready := state === waitRead || state === waitWrite
  // Domain guard is on valid itself: invalid +x/NaN/Inf can NEVER fire Exp4.
  io.scalar.request.valid := state === issueExp && expDomain(expArgument)
  io.scalar.request.bits.op := ScalarOp.ExpNegative.U
  io.scalar.request.bits.a := expArgument
  io.scalar.request.bits.b := 0.U
  io.scalar.result.ready := state === waitExp
  io.loan.request.valid := state === issueLoan && !io.loan.resetRequired
  io.loan.request.bits.tag := currentLoanTag
  io.loan.request.bits.op := Mux(isAdd, ElementwiseLoanOp.Add.U, ElementwiseLoanOp.Mul.U)
  io.loan.request.bits.a := Mux(isAdd, Cat(0.U(480.W), singleA), multiplyA)
  io.loan.request.bits.b := Mux(isAdd, Cat(0.U(480.W), singleB), Fill(16, multiplyB))
  io.loan.request.bits.inverse := 0.U
  io.loan.result.ready := state === waitLoan
  io.loan.abort := false.B
  io.loan.resetLoan := false.B

  val locallyDrained = !memoryOutstanding && !scalarOutstanding && !loanOutstanding
  val complete = state === finish && status === Status.Ok.U && locallyDrained &&
    readBytes === phaseReadBytes.U && writeBytes === phaseBytes.U &&
    expRequests === 2209.U && expResults === 2209.U && addRequests === 2144.U && addResults === 2144.U &&
    mulRequests === 2560.U && mulResults === 2560.U
  io.done.valid := state === finish
  io.done.bits.receipt.tag := context.tag
  io.done.bits.receipt.expectedGeneration := context.expectedGeneration
  io.done.bits.receipt.head := head; io.done.bits.receipt.chunk := chunk
  io.done.bits.receipt.phase := 2.U; io.done.bits.receipt.status := status
  io.done.bits.receipt.scratchAckBytes := writeBytes
  io.done.bits.receipt.outputAckBytes := 0.U; io.done.bits.receipt.stateAckBytes := 0.U
  io.done.bits.receipt.drained := state === finish && status === Status.Ok.U && locallyDrained
  io.done.bits.decay.context := context
  io.done.bits.decay.head := head; io.done.bits.decay.chunk := chunk
  io.done.bits.decay.value := Mux(complete, chunkDecay, 0.U)
  io.done.bits.decay.valid := complete
  io.done.bits.readBytes := readBytes
  io.done.bits.expRequests := expRequests; io.done.bits.expResults := expResults
  io.done.bits.addRequests := addRequests; io.done.bits.addResults := addResults
  io.done.bits.mulRequests := mulRequests; io.done.bits.mulResults := mulResults
  io.done.bits.cycles := cycles; io.done.bits.stageComplete := complete
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  when(state === issueExp && !expDomain(expArgument)) { fail(Status.Numerical.U) }
  when(state === issueLoan && io.loan.resetRequired) { fail(Status.Dependency.U) }

  when(io.job.fire) {
    val j = io.job.bits; val c = j.context; val r = j.phase1Ready; val p = r.receipt
    context := c; head := j.head(3, 0); chunk := j.chunk(0)
    row := 0.U; beat := 0.U; pairBeat := 0.U; lane := 0.U
    memorySequence := 0.U; loanSequence := 0.U
    payload.foreach(_ := 0.U)
    finalCumulative := 0.U; cumulative := 0.U; beta := 0.U; earlierCumulative := 0.U
    difference := 0.U; expG := 0.U; expRemaining := 0.U; chunkDecay := 0.U
    memoryOutstanding := false.B; scalarOutstanding := false.B; loanOutstanding := false.B
    status := Status.Ok.U; readBytes := 0.U; writeBytes := 0.U
    expRequests := 0.U; expResults := 0.U; addRequests := 0.U; addResults := 0.U
    mulRequests := 0.U; mulResults := 0.U; cycles := 0.U; step := finalGate
    val is128 = c.tokens === 128.U
    val stride = Mux(is128, stride128.U, stride16.U)
    val selectedChunk = c.scratch.pad(66) + (j.head * stride).pad(66) + stateBytes.U + (j.chunk * chunkBytes.U).pad(66)
    chunkBase := selectedChunk(63, 0)
    val inputBytes = (c.tokens * PreparedRowBytes.U).pad(66)
    val outputBytes = (c.tokens * OutputRowBytes.U).pad(66)
    val scratchBytes = Mux(is128, GdnChunkAddressPlan.scratchBytes(128).U(66.W), GdnChunkAddressPlan.scratchBytes(16).U(66.W))
    val spans = Seq((c.input, inputBytes), (c.stateIn, StateBytes.U(66.W)),
      (c.stateOut, StateBytes.U(66.W)), (c.output, outputBytes), (c.scratch, scratchBytes))
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || size === 0.U || base.pad(66) + size > (BigInt(1) << AddressBits).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(66) < b.pad(66) + nb && b.pad(66) < a.pad(66) + na
    val badAddress = spans.map { case (b, n) => badSpan(b, n) }.reduce(_ || _)
    val aliases = spans.indices.flatMap(i => (0 until i).map(k =>
      overlap(spans(i)._1, spans(i)._2, spans(k)._1, spans(k)._2))).reduce(_ || _)
    val rootBad = c.expectedGeneration =/= io.committed.generation ||
      Mux(c.cold, c.expectedGeneration =/= 0.U || io.committed.valid,
        c.expectedGeneration === 0.U || !io.committed.valid || io.committed.state =/= c.stateIn)
    val phase1Qualified = j.phase1Context.asUInt === c.asUInt && r.stageComplete &&
      p.tag === c.tag && p.expectedGeneration === c.expectedGeneration &&
      p.head.pad(16) === j.head && p.chunk.pad(16) === j.chunk && p.phase === 1.U &&
      p.status === Status.Ok.U && p.drained && p.scratchAckBytes === 102400.U &&
      p.outputAckBytes === 0.U && p.stateAckBytes === 0.U &&
      r.addRequests === 64.U && r.addResults === 64.U && r.readBytes === Mux(is128, 102400.U, 25600.U)
    when(rootBad) { fail(Status.Dependency.U) }
      .elsewhen((c.tokens =/= 16.U && c.tokens =/= 128.U) || j.head >= Heads.U ||
        j.chunk >= Mux(is128, 2.U, 1.U) || c.expectedGeneration === "hffffffff".U || badAddress || aliases) { fail(Status.Bounds.U) }
      .elsewhen(c.vectorPolicy =/= GdnChunkVectorPolicy.LegacyFatalUnderflow.U) { fail(Status.Unsupported.U) }
      .elsewhen(!phase1Qualified) { fail(Status.Dependency.U) }
      .elsewhen(io.response.valid || io.scalar.result.valid || io.loan.result.valid || io.loan.busy || io.loan.resetRequired) { fail(Status.Protocol.U) }
      .otherwise { state := issueRead }
  }

  when(io.memory.fire) {
    memoryOutstanding := true.B
    state := Mux(state === issueRead, waitRead, waitWrite)
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(context.tag, memorySequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { memoryOutstanding := false.B; fail(Status.Memory.U) }
      .otherwise {
        memoryOutstanding := false.B; memorySequence := memorySequence + 1.U
        when(state === waitRead) {
          readBytes := readBytes + BeatBytes.U
          when(!finiteBeat(r.data)) { fail(Status.Numerical.U) }
            .otherwise {
              switch(step) {
                is(finalGate) { finalCumulative := r.data(31, 0); step := chunkExp; state := issueExp }
                is(rowGate) { cumulative := r.data(31, 0); beta := r.data(63, 32); step := rowExp; state := issueExp }
                is(readK) { payload(0) := r.data; step := readQ; state := issueRead }
                is(readQ) { payload(1) := r.data; step := mulKb; state := issueLoan }
                is(readV) { payload(0) := r.data; step := mulVb; state := issueLoan }
                is(pairRead) { earlierCumulative := r.data(31, 0); step := pairAdd; state := issueLoan }
              }
            }
        }.otherwise {
          writeBytes := writeBytes + BeatBytes.U
          switch(step) {
            is(writeKb) { step := writeKbg; state := issueWrite }
            is(writeKbg) { step := writeQg; state := issueWrite }
            is(writeQg) { step := writeKe; state := issueWrite }
            is(writeKe) {
              when(beat === 7.U) { beat := 0.U; step := readV }
                .otherwise { beat := beat + 1.U; step := readK }
              state := issueRead
            }
            is(writeVb) {
              when(beat === 7.U) {
                pairBeat := 0.U; lane := 0.U; payload(0) := 0.U; step := pairRead; state := issueRead
              }.otherwise { beat := beat + 1.U; step := readV; state := issueRead }
            }
            is(pairWrite) {
              when(pairBeat === 3.U) {
                when(row === 63.U) { state := finish }
                  .otherwise { row := row + 1.U; beat := 0.U; step := rowGate; state := issueRead }
              }.otherwise {
                val nextFirst = ((pairBeat +& 1.U).pad(6) << 4)
                pairBeat := pairBeat + 1.U; lane := 0.U; payload(0) := 0.U
                when(nextFirst <= row) { step := pairRead; state := issueRead }
                  .otherwise { step := pairWrite; state := issueWrite }
              }
            }
          }
        }
      }
  }

  when(io.loan.request.fire) {
    loanOutstanding := true.B
    when(isAdd) { addRequests := addRequests + 1.U }.otherwise { mulRequests := mulRequests + 1.U }
    state := waitLoan
  }
  when(io.loan.result.fire) {
    val r = io.loan.result.bits
    when(r.tag =/= currentLoanTag) { fail(Status.Protocol.U) }
      .elsewhen(r.status =/= Status.Ok.U) { loanOutstanding := false.B; fail(r.status) }
      .elsewhen(!finiteBeat(r.value)) { loanOutstanding := false.B; fail(Status.Numerical.U) }
      .otherwise {
        loanOutstanding := false.B; loanSequence := loanSequence + 1.U
        when(isAdd) { addResults := addResults + 1.U }.otherwise { mulResults := mulResults + 1.U }
        switch(step) {
          is(remainingAdd) { difference := r.value(31, 0); step := remainingExp; state := issueExp }
          is(pairAdd) { difference := r.value(31, 0); step := pairExp; state := issueExp }
          is(mulKb) { payload(2) := r.value; step := mulKbg; state := issueLoan }
          is(mulKbg) { payload(3) := r.value; step := mulQg; state := issueLoan }
          is(mulQg) { payload(1) := r.value; step := mulKe; state := issueLoan }
          is(mulKe) { payload(0) := r.value; step := writeKb; state := issueWrite }
          is(mulVb) { payload(0) := r.value; step := writeVb; state := issueWrite }
        }
      }
  }
  when(io.scalar.request.fire) { scalarOutstanding := true.B; expRequests := expRequests + 1.U; state := waitExp }
  when(io.scalar.result.fire) {
    scalarOutstanding := false.B
    when(io.scalar.error || !finite(io.scalar.result.bits)) { fail(Status.Numerical.U) }
      .otherwise {
        expResults := expResults + 1.U
        switch(step) {
          is(chunkExp) { chunkDecay := io.scalar.result.bits; step := rowGate; state := issueRead }
          is(rowExp) { expG := io.scalar.result.bits; step := remainingAdd; state := issueLoan }
          is(remainingExp) { expRemaining := io.scalar.result.bits; beat := 0.U; step := readK; state := issueRead }
          is(pairExp) {
            val words = Wire(Vec(16, UInt(32.W)))
            for (i <- 0 until 16) { words(i) := Mux(lane === i.U, io.scalar.result.bits, payload(0)(32*i+31, 32*i)) }
            payload(0) := words.asUInt
            when(lane =/= 15.U && earlierRow < row) { lane := lane + 1.U; step := pairRead; state := issueRead }
              .otherwise { step := pairWrite; state := issueWrite }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
