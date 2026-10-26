// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** First shared-controller increment. One no-argument elaboration admits all
  * five profiles sequentially. It latches the complete launch and decoded
  * dimensions atomically, holds dispatch/result under backpressure, and does
  * not permit config changes to retarget an in-flight transaction.
  *
  * This is NOT yet the shared arithmetic/block scheduler. It allocates no MAC,
  * no persistent tensor SRAM, and cannot by itself prove any numerical result.
  * Full region/overlap/weight/state-generation validation belongs to the typed
  * scheduler; this component checks version/shape/context/alignment only.
  */
class UnifiedBlockAdmission extends Module {
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new UnifiedBlockLaunchV1))
    val dispatch = Decoupled(new UnifiedBlockDispatchV1)
    val completion = Flipped(Decoupled(new UnifiedBlockCompletionV1))
    val result = Decoupled(new UnifiedBlockResultV1)
    val active = Output(Bool())
    val context = Output(new UnifiedBlockDispatchV1)
    val resetRequired = Output(Bool())
  })
  val idle :: dispatching :: running :: holding :: locked :: Nil = Enum(5)
  val state = RegInit(idle)
  val context = Reg(new UnifiedBlockDispatchV1)
  val result = Reg(new UnifiedBlockResultV1)
  val cycles = RegInit(0.U(64.W))
  val poisoned = RegInit(false.B)
  val nextTransaction = RegInit(0.U(64.W))
  val sequenceAvailable = nextTransaction =/= "hffffffffffffffff".U

  val launch = io.launch.bits
  val (profile, knownProfile) = UnifiedRuntimeProfile.decode(launch.profileId)
  val countOk = launch.tokens >= 1.U && launch.tokens <= UnifiedPhysicalLimits.MaxBlockTokens.U
  // Extended additions prevent UInt32 wraparound accepting a bad range.
  val positionEnd = launch.positionBase +& launch.tokens.pad(32)
  val cacheEnd = launch.cacheLength +& launch.tokens.pad(32)
  val positionOk = positionEnd <= profile.maxPosition.pad(33)
  val attention = profile.mixer === 0.U
  val cacheOk = Mux(attention,
    launch.cacheCapacity > 0.U && launch.cacheCapacity <= profile.maxPosition &&
      launch.cacheLength <= launch.cacheCapacity && cacheEnd <= launch.cacheCapacity.pad(33) &&
      (!launch.cold || launch.cacheLength === 0.U),
    launch.cacheCapacity === 0.U && launch.cacheLength === 0.U)
  def aligned(x: UInt): Bool = x(5, 0) === 0.U
  val commonAligned = Seq(launch.input, launch.weights, launch.output, launch.scratch).map(aligned).reduce(_ && _)
  val stateAligned = Mux(attention, aligned(launch.kvK) && aligned(launch.kvV),
    aligned(launch.stateOut) && (launch.cold || aligned(launch.stateIn)))
  val legal = launch.version === 1.U && launch.opcode === 0.U && knownProfile &&
    countOk && positionOk && cacheOk && commonAligned && stateAligned && sequenceAvailable

  io.launch.ready := state === idle && !poisoned
  io.dispatch.valid := state === dispatching
  io.dispatch.bits := context
  io.completion.ready := state === running
  io.result.valid := state === holding
  io.result.bits := result
  io.active := state === dispatching || state === running || state === holding
  io.context := context // valid only when io.active
  io.resetRequired := poisoned

  when(state === dispatching || state === running) { cycles := cycles + 1.U }
  when(io.launch.fire) {
    context.transactionId := nextTransaction
    when(sequenceAvailable) { nextTransaction := nextTransaction + 1.U }
    context.launch := launch
    context.profile := profile
    cycles := 0.U
    result := 0.U.asTypeOf(new UnifiedBlockResultV1)
    result.transactionId := nextTransaction
    result.version := 1.U; result.profileId := launch.profileId; result.tag := launch.tag
    when(legal) { state := dispatching }
      .otherwise { result.status := 1.U; state := holding }
  }
  when(io.dispatch.fire) { state := running }
  when(io.completion.fire) {
    val matchIdentity = io.completion.bits.tag === context.launch.tag &&
      io.completion.bits.profileId === context.launch.profileId &&
      io.completion.bits.transactionId === context.transactionId
    val safe = matchIdentity && io.completion.bits.drained
    val lock = !safe || io.completion.bits.resetRequired
    result.controlCycles := cycles + 1.U
    result.status := Mux(safe, io.completion.bits.status, 2.U)
    result.acknowledgedWriteBytes := Mux(safe, io.completion.bits.acknowledgedWriteBytes, 0.U)
    result.issuedSliceSteps := Mux(safe, io.completion.bits.issuedSliceSteps, 0.U)
    result.resetRequired := lock
    when(lock) { poisoned := true.B }
    state := holding
  }
  when(io.result.fire) { state := Mux(poisoned, locked, idle) }
}
