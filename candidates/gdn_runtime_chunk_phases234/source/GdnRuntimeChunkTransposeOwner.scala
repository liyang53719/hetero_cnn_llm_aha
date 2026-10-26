// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Private scheduler wrapper, not a public entry or authenticated receipt.
  * phase2Ready is the ACTUAL retained full phase2 result. Its decay.context
  * binds all roots/policy, not only the transaction tag. The scheduler owns
  * stable source matrices/roots throughout this job and held terminal result.
  */
class GdnRuntimeChunkTransposeJob extends Bundle {
  val context = new GdnChunkJob
  val layout = new GdnRuntimeChunkLayout
  val head = UInt(5.W)
  val chunk = UInt(1.W)
  val phase2Ready = new GdnRuntimeChunkDerivedAndPairResult
}

class GdnRuntimeChunkTransposeResult extends Bundle {
  val phase3 = new GdnChunkStageReceipt
  val phase4 = new GdnChunkStageReceipt
  val decay = new GdnRuntimeChunkPrivateDecay
  val phase3ReadBytes = UInt(64.W)
  val phase4ReadBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val phase3Complete = Bool()
  val phase4Complete = Bool()
  val stageComplete = Bool()
  val drained = Bool()
  val status = UInt(8.W)
}

class GdnRuntimeChunkTransposePort extends Bundle {
  val job = Flipped(Decoupled(new GdnRuntimeChunkTransposeJob))
  val committed = Input(new GdnChunkCommittedState)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val done = Decoupled(new GdnRuntimeChunkTransposeResult)
  val resetRequired = Output(Bool())
}

/** Complete phases3 then4 only. One 16x16 FP32 tile =1024 payload bytes;
  * context/decay/counters/control are additional. No Module/ALU/SRAM/service.
  * Reads reject all NaN/Inf, but finite words (including +/-0/subnormals) move
  * bitwise. Read all16 rows before writing any row of the transposed tile.
  *
  * Single outstanding original64B memory ABI; response has NO nbytes.
  * Wrong tag is checked before error. Error retirement locks this owner; it
  * does not drain/quarantine the shared fabric or roll back partial writes.
  * Recovery requires coordinated transport/owner reset, not owner-only clear.
  * Accepted responses are assumed unique/no-stale, not replay authenticated.
  */
// Fixed maximum32 candidate: one hardware implementation for runtime16/32.
// Existing payload registers, micro-order and shared service contracts unchanged.
// Full phases5-17/coordinator/root publication are NOT implemented here.
class GdnRuntimeChunkTransposeOwner extends Module {
  import GdnChunkGeometry._
  private val stateBytes = GdnChunkAddressPlan.PerHeadStateBytes
  private val chunkBytes = GdnChunkAddressPlan.PerHeadChunkBytes
  private val stride16 = stateBytes + chunkBytes
  private val stride128 = stateBytes + 2 * chunkBytes
  require(KeyDim == 128 && ValueDim == 128 && ChunkRows == 64 && BeatBytes == 64)
  require(stateBytes == 65536 && chunkBytes == 806912 && stride16 == 872448 && stride128 == 1679360)
  private val offsets = Map("k" -> 36864, "ke" -> 233472, "kt" -> 266240, "ket" -> 299008)
  offsets.foreach { case (name, offset) =>
    val i = GdnChunkAddressPlan.Shapes.indexWhere(_.name == name)
    require(i >= 0 && GdnChunkAddressPlan.Shapes.take(i).map(_.bytes).sum == offset)
    require(GdnChunkAddressPlan.Shapes(i).bytes == 32768)
  }
  require(GdnChunkAddressPlan.Phases(2).writes == Vector("kt"))
  require(GdnChunkAddressPlan.Phases(3).writes == Vector("ket"))

