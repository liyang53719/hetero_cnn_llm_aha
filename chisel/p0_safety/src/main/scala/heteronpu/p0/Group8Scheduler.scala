// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0

import chisel3._
import chisel3.util._

/** The real production scheduling FSM, exposed at child module boundaries for
  * unit testing. The production root reconnects unchanged descriptor/Norm/Matrix
  * leaves; the payload implementation is the Chisel MatrixTilePayload above.
  */
class Group8SchedulerIO extends Bundle {
  val start = Input(Bool()); val command = Input(UInt(128.W)); val traceOnly = Input(Bool()); val batches = Input(UInt(32.W))
  val heldCommand = Output(UInt(128.W))
  val descriptorStart = Output(Bool()); val contextValid = Input(Bool()); val contextReady = Output(Bool())
  val contextLegal = Input(Bool()); val contextStatus = Input(UInt(8.W))
  val addresses = Input(UInt(168.W)); val columns = Input(UInt(18.W)); val weightStride = Input(UInt(32.W)); val tiles = Input(UInt(6.W)); val contextFp32 = Input(Bool())
  val normStart = Output(Bool()); val normDone = Input(Bool()); val normStatus = Input(UInt(8.W)); val normBytes = Input(UInt(64.W))
  val normBase = Output(UInt(64.W)); val tokenBase = Output(UInt(32.W))
  val payloadStart = Output(Bool()); val payloadDone = Input(Bool()); val payloadStatus = Input(UInt(8.W)); val payloadSteps = Input(UInt(32.W))
  val payloadWeight = Output(UInt(64.W)); val payloadStride = Output(UInt(32.W)); val outputFp32 = Output(Bool())
  val matrixCmdValid = Output(Bool()); val matrixCmdReady = Input(Bool())
  val matrixCompletion = Input(Bool()); val matrixStatus = Input(UInt(8.W)); val matrixError = Input(Bool()); val lastTile = Output(Bool())
  val dmaValid = Output(Bool()); val dmaReady = Input(Bool()); val dmaKind = Output(UInt(2.W))
  val dmaSource = Output(UInt(64.W)); val dmaDestination = Output(UInt(64.W))
  val dmaRowBytes = Output(UInt(32.W)); val dmaRows = Output(UInt(32.W)); val dmaSourceStride = Output(UInt(32.W)); val dmaDestinationStride = Output(UInt(32.W))
  val dmaResponse = Input(Bool()); val dmaResponseReady = Output(Bool()); val dmaError = Input(Bool())
  val selectNorm = Output(Bool()); val selectPayload = Output(Bool())
  val done = Output(Bool()); val status = Output(UInt(8.W)); val resetRequired = Output(Bool())
  val matrixSteps = Output(UInt(32.W)); val values = Output(UInt(32.W)); val weightLoads = Output(UInt(32.W)); val normLoads = Output(UInt(32.W))
  val readBytes = Output(UInt(64.W)); val writeBytes = Output(UInt(64.W))
}

