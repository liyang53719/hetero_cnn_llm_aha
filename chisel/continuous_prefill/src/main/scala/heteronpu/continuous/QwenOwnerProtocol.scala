// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Internal, decoded owner job. Never a Host opcode or on-DDR encoding. */
object QwenOwnerKind { val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4; val Add=5; val Activation=6; val KvAppend=7; val GdnConv=8; val GdnRecurrent=9; val GdnInputPrep=10; val GdnRmsNorm=11; val GdnGatedNorm=12; val GdnElementwise=13; val QkNorm256=14; val PartialRope64=15 }
class QwenOwnerJob extends Bundle {
  // Explicit internal ABI extension. Values 0..7 retain their old meanings;
  // GDN is never truncated or aliased to a legacy owner kind.
  val kind=UInt(4.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val weightBf16=Bool() // Dense B storage, or explicit BF16 B in typed Attention jobs.
  val activationBf16=Bool() // Typed A storage; false preserves legacy Dense FP32 ingress.
  val outputBf16=Bool() // Explicit terminal RNE BF16 D storage; false preserves FP32 stores.
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
  val historyOut=UInt(64.W);val expectedGeneration=UInt(32.W);val currentGeneration=UInt(32.W);val cold=Bool()
  // Explicit BF16 Attention context extension; legacy jobs leave these zero.
  val cacheCapacity=UInt(32.W);val cacheLength=UInt(32.W)
  val expectedCacheLength=UInt(32.W);val queryStart=UInt(32.W)
  val qkRole=UInt(2.W);val qkPositionBase=UInt(32.W);val qkTrigTokens=UInt(32.W)
  val gdnALog=UInt(64.W);val gdnDtBias=UInt(64.W);val gdnStateOut=UInt(64.W);val gdnRecurrentMode=Bool();val gdnElementwiseOp=UInt(2.W)
}
class QwenOwnerResult extends Bundle {
  val tag=UInt(32.W); val status=UInt(8.W); val writeBytes=UInt(64.W)
  val cycles=UInt(64.W); val usefulMacs=UInt(64.W); val executedMacs=UInt(64.W)
}
/** No block launch is exposed. One decoded owner operation per transaction;
  * the arithmetic implementation must return instead of advancing to a phase.
  */
class QwenOwnerKernel(s:QwenBlockShape,pipelined:Boolean=false,burstWrites:Boolean=false,overlapSilu:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false) extends Module {
  require(!bf16AttentionCore || bf16QkNormRope,"Attention core requires the explicit QKV/Norm/RoPE profile")
  require(!bf16QkNormRope || (pipelined && s.qwen35QkvOnly && !bf16Gdn), "QK Norm/RoPE requires the exclusive pipelined QKV profile")
  require(!bf16Gdn || (pipelined && s.qwen35GdnOnly), "GDN requires the explicit pipelined profile")
  require(!bf16GdnCore || bf16Gdn, "GDN core requires the explicit GDN profile")
  require(!bf16GdnBlock || bf16GdnCore, "GDN block requires the explicit core profile")
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
    val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true,externalMatrix=true,externalScalar=bf16Gdn||bf16QkNormRope,enableGdnSoftplus=bf16GdnCore))
    core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
    val dense=Module(new StreamingDenseOwner(s.maxRow,burstWrites=burstWrites))
    // The core-only GDN command profile never accepts legacy Activation jobs.
    // Do not elaborate the otherwise unused sixteen-lane legacy SFU here.
    val silu=if(bf16GdnCore||bf16QkNormRope)None else Some(Module(new ScheduledSiluOwner(overlapSilu)))
    val matrix=Module(new MatrixPipelineService)
    val legacy=Module(new LegacyMatrixStreamClient)
    val gdn=if(bf16Gdn)Some(Module(new GdnConv4Owner(channels=6144,maxTokens=s.maxTokens)))else None
    val prep=if(bf16GdnCore)Some(Module(new GdnInputPrepOwner(heads=16)))else None
    val recurrent=if(bf16GdnCore)Some(Module(new GdnRecurrentOwner(maxHeads=16)))else None
    val gatedNorm=if(bf16GdnCore)Some(Module(new GdnGatedNormOwner(heads=16,maxTokens=1)))else None
    legacy.io.request<>core.io.matrixRequest.get;core.io.matrixResult.get<>legacy.io.result
    core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps
    dense.io.physicalSteps:=matrix.io.acceptedSteps
    val rmsNorm=if(bf16GdnBlock)Some(Module(new GdnRmsNormOwner(width=1024,maxTokens=1)))else None
    val elementwise=if(bf16GdnBlock)Some(Module(new GdnElementwiseOwner(hiddenWidth=1024,ffnWidth=3584,maxTokens=1)))else None
    val qkNorm=if(bf16QkNormRope)Some(Module(new QkNorm256Owner(qHeads=8,kvHeads=2,maxTokens=s.maxTokens)))else None
    val partialRope=if(bf16QkNormRope)Some(Module(new PartialRope64Owner(maxHeads=8,maxTokens=s.maxTokens)))else None
    val kvAppend=if(bf16AttentionCore)Some(Module(new Bf16KvAppendOwner(maxTokens=s.maxTokens)))else None
    val gqa=if(bf16AttentionCore)Some(Module(new Bf16CausalGqaOwner(maxTokens=s.maxTokens,maxCacheTokens=256)))else None
    val kvRoot=Reg(UInt(64.W));val kvCapacity=Reg(UInt(32.W));val kvLength=Reg(UInt(32.W))
    val gqaPhysicalBase=Reg(UInt(64.W));val gqaLogicalMacs=Reg(UInt(64.W))
    val active=RegInit(false.B);val mode=Reg(UInt(4.W));val tag=Reg(UInt(32.W));val rejected=RegInit(false.B)
    val gdnExpected=Reg(UInt(32.W));val gdnCurrent=Reg(UInt(32.W))
    val chooseCore=Mux(bf16Gdn.B && io.job.bits.kind===QwenOwnerKind.GdnConv.U,3.U,
      Mux(bf16GdnCore.B && io.job.bits.kind===QwenOwnerKind.GdnInputPrep.U,4.U,
        Mux(bf16GdnCore.B && io.job.bits.kind===QwenOwnerKind.GdnRecurrent.U,5.U,
          Mux(bf16GdnCore.B && io.job.bits.kind===QwenOwnerKind.GdnGatedNorm.U,6.U,
            Mux(io.job.bits.kind>QwenOwnerKind.KvAppend.U,7.U,
              Mux(io.job.bits.kind===QwenOwnerKind.Dense.U,1.U,Mux((bf16GdnCore||bf16QkNormRope).B,7.U,Mux(io.job.bits.kind===QwenOwnerKind.Activation.U,2.U,0.U))))))))
    val chooseBase=Mux(bf16GdnBlock.B && io.job.bits.kind===QwenOwnerKind.GdnRmsNorm.U,8.U,
      Mux(bf16GdnBlock.B && io.job.bits.kind===QwenOwnerKind.GdnElementwise.U,9.U,chooseCore))
    val chooseQk=Mux(bf16QkNormRope.B && io.job.bits.kind===QwenOwnerKind.QkNorm256.U,10.U,
      Mux(bf16QkNormRope.B && io.job.bits.kind===QwenOwnerKind.PartialRope64.U,11.U,chooseBase))
    val attentionTyped=io.job.bits.activationBf16 && io.job.bits.weightBf16 && io.job.bits.outputBf16 &&
      io.job.bits.cacheCapacity>0.U && io.job.bits.cacheCapacity<=256.U
    val choose=Mux(bf16AttentionCore.B && io.job.bits.kind===QwenOwnerKind.KvAppend.U,
      Mux(attentionTyped && io.job.bits.n===512.U,12.U,7.U),
      Mux(bf16AttentionCore.B && io.job.bits.kind===QwenOwnerKind.Attention.U,
        Mux(attentionTyped && io.job.bits.n===2048.U,13.U,7.U),chooseQk))
    val gdnReady=gdn.map(_.io.job.ready).getOrElse(false.B)
    val gdnPoison=(gdn.toSeq.map(_.io.resetRequired)++prep.toSeq.map(_.io.resetRequired)++recurrent.toSeq.map(_.io.resetRequired)++gatedNorm.toSeq.map(_.io.resetRequired)++rmsNorm.toSeq.map(_.io.resetRequired)++elementwise.toSeq.map(_.io.resetRequired)++qkNorm.toSeq.map(_.io.resetRequired)++partialRope.toSeq.map(_.io.resetRequired)++kvAppend.toSeq.map(_.io.resetRequired)++gqa.toSeq.map(_.io.resetRequired)).foldLeft(false.B)(_||_)
    val sharedPoison=core.io.resetRequired||dense.io.resetRequired||silu.map(_.io.resetRequired).getOrElse(false.B)||matrix.io.resetRequired||legacy.io.resetRequired
    val canStart= !active && !rejected && !gdnPoison && !((bf16Gdn||bf16QkNormRope).B && sharedPoison)
    io.job.ready:=canStart && MuxLookup(choose,false.B)(Seq(0.U->core.io.ownerJob.get.ready,1.U->dense.io.job.ready,2.U->silu.map(_.io.job.ready).getOrElse(false.B),3.U->gdnReady,
      4.U->prep.map(_.io.job.ready).getOrElse(false.B),5.U->recurrent.map(_.io.job.ready).getOrElse(false.B),6.U->gatedNorm.map(_.io.job.ready).getOrElse(false.B),7.U->true.B,8.U->rmsNorm.map(_.io.job.ready).getOrElse(false.B),9.U->elementwise.map(_.io.job.ready).getOrElse(false.B),10.U->qkNorm.map(_.io.job.ready).getOrElse(false.B),11.U->partialRope.map(_.io.job.ready).getOrElse(false.B),12.U->kvAppend.map(_.io.job.ready).getOrElse(false.B),13.U->gqa.map(_.io.job.ready).getOrElse(false.B)))
    core.io.ownerJob.get.valid:=io.job.valid && canStart && choose===0.U;core.io.ownerJob.get.bits:=io.job.bits
    dense.io.job.valid:=io.job.valid && canStart && choose===1.U;dense.io.job.bits:=io.job.bits
    silu.foreach{a=>a.io.job.valid:=io.job.valid && canStart && choose===2.U;a.io.job.bits:=io.job.bits}
    when(io.job.fire){active:=true.B;mode:=choose;tag:=io.job.bits.tag
      when(choose===3.U || choose===5.U || choose===12.U){gdnExpected:=io.job.bits.expectedGeneration;gdnCurrent:=io.job.bits.currentGeneration}
      when(choose===12.U){kvRoot:=io.job.bits.dst;kvCapacity:=io.job.bits.cacheCapacity;kvLength:=io.job.bits.cacheLength+io.job.bits.m}
      when(choose===13.U){gqaPhysicalBase:=matrix.io.acceptedSteps;gqaLogicalMacs:=(io.job.bits.m.pad(64)*io.job.bits.cacheLength.pad(64))<<12}
      when(choose===7.U){rejected:=true.B}
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
      gdnValid:=gd.io.done.valid;gdnDone.tag:=gd.io.done.bits.tag
      val invalidCommit=gd.io.done.bits.status===0.U &&
        (!gd.io.done.bits.historyCommitted || gd.io.done.bits.generation=/=gdnExpected+1.U)
      gdnDone.status:=Mux(invalidCommit,Status.Protocol.U,gd.io.done.bits.status)
      gdnDone.writeBytes:=gd.io.done.bits.writeBytes;gdnDone.cycles:=gd.io.done.bits.cycles
      gd.io.done.ready:=active && mode===3.U && io.done.ready
      when(gd.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val prepDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val prepValid=WireDefault(false.B)
    prep.foreach{p=>
      p.io.job.valid:=io.job.valid && canStart && choose===4.U
      p.io.job.bits.tokens:=io.job.bits.m;p.io.job.bits.heads:=io.job.bits.n
      p.io.job.bits.queryIn:=io.job.bits.a;p.io.job.bits.keyIn:=io.job.bits.a+4096.U;p.io.job.bits.valueIn:=io.job.bits.a+8192.U
      p.io.job.bits.ab:=io.job.bits.b;p.io.job.bits.aLog:=io.job.bits.gdnALog;p.io.job.bits.dtBias:=io.job.bits.gdnDtBias
      p.io.job.bits.query:=io.job.bits.dst;p.io.job.bits.key:=io.job.bits.dst+8192.U;p.io.job.bits.value:=io.job.bits.dst+16384.U;p.io.job.bits.gates:=io.job.bits.dst+24576.U
      p.io.job.bits.recurrentMode:=io.job.bits.gdnRecurrentMode;p.io.job.bits.tag:=io.job.bits.tag
      prepValid:=p.io.done.valid;prepDone.tag:=p.io.done.bits.tag
      val invalidCommit=p.io.done.bits.status===0.U && !p.io.done.bits.outputCommitted
      prepDone.status:=Mux(invalidCommit,Status.Protocol.U,p.io.done.bits.status)
      prepDone.writeBytes:=p.io.done.bits.writeBytes;prepDone.cycles:=p.io.done.bits.cycles
      p.io.done.ready:=active && mode===4.U && io.done.ready
      when(p.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val recurrentDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val recurrentValid=WireDefault(false.B)
    recurrent.foreach{r=>
      r.io.job.valid:=io.job.valid && canStart && choose===5.U
      r.io.job.bits.tokens:=io.job.bits.m;r.io.job.bits.heads:=io.job.bits.n;r.io.job.bits.keyDim:=io.job.bits.k;r.io.job.bits.valueDim:=io.job.bits.k
      r.io.job.bits.query:=io.job.bits.a;r.io.job.bits.key:=io.job.bits.a+8192.U;r.io.job.bits.value:=io.job.bits.a+16384.U;r.io.job.bits.gates:=io.job.bits.a+24576.U
      r.io.job.bits.stateIn:=io.job.bits.b;r.io.job.bits.stateOut:=io.job.bits.gdnStateOut;r.io.job.bits.output:=io.job.bits.dst
      r.io.job.bits.cold:=io.job.bits.cold;r.io.job.bits.expectedGeneration:=io.job.bits.expectedGeneration;r.io.job.bits.tag:=io.job.bits.tag
      r.io.currentGeneration:=Mux(active,gdnCurrent,io.job.bits.currentGeneration)
      recurrentValid:=r.io.done.valid;recurrentDone.tag:=r.io.done.bits.tag
      val invalidCommit=r.io.done.bits.status===0.U && (!r.io.done.bits.stateCommitted || r.io.done.bits.generation=/=gdnExpected+1.U)
      recurrentDone.status:=Mux(invalidCommit,Status.Protocol.U,r.io.done.bits.status)
      recurrentDone.writeBytes:=r.io.done.bits.writeBytes;recurrentDone.cycles:=r.io.done.bits.cycles
      r.io.done.ready:=active && mode===5.U && io.done.ready
      when(r.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val gatedDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gatedValid=WireDefault(false.B)
    gatedNorm.foreach{n=>
      n.io.job.valid:=io.job.valid && canStart && choose===6.U
      n.io.job.bits.tokens:=io.job.bits.m;n.io.job.bits.heads:=io.job.bits.n
      n.io.job.bits.core:=io.job.bits.a;n.io.job.bits.gate:=io.job.bits.b;n.io.job.bits.weight:=io.job.bits.c;n.io.job.bits.output:=io.job.bits.dst;n.io.job.bits.tag:=io.job.bits.tag
      gatedValid:=n.io.done.valid;gatedDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===0.U && !n.io.done.bits.outputCommitted
      gatedDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      gatedDone.writeBytes:=n.io.done.bits.writeBytes;gatedDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===6.U && io.done.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val rmsDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val rmsValid=WireDefault(false.B)
    rmsNorm.foreach{n=>
      n.io.job.valid:=io.job.valid && canStart && choose===8.U
      n.io.job.bits.tokens:=io.job.bits.m;n.io.job.bits.hiddenWidth:=io.job.bits.n
      n.io.job.bits.input:=io.job.bits.a;n.io.job.bits.weight:=io.job.bits.b;n.io.job.bits.output:=io.job.bits.dst;n.io.job.bits.tag:=io.job.bits.tag
      rmsValid:=n.io.done.valid;rmsDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===0.U && !n.io.done.bits.outputCommitted
      rmsDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      rmsDone.writeBytes:=n.io.done.bits.writeBytes;rmsDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===8.U && io.done.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val elementDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val elementValid=WireDefault(false.B)
    elementwise.foreach{e=>
      e.io.job.valid:=io.job.valid && canStart && choose===9.U
      e.io.job.bits.op:=io.job.bits.gdnElementwiseOp;e.io.job.bits.tokens:=io.job.bits.m;e.io.job.bits.rowWidth:=io.job.bits.n
      e.io.job.bits.a:=io.job.bits.a;e.io.job.bits.b:=io.job.bits.b;e.io.job.bits.output:=io.job.bits.dst;e.io.job.bits.tag:=io.job.bits.tag
      elementValid:=e.io.done.valid;elementDone.tag:=e.io.done.bits.tag
      val invalidCommit=e.io.done.bits.status===0.U && !e.io.done.bits.outputCommitted
      elementDone.status:=Mux(invalidCommit,Status.Protocol.U,e.io.done.bits.status)
      elementDone.writeBytes:=e.io.done.bits.writeBytes;elementDone.cycles:=e.io.done.bits.cycles
      e.io.done.ready:=active && mode===9.U && io.done.ready
      when(e.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val qkNormDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val qkNormValid=WireDefault(false.B)
    qkNorm.foreach{n=>
      n.io.job.valid:=io.job.valid && canStart && choose===10.U
      n.io.job.bits.tokens:=io.job.bits.m;n.io.job.bits.role:=io.job.bits.qkRole
      n.io.job.bits.headDim:=io.job.bits.k;n.io.job.bits.policy:="hc1".U;n.io.job.bits.epsilon:="h358637bd".U
      n.io.job.bits.input:=io.job.bits.a;n.io.job.bits.weight:=io.job.bits.b
      n.io.job.bits.output:=io.job.bits.dst;n.io.job.bits.gateOutput:=io.job.bits.c;n.io.job.bits.tag:=io.job.bits.tag
      n.io.scalarFlags:=core.io.scalarPrimitiveFlags.get;n.io.scalarFlagsValid:=core.io.scalarPrimitiveFlagsValid.get
      qkNormValid:=n.io.done.valid;qkNormDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===0.U && !n.io.done.bits.outputCommitted
      qkNormDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      qkNormDone.writeBytes:=n.io.done.bits.writeBytes;qkNormDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===10.U && io.done.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val partialRopeDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val partialRopeValid=WireDefault(false.B)
    partialRope.foreach{r=>
      r.io.job.valid:=io.job.valid && canStart && choose===11.U
      r.io.job.bits.tokens:=io.job.bits.m;r.io.job.bits.heads:=io.job.bits.n
      r.io.job.bits.headDim:=io.job.bits.k;r.io.job.bits.rotaryDim:=64.U;r.io.job.bits.policy:="hb1".U
      r.io.job.bits.input:=io.job.bits.a;r.io.job.bits.trig:=io.job.bits.b;r.io.job.bits.output:=io.job.bits.dst
      r.io.job.bits.positionBase:=io.job.bits.qkPositionBase;r.io.job.bits.trigTokens:=io.job.bits.qkTrigTokens;r.io.job.bits.tag:=io.job.bits.tag
      r.io.scalarFlags:=core.io.scalarPrimitiveFlags.get;r.io.scalarFlagsValid:=core.io.scalarPrimitiveFlagsValid.get
      partialRopeValid:=r.io.done.valid;partialRopeDone.tag:=r.io.done.bits.tag
      val invalidCommit=r.io.done.bits.status===0.U && !r.io.done.bits.outputCommitted
      partialRopeDone.status:=Mux(invalidCommit,Status.Protocol.U,r.io.done.bits.status)
      partialRopeDone.writeBytes:=r.io.done.bits.writeBytes;partialRopeDone.cycles:=r.io.done.bits.cycles
      r.io.done.ready:=active && mode===11.U && io.done.ready
      when(r.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val kvAppendDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val kvAppendValid=WireDefault(false.B)
    kvAppend.foreach{kv=>
      kv.io.job.valid:=io.job.valid && canStart && choose===12.U
      kv.io.job.bits.tokens:=io.job.bits.m;kv.io.job.bits.kvHeads:=2.U;kv.io.job.bits.headDim:=io.job.bits.k
      kv.io.job.bits.keyInput:=io.job.bits.a;kv.io.job.bits.valueInput:=io.job.bits.b;kv.io.job.bits.cacheBase:=io.job.bits.dst
      kv.io.job.bits.capacityTokens:=io.job.bits.cacheCapacity;kv.io.job.bits.appendStart:=io.job.bits.queryStart
      kv.io.job.bits.currentLength:=io.job.bits.cacheLength;kv.io.job.bits.expectedLength:=io.job.bits.expectedCacheLength
      kv.io.job.bits.currentGeneration:=io.job.bits.currentGeneration;kv.io.job.bits.expectedGeneration:=io.job.bits.expectedGeneration
      kv.io.job.bits.cold:=io.job.bits.cold;kv.io.job.bits.tag:=io.job.bits.tag
      kvAppendValid:=kv.io.done.valid;kvAppendDone.tag:=kv.io.done.bits.tag
      val invalidProposal=kv.io.done.bits.status===0.U && (!kv.io.done.bits.proposalValid ||
        kv.io.done.bits.cacheBase=/=kvRoot || kv.io.done.bits.capacityTokens=/=kvCapacity ||
        kv.io.done.bits.proposedLength=/=kvLength || kv.io.done.bits.proposedGeneration=/=gdnExpected+1.U)
      kvAppendDone.status:=Mux(invalidProposal,Status.Protocol.U,kv.io.done.bits.status)
      kvAppendDone.writeBytes:=kv.io.done.bits.writeBytes;kvAppendDone.cycles:=kv.io.done.bits.cycles
      kv.io.done.ready:=active && mode===12.U && io.done.ready
      when(kv.io.done.fire && invalidProposal){rejected:=true.B}
    }
    val gqaDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gqaValid=WireDefault(false.B)
    gqa.foreach{a=>
      a.io.job.valid:=io.job.valid && canStart && choose===13.U
      a.io.job.bits.tokens:=io.job.bits.m;a.io.job.bits.queryHeads:=8.U;a.io.job.bits.kvHeads:=2.U;a.io.job.bits.headDim:=io.job.bits.k
      a.io.job.bits.queryInput:=io.job.bits.a;a.io.job.bits.cacheBase:=io.job.bits.b;a.io.job.bits.output:=io.job.bits.dst
      a.io.job.bits.queryStart:=io.job.bits.queryStart;a.io.job.bits.cacheLength:=io.job.bits.cacheLength
      a.io.job.bits.capacityTokens:=io.job.bits.cacheCapacity;a.io.job.bits.tag:=io.job.bits.tag
      gqaValid:=a.io.done.valid;gqaDone.tag:=a.io.done.bits.tag
      val invalidCommit=a.io.done.bits.status===0.U && !a.io.done.bits.outputCommitted
      gqaDone.status:=Mux(invalidCommit,Status.Protocol.U,a.io.done.bits.status)
      gqaDone.writeBytes:=a.io.done.bits.writeBytes;gqaDone.cycles:=a.io.done.bits.cycles
      // Completed logical QK/PV products include causal-zero PV terms.
      // Failed jobs do not claim completed useful products.
      gqaDone.usefulMacs:=Mux(gqaDone.status===0.U,gqaLogicalMacs,0.U)
      gqaDone.executedMacs:=(matrix.io.acceptedSteps-gqaPhysicalBase)*512.U
      a.io.done.ready:=active && mode===13.U && io.done.ready
      when(a.io.done.fire && invalidCommit){rejected:=true.B}
    }
    // The accepted owner retains exclusive scalar ownership until done.
    // All clients use the one existing core ALU/divider/exp service.
    if(bf16Gdn||bf16QkNormRope){
      val clients=gdn.toSeq.map(x=>3->x.io.scalar)++prep.toSeq.map(x=>4->x.io.scalar)++recurrent.toSeq.map(x=>5->x.io.scalar)++gatedNorm.toSeq.map(x=>6->x.io.scalar)++rmsNorm.toSeq.map(x=>8->x.io.scalar)++elementwise.toSeq.map(x=>9->x.io.scalar)++qkNorm.toSeq.map(x=>10->x.io.scalar)++partialRope.toSeq.map(x=>11->x.io.scalar)++gqa.toSeq.map(x=>13->x.io.scalar)
      val service=core.io.scalarService.get
      service.request.valid:=active && MuxLookup(mode,false.B)(clients.map{case(i,c)=>i.U->c.request.valid})
      service.request.bits:=MuxLookup(mode,0.U.asTypeOf(new ScalarRequest))(clients.map{case(i,c)=>i.U->c.request.bits})
      service.result.ready:=active && MuxLookup(mode,false.B)(clients.map{case(i,c)=>i.U->c.result.ready})
      for((i,c)<-clients){
        c.request.ready:=active && mode===i.U && service.request.ready
        c.result.valid:=active && mode===i.U && service.result.valid
        c.result.bits:=service.result.bits;c.error:=service.error
      }
    }
    val rejectedDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));rejectedDone.tag:=tag;rejectedDone.status:=Status.Unsupported.U
    val oldDone=Wire(new QwenOwnerResult)
    oldDone.tag:=tag;oldDone.status:=core.io.result.bits.status;oldDone.cycles:=core.io.result.bits.cycles
    oldDone.writeBytes:=core.io.acknowledgedWriteBytes;oldDone.usefulMacs:=core.io.result.bits.macs;oldDone.executedMacs:=core.io.result.bits.executedMacs
    io.done.valid:=active && MuxLookup(mode,false.B)(Seq(0.U->core.io.result.valid,1.U->dense.io.done.valid,2.U->silu.map(_.io.done.valid).getOrElse(false.B),3.U->gdnValid,4.U->prepValid,5.U->recurrentValid,6.U->gatedValid,7.U->true.B,8.U->rmsValid,9.U->elementValid,10.U->qkNormValid,11.U->partialRopeValid,12.U->kvAppendValid,13.U->gqaValid))
    io.done.bits:=MuxLookup(mode,rejectedDone)(Seq(0.U->oldDone,1.U->dense.io.done.bits,2.U->silu.map(_.io.done.bits).getOrElse(rejectedDone),3.U->gdnDone,4.U->prepDone,5.U->recurrentDone,6.U->gatedDone,8.U->rmsDone,9.U->elementDone,10.U->qkNormDone,11.U->partialRopeDone,12.U->kvAppendDone,13.U->gqaDone))
    core.io.result.ready:=active&&mode===0.U&&io.done.ready
    dense.io.done.ready:=active&&mode===1.U&&io.done.ready;silu.foreach{a=>a.io.done.ready:=active&&mode===2.U&&io.done.ready}
    when(io.done.fire){active:=false.B}
    // Explicit mode keys keep GDN slots stable when legacy Activation is absent.
    val memories=Seq(0->core.io.memory,1->dense.io.memory)++silu.toSeq.map(x=>2->x.io.memory)++gdn.toSeq.map(x=>3->x.io.memory)++prep.toSeq.map(x=>4->x.io.memory)++recurrent.toSeq.map(x=>5->x.io.memory)++gatedNorm.toSeq.map(x=>6->x.io.memory)++rmsNorm.toSeq.map(x=>8->x.io.memory)++elementwise.toSeq.map(x=>9->x.io.memory)++qkNorm.toSeq.map(x=>10->x.io.memory)++partialRope.toSeq.map(x=>11->x.io.memory)++kvAppend.toSeq.map(x=>12->x.io.memory)++gqa.toSeq.map(x=>13->x.io.memory)
    val responses=Seq(0->core.io.response,1->dense.io.response)++silu.toSeq.map(x=>2->x.io.response)++gdn.toSeq.map(x=>3->x.io.response)++prep.toSeq.map(x=>4->x.io.response)++recurrent.toSeq.map(x=>5->x.io.response)++gatedNorm.toSeq.map(x=>6->x.io.response)++rmsNorm.toSeq.map(x=>8->x.io.response)++elementwise.toSeq.map(x=>9->x.io.response)++qkNorm.toSeq.map(x=>10->x.io.response)++partialRope.toSeq.map(x=>11->x.io.response)++kvAppend.toSeq.map(x=>12->x.io.response)++gqa.toSeq.map(x=>13->x.io.response)
    io.memory.valid:=active&&MuxLookup(mode,false.B)(memories.map{case(i,p)=>i.U->p.valid})
    io.memory.bits:=MuxLookup(mode,0.U.asTypeOf(new MemoryRequest))(memories.map{case(i,p)=>i.U->p.bits})
    io.response.ready:=active&&MuxLookup(mode,false.B)(responses.map{case(i,p)=>i.U->p.ready})
    for((i,p)<-memories){p.ready:=active&&mode===i.U&&io.memory.ready}
    for((i,p)<-responses){p.valid:=active&&mode===i.U&&io.response.valid;p.bits:=io.response.bits}
    if(burstWrites){io.writeRequest.get<>dense.io.writeRequest.get;io.writeData.get<>dense.io.writeData.get;dense.io.writeResponse.get<>io.writeResponse.get}
    io.burst.get<>dense.io.burst;dense.io.burstResponse<>io.burstResponse.get
    if(bf16AttentionCore){
      // Exactly one retained service owns all eight physical slices. The
      // selected owner retains the service through terminal result and done.
      val clients=Seq(0->legacy.io.port,1->dense.io.matrix)++gqa.toSeq.map(x=>13->x.io.matrix)
      val selectedMode=Mux(active,mode,0.U)
      for((i,c)<-clients){
        val selected=selectedMode===i.U
        c.group.ready:=selected && matrix.io.port.group.ready
        c.step.ready:=selected && matrix.io.port.step.ready
        c.result.valid:=selected && matrix.io.port.result.valid;c.result.bits:=matrix.io.port.result.bits
        c.done.valid:=selected && matrix.io.port.done.valid;c.done.bits:=matrix.io.port.done.bits
      }
      matrix.io.port.group.valid:=MuxLookup(selectedMode,false.B)(clients.map{case(i,c)=>i.U->c.group.valid})
      matrix.io.port.group.bits:=MuxLookup(selectedMode,0.U.asTypeOf(new MatrixStreamGroup))(clients.map{case(i,c)=>i.U->c.group.bits})
      matrix.io.port.step.valid:=MuxLookup(selectedMode,false.B)(clients.map{case(i,c)=>i.U->c.step.valid})
      matrix.io.port.step.bits:=MuxLookup(selectedMode,0.U.asTypeOf(new MatrixStreamStep))(clients.map{case(i,c)=>i.U->c.step.bits})
      matrix.io.port.result.ready:=MuxLookup(selectedMode,false.B)(clients.map{case(i,c)=>i.U->c.result.ready})
      matrix.io.port.done.ready:=MuxLookup(selectedMode,false.B)(clients.map{case(i,c)=>i.U->c.done.ready})
      matrix.io.port.abort:=MuxLookup(selectedMode,false.B)(clients.map{case(i,c)=>i.U->c.abort})
    }else{
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
    }
    io.pipelineIssues:=matrix.io.wideSteps;io.pipelineStalls:=matrix.io.stallCycles
    io.resetRequired:=rejected||gdnPoison||core.io.resetRequired||dense.io.resetRequired||silu.map(_.io.resetRequired).getOrElse(false.B)||matrix.io.resetRequired||legacy.io.resetRequired
  }
}
