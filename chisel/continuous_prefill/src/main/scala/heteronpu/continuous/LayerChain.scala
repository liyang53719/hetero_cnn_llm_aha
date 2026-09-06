// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Arena-strided layer chain. The host may preload only parameters/constants and
  * layer-0 X before launch. For every later layer X is an address alias of the
  * preceding layer's committed Y, never a host copy or a reference tensor.
  */
class LayerChainLaunch extends Bundle {
  val base = UInt(64.W); val limit = UInt(64.W); val stride = UInt(64.W)
  val tokens = UInt(16.W); val epoch = UInt(16.W); val layers = UInt(8.W)
}
class LayerChainResult extends Bundle {
  val status = UInt(8.W); val phase = UInt(5.W); val epoch = UInt(16.W)
  val completedLayers = UInt(8.W); val failedLayer = UInt(8.W)
  val cycles = UInt(64.W); val macs = UInt(64.W); val executedMacs = UInt(64.W)
  val finalOutput = UInt(64.W)
}

/** Scheduling-only module; tested separately, then instantiated with the actual
  * numerical block below. No arithmetic completion may stand in for write ACK.
  */
class LayerChainController(s: QwenBlockShape, maxLayers: Int = 28) extends Module {
  require(maxLayers > 0 && maxLayers <= 255)
  private val layout = new QwenBlockLayout(s)
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new LayerChainLaunch))
    val result = Decoupled(new LayerChainResult)
    val blockLaunch = Decoupled(new BlockLaunch)
    val blockResult = Flipped(Decoupled(new BlockResult))
    val stageCommit = Input(Bool()); val committedPhase = Input(UInt(5.W))
    val memoryDrained = Input(Bool()); val externalFault = Input(Bool())
    val currentLayer = Output(UInt(8.W)); val arenaBase = Output(UInt(64.W))
    val previousBase = Output(UInt(64.W)); val tokenCount = Output(UInt(16.W))
    val layerCommit = Output(Bool()); val resetRequired = Output(Bool())
    val busy = Output(Bool())
  })
  val idle :: issue :: run :: finish :: locked :: Nil = Enum(5)
  val state = RegInit(idle); val req = Reg(new LayerChainLaunch)
  val current = RegInit(0.U(8.W)); val stages = RegInit(0.U(5.W))
  val completed = RegInit(0.U(8.W)); val status = RegInit(0.U(8.W))
  val poison = RegInit(false.B); val cycles = RegInit(0.U(64.W))
  val macs = RegInit(0.U(64.W)); val physical = RegInit(0.U(64.W))
  val arena = req.base + current * req.stride
  io.launch.ready := state === idle
  io.result.valid := state === finish
  io.result.bits.status := status; io.result.bits.phase := Mux(stages === 15.U,14.U,stages)
  io.result.bits.epoch := req.epoch; io.result.bits.completedLayers := completed
  io.result.bits.failedLayer := current; io.result.bits.cycles := cycles
  io.result.bits.macs := macs; io.result.bits.executedMacs := physical
  io.result.bits.finalOutput := arena + layout("y").U
  io.blockLaunch.valid := state === issue && !poison
  io.blockLaunch.bits.base := arena; io.blockLaunch.bits.limit := arena + layout.total.U
  io.blockLaunch.bits.tokens := req.tokens; io.blockLaunch.bits.epoch := req.epoch
  io.blockResult.ready := state === run
  io.currentLayer := current; io.arenaBase := arena
  io.previousBase := req.base + (current - 1.U) * req.stride
  io.tokenCount := req.tokens; io.layerCommit := false.B
  io.resetRequired := poison; io.busy := state === issue || state === run
  when(io.busy) { cycles := cycles + 1.U }
  when(io.launch.fire) {
    req := io.launch.bits; current := 0.U; stages := 0.U; completed := 0.U
    status := 0.U; cycles := 0.U; macs := 0.U; physical := 0.U
    val l = io.launch.bits
    // Widen BEFORE multiplication/addition, do not validate truncated addresses.
    val end = l.base.pad(80) + (l.layers.pad(80) - 1.U) * l.stride.pad(80) + layout.total.U
    val legal = l.layers > 0.U && l.layers <= maxLayers.U && l.tokens > 0.U && l.tokens <= s.maxTokens.U &&
      l.base(5,0) === 0.U && l.stride(5,0) === 0.U && l.stride >= layout.total.U &&
      end <= l.limit.pad(80) && end <= (BigInt(1) << 56).U
    when(legal) { state := issue }.otherwise { status := Status.Bounds.U; state := finish }
  }
  when(io.blockLaunch.fire) { state := run }
  when(state === run && io.stageCommit) {
    when(io.committedPhase =/= stages || stages >= 15.U || !io.memoryDrained) {
      when(status === 0.U) { status := Status.Protocol.U }; poison := true.B
    }.otherwise { stages := stages + 1.U }
  }
  when(state === run && io.blockResult.fire) {
    val completedNow = stages + io.stageCommit.asUInt
    val valid = !poison && !io.externalFault && status === 0.U && io.blockResult.bits.status === 0.U &&
      io.blockResult.bits.epoch === req.epoch && io.blockResult.bits.phase === 14.U &&
      completedNow === 15.U && io.memoryDrained
    when(valid) {
      macs := macs + io.blockResult.bits.macs
      physical := physical + io.blockResult.bits.executedMacs
      completed := completed + 1.U; io.layerCommit := true.B
      when(current +& 1.U === req.layers) { state := finish }
        .otherwise { current := current + 1.U; stages := 0.U; state := issue }
    }.otherwise {
      when(status === 0.U) { status := Mux(io.blockResult.bits.status === 0.U,Status.Protocol.U,io.blockResult.bits.status) }
      poison := true.B; state := finish
    }
  }
  // Wait for the already launched block to drain/fail; never drop its requests.
  when(io.busy && io.externalFault) { poison := true.B; when(status === 0.U) { status := Status.Memory.U } }
  when(io.result.fire) { state := Mux(poison,locked,idle) }
}

