// Source candidate only: not compiled/elaborated. No arithmetic replacement.
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Future Attention-only test shell. This is not the full host/block owner graph.
  * Exact original Core+PackedClient and MatrixService+Legacy client are retained.
  * RetainedMatrixEndpoint blackbox providers must be closed in a joint namespace.
  */
class OrderedQkRealMatrixCore extends Module {
  val core=Module(new OrderedQkBehaviorCore(true))
  val matrix=Module(new MatrixPipelineService(returnTagBits=0,enableTransposedDense=false,enableAccumulatorSeed=false,enablePackedDrainStatus=true))
  val legacy=Module(new LegacyMatrixStreamClient)
  val io=IO(new Bundle {
    val ownerJob=Flipped(Decoupled(new QwenOwnerJob))
    val result=Decoupled(new BlockResult)
    val memory=Decoupled(new MemoryRequest)
    val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
    val acknowledgedWriteBytes=Output(UInt(64.W))
    val issuedSliceSteps=Output(UInt(64.W))
    val wideSteps=Output(UInt(64.W));val stallCycles=Output(UInt(64.W))
  })
  val observation=IO(Output(chiselTypeOf(core.observation)))
  val scoreWrite=IO(Output(chiselTypeOf(core.testScoreWrite)))
  core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
  core.io.ownerJob.get<>io.ownerJob
  io.result<>core.io.result;io.memory<>core.io.memory;core.io.response<>io.response
  observation:=core.observation;scoreWrite:=core.testScoreWrite
  io.acknowledgedWriteBytes:=core.io.acknowledgedWriteBytes
  io.resetRequired:=core.io.resetRequired||matrix.io.resetRequired||legacy.io.resetRequired
  io.issuedSliceSteps:=matrix.io.acceptedSteps
  io.wideSteps:=matrix.io.wideSteps;io.stallCycles:=matrix.io.stallCycles
  when(io.ownerJob.fire){assert(io.ownerJob.bits.kind===QwenOwnerKind.Attention.U,"Attention-only test shell")}

  // Exact production route QwenOwnerProtocol:154-155. No scripted result tile.
  legacy.io.request<>core.io.matrixRequest.get
  core.io.matrixResult.get<>legacy.io.result
  core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps
  // Production packed-lease select: the core retains ownership through completion.
  val p=core.io.packedQk.get;val l=legacy.io.port
  val select=core.io.packedQkActive.get
  core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get
  // Default legacy path, overridden atomically by the packed lease. No Dense owner
  // is instantiated in this deliberately narrow shell, not a resource reduction
  // of the original eight retained 512-MAC Matrix endpoints.
  for((client,chosen)<-Seq((p,select),(l,!select))){
    client.group.ready:=chosen&&matrix.io.port.group.ready
    client.step.ready:=chosen&&matrix.io.port.step.ready
    client.result.valid:=chosen&&matrix.io.port.result.valid
    client.result.bits:=matrix.io.port.result.bits
    client.done.valid:=chosen&&matrix.io.port.done.valid
    client.done.bits:=matrix.io.port.done.bits
  }
  matrix.io.port.group.valid:=Mux(select,p.group.valid,l.group.valid)
  matrix.io.port.group.bits.opcode:=Mux(select,p.group.bits.opcode,l.group.bits.opcode)
  matrix.io.port.group.bits.sliceMask:=Mux(select,p.group.bits.sliceMask,l.group.bits.sliceMask)
  matrix.io.port.group.bits.tag:=Mux(select,p.group.bits.tag,l.group.bits.tag)
  matrix.io.port.step.valid:=Mux(select,p.step.valid,l.step.valid)
  matrix.io.port.step.bits:=Mux(select,p.step.bits,l.step.bits)
  matrix.io.port.result.ready:=Mux(select,p.result.ready,l.result.ready)
  matrix.io.port.done.ready:=Mux(select,p.done.ready,l.done.ready)
  matrix.io.port.abort:=Mux(select,p.abort,l.abort)
  when(select){assert(!core.io.matrixRequest.get.valid,"packed lease excludes legacy PV request")}
  // Future testbench reads real service results/acceptance; no steps==8 drain stub.
}
