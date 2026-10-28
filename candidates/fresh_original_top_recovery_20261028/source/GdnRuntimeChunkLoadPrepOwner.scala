// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Trusted scheduler wrapping of a complete prepared allocation, not a new
  * public producer ABI or proof that a producer has actually executed.
  * Generation/input identity are supplied by that scheduler. The existing
  * prep result alone does not carry these fields. All roots, receipts and input
  * bytes must remain exclusively owned and stable for the entire stage job.
  */
class GdnRuntimeChunkPreparedReceipt extends Bundle {
  val tag = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val tokens = UInt(16.W)
  val input = UInt(64.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W)
  val preparedComplete = Bool()
  val drained = Bool()
  val recurrentMode = Bool()
  // Layout 0 is the existing prepared FP32 [Q[valueHead], K[valueHead],
  // V[valueHead], gates[valueHead,16]] row, NOT compact raw Conv/QKV.
  val layoutId = UInt(2.W)
  val layoutVersion = UInt(8.W)
  val rowBytes = UInt(32.W)
  val keyHeads = UInt(6.W)
  val valueHeads = UInt(6.W)
}

class GdnRuntimeChunkLoadPrepJob extends Bundle {
  val context = new GdnChunkJob
  val keyHeads = UInt(6.W) // admitted pinned key-head count is 16
  val valueHeads = UInt(6.W) // runtime 16 or 32; no elaboration parameter
  val head = UInt(5.W) // fixed physical maximum 32
  val chunk = UInt(1.W)
  val prepReady = new GdnRuntimeChunkPreparedReceipt
  val initialReady = new GdnChunkStageReceipt
  val previousStateReady = new GdnChunkStageReceipt
  val previousOutputReady = new GdnChunkStageReceipt
}

class GdnRuntimeChunkLoadPrepResult extends Bundle {
  val receipt = new GdnChunkStageReceipt
  val readBytes = UInt(64.W)
  val addRequests = UInt(7.W)
  val addResults = UInt(7.W)
  val cycles = UInt(64.W)
  val stageComplete = Bool()
}

class GdnRuntimeChunkLoadPrepPort extends Bundle {
  val job = Flipped(Decoupled(new GdnRuntimeChunkLoadPrepJob))
  val committed = Input(new GdnChunkCommittedState)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val scalar = new GdnScalarClient
  val done = Decoupled(new GdnRuntimeChunkLoadPrepResult)
  val resetRequired = Output(Bool())
}

/** Only chunk phase1: 64 ordered binary32 Add calls and prepared Q/K/V copies.
  * No scalar/vector unit is instantiated; uses the existing shared scalar Add
  * (RNE, after-rounding tininess, legacy error policy). Exact subnormals/zero
  * are not rejected merely for their exponent. Q is already scaled in prep.
  * Fixed maximum32 interface, runtime16/32 value heads, keyHeads always16.
  * Prepared row bytes are 25600/51200, matching the existing grouped recipe
  * and unified state-transfer owner's complete-span checks. No compact layout
  * is accepted. Q/K repetition belongs to the prepared producer, not here.
  * No exp, derived QK, Matrix, solve, state-update or root publication exists.
  *
  * One memory OR scalar request is outstanding at a time. MemoryResponse has
  * no nbytes; requests require aligned full 64 B beats and exactly one matching
  * response. The scalar ABI has no tag, hence requires exclusive service and
  * no stale returns. Neither contract provides replay protection. A response
  * arriving at issue must be held until the next wait cycle to be consumed.
  * Errors lock after held done; partial private writes are not rolled back.
  * Reset recovery must also reset/drain shared scalar and memory transport.
  */
