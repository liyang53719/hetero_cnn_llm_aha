// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Numerical materialization policy. This does not select packed storage. */
sealed trait Qwen2NumericPolicy
object Qwen2NumericPolicy {
  case object LegacyV0 extends Qwen2NumericPolicy
  case object Qwen2OfficialBf16V2 extends Qwen2NumericPolicy
  def official(policy:Qwen2NumericPolicy):Boolean=policy match {
    case LegacyV0=>false
    case Qwen2OfficialBf16V2=>true
  }
  def checkShape(policy:Qwen2NumericPolicy,s:QwenBlockShape):Unit={
    require(!official(policy) || (!s.nativeProfile && s.hidden==1536 && s.ffn==8960 &&
      s.heads==12 && s.kvHeads==2 && s.headDim==128 && s.maxTokens==1024),
      "Qwen2OfficialBf16V2 rejects Qwen3.5 native and non-Qwen2 public21 shapes")
  }
}

/** Private fixed Scalar borrowing interface for the common five-profile parent.
  * The parent must validate its allocator/whole-group lease BEFORE offering a
  * request. Echoing a tag is correlation, not authority or stale-data isolation.
  * No host policy/boolean grants a lease. Reset requires joint isolation.
  */
object QwenSharedScalarContractV3 { val ScalarResource=2 } // UnifiedResourceKind.Scalar ABI
class QwenSharedScalarRequestV3 extends Bundle {
  val identity=new UnifiedSharedOperationTagV3
  val payload=new UnifiedScalarRequestV2
}
class QwenSharedScalarResultV3 extends Bundle {
  val identity=new UnifiedSharedOperationTagV3
  val payload=new UnifiedScalarResultV2
}
class QwenSharedScalarStatusV3 extends Bundle {
  // Cumulative private-port counts since isolated reset, NOT a release receipt.
  // accepted includes the one held offer; issued is physical request.fire;
  // returned is matching consumer result.fire, never primitive valid alone.
  val counts=new UnifiedSharedOperationCountsV3
  val heldRequest=Bool();val pending=Bool();val heldResult=Bool()
  val resourcesDrained=Bool();val resetRequired=Bool()
}
class QwenSharedScalarServiceV3 extends Bundle {
  val request=Flipped(Decoupled(new QwenSharedScalarRequestV3))
  val result=Decoupled(new QwenSharedScalarResultV3)
  val status=Output(new QwenSharedScalarStatusV3)
}

/** Private runtime RMS/Conv borrower (runtimeRms is the historical port name). The Top supplies raw clients ONLY under its
  * retained ordinary Guard job/txn/physical-sequence lease. This port grants no
  * authority; no MoE allocation is forged for an ordinary operation. */
class QwenRuntimeRmsClientV6 extends Bundle {
  val scalar=new UnifiedScalarClientV2
  val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
  val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
  val parentFault=Input(Bool())
  val resourcesDrained=Output(Bool())
}

/** Internal, decoded owner job. Never a Host opcode or on-DDR encoding. */
object QwenOwnerKind { val Norm=0; val Dense=1; val Bias=2; val Rope=3; val Attention=4; val Add=5; val Activation=6; val KvAppend=7; val GdnConv=8; val GdnRecurrent=9; val GdnInputPrep=10; val GdnRmsNorm=11; val GdnGatedNorm=12; val GdnElementwise=13; val QkNorm256=14; val PartialRope64=15 }
class QwenOwnerJob extends Bundle {
  // Explicit internal ABI extension. Values 0..7 retain their old meanings;
  // GDN is never truncated or aliased to a legacy owner kind.
  val kind=UInt(4.W); val m=UInt(16.W); val n=UInt(16.W); val k=UInt(16.W)
  val a=UInt(64.W); val b=UInt(64.W); val c=UInt(64.W); val dst=UInt(64.W)
  val weightBf16=Bool() // Dense B storage, or explicit BF16 B in typed Attention jobs.
  val activationBf16=Bool() // Typed A storage; false preserves legacy Dense FP32 ingress.
  val materializeDenseOutput=Bool() // Numerical BF16 value in FP32 storage, bound by validated public role.
  val outputBf16=Bool() // Explicit terminal RNE BF16 D storage; false preserves FP32 stores.
  val writeBytes=UInt(64.W); val tag=UInt(32.W)
  val historyOut=UInt(64.W);val expectedGeneration=UInt(32.W);val currentGeneration=UInt(32.W);val cold=Bool()
  // Explicit BF16 Attention context extension; legacy jobs leave these zero.
  val cacheCapacity=UInt(32.W);val cacheLength=UInt(32.W)
  val expectedCacheLength=UInt(32.W);val queryStart=UInt(32.W)
  val qkRole=UInt(2.W);val qkPositionBase=UInt(32.W);val qkTrigTokens=UInt(32.W)
  val gdnALog=UInt(64.W);val gdnDtBias=UInt(64.W);val gdnStateOut=UInt(64.W);val gdnRecurrentMode=Bool();val gdnElementwiseOp=UInt(2.W)
}
/** Internal cancellation/recovery only. clear attests external memory/Scalar
  * recovery and stale-response exclusion; drained alone is not that attestation.
  */
class QwenRmsBorrowerControl extends Bundle {
  val abort=Input(Bool());val clear=Input(Bool())
  val drained=Output(Bool());val locked=Output(Bool())
}
class QwenOwnerResult extends Bundle {
  val tag=UInt(32.W); val status=UInt(8.W); val writeBytes=UInt(64.W)
  val cycles=UInt(64.W); val usefulMacs=UInt(64.W); val executedMacs=UInt(64.W)
}
/** No block launch is exposed. One decoded owner operation per transaction;
  * the arithmetic implementation must return instead of advancing to a phase.
  */
