// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal, decoded owner job. Never a Host opcode or on-DDR encoding. */
object QwenOwnerKind { val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4; val Add=5; val Activation=6; val KvAppend=7; val GdnConv=8 }
class QwenOwnerJob extends Bundle {
  // Explicit internal ABI extension. Values 0..7 retain their old meanings;
  // GDN is never truncated or aliased to a legacy owner kind.
  val kind=UInt(4.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val weightBf16=Bool() // Dense B storage only; compute remains BF16 x BF16 + FP32.
  val activationBf16=Bool() // Explicit Dense A storage; false preserves FP32 ingress.
  val outputBf16=Bool() // Explicit terminal RNE BF16 D storage; false preserves FP32 stores.
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
  val historyOut=UInt(64.W);val expectedGeneration=UInt(32.W);val currentGeneration=UInt(32.W);val cold=Bool()
}
class QwenOwnerResult extends Bundle {
  val tag=UInt(32.W); val status=UInt(8.W); val writeBytes=UInt(64.W)
  val cycles=UInt(64.W); val usefulMacs=UInt(64.W); val executedMacs=UInt(64.W)
}
/** No block launch is exposed. One decoded owner operation per transaction;
  * the arithmetic implementation must return instead of advancing to a phase.
  */
class QwenOwnerKernel(s:QwenBlockShape,pipelined:Boolean=false,burstWrites:Boolean=false,overlapSilu:Boolean=false,bf16Gdn:Boolean=false) extends Module {
  require(!bf16Gdn || (pipelined && s.qwen35GdnOnly), "GDN requires the explicit pipelined profile")
  require(!burstWrites || pipelined)
  require(!overlapSilu || pipelined, "overlapped SiLU requires the pipelined owner path")
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new QwenOwnerJob)); val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest); val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
    val burst=if(pipelined)Some(Decoupled(new BurstReadRequest))else None
    val burstResponse=if(pipelined)Some(Flipped(Decoupled(new BurstReadResponse)))else None
    val writeRequest=if(burstWrites)Some(Decoupled(new BurstWriteRequest))else None
    val writeData=if(burstWrites)Some(Decoupled(new BurstWriteBeat))else None
    val writeResponse=if(burstWrites)Some(Flipped(Decoupled(new MemoryResponse)))else None
    val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
  })
  if(!pipelined){
  val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true))
  core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
  core.io.ownerJob.get<>io.job
  val tag=Reg(UInt(32.W));when(io.job.fire){tag:=io.job.bits.tag}
  io.done.valid:=core.io.result.valid;core.io.result.ready:=io.done.ready
  io.done.bits.tag:=tag;io.done.bits.status:=core.io.result.bits.status
  io.done.bits.writeBytes:=core.io.acknowledgedWriteBytes
  io.done.bits.cycles:=core.io.result.bits.cycles
  io.done.bits.usefulMacs:=core.io.result.bits.macs;io.done.bits.executedMacs:=core.io.result.bits.executedMacs
  io.memory<>core.io.memory;core.io.response<>io.response;io.resetRequired:=core.io.resetRequired
    io.pipelineIssues:=0.U;io.pipelineStalls:=0.U
  }else{
    require(s.matrixColumns==256 && s.retainedMatrix)
    val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true,externalMatrix=true,externalScalar=bf16Gdn))
    core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
    val dense=Module(new StreamingDenseOwner(s.maxRow,burstWrites=burstWrites))
    val silu=Module(new ScheduledSiluOwner(overlapSilu))
    val matrix=Module(new MatrixPipelineService)
    val legacy=Module(new LegacyMatrixStreamClient)
    val gdn=if(bf16Gdn)Some(Module(new GdnConv4Owner(channels=6144,maxTokens=s.maxTokens)))else None
    legacy.io.request<>core.io.matrixRequest.get;core.io.matrixResult.get<>legacy.io.result
    core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps
    dense.io.physicalSteps:=matrix.io.acceptedSteps
    val active=RegInit(false.B);val mode=Reg(UInt(3.W));val tag=Reg(UInt(32.W));val rejected=RegInit(false.B)
    val gdnExpected=Reg(UInt(32.W));val gdnCurrent=Reg(UInt(32.W))
    val choose=Mux(bf16Gdn.B && io.job.bits.kind===QwenOwnerKind.GdnConv.U,3.U,
      Mux(io.job.bits.kind>QwenOwnerKind.KvAppend.U,4.U,
        Mux(io.job.bits.kind===QwenOwnerKind.Dense.U,1.U,Mux(io.job.bits.kind===QwenOwnerKind.Activation.U,2.U,0.U))))
    val gdnReady=gdn.map(_.io.job.ready).getOrElse(false.B)
    val gdnPoison=gdn.map(_.io.resetRequired).getOrElse(false.B)
    val sharedPoison=core.io.resetRequired||dense.io.resetRequired||silu.io.resetRequired||matrix.io.resetRequired||legacy.io.resetRequired
    val canStart= !active && !rejected && !gdnPoison && !(bf16Gdn.B && sharedPoison)
    io.job.ready:=canStart && MuxLookup(choose,false.B)(Seq(0.U->core.io.ownerJob.get.ready,1.U->dense.io.job.ready,2.U->silu.io.job.ready,3.U->gdnReady,4.U->true.B))
    core.io.ownerJob.get.valid:=io.job.valid && canStart && choose===0.U;core.io.ownerJob.get.bits:=io.job.bits
    dense.io.job.valid:=io.job.valid && canStart && choose===1.U;dense.io.job.bits:=io.job.bits
    silu.io.job.valid:=io.job.valid && canStart && choose===2.U;silu.io.job.bits:=io.job.bits
    when(io.job.fire){active:=true.B;mode:=choose;tag:=io.job.bits.tag
      when(choose===3.U){gdnExpected:=io.job.bits.expectedGeneration;gdnCurrent:=io.job.bits.currentGeneration}
      when(choose===4.U){rejected:=true.B}
    }
    val gdnDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gdnValid=WireDefault(false.B)
    gdn.foreach{gd=>
      gd.io.job.valid:=io.job.valid && canStart && choose===3.U
      gd.io.job.bits.tokens:=io.job.bits.m;gd.io.job.bits.channels:=io.job.bits.n
      gd.io.job.bits.input:=io.job.bits.a;gd.io.job.bits.weight:=io.job.bits.b
      gd.io.job.bits.historyIn:=io.job.bits.c;gd.io.job.bits.historyOut:=io.job.bits.historyOut
      gd.io.job.bits.output:=io.job.bits.dst;gd.io.job.bits.cold:=io.job.bits.cold
      gd.io.job.bits.expectedGeneration:=io.job.bits.expectedGeneration;gd.io.job.bits.tag:=io.job.bits.tag
      gd.io.currentGeneration:=Mux(active,gdnCurrent,io.job.bits.currentGeneration)
      core.io.scalarService.get<>gd.io.scalar
      gdnValid:=gd.io.done.valid;gdnDone.tag:=gd.io.done.bits.tag
      val invalidCommit=gd.io.done.bits.status===0.U &&
        (!gd.io.done.bits.historyCommitted || gd.io.done.bits.generation=/=gdnExpected+1.U)
      gdnDone.status:=Mux(invalidCommit,Status.Protocol.U,gd.io.done.bits.status)
      gdnDone.writeBytes:=gd.io.done.bits.writeBytes;gdnDone.cycles:=gd.io.done.bits.cycles
      gd.io.done.ready:=active && mode===3.U && io.done.ready
      when(gd.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val rejectedDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));rejectedDone.tag:=tag;rejectedDone.status:=Status.Unsupported.U
    val oldDone=Wire(new QwenOwnerResult)
    oldDone.tag:=tag;oldDone.status:=core.io.result.bits.status;oldDone.cycles:=core.io.result.bits.cycles
    oldDone.writeBytes:=core.io.acknowledgedWriteBytes;oldDone.usefulMacs:=core.io.result.bits.macs;oldDone.executedMacs:=core.io.result.bits.executedMacs
    io.done.valid:=active && MuxLookup(mode,false.B)(Seq(0.U->core.io.result.valid,1.U->dense.io.done.valid,2.U->silu.io.done.valid,3.U->gdnValid,4.U->true.B))
    io.done.bits:=MuxLookup(mode,rejectedDone)(Seq(0.U->oldDone,1.U->dense.io.done.bits,2.U->silu.io.done.bits,3.U->gdnDone))
    core.io.result.ready:=active&&mode===0.U&&io.done.ready
    dense.io.done.ready:=active&&mode===1.U&&io.done.ready;silu.io.done.ready:=active&&mode===2.U&&io.done.ready
    when(io.done.fire){active:=false.B}
    val memories=Seq(core.io.memory,dense.io.memory,silu.io.memory)++gdn.toSeq.map(_.io.memory)
    val responses=Seq(core.io.response,dense.io.response,silu.io.response)++gdn.toSeq.map(_.io.response)
    io.memory.valid:=active&&MuxLookup(mode,false.B)(memories.zipWithIndex.map{case(p,i)=>i.U->p.valid})
    io.memory.bits:=MuxLookup(mode,0.U.asTypeOf(new MemoryRequest))(memories.zipWithIndex.map{case(p,i)=>i.U->p.bits})
    io.response.ready:=active&&MuxLookup(mode,false.B)(responses.zipWithIndex.map{case(p,i)=>i.U->p.ready})
    for(i<-memories.indices){memories(i).ready:=active&&mode===i.U&&io.memory.ready
      responses(i).valid:=active&&mode===i.U&&io.response.valid;responses(i).bits:=io.response.bits}
    if(burstWrites){io.writeRequest.get<>dense.io.writeRequest.get;io.writeData.get<>dense.io.writeData.get;dense.io.writeResponse.get<>io.writeResponse.get}
    io.burst.get<>dense.io.burst;dense.io.burstResponse<>io.burstResponse.get
    val useDense=active&&mode===1.U
    for((client,index)<-Seq(legacy.io.port,dense.io.matrix).zipWithIndex){
      val selected=if(index==1)useDense else !useDense
      client.group.ready:=selected&&matrix.io.port.group.ready
      client.step.ready:=selected&&matrix.io.port.step.ready
      client.result.valid:=selected&&matrix.io.port.result.valid;client.result.bits:=matrix.io.port.result.bits
      client.done.valid:=selected&&matrix.io.port.done.valid;client.done.bits:=matrix.io.port.done.bits
    }
    matrix.io.port.group.valid:=Mux(useDense,dense.io.matrix.group.valid,legacy.io.port.group.valid)
    matrix.io.port.group.bits:=Mux(useDense,dense.io.matrix.group.bits,legacy.io.port.group.bits)
    matrix.io.port.step.valid:=Mux(useDense,dense.io.matrix.step.valid,legacy.io.port.step.valid)
    matrix.io.port.step.bits:=Mux(useDense,dense.io.matrix.step.bits,legacy.io.port.step.bits)
    matrix.io.port.result.ready:=Mux(useDense,dense.io.matrix.result.ready,legacy.io.port.result.ready)
    matrix.io.port.done.ready:=Mux(useDense,dense.io.matrix.done.ready,legacy.io.port.done.ready)
    matrix.io.port.abort:=Mux(useDense,dense.io.matrix.abort,legacy.io.port.abort)
    io.pipelineIssues:=matrix.io.wideSteps;io.pipelineStalls:=matrix.io.stallCycles
    io.resetRequired:=rejected||gdnPoison||core.io.resetRequired||dense.io.resetRequired||silu.io.resetRequired||matrix.io.resetRequired||legacy.io.resetRequired
  }
}