class GdnRuntimeChunkLoadPrepOwner extends Module {
  import GdnChunkGeometry._
  private val stateBytes = GdnChunkAddressPlan.PerHeadStateBytes
  private val chunkBytes = GdnChunkAddressPlan.PerHeadChunkBytes
  private val stride16 = stateBytes + chunkBytes
  private val stride128 = stateBytes + 2 * chunkBytes
  private val phaseBytes = 102400
  private val qkvOffsets = Seq(4096, 36864, 69632)
  require(KeyDim == 128 && ValueDim == 128 && ChunkRows == 64 && BeatBytes == 64)
  require(stateBytes == 65536 && chunkBytes == 806912 && stride16 == 872448 && stride128 == 1679360)
  require(GdnChunkAddressPlan.Shapes.take(4).map(_.name) == Vector("gates", "q", "k", "v"))
  require(GdnChunkAddressPlan.Shapes.take(4).map(_.bytes).sum == phaseBytes)
  require((1 to 3).map(i => GdnChunkAddressPlan.Shapes.take(i).map(_.bytes).sum) == qkvOffsets)

  val io = IO(new GdnRuntimeChunkLoadPrepPort)
  val idle :: issueRead :: waitRead :: issueAdd :: waitAdd :: issueWrite :: waitWrite :: finish :: locked :: Nil = Enum(9)
  val state = RegInit(idle)
  val tag = RegInit(0.U(32.W))
  val generation = RegInit(0.U(32.W))
  val head = RegInit(0.U(5.W))
  val activeValueHeads = RegInit(16.U(6.W))
  val chunk = RegInit(0.U(1.W))
  val tokens = RegInit(0.U(16.W))
  val inputBase = RegInit(0.U(64.W))
  val chunkBase = RegInit(0.U(64.W))
  val row = RegInit(0.U(6.W))
  val role = RegInit(0.U(2.W)) // 0 gate; 1 Q; 2 K; 3 V
  val beat = RegInit(0.U(3.W))
  val sequence = RegInit(0.U(32.W))
  val payload = RegInit(0.U(512.W))
  val cumulative = RegInit(0.U(32.W))
  val memoryOutstanding = RegInit(false.B)
  val scalarOutstanding = RegInit(false.B)
  val status = RegInit(Status.Ok.U(8.W))
  val readBytes = RegInit(0.U(64.W))
  val writeBytes = RegInit(0.U(64.W))
  val addRequests = RegInit(0.U(7.W))
  val addResults = RegInit(0.U(7.W))
  val cycles = RegInit(0.U(64.W))
  val token = Cat(chunk, row)
  val validRow = token.pad(16) < tokens
  // Prepared producer already applies official Q/K repeat_interleave ordering.
  // All three role sections therefore have valueHeads * 128 FP32 words.
  val roleBytes = (activeValueHeads.pad(66) << 9)
  val preparedRowBytes = (activeValueHeads.pad(66) * 1600.U)
  val roleInputOffset = MuxLookup(role, 0.U(66.W))(Seq(1.U -> 0.U(66.W), 2.U -> roleBytes, 3.U -> (roleBytes << 1)))
  val roleScratchOffset = MuxLookup(role, 0.U(66.W))(Seq(1.U -> 4096.U(66.W), 2.U -> 36864.U(66.W), 3.U -> 69632.U(66.W)))
  val inputRow = inputBase.pad(66) + (token * preparedRowBytes).pad(66)
  val gateReadAddress = inputRow + roleBytes * 3.U + (head.pad(66) << 6)
  val vectorReadAddress = inputRow + roleInputOffset + (head.pad(66) << 9) + (beat.pad(66) << 6)
  val gateWriteAddress = chunkBase.pad(66) + (row.pad(66) << 6)
  val vectorWriteAddress = chunkBase.pad(66) + roleScratchOffset + (row.pad(66) << 9) + (beat.pad(66) << 6)
  val readAddress = Mux(role === 0.U, gateReadAddress, vectorReadAddress)
  val writeAddress = Mux(role === 0.U, gateWriteAddress, vectorWriteAddress)