class QwenOwnerKernel(s:QwenBlockShape,pipelined:Boolean=false,burstWrites:Boolean=false,overlapSilu:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false,bf16AttentionBlock:Boolean=false,enableH2048RmsBorrower:Boolean=false,enableTransposedDense:Boolean=false,enableTransposedSeed:Boolean=false,enableTransposedDown:Boolean=false,enableFfnTiles:Boolean=false,enableFfnWindow:Boolean=false,enableFfnDrain:Boolean=false,enableResidentFfn:Boolean=false,enablePublic21QkvReduction:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableProductionPackedQk16:Boolean=false,enableOrderedVectorQkFold:Boolean=false,enableUnifiedScalarService:Boolean=false,enableRuntimeRmsNorm:Boolean=false,enableRuntimeConv:Boolean=false,enableRuntimeRawPrep:Boolean=false,enableRuntimeChunk:Boolean=false,enableRuntimeGatedNorm:Boolean=false) extends Module {
  require(!enableRuntimeGatedNorm || enableRuntimeChunk,"runtime GatedNorm follows the actual Chunk and shared ordinary arithmetic chain")
  require(!enableRuntimeChunk || enableRuntimeRawPrep,"runtime Chunk uses the real RawPrep and shared ordinary arithmetic chain")
  require(!enableRuntimeRawPrep || enableRuntimeRmsNorm,"runtime RawPrep reuses the ordinary Scalar/format port")
  require(!enableRuntimeConv || enableRuntimeRmsNorm,"runtime Conv reuses the common ordinary Scalar/format port")
  require(!enableRuntimeRmsNorm || (pipelined && enableUnifiedScalarService && !enableH2048RmsBorrower),
    "runtime RMS replaces the legacy borrower and uses the single tagged shared arithmetic path")
  require(!enableOrderedVectorQkFold || enableProductionPackedQk16,"ordered vector QK fold requires packed QK16")
  require(!enableProductionPackedQk16 || (pipelined && Qwen2NumericPolicy.official(numericPolicy) && !bf16Gdn && !bf16QkNormRope && !bf16AttentionCore && !enableH2048RmsBorrower), "production QK16 keeps the official Qwen2 owner profile")
  require(!enableH2048RmsBorrower || (pipelined && (bf16GdnBlock || bf16AttentionBlock) && s.maxTokens<=128),
    "H2048 RMS borrower requires a pipelined BF16 block profile with at most 128 tokens")
  require(!enablePublic21QkvReduction || (pipelined && enableResidentFfn && enableTransposedDown && !overlapSilu && !enableH2048RmsBorrower && Qwen2NumericPolicy.official(numericPolicy)),
    "public21 QKV reduction requires the original official resident chain")
  Qwen2NumericPolicy.checkShape(numericPolicy,s)
  require(!Qwen2NumericPolicy.official(numericPolicy) || (enableResidentFfn && !bf16Gdn && !bf16QkNormRope && !bf16AttentionCore),
    "official policy requires the public21 resident Qwen2 chain")
  require(!enableResidentFfn || (enableFfnWindow && enableFfnDrain && enableFfnTiles),"resident coordinator owns all internal services")
  require(!enableFfnDrain || enableFfnTiles,"act drain requires the selected shared tile owner")
  require(!enableFfnWindow || enableFfnTiles,"internal windows require the selected shared tile owner")
  require(!enableFfnTiles || (enableTransposedDown && !overlapSilu),"FFN tile loan requires the selected Down owner and serial SiLU")
  require(!enableTransposedDown || enableTransposedSeed,"Down chunks require the prefix seed profile")
  require(!enableTransposedSeed || enableTransposedDense,"prefix restore requires the transposed owner profile")
  require(!enableTransposedDense || (pipelined && !bf16Gdn && !bf16QkNormRope),
    "transposed Dense is an explicit Qwen2 pipelined elaboration profile")
  require(!bf16AttentionBlock || bf16AttentionCore,"Attention block requires the explicit core profile")
  require(!bf16AttentionCore || bf16QkNormRope,"Attention core requires the explicit QKV/Norm/RoPE profile")
  require(!bf16QkNormRope || (pipelined && s.qwen35QkvOnly && !bf16Gdn), "QK Norm/RoPE requires the exclusive pipelined QKV profile")
  require(!bf16Gdn || (pipelined && s.qwen35GdnOnly), "GDN requires the explicit pipelined profile")
  require(!bf16GdnCore || bf16Gdn, "GDN core requires the explicit GDN profile")
  require(!bf16GdnBlock || bf16GdnCore, "GDN block requires the explicit core profile")
  require(!burstWrites || pipelined)
  require(!overlapSilu || pipelined, "overlapped SiLU requires the pipelined owner path")
  val io=IO(new Bundle {
    // Compatibility switch only: a common five-profile top MUST set this true
    // once for every runtime profile, never specialize it by profileId.
    val sharedScalar=if(enableUnifiedScalarService)Some(new QwenSharedScalarServiceV3)else None
    val runtimeRms=if(enableRuntimeRmsNorm)Some(new QwenRuntimeRmsClientV6)else None
    val runtimeChunk=if(enableRuntimeChunk)Some(new QwenRuntimeChunkClientV9)else None
    val runtimeGatedDoneFire=if(enableRuntimeGatedNorm)Some(Output(Valid(new GdnRuntimeGatedNormResultV10)))else None
    val runtimePrepPrepare=if(enableRuntimeRawPrep)Some(Decoupled(new GdnRuntimeRawPrepReadyV7))else None
    // Read-only ACTUAL child terminal transfer; generic QwenOwnerResult drops
    // accepted/outputCommitted. Parent must bind this event to its Guard lease.
    val runtimePrepDoneFire=if(enableRuntimeRawPrep)Some(Output(Valid(new GdnRuntimeRawPrepResultV7)))else None
    val public21BackendReset=if(enablePublic21QkvReduction)Some(Input(Bool()))else None
    val resident=if(enableResidentFfn)Some(new FfnResidentPort)else None
    val residentHandoff=if(enableResidentFfn)Some(Output(Valid(new QwenOwnerJob)))else None
    val drain=if(enableFfnDrain && !enableResidentFfn)Some(new FfnDrainPort)else None
    val window=if(enableFfnWindow && !enableResidentFfn)Some(new FfnWindowPort(enableFfnDrain))else None
    val tiles=if(enableFfnTiles && !enableResidentFfn)Some(new FfnTilePort(enableMatrixProducerOrder=enableFfnWindow))else None
    val tileSilu=if(enableFfnTiles && !enableResidentFfn)Some(new FfnSiluLoanPort)else None
    val job=Flipped(Decoupled(new QwenOwnerJob)); val done=Decoupled(new QwenOwnerResult)
    val memory=Decoupled(new MemoryRequest); val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool())
    val resourcesDrained=Output(Bool()) // private actual aggregate, not !active
    val rmsBorrowerControl=if(enableH2048RmsBorrower)Some(new QwenRmsBorrowerControl)else None
    val burst=if(pipelined)Some(Decoupled(new BurstReadRequest))else None
    val burstResponse=if(pipelined)Some(Flipped(Decoupled(new BurstReadResponse)))else None
    val writeRequest=if(burstWrites)Some(Decoupled(new BurstWriteRequest))else None
    val writeData=if(burstWrites)Some(Decoupled(new BurstWriteBeat))else None
    val writeResponse=if(burstWrites)Some(Flipped(Decoupled(new MemoryResponse)))else None
    val prefixWorkspace=if(enableTransposedSeed)Some(Input(new TransposedPrefixWorkspace(if(enableTransposedDown)2560 else 1536)))else None
    val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
  })
  val resident=if(enableResidentFfn)Some(Module(new FfnResidentCoordinator))else None
  val qkvRouter=if(enablePublic21QkvReduction)Some(Module(new Public21QkvReductionRouter))else None
  val ordinaryJob=if(enablePublic21QkvReduction)qkvRouter.get.io.ordinaryJob else io.job
  val ordinaryDone=if(enablePublic21QkvReduction)qkvRouter.get.io.ordinaryDone else io.done
  val residentInput=if(enablePublic21QkvReduction)Some(qkvRouter.get.io.resident)else io.resident
  val ffnWindow=if(enablePublic21QkvReduction)Some(qkvRouter.get.io.window)else if(enableResidentFfn)Some(resident.get.io.window)else io.window
  val ffnTiles=if(enablePublic21QkvReduction)Some(qkvRouter.get.io.tiles)else if(enableResidentFfn)Some(resident.get.io.tiles)else io.tiles
  val ffnTileSilu=if(enablePublic21QkvReduction)Some(qkvRouter.get.io.vector)else if(enableResidentFfn)Some(resident.get.io.silu)else io.tileSilu
  val ffnDrain=if(enablePublic21QkvReduction)Some(qkvRouter.get.io.drain)else if(enableResidentFfn)Some(resident.get.io.drain)else io.drain
  if(enableResidentFfn){resident.get.io.group<>residentInput.get;
    io.residentHandoff.get:=resident.get.io.handoff}
  if(enablePublic21QkvReduction){
    val r=qkvRouter.get
    r.io.job<>io.job;io.done<>r.io.done;r.io.residentHost<>io.resident.get
    r.io.residentWindow<>resident.get.io.window;r.io.residentDrain<>resident.get.io.drain
    r.io.residentTiles<>resident.get.io.tiles;r.io.residentVector<>resident.get.io.silu
    r.io.residentHandoff:=resident.get.io.handoff;io.residentHandoff.get:=r.io.handoff
  }
  if(!pipelined){
  val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true,numericPolicy=numericPolicy,enableUnifiedScalarService=enableUnifiedScalarService))
  if(enableUnifiedScalarService){
    io.sharedScalar.get<>core.io.sharedScalar.get
    core.io.sharedScalarSchedulerAvailable.get:=true.B
  }
  core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
  core.io.ownerJob.get<>ordinaryJob
  val tag=Reg(UInt(32.W));when(ordinaryJob.fire){tag:=ordinaryJob.bits.tag}
  ordinaryDone.valid:=core.io.result.valid;core.io.result.ready:=ordinaryDone.ready
  ordinaryDone.bits.tag:=tag;ordinaryDone.bits.status:=core.io.result.bits.status
  ordinaryDone.bits.writeBytes:=core.io.acknowledgedWriteBytes
  ordinaryDone.bits.cycles:=core.io.result.bits.cycles
  ordinaryDone.bits.usefulMacs:=core.io.result.bits.macs;ordinaryDone.bits.executedMacs:=core.io.result.bits.executedMacs
  io.memory<>core.io.memory;core.io.response<>io.response;io.resetRequired:=core.io.resetRequired
  io.resourcesDrained:=core.io.resourcesDrained && !io.job.valid && !io.done.valid
    io.pipelineIssues:=0.U;io.pipelineStalls:=0.U
  }else{
    require(s.matrixColumns==256 && s.retainedMatrix)
    val core=Module(new Qwen2ContinuousBlock(s,ownerDriven=true,externalMatrix=true,externalScalar=bf16Gdn||bf16QkNormRope,enableGdnSoftplus=bf16GdnCore,externalElementwiseLoan=enableH2048RmsBorrower,numericPolicy=numericPolicy,enableProductionPackedQk16=enableProductionPackedQk16,enableOrderedVectorQkFold=enableOrderedVectorQkFold,enableUnifiedScalarService=enableUnifiedScalarService))
    val sharedScalarAvailable=WireDefault(false.B)
    val sharedScalarOwned=io.sharedScalar.map(p=>p.status.heldRequest || p.status.pending || p.result.valid).getOrElse(false.B)
    val sharedScalarExclusive=sharedScalarOwned || io.sharedScalar.map(_.request.valid).getOrElse(false.B)
    if(enableUnifiedScalarService){
      val parent=io.sharedScalar.get;val service=core.io.sharedScalar.get
      // Forward valid/bits unchanged even while Core backpressures. Admission
      // is a ready-side interlock, never a withdrawal of an offered request.
      service.request.valid:=parent.request.valid
      service.request.bits:=parent.request.bits
      parent.request.ready:=service.request.ready
      core.io.sharedScalarSchedulerAvailable.get:=sharedScalarAvailable
      parent.result<>service.result;parent.status:=service.status
    }
    core.io.launch.valid:=false.B;core.io.launch.bits:=0.U.asTypeOf(new BlockLaunch)
    // Elaborate one owner and one bank allocation; the common IO is storage-free.
    val dense:DenseOwnerIO=if(enableTransposedDown)
      Module(new TransposedDenseDownOwner(burstWrites=burstWrites,enableFfnTiles=enableFfnTiles,enableFfnWindow=enableFfnWindow,enableFfnDrain=enableFfnDrain,numericPolicy=numericPolicy,enableKWindow=enablePublic21QkvReduction,enableDenseDrain=enablePublic21QkvReduction)).io
    else if(enableTransposedSeed)
      Module(new TransposedDenseSeedOwner(burstWrites=burstWrites)).io
    else if(enableTransposedDense)
      Module(new TransposedDenseOwner(burstWrites=burstWrites)).io
    else Module(new StreamingDenseOwner(s.maxRow,burstWrites=burstWrites)).io
    // The core-only GDN command profile never accepts legacy Activation jobs.
    // Do not elaborate the otherwise unused sixteen-lane legacy SFU here.
    val silu=if(bf16GdnCore||bf16QkNormRope)None else Some(Module(new ScheduledSiluOwner(overlapSilu,enableTileLoan=enableFfnTiles,numericPolicy=numericPolicy,enableBinaryAdd=enablePublic21QkvReduction)))
    if(enableFfnTiles){dense.tiles.get<>ffnTiles.get;silu.get.io.loan.get<>ffnTileSilu.get}
    val matrix=Module(new MatrixPipelineService(enableTransposedDense=enableTransposedDense,enableAccumulatorSeed=enableTransposedSeed,enablePackedDrainStatus=enableProductionPackedQk16))
    if(enableTransposedSeed){dense.prefixWorkspace.get:=io.prefixWorkspace.get}
    val legacy=Module(new LegacyMatrixStreamClient)
    val gdn=if(bf16Gdn && !enableRuntimeConv)Some(Module(new GdnConv4Owner(channels=6144,maxTokens=s.maxTokens)))else None
    val runtimeConv=if(enableRuntimeConv)Some(Module(new GdnRuntimeConv4OwnerV6))else None
    val prep=if(bf16GdnCore && !enableRuntimeRawPrep)Some(Module(new GdnInputPrepOwner(heads=16)))else None
    val runtimeRawPrep=if(enableRuntimeRawPrep)Some(Module(new GdnRuntimeRawPrepOwnerV7))else None
    val chunk=if(enableRuntimeChunk)Some(Module(new GdnRuntimeChunkLeafCollection))else None
    val recurrent=if(bf16GdnCore)Some(Module(new GdnRecurrentOwner(maxHeads=16)))else None
    val runtimeGatedNorm=if(enableRuntimeGatedNorm)Some(Module(new GdnRuntimeGatedNormOwnerV10))else None
    val gatedNorm=if(bf16GdnCore && !enableRuntimeGatedNorm)Some(Module(new GdnGatedNormOwner(heads=16,maxTokens=1)))else None
    legacy.io.request<>core.io.matrixRequest.get;core.io.matrixResult.get<>legacy.io.result
    core.io.matrixAcceptedSteps.get:=matrix.io.acceptedSteps
    dense.physicalSteps:=matrix.io.acceptedSteps
    // The common Top enables this ONCE for all runtime profiles. One fixed
    // three-bank owner replaces, rather than parallels, either legacy RMS.
    // Qwen2 kind Norm continues to use its unchanged original FP32 path.
    val runtimeRms=if(enableRuntimeRmsNorm)Some(Module(new GdnRuntimeRmsNormOwnerV3))else None
    val rmsBorrower=if(enableH2048RmsBorrower)Some(Module(new GdnRmsNormFixedBankOwner(s.maxTokens)))else None
    val rmsNorm:Seq[GdnRmsNormOwnerPort]=if(enableRuntimeRmsNorm)Seq.empty
      else if(enableH2048RmsBorrower)rmsBorrower.toSeq.map(_.io)
      else if(bf16GdnBlock||bf16AttentionBlock)Seq(Module(new GdnRmsNormOwner(width=1024,maxTokens=1)).io)
      else Seq.empty
    val elementwise=if(bf16GdnBlock||bf16AttentionBlock)Some(Module(new GdnElementwiseOwner(hiddenWidth=1024,ffnWidth=3584,maxTokens=1,attentionWidth=2048,enableAttentionSigmoidMul=bf16AttentionBlock)))else None
    val qkNorm=if(bf16QkNormRope)Some(Module(new QkNorm256Owner(qHeads=8,kvHeads=2,maxTokens=s.maxTokens)))else None
    val partialRope=if(bf16QkNormRope)Some(Module(new PartialRope64Owner(maxHeads=8,maxTokens=s.maxTokens)))else None
    val kvAppend=if(bf16AttentionCore)Some(Module(new Bf16KvAppendOwner(maxTokens=s.maxTokens)))else None
    val gqa=if(bf16AttentionCore)Some(Module(new Bf16CausalGqaOwner(maxTokens=s.maxTokens,maxCacheTokens=256)))else None
    val kvRoot=Reg(UInt(64.W));val kvCapacity=Reg(UInt(32.W));val kvLength=Reg(UInt(32.W))
    val gqaPhysicalBase=Reg(UInt(64.W));val gqaLogicalMacs=Reg(UInt(64.W))
    val active=RegInit(false.B);val mode=Reg(UInt(4.W));val tag=Reg(UInt(32.W));val rejected=RegInit(false.B)
    // One shared raw client pair serves only the actually selected ordinary
    // borrower. Mode is retained until all actual terminal/debt retires; no
    // profile constructor chooses a second numerical service.
    if(enableRuntimeRmsNorm){
      val port=io.runtimeRms.get
      val clients=runtimeRms.toSeq.map(n=>(8,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))++
        runtimeConv.toSeq.map(n=>(3,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))++
        runtimeRawPrep.toSeq.map(n=>(4,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))++
        runtimeGatedNorm.toSeq.map(n=>(6,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))
      port.scalar.request.valid:=active && MuxLookup(mode,false.B)(clients.map{case(i,s,f,r,d)=>i.U->s.request.valid})
      port.scalar.request.bits:=MuxLookup(mode,0.U.asTypeOf(new UnifiedScalarRequestV2))(clients.map{case(i,s,f,r,d)=>i.U->s.request.bits})
      port.scalar.result.ready:=MuxLookup(mode,false.B)(clients.map{case(i,s,f,r,d)=>i.U->s.result.ready})
      port.formatRequest.valid:=active && MuxLookup(mode,false.B)(clients.map{case(i,s,f,r,d)=>i.U->f.valid})
      port.formatRequest.bits:=MuxLookup(mode,0.U.asTypeOf(new UnifiedRawFp32FormatRequestV3))(clients.map{case(i,s,f,r,d)=>i.U->f.bits})
      port.formatResult.ready:=MuxLookup(mode,false.B)(clients.map{case(i,s,f,r,d)=>i.U->r.ready})
      for((i,s,f,r,d)<-clients){
        s.request.ready:=active && mode===i.U && port.scalar.request.ready
        s.result.valid:=mode===i.U && port.scalar.result.valid;s.result.bits:=port.scalar.result.bits
        f.ready:=active && mode===i.U && port.formatRequest.ready
        r.valid:=mode===i.U && port.formatResult.valid;r.bits:=port.formatResult.bits
      }
      runtimeRms.foreach(_.io.parentFault:=port.parentFault)
      runtimeConv.foreach(_.io.parentFault:=port.parentFault)
      runtimeRawPrep.foreach(_.io.parentFault:=port.parentFault)
      runtimeGatedNorm.foreach(_.io.parentFault:=port.parentFault)
      port.resourcesDrained:=clients.map(_._5).reduce(_&&_)
    }

    val transportFault=WireDefault(false.B)
    val transportQuarantine=RegInit(false.B);when(transportFault){transportQuarantine:=true.B}
    val gdnExpected=Reg(UInt(32.W));val gdnCurrent=Reg(UInt(32.W))
    val chooseCore=Mux((bf16Gdn||enableRuntimeConv).B && ordinaryJob.bits.kind===QwenOwnerKind.GdnConv.U,3.U,
      Mux((bf16GdnCore||enableRuntimeRawPrep).B && ordinaryJob.bits.kind===QwenOwnerKind.GdnInputPrep.U,4.U,
        Mux(bf16GdnCore.B && ordinaryJob.bits.kind===QwenOwnerKind.GdnRecurrent.U,5.U,
          Mux((bf16GdnCore||enableRuntimeGatedNorm).B && ordinaryJob.bits.kind===QwenOwnerKind.GdnGatedNorm.U,6.U,
            Mux(ordinaryJob.bits.kind>QwenOwnerKind.KvAppend.U,7.U,
              Mux(ordinaryJob.bits.kind===QwenOwnerKind.Dense.U,1.U,Mux((bf16GdnCore||bf16QkNormRope).B,7.U,Mux(ordinaryJob.bits.kind===QwenOwnerKind.Activation.U,2.U,0.U))))))))
    val rmsTyped=ordinaryJob.bits.activationBf16 && ordinaryJob.bits.weightBf16 && ordinaryJob.bits.outputBf16 &&
      ordinaryJob.bits.n===2048.U && ordinaryJob.bits.k===2048.U &&
      ordinaryJob.bits.writeBytes===(ordinaryJob.bits.m.pad(64)<<12)(63,0)
    val runtimeRmsTyped=ordinaryJob.bits.activationBf16 && ordinaryJob.bits.weightBf16 && ordinaryJob.bits.outputBf16 &&
      ordinaryJob.bits.m>=1.U && ordinaryJob.bits.m<=128.U &&
      (ordinaryJob.bits.n===1024.U || ordinaryJob.bits.n===2048.U) && ordinaryJob.bits.k===ordinaryJob.bits.n &&
      ordinaryJob.bits.writeBytes===(ordinaryJob.bits.m.pad(64)*ordinaryJob.bits.n.pad(64)<<1)(63,0)
    val rmsMode=if(enableRuntimeRmsNorm)Mux(runtimeRmsTyped,8.U,7.U)
      else if(enableH2048RmsBorrower)Mux(rmsTyped,8.U,7.U)else 8.U
    val chooseChunk=Mux(enableRuntimeChunk.B && HostRuntimeChunkJobV9.selected(ordinaryJob.bits),14.U,chooseCore)
    val chooseBase=Mux((enableRuntimeRmsNorm||bf16GdnBlock||bf16AttentionBlock).B && ordinaryJob.bits.kind===QwenOwnerKind.GdnRmsNorm.U,rmsMode,
      Mux((bf16GdnBlock||bf16AttentionBlock).B && ordinaryJob.bits.kind===QwenOwnerKind.GdnElementwise.U,9.U,chooseChunk))
    val chooseQk=Mux(bf16QkNormRope.B && ordinaryJob.bits.kind===QwenOwnerKind.QkNorm256.U,10.U,
      Mux(bf16QkNormRope.B && ordinaryJob.bits.kind===QwenOwnerKind.PartialRope64.U,11.U,chooseBase))
    val attentionTyped=ordinaryJob.bits.activationBf16 && ordinaryJob.bits.weightBf16 && ordinaryJob.bits.outputBf16 &&
      ordinaryJob.bits.cacheCapacity>0.U && ordinaryJob.bits.cacheCapacity<=256.U
    val choose=if(enableFfnTiles)Mux(ffnTiles.get.leased && ordinaryJob.bits.kind=/=QwenOwnerKind.Dense.U,7.U,Mux(bf16AttentionCore.B && ordinaryJob.bits.kind===QwenOwnerKind.KvAppend.U,
      Mux(attentionTyped && ordinaryJob.bits.n===512.U,12.U,7.U),
      Mux(bf16AttentionCore.B && ordinaryJob.bits.kind===QwenOwnerKind.Attention.U,
        Mux(attentionTyped && ordinaryJob.bits.n===2048.U,13.U,7.U),chooseQk)))else Mux(bf16AttentionCore.B && ordinaryJob.bits.kind===QwenOwnerKind.KvAppend.U,
      Mux(attentionTyped && ordinaryJob.bits.n===512.U,12.U,7.U),
      Mux(bf16AttentionCore.B && ordinaryJob.bits.kind===QwenOwnerKind.Attention.U,
        Mux(attentionTyped && ordinaryJob.bits.n===2048.U,13.U,7.U),chooseQk))
    val gdnReady=gdn.map(_.io.job.ready).getOrElse(false.B) || runtimeConv.map(_.io.job.ready).getOrElse(false.B)
    val gdnPoison=(chunk.toSeq.map(_.io.resetRequired)++gdn.toSeq.map(_.io.resetRequired)++runtimeConv.toSeq.map(_.io.resetRequired)++prep.toSeq.map(_.io.resetRequired)++runtimeRawPrep.toSeq.map(_.io.resetRequired)++recurrent.toSeq.map(_.io.resetRequired)++gatedNorm.toSeq.map(_.io.resetRequired)++runtimeGatedNorm.toSeq.map(_.io.resetRequired)++rmsNorm.map(_.resetRequired)++runtimeRms.toSeq.map(_.io.resetRequired)++elementwise.toSeq.map(_.io.resetRequired)++qkNorm.toSeq.map(_.io.resetRequired)++partialRope.toSeq.map(_.io.resetRequired)++kvAppend.toSeq.map(_.io.resetRequired)++gqa.toSeq.map(_.io.resetRequired)).foldLeft(false.B)(_||_)
    val sharedPoison=core.io.resetRequired||dense.resetRequired||silu.map(_.io.resetRequired).getOrElse(false.B)||matrix.io.resetRequired||legacy.io.resetRequired
    val rmsBorrowerUnavailable=WireDefault(false.B)
    rmsBorrower.foreach{n=>
      val control=io.rmsBorrowerControl.get
      val selected= !active || mode===8.U
      n.io.abort:=selected && control.abort;n.io.clear:=selected && control.clear
      control.drained:=selected && n.io.drained;control.locked:=n.io.locked
      val loan=core.io.elementwiseLoan.get
      loan.request.valid:=active && mode===8.U && n.io.loan.request.valid
      loan.request.bits:=n.io.loan.request.bits
      n.io.loan.request.ready:=active && mode===8.U && loan.request.ready
      // Terminal drain and recovery remain connected after owner done retires.
      n.io.loan.result.valid:=loan.result.valid;n.io.loan.result.bits:=loan.result.bits
      loan.result.ready:=n.io.loan.result.ready
      loan.abort:=n.io.loan.abort;loan.resetLoan:=n.io.loan.resetLoan
      n.io.loan.busy:=loan.busy;n.io.loan.resetRequired:=loan.resetRequired
      n.io.vectorUnavailable:=core.io.elementwiseResetRequired.get
      rmsBorrowerUnavailable:=control.abort || control.clear || n.io.locked ||
        n.io.loan.request.valid || loan.busy || loan.result.valid || core.io.elementwiseResetRequired.get ||
        (!active && (io.response.valid || core.io.scalarService.get.result.valid))
    }
    val canStart= !active && !sharedScalarExclusive && !transportQuarantine && !transportFault && !rejected && !gdnPoison && !((bf16Gdn||bf16QkNormRope||enableTransposedDense).B && sharedPoison) && !rmsBorrowerUnavailable
    if(enableResidentFfn){
      val g=resident.get.io.group;val host=residentInput.get
      val available= !active && !sharedScalarOwned && !rejected && !gdnPoison && !sharedPoison
      g.request.valid:=host.request.valid && available;host.request.ready:=g.request.ready && available
      // Register aggregate service failure before feeding an abort back into
      // those same services. The coordinator's local poison is also sticky.
      g.abort:=host.abort || RegNext(sharedPoison || gdnPoison,false.B)
    }
    if(enableFfnTiles){
      val available=if(enableFfnDrain)!active && !sharedScalarOwned && !sharedPoison && !rejected && !dense.drain.get.busy && !dense.window.map(_.busy).getOrElse(false.B)else if(enableFfnWindow)!active && !sharedScalarOwned && !sharedPoison && !rejected && !dense.window.get.busy else !active && !sharedScalarOwned && !sharedPoison && !rejected
      dense.tiles.get.control.valid:=ffnTiles.get.control.valid && available
      ffnTiles.get.control.ready:=dense.tiles.get.control.ready && available
      dense.tiles.get.write.valid:=ffnTiles.get.write.valid && available
      ffnTiles.get.write.ready:=dense.tiles.get.write.ready && available
      dense.tiles.get.read.valid:=ffnTiles.get.read.valid && available
      ffnTiles.get.read.ready:=dense.tiles.get.read.ready && available
      silu.get.io.loan.get.request.valid:=ffnTileSilu.get.request.valid && available
      ffnTileSilu.get.request.ready:=silu.get.io.loan.get.request.ready && available
    }
    val tileBusy=if(enableFfnTiles)ffnTiles.get.busy || ffnTileSilu.get.busy || ffnTiles.get.control.valid || ffnTiles.get.write.valid || ffnTiles.get.read.valid || ffnTileSilu.get.request.valid || ffnTiles.get.abort || ffnTileSilu.get.abort else false.B
    if(enableFfnWindow){
      dense.window.get<>ffnWindow.get
      dense.window.get.invalidateLease:=ffnWindow.get.invalidateLease || ordinaryJob.fire
      val available=if(enableFfnDrain)!active && !sharedScalarOwned && !sharedPoison && !rejected && !tileBusy && !dense.drain.get.busy else !active && !sharedScalarOwned && !sharedPoison && !rejected && !tileBusy
      dense.window.get.request.valid:=ffnWindow.get.request.valid && available
      ffnWindow.get.request.ready:=dense.window.get.request.ready && available
      // The window shares the poison domain; an upstream service failure must
      // reach the owner's normal drain path and invalidate its A lease.
      dense.tiles.get.abort:=ffnTiles.get.abort || ffnTileSilu.get.abort ||
        (dense.window.get.busy && (core.io.resetRequired || matrix.io.resetRequired || legacy.io.resetRequired || silu.get.io.resetRequired))
    }
    if(enableFfnDrain){
      dense.drain.get<>ffnDrain.get
      val available= !active && !sharedScalarOwned && !sharedPoison && !rejected && !tileBusy && !dense.window.map(_.busy).getOrElse(false.B) && !ffnWindow.map(_.request.valid).getOrElse(false.B)
      dense.drain.get.request.valid:=ffnDrain.get.request.valid && available
      ffnDrain.get.request.ready:=dense.drain.get.request.ready && available
      dense.drain.get.abort:=ffnDrain.get.abort || ffnTiles.get.abort || ffnTileSilu.get.abort ||
        (dense.drain.get.busy && (core.io.resetRequired || matrix.io.resetRequired || legacy.io.resetRequired || silu.get.io.resetRequired))
    }
    val drainBusy=if(enableFfnDrain)dense.drain.get.busy || ffnDrain.get.request.valid else false.B
    val windowBusy=if(enableFfnWindow)dense.window.get.busy || ffnWindow.get.request.valid else false.B
    val canStartWithTiles=if(enableResidentFfn)canStart && !tileBusy && !windowBusy && !drainBusy && !resident.get.io.group.busy && !residentInput.get.request.valid
    else if(enableFfnDrain)canStart && !tileBusy && !windowBusy && !drainBusy else if(enableFfnWindow)canStart && !tileBusy && !windowBusy else if(enableFfnTiles)canStart && !tileBusy else canStart
    val chunkJobHeld=RegInit(false.B);val gatedJobHeld=RegInit(false.B)
    val ordinaryCanStart=canStartWithTiles || (enableRuntimeChunk.B && chunkJobHeld && choose===14.U) ||
      (enableRuntimeGatedNorm.B && gatedJobHeld && choose===6.U)
    ordinaryJob.ready:=ordinaryCanStart && MuxLookup(choose,false.B)(Seq(0.U->core.io.ownerJob.get.ready,1.U->dense.job.ready,2.U->silu.map(_.io.job.ready).getOrElse(false.B),3.U->gdnReady,
      4.U->(prep.map(_.io.job.ready).getOrElse(false.B) || runtimeRawPrep.map(_.io.job.ready).getOrElse(false.B)),5.U->recurrent.map(_.io.job.ready).getOrElse(false.B),6.U->(gatedNorm.map(_.io.job.ready).getOrElse(false.B) || runtimeGatedNorm.map(_.io.job.ready).getOrElse(false.B)),7.U->true.B,8.U->(rmsNorm.headOption.map(_.job.ready).getOrElse(false.B) || runtimeRms.map(_.io.job.ready).getOrElse(false.B)),9.U->elementwise.map(_.io.job.ready).getOrElse(false.B),10.U->qkNorm.map(_.io.job.ready).getOrElse(false.B),11.U->partialRope.map(_.io.job.ready).getOrElse(false.B),12.U->kvAppend.map(_.io.job.ready).getOrElse(false.B),13.U->gqa.map(_.io.job.ready).getOrElse(false.B),14.U->chunk.map(_.io.job.ready).getOrElse(false.B)))
    core.io.ownerJob.get.valid:=ordinaryJob.valid && canStartWithTiles && choose===0.U;core.io.ownerJob.get.bits:=ordinaryJob.bits
    dense.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===1.U;dense.job.bits:=ordinaryJob.bits
    silu.foreach{a=>a.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===2.U;a.io.job.bits:=ordinaryJob.bits}
    when(ordinaryJob.fire){active:=true.B;mode:=choose;tag:=ordinaryJob.bits.tag
      when(choose===3.U || choose===5.U || choose===12.U){gdnExpected:=ordinaryJob.bits.expectedGeneration;gdnCurrent:=ordinaryJob.bits.currentGeneration}
      when(choose===12.U){kvRoot:=ordinaryJob.bits.dst;kvCapacity:=ordinaryJob.bits.cacheCapacity;kvLength:=ordinaryJob.bits.cacheLength+ordinaryJob.bits.m}
      when(choose===13.U){gqaPhysicalBase:=matrix.io.acceptedSteps;gqaLogicalMacs:=(ordinaryJob.bits.m.pad(64)*ordinaryJob.bits.cacheLength.pad(64))<<12}
      when(choose===7.U){rejected:=true.B}
    }
    val gdnDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gdnValid=WireDefault(false.B)
    gdn.foreach{gd=>
      gd.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===3.U
      gd.io.job.bits.tokens:=ordinaryJob.bits.m;gd.io.job.bits.channels:=ordinaryJob.bits.n
      gd.io.job.bits.input:=ordinaryJob.bits.a;gd.io.job.bits.weight:=ordinaryJob.bits.b
      gd.io.job.bits.historyIn:=ordinaryJob.bits.c;gd.io.job.bits.historyOut:=ordinaryJob.bits.historyOut
      gd.io.job.bits.output:=ordinaryJob.bits.dst;gd.io.job.bits.cold:=ordinaryJob.bits.cold
      gd.io.job.bits.expectedGeneration:=ordinaryJob.bits.expectedGeneration;gd.io.job.bits.tag:=ordinaryJob.bits.tag
      gd.io.currentGeneration:=Mux(active,gdnCurrent,ordinaryJob.bits.currentGeneration)
      gdnValid:=gd.io.done.valid;gdnDone.tag:=gd.io.done.bits.tag
      val invalidCommit=gd.io.done.bits.status===0.U &&
        (!gd.io.done.bits.historyCommitted || gd.io.done.bits.generation=/=gdnExpected+1.U)
      gdnDone.status:=Mux(invalidCommit,Status.Protocol.U,gd.io.done.bits.status)
      gdnDone.writeBytes:=gd.io.done.bits.writeBytes;gdnDone.cycles:=gd.io.done.bits.cycles
      gd.io.done.ready:=active && mode===3.U && ordinaryDone.ready
      when(gd.io.done.fire && invalidCommit){rejected:=true.B}
    }
    runtimeConv.foreach{gd=>
      gd.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===3.U
      gd.io.job.bits.tokens:=ordinaryJob.bits.m;gd.io.job.bits.channels:=ordinaryJob.bits.n
      gd.io.job.bits.input:=ordinaryJob.bits.a;gd.io.job.bits.weight:=ordinaryJob.bits.b
      gd.io.job.bits.historyIn:=ordinaryJob.bits.c;gd.io.job.bits.historyOut:=ordinaryJob.bits.historyOut
      gd.io.job.bits.output:=ordinaryJob.bits.dst;gd.io.job.bits.cold:=ordinaryJob.bits.cold
      gd.io.job.bits.expectedGeneration:=ordinaryJob.bits.expectedGeneration;gd.io.job.bits.tag:=ordinaryJob.bits.tag
      gd.io.currentGeneration:=Mux(active,gdnCurrent,ordinaryJob.bits.currentGeneration)
      gdnValid:=gd.io.done.valid;gdnDone.tag:=gd.io.done.bits.tag
      val invalidCommit=gd.io.done.bits.status===0.U &&
        (!gd.io.done.bits.historyCommitted || gd.io.done.bits.generation=/=gdnExpected+1.U)
      gdnDone.status:=Mux(invalidCommit,Status.Protocol.U,gd.io.done.bits.status)
      gdnDone.writeBytes:=gd.io.done.bits.writeBytes;gdnDone.cycles:=gd.io.done.bits.cycles
      gd.io.done.ready:=active && mode===3.U && ordinaryDone.ready
      when(gd.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val prepDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val prepValid=WireDefault(false.B)
    prep.foreach{p=>
      p.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===4.U
      p.io.job.bits.tokens:=ordinaryJob.bits.m;p.io.job.bits.heads:=ordinaryJob.bits.n
      p.io.job.bits.queryIn:=ordinaryJob.bits.a;p.io.job.bits.keyIn:=ordinaryJob.bits.a+4096.U;p.io.job.bits.valueIn:=ordinaryJob.bits.a+8192.U
      p.io.job.bits.ab:=ordinaryJob.bits.b;p.io.job.bits.aLog:=ordinaryJob.bits.gdnALog;p.io.job.bits.dtBias:=ordinaryJob.bits.gdnDtBias
      p.io.job.bits.query:=ordinaryJob.bits.dst;p.io.job.bits.key:=ordinaryJob.bits.dst+8192.U;p.io.job.bits.value:=ordinaryJob.bits.dst+16384.U;p.io.job.bits.gates:=ordinaryJob.bits.dst+24576.U
      p.io.job.bits.recurrentMode:=ordinaryJob.bits.gdnRecurrentMode;p.io.job.bits.tag:=ordinaryJob.bits.tag
      prepValid:=p.io.done.valid;prepDone.tag:=p.io.done.bits.tag
      val invalidCommit=p.io.done.bits.status===0.U && !p.io.done.bits.outputCommitted
      prepDone.status:=Mux(invalidCommit,Status.Protocol.U,p.io.done.bits.status)
      prepDone.writeBytes:=p.io.done.bits.writeBytes;prepDone.cycles:=p.io.done.bits.cycles
      p.io.done.ready:=active && mode===4.U && ordinaryDone.ready
      when(p.io.done.fire && invalidCommit){rejected:=true.B}
    }
    runtimeRawPrep.foreach{p=>
      val actualJob=GdnRuntimeRawPrepJobV7.fromOwner(ordinaryJob.bits)
      p.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===4.U
      p.io.job.bits:=actualJob
      io.runtimePrepPrepare.get<>p.io.prepare
      io.runtimePrepDoneFire.get.valid:=p.io.done.fire
      io.runtimePrepDoneFire.get.bits:=p.io.done.bits
      prepValid:=p.io.done.valid;prepDone.tag:=p.io.done.bits.tag
      val invalidCommit=p.io.done.bits.status===Status.Ok.U && !p.io.done.bits.outputCommitted
      prepDone.status:=Mux(invalidCommit,Status.Protocol.U,p.io.done.bits.status)
      prepDone.writeBytes:=p.io.done.bits.writeBytes;prepDone.cycles:=p.io.done.bits.cycles
      p.io.done.ready:=active && mode===4.U && ordinaryDone.ready
      when(p.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val chunkDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val chunkValid=WireDefault(false.B)
    chunk.foreach{c=>
      val port=io.runtimeChunk.get
      c.io.job.valid:=ordinaryJob.valid && ordinaryCanStart && choose===14.U
      when(c.io.job.valid){chunkJobHeld:= !c.io.job.ready}
      assert(!chunkJobHeld || (ordinaryJob.valid && choose===14.U),"held Chunk job must persist")
      c.io.job.bits:=HostRuntimeChunkJobV9.fromOwner(ordinaryJob.bits,port.prepBinding)
      c.io.committed:=port.committed;c.io.prepDone<>port.prepDone
      for(i<-0 until 5){port.memory(i)<>c.io.memory(i)}
      for(i<-0 until 2){port.scalar(i)<>c.io.scalar(i);port.vector(i)<>c.io.vector(i)}
      c.io.fabricFault:=port.fabricFault;c.io.fabricFaultStatus:=Status.Protocol.U
      c.io.fabricDrained:=port.fabricDrained
      port.jobFire:=c.io.job.fire;port.acceptedJob:=c.io.job.bits
      port.doneFire.valid:=c.io.done.fire;port.doneFire.bits:=c.io.done.bits
      port.routeAccepted:=c.io.routeAccepted;port.route:=c.io.route
      port.resetRequired:=c.io.resetRequired || c.io.routeMetadataFault
      val cycles=RegInit(0.U(64.W))
      when(c.io.job.fire){cycles:=0.U}.elsewhen(active && mode===14.U && !c.io.done.valid){cycles:=cycles+1.U}
      chunkValid:=c.io.done.valid;chunkDone.tag:=c.io.done.bits.accepted.context.tag
      val invalidCommit=c.io.done.bits.status===Status.Ok.U && (!c.io.done.bits.stagedComplete || !c.io.done.bits.drained)
      chunkDone.status:=Mux(invalidCommit,Status.Protocol.U,c.io.done.bits.status)
      // Scratch traffic is counted by the leaf receipt, not published as a tensor.
      chunkDone.writeBytes:=c.io.done.bits.outputAckBytes+c.io.done.bits.stateAckBytes
      chunkDone.cycles:=cycles;c.io.done.ready:=active && mode===14.U && ordinaryDone.ready
      when(c.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val recurrentDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val recurrentValid=WireDefault(false.B)
    recurrent.foreach{r=>
      r.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===5.U
      r.io.job.bits.tokens:=ordinaryJob.bits.m;r.io.job.bits.heads:=ordinaryJob.bits.n;r.io.job.bits.keyDim:=ordinaryJob.bits.k;r.io.job.bits.valueDim:=ordinaryJob.bits.k
      r.io.job.bits.query:=ordinaryJob.bits.a;r.io.job.bits.key:=ordinaryJob.bits.a+8192.U;r.io.job.bits.value:=ordinaryJob.bits.a+16384.U;r.io.job.bits.gates:=ordinaryJob.bits.a+24576.U
      r.io.job.bits.stateIn:=ordinaryJob.bits.b;r.io.job.bits.stateOut:=ordinaryJob.bits.gdnStateOut;r.io.job.bits.output:=ordinaryJob.bits.dst
      r.io.job.bits.cold:=ordinaryJob.bits.cold;r.io.job.bits.expectedGeneration:=ordinaryJob.bits.expectedGeneration;r.io.job.bits.tag:=ordinaryJob.bits.tag
      r.io.currentGeneration:=Mux(active,gdnCurrent,ordinaryJob.bits.currentGeneration)
      recurrentValid:=r.io.done.valid;recurrentDone.tag:=r.io.done.bits.tag
      val invalidCommit=r.io.done.bits.status===0.U && (!r.io.done.bits.stateCommitted || r.io.done.bits.generation=/=gdnExpected+1.U)
      recurrentDone.status:=Mux(invalidCommit,Status.Protocol.U,r.io.done.bits.status)
      recurrentDone.writeBytes:=r.io.done.bits.writeBytes;recurrentDone.cycles:=r.io.done.bits.cycles
      r.io.done.ready:=active && mode===5.U && ordinaryDone.ready
      when(r.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val gatedDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gatedValid=WireDefault(false.B)
    gatedNorm.foreach{n=>
      n.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===6.U
      n.io.job.bits.tokens:=ordinaryJob.bits.m;n.io.job.bits.heads:=ordinaryJob.bits.n
      n.io.job.bits.core:=ordinaryJob.bits.a;n.io.job.bits.gate:=ordinaryJob.bits.b;n.io.job.bits.weight:=ordinaryJob.bits.c;n.io.job.bits.output:=ordinaryJob.bits.dst;n.io.job.bits.tag:=ordinaryJob.bits.tag
      gatedValid:=n.io.done.valid;gatedDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===0.U && !n.io.done.bits.outputCommitted
      gatedDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      gatedDone.writeBytes:=n.io.done.bits.writeBytes;gatedDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===6.U && ordinaryDone.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    runtimeGatedNorm.foreach{n=>
      n.io.job.valid:=ordinaryJob.valid && ordinaryCanStart && choose===6.U
      when(n.io.job.valid){gatedJobHeld:= !n.io.job.ready}
      assert(!gatedJobHeld || (ordinaryJob.valid && choose===6.U),"held GatedNorm job must persist")
      n.io.job.bits:=GdnRuntimeGatedNormJobV10.fromOwner(ordinaryJob.bits)
      io.runtimeGatedDoneFire.get.valid:=n.io.done.fire;io.runtimeGatedDoneFire.get.bits:=n.io.done.bits
      gatedValid:=n.io.done.valid;gatedDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===Status.Ok.U && (!n.io.done.bits.outputCommitted ||
        n.io.done.bits.writeBytes=/=((n.io.done.bits.accepted.tokens.pad(64)*n.io.done.bits.accepted.heads.pad(64))<<8)(63,0))
      gatedDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      gatedDone.writeBytes:=n.io.done.bits.writeBytes;gatedDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===6.U && ordinaryDone.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val rmsDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val rmsValid=WireDefault(false.B)
    rmsNorm.foreach{n=>
      n.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===8.U
      n.job.bits.tokens:=ordinaryJob.bits.m;n.job.bits.hiddenWidth:=ordinaryJob.bits.n
      n.job.bits.input:=ordinaryJob.bits.a;n.job.bits.weight:=ordinaryJob.bits.b;n.job.bits.output:=ordinaryJob.bits.dst;n.job.bits.tag:=ordinaryJob.bits.tag
      rmsValid:=n.done.valid;rmsDone.tag:=n.done.bits.tag
      val invalidCommit=n.done.bits.status===0.U && !n.done.bits.outputCommitted
      rmsDone.status:=Mux(invalidCommit,Status.Protocol.U,n.done.bits.status)
      rmsDone.writeBytes:=n.done.bits.writeBytes;rmsDone.cycles:=n.done.bits.cycles
      n.done.ready:=active && mode===8.U && ordinaryDone.ready
      when(n.done.fire && invalidCommit){rejected:=true.B}
    }
    runtimeRms.foreach{n=>
      n.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===8.U
      n.io.job.bits.tokens:=ordinaryJob.bits.m;n.io.job.bits.hiddenWidth:=ordinaryJob.bits.n
      n.io.job.bits.input:=ordinaryJob.bits.a;n.io.job.bits.weight:=ordinaryJob.bits.b
      n.io.job.bits.output:=ordinaryJob.bits.dst;n.io.job.bits.tag:=ordinaryJob.bits.tag
      n.io.job.bits.reductionRecipe:=1.U
      rmsValid:=n.io.done.valid;rmsDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===Status.Ok.U && !n.io.done.bits.outputCommitted
      rmsDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      rmsDone.writeBytes:=n.io.done.bits.writeBytes;rmsDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===8.U && ordinaryDone.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val elementDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val elementValid=WireDefault(false.B)
    elementwise.foreach{e=>
      e.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===9.U
      e.io.job.bits.op:=ordinaryJob.bits.gdnElementwiseOp;e.io.job.bits.tokens:=ordinaryJob.bits.m;e.io.job.bits.rowWidth:=ordinaryJob.bits.n
      e.io.job.bits.a:=ordinaryJob.bits.a;e.io.job.bits.b:=ordinaryJob.bits.b;e.io.job.bits.output:=ordinaryJob.bits.dst;e.io.job.bits.tag:=ordinaryJob.bits.tag
      elementValid:=e.io.done.valid;elementDone.tag:=e.io.done.bits.tag
      val invalidCommit=e.io.done.bits.status===0.U && !e.io.done.bits.outputCommitted
      elementDone.status:=Mux(invalidCommit,Status.Protocol.U,e.io.done.bits.status)
      elementDone.writeBytes:=e.io.done.bits.writeBytes;elementDone.cycles:=e.io.done.bits.cycles
      e.io.done.ready:=active && mode===9.U && ordinaryDone.ready
      when(e.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val qkNormDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val qkNormValid=WireDefault(false.B)
    qkNorm.foreach{n=>
      n.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===10.U
      n.io.job.bits.tokens:=ordinaryJob.bits.m;n.io.job.bits.role:=ordinaryJob.bits.qkRole
      n.io.job.bits.headDim:=ordinaryJob.bits.k;n.io.job.bits.policy:="hc1".U;n.io.job.bits.epsilon:="h358637bd".U
      n.io.job.bits.input:=ordinaryJob.bits.a;n.io.job.bits.weight:=ordinaryJob.bits.b
      n.io.job.bits.output:=ordinaryJob.bits.dst;n.io.job.bits.gateOutput:=ordinaryJob.bits.c;n.io.job.bits.tag:=ordinaryJob.bits.tag
      n.io.scalarFlags:=core.io.scalarPrimitiveFlags.get;n.io.scalarFlagsValid:=core.io.scalarPrimitiveFlagsValid.get
      qkNormValid:=n.io.done.valid;qkNormDone.tag:=n.io.done.bits.tag
      val invalidCommit=n.io.done.bits.status===0.U && !n.io.done.bits.outputCommitted
      qkNormDone.status:=Mux(invalidCommit,Status.Protocol.U,n.io.done.bits.status)
      qkNormDone.writeBytes:=n.io.done.bits.writeBytes;qkNormDone.cycles:=n.io.done.bits.cycles
      n.io.done.ready:=active && mode===10.U && ordinaryDone.ready
      when(n.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val partialRopeDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val partialRopeValid=WireDefault(false.B)
    partialRope.foreach{r=>
      r.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===11.U
      r.io.job.bits.tokens:=ordinaryJob.bits.m;r.io.job.bits.heads:=ordinaryJob.bits.n
      r.io.job.bits.headDim:=ordinaryJob.bits.k;r.io.job.bits.rotaryDim:=64.U;r.io.job.bits.policy:="hb1".U
      r.io.job.bits.input:=ordinaryJob.bits.a;r.io.job.bits.trig:=ordinaryJob.bits.b;r.io.job.bits.output:=ordinaryJob.bits.dst
      r.io.job.bits.positionBase:=ordinaryJob.bits.qkPositionBase;r.io.job.bits.trigTokens:=ordinaryJob.bits.qkTrigTokens;r.io.job.bits.tag:=ordinaryJob.bits.tag
      r.io.scalarFlags:=core.io.scalarPrimitiveFlags.get;r.io.scalarFlagsValid:=core.io.scalarPrimitiveFlagsValid.get
      partialRopeValid:=r.io.done.valid;partialRopeDone.tag:=r.io.done.bits.tag
      val invalidCommit=r.io.done.bits.status===0.U && !r.io.done.bits.outputCommitted
      partialRopeDone.status:=Mux(invalidCommit,Status.Protocol.U,r.io.done.bits.status)
      partialRopeDone.writeBytes:=r.io.done.bits.writeBytes;partialRopeDone.cycles:=r.io.done.bits.cycles
      r.io.done.ready:=active && mode===11.U && ordinaryDone.ready
      when(r.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val kvAppendDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val kvAppendValid=WireDefault(false.B)
    kvAppend.foreach{kv=>
      kv.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===12.U
      kv.io.job.bits.tokens:=ordinaryJob.bits.m;kv.io.job.bits.kvHeads:=2.U;kv.io.job.bits.headDim:=ordinaryJob.bits.k
      kv.io.job.bits.keyInput:=ordinaryJob.bits.a;kv.io.job.bits.valueInput:=ordinaryJob.bits.b;kv.io.job.bits.cacheBase:=ordinaryJob.bits.dst
      kv.io.job.bits.capacityTokens:=ordinaryJob.bits.cacheCapacity;kv.io.job.bits.appendStart:=ordinaryJob.bits.queryStart
      kv.io.job.bits.currentLength:=ordinaryJob.bits.cacheLength;kv.io.job.bits.expectedLength:=ordinaryJob.bits.expectedCacheLength
      kv.io.job.bits.currentGeneration:=ordinaryJob.bits.currentGeneration;kv.io.job.bits.expectedGeneration:=ordinaryJob.bits.expectedGeneration
      kv.io.job.bits.cold:=ordinaryJob.bits.cold;kv.io.job.bits.tag:=ordinaryJob.bits.tag
      kvAppendValid:=kv.io.done.valid;kvAppendDone.tag:=kv.io.done.bits.tag
      val invalidProposal=kv.io.done.bits.status===0.U && (!kv.io.done.bits.proposalValid ||
        kv.io.done.bits.cacheBase=/=kvRoot || kv.io.done.bits.capacityTokens=/=kvCapacity ||
        kv.io.done.bits.proposedLength=/=kvLength || kv.io.done.bits.proposedGeneration=/=gdnExpected+1.U)
      kvAppendDone.status:=Mux(invalidProposal,Status.Protocol.U,kv.io.done.bits.status)
      kvAppendDone.writeBytes:=kv.io.done.bits.writeBytes;kvAppendDone.cycles:=kv.io.done.bits.cycles
      kv.io.done.ready:=active && mode===12.U && ordinaryDone.ready
      when(kv.io.done.fire && invalidProposal){rejected:=true.B}
    }
    val gqaDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));val gqaValid=WireDefault(false.B)
    gqa.foreach{a=>
      a.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===13.U
      a.io.job.bits.tokens:=ordinaryJob.bits.m;a.io.job.bits.queryHeads:=8.U;a.io.job.bits.kvHeads:=2.U;a.io.job.bits.headDim:=ordinaryJob.bits.k
      a.io.job.bits.queryInput:=ordinaryJob.bits.a;a.io.job.bits.cacheBase:=ordinaryJob.bits.b;a.io.job.bits.output:=ordinaryJob.bits.dst
      a.io.job.bits.queryStart:=ordinaryJob.bits.queryStart;a.io.job.bits.cacheLength:=ordinaryJob.bits.cacheLength
      a.io.job.bits.capacityTokens:=ordinaryJob.bits.cacheCapacity;a.io.job.bits.tag:=ordinaryJob.bits.tag
      gqaValid:=a.io.done.valid;gqaDone.tag:=a.io.done.bits.tag
      val invalidCommit=a.io.done.bits.status===0.U && !a.io.done.bits.outputCommitted
      gqaDone.status:=Mux(invalidCommit,Status.Protocol.U,a.io.done.bits.status)
      gqaDone.writeBytes:=a.io.done.bits.writeBytes;gqaDone.cycles:=a.io.done.bits.cycles
      // Completed logical QK/PV products include causal-zero PV terms.
      // Failed jobs do not claim completed useful products.
      gqaDone.usefulMacs:=Mux(gqaDone.status===0.U,gqaLogicalMacs,0.U)
      gqaDone.executedMacs:=(matrix.io.acceptedSteps-gqaPhysicalBase)*512.U
      a.io.done.ready:=active && mode===13.U && ordinaryDone.ready
      when(a.io.done.fire && invalidCommit){rejected:=true.B}
    }
    val legacyScalarDebt=WireDefault(false.B)
    val legacyScalarFault=WireDefault(false.B)
    // The accepted owner retains exclusive scalar ownership until done.
    // All clients use the one existing core ALU/divider/exp service.
    if(bf16Gdn||bf16QkNormRope){
      val clients=gdn.toSeq.map(x=>3->x.io.scalar)++prep.toSeq.map(x=>4->x.io.scalar)++recurrent.toSeq.map(x=>5->x.io.scalar)++gatedNorm.toSeq.map(x=>6->x.io.scalar)++rmsNorm.map(x=>8->x.scalar)++elementwise.toSeq.map(x=>9->x.io.scalar)++qkNorm.toSeq.map(x=>10->x.io.scalar)++partialRope.toSeq.map(x=>11->x.io.scalar)++gqa.toSeq.map(x=>13->x.io.scalar)
      val service=core.io.scalarService.get
      val pending=RegInit(false.B);val responseOwner=Reg(UInt(4.W))
      // Policy0 is assigned at the one core primitive ingress, not inferred
      // from this mode or from a runtime profile. This ABI remains unchanged.
      service.request.valid:=active && !pending && MuxLookup(mode,false.B)(clients.map{case(i,c)=>i.U->c.request.valid})
      service.request.bits:=MuxLookup(mode,0.U.asTypeOf(new ScalarRequest))(clients.map{case(i,c)=>i.U->c.request.bits})
      service.result.ready:=pending && MuxLookup(responseOwner,false.B)(clients.map{case(i,c)=>i.U->c.result.ready})
      when(service.request.fire){pending:=true.B;responseOwner:=mode}
      when(service.result.fire){pending:=false.B}
      legacyScalarDebt:=pending
      legacyScalarFault:=(service.result.valid && !pending) ||
        (pending && (!active || mode=/=responseOwner))
      for((i,c)<-clients){
        c.request.ready:=active && !pending && mode===i.U && service.request.ready
        // A held reply retains its actual accepting client through mode/fault
        // changes. The borrower also sees stray idle data for recovery checks.
        val ownedResponse=pending && responseOwner===i.U
        val strayBorrower=if(enableH2048RmsBorrower && i==8)(!pending && !active)else false.B
        c.result.valid:=(ownedResponse || strayBorrower) && service.result.valid
        c.result.bits:=service.result.bits;c.error:=service.error
      }
    }
    val rejectedDone=WireDefault(0.U.asTypeOf(new QwenOwnerResult));rejectedDone.tag:=tag;rejectedDone.status:=Status.Unsupported.U
    val oldDone=Wire(new QwenOwnerResult)
    oldDone.tag:=tag;oldDone.status:=core.io.result.bits.status;oldDone.cycles:=core.io.result.bits.cycles
    oldDone.writeBytes:=core.io.acknowledgedWriteBytes;oldDone.usefulMacs:=core.io.result.bits.macs;oldDone.executedMacs:=core.io.result.bits.executedMacs
    ordinaryDone.valid:=active && MuxLookup(mode,false.B)(Seq(0.U->core.io.result.valid,1.U->dense.done.valid,2.U->silu.map(_.io.done.valid).getOrElse(false.B),3.U->gdnValid,4.U->prepValid,5.U->recurrentValid,6.U->gatedValid,7.U->true.B,8.U->rmsValid,9.U->elementValid,10.U->qkNormValid,11.U->partialRopeValid,12.U->kvAppendValid,13.U->gqaValid,14.U->chunkValid))
    ordinaryDone.bits:=MuxLookup(mode,rejectedDone)(Seq(0.U->oldDone,1.U->dense.done.bits,2.U->silu.map(_.io.done.bits).getOrElse(rejectedDone),3.U->gdnDone,4.U->prepDone,5.U->recurrentDone,6.U->gatedDone,8.U->rmsDone,9.U->elementDone,10.U->qkNormDone,11.U->partialRopeDone,12.U->kvAppendDone,13.U->gqaDone,14.U->chunkDone))
    core.io.result.ready:=active&&mode===0.U&&ordinaryDone.ready
    dense.done.ready:=active&&mode===1.U&&ordinaryDone.ready;silu.foreach{a=>a.io.done.ready:=active&&mode===2.U&&ordinaryDone.ready}
    when(ordinaryDone.fire){active:=false.B}
    // Explicit mode keys keep GDN slots stable when legacy Activation is absent.
    val memories=Seq(0->core.io.memory,1->dense.memory)++silu.toSeq.map(x=>2->x.io.memory)++gdn.toSeq.map(x=>3->x.io.memory)++runtimeConv.toSeq.map(x=>3->x.io.memory)++prep.toSeq.map(x=>4->x.io.memory)++runtimeRawPrep.toSeq.map(x=>4->x.io.memory)++recurrent.toSeq.map(x=>5->x.io.memory)++gatedNorm.toSeq.map(x=>6->x.io.memory)++runtimeGatedNorm.toSeq.map(x=>6->x.io.memory)++rmsNorm.map(x=>8->x.memory)++runtimeRms.toSeq.map(x=>8->x.io.memory)++elementwise.toSeq.map(x=>9->x.io.memory)++qkNorm.toSeq.map(x=>10->x.io.memory)++partialRope.toSeq.map(x=>11->x.io.memory)++kvAppend.toSeq.map(x=>12->x.io.memory)++gqa.toSeq.map(x=>13->x.io.memory)
    val responses=Seq(0->core.io.response,1->dense.response)++silu.toSeq.map(x=>2->x.io.response)++gdn.toSeq.map(x=>3->x.io.response)++runtimeConv.toSeq.map(x=>3->x.io.response)++prep.toSeq.map(x=>4->x.io.response)++runtimeRawPrep.toSeq.map(x=>4->x.io.response)++recurrent.toSeq.map(x=>5->x.io.response)++gatedNorm.toSeq.map(x=>6->x.io.response)++runtimeGatedNorm.toSeq.map(x=>6->x.io.response)++rmsNorm.map(x=>8->x.response)++runtimeRms.toSeq.map(x=>8->x.io.response)++elementwise.toSeq.map(x=>9->x.io.response)++qkNorm.toSeq.map(x=>10->x.io.response)++partialRope.toSeq.map(x=>11->x.io.response)++kvAppend.toSeq.map(x=>12->x.io.response)++gqa.toSeq.map(x=>13->x.io.response)
    io.memory.valid:=active&&MuxLookup(mode,false.B)(memories.map{case(i,p)=>i.U->p.valid})
    io.memory.bits:=MuxLookup(mode,0.U.asTypeOf(new MemoryRequest))(memories.map{case(i,p)=>i.U->p.bits})
    io.response.ready:=active&&MuxLookup(mode,false.B)(responses.map{case(i,p)=>i.U->p.ready})
    for((i,p)<-memories){p.ready:=active&&mode===i.U&&io.memory.ready}
    for((i,p)<-responses){
      val selected=if(enableH2048RmsBorrower && i==8)(!active || mode===8.U)else(active && mode===i.U)
      p.valid:=selected&&io.response.valid;p.bits:=io.response.bits
    }
    if(enableFfnDrain){
      // Nonburst drain has no normal kernel active/mode token.
      when(dense.drain.get.busy){
        io.memory.valid:=dense.memory.valid;io.memory.bits:=dense.memory.bits;dense.memory.ready:=io.memory.ready
        io.response.ready:=dense.response.ready;dense.response.valid:=io.response.valid
      }
    }
    if(burstWrites){io.writeRequest.get<>dense.writeRequest.get;io.writeData.get<>dense.writeData.get;dense.writeResponse.get<>io.writeResponse.get}
    io.burst.get<>dense.burst;dense.burstResponse<>io.burstResponse.get
    if(bf16AttentionCore){
      // Exactly one retained service owns all eight physical slices. The
      // selected owner retains the service through terminal result and done.
      val clients=Seq(0->legacy.io.port,1->dense.matrix)++gqa.toSeq.map(x=>13->x.io.matrix)
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
    val reductionOwns=qkvRouter.map(_.io.reductionOwns).getOrElse(false.B)
    val useDense=if(enablePublic21QkvReduction)reductionOwns || (active&&mode===1.U) || dense.window.get.busy || dense.drain.get.busy else if(enableFfnDrain)(active&&mode===1.U) || dense.window.map(_.busy).getOrElse(false.B) || dense.drain.get.busy else if(enableFfnWindow)(active&&mode===1.U) || dense.window.get.busy else active&&mode===1.U
    for((client,index)<-Seq(legacy.io.port,dense.matrix).zipWithIndex){
      val selected=if(index==1)useDense else !useDense
      client.group.ready:=selected&&matrix.io.port.group.ready
      client.step.ready:=selected&&matrix.io.port.step.ready
      client.result.valid:=selected&&matrix.io.port.result.valid;client.result.bits:=matrix.io.port.result.bits
      client.done.valid:=selected&&matrix.io.port.done.valid;client.done.bits:=matrix.io.port.done.bits
    }
    matrix.io.port.group.valid:=Mux(useDense,dense.matrix.group.valid,legacy.io.port.group.valid)
    matrix.io.port.group.bits.opcode:=Mux(useDense,dense.matrix.group.bits.opcode,legacy.io.port.group.bits.opcode)
    matrix.io.port.group.bits.sliceMask:=Mux(useDense,dense.matrix.group.bits.sliceMask,legacy.io.port.group.bits.sliceMask)
    matrix.io.port.group.bits.tag:=Mux(useDense,dense.matrix.group.bits.tag,legacy.io.port.group.bits.tag)
    matrix.io.port.group.bits.transposedDense.foreach(_:=useDense)
    if(enableTransposedSeed){
      matrix.io.port.group.bits.groupSequence.get:=Mux(useDense,dense.matrix.group.bits.groupSequence.get,0.U)
      matrix.io.port.seed.get.begin.valid:=useDense && dense.matrix.seed.get.begin.valid
      matrix.io.port.seed.get.begin.bits:=dense.matrix.seed.get.begin.bits
      dense.matrix.seed.get.begin.ready:=useDense && matrix.io.port.seed.get.begin.ready
      matrix.io.port.seed.get.beat.valid:=useDense && dense.matrix.seed.get.beat.valid
      matrix.io.port.seed.get.beat.bits:=dense.matrix.seed.get.beat.bits
      dense.matrix.seed.get.beat.ready:=useDense && matrix.io.port.seed.get.beat.ready
      dense.matrix.seed.get.ack.valid:=useDense && matrix.io.port.seed.get.ack.valid
      dense.matrix.seed.get.ack.bits:=matrix.io.port.seed.get.ack.bits
      matrix.io.port.seed.get.ack.ready:=useDense && dense.matrix.seed.get.ack.ready
    }
    matrix.io.port.step.valid:=Mux(useDense,dense.matrix.step.valid,legacy.io.port.step.valid)
    matrix.io.port.step.bits:=Mux(useDense,dense.matrix.step.bits,legacy.io.port.step.bits)
    matrix.io.port.result.ready:=Mux(useDense,dense.matrix.result.ready,legacy.io.port.result.ready)
    matrix.io.port.done.ready:=Mux(useDense,dense.matrix.done.ready,legacy.io.port.done.ready)
    matrix.io.port.abort:=Mux(useDense,dense.matrix.abort,legacy.io.port.abort)
    if(enableProductionPackedQk16){
      val p=core.io.packedQk.get;val select=core.io.packedQkActive.get
      core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get
      p.group.ready:=select && matrix.io.port.group.ready;p.step.ready:=select && matrix.io.port.step.ready
      p.result.valid:=select && matrix.io.port.result.valid;p.result.bits:=matrix.io.port.result.bits
      p.done.valid:=select && matrix.io.port.done.valid;p.done.bits:=matrix.io.port.done.bits
      when(select){
        assert(active && mode===0.U && !useDense,"packed QK lease belongs only to the original core")
        legacy.io.port.group.ready:=false.B;legacy.io.port.step.ready:=false.B
        legacy.io.port.result.valid:=false.B;legacy.io.port.done.valid:=false.B
        dense.matrix.group.ready:=false.B;dense.matrix.step.ready:=false.B
        dense.matrix.result.valid:=false.B;dense.matrix.done.valid:=false.B
        matrix.io.port.group.valid:=p.group.valid
        matrix.io.port.group.bits.opcode:=p.group.bits.opcode
        matrix.io.port.group.bits.sliceMask:=p.group.bits.sliceMask
        matrix.io.port.group.bits.tag:=p.group.bits.tag
        matrix.io.port.group.bits.transposedDense.foreach(_:=false.B)
        matrix.io.port.group.bits.groupSequence.foreach(_:=0.U)
        matrix.io.port.step.valid:=p.step.valid;matrix.io.port.step.bits:=p.step.bits
        matrix.io.port.result.ready:=p.result.ready;matrix.io.port.done.ready:=p.done.ready
        matrix.io.port.abort:=p.abort
        if(enableTransposedSeed){
          matrix.io.port.seed.get.begin.valid:=false.B;matrix.io.port.seed.get.beat.valid:=false.B
          matrix.io.port.seed.get.ack.ready:=false.B
          dense.matrix.seed.get.begin.ready:=false.B;dense.matrix.seed.get.beat.ready:=false.B
          dense.matrix.seed.get.ack.valid:=false.B
        }
      }
    }
    }
    if(enablePublic21QkvReduction){
      val r=qkvRouter.get
      // Physical retirement, never reset/abort shortcuts. The Matrix service
      // accepts one group until its terminal result queue and Done retire.
      val matrixDebt=RegInit(false.B);val readDebt=RegInit(false.B)
      val writeDebt=RegInit(false.B);val memoryDebt=RegInit(false.B)
      val seedDebt=RegInit(false.B)
      when(matrix.io.port.group.fire){assert(!matrixDebt);matrixDebt:=true.B}
      when(matrix.io.port.done.fire){assert(matrixDebt);matrixDebt:=false.B}
      when(dense.burst.fire){assert(!readDebt && dense.burst.bits.beats===1.U);readDebt:=true.B}
      when(dense.burstResponse.fire){assert(readDebt);readDebt:=false.B}
      when(io.memory.fire){assert(!memoryDebt);memoryDebt:=true.B}
      when(io.response.fire){assert(memoryDebt);memoryDebt:=false.B}
      if(burstWrites){
        when(dense.writeRequest.get.fire){assert(!writeDebt);writeDebt:=true.B}
        when(dense.writeResponse.get.fire){assert(writeDebt);writeDebt:=false.B}
      }
      when(matrix.io.port.seed.get.begin.fire){assert(!seedDebt);seedDebt:=true.B}
      when(matrix.io.port.seed.get.ack.fire){assert(seedDebt);seedDebt:=false.B}
      r.io.matrixDrained:= !matrixDebt && !seedDebt && !matrix.io.port.result.valid && !matrix.io.port.done.valid
      r.io.dmaDrained:= !readDebt && !writeDebt && !memoryDebt
      // Break reflected owner.abort -> resetRequired feedback with a register.
      r.io.backendReset:=io.public21BackendReset.get || RegNext(sharedPoison || gdnPoison,false.B)
      when(r.io.reductionOwns){
        if(enableProductionPackedQk16){assert(!core.io.packedQkActive.get,"QKV reduction and packed QK cannot share the Matrix lease")}
        matrix.io.port.abort:=dense.matrix.abort || r.io.backendAbort
      }
    }
    val noAuxOwner= !tileBusy && !windowBusy && !drainBusy &&
      !resident.map(_.io.group.busy).getOrElse(false.B) &&
      !residentInput.map(_.request.valid).getOrElse(false.B) &&
      !qkvRouter.map(_.io.reductionOwns).getOrElse(false.B) &&
      !ffnTiles.map(_.leased).getOrElse(false.B)
    val rawReturn=io.response.valid || io.burstResponse.get.valid ||
      io.writeResponse.map(_.valid).getOrElse(false.B) ||
      core.io.scalarService.map(_.result.valid).getOrElse(false.B)
    // This affects only admission-ready, never forwarded valid or held offers.
    // Lending is serialized against every actual ordinary/auxiliary owner;
    // new requests cannot create a second use of the core's private Scalar.
    // The only active-owner exceptions are the exact runtime RMS/Conv borrowers.
    // Its Top-validated ordinary lease still gates every shared request; all
    // other owners/auxiliary paths retain the original mutual exclusion.
    sharedScalarAvailable:= (!active || ((enableRuntimeRmsNorm.B && mode===8.U) || (enableRuntimeConv.B && mode===3.U) || (enableRuntimeRawPrep.B && mode===4.U) || (enableRuntimeChunk.B && mode===14.U) || (enableRuntimeGatedNorm.B && mode===6.U))) && noAuxOwner && !transportQuarantine &&
      !rejected && !gdnPoison && !sharedPoison && !legacyScalarDebt && !rawReturn
    transportFault:=( !active && noAuxOwner && rawReturn) || legacyScalarFault
    val anyTerminal=core.io.result.valid || dense.done.valid || silu.map(_.io.done.valid).getOrElse(false.B) ||
      gdnValid || prepValid || chunkValid || recurrentValid || gatedValid || rmsValid || elementValid ||
      qkNormValid || partialRopeValid || kvAppendValid || gqaValid
    io.resourcesDrained:= !active && noAuxOwner && !sharedScalarExclusive && !legacyScalarDebt && !io.resetRequired &&
      core.io.resourcesDrained && matrix.io.resourcesDrained &&
      runtimeRms.map(_.io.resourcesDrained).getOrElse(true.B) && runtimeConv.map(_.io.resourcesDrained).getOrElse(true.B) && runtimeRawPrep.map(_.io.resourcesDrained).getOrElse(true.B) && runtimeGatedNorm.map(_.io.resourcesDrained).getOrElse(true.B) && !anyTerminal &&
      !memories.map(_._2.valid).reduce(_||_) && !io.memory.valid && !rawReturn &&
      !io.burst.get.valid && !io.writeRequest.map(_.valid).getOrElse(false.B) &&
      !io.writeData.map(_.valid).getOrElse(false.B) && !io.job.valid && !io.done.valid
    io.pipelineIssues:=matrix.io.wideSteps;io.pipelineStalls:=matrix.io.stallCycles
    io.resetRequired:=transportQuarantine||transportFault||rejected||gdnPoison||chunk.map(_.io.routeMetadataFault).getOrElse(false.B)||core.io.resetRequired||dense.resetRequired||silu.map(_.io.resetRequired).getOrElse(false.B)||matrix.io.resetRequired||legacy.io.resetRequired
    if(enableResidentFfn){when(resident.get.io.group.resetRequired){io.resetRequired:=true.B}}
    if(enablePublic21QkvReduction){when(qkvRouter.get.io.resetRequired){io.resetRequired:=true.B}}
  }
}