  val io = IO(new GdnRuntimeChunkTransposePort)
  val idle :: issueRead :: waitRead :: issueWrite :: waitWrite :: finish :: locked :: Nil = Enum(7)
  val state = RegInit(idle)
  val context = RegInit(0.U.asTypeOf(new GdnChunkJob))
  val layout = RegInit(0.U.asTypeOf(new GdnRuntimeChunkLayout))
  val head = RegInit(0.U(5.W)); val chunk = RegInit(0.U(1.W))
  val chunkBase = RegInit(0.U(64.W))
  val decayValue = RegInit(0.U(32.W))
  val second = RegInit(false.B) // false:phase3, true:phase4
  val phase3Done = RegInit(false.B)
  val tileRow = RegInit(0.U(2.W)); val tileCol = RegInit(0.U(3.W))
  val index = RegInit(0.U(4.W))
  val tile = RegInit(VecInit(Seq.fill(16)(0.U(512.W)))) // exactly1024B payload
  val sequence = RegInit(0.U(32.W))
  val outstanding = RegInit(false.B)
  val status = RegInit(Status.Ok.U(8.W))
  val readBytes = RegInit(VecInit(Seq.fill(2)(0.U(64.W))))
  val writeBytes = RegInit(VecInit(Seq.fill(2)(0.U(64.W))))
  val cycles = RegInit(0.U(64.W))
  def finite(word: UInt): Bool = word(30, 23) =/= "hff".U
  def finiteBeat(words: UInt): Bool = (0 until 16).map(i => finite(words(32*i+31, 32*i))).reduce(_ && _)
  def fail(code: UInt): Unit = { status := code; state := finish }

  val sourceOffset = Mux(second, 233472.U(66.W), 36864.U(66.W))
  val destinationOffset = Mux(second, 299008.U(66.W), 266240.U(66.W))
  val sourceAddress = chunkBase.pad(66) + sourceOffset + (Cat(tileRow, index).pad(66) << 9) + (tileCol.pad(66) << 6)
  val destinationAddress = chunkBase.pad(66) + destinationOffset + (Cat(tileCol, index).pad(66) << 8) + (tileRow.pad(66) << 6)
  val transposed = Wire(Vec(16, UInt(32.W)))
  for (j <- 0 until 16) { transposed(j) := (tile(j) >> (index << 5))(31, 0) }

  io.job.ready := state === idle
  io.memory.valid := state === issueRead || state === issueWrite
  io.memory.bits.write := state === issueWrite
  io.memory.bits.address := Mux(state === issueWrite, destinationAddress(63, 0), sourceAddress(63, 0))
  io.memory.bits.data := Mux(state === issueWrite, transposed.asUInt, 0.U(512.W))
  io.memory.bits.mask := Mux(state === issueWrite, Fill(64, 1.U(1.W)), 0.U(64.W))
  io.memory.bits.tag := Cat(context.tag, sequence)
  io.response.ready := state === waitRead || state === waitWrite

