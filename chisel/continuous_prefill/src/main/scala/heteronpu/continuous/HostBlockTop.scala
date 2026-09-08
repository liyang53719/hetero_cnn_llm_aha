// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import _root_.circt.stage.ChiselStage
import java.nio.file.{Files,Paths}
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}

/** Only Host tables launch this root. No legacy block launch, phase permit,
  * payload injection, or second iDMA exists. Metadata and owner traffic share
  * the same arbiter, mailbox adapter, original upstream backend and AXI port.
  */
class HostBlockTop(s:QwenBlockShape, weightReadBeats:Int=1,pipelined:Boolean=false) extends Module {
  require(Set(1,16).contains(weightReadBeats))
  require(s.retainedMatrix)
  require(!pipelined || (weightReadBeats==16 && s.matrixColumns==256))
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunch));val result=Decoupled(new HostCommandResult)
    val completion=Decoupled(UInt(56.W));val axi=new BlockAxiMaster
    val resetRequired=Output(Bool());val idmaTransfers=Output(UInt(64.W))
    val idmaStreamedBeats=Output(UInt(64.W));val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
    val idmaReadBursts=Output(UInt(64.W));val idmaReadBeats=Output(UInt(64.W));val idmaCacheHits=Output(UInt(64.W))
    val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W))
    val usefulMacs=Output(UInt(64.W));val executedMacs=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
    val memoryAccepted=Output(Vec(2,UInt(64.W)));val memoryReturned=Output(Vec(2,UInt(64.W)))
  })
  dontTouch(io)
  val cmd=Module(new HostBlockCommands(s));val owner=Module(new QwenOwnerKernel(s,pipelined))
  val hub=Module(new SharedMemoryArbiter(2))
  val dmaPoison=Wire(Bool())
  cmd.io.launch<>io.launch;io.result<>cmd.io.result;io.completion<>cmd.io.completion
  owner.io.job<>cmd.io.job;cmd.io.done<>owner.io.done
  hub.io.requests(0)<>cmd.io.memory;cmd.io.response<>hub.io.responses(0)
  hub.io.requests(1)<>owner.io.memory;owner.io.response<>hub.io.responses(1)
  if(weightReadBeats==1){
    val dma=Module(new RetainedIdmaMemoryAdapter)
    dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
    dmaPoison:=dma.io.resetRequired;io.idmaTransfers:=dma.io.transfers
    io.idmaReadBursts:=dma.io.readBeats;io.idmaReadBeats:=dma.io.readBeats;io.idmaCacheHits:=0.U;io.idmaStreamedBeats:=0.U
  }else{
    val dma=Module(new RetainedIdmaWeightBurstAdapter(weightReadBeats,streaming=pipelined))
    val window=RegInit(0.U.asTypeOf(new IdmaWeightWindow))
    when(io.launch.fire||owner.io.done.fire){window.enable:=false.B}
    when(owner.io.job.fire){
      val job=owner.io.job.bits
      val end=job.b.pad(66)+((job.n.pad(66)*job.k.pad(66))<<2)
      window.enable:=job.kind===QwenOwnerKind.Dense.U && end<=(BigInt(1)<<56).U
      window.base:=job.b;window.limit:=end(63,0)
    }
    dma.io.window:=window
    if(pipelined){dma.io.streamRequest.get<>owner.io.burst.get;owner.io.burstResponse.get<>dma.io.streamResponse.get}
    io.idmaStreamedBeats:=dma.io.streamedBeats
    dma.io.flush:=io.launch.fire||owner.io.job.fire||owner.io.done.fire
    dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
    dmaPoison:=dma.io.resetRequired;io.idmaTransfers:=dma.io.transfers
    io.idmaReadBursts:=dma.io.readBursts;io.idmaReadBeats:=dma.io.readBeats;io.idmaCacheHits:=dma.io.cacheHits
  }
  io.resetRequired:=cmd.io.resetRequired||owner.io.resetRequired||hub.io.resetRequired||dmaPoison
  io.pc:=cmd.io.pc;io.issuedJobs:=cmd.io.issuedJobs
  io.usefulMacs:=cmd.io.usefulMacs;io.executedMacs:=cmd.io.executedMacs;io.writeBytes:=cmd.io.writeBytes
  io.pipelineIssues:=owner.io.pipelineIssues;io.pipelineStalls:=owner.io.pipelineStalls
  io.memoryAccepted:=hub.io.accepted;io.memoryReturned:=hub.io.returned
}
class HostBlockCollection(s:QwenBlockShape, weightReadBeats:Int=1,pipelined:Boolean=false) extends Module {
  val top=Module(new HostBlockTop(s,weightReadBeats,pipelined));val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitHostBlock extends App {
  require((args.length>=2&&args.length<=5) && Set("tiny","real").contains(args(1)),"OUT tiny|real [512|4096] [weightReadBeats=1|16] [pipeline=0|1]")
  val matrixMacs=if(args.length>=3)args(2).toInt else 4096
  require(Set(512,4096).contains(matrixMacs),"supported Matrix geometry")
  val weightReadBeats=if(args.length>=4)args(3).toInt else 1
  require(Set(1,16).contains(weightReadBeats))
  val pipelined=args.length>=5 && args(4)=="1"
  require(!pipelined || (matrixMacs==4096 && weightReadBeats==16))
  val out=Paths.get(args(0));require(!Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  val s=(if(args(1)=="tiny")QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32)else QwenBlockShape()).copy(retainedMatrix=true,matrixColumns=matrixMacs/16)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(new HostBlockCollection(s,weightReadBeats,pipelined),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("owner_shape.h"),s"""// Generated by Chisel. Do not edit.
#pragma once
#define OWNER_MATRIX_MACS ${matrixMacs}
#define OWNER_WEIGHT_READ_BEATS ${weightReadBeats}
#define OWNER_PIPELINED ${if(pipelined)1 else 0}
static constexpr unsigned H=${s.hidden},F=${s.ffn},HEADS=${s.heads},KVHEADS=${s.kvHeads},HD=${s.headDim},MAX_TOKENS=${s.maxTokens};
""")
  Files.writeString(out.resolve("SCOPE.json"),s"""{"pipelined":${pipelined},"silu_lanes":${if(pipelined)16 else 1},"dense_contexts":${if(pipelined)5 else 1},"weight_read_burst_beats":${weightReadBeats},"weight_read_cache_bytes":${if(weightReadBeats>1)1024 else 0},"host_commands":true,"block_launch":false,"hidden":${s.hidden},"ffn":${s.ffn},"retained_matrix":true,"matrix_macs":${matrixMacs},"matrix_columns":${s.matrixColumns},"matrix_rows":16,"logical_matrix_engines":1,"physical_matrix_slices":${matrixMacs/512},"peak_requires_context_interleaving":true,"pinned_idma":true,"attention_fusion":"checked QK/SOFTMAX/PV; no DDR scores","official_weights":false,"timing_signoff":false}\n""")
}
