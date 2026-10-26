// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** One outstanding legacy owner job. Full identity stays outside the original
  * public21 tag32 ABI; low16 must remain public PC for the original router.
  * Epochs never wrap within a reset lifetime, including across block changes.
  * This does not authorize reset before external stale-response exclusion.
  * No arithmetic or memory service is instantiated here.
  */
object Qwen2Public21EpochV2 {
  def exhausted(epoch: UInt): Bool = epoch === "hffff".U
}
class Qwen2Public21TagAdapterV2 extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new UnifiedRuntimeDensePlanV2))
    val legacyJob = Decoupled(new QwenOwnerJob)
    val legacyDone = Flipped(Decoupled(new QwenOwnerResult))
    val result = Decoupled(new Bundle {
      val transactionId = UInt(64.W)
      val ownerSequence = UInt(32.W)
      val publicPc = UInt(5.W)
      val result = new QwenOwnerResult
    })
    val resetRequired = Output(Bool())
  })
  val idle :: issue :: awaitDone :: report :: locked :: Nil = Enum(5)
  val state = RegInit(idle)
  val epoch = RegInit(0.U(16.W))
  val plan = Reg(new UnifiedRuntimeDensePlanV2)
  val legacyTag = Reg(UInt(32.W))
  val receipt = Reg(new QwenOwnerResult)
  val fault = RegInit(false.B)
  val exhausted = Qwen2Public21EpochV2.exhausted(epoch)
  // Fault is a sideband quarantine, never cancellation of an already offered
  // Decoupled job/result. Existing obligations remain until real handshakes.
  val stray = io.legacyDone.valid && state =/= awaitDone
  val acceptedPlan = io.request.bits.valid &&
    io.request.bits.route === UnifiedDenseRouteV2.Qwen2Public21.U &&
    io.request.bits.qwen2Boundary.valid && io.request.bits.qwen2Boundary.dense
  val malformed = state === idle && io.request.valid && !acceptedPlan
  io.request.ready := state === idle && !fault && !exhausted && !stray && acceptedPlan
  io.legacyJob.valid := state === issue
  io.legacyJob.bits := plan.job
  io.legacyJob.bits.tag := legacyTag
  io.legacyDone.ready := state === awaitDone
  io.result.valid := state === report
  io.result.bits.transactionId := plan.context.transactionId
  io.result.bits.ownerSequence := plan.firstOwnerSequence
  io.result.bits.publicPc := plan.publicPc
  io.result.bits.result := receipt
  io.resetRequired := fault || state === locked || stray || malformed || (state === idle && exhausted)
  when(io.request.fire) {
    plan := io.request.bits
    epoch := epoch + 1.U
    legacyTag := Cat(epoch + 1.U, io.request.bits.publicPc.pad(16))
    state := issue
  }
  when(io.legacyJob.fire) { state := awaitDone }
  when(io.legacyDone.fire) {
    val d = io.legacyDone.bits
    // A wrong tag is not retirement of our accepted owner. Retain that debt
    // until its matching completion or an externally isolated reset.
    when(d.tag =/= legacyTag) {
      fault := true.B
    }.otherwise {
      receipt := d
      when(fault || d.status =/= 0.U || d.writeBytes =/= plan.job.writeBytes) {
        receipt.status := Status.Protocol.U
        fault := true.B
      }
      state := report
    }
  }
  // A fault arriving after result.valid cannot rewrite its held payload.
  // Parent must combine resetRequired with terminal/final-memory fences;
  // a held status=0 receipt alone is NOT permission to report block success.
  when(io.result.fire) { state := Mux(fault || stray, locked, idle) }
  when(stray || malformed) {
    fault := true.B
    when(state === idle) { state := locked }
  }
}