class Qwen2LayerChain(s: QwenBlockShape = QwenBlockShape(), maxLayers: Int = 28) extends Module {
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new LayerChainLaunch)); val result = Decoupled(new LayerChainResult)
    val memory = Decoupled(new MemoryRequest); val response = Flipped(Decoupled(new MemoryResponse))
    val stageCommit = Output(Bool()); val committedPhase = Output(UInt(5.W)); val phase = Output(UInt(5.W))
    val layerCommit = Output(Bool()); val currentLayer = Output(UInt(8.W))
    val resetRequired = Output(Bool()); val readBytes = Output(UInt(64.W)); val writeBytes = Output(UInt(64.W))
    val forwardedInputReads = Output(UInt(64.W))
  })
  dontTouch(io)
  val l = new QwenBlockLayout(s)
  val control = Module(new LayerChainController(s,maxLayers))
  val block = Module(new Qwen2ContinuousBlock(s))
  control.io.launch <> io.launch; io.result <> control.io.result
  block.io.launch <> control.io.blockLaunch; control.io.blockResult <> block.io.result
  control.io.stageCommit := block.io.stageCommit; control.io.committedPhase := block.io.committedPhase
  control.io.externalFault := block.io.resetRequired
  val outstanding = RegInit(false.B)
  when(io.memory.fire) { outstanding := true.B }
  when(io.response.fire) { outstanding := false.B }
  control.io.memoryDrained := !outstanding
  io.memory <> block.io.memory; block.io.response <> io.response
  val first = control.io.currentLayer === 0.U
  val x = control.io.arenaBase + l("x").U
  val inputBytes = control.io.tokenCount.pad(64) * s.hidden.U * 4.U
  val inputRead = !block.io.memory.bits.write && block.io.memory.bits.address >= x && block.io.memory.bits.address < x + inputBytes
  when(!first && inputRead) {
    io.memory.bits.address := control.io.previousBase + l("y").U + (block.io.memory.bits.address - x)
  }
  val reads = RegInit(0.U(64.W)); val writes = RegInit(0.U(64.W)); val forwards = RegInit(0.U(64.W))
  when(io.launch.fire) { reads := 0.U; writes := 0.U; forwards := 0.U }
  when(io.memory.fire) {
    when(io.memory.bits.write) { writes := writes + PopCount(io.memory.bits.mask) }.otherwise { reads := reads + 64.U }
    when(!first && inputRead) { forwards := forwards + 1.U }
  }
  io.readBytes := reads; io.writeBytes := writes; io.forwardedInputReads := forwards
  io.stageCommit := block.io.stageCommit; io.committedPhase := block.io.committedPhase; io.phase := block.io.phase
  io.layerCommit := control.io.layerCommit; io.currentLayer := control.io.currentLayer
  io.resetRequired := control.io.resetRequired || block.io.resetRequired
}

class Qwen2AxiLayerChain(s: QwenBlockShape = QwenBlockShape(), maxLayers: Int = 28) extends Module {
  val chain = Module(new Qwen2LayerChain(s,maxLayers)); val bridge = Module(new BlockAxiMemoryAdapter)
  val io = IO(new Bundle {
    val launch = Flipped(Decoupled(new LayerChainLaunch)); val result = Decoupled(new LayerChainResult)
    val axi = new BlockAxiMaster
    val stageCommit = Output(Bool()); val committedPhase = Output(UInt(5.W)); val phase = Output(UInt(5.W))
    val layerCommit = Output(Bool()); val currentLayer = Output(UInt(8.W)); val resetRequired = Output(Bool())
    val readBytes = Output(UInt(64.W)); val writeBytes = Output(UInt(64.W)); val forwardedInputReads = Output(UInt(64.W))
  })
  dontTouch(io)
  chain.io.launch <> io.launch; io.result <> chain.io.result
  bridge.io.request <> chain.io.memory; chain.io.response <> bridge.io.response; io.axi <> bridge.io.axi
  io.stageCommit := chain.io.stageCommit; io.committedPhase := chain.io.committedPhase; io.phase := chain.io.phase
  io.layerCommit := chain.io.layerCommit; io.currentLayer := chain.io.currentLayer
  io.resetRequired := chain.io.resetRequired || bridge.io.resetRequired
  io.readBytes := chain.io.readBytes; io.writeBytes := chain.io.writeBytes; io.forwardedInputReads := chain.io.forwardedInputReads
}
