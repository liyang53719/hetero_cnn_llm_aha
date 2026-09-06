// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Physical byte addresses. Only the first hidden input is supplied by the host.
  * Hidden arenas alternate after the previous block's final acknowledged write.
  * Weights are layer-specific; RoPE and intermediate scratch are shared.
  */
class StackLaunch extends Bundle {
  val weights = UInt(64.W); val weightStride = UInt(64.W)
  val rope = UInt(64.W); val scratch = UInt(64.W)
  val hiddenA = UInt(64.W); val hiddenB = UInt(64.W); val limit = UInt(64.W)
  val tokens = UInt(16.W); val layers = UInt(8.W); val epoch = UInt(16.W)
}
class StackResult extends Bundle {
  val status = UInt(8.W); val completedLayers = UInt(8.W); val failedLayer = UInt(8.W)
  val epoch = UInt(16.W); val output = UInt(64.W)
  val cycles = UInt(64.W); val usefulMacs = UInt(64.W); val executedMacs = UInt(64.W)
}
class StackGeometry(s: QwenBlockShape) {
  val layout = new QwenBlockLayout(s)
  val weightBytes: BigInt = BigInt(layout("cos"))
  val ropeBytes: BigInt = BigInt(layout("x") - layout("cos"))
  val hiddenBytes: BigInt = BigInt(s.maxTokens) * s.hidden * 4
  val scratchBytes: BigInt = BigInt(layout("y") - layout.writableStart)
}

/** The integrated wrapper uses the real block; it never synthesizes a numeric
  * completion. The separated controller permits directed protocol tests.
  */
class LayerStackController(s: QwenBlockShape, maxLayers: Int = 28) extends Module {
  require(maxLayers > 0 && maxLayers <= 255)
  val g = new StackGeometry(s)
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new StackLaunch)); val result = Decoupled(new StackResult)
    val childLaunch = Decoupled(new BlockLaunch); val childResult = Flipped(Decoupled(new BlockResult))
    val config = Output(new StackLaunch); val layer = Output(UInt(8.W))
    val sourceHidden = Output(UInt(64.W)); val destinationHidden = Output(UInt(64.W))
    val resetRequired = Output(Bool()); val layerCommit = Output(Bool())
  })
  val idle :: issue :: running :: finish :: locked :: Nil = Enum(5)
  val state = RegInit(idle); val cfg = Reg(new StackLaunch)
  val layer = RegInit(0.U(8.W)); val completed = RegInit(0.U(8.W))
  val status = RegInit(0.U(8.W)); val poisoned = RegInit(false.B)
  val cycles = RegInit(0.U(64.W)); val useful = RegInit(0.U(64.W)); val executed = RegInit(0.U(64.W))
  val published = RegInit(0.U(64.W))
  io.launch.ready := state === idle
  io.result.valid := state === finish
  io.result.bits.status := status; io.result.bits.completedLayers := completed
  io.result.bits.failedLayer := layer; io.result.bits.epoch := cfg.epoch
  io.result.bits.output := published; io.result.bits.cycles := cycles
  io.result.bits.usefulMacs := useful; io.result.bits.executedMacs := executed
  io.config := cfg; io.layer := layer
  io.sourceHidden := Mux(layer(0), cfg.hiddenB, cfg.hiddenA)
  io.destinationHidden := Mux(layer(0), cfg.hiddenA, cfg.hiddenB)
  io.resetRequired := poisoned; io.layerCommit := false.B
  io.childLaunch.valid := state === issue
  io.childLaunch.bits.base := 0.U; io.childLaunch.bits.limit := g.layout.total.U
  io.childLaunch.bits.tokens := cfg.tokens
  io.childLaunch.bits.epoch := cfg.epoch + layer
  io.childResult.ready := state === running
  when(state === issue || state === running) { cycles := cycles + 1.U }

  val l = io.launch.bits
  val weightSpan = ((l.layers - 1.U) * l.weightStride) +& g.weightBytes.U
  val starts = Seq(l.weights, l.rope, l.hiddenA, l.hiddenB, l.scratch)
  val lengths = Seq(weightSpan, g.ropeBytes.U(73.W), g.hiddenBytes.U(73.W), g.hiddenBytes.U(73.W), g.scratchBytes.U(73.W))
  val ends = starts.zip(lengths).map { case (a, n) => a.pad(74) + n.pad(74) }
  val rangesOK = starts.zip(ends).map { case (a, e) => a(5, 0) === 0.U && e <= l.limit && e > a }.reduce(_ && _)
  val overlaps = (for (i <- starts.indices; j <- (i + 1) until starts.size)
    yield starts(i).pad(74) < ends(j) && starts(j).pad(74) < ends(i)).reduce(_ || _)
  val shapeOK = l.layers > 0.U && l.layers <= maxLayers.U && l.tokens > 0.U && l.tokens <= s.maxTokens.U &&
    l.weightStride >= g.weightBytes.U && l.weightStride(5, 0) === 0.U && l.limit <= (BigInt(1) << 56).U &&
    (l.epoch +& l.layers) <= 65536.U
  when(state === idle && io.launch.fire) {
    cfg := l; layer := 0.U; completed := 0.U; status := 0.U
    cycles := 0.U; useful := 0.U; executed := 0.U; published := 0.U
    when(!shapeOK || !rangesOK || overlaps) { status := Status.Bounds.U; state := finish }
      .otherwise { state := issue }
  }
  when(state === issue && io.childLaunch.fire) { state := running }
  when(state === running && io.childResult.fire) {
    val r = io.childResult.bits
    useful := useful + r.macs; executed := executed + r.executedMacs
    when(r.status =/= 0.U || r.phase =/= 14.U || r.epoch =/= cfg.epoch + layer) {
      status := Mux(r.status =/= 0.U, r.status, Status.Protocol.U)
      poisoned := true.B; state := finish
    }.otherwise {
      published := io.destinationHidden; completed := completed + 1.U; io.layerCommit := true.B
      when(layer +& 1.U === cfg.layers) { state := finish }
        .otherwise { layer := layer + 1.U; state := issue }
    }
  }
  when(state === finish && io.result.fire) { state := Mux(poisoned, locked, idle) }
}

