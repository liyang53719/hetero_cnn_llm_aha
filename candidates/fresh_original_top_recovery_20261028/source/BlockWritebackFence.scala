// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Observes the single-outstanding MemoryRequest/Response contract.
  * A stage is publishable only after exactly expectedBytes successful write ACKs.
  * This is a hardware completion check, not a simulator PASS indicator.
  * An error poisons the request until reset; neither issue nor AW/W acceptance
  * counts as a write commit. The surrounding controller owns abort/drain.
  */
class BlockWritebackFence extends Module {
  val io = IO(new Bundle {
    val startRequest = Input(Bool())
    val startStage = Input(Bool())
    val issue = Flipped(Valid(new MemoryRequest))
    val response = Flipped(Valid(new MemoryResponse))
    val expectedBytes = Input(UInt(64.W))
    val phaseBytes = Output(UInt(64.W))
    val totalBytes = Output(UInt(64.W))
    val pending = Output(Bool())
    val error = Output(Bool())
    val canCommit = Output(Bool())
  })
  val pending = RegInit(false.B)
  val write = RegInit(false.B)
  val tag = RegInit(0.U(64.W))
  val byteCount = RegInit(0.U(7.W))
  val phaseBytes = RegInit(0.U(64.W))
  val totalBytes = RegInit(0.U(64.W))
  val error = RegInit(false.B)
  io.phaseBytes := phaseBytes
  io.totalBytes := totalBytes
  io.pending := pending
  io.error := error
  io.canCommit := !pending && !error && phaseBytes === io.expectedBytes

  // Configuration events are legal only at a quiescent request/stage boundary.
  when(io.startRequest || io.startStage) {
    when(pending || io.issue.valid || io.response.valid) { error := true.B }
    phaseBytes := 0.U
    when(io.startRequest) { totalBytes := 0.U }
  }
  when(io.response.valid) {
    pending := false.B
    when(!pending || io.response.bits.tag =/= tag || io.response.bits.error) {
      error := true.B
    }.elsewhen(write) {
      val phaseNext = phaseBytes +& byteCount
      val totalNext = totalBytes +& byteCount
      when(phaseNext(64) || totalNext(64) || phaseNext > io.expectedBytes) {
        error := true.B
      }.otherwise {
        phaseBytes := phaseNext(63,0)
        totalBytes := totalNext(63,0)
      }
    }
  }
  when(io.issue.valid) {
    when(pending && !io.response.valid) { error := true.B }
    when(io.issue.bits.write && !io.issue.bits.mask.orR) { error := true.B }
    pending := true.B
    write := io.issue.bits.write
    tag := io.issue.bits.tag
    byteCount := PopCount(io.issue.bits.mask)
  }
}
