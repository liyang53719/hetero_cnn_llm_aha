// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Private scheduler command, not a public Host opcode. Receipts must eventually
  * come from real producers; these fields alone do not prove their provenance.
  */
class GdnChunkStateTransferJob extends Bundle {
  val activeHeads = UInt(6.W) // runtime legal values are exactly 16 or 32
  val context = new GdnChunkJob
  val head = UInt(16.W)
  val operation = UInt(2.W) // 0 Initialize; 1 ExportFinal; other values rejected
  val nextStateReady = new GdnChunkStageReceipt
  val outputReady = new GdnChunkStageReceipt
}

/** Private copy completion only. No persistent root or generation publication. */
class GdnChunkStateTransferResult extends Bundle {
  val tag = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val head = UInt(16.W)
  val operation = UInt(2.W)
  val status = UInt(8.W)
  val readBytes = UInt(64.W)
  val writeBytes = UInt(64.W)
  val cycles = UInt(64.W)
  val transferComplete = Bool()
  val localDrained = Bool()
}

class GdnChunkStateTransferPort extends Bundle {
  val job = Flipped(Decoupled(new GdnChunkStateTransferJob))
  val committed = Input(new GdnChunkCommittedState)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val done = Decoupled(new GdnChunkStateTransferResult)
  val resetRequired = Output(Bool())
}

/** One-head, one-outstanding, bitwise private state transfer. No arithmetic,
  * DMA, SRAM or additional compute instance. The sole payload register is 64 B.
  * Cold writes zero initial; warm copies stateIn to initial; ExportFinal copies
  * the last chunk's next_state to private stateOut after phase 16/17 receipts.
  *
  * MemoryResponse has no nbytes or direction: only tag/error are observable.
  * The unchanged fabric must implement each aligned full-mask 64 B request with
  * exactly one response and no stale responses across successful commands. This
  * is not replay protection. A zero-latency producer must hold response.valid
  * until the following wait state accepts it. Root/source stability throughout
  * a job is the trusted scheduler's obligation, not a global lock in this unit.
  *
  * Failure may leave partial private writes; it never rolls them back or makes
  * them publishable. Any failure locks after its held result is consumed. Reset
  * recovery requires joint transport drain/reset, not resetting this unit alone.
  */
class GdnChunkStateTransferOwner extends Module {
  import GdnChunkGeometry._
  private val stateBytes = GdnChunkAddressPlan.PerHeadStateBytes
  private val chunkBytes = GdnChunkAddressPlan.PerHeadChunkBytes
  private val nextIndex = GdnChunkAddressPlan.Shapes.indexWhere(_.name == "next_state")
  private val nextOffset = GdnChunkAddressPlan.Shapes.take(nextIndex).map(_.bytes).sum
  private val stride16 = stateBytes + chunkBytes
  private val stride128 = stateBytes + 2 * chunkBytes
  private val next16 = stateBytes + nextOffset
  private val next128 = stateBytes + chunkBytes + nextOffset
  require(KeyDim == 128 && ValueDim == 128 && BeatBytes == 64)
  // Fixed maximum-32 physical controller and receipt interface. activeHeads is
  // consumed only on job.fire; all live addresses are latched before DMA.
  // There is no model-specific elaboration, payload bank, or arithmetic unit.
  private def scratchSpanBytes(tokens: Int, activeHeads: Int): BigInt =
    BigInt(activeHeads) * (stateBytes + GdnChunkAddressPlan.chunks(tokens) * chunkBytes)
  require(scratchSpanBytes(16, 16) == GdnChunkAddressPlan.scratchBytes(16))
  require(scratchSpanBytes(128, 16) == GdnChunkAddressPlan.scratchBytes(128))
  require(nextIndex == 23 && stateBytes == 65536 && chunkBytes == 806912)
  require(nextOffset == 741376 && stride16 == 872448 && stride128 == 1679360)
  require(next16 == 806912 && next128 == 1613824)

  val io = IO(new GdnChunkStateTransferPort)
  val idle :: issueRead :: waitRead :: issueWrite :: waitWrite :: finish :: locked :: Nil = Enum(7)
  val state = RegInit(idle)
  val tag = RegInit(0.U(32.W))
  val generation = RegInit(0.U(32.W))
  val head = RegInit(0.U(16.W))
  val operation = RegInit(0.U(2.W))
  val zeroFill = RegInit(false.B)
  val sourceBase = RegInit(0.U(64.W))
  val targetBase = RegInit(0.U(64.W))
  val beat = RegInit(0.U(10.W))
  val sequence = RegInit(0.U(32.W))
  val payload = RegInit(0.U(512.W))
  val outstanding = RegInit(false.B)
  val status = RegInit(Status.Ok.U(8.W))
  val readBytes = RegInit(0.U(64.W))
  val writeBytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.memory.valid := state === issueRead || state === issueWrite
  io.memory.bits.write := state === issueWrite
  val beatOffset = beat.pad(66) << 6
  val readAddress = sourceBase.pad(66) + beatOffset
  val writeAddress = targetBase.pad(66) + beatOffset
  io.memory.bits.address := Mux(state === issueWrite, writeAddress(63, 0), readAddress(63, 0))
  io.memory.bits.data := Mux(state === issueWrite && !zeroFill, payload, 0.U(512.W))
  io.memory.bits.mask := Mux(state === issueWrite, Fill(64, 1.U(1.W)), 0.U(64.W))
  io.memory.bits.tag := Cat(tag, sequence)
  io.response.ready := state === waitRead || state === waitWrite

