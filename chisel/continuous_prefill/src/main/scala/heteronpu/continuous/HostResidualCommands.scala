// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

class HostCommandLaunch extends Bundle {
  val commandBase = UInt(64.W); val commandLimit = UInt(64.W)
  val commands = UInt(16.W)
  val descriptorBase = UInt(64.W); val descriptorLimit = UInt(64.W)
  val descriptors = UInt(25.W)
  val epoch = UInt(16.W)
  val regions = Vec(4, new Region)
}
class HostCommandResult extends Bundle {
  val status = UInt(8.W); val completed = UInt(16.W)
  val failedPc = UInt(16.W); val epoch = UInt(16.W)
}
/** First enabled owner is the already-existing binary SFU_VECTOR residual add.
  * Uses the frozen Command128 bits and SFU_PROGRAM ID = zero-extended opcode.
  * This is not a new opaque block opcode and not a claim of all-op coverage.
  * Three tensor prefixes are decoded from DDR, not host-predecoded metadata.
  * Completion and event publication occur only after the owner's write ACKs.
  * The command table is in-order. A forward/unsatisfied event is rejected, not
  * silently ignored or waited on forever. Unimplemented opcodes fail closed.
  */
class HostResidualCommands(eventSlots: Int = 256, maxCommands: Int = 64) extends Module {
  require(eventSlots >= 2 && eventSlots <= 65536 && isPow2(eventSlots))
  require(maxCommands >= 1 && maxCommands <= 65535)
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new HostCommandLaunch))
    val result = Decoupled(new HostCommandResult)
    val completion = Decoupled(UInt(56.W))
    val job = Decoupled(new BoundJob)
    val done = Flipped(Decoupled(new JobResult))
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val resetRequired = Output(Bool())
  })
  val idle :: fetchCommand :: getCommand :: decodeCommand :: issueTensor :: getTensor :: fetchPolicy :: getPolicy :: validate :: issueJob :: getJob :: complete :: finish :: locked :: Nil = Enum(14)
  val state = RegInit(idle)
  val cfg = Reg(new HostCommandLaunch)
  val command = Reg(UInt(128.W))
  val policy = Reg(UInt(128.W))
  val pc = RegInit(0.U(16.W)); val completed = RegInit(0.U(16.W))
  val status = RegInit(0.U(8.W)); val poison = RegInit(false.B)
  val slot = RegInit(0.U(2.W))
  val tensors = Reg(Vec(3, new DecodedTensor))
  val events = RegInit(VecInit(Seq.fill(eventSlots)(false.B)))
  val roots = Wire(Vec(3, UInt(24.W)))
  roots(0) := command(79,56); roots(1) := command(103,80); roots(2) := command(127,104)
  val waitEvent = command(39,24); val signalEvent = command(55,40)
  val record = Module(new Record128Reader)
  val tensor = Module(new TypedTensorReader)
  val tensorMode = state === issueTensor || state === getTensor

  io.launch.ready := state === idle && !poison
  io.result.valid := state === finish
  io.result.bits.status := status; io.result.bits.completed := completed
  io.result.bits.failedPc := pc; io.result.bits.epoch := cfg.epoch
  io.completion.valid := state === complete
  // Same 56-bit event/status/engine/diagnostic envelope as retained endpoints.
  io.completion.bits := Cat(signalEvent, status, 3.U(3.W), pc.pad(29))
  io.resetRequired := poison || record.io.resetRequired
  io.memory <> record.io.memory; record.io.response <> io.response

  record.io.request.valid := Mux(tensorMode, tensor.io.record.valid, state === fetchCommand || state === fetchPolicy)
  record.io.request.bits := tensor.io.record.bits
  when(!tensorMode) {
    record.io.request.bits.tableBase := Mux(state === fetchCommand, cfg.commandBase, cfg.descriptorBase)
    record.io.request.bits.tableLimit := Mux(state === fetchCommand, cfg.commandLimit, cfg.descriptorLimit)
    record.io.request.bits.entryCount := Mux(state === fetchCommand, cfg.commands, cfg.descriptors)
    record.io.request.bits.index := Mux(state === fetchCommand, pc, tensors(0).tail)
    record.io.request.bits.requestTag := Cat(cfg.epoch, pc, 0.U(32.W))
  }
  tensor.io.record.ready := record.io.request.ready && tensorMode
  tensor.io.recordResult.valid := record.io.result.valid && tensorMode
  tensor.io.recordResult.bits := record.io.result.bits
  record.io.result.ready := Mux(tensorMode, tensor.io.recordResult.ready, state === getCommand || state === getPolicy)

  tensor.io.request.valid := state === issueTensor
  tensor.io.request.bits.tableBase := cfg.descriptorBase
  tensor.io.request.bits.tableLimit := cfg.descriptorLimit
  tensor.io.request.bits.entryCount := cfg.descriptors
  tensor.io.request.bits.root := roots(slot)
  tensor.io.request.bits.regions := cfg.regions
  tensor.io.request.bits.writeAccess := slot === 2.U
  tensor.io.result.ready := state === getTensor

  io.job.valid := state === issueJob
  io.job.bits.op := ElemOp.Add.U
  io.job.bits.a := tensors(0).address; io.job.bits.b := tensors(1).address
  io.job.bits.dst := tensors(2).address
  io.job.bits.aBf16 := tensors(0).dtype === 5.U
  io.job.bits.bBf16 := tensors(1).dtype === 5.U
  io.job.bits.dstBf16 := tensors(2).dtype === 5.U
  io.job.bits.elementCount := tensors(2).elementCount
  io.job.bits.tag := Cat(cfg.epoch, pc)
  io.done.ready := state === getJob

  def fail(code: UInt): Unit = { status := code; poison := true.B; state := complete }
  def overlap(a: UInt, endA: UInt, b: UInt, endB: UInt): Bool = a < endB && b < endA
  when(io.launch.fire) {
    val l = io.launch.bits
    val cmdEnd = l.commandBase.pad(80) + (((l.commands.pad(80)*16.U+63.U)>>6)<<6)
    val descEnd = l.descriptorBase.pad(80) + (((l.descriptors.pad(80)*16.U+63.U)>>6)<<6)
    val validRegions = l.regions.map(r => (r.base===r.limit && !r.read && !r.write) ||
      (r.base < r.limit && r.base(5,0)===0.U && r.limit(5,0)===0.U && r.limit <= (BigInt(1)<<56).U)).reduce(_ && _)
    val regionOverlap = (for (i <- 0 until 4; j <- i+1 until 4)
      yield l.regions(i).base<l.regions(i).limit && l.regions(j).base<l.regions(j).limit &&
        overlap(l.regions(i).base,l.regions(i).limit,l.regions(j).base,l.regions(j).limit)).reduce(_ || _)
    def readonlyTable(base: UInt, limit: UInt): Bool = l.regions.map(r =>
      r.base<=base && limit<=r.limit && r.read && !r.write).reduce(_ || _)
    val valid = l.commands>0.U && l.commands<=maxCommands.U && l.descriptors>0.U && l.descriptors<=0xffffff.U &&
      l.commandBase(5,0)===0.U && l.descriptorBase(5,0)===0.U &&
      l.commandLimit(5,0)===0.U && l.descriptorLimit(5,0)===0.U &&
      cmdEnd<=l.commandLimit && descEnd<=l.descriptorLimit &&
      l.commandBase<l.commandLimit && l.descriptorBase<l.descriptorLimit &&
      !overlap(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit) &&
      validRegions && !regionOverlap && readonlyTable(l.commandBase,l.commandLimit) && readonlyTable(l.descriptorBase,l.descriptorLimit)
    cfg := l; pc := 0.U; completed := 0.U; status := 0.U; command := 0.U
    events := VecInit(Seq.fill(eventSlots)(false.B)); events(0) := true.B
    when(!valid) { status := Status.Bounds.U; state := finish }
      .otherwise { state := fetchCommand }
  }
  when(state===fetchCommand && record.io.request.fire) { state := getCommand }
  when(state===getCommand && record.io.result.fire) {
    command := record.io.result.bits.data
    when(record.io.result.bits.status=/=0.U) { fail(record.io.result.bits.status) }
    .elsewhen(record.io.result.bits.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))) { fail(Status.Protocol.U) }
    .otherwise { state := decodeCommand }
  }
  when(state===decodeCommand) {
    when(command(7,0)=/=0x30.U || command(10,8)=/=3.U) { fail(Status.Unsupported.U) }
    .elsewhen(command(23,11)=/=0.U || roots.map(r => r===0xffffff.U || r>=cfg.descriptors).reduce(_||_)) { fail(Status.Malformed.U) }
    .elsewhen(waitEvent>=eventSlots.U || signalEvent===0.U || signalEvent>=eventSlots.U ||
      !events(waitEvent(log2Ceil(eventSlots)-1,0)) || events(signalEvent(log2Ceil(eventSlots)-1,0)) || waitEvent===signalEvent) { fail(Status.Dependency.U) }
    .otherwise { slot := 0.U; state := issueTensor }
  }
  when(state===issueTensor && tensor.io.request.fire) { state := getTensor }
  when(state===getTensor && tensor.io.result.fire) {
    when(tensor.io.result.bits.status=/=0.U) { fail(tensor.io.result.bits.status) }
    .otherwise {
      tensors(slot) := tensor.io.result.bits.tensor
      when(slot===2.U) { state := fetchPolicy }
        .otherwise { slot := slot+1.U; state := issueTensor }
    }
  }
  when(state===fetchPolicy && record.io.request.fire) { state := getPolicy }
  when(state===getPolicy && record.io.result.fire) {
    policy := record.io.result.bits.data
    when(record.io.result.bits.status=/=0.U) { fail(record.io.result.bits.status) }
    .elsewhen(record.io.result.bits.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))) { fail(Status.Protocol.U) }
    .otherwise { state := validate }
  }
  when(state===validate) {
    val a=tensors(0);val b=tensors(1);val d=tensors(2)
    val shapes = (0 until 4).map(i=>a.dims(i)===b.dims(i) && a.dims(i)===d.dims(i)).reduce(_&&_) && a.rank===b.rank && a.rank===d.rank
    val p=policy
    val programOK = p(7,0)===0x20.U && p(31,8)===0.U && p(55,32)===0xffffff.U &&
      p(71,56)===0x30.U && p(79,72)===2.U && p(87,80)===1.U &&
      p(91,88)===a.dtype && p(95,92)===d.dtype && p(103,96)===16.U && p(127,104)===0.U
    when(!shapes || a.dtype=/=b.dtype || b.tail=/=0xffffff.U || d.tail=/=0xffffff.U || !programOK) { fail(Status.Unsupported.U) }
    .elsewhen(overlap(d.address,d.paddedEnd,a.address,a.paddedEnd) || overlap(d.address,d.paddedEnd,b.address,b.paddedEnd) ||
      overlap(d.address,d.paddedEnd,cfg.commandBase,cfg.commandLimit) || overlap(d.address,d.paddedEnd,cfg.descriptorBase,cfg.descriptorLimit)) { fail(Status.Permission.U) }
    .otherwise { state := issueJob }
  }
  when(io.job.fire) { state := getJob }
  when(io.done.fire) {
    val r=io.done.bits
    when(r.tag=/=Cat(cfg.epoch,pc)) { fail(Status.Protocol.U) }
    .elsewhen(r.status=/=0.U) { fail(r.status) }
    .elsewhen(r.elementCount=/=tensors(2).elementCount || r.writeBytes=/=tensors(2).payloadBytes) { fail(Status.Protocol.U) }
    .otherwise { state := complete }
  }
  when(io.completion.fire) {
    when(status=/=0.U) { state := finish }
    .otherwise {
      events(signalEvent(log2Ceil(eventSlots)-1,0)) := true.B
      completed := completed+1.U
      when(pc+1.U===cfg.commands) { state := finish }
      .otherwise { pc := pc+1.U; state := fetchCommand }
    }
  }
  when(io.result.fire) { state := Mux(poison,locked,idle) }
}
