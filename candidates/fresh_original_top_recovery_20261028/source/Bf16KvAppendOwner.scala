// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Internal typed job, not a Host opcode or the legacy owner kind 7 ABI.
  * Inputs are contiguous BF16 [tokens,2,256]. The combined cache is BF16
  * [2,capacityTokens,512]: K starts at cacheBase, V at cacheBase+capacity*1024.
  * Each token occupies 1024 bytes in each plane. Only the two append tails
  * [appendStart,appendStart+tokens) may be written.
  *
  * cacheBase/capacityTokens/currentLength/currentGeneration are trusted metadata
  * supplied by the Host. expected* bind the requested append to that snapshot.
  * This owner cannot authenticate an invented snapshot; Host must serialize
  * jobs, validate the cache identity/capacity and retain the published metadata
  * across an owner reset. cold is valid only for length=0 and generation=0.
  */
class Bf16KvAppendJob extends Bundle {
  val tokens = UInt(16.W)
  val kvHeads = UInt(16.W)
  val headDim = UInt(16.W)
  val keyInput = UInt(64.W)
  val valueInput = UInt(64.W)
  val cacheBase = UInt(64.W)
  val capacityTokens = UInt(32.W)
  val appendStart = UInt(32.W)
  val currentLength = UInt(32.W)
  val expectedLength = UInt(32.W)
  val currentGeneration = UInt(32.W)
  val expectedGeneration = UInt(32.W)
  val cold = Bool()
  val tag = UInt(32.W)
}

class Bf16KvAppendResult extends Bundle {
  val tag = UInt(32.W)
  val cacheBase = UInt(64.W)
  val capacityTokens = UInt(32.W)
  val status = UInt(8.W)
  val writeBytes = UInt(64.W) // Matching, successful write ACKs only.
  val cycles = UInt(64.W)
  // A staging-completion proposal, NOT publication of global cache state.
  // The Host may publish only at its whole-block fence. Before that fence it
  // must retain the previous published snapshot, even after consuming done.
  val proposalValid = Bool()
  val proposedLength = UInt(32.W)
  val proposedGeneration = UInt(32.W)
}

class Bf16KvAppendOwnerPort extends Bundle {
  val job = Flipped(Decoupled(new Bf16KvAppendJob))
  val done = Decoupled(new Bf16KvAppendResult)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val resetRequired = Output(Bool())
}

/** BF16 bit-preserving append using the retained external Memory transport.
  * One 64-byte beat is buffered; no transport, arithmetic, Matrix or SFU is
  * instantiated. Every store is aligned and full64, including both final
  * stores. Full input allocations and the ENTIRE cache allocation are pairwise
  * disjoint, so a failure in either tail cannot modify the published prefix.
  *
  * The two tails become eligible for a length/generation proposal together,
  * after BOTH final matching write ACKs. An error poisons the owner until
  * reset. Physical staging writes may survive failure/reset, but remain
  * outside the published length. Retry uses the Host's prior trusted snapshot
  * and rewrites both tails. Jointly reset/drain the external memory transport
  * before reuse; resetting this owner alone does not cancel in-flight DMA.
  */
class Bf16KvAppendOwner(maxTokens: Int = 128) extends Module {
  require(maxTokens >= 1 && maxTokens <= 128)
  val io = IO(new Bf16KvAppendOwnerPort)
  val idle :: readInput :: waitInput :: writeTail :: waitTail :: finish :: locked :: Nil = Enum(7)
  val state = RegInit(idle)
  val job = Reg(new Bf16KvAppendJob)
  val valuePlane = RegInit(false.B)
  val beat = RegInit(0.U(11.W)) // At most 128*16 beats per plane.
  val data = Reg(UInt(512.W))
  val sequence = RegInit(0.U(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))

  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag
  io.done.bits.cacheBase := job.cacheBase
  io.done.bits.capacityTokens := job.capacityTokens
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.proposalValid := state === finish && status === Status.Ok.U
  io.done.bits.proposedLength := job.currentLength + Mux(io.done.bits.proposalValid, job.tokens, 0.U)
  io.done.bits.proposedGeneration := job.currentGeneration + Mux(io.done.bits.proposalValid, 1.U, 0.U)
  io.resetRequired := status =/= Status.Ok.U