  io.done.valid := state === finish
  io.done.bits.tag := tag
  io.done.bits.expectedGeneration := generation
  io.done.bits.head := head
  io.done.bits.operation := operation
  io.done.bits.status := status
  io.done.bits.readBytes := readBytes
  io.done.bits.writeBytes := writeBytes
  io.done.bits.cycles := cycles
  io.done.bits.transferComplete := state === finish && status === Status.Ok.U &&
    writeBytes === stateBytes.U && !outstanding
  // An error can hide a downstream tag mismatch remapped by SharedMemoryArbiter.
  io.done.bits.localDrained := state === finish && status === Status.Ok.U && !outstanding
  io.resetRequired := status =/= Status.Ok.U
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }

  when(io.job.fire) {
    val j = io.job.bits
    val c = j.context
    tag := c.tag; generation := c.expectedGeneration; head := j.head; operation := j.operation
    beat := 0.U; sequence := 0.U; payload := 0.U; outstanding := false.B
    status := Status.Ok.U; readBytes := 0.U; writeBytes := 0.U; cycles := 0.U
    zeroFill := j.operation === 0.U && c.cold
    val is128 = c.tokens === 128.U
    val stride = Mux(is128, stride128.U, stride16.U)
    val headOffset = (j.head * stride).pad(66)
    val initial = c.scratch.pad(66) + headOffset
    val lastState = initial + Mux(is128, next128.U, next16.U)
    val externalOffset = (j.head * stateBytes.U).pad(66)
    val stateIn = c.stateIn.pad(66) + externalOffset
    val stateOut = c.stateOut.pad(66) + externalOffset
    sourceBase := Mux(j.operation === 1.U, lastState(63, 0), stateIn(63, 0))
    targetBase := Mux(j.operation === 1.U, stateOut(63, 0), initial(63, 0))

    val is32 = j.activeHeads === 32.U
    val preparedRowBytes = Mux(is32, 51200.U, 25600.U)
    val outputRowBytes = Mux(is32, 8192.U, 4096.U)
    val totalStateBytes = Mux(is32, 2097152.U(66.W), 1048576.U(66.W))
    val inputBytes = (c.tokens * preparedRowBytes).pad(66)
    val outputBytes = (c.tokens * outputRowBytes).pad(66)
    val scratchBytes = Mux(is32,
      Mux(is128, scratchSpanBytes(128, 32).U(66.W), scratchSpanBytes(16, 32).U(66.W)),
      Mux(is128, scratchSpanBytes(128, 16).U(66.W), scratchSpanBytes(16, 16).U(66.W)))
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
    def sameReceipt(r: GdnChunkStageReceipt, phase: Int): Bool =
      r.tag === c.tag && r.expectedGeneration === c.expectedGeneration &&
        r.head.pad(16) === j.head && r.chunk === Mux(is128, 1.U, 0.U) &&
        r.phase === phase.U && r.status === Status.Ok.U && r.drained
    val nextReady = sameReceipt(j.nextStateReady, 16) &&
      j.nextStateReady.scratchAckBytes === stateBytes.U &&
      j.nextStateReady.outputAckBytes === 0.U && j.nextStateReady.stateAckBytes === 0.U
    val outputReady = sameReceipt(j.outputReady, 17) &&
      j.outputReady.outputAckBytes === Mux(is128, 16384.U, 4096.U) &&
      j.outputReady.scratchAckBytes === 0.U && j.outputReady.stateAckBytes === 0.U
    when(rootBad) { fail(Status.Dependency.U) }
      .elsewhen((c.tokens =/= 16.U && c.tokens =/= 128.U) || (j.activeHeads =/= 16.U && j.activeHeads =/= 32.U) ||
        j.head >= j.activeHeads ||
        c.expectedGeneration === "hffffffff".U || badAddress || aliases) { fail(Status.Bounds.U) }
      .elsewhen(j.operation > 1.U) { fail(Status.Unsupported.U) }
      .elsewhen(j.operation === 1.U && (!nextReady || !outputReady)) { fail(Status.Dependency.U) }
      .otherwise { state := Mux(j.operation === 0.U && c.cold, issueWrite, issueRead) }
  }

  when(io.memory.fire) {
    outstanding := true.B
    state := Mux(state === issueRead, waitRead, waitWrite)
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { outstanding := false.B; fail(Status.Memory.U) }
      .otherwise {
        outstanding := false.B
        sequence := sequence + 1.U
        when(state === waitRead) {
          payload := r.data
          readBytes := readBytes + BeatBytes.U
          state := issueWrite
        }.otherwise {
          writeBytes := writeBytes + BeatBytes.U
          when(beat === (stateBytes / BeatBytes - 1).U) { state := finish }
            .otherwise {
              beat := beat + 1.U
              state := Mux(zeroFill, issueWrite, issueRead)
            }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