  io.job.ready := state === idle
  io.memory.valid := state === issueRead || state === issueWrite
  io.memory.bits.write := state === issueWrite
  io.memory.bits.address := Mux(state === issueWrite, writeAddress(63, 0), readAddress(63, 0))
  io.memory.bits.data := Mux(state === issueWrite, payload, 0.U(512.W))
  io.memory.bits.mask := Mux(state === issueWrite, Fill(64, 1.U(1.W)), 0.U(64.W))
  io.memory.bits.tag := Cat(tag, sequence)
  io.response.ready := state === waitRead || state === waitWrite
  io.scalar.request.valid := state === issueAdd
  io.scalar.request.bits.op := ScalarOp.Add.U
  io.scalar.request.bits.a := cumulative
  io.scalar.request.bits.b := payload(31, 0)
  io.scalar.result.ready := state === waitAdd
  val locallyDrained = !memoryOutstanding && !scalarOutstanding
  io.done.valid := state === finish
  io.done.bits.receipt.tag := tag
  io.done.bits.receipt.expectedGeneration := generation
  io.done.bits.receipt.head := head
  io.done.bits.receipt.chunk := chunk
  io.done.bits.receipt.phase := 1.U
  io.done.bits.receipt.status := status
  io.done.bits.receipt.scratchAckBytes := writeBytes
  io.done.bits.receipt.outputAckBytes := 0.U
  io.done.bits.receipt.stateAckBytes := 0.U
  io.done.bits.receipt.drained := state === finish && status === Status.Ok.U && locallyDrained
  io.done.bits.readBytes := readBytes
  io.done.bits.addRequests := addRequests
  io.done.bits.addResults := addResults
  io.done.bits.cycles := cycles
  io.done.bits.stageComplete := state === finish && status === Status.Ok.U && locallyDrained &&
    writeBytes === phaseBytes.U && addRequests === 64.U && addResults === 64.U
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  def finite(word: UInt): Bool = word(30, 23) =/= "hff".U

