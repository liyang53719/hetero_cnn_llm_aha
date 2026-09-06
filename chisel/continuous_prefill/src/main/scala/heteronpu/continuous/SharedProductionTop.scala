// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import heteronpu.p0.LocalSramConfig

/** No second iDMA: block, metadata reader and command-driven residual data all
  * pass through one captured-owner arbiter to the same retained backend/AXI.
  * Existing block launch remains explicit; Host Command128 currently enables
  * only the binary residual owner. Full decoder command lowering is NOT done.
  * Requests are serialized at task granularity; clients cannot race writes in
  * overlapping tensor arenas. Completion backpressure preserves that lock.
  */
class Qwen2SharedProductionTop(s: QwenBlockShape=QwenBlockShape(retainedMatrix=true)) extends Module {
  require(s.retainedMatrix)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new BlockLaunch)); val result=Decoupled(new BlockResult)
    val commandLaunch=Flipped(Decoupled(new HostCommandLaunch))
    val commandResult=Decoupled(new HostCommandResult); val commandCompletion=Decoupled(UInt(56.W))
    val axi=new BlockAxiMaster
    val phase=Output(UInt(5.W)); val stageCommit=Output(Bool()); val committedPhase=Output(UInt(5.W))
    val resetRequired=Output(Bool()); val idmaTransfers=Output(UInt(64.W))
    val readBytes=Output(UInt(64.W)); val writeBytes=Output(UInt(64.W))
    val memoryAccepted=Output(Vec(3,UInt(64.W)));val memoryReturned=Output(Vec(3,UInt(64.W)))
  })
  dontTouch(io)
  val block=Module(new Qwen2ContinuousBlock(s))
  val commands=Module(new HostResidualCommands)
  val c=ChainConfig()
  val residual=Module(new ElementwiseMemoryEngine(c,LocalSramConfig(rowsPerBank=c.localBytes/256)))
  val hub=Module(new SharedMemoryArbiter(3))
  val dma=Module(new RetainedIdmaMemoryAdapter)
  val idle::blockMode::commandMode::Nil=Enum(3)
  val mode=RegInit(idle)
  val poison=hub.io.resetRequired || dma.io.resetRequired || block.io.resetRequired || commands.io.resetRequired || residual.io.resetRequired
  // Block launch wins a same-cycle race. Neither requester loses a handshake.
  io.launch.ready:=mode===idle && !poison && block.io.launch.ready
  block.io.launch.valid:=io.launch.valid && mode===idle && !poison
  block.io.launch.bits:=io.launch.bits
  io.commandLaunch.ready:=mode===idle && !poison && !io.launch.valid && commands.io.launch.ready
  commands.io.launch.valid:=io.commandLaunch.valid && mode===idle && !poison && !io.launch.valid
  commands.io.launch.bits:=io.commandLaunch.bits
  io.result<>block.io.result;io.commandResult<>commands.io.result
  io.commandCompletion<>commands.io.completion
  when(io.launch.fire){mode:=blockMode}
  when(io.commandLaunch.fire){mode:=commandMode}
  when((mode===blockMode && io.result.fire)||(mode===commandMode && io.commandResult.fire)){mode:=idle}
  residual.io.job<>commands.io.job;commands.io.done<>residual.io.done
  hub.io.requests(0)<>block.io.memory;block.io.response<>hub.io.responses(0)
  hub.io.requests(1)<>commands.io.memory;commands.io.response<>hub.io.responses(1)
  hub.io.requests(2)<>residual.io.memory;residual.io.response<>hub.io.responses(2)
  dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
  io.phase:=block.io.phase;io.stageCommit:=block.io.stageCommit;io.committedPhase:=block.io.committedPhase
  io.readBytes:=block.io.readBytes;io.writeBytes:=block.io.writeBytes;io.resetRequired:=poison
  io.idmaTransfers:=dma.io.transfers;io.memoryAccepted:=hub.io.accepted;io.memoryReturned:=hub.io.returned
}

/** Fast integration root: the exact command/controller/residual/iDMA components
  * used above, without compiling a Matrix for every malformed-command case.
  */
class HostResidualIdmaTop extends Module {
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunch));val result=Decoupled(new HostCommandResult)
    val completion=Decoupled(UInt(56.W));val axi=new BlockAxiMaster
    val resetRequired=Output(Bool());val idmaTransfers=Output(UInt(64.W))
    val memoryAccepted=Output(Vec(2,UInt(64.W)));val memoryReturned=Output(Vec(2,UInt(64.W)))
  })
  val cmd=Module(new HostResidualCommands);val c=ChainConfig()
  val engine=Module(new ElementwiseMemoryEngine(c,LocalSramConfig(rowsPerBank=c.localBytes/256)))
  val hub=Module(new SharedMemoryArbiter(2));val dma=Module(new RetainedIdmaMemoryAdapter)
  io.launch<>cmd.io.launch;io.result<>cmd.io.result;io.completion<>cmd.io.completion
  engine.io.job<>cmd.io.job;cmd.io.done<>engine.io.done
  hub.io.requests(0)<>cmd.io.memory;cmd.io.response<>hub.io.responses(0)
  hub.io.requests(1)<>engine.io.memory;engine.io.response<>hub.io.responses(1)
  dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
  io.resetRequired:=cmd.io.resetRequired||engine.io.resetRequired||hub.io.resetRequired||dma.io.resetRequired
  io.idmaTransfers:=dma.io.transfers;io.memoryAccepted:=hub.io.accepted;io.memoryReturned:=hub.io.returned
}
