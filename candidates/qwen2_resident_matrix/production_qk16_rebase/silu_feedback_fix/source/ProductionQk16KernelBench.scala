// Test-only shell; never a replacement production top or a Host PASS.
package heteronpu.continuous
import chisel3._
import chisel3.util._
class ProductionQk16KernelBench(selected:Boolean) extends Module {
  val s=QwenBlockShape(hidden=1536,ffn=8960,heads=12,kvHeads=2,headDim=128,
    maxTokens=1024,retainedMatrix=true,matrixColumns=256)
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob));val done=Decoupled(new QwenOwnerResult)
    val axi=new BlockAxiMaster;val resetRequired=Output(Bool())
    val accepted=Output(Vec(2,UInt(64.W)));val returned=Output(Vec(2,UInt(64.W)))
  })
  val owner=Module(new QwenOwnerKernel(s,pipelined=true,burstWrites=true,
    enableTransposedDense=true,enableTransposedSeed=true,enableTransposedDown=true,
    enableFfnTiles=true,enableFfnWindow=true,enableFfnDrain=true,enableResidentFfn=true,
    enablePublic21QkvReduction=true,numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
    enableProductionPackedQk16=selected))
  val hub=Module(new SharedMemoryArbiter(2))
  val dma=Module(new RetainedIdmaWeightBurstAdapter(16,streaming=true,burstWrites=true,commitTailRead=false))
  owner.io.job<>io.job;io.done<>owner.io.done
  owner.io.public21BackendReset.get:=hub.io.resetRequired||dma.io.resetRequired
  owner.io.resident.get.request.valid:=false.B
  owner.io.resident.get.request.bits:=0.U.asTypeOf(owner.io.resident.get.request.bits)
  owner.io.resident.get.result.ready:=false.B
  owner.io.resident.get.abort:=RegNext(hub.io.resetRequired||dma.io.resetRequired,false.B)
  owner.io.prefixWorkspace.get:=0.U.asTypeOf(owner.io.prefixWorkspace.get)
  // Original hub client0 is Host metadata. No Host exists in this kernel-only shell.
  hub.io.requests(0).valid:=false.B;hub.io.requests(0).bits:=0.U.asTypeOf(hub.io.requests(0).bits)
  hub.io.responses(0).ready:=false.B
  hub.io.requests(1)<>owner.io.memory;owner.io.response<>hub.io.responses(1)
  val window=RegInit(0.U.asTypeOf(new IdmaWeightWindow))
  when(owner.io.done.fire){window.enable:=false.B}
  when(owner.io.job.fire){
    val job=owner.io.job.bits;val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
    val end=job.b.pad(66)+(job.n.pad(66)*job.k.pad(66)*weightBytes)
    window.enable:=job.kind===QwenOwnerKind.Dense.U&&end<=(BigInt(1)<<56).U
    window.base:=job.b;window.limit:=end(63,0)
  }
  when(owner.io.residentHandoff.get.valid){
    val job=owner.io.residentHandoff.get.bits;val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
    val end=job.b.pad(66)+(job.n.pad(66)*job.k.pad(66)*weightBytes)
    window.enable:=job.kind===QwenOwnerKind.Dense.U&&end<=(BigInt(1)<<56).U
    window.base:=job.b;window.limit:=end(63,0)
  }
  dma.io.window:=window
  dma.io.streamRequest.get<>owner.io.burst.get;owner.io.burstResponse.get<>dma.io.streamResponse.get
  dma.io.streamWriteRequest.get<>owner.io.writeRequest.get
  dma.io.streamWriteData.get<>owner.io.writeData.get
  owner.io.writeResponse.get<>dma.io.streamWriteResponse.get
  dma.io.flush:=owner.io.job.fire||owner.io.done.fire||owner.io.residentHandoff.get.valid
  dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
  io.resetRequired:=owner.io.resetRequired||hub.io.resetRequired||dma.io.resetRequired
  io.accepted:=hub.io.accepted;io.returned:=hub.io.returned
  when(io.job.fire){assert(io.job.bits.kind===QwenOwnerKind.Attention.U)}
  dontTouch(io)
}