  when(io.job.fire) {
    val j = io.job.bits
    val c = j.context
    tag := c.tag; generation := c.expectedGeneration; head := j.head; chunk := j.chunk
    activeValueHeads := j.valueHeads
    tokens := c.tokens; inputBase := c.input
    row := 0.U; role := 0.U; beat := 0.U; sequence := 0.U; payload := 0.U; cumulative := 0.U
    memoryOutstanding := false.B; scalarOutstanding := false.B
    status := Status.Ok.U; readBytes := 0.U; writeBytes := 0.U; addRequests := 0.U; addResults := 0.U; cycles := 0.U
    val is128 = c.tokens === 128.U
    val stride = Mux(is128, stride128.U, stride16.U)
    val selectedChunk = c.scratch.pad(66) + (j.head * stride).pad(66) + stateBytes.U + (j.chunk * chunkBytes.U).pad(66)
    chunkBase := selectedChunk(63, 0)
    val inputBytes = (c.tokens * j.valueHeads * 1600.U).pad(66)
    val outputBytes = (c.tokens * j.valueHeads * 256.U).pad(66)
    val totalStateBytes = (j.valueHeads * 65536.U).pad(66)
    val scratchBytes = (j.valueHeads * stride).pad(66)
    val spans = Seq((c.input, inputBytes), (c.stateIn, totalStateBytes),
      (c.stateOut, totalStateBytes), (c.output, outputBytes), (c.scratch, scratchBytes))
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
    val p = j.prepReady
    val prepReady = p.tag === c.tag && p.expectedGeneration === c.expectedGeneration && p.tokens === c.tokens &&
      p.input === c.input && p.status === Status.Ok.U && p.writeBytes === inputBytes &&
      p.preparedComplete && p.drained && !p.recurrentMode && p.layoutId === 0.U &&
      p.layoutVersion === 1.U && p.rowBytes === j.valueHeads * 1600.U &&
      p.keyHeads === j.keyHeads && p.valueHeads === j.valueHeads
    def sameReceipt(r: GdnChunkStageReceipt, phase: Int): Bool =
      r.tag === c.tag && r.expectedGeneration === c.expectedGeneration && r.head === j.head &&
        r.chunk === 0.U && r.phase === phase.U && r.status === Status.Ok.U && r.drained
    val initialReady = sameReceipt(j.initialReady, 0) && j.initialReady.scratchAckBytes === stateBytes.U &&
      j.initialReady.outputAckBytes === 0.U && j.initialReady.stateAckBytes === 0.U
    val previousStateReady = sameReceipt(j.previousStateReady, 16) && j.previousStateReady.scratchAckBytes === stateBytes.U &&
      j.previousStateReady.outputAckBytes === 0.U && j.previousStateReady.stateAckBytes === 0.U
    val previousOutputReady = sameReceipt(j.previousOutputReady, 17) && j.previousOutputReady.outputAckBytes === 16384.U &&
      j.previousOutputReady.scratchAckBytes === 0.U && j.previousOutputReady.stateAckBytes === 0.U
    when(rootBad) { fail(Status.Dependency.U) }
      .elsewhen((c.tokens =/= 16.U && c.tokens =/= 128.U) || j.keyHeads =/= 16.U ||
        (j.valueHeads =/= 16.U && j.valueHeads =/= 32.U) || j.head >= j.valueHeads ||
        j.chunk >= Mux(is128, 2.U, 1.U) || c.expectedGeneration === "hffffffff".U || badAddress || aliases) { fail(Status.Bounds.U) }
      .elsewhen(c.vectorPolicy =/= GdnChunkVectorPolicy.LegacyFatalUnderflow.U) { fail(Status.Unsupported.U) }
      .elsewhen(!prepReady || !Mux(j.chunk === 0.U, initialReady, previousStateReady && previousOutputReady)) { fail(Status.Dependency.U) }
      .otherwise { state := issueRead }
  }
  when(io.memory.fire) {
    memoryOutstanding := true.B
    state := Mux(state === issueRead, waitRead, waitWrite)
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { memoryOutstanding := false.B; fail(Status.Memory.U) }
      .otherwise {
        memoryOutstanding := false.B; sequence := sequence + 1.U
        when(state === waitRead) {
          readBytes := readBytes + BeatBytes.U
          val finiteBeat = (0 until 16).map(i => finite(r.data(32*i+31, 32*i))).reduce(_ && _)
          val g = r.data(31, 0)
          val beta = r.data(63, 32)
          val gateDomain = (g(31) || g(30, 0) === 0.U) && (!beta(31) || beta(30, 0) === 0.U) &&
            beta(30, 0) <= "h3f800000".U && r.data(511, 64) === 0.U
          when(!finiteBeat || (role === 0.U && !gateDomain)) { fail(Status.Numerical.U) }
            .otherwise { payload := r.data; state := Mux(role === 0.U, issueAdd, issueWrite) }
        }.otherwise {
          writeBytes := writeBytes + BeatBytes.U
          when(role === 0.U) {
            role := 1.U; beat := 0.U; payload := 0.U
            state := Mux(validRow, issueRead, issueWrite)
          }.elsewhen(beat =/= 7.U) {
            beat := beat + 1.U; payload := 0.U; state := Mux(validRow, issueRead, issueWrite)
          }.elsewhen(role =/= 3.U) {
            role := role + 1.U; beat := 0.U; payload := 0.U; state := Mux(validRow, issueRead, issueWrite)
          }.elsewhen(row === 63.U) { state := finish }
            .otherwise {
              row := row + 1.U; role := 0.U; beat := 0.U; payload := 0.U
              state := Mux((token +& 1.U) < tokens, issueRead, issueAdd)
            }
        }
      }
  }
  when(io.scalar.request.fire) { scalarOutstanding := true.B; addRequests := addRequests + 1.U; state := waitAdd }
  when(io.scalar.result.fire) {
    scalarOutstanding := false.B
    when(io.scalar.error || !finite(io.scalar.result.bits)) { fail(Status.Numerical.U) }
      .otherwise {
        cumulative := io.scalar.result.bits; addResults := addResults + 1.U
        payload := Cat(0.U(448.W), payload(63, 32), io.scalar.result.bits)
        state := issueWrite
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