class Group8Scheduler extends Module {
  val io = IO(new Group8SchedulerIO)
  val idle :: context :: cmd :: weightReq :: weightRsp :: norm :: payload :: storeReq :: storeRsp :: trace :: finish :: done :: locked :: Nil = Enum(13)
  val state = RegInit(idle)
  val command = RegInit(0.U(128.W)); val traceMode = RegInit(false.B); val batches = RegInit(0.U(32.W))
  val addresses = RegInit(0.U(168.W)); val columns = RegInit(0.U(18.W)); val stride = RegInit(0.U(32.W)); val tiles = RegInit(0.U(6.W))
  val groupBase = RegInit(0.U(6.W)); val groupCount = RegInit(0.U(6.W)); val slot = RegInit(0.U(6.W)); val batch = RegInit(0.U(7.W)); val fp32 = RegInit(false.B)
  val status = RegInit(0.U(8.W)); val poisoned = RegInit(false.B); val completionSeen = RegInit(false.B)
  val ds = RegInit(false.B); val ns = RegInit(false.B); val ps = RegInit(false.B)
  val steps = RegInit(0.U(32.W)); val values = RegInit(0.U(32.W)); val weights = RegInit(0.U(32.W)); val norms = RegInit(0.U(32.W))
  val reads = RegInit(0.U(64.W)); val writes = RegInit(0.U(64.W))
  val elementBytes = Mux(fp32,4.U(3.W),2.U(3.W)); val tileRowBytes = Mux(fp32,128.U(32.W),64.U(32.W))
  val asyncFault = io.matrixError || (io.matrixCompletion && io.matrixStatus =/= 0.U)
  val active = state =/= idle && state =/= done && state =/= locked
  def fail(code: UInt): Unit = { when(status === 0.U) { status := code }; poisoned := true.B; state := done }
  ds := false.B; ns := false.B; ps := false.B
  io.heldCommand := command; io.descriptorStart := ds; io.contextReady := state === context
  io.normStart := ns; io.payloadStart := ps
  io.normBase := addresses(55,0); io.tokenBase := batch << 4
  io.payloadWeight := "ha0000".U(64.W) + (slot << 6); io.payloadStride := groupCount << 6; io.outputFp32 := fp32
  io.matrixCmdValid := state === cmd && !poisoned && !asyncFault
  io.lastTile := groupBase +& slot +& 1.U === tiles && batch +& 1.U === batches
  io.selectNorm := state === norm; io.selectPayload := state === payload
  io.dmaValid := (state === weightReq || state === storeReq) && !poisoned && !asyncFault
  io.dmaKind := Mux(state === weightReq,1.U,3.U)
  io.dmaSource := Mux(state === weightReq,addresses(111,56).pad(64) + (groupBase << 6),"h160000".U)
  io.dmaDestination := Mux(state === weightReq,"ha0000".U,
    addresses(167,112).pad(64) + batch.pad(64)*16.U*columns*elementBytes + (groupBase.pad(64)+slot)*tileRowBytes)
  io.dmaRowBytes := Mux(state === weightReq,groupCount << 6,tileRowBytes)
  io.dmaRows := Mux(state === weightReq,1536.U,16.U)
  io.dmaSourceStride := Mux(state === weightReq,stride,tileRowBytes)
  io.dmaDestinationStride := Mux(state === weightReq,groupCount << 6,columns*elementBytes)
  io.dmaResponseReady := state === weightRsp || state === storeRsp
  io.done := state === done; io.status := status; io.resetRequired := poisoned
  io.matrixSteps := steps; io.values := values; io.weightLoads := weights; io.normLoads := norms
  io.readBytes := reads; io.writeBytes := writes
  when(active && io.matrixCompletion) { completionSeen := true.B }
  // Preserve the first fault while draining already-issued child work.
  when(active && asyncFault) { when(status === 0.U) { status := 7.U }; poisoned := true.B }
  switch(state) {
    is(idle) { when(io.start) {
      command := io.command; traceMode := io.traceOnly; batches := io.batches
      groupBase := 0.U; groupCount := 0.U; slot := 0.U; batch := 0.U; completionSeen := false.B; fp32 := false.B
      steps := 0.U; values := 0.U; weights := 0.U; norms := 0.U; reads := 0.U; writes := 0.U; status := 0.U
      when(io.batches === 0.U || io.batches > 64.U) { status := 5.U; state := done }
        .otherwise { ds := true.B; state := context }
    } }
    is(context) { when(io.contextValid) {
      when(!io.contextLegal) { status := Mux(io.contextStatus === 0.U,2.U,io.contextStatus); state := done }
        .elsewhen(io.tiles === 0.U || io.tiles > 48.U || io.columns === 0.U || io.columns =/= io.tiles*32.U) { status := 5.U; state := done }
        .otherwise {
          addresses := io.addresses; columns := io.columns; stride := io.weightStride; tiles := io.tiles; fp32 := io.contextFp32
          groupCount := Mux(io.tiles > 8.U,8.U,io.tiles)
          when(traceMode) {
            weights := Mux(io.tiles > 8.U,8.U,io.tiles); norms := 1.U
            reads := Mux(io.tiles > 8.U,8.U,io.tiles)*98304.U +& 49152.U; state := trace
          }.otherwise { state := cmd }
        }
    } }
    is(cmd) { when(poisoned || asyncFault) { fail(7.U) }.elsewhen(io.matrixCmdReady) { state := weightReq } }
    is(weightReq) { when(poisoned || asyncFault) { fail(7.U) }.elsewhen(io.dmaReady) { state := weightRsp } }
    is(weightRsp) { when(io.dmaResponse) {
      when(io.dmaError) { fail(3.U) }.elsewhen(poisoned || asyncFault) { fail(7.U) }.otherwise {
        weights := weights + groupCount; reads := reads + groupCount*98304.U; batch := 0.U; ns := true.B; state := norm
      }
    } }
    is(norm) { when(io.normDone) {
      when(io.normStatus =/= 0.U) { fail(io.normStatus) }.elsewhen(poisoned || asyncFault) { fail(7.U) }.otherwise {
        norms := norms + 1.U; reads := reads + io.normBytes; slot := 0.U; ps := true.B; state := payload
      }
    } }
    is(payload) { when(io.payloadDone) {
      steps := steps + io.payloadSteps
      when(io.payloadStatus =/= 0.U) { fail(io.payloadStatus) }.elsewhen(poisoned || asyncFault) { fail(7.U) }.otherwise { state := storeReq }
    } }
    is(storeReq) { when(poisoned || asyncFault) { fail(7.U) }.elsewhen(io.dmaReady) { state := storeRsp } }
    is(storeRsp) { when(io.dmaResponse) {
      when(io.dmaError) { fail(3.U) }.elsewhen(poisoned || asyncFault) { fail(7.U) }.otherwise {
        values := values + 512.U; writes := writes + tileRowBytes*16.U
        when(slot +& 1.U < groupCount) { slot := slot + 1.U; ps := true.B; state := payload }
          .elsewhen(batch +& 1.U < batches) { batch := batch + 1.U; ns := true.B; state := norm }
          .elsewhen(groupBase +& groupCount < tiles) {
            val rest = tiles - (groupBase + groupCount)
            groupBase := groupBase + groupCount; groupCount := Mux(rest > 8.U,8.U,rest); state := weightReq
          }.otherwise { state := finish }
      }
    } }
    is(trace) {
      steps := steps + 1536.U; values := values + 512.U; writes := writes + tileRowBytes*16.U
      when(slot +& 1.U < groupCount) { slot := slot + 1.U }
        .elsewhen(batch +& 1.U < batches) { batch := batch + 1.U; slot := 0.U; norms := norms + 1.U; reads := reads + 49152.U }
        .elsewhen(groupBase +& groupCount < tiles) {
          val rest = tiles - (groupBase + groupCount); val next = Mux(rest > 8.U,8.U,rest)
          groupBase := groupBase + groupCount; groupCount := next; slot := 0.U; batch := 0.U
          weights := weights + next; norms := norms + 1.U; reads := reads + next*98304.U + 49152.U
        }.otherwise { state := done }
    }
    is(finish) { when(poisoned || asyncFault) { fail(7.U) }.elsewhen(completionSeen || io.matrixCompletion) { state := done } }
    is(done) { state := Mux(poisoned,locked,idle) }
    is(locked) { /* reset-only recovery; never create another completion pulse */ }
  }
}