  val beatOffset = (beat << 6).pad(65)
  val planeOffset = Mux(valuePlane, (job.capacityTokens << 10).pad(65), 0.U)
  val appendOffset = (job.appendStart << 10).pad(65)
  val inputAddress = Mux(valuePlane, job.valueInput, job.keyInput).pad(65) + beatOffset
  val tailAddress = job.cacheBase.pad(65) + planeOffset + appendOffset + beatOffset
  io.memory.valid := state === readInput || state === writeTail
  io.memory.bits.write := state === writeTail
  io.memory.bits.address := Mux(state === writeTail, tailAddress, inputAddress)
  io.memory.bits.data := Mux(state === writeTail, data, 0.U)
  io.memory.bits.mask := Mux(state === writeTail, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitInput || state === waitTail

  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  when(io.job.fire) {
    job := io.job.bits
    valuePlane := false.B; beat := 0.U; sequence := 0.U
    status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val inputBytes = (j.tokens << 10).pad(65)
    val cacheBytes = (j.capacityTokens << 11).pad(65)
    val appendEnd = j.appendStart.pad(65) + j.tokens.pad(65)
    // The retained iDMA/AXI aperture ends at 2^56. Widen before adding;
    // neither 64-bit wrap nor a legal tail inside an illegal cache is allowed.
    def badSpan(base: UInt, size: UInt): Bool =
      base(5, 0) =/= 0.U || base.pad(65) + size > (BigInt(1) << 56).U
    def overlap(a: UInt, na: UInt, b: UInt, nb: UInt): Bool =
      a.pad(65) < b.pad(65) + nb && b.pad(65) < a.pad(65) + na
    val badAddress = badSpan(j.keyInput, inputBytes) || badSpan(j.valueInput, inputBytes) ||
      badSpan(j.cacheBase, cacheBytes)
    val alias = overlap(j.keyInput, inputBytes, j.valueInput, inputBytes) ||
      overlap(j.cacheBase, cacheBytes, j.keyInput, inputBytes) ||
      overlap(j.cacheBase, cacheBytes, j.valueInput, inputBytes)
    val badGeometry = j.tokens === 0.U || j.tokens > maxTokens.U || j.kvHeads =/= 2.U ||
      j.headDim =/= 256.U || j.capacityTokens === 0.U || j.currentLength > j.capacityTokens ||
      appendEnd > j.capacityTokens.pad(65)
    val wrongSnapshot = j.appendStart =/= j.currentLength || j.expectedLength =/= j.currentLength ||
      j.expectedGeneration =/= j.currentGeneration ||
      j.currentGeneration === "hffffffff".U ||
      Mux(j.cold, j.currentLength =/= 0.U || j.currentGeneration =/= 0.U,
        j.currentLength === 0.U || j.currentGeneration === 0.U)
    when(badGeometry || badAddress || alias) { fail(Status.Bounds.U) }
      .elsewhen(wrongSnapshot) { fail(Status.Dependency.U) }
      .otherwise { state := readInput }
  }
  when(io.memory.fire) { state := Mux(state === readInput, waitInput, waitTail) }
  when(io.response.fire) {
    when(io.response.bits.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(io.response.bits.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitInput) {
          data := io.response.bits.data
          state := writeTail
        }.otherwise {
          bytes := bytes + 64.U
          when(beat +& 1.U === (job.tokens << 4)) {
            when(valuePlane) { state := finish }
              .otherwise { valuePlane := true.B; beat := 0.U; state := readInput }
          }.otherwise { beat := beat + 1.U; state := readInput }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
