// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files, Paths}

/** Actual production controller and SRAMs. Matrix results and DDR responses are
  * externally injected. This is storage/protocol coverage, NOT arithmetic or
  * retained-iDMA numerical signoff. Packed observation ports add no arithmetic.
  */
class NativeBf16StorageProbe(burstWrites: Boolean) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new QwenOwnerJob))
    val done = Decoupled(new QwenOwnerResult)
    val burst = Decoupled(new BurstReadRequest)
    val burstResponse = Flipped(Decoupled(new BurstReadResponse))
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val writeRequest = Decoupled(new BurstWriteRequest)
    val writeData = Decoupled(new BurstWriteBeat)
    val writeResponse = Flipped(Decoupled(new MemoryResponse))
    val group = Decoupled(new MatrixStreamGroup)
    val stepValid = Output(Bool()); val stepReady = Input(Bool())
    val stepA = Output(UInt(256.W)); val stepB = Output(UInt(4096.W))
    val stepContext = Output(UInt(3.W))
    val stepClear = Output(Bool()); val stepLast = Output(Bool())
    val stepFinish = Output(Bool()); val stepEmit = Output(Bool())
    val resultValid = Input(Bool()); val resultReady = Output(Bool())
    val resultData = Input(UInt((16 * 256 * 32).W))
    val resultContext = Input(UInt(3.W)); val resultLast = Input(Bool()); val resultError = Input(Bool())
    val matrixDone = Flipped(Decoupled(new MatrixStreamDone))
    val matrixAbort = Output(Bool()); val resetRequired = Output(Bool())
  })
  val dense = Module(new StreamingDenseOwner(maxK = 64, burstWrites = burstWrites))
  dense.io.job <> io.job; io.done <> dense.io.done
  io.burst <> dense.io.burst; dense.io.burstResponse <> io.burstResponse
  io.memory <> dense.io.memory; dense.io.response <> io.response
  if (burstWrites) {
    io.writeRequest <> dense.io.writeRequest.get
    io.writeData <> dense.io.writeData.get
    dense.io.writeResponse.get <> io.writeResponse
  } else {
    io.writeRequest.valid := false.B; io.writeRequest.bits := 0.U.asTypeOf(new BurstWriteRequest)
    io.writeData.valid := false.B; io.writeData.bits := 0.U.asTypeOf(new BurstWriteBeat)
    io.writeResponse.ready := false.B
  }
  io.group <> dense.io.matrix.group
  io.stepValid := dense.io.matrix.step.valid; dense.io.matrix.step.ready := io.stepReady
  io.stepA := dense.io.matrix.step.bits.a.asUInt; io.stepB := dense.io.matrix.step.bits.b.asUInt
  io.stepContext := dense.io.matrix.step.bits.context
  io.stepClear := dense.io.matrix.step.bits.clear; io.stepLast := dense.io.matrix.step.bits.last
  io.stepFinish := dense.io.matrix.step.bits.finish; io.stepEmit := dense.io.matrix.step.bits.emit
  dense.io.matrix.result.valid := io.resultValid; io.resultReady := dense.io.matrix.result.ready
  dense.io.matrix.result.bits.value := io.resultData.asTypeOf(dense.io.matrix.result.bits.value)
  dense.io.matrix.result.bits.context := io.resultContext
  dense.io.matrix.result.bits.last := io.resultLast; dense.io.matrix.result.bits.error := io.resultError
  dense.io.matrix.done <> io.matrixDone; io.matrixAbort := dense.io.matrix.abort
  dense.io.physicalSteps := 0.U // External Matrix is mocked; no physical-MAC claim.
  io.resetRequired := dense.io.resetRequired
}
object EmitNativeBf16StorageProbe extends App {
  val p = Paths.get(args(0)); require(p.isAbsolute && !Files.exists(p)); Files.createDirectories(p)
  Files.writeString(p.resolve("NativeBf16StorageProbe.sv"),
    ChiselStage.emitSystemVerilog(new NativeBf16StorageProbe(args(1) == "1"),
      firtoolOpts = Array("-disable-all-randomization", "-strip-debug-info")))
}