  val complete = state === finish && status === Status.Ok.U && !outstanding && second && phase3Done &&
    readBytes(0) === 32768.U && writeBytes(0) === 32768.U && readBytes(1) === 32768.U && writeBytes(1) === 32768.U
  io.done.valid := state === finish
  for ((receipt, p) <- Seq((io.done.bits.phase3, 0), (io.done.bits.phase4, 1))) {
    receipt.tag := context.tag; receipt.expectedGeneration := context.expectedGeneration
    receipt.head := head; receipt.chunk := chunk; receipt.phase := (p + 3).U
    receipt.status := (if (p == 0) Mux(phase3Done, Status.Ok.U, status) else status)
    receipt.scratchAckBytes := writeBytes(p)
    receipt.outputAckBytes := 0.U; receipt.stateAckBytes := 0.U
    receipt.drained := (if (p == 0) phase3Done else complete)
  }
  io.done.bits.decay.context := context
  io.done.bits.decay.layout := layout
  io.done.bits.decay.head := head; io.done.bits.decay.chunk := chunk
  io.done.bits.decay.value := Mux(complete, decayValue, 0.U)
  io.done.bits.decay.valid := complete
  io.done.bits.phase3ReadBytes := readBytes(0); io.done.bits.phase4ReadBytes := readBytes(1)
  io.done.bits.cycles := cycles
  io.done.bits.phase3Complete := phase3Done
  io.done.bits.phase4Complete := complete; io.done.bits.stageComplete := complete
  io.done.bits.drained := complete; io.done.bits.status := status
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }

  when(io.job.fire) {
    val j = io.job.bits; val c = j.context; val r = j.phase2Ready; val p = r.receipt; val d = r.decay
    context := c; layout := j.layout; head := j.head; chunk := j.chunk; decayValue := d.value
    second := false.B; phase3Done := false.B
    tileRow := 0.U; tileCol := 0.U; index := 0.U; tile.foreach(_ := 0.U)
    sequence := 0.U; outstanding := false.B; status := Status.Ok.U
    readBytes.foreach(_ := 0.U); writeBytes.foreach(_ := 0.U); cycles := 0.U
    val is128 = c.tokens === 128.U
    val stride = Mux(is128, stride128.U, stride16.U)
    val selectedChunk = c.scratch.pad(66) + (j.head * stride).pad(66) + stateBytes.U + (j.chunk * chunkBytes.U).pad(66)
    chunkBase := selectedChunk(63, 0)
    // Same expanded prepared allocation as runtime LoadPrep/state-transfer.
    // This leaf only reads per-head scratch; it never remaps head//2 again.
    val inputBytes = (c.tokens * j.layout.valueHeads * 1600.U).pad(66)
    val outputBytes = (c.tokens * j.layout.valueHeads * 256.U).pad(66)
    val totalStateBytes = (j.layout.valueHeads * 65536.U).pad(66)
    val scratchBytes = (j.layout.valueHeads * stride).pad(66)
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
    val phase2Qualified = r.stageComplete && p.tag === c.tag && p.expectedGeneration === c.expectedGeneration &&
      p.head === j.head && p.chunk === j.chunk && p.phase === 2.U &&
      p.status === Status.Ok.U && p.drained && p.scratchAckBytes === 180224.U &&
      p.outputAckBytes === 0.U && p.stateAckBytes === 0.U && r.readBytes === 235584.U &&
      r.expRequests === 2209.U && r.expResults === 2209.U && r.addRequests === 2144.U && r.addResults === 2144.U &&
      r.mulRequests === 2560.U && r.mulResults === 2560.U && d.valid && finite(d.value) &&
      d.context.asUInt === c.asUInt && d.layout.asUInt === j.layout.asUInt &&
      d.head === j.head && d.chunk === j.chunk
    when(rootBad) { fail(Status.Dependency.U) }
      .elsewhen((c.tokens =/= 16.U && c.tokens =/= 128.U) ||
        !GdnRuntimeChunkLayout.admitted(j.layout) || j.head >= j.layout.valueHeads ||
        j.chunk >= Mux(is128, 2.U, 1.U) || c.expectedGeneration === "hffffffff".U || badAddress || aliases) { fail(Status.Bounds.U) }
      .elsewhen(c.vectorPolicy =/= GdnChunkVectorPolicy.LegacyFatalUnderflow.U) { fail(Status.Unsupported.U) }
      .elsewhen(!phase2Qualified) { fail(Status.Dependency.U) }
      .elsewhen(io.response.valid) { fail(Status.Protocol.U) }
      .otherwise { state := issueRead }
  }

  when(io.memory.fire) { outstanding := true.B; state := Mux(state === issueRead, waitRead, waitWrite) }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(context.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { outstanding := false.B; fail(Status.Memory.U) }
      .otherwise {
        outstanding := false.B; sequence := sequence + 1.U
        when(state === waitRead) {
          readBytes(second.asUInt) := readBytes(second.asUInt) + BeatBytes.U
          when(!finiteBeat(r.data)) { fail(Status.Numerical.U) }
            .otherwise {
              tile(index) := r.data
              when(index === 15.U) { index := 0.U; state := issueWrite }
                .otherwise { index := index + 1.U; state := issueRead }
            }
        }.otherwise {
          writeBytes(second.asUInt) := writeBytes(second.asUInt) + BeatBytes.U
          when(index =/= 15.U) { index := index + 1.U; state := issueWrite }
            .otherwise {
              index := 0.U
              when(tileCol =/= 7.U) { tileCol := tileCol + 1.U; state := issueRead }
                .elsewhen(tileRow =/= 3.U) { tileCol := 0.U; tileRow := tileRow + 1.U; state := issueRead }
                .otherwise {
                  when(readBytes(second.asUInt) =/= 32768.U || writeBytes(second.asUInt) =/= 32704.U) { fail(Status.Protocol.U) }
                    .elsewhen(!second) {
                      // Real phase3 ACK checkpoint; never inferred from caller readiness.
                      phase3Done := true.B; second := true.B; tileRow := 0.U; tileCol := 0.U; state := issueRead
                    }.otherwise { state := finish }
                }
            }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
