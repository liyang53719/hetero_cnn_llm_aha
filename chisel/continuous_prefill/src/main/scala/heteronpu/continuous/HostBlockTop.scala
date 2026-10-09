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
class HostBlockTop(s:QwenBlockShape, weightReadBeats:Int=1,pipelined:Boolean=false,burstWrites:Boolean=false,commitTailRead:Boolean=false,overlapSilu:Boolean=false,bf16V:Boolean=false,bf16Qkv:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false) extends Module {
  require(!bf16AttentionCore || bf16QkNormRope,"Attention core requires the explicit QKV/Norm/RoPE profile")
  require(!bf16QkNormRope || bf16Qkv,"QK Norm/RoPE requires the explicit QKV profile")
  require(!bf16V || (pipelined && s.qwen35VOnly), "native V requires the pipelined Qwen3.5 V-only profile")
  require(!bf16Qkv || (pipelined && s.qwen35QkvOnly), "native QKV requires the pipelined Qwen3.5 QKV-only profile")
  require(!bf16Gdn || (pipelined && s.qwen35GdnOnly), "native GDN requires the pipelined GDN profile")
  require(!bf16GdnCore || bf16Gdn, "native GDN core requires the explicit GDN profile")
  require(!bf16GdnBlock || bf16GdnCore, "native GDN block requires the explicit core profile")
  require(Seq(bf16V,bf16Qkv,bf16Gdn).count(identity)<=1, "native profiles are distinct")
  require(!overlapSilu || pipelined, "overlapped SiLU requires the pipelined owner path")
  require(!commitTailRead || pipelined)
  require(!burstWrites || pipelined)
  require(Set(1,16).contains(weightReadBeats))
  require(s.retainedMatrix)
  require(!pipelined || (weightReadBeats==16 && s.matrixColumns==256))
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunch));val result=Decoupled(new HostCommandResult)
    val completion=Decoupled(UInt(56.W));val axi=new BlockAxiMaster
    val resetRequired=Output(Bool());val idmaTransfers=Output(UInt(64.W))
    val idmaStreamedWriteBeats=Output(UInt(64.W))
    val idmaStreamedBeats=Output(UInt(64.W));val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
    val idmaReadBursts=Output(UInt(64.W));val idmaReadBeats=Output(UInt(64.W));val idmaCacheHits=Output(UInt(64.W))
    val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W))
    val usefulMacs=Output(UInt(64.W));val executedMacs=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
    val memoryAccepted=Output(Vec(2,UInt(64.W)));val memoryReturned=Output(Vec(2,UInt(64.W)))
  })
  dontTouch(io)
  val cmd=Module(new HostBlockCommands(s,bf16Weights=pipelined,bf16V=bf16V,bf16Qkv=bf16Qkv,bf16Gdn=bf16Gdn,bf16GdnCore=bf16GdnCore,bf16GdnBlock=bf16GdnBlock,bf16QkNormRope=bf16QkNormRope,bf16AttentionCore=bf16AttentionCore));val owner=Module(new QwenOwnerKernel(s,pipelined,burstWrites,overlapSilu,bf16Gdn,bf16GdnCore,bf16GdnBlock,bf16QkNormRope,bf16AttentionCore))
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
    io.idmaReadBursts:=dma.io.readBeats;io.idmaReadBeats:=dma.io.readBeats;io.idmaCacheHits:=0.U;io.idmaStreamedBeats:=0.U;io.idmaStreamedWriteBeats:=0.U
  }else{
    val dma=Module(new RetainedIdmaWeightBurstAdapter(weightReadBeats,streaming=pipelined,burstWrites=burstWrites,commitTailRead=commitTailRead))
    val window=RegInit(0.U.asTypeOf(new IdmaWeightWindow))
    when(io.launch.fire||owner.io.done.fire){window.enable:=false.B}
    when(owner.io.job.fire){
      val job=owner.io.job.bits
      val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
      val end=job.b.pad(66)+(job.n.pad(66)*job.k.pad(66)*weightBytes)
      window.enable:=job.kind===QwenOwnerKind.Dense.U && end<=(BigInt(1)<<56).U
      window.base:=job.b;window.limit:=end(63,0)
    }
    dma.io.window:=window
    if(pipelined){dma.io.streamRequest.get<>owner.io.burst.get;owner.io.burstResponse.get<>dma.io.streamResponse.get}
    if(burstWrites){dma.io.streamWriteRequest.get<>owner.io.writeRequest.get;dma.io.streamWriteData.get<>owner.io.writeData.get;owner.io.writeResponse.get<>dma.io.streamWriteResponse.get}
    io.idmaStreamedWriteBeats:=dma.io.streamedWriteBeats
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
class HostBlockCollection(s:QwenBlockShape, weightReadBeats:Int=1,pipelined:Boolean=false,burstWrites:Boolean=false,commitTailRead:Boolean=false,overlapSilu:Boolean=false,bf16V:Boolean=false,bf16Qkv:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false) extends Module {
  val top=Module(new HostBlockTop(s,weightReadBeats,pipelined,burstWrites,commitTailRead,overlapSilu,bf16V,bf16Qkv,bf16Gdn,bf16GdnCore,bf16GdnBlock,bf16QkNormRope,bf16AttentionCore));val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val a=IO(chiselTypeOf(pre.io));a<>pre.io;dontTouch(a)
  val mul=Module(new HeteroBF16FmaMul);val b=IO(chiselTypeOf(mul.io));b<>mul.io;dontTouch(b)
  val post=Module(new HeteroBF16FmaPost);val c=IO(chiselTypeOf(post.io));c<>post.io;dontTouch(c)
  val round=Module(new HeteroBF16FmaRound);val d=IO(chiselTypeOf(round.io));d<>round.io;dontTouch(d)
}
object EmitHostBlock extends App {
  require((args.length>=2&&args.length<=8) && Set("tiny","real").contains(args(1)),"OUT tiny|real [512|4096] [weightReadBeats=1|16] [pipeline=0|1] [burstWrites=0|1] [commitTailRead=0|1] [overlapSilu=0|1]")
  val matrixMacs=if(args.length>=3)args(2).toInt else 4096
  require(Set(512,4096).contains(matrixMacs),"supported Matrix geometry")
  val weightReadBeats=if(args.length>=4)args(3).toInt else 1
  require(Set(1,16).contains(weightReadBeats))
  val pipelined=args.length>=5 && args(4)=="1"
  val burstWrites=args.length>=6 && args(5)=="1"
  val commitTailRead=args.length>=7 && args(6)=="1"
  require(args.length<8 || Set("0","1").contains(args(7)), "overlapSilu must be 0 or 1")
  val overlapSilu=args.length>=8 && args(7)=="1"
  require(!overlapSilu || pipelined, "overlapped SiLU requires the pipelined owner path")
  require(!commitTailRead || pipelined)
  require(!burstWrites || pipelined)
  require(!pipelined || (matrixMacs==4096 && weightReadBeats==16))
  val out=Paths.get(args(0));require(!Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  val s=(if(args(1)=="tiny")QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32)else QwenBlockShape()).copy(retainedMatrix=true,matrixColumns=matrixMacs/16)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(new HostBlockCollection(s,weightReadBeats,pipelined,burstWrites,commitTailRead,overlapSilu),firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("owner_shape.h"),s"""// Generated by Chisel. Do not edit.
#pragma once
#define OWNER_MATRIX_MACS ${matrixMacs}
#define OWNER_WEIGHT_READ_BEATS ${weightReadBeats}
#define OWNER_PIPELINED ${if(pipelined)1 else 0}
#define OWNER_BURST_WRITE ${if(burstWrites)1 else 0}
#define OWNER_COMMIT_TAIL_READ ${if(commitTailRead)1 else 0}
#define OWNER_OVERLAP_SILU ${if(overlapSilu)1 else 0}
static constexpr unsigned H=${s.hidden},F=${s.ffn},HEADS=${s.heads},KVHEADS=${s.kvHeads},HD=${s.headDim},MAX_TOKENS=${s.maxTokens};
""")
  Files.writeString(out.resolve("SCOPE.json"),s"""{"overlap_silu":${overlapSilu},"commit_tail_read":${commitTailRead},"burst_writes":${burstWrites},"pipelined":${pipelined},"silu_lanes":${if(pipelined)16 else 1},"dense_contexts":${if(pipelined)5 else 1},"weight_read_burst_beats":${weightReadBeats},"weight_read_cache_bytes":${if(weightReadBeats>1)1024 else 0},"host_commands":true,"block_launch":false,"hidden":${s.hidden},"ffn":${s.ffn},"retained_matrix":true,"matrix_macs":${matrixMacs},"matrix_columns":${s.matrixColumns},"matrix_rows":16,"logical_matrix_engines":1,"physical_matrix_slices":${matrixMacs/512},"peak_requires_context_interleaving":true,"pinned_idma":true,"attention_fusion":"checked QK/SOFTMAX/PV; no DDR scores","official_weights":false,"timing_signoff":false}\n""")
}

/** Explicit default-off experimental V storage route. Ordinary EmitHostBlock
  * remains unchanged; no Q/K or complete Qwen3.5 block is advertised here. */
object EmitHostBf16V extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  val s=QwenBlockShape.qwen35V()
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(s,16,true,burst,false,false,true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_v":true,"default_enabled":false,"policy_version":2,"owner_managed_staging":true,"hidden":1024,"q_context":2048,"packed_q":4096,"kv":512,"ffn":3584,"max_row":4096,"q_k_supported":false,"full_block_supported":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** Explicit projection-only Qwen3.5 route. The public Dense command selects
  * Q/gate, K or V with policy-v2 role 0, 1 or 2. Norm/RoPE and full blocks are
  * deliberately not admitted; arithmetic, Matrix slices and iDMA are shared. */
object EmitHostBf16Qkv extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  val s=QwenBlockShape.qwen35Qkv()
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(s,16,true,burst,false,false,bf16Qkv=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_qkv":true,"default_enabled":false,"policy_version":2,"owner_managed_staging":true,"hidden":1024,"q_context":2048,"packed_q":4096,"kv":512,"ffn":3584,"max_row":4096,"max_tokens":128,"q_role":0,"k_role":1,"v_role":2,"q_layout":"token_head_query256_gate256","q_k_supported":true,"norm_supported":false,"rope_supported":false,"full_block_supported":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** Default-off layer0 Dense-QKV -> Conv4/SiLU command subchain. The GDN owner
  * borrows the legacy core's scalar service and the original memory/iDMA path.
  * Recurrent FP32 state, gated norm and the complete block remain unsupported. */
object EmitHostBf16Gdn extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  val s=QwenBlockShape.qwen35Gdn()
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(s,16,true,burst,false,false,bf16Gdn=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_gdn":true,"default_enabled":false,"scope":"DENSE_QKV_CONV4_SILU_ONLY","policy_version":1,"hidden":1024,"gdn_channels":6144,"conv_kernel":4,"max_tokens":128,"managed_state_contexts":1,"scalar_service_shared":true,"conv_multiply_scalar_opcode":6,"recurrent_state_supported":false,"gated_norm_supported":false,"full_block_supported":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** The production Host root with explicit GDN-core policy v2. The final fence
  * publishes both recurrent state domains. This is still before O/residual/FFN. */
object EmitHostBf16GdnCore extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(QwenBlockShape.qwen35Gdn(),16,true,burst,false,false,bf16Gdn=true,bf16GdnCore=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_gdn":true,"experimental_gdn_core":true,"default_enabled":false,"scope":"GDN_CORE_M1_BEFORE_OUTPUT_PROJECTION","policy_version":2,"hidden":1024,"gdn_channels":6144,"conv_kernel":4,"max_tokens":1,"heads":16,"head_dim":128,"managed_state_contexts":1,"scalar_service_shared":true,"softplus_enabled":true,"recurrent_state_dtype":"FP32","full_block_supported":false,"output_projection_supported":false,"ffn_supported":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** Full layer0 GDN block policy v3. This emits structure only, never acceptance. */
object EmitHostBf16GdnBlock extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(QwenBlockShape.qwen35Gdn(),16,true,burst,false,false,bf16Gdn=true,bf16GdnCore=true,bf16GdnBlock=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_gdn":true,"experimental_gdn_core":true,"experimental_gdn_block":true,"default_enabled":false,"scope":"GDN_LAYER0_BLOCK_M1","policy_version":3,"hidden":1024,"ffn":3584,"gdn_channels":6144,"conv_kernel":4,"max_tokens":1,"heads":16,"head_dim":128,"managed_state_contexts":1,"scalar_service_shared":true,"softplus_enabled":true,"recurrent_state_dtype":"FP32","input_norm_dut":true,"output_projection_supported":true,"residual_supported":true,"ffn_supported":true,"full_block_supported":true,"numerical_acceptance":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** Default-off production Host QKV -> frozen QK Norm256 -> partial64 RoPE.
  * Only the command subchain is represented; attention and FFN are not admitted.
  */
object EmitHostBf16QkNormRope extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(QwenBlockShape.qwen35Qkv(),16,true,burst,false,false,bf16Qkv=true,bf16QkNormRope=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"experimental_bf16_qkv":true,"experimental_qk_norm_rope":true,"default_enabled":false,"scope":"QKV_NORM256_PARTIAL64_COMMAND_SUBCHAIN","projection_policy_version":2,"attention_policy_version":1,"norm_recipe":"C1","rope_recipe":"B1","hidden":1024,"q_context":2048,"packed_q":4096,"kv":512,"max_tokens":128,"q_heads":8,"kv_heads":2,"head_dim":256,"rotary_dim":64,"scalar_service_shared":true,"primitive_flags_shared":true,"attention_supported":false,"ffn_supported":false,"full_block_supported":false,"numerical_acceptance":false,"burst_writes":${burst},"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"timing_signoff":false}\n""")
}

/** Default-off production Attention core subchain; not a complete block. */
object EmitHostBf16AttentionCore extends App {
  require(args.length>=1 && args.length<=2,"OUT [burstWrites=0|1]")
  require(args.length<2 || Set("0","1").contains(args(1)))
  val burst=args.length==2 && args(1)=="1"
  val out=Paths.get(args(0));require(out.isAbsolute && !Files.exists(out),"preserve old outputs");Files.createDirectories(out)
  Files.writeString(out.resolve("HostBlockTop.sv"),ChiselStage.emitSystemVerilog(
    new HostBlockCollection(QwenBlockShape.qwen35Qkv(),16,true,burst,false,false,bf16Qkv=true,bf16QkNormRope=true,bf16AttentionCore=true),
    firtoolOpts=Array("--preserve-values=all","-disable-all-randomization")))
  Files.writeString(out.resolve("SCOPE.json"),s"""{"scope":"QKV_NORM_ROPE_KV_RECTANGULAR_GQA_CORE","default_enabled":false,"attention_policy_version":2,"input_norm_dut":false,"sigmoid_gate_dut":false,"output_projection_dut":false,"ffn_supported":false,"full_block_supported":false,"numerical_acceptance":false,"fault_restore_supported":false,"max_tokens":128,"max_cache_tokens":256,"scalar_service_shared":true,"logical_matrix_engines":1,"physical_matrix_slices":8,"pinned_idma_instances":1,"burst_writes":${burst}}\n""")
}