/** Address-only relocation, with no tensor arithmetic and one in-flight request.
  * An illegal write to a read-only allocation returns an explicit error.
  */
class LayerAddressMapper(s: QwenBlockShape) extends Module {
  val g = new StackGeometry(s); val p = g.layout
  val io = IO(new Bundle {
    val config = Input(new StackLaunch); val layer = Input(UInt(8.W))
    val sourceHidden = Input(UInt(64.W)); val destinationHidden = Input(UInt(64.W))
    val request = Flipped(Decoupled(new MemoryRequest)); val response = Decoupled(new MemoryResponse)
    val memory = Decoupled(new MemoryRequest); val memoryResponse = Flipped(Decoupled(new MemoryResponse))
  })
  val idle :: waitResponse :: localError :: Nil = Enum(3)
  val state = RegInit(idle); val originalTag = Reg(UInt(64.W))
  val a = io.request.bits.address; val cfg = io.config
  val weights = a < p("cos").U
  val rope = a >= p("cos").U && a < p("x").U
  val input = a >= p("x").U && a < (BigInt(p("x")) + g.hiddenBytes).U
  val scratch = a >= p.writableStart.U && a < p("y").U
  val output = a >= p("y").U && a < (BigInt(p("y")) + g.hiddenBytes).U
  val mapped = Mux(weights, cfg.weights + io.layer * cfg.weightStride + a,
    Mux(rope, cfg.rope + a - p("cos").U,
      Mux(input, io.sourceHidden + a - p("x").U,
        Mux(output, io.destinationHidden + a - p("y").U,
          cfg.scratch + a - p.writableStart.U))))
  val legal = a(5, 0) === 0.U && (weights || rope || input || scratch || output) &&
    !(io.request.bits.write && (weights || rope || input)) && (mapped +& 64.U) <= cfg.limit
  io.memory.valid := state === idle && io.request.valid && legal
  io.memory.bits := io.request.bits; io.memory.bits.address := mapped
  io.request.ready := state === idle && Mux(legal, io.memory.ready, true.B)
  io.response.valid := state === localError || (state === waitResponse && io.memoryResponse.valid)
  io.response.bits := io.memoryResponse.bits
  when(state === localError) {
    io.response.bits.data := 0.U; io.response.bits.tag := originalTag; io.response.bits.error := true.B
  }
  io.memoryResponse.ready := state === waitResponse && io.response.ready
  when(io.request.fire) { originalTag := io.request.bits.tag; state := Mux(legal, waitResponse, localError) }
  when(io.response.fire) { state := idle }
}

class Qwen2LayerStack(s: QwenBlockShape = QwenBlockShape(), maxLayers: Int = 28) extends Module {
  val controller = Module(new LayerStackController(s, maxLayers))
  val block = Module(new Qwen2ContinuousBlock(s)); val mapper = Module(new LayerAddressMapper(s))
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new StackLaunch)); val result = Decoupled(new StackResult)
    val memory = Decoupled(new MemoryRequest); val response = Flipped(Decoupled(new MemoryResponse))
    val layer = Output(UInt(8.W)); val phase = Output(UInt(5.W))
    val stageCommit = Output(Bool()); val committedPhase = Output(UInt(5.W)); val layerCommit = Output(Bool())
    val resetRequired = Output(Bool())
  })
  dontTouch(io)
  controller.io.launch <> io.launch; io.result <> controller.io.result
  block.io.launch <> controller.io.childLaunch; controller.io.childResult <> block.io.result
  mapper.io.config := controller.io.config; mapper.io.layer := controller.io.layer
  mapper.io.sourceHidden := controller.io.sourceHidden; mapper.io.destinationHidden := controller.io.destinationHidden
  mapper.io.request <> block.io.memory; block.io.response <> mapper.io.response
  io.memory <> mapper.io.memory; mapper.io.memoryResponse <> io.response
  io.layer := controller.io.layer; io.phase := block.io.phase
  io.stageCommit := block.io.stageCommit; io.committedPhase := block.io.committedPhase
  io.layerCommit := controller.io.layerCommit; io.resetRequired := controller.io.resetRequired || block.io.resetRequired
}
