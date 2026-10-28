// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Existing Command128 -> typed tensor/policy records -> actual owner job.
  * No fixed phase counter authorizes work. Operands/outputs are decoded DDR
  * addresses. Only this request's acknowledged outputs or readonly inputs may
  * be read. SSA destinations cannot overwrite a live producer. Unsupported
  * policy/stride/dtype/aliasing is rejected before issuing an owner job.
  *
  * QK/SOFTMAX/PV form a checked three-command streaming fusion. All three are
  * fetched and validated BEFORE arithmetic starts. Their score/probability
  * tensors are internal-only logical values, never DDR materializations.
  * Their completion events are conservatively delayed until PV writeback.
  */
class HostBlockCommandsV4(s:QwenBlockShape,eventSlots:Int=256,maxCommands:Int=64,bf16Weights:Boolean=false,bf16V:Boolean=false,bf16Qkv:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false,bf16AttentionBlock:Boolean=false,enableTransposedDown:Boolean=false,enableResidentFfn:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableRuntimeQkNorm:Boolean=false,enableRuntimeRope:Boolean=false,enableRuntimeKvAppend:Boolean=false,enableRuntimeGqa:Boolean=false,enableRuntimeOutput:Boolean=false) extends Module {
  Qwen2NumericPolicy.checkShape(numericPolicy,s)
  private val officialBf16=Qwen2NumericPolicy.official(numericPolicy)
  require(!enableRuntimeRope || enableRuntimeQkNorm,"runtime RoPE follows the same actual QKNorm producers")
  require(!enableRuntimeKvAppend || enableRuntimeRope,"runtime KV append follows actual K RoPE and V Dense acknowledgements")
  require(!enableRuntimeGqa || enableRuntimeKvAppend,"runtime GQA follows actual Q RoPE and complete staged KV acknowledgements")
  require(!enableRuntimeOutput || enableRuntimeGqa,"runtime output follows actual GatedNorm or Qgate/GQA acknowledgements")
  require(!officialBf16 || (enableResidentFfn && !bf16V && !bf16Qkv && !bf16Gdn && !bf16QkNormRope && !bf16AttentionCore),
    "official BF16 policy requires validated public21 resident dispatch")
  require(!enableResidentFfn || (enableTransposedDown && bf16Weights && !bf16V && !bf16Qkv && !bf16Gdn && !bf16QkNormRope && s.hidden==1536 && s.ffn==8960),
    "resident FFN is an explicit legacy Qwen2 BF16-weight profile")
  require(!bf16AttentionBlock || (bf16AttentionCore && bf16QkNormRope && bf16Qkv),"BF16 Attention block requires the explicit Attention core/QKV/QK profile")
  require(!bf16AttentionBlock || maxCommands>=22,"Attention block requires 22 public commands")
  require(!bf16AttentionCore || (bf16QkNormRope && bf16Qkv),"BF16 Attention core requires actual QKV and QK Norm/RoPE producers")
  require(!bf16QkNormRope || bf16Qkv,"QK Norm/RoPE requires the explicit QKV profile")
  require(!bf16V || s.qwen35VOnly, "native V requires the explicit Qwen3.5 V-only profile")
  require(!bf16Qkv || s.qwen35QkvOnly, "native QKV requires the explicit Qwen3.5 QKV-only profile")
  require(!bf16GdnBlock || bf16GdnCore, "native full GDN block requires bf16GdnCore")
  require(!bf16GdnCore || bf16Gdn, "native GDN core requires bf16Gdn")
  require(!bf16Gdn || s.qwen35GdnOnly, "native GDN requires the explicit Qwen3.5 GDN-only profile")
  require(Seq(bf16V,bf16Qkv,bf16Gdn).count(identity)<=1, "native V-only, QKV and GDN features are distinct")
  require(eventSlots>=4 && isPow2(eventSlots) && maxCommands>=21 && maxCommands<=255)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunchV4));val result=Decoupled(new HostCommandResult)
    // Uniform844-bit candidate. Legacy833 type/source remain frozen separately.
    val resident=if(enableResidentFfn)Some(Flipped(new FfnResidentPort))else None
    val prefixWorkspace=if(enableTransposedDown)Some(Output(new TransposedPrefixWorkspace(2560)))else None
    val completion=Decoupled(UInt(56.W))
    val runtimeChunkCommitted=Output(new GdnChunkCommittedState) // read-only actual root, not host supplied
    val runtimeAuthority=Output(new HostRuntimeAuthoritySnapshotV4) // private parent only, not Host ABI
    // Private registered physical proof from the one original Guard/Prefix.
    // This is not a Host-supplied receipt and never gates job.valid or ready.
    val runtimePostnormReceipt=Input(Valid(new HostRuntimePostnormStagedReceiptV16))
    // Same original Guard/Prefix physical receipt, not a Host supplied grant.
    val runtimeFfnReceipt=Input(Valid(new HostRuntimeFfnStagedReceiptV17))
    // Private original-parent drain observation, never a Host supplied grant.
    val runtimeFinalDrained=Input(Bool())
    val parserLocalFault=Output(Bool()) // private real local/sticky faults; excludes current reflected moePhaseFault
    // PRIVATE original-parent handoff. No Host completion/grant input exists.
    val moePhase=Decoupled(new HostMoePhaseProposalV5)
    val moePhaseResult=Flipped(Decoupled(new HostMoePhaseRetirementV5))
    val moePhaseFailure=Flipped(Decoupled(new HostMoePhaseFailureV5)) // actual allocator rejection
    val moePhaseFault=Input(Bool()) // independent parent/resource fault, not reflected resetRequired
    val moeRegionConflict=Output(Bool()) // private live objects from this actual accepted cfg
    val metadataDrained=Output(Bool()) // actual sole readers/scanner and their held interfaces
    val moeSharedGateImage=Output(Valid(new HostMoeSharedGateImageV5)) // read-only actual clean metadata pulse
    val job=Decoupled(new QwenOwnerJob);val done=Flipped(Decoupled(new QwenOwnerResult))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool());val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W))
    val usefulMacs=Output(UInt(64.W));val executedMacs=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
  })
  val states=Enum(if(enableResidentFfn)20 else 16)
  val idle::fetch::get::decode::tensorIssue::tensorGet::policyIssue::policyGet::validate::issue::waitDone::complete::finish::locked::Nil=states.take(14)
  val scanFetch=if(enableResidentFfn)states(14)else idle;val scanGet=if(enableResidentFfn)states(15)else idle
  val scanTensorIssue=if(enableResidentFfn)states(16)else idle;val scanTensorGet=if(enableResidentFfn)states(17)else idle
  val moeScan=if(enableResidentFfn)states(18)else states(14)
  val moeWait=if(enableResidentFfn)states(19)else states(15)
  // A phase completion must NEVER execute the old bound.kind producer cases.
  val boundMoePhase=RegInit(false.B)
  val boundRuntimeFence=RegInit(false.B)
  val runtimeFenceHost=Reg(new HostCommandLaunchV4);val runtimeFenceTransaction=Reg(UInt(64.W))
  val runtimeFinalTensor=Reg(new DecodedTensor)
  val runtimeStateTensor=Reg(new DecodedTensor)
  // Cold-only checkpoint publication. Carried parameter binding is not yet
  // complete for runtime MoE; no partial legacy parameter table authenticates it.
  val runtimeCheckpointCommitted=RegInit(false.B)
  val runtimeResultQualified=RegInit(false.B);val runtimeResultStatus=Reg(UInt(8.W))
  val boundRuntimePrefix=RegInit(false.B) // exact runtime norm/Dense prefix, not a Host grant
  val moePhasePoison=RegInit(false.B)
  val moePhaseUnknown=Wire(Bool())

  // Only metadata is added. The original q/k/score/probability registers hold
  // A/Wgate/Gate/Up while this checked group owns the parser.
  class ResidentHostState {
    val inGroup=RegInit(false.B);val pending=RegInit(false.B)
    val gateJob=Reg(new QwenOwnerJob);val upJob=Reg(new QwenOwnerJob);val upWeight=Reg(new DecodedTensor)
    val scanPc=Reg(UInt(16.W));val scanCmd=Reg(UInt(128.W));val scanSlot=Reg(UInt(2.W))
  }
  val resident=if(enableResidentFfn)Some(new ResidentHostState)else None
  // Match the explicit software public21 hardening before any Attention issue.
  // Reuse the FFN typed-root scanner and its existing metadata ports/state.
  val scanAttention=if(enableResidentFfn && officialBf16)Some(RegInit(false.B))else None
  val attentionScan=scanAttention.getOrElse(false.B)
  val state=RegInit(idle);val cfg=Reg(new HostCommandLaunchV4);val cmd=RegInit(0.U(128.W))
  // The old resident path cannot cancel/mutate a held MoE completion. Its
  // real live reset sideband still vetoes phase acceptance/publication.
  val phaseResidentFault=if(enableResidentFfn)
    (state===moeScan || boundMoePhase || boundRuntimePrefix || boundRuntimeFence ||
      (state===finish && cfg.profileId>=1.U && cfg.profileId<=4.U)) && io.resident.get.resetRequired else false.B
  val moePhaseLiveFault=io.moePhaseFault || moePhasePoison || moePhaseUnknown || phaseResidentFault
  when(io.moePhaseFault || moePhaseUnknown || phaseResidentFault){moePhasePoison:=true.B}
  val runtimeAccepted=RegInit(false.B)
  val runtimeTransaction=Reg(UInt(64.W));val runtimeNextTransaction=RegInit(0.U(64.W))
  val runtimeIdentityExhausted=RegInit(false.B)
  val (runtimeProfile,runtimeProfileKnown)=UnifiedRuntimeProfile.decode(cfg.profileId)
  // One hardware definition. Only geometry/policy interpretation is runtime.
  val runtimeNormProfile=runtimeProfileKnown && cfg.profileId>=1.U && cfg.profileId<=4.U
  val runtimeNormHidden=Mux(cfg.profileId===1.U || cfg.profileId===2.U,1024.U(16.W),2048.U(16.W))
  val runtimeGdnProfile=cfg.profileId===1.U || cfg.profileId===3.U
  val runtimeAttentionProfile=enableRuntimeQkNorm.B && runtimeProfileKnown && (cfg.profileId===2.U || cfg.profileId===4.U)
  // The original common constructor admits runtime profiles through the same
  // typed-record parser and real owners. Admission is not numerical acceptance.
  // Legacy partial constructors remain unsupported: all installed runtime tail
  // services and the fixed production Dense path must be present together.
  private val commonRuntimeInstalled=officialBf16 && s.retainedMatrix && s.matrixColumns==256 &&
    enableResidentFfn && enableTransposedDown &&
    enableRuntimeQkNorm && enableRuntimeRope && enableRuntimeKvAppend && enableRuntimeGqa && enableRuntimeOutput

  val pc=RegInit(0.U(16.W));val completed=RegInit(0.U(16.W));val status=RegInit(0.U(8.W));val poison=RegInit(false.B)
  val events=RegInit(VecInit(Seq.fill(eventSlots)(false.B)))
  val tensorSlots=5 // fixed common maximum; runtime profile never changes capacity
  val tensors=Reg(Vec(tensorSlots,new DecodedTensor));val slot=RegInit(0.U(log2Ceil(tensorSlots).W))
  val policy=Reg(Vec(12,UInt(128.W)));val policySlot=RegInit(0.U(4.W));val policyIndex=Reg(UInt(24.W))
  val policyIndices=Reg(Vec(12,UInt(24.W)));val extendedProjection=RegInit(false.B)
  val bound=Reg(new QwenOwnerJob)
  // Captured ONLY in the existing descriptor/policy/producer validated branch.
  // Both inputNorm and postNorm use kind GdnRmsNorm: kind alone cannot prove
  // postnorm provenance. This metadata holds with the original bound job.
  val boundPostnorm=RegInit(false.B)
  val boundInputTensor=Reg(new DecodedTensor)
  val postnormCommitValid=RegInit(false.B)
  // Runtime postNorm does not publish a FFN input at raw done: it must also
  // cross the original held completion event with its exact accepted lifetime.
  // These are metadata snapshots only; no additional tensor or compute bank.
  val postnormDonePending=RegInit(false.B)
  val boundPostnormHost=Reg(new HostCommandLaunchV4);val boundPostnormTransaction=Reg(UInt(64.W))
  val boundPostnormGamma=Reg(new DecodedTensor);val boundPostnormOutput=Reg(new DecodedTensor)
  val postnormHost=Reg(new HostCommandLaunchV4);val postnormTransaction=Reg(UInt(64.W))
  val postnormPhysicalReceipt=Reg(new HostRuntimePostnormStagedReceiptV16)
  val postnormJob=Reg(new QwenOwnerJob);val postnormResult=Reg(new QwenOwnerResult)
  val postnormResidual=Reg(new DecodedTensor);val postnormOutputTensor=Reg(new DecodedTensor)
  // Ordinary Dense0.8 continuation snapshots. These are metadata, not a second
  // FFN dispatcher, numerical bank, or a replacement for the physical receipt.
  val ffnDonePending=RegInit(false.B)
  val boundFfnHost=Reg(new HostCommandLaunchV4);val boundFfnTransaction=Reg(UInt(64.W))
  val boundFfnA=Reg(new DecodedTensor);val boundFfnB=Reg(new DecodedTensor);val boundFfnD=Reg(new DecodedTensor)
  val ffnPhysicalReceipt=Reg(new HostRuntimeFfnStagedReceiptV17)
  val runtimeFfnTensors=Reg(Vec(5,new DecodedTensor)) // gate/up/silu/down/residual2
  // Address provenance from typed public21 records, captured only in validated
  // branches. These metadata registers are never tensor payload or authority.
  val officialOutputs=if(officialBf16)Some(Reg(Vec(21,UInt(64.W))))else None
  val officialHidden=if(officialBf16)Some(Reg(UInt(64.W)))else None
  val officialRows=if(officialBf16)Some(Reg(UInt(16.W)))else None
  def rememberOfficial():Unit=if(officialBf16){
    when(cfg.profileId===0.U){
      officialOutputs.get(pc):=tensors(2).address
      when(pc===0.U){officialHidden.get:=tensors(0).address;officialRows.get:=tensors(0).dims(0)}
    }
  }
  val officialMaterializeDense=officialBf16.B && (pc===13.U || pc===16.U || pc===17.U || pc===19.U)
  // The owner acknowledges both writes, but D and history are separate spans.
  val mainPublishBytes=Reg(UInt(64.W));val boundGdn=RegInit(false.B)
  // One explicit layer-0 / stream-0 context. Host launches never reset it.
  val stateValid=RegInit(false.B);val currentGeneration=RegInit(0.U(32.W))
  val currentHistoryAddress=RegInit(0.U(64.W));val currentHistoryEnd=RegInit(0.U(64.W))
  // Core v2 stages write fresh allocations. Only the terminal fence commits
  // the history and recurrent roots together; Host launches retain both roots.
  val currentStateAddress=RegInit(0.U(64.W));val currentStateEnd=RegInit(0.U(64.W))
  io.runtimeChunkCommitted.valid:=stateValid;io.runtimeChunkCommitted.generation:=currentGeneration
  io.runtimeChunkCommitted.state:=currentStateAddress
  val txInputValid=RegInit(false.B);val txInputAddress=Reg(UInt(64.W));val txInputEnd=Reg(UInt(64.W))
  val txQkvValid=RegInit(false.B);val txZValid=RegInit(false.B);val txAbValid=RegInit(false.B)
  val txQkv=Reg(UInt(64.W));val txZ=Reg(UInt(64.W));val txAb=Reg(UInt(64.W))
  val txConvValid=RegInit(false.B);val txPrepValid=RegInit(false.B);val txRecurrentValid=RegInit(false.B);val txNormValid=RegInit(false.B)
  val txConv=Reg(UInt(64.W));val txPrep=Reg(UInt(64.W));val txRecurrent=Reg(UInt(64.W));val txNorm=Reg(UInt(64.W))
  // Full v3 block values are published only after their exact owner ACK.
  val txInputNormValid=RegInit(false.B);val txInputNorm=Reg(UInt(64.W))
  val runtimeInputNormTensor=Reg(new DecodedTensor)
  val runtimeProjectionTensors=Reg(Vec(3,new DecodedTensor)) // actual QKV/Z/AB completions
  val runtimePrepTensor=Reg(new DecodedTensor) // actual RawPrep complete ACK, no recurrent state commit
  val runtimeChunkTensor=Reg(new DecodedTensor) // exact completed Chunk BF16 staging allocation
  val runtimeGatedNormTensor=Reg(new DecodedTensor) // exact completed GatedNorm staging, not final roots
  val runtimeConvTensor=Reg(new DecodedTensor);val runtimeHistoryTensor=Reg(new DecodedTensor) // actual output/history ACKs, not persistent state commit
  val txOValid=RegInit(false.B);val txO=Reg(UInt(64.W))
  val runtimeOTensor=Reg(new DecodedTensor) // exact DenseO ACK, shared across all hetero profiles
  val txResidual1Valid=RegInit(false.B);val txResidual1=Reg(UInt(64.W))
  val txResidual1Tensor=Reg(new DecodedTensor) // actual residual completion only
  val txPostNormValid=RegInit(false.B);val txPostNorm=Reg(UInt(64.W))
  val txGateValid=RegInit(false.B);val txGate=Reg(UInt(64.W))
  val txUpValid=RegInit(false.B);val txUp=Reg(UInt(64.W))
  val txSiluValid=RegInit(false.B);val txSilu=Reg(UInt(64.W))
  val txDownValid=RegInit(false.B);val txDown=Reg(UInt(64.W))
  val txResidual2Valid=RegInit(false.B);val txResidual2=Reg(UInt(64.W))
  val pendingHistoryAddress=Reg(UInt(64.W));val pendingHistoryEnd=Reg(UInt(64.W))
  val pendingStateAddress=Reg(UInt(64.W));val pendingStateEnd=Reg(UInt(64.W))
  val txGeneration=Reg(UInt(32.W));val txCold=Reg(Bool());val boundFence=RegInit(false.B)
  // Fixed semantic sources: hidden, Wqkv, Wz, Wab, Wconv, A_log, dt_bias,
  // norm weight, old history, old recurrent state. Distinct roles never alias.
  val sourceCount=16 // fixed maximum semantic metadata capacity for all runtime profiles
  val parameterRoles=if(bf16GdnBlock)(1 to 7)++(10 to 15) else (1 to 7)
  val sourceValid=RegInit(VecInit(Seq.fill(sourceCount)(false.B)))
  val sourceStarts=Reg(Vec(sourceCount,UInt(64.W)));val sourceEnds=Reg(Vec(sourceCount,UInt(64.W)))
  val sourceTensor=Reg(Vec(sourceCount,new DecodedTensor))
  // The seven core (thirteen full-block) bindings belong to the committed checkpoint.
  // Hidden changes with each token; carried state cannot change its weights.
  val committedParameterStarts=Reg(Vec(parameterRoles.size,UInt(64.W)));val committedParameterEnds=Reg(Vec(parameterRoles.size,UInt(64.W)))
  // Actual projection/normalization producers for this Host launch. Readonly
  // preloaded lookalikes cannot satisfy these semantic dependencies.
  val qkProjectedValid=RegInit(VecInit(Seq.fill(3)(false.B)))
  val qkProjected=Reg(Vec(3,UInt(64.W)));val qkRows=Reg(Vec(3,UInt(16.W)))
  val qkWindowBase=Reg(Vec(3,UInt(32.W)));val qkWindowCount=Reg(Vec(3,UInt(8.W)))
  val qkNormalizedValid=RegInit(VecInit(Seq.fill(2)(false.B)))
  val qkNormalized=Reg(Vec(2,UInt(64.W)))
  // Typed allocation snapshots bind completed roles, never readonly lookalikes.
  // Decoder canonicalization already fixes contiguous strides and legal spans.
  val qkProjectedTensor=Reg(Vec(3,new DecodedTensor))
  val qkNormalizedTensor=Reg(Vec(2,new DecodedTensor))
  val qkRotatedValid=RegInit(VecInit(Seq.fill(2)(false.B)))
  val qkRotatedTensor=Reg(Vec(2,new DecodedTensor));val qkAbsolutePosition=Reg(Vec(2,UInt(32.W)))
  // One checkpoint survives normal Host launches; reset has no restore API.
  // Core v2 commits context. Block v3 commits only the final residual output.
  val attentionCacheValid=RegInit(false.B)
  val attentionCache=Reg(new DecodedTensor);val attentionContext=Reg(new DecodedTensor)
  // Wq/Wk/Wv, gammaQ/gammaK and trig belong to the cache checkpoint.
  // Hidden (source role 0) is deliberately not persistent.
  val attentionParameterCount=if(bf16AttentionBlock)12 else 6
  val attentionParameters=Reg(Vec(attentionParameterCount,new DecodedTensor))
  // Block roles: raw hidden=0, legacy Wq/Wk/Wv/Qgamma/Kgamma/trig=1..6,
  // input gamma=7, Wo=8, post gamma=9, Wgate/Wup/Wdown=10..12.
  // Actual ACK snapshots: inputNorm, Qgate, sigmoidMul, O, residual1,
  // postNorm, FFNgate, FFNup, siluMul, down, finalResidual.
  val attentionBlockValues=Reg(Vec(11,new DecodedTensor))
  val attentionBlockValid=RegInit(VecInit(Seq.fill(11)(false.B)))
  val attentionBlockContext=Reg(UInt(72.W))
  val attentionBlockMatrix=RegInit(false.B)
  val runtimeAttentionOutputPolicy=RegInit(false.B) // original ATTENTION_POLICY v3, selected by typed record
  val attentionLength=RegInit(0.U(32.W));val attentionGeneration=RegInit(0.U(32.W))
  val pendingAttentionValid=RegInit(false.B);val pendingGqaValid=RegInit(false.B)
  val pendingAttentionCache=Reg(new DecodedTensor);val pendingAttentionContext=Reg(new DecodedTensor)
  val pendingAttentionLength=Reg(UInt(32.W));val pendingAttentionOldLength=Reg(UInt(32.W))
  val pendingAttentionGeneration=Reg(UInt(32.W));val pendingAttentionCold=Reg(Bool())
  val pendingAttentionBase=Reg(UInt(32.W));val pendingAttentionCount=Reg(UInt(8.W))
  val boundAttentionAppend=RegInit(false.B);val boundAttentionGqa=RegInit(false.B);val boundAttentionFence=RegInit(false.B)
  val previousSignal=RegInit(0.U(16.W))
  def clearTransaction():Unit={
    txInputValid:=false.B;txQkvValid:=false.B;txZValid:=false.B;txAbValid:=false.B
    txConvValid:=false.B;txPrepValid:=false.B;txRecurrentValid:=false.B;txNormValid:=false.B
    txInputNormValid:=false.B;txOValid:=false.B;txResidual1Valid:=false.B;txPostNormValid:=false.B
    txGateValid:=false.B;txUpValid:=false.B;txSiluValid:=false.B;txDownValid:=false.B;txResidual2Valid:=false.B
    sourceValid:=VecInit(Seq.fill(sourceCount)(false.B))
    attentionBlockValid:=VecInit(Seq.fill(11)(false.B))
  }
  val group=RegInit(0.U(2.W));val qkCommand=Reg(UInt(128.W));val softCommand=Reg(UInt(128.W))
  val q=Reg(new DecodedTensor);val k=Reg(new DecodedTensor);val score=Reg(new DecodedTensor);val probability=Reg(new DecodedTensor)
  val completingGroup=RegInit(false.B);val completionIndex=RegInit(0.U(2.W))
  val producedCapacity=if(bf16Gdn||bf16QkNormRope)2*maxCommands else maxCommands
  val producedIndexBits=log2Ceil(producedCapacity)
  val producedCount=RegInit(0.U(log2Ceil(producedCapacity+1).W))
  val starts=Reg(Vec(producedCapacity,UInt(64.W)));val ends=Reg(Vec(producedCapacity,UInt(64.W)))
  val allocationStarts=Reg(Vec(producedCapacity,UInt(64.W)));val allocationEnds=Reg(Vec(producedCapacity,UInt(64.W)))
  val producedValid=RegInit(VecInit(Seq.fill(producedCapacity)(false.B)))
  val managedHistory=RegInit(VecInit(Seq.fill(producedCapacity)(false.B)))
  val virtualCount=RegInit(0.U(8.W));val vStarts=Reg(Vec(maxCommands,UInt(64.W)));val vEnds=Reg(Vec(maxCommands,UInt(64.W)))
  val jobs=RegInit(0.U(16.W));val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W));val written=RegInit(0.U(64.W))
  io.pc:=pc;io.issuedJobs:=jobs;io.usefulMacs:=useful;io.executedMacs:=executed;io.writeBytes:=written
  val roots=VecInit(Seq(cmd(79,56),cmd(103,80),cmd(127,104)))
  val opcode=cmd(7,0);val engine=cmd(10,8);val waitEvent=cmd(39,24);val signalEvent=cmd(55,40)
  val isMatrix=opcode===0x20.U||opcode===0x23.U||opcode===0x24.U
  val isMoeManifest=opcode===0x50.U
  val isSoftmax=opcode===0x33.U;val kv=opcode===0x41.U
  val runtimeQkNormCommand=runtimeAttentionProfile && opcode===0x32.U
  val runtimeRopeCommand=enableRuntimeRope.B && runtimeAttentionProfile && opcode===0x34.U
  val runtimeQkCommand=runtimeQkNormCommand || runtimeRopeCommand
  val runtimeKvAppendCommand=enableRuntimeKvAppend.B && runtimeAttentionProfile && kv
  val runtimeGqaCommand=enableRuntimeGqa.B && runtimeAttentionProfile && (opcode===0x23.U || isSoftmax || opcode===0x24.U)
  val qkCommandPolicy=(bf16QkNormRope.B && (opcode===0x32.U||opcode===0x34.U)) || runtimeQkCommand
  val runtimeNormCommand=runtimeNormProfile && opcode===0x30.U
  val runtimeProjectionCommand=runtimeNormProfile && (runtimeGdnProfile || runtimeAttentionProfile) && opcode===0x20.U
  val gdnCommand=bf16Gdn.B && opcode===0x30.U
  val attentionCommandPolicy=(bf16AttentionCore.B && (kv || opcode===0x23.U || opcode===0x24.U || isSoftmax || opcode===0x30.U || (bf16AttentionBlock.B && attentionBlockMatrix && opcode===0x20.U))) || runtimeKvAppendCommand || runtimeGqaCommand || runtimeAttentionOutputPolicy
  val attentionPolicySlot=Mux(kv,0.U,Mux(isMatrix,2.U,1.U))
  val attentionContextSlot=attentionPolicySlot+1.U
  val reader=Module(new Record128Reader);val tensor=Module(new TypedTensorReader)
  // Metadata-only extension borrows these exact two readers. No second reader
  // or memory client is instantiated; public128 existing operations are kept.
  val moeWeightScan=Module(new HostMoeWeightScanV4)
  io.metadataDrained:=reader.io.request.ready && !reader.io.request.valid && !reader.io.result.valid &&
    tensor.io.request.ready && !tensor.io.request.valid && !tensor.io.result.valid &&
    moeWeightScan.io.resourcesDrained && !io.memory.valid && !io.response.valid &&
    !reader.io.resetRequired && !moeWeightScan.io.resetRequired
  io.memory<>reader.io.memory;reader.io.response<>io.response
  val tensorMode=if(enableResidentFfn)state===tensorIssue||state===tensorGet||state===scanTensorIssue||state===scanTensorGet else state===tensorIssue||state===tensorGet
  reader.io.request.valid:=Mux(tensorMode,tensor.io.record.valid,if(enableResidentFfn)state===fetch||state===policyIssue||state===scanFetch else state===fetch||state===policyIssue)
  reader.io.request.bits:=tensor.io.record.bits
  when(!tensorMode){
    reader.io.request.bits.tableBase:=Mux(state===fetch,cfg.commandBase,cfg.descriptorBase)
    reader.io.request.bits.tableLimit:=Mux(state===fetch,cfg.commandLimit,cfg.descriptorLimit)
    reader.io.request.bits.entryCount:=Mux(state===fetch,cfg.commands,cfg.descriptors)
    reader.io.request.bits.index:=Mux(state===fetch,pc,policyIndex)
    reader.io.request.bits.requestTag:=Cat(cfg.epoch,pc,0.U(32.W))
  }
  if(enableResidentFfn){when(state===scanFetch){
    reader.io.request.bits.tableBase:=cfg.commandBase;reader.io.request.bits.tableLimit:=cfg.commandLimit
    reader.io.request.bits.entryCount:=cfg.commands;reader.io.request.bits.index:=resident.get.scanPc
    reader.io.request.bits.requestTag:=Cat(cfg.epoch,resident.get.scanPc,0.U(32.W))
  }}
  tensor.io.record.ready:=reader.io.request.ready&&tensorMode
  tensor.io.recordResult.valid:=reader.io.result.valid&&tensorMode;tensor.io.recordResult.bits:=reader.io.result.bits
  reader.io.result.ready:=Mux(tensorMode,tensor.io.recordResult.ready,if(enableResidentFfn)state===get||state===policyGet||state===scanGet else state===get||state===policyGet)
  tensor.io.request.valid:=(if(enableResidentFfn)state===tensorIssue||state===scanTensorIssue else state===tensorIssue);tensor.io.request.bits.tableBase:=cfg.descriptorBase
  tensor.io.request.bits.tableLimit:=cfg.descriptorLimit;tensor.io.request.bits.entryCount:=cfg.descriptors
  tensor.io.request.bits.root:=roots(slot(1,0))
  if(bf16Gdn){when(slot>=3.U){tensor.io.request.bits.root:=Mux(slot===3.U,policy(2)(79,56),policy(2)(103,80))}}
  if(bf16QkNormRope||enableRuntimeQkNorm){when(qkCommandPolicy && slot===3.U){tensor.io.request.bits.root:=policy(2)(79,56)}}
  when(runtimeNormCommand && runtimeGdnProfile && (policy(1)(71,64)===1.U || policy(1)(71,64)===3.U || policy(1)(71,64)===4.U || policy(1)(71,64)===5.U) && slot>=3.U){
    tensor.io.request.bits.root:=Mux(slot===3.U,policy(2)(79,56),policy(2)(103,80))
  }
  tensor.io.request.bits.regions:=cfg.regions
  if(enableTransposedDown){
    // Slot 3 belongs exclusively to the launch-snapshotted workspace lease.
    // Generic tensor accesses cannot borrow its read or write permission.
    tensor.io.request.bits.regions(3):=0.U.asTypeOf(new Region)
  }
  val gdnOperation=policy(1)(71,64)
  val extraWrite=if(bf16GdnCore) (slot===4.U && gdnOperation===1.U)||(slot===3.U && gdnOperation===4.U) else bf16Gdn.B && slot===4.U
  tensor.io.request.bits.writeAccess:=slot===2.U || extraWrite || (qkCommandPolicy && slot===3.U) ||
    (runtimeNormCommand && runtimeGdnProfile && ((gdnOperation===1.U && slot===4.U) || (gdnOperation===4.U && slot>=3.U)))
  if(enableResidentFfn){when(state===scanTensorIssue || state===scanTensorGet){
    val scan=resident.get
    val scanRoots=VecInit(Seq(scan.scanCmd(79,56),scan.scanCmd(103,80),scan.scanCmd(127,104)))
    tensor.io.request.bits.root:=scanRoots(scan.scanSlot)
    tensor.io.request.bits.writeAccess:=scan.scanSlot===2.U
  }}
  tensor.io.result.ready:=(if(enableResidentFfn)state===tensorGet||state===scanTensorGet else state===tensorGet)
  io.launch.ready:=state===idle && !poison && !moePhaseLiveFault && !runtimeIdentityExhausted
  // Freeze final status before its first offer. A later fault remains on the
  // existing resetRequired sideband; it cannot rewrite a held result payload.
  io.result.valid:=state===finish && (!runtimeNormProfile || runtimeResultQualified)
  io.result.bits.status:=Mux(runtimeNormProfile,runtimeResultStatus,status);io.result.bits.completed:=completed
  when(state===finish && runtimeNormProfile && !runtimeResultQualified){
    runtimeResultStatus:=Mux(status=/=Status.Ok.U,status,
      Mux(io.runtimeAuthority.currentFault || !io.runtimeFinalDrained || !runtimeCheckpointCommitted,Status.Protocol.U,Status.Ok.U))
    when(status===Status.Ok.U && (io.runtimeAuthority.currentFault || !io.runtimeFinalDrained || !runtimeCheckpointCommitted)){
      status:=Status.Protocol.U;poison:=true.B
    }
    runtimeResultQualified:=true.B
  }
  io.result.bits.failedPc:=pc;io.result.bits.epoch:=cfg.epoch
  val completionCommand=Mux(completingGroup,Mux(completionIndex===0.U,qkCommand,Mux(completionIndex===1.U,softCommand,cmd)),cmd)
  val completionPc=Mux(completingGroup,pc-2.U+completionIndex,pc)
  io.completion.valid:=(if(enableResidentFfn)state===complete && (boundMoePhase || boundRuntimePrefix || boundRuntimeFence || status=/=0.U || !io.resident.get.resetRequired)else state===complete)
  io.completion.bits:=Cat(completionCommand(55,40),status,completionCommand(10,8),completionPc.pad(29))
  io.job.valid:=(if(enableResidentFfn)state===issue && !resident.get.pending else state===issue)
  io.job.bits:=bound;io.done.ready:=(if(enableResidentFfn)state===waitDone && !resident.get.pending else state===waitDone)
  if(enableResidentFfn){
    val p=io.resident.get;val r=resident.get
    p.request.valid:=state===issue && r.pending
    p.request.bits.gate:=r.gateJob;p.request.bits.up:=r.upJob;p.request.bits.act:=bound
    p.request.bits.identity:=r.gateJob.tag+1.U
    p.result.ready:=state===waitDone && r.pending
    p.abort:=poison
  }
  io.resetRequired:=poison||reader.io.resetRequired||moeWeightScan.io.resetRequired||moePhaseLiveFault
  // Separate the original local/sticky terms from the CURRENT reflected Top
  // fault. Used only for private fresh-ordinary arithmetic admission; full
  // resetRequired/currentFault still governs final success and global reset.
  io.parserLocalFault:=poison || reader.io.resetRequired || moeWeightScan.io.resetRequired ||
    moePhasePoison || moePhaseUnknown || phaseResidentFault || status=/=Status.Ok.U
  def fail(code:UInt):Unit={status:=code;poison:=true.B;completingGroup:=false.B;state:=complete;if(bf16GdnCore){clearTransaction()};if(bf16AttentionCore||enableRuntimeKvAppend||enableRuntimeGqa){pendingAttentionValid:=false.B;pendingGqaValid:=false.B}}
  def overlap(a:UInt,e:UInt,b:UInt,f:UInt):Bool=a<f && b<e
  def intersectsVirtual(t:DecodedTensor):Bool=(0 until maxCommands).map(i=>i.U<virtualCount && overlap(t.address,t.paddedEnd,vStarts(i),vEnds(i))).reduce(_||_)
  val ordinaryRegions=cfg.regions.take(if(enableTransposedDown)3 else 4)
  def liveSpan(address:UInt,end:UInt):Bool={
    val initial=ordinaryRegions.map(r=>r.read && !r.write && r.base<=address && end<=r.limit).reduce(_||_)
    val published=(0 until producedCapacity).map(i=>producedValid(i) && starts(i)<=address && end<=ends(i)).reduce(_||_)
    val virtual=(0 until maxCommands).map(i=>i.U<virtualCount && overlap(address,end,vStarts(i),vEnds(i))).reduce(_||_)
    (initial||published) && !virtual
  }
  def live(t:DecodedTensor):Bool=liveSpan(t.address,t.paddedEnd)
  def freshSpan(address:UInt,end:UInt):Bool= {
    val published=(0 until producedCapacity).map(i=>producedValid(i) && overlap(address,end,starts(i),ends(i))).reduce(_||_)
    val virtual=(0 until maxCommands).map(i=>i.U<virtualCount && overlap(address,end,vStarts(i),vEnds(i))).reduce(_||_)
    val current=bf16Gdn.B && stateValid && overlap(address,end,currentHistoryAddress,currentHistoryEnd)
    val recurrent=bf16GdnCore.B && stateValid && overlap(address,end,currentStateAddress,currentStateEnd)
    val source=((bf16GdnCore||bf16QkNormRope).B || runtimeNormProfile) && (0 until sourceCount).map(i=>sourceValid(i) && overlap(address,end,sourceStarts(i),sourceEnds(i))).reduce(_||_)
    val parameter=bf16GdnCore.B && stateValid && parameterRoles.indices.map(i=>
      overlap(address,end,committedParameterStarts(i),committedParameterEnds(i))).reduce(_||_)
    val allocation=(bf16QkNormRope.B || runtimeAttentionProfile) && (0 until producedCapacity).map(i=>producedValid(i) && overlap(address,end,allocationStarts(i),allocationEnds(i))).reduce(_||_)
    val attention=(bf16AttentionCore.B || runtimeAttentionProfile) && ((attentionCacheValid &&
      (overlap(address,end,attentionCache.address,attentionCache.paddedEnd) || overlap(address,end,attentionContext.address,attentionContext.paddedEnd))) ||
      (pendingAttentionValid && overlap(address,end,pendingAttentionCache.address,pendingAttentionCache.paddedEnd)))
    val attentionParameter=(bf16AttentionCore.B || runtimeAttentionProfile) && attentionCacheValid && (0 until attentionParameterCount).map(i=>
      overlap(address,end,attentionParameters(i).address,attentionParameters(i).paddedEnd)).reduce(_||_)
    !(published || virtual || current || recurrent || source || parameter || allocation || attention || attentionParameter)
  }
  // Check EVERY real allocation subregion against the original decoder's
  // complete live-object tables. No Host supplied live-span list or grant bit.
  // 80-bit addition cannot wrap a high base into a spuriously fresh low span;
  // allocator separately proves region3 rights, bounds and exact cfg identity.
  io.moeRegionConflict:=HostMoePhaseLayoutV4.Regions.map{case(offset,bytes)=>
    val begin=cfg.regions(3).base.pad(80)+offset.U(80.W)
    val end=begin+bytes.U(80.W)
    !freshSpan(begin,end)
  }.reduce(_||_)
  def fresh(t:DecodedTensor):Bool=freshSpan(t.address,t.paddedEnd)
  def sourceAllowed(t:DecodedTensor,role:UInt):Bool={
    val roles=(0 until sourceCount).map(i=> !sourceValid(i) || Mux(i.U===role,
      t.address===sourceStarts(i) && t.paddedEnd===sourceEnds(i) && (!(bf16AttentionCore.B || runtimeAttentionProfile) || sameAllocation(t,sourceTensor(i))),
      !overlap(t.address,t.paddedEnd,sourceStarts(i),sourceEnds(i)))).reduce(_&&_)
    val published=(0 until producedCapacity).map(i=>producedValid(i) && overlap(t.address,t.paddedEnd,starts(i),ends(i))).reduce(_||_)
    // Old state roots are valid sources only in their dedicated semantic role.
    val oldHistory=stateValid && role=/=8.U && overlap(t.address,t.paddedEnd,currentHistoryAddress,currentHistoryEnd)
    val oldState=stateValid && role=/=9.U && overlap(t.address,t.paddedEnd,currentStateAddress,currentStateEnd)
    val checkpointParameters=parameterRoles.zipWithIndex.map{case(sourceRole,i)=> !stateValid || Mux(role===sourceRole.U,
      t.address===committedParameterStarts(i) && t.paddedEnd===committedParameterEnds(i),
      !overlap(t.address,t.paddedEnd,committedParameterStarts(i),committedParameterEnds(i)))}.reduce(_&&_)
    val allocation=(bf16QkNormRope.B || runtimeAttentionProfile) && (0 until producedCapacity).map(i=>producedValid(i) && overlap(t.address,t.paddedEnd,allocationStarts(i),allocationEnds(i))).reduce(_||_)
    val attention=(bf16AttentionCore.B || runtimeAttentionProfile) && attentionCacheValid &&
      (overlap(t.address,t.paddedEnd,attentionCache.address,attentionCache.paddedEnd) || overlap(t.address,t.paddedEnd,attentionContext.address,attentionContext.paddedEnd))
    val attentionParametersOK= !(bf16AttentionCore.B || runtimeAttentionProfile) || !attentionCacheValid || (0 until attentionParameterCount).map(i=>Mux(role===(i+1).U,
      sameAllocation(t,attentionParameters(i)), !overlap(t.address,t.paddedEnd,attentionParameters(i).address,attentionParameters(i).paddedEnd))).reduce(_&&_)
    roles && !published && !allocation && !oldHistory && !oldState && checkpointParameters && !attention && attentionParametersOK
  }
  def rememberSource(t:DecodedTensor,role:UInt):Unit={
    sourceValid(role.pad(4)):=true.B;sourceStarts(role.pad(4)):=t.address;sourceEnds(role.pad(4)):=t.paddedEnd;sourceTensor(role.pad(4)):=t
  }
  def readonly(t:DecodedTensor):Bool=ordinaryRegions.map(r=>r.read && !r.write && r.base<=t.address && t.paddedEnd<=r.limit).reduce(_||_)
  def readwrite(t:DecodedTensor):Bool=ordinaryRegions.map(r=>r.read && r.write && r.base<=t.address && t.paddedEnd<=r.limit).reduce(_||_)
  def same(a:DecodedTensor,b:DecodedTensor):Bool=a.address===b.address && a.rank===b.rank && a.dtype===b.dtype && a.dims.asUInt===b.dims.asUInt
  def sameAllocation(a:DecodedTensor,b:DecodedTensor):Bool=same(a,b) && a.elementCount===b.elementCount &&
    a.payloadBytes===b.payloadBytes && a.paddedEnd===b.paddedEnd
  // The only lifecycle alias exception: exact previously committed cache.
  // Sources, producer FULL allocations, virtual values and the old context
  // stay protected even when the append tail reuses that cache allocation.
  def reusableAttentionCache(t:DecodedTensor):Bool={
    val producers=(0 until producedCapacity).map(i=>producedValid(i) && overlap(t.address,t.paddedEnd,allocationStarts(i),allocationEnds(i))).reduce(_||_)
    val sources=(0 until sourceCount).map(i=>sourceValid(i) && overlap(t.address,t.paddedEnd,sourceStarts(i),sourceEnds(i))).reduce(_||_)
    attentionCacheValid && sameAllocation(t,attentionCache) && !producers && !sources && !intersectsVirtual(t) &&
      !overlap(t.address,t.paddedEnd,attentionContext.address,attentionContext.paddedEnd)
  }
  def shape2(t:DecodedTensor,m:UInt,n:UInt):Bool=t.rank===2.U && t.dims(0)===m && t.dims(1)===n && t.dims(2)===1.U && t.dims(3)===1.U
  def shape3(t:DecodedTensor,m:UInt,n:UInt,k:UInt):Bool=t.rank===3.U && t.dims(0)===m && t.dims(1)===n && t.dims(2)===k && t.dims(3)===1.U
  def finishRecord(w:UInt,kind:UInt):Bool=w(7,0)===kind && w(31,8)===0.U && w(55,32)===0xffffff.U
  def matrixPolicy(m:UInt,n:UInt,k:UInt,transposeB:Bool):Bool={
    val p=policy(0);val a=policy(1)
    // Original MATRIX_OP + MATRIX_AUX fields, BF16-input / FP32-output recipe.
    p(7,0)===0x10.U && p(31,8)===0.U && p(55,32)=/=0xffffff.U &&
    p(71,56)===m && p(87,72)===n && p(111,88)===k &&
    p(114,112)===0.U && p(115)===transposeB && p(127,116)===0.U &&
    finishRecord(a,0x12.U) && a(127,56)==="h4000040024ffffff".U(72.W)
  }
  def sfuPolicy(inputs:Int):Bool={val p=policy(0)
    finishRecord(p,0x20.U) && p(71,56)===opcode && p(79,72)===inputs.U && p(87,80)===1.U &&
    p(91,88)===7.U && p(95,92)===7.U && p(103,96)===16.U && p(127,104)===0.U
  }
  def nextCommand():Unit={when(pc+1.U>=cfg.commands){fail(Status.Malformed.U)}.otherwise{pc:=pc+1.U;state:=fetch}}
  when(io.launch.fire){
    val l=io.launch.bits
    def roTable(b:UInt,e:UInt):Bool=l.regions.take(if(enableTransposedDown)3 else 4).map(r=>r.read && !r.write && r.base<=b && e<=r.limit).reduce(_||_)
    val validRegions=l.regions.map(r=>(r.base===r.limit && !r.read && !r.write)||
      (r.base<r.limit && r.base(5,0)===0.U && r.limit(5,0)===0.U && r.limit<=(BigInt(1)<<56).U)).reduce(_&&_)
    val collisions=(for(i<-0 until 4;j<-i+1 until 4)yield l.regions(i).base<l.regions(i).limit && l.regions(j).base<l.regions(j).limit && overlap(l.regions(i).base,l.regions(i).limit,l.regions(j).base,l.regions(j).limit)).reduce(_||_)
    val cmdEnd=l.commandBase.pad(80)+(((l.commands.pad(80)*16.U+63.U)>>6)<<6)
    val descEnd=l.descriptorBase.pad(80)+(((l.descriptors.pad(80)*16.U+63.U)>>6)<<6)
    val ok=(!officialBf16.B || l.profileId=/=0.U || l.commands===21.U) && (!bf16AttentionCore.B || l.commands===(if(bf16AttentionBlock)22 else 12).U) && (!bf16GdnBlock.B || l.commands===17.U) && l.commands>0.U && l.commands<=maxCommands.U && l.descriptors>0.U && l.descriptors<=0xffffff.U &&
      Seq(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit).map(_(5,0)===0.U).reduce(_&&_) &&
      l.commandBase<l.commandLimit && l.descriptorBase<l.descriptorLimit && cmdEnd<=l.commandLimit && descEnd<=l.descriptorLimit &&
      !overlap(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit) && validRegions && !collisions &&
      roTable(l.commandBase,l.commandLimit) && roTable(l.descriptorBase,l.descriptorLimit)
    if(enableResidentFfn){resident.get.inGroup:=false.B;resident.get.pending:=false.B}
    val headerOK=HostCommandLaunchV4.known(l)
    val lease=l.regions(3)
    val workspaceOK=(!enableTransposedDown.B) || (lease.read && lease.write && lease.base<lease.limit &&
      lease.base(5,0)===0.U && lease.limit(5,0)===0.U && lease.limit<=(BigInt(1)<<56).U &&
      lease.limit-lease.base>=64.U && !overlap(lease.base,lease.limit,l.commandBase,l.commandLimit) &&
      !overlap(lease.base,lease.limit,l.descriptorBase,l.descriptorLimit))
    val envelopeAccepted=ok && headerOK && workspaceOK
    runtimeAccepted:=envelopeAccepted
    postnormCommitValid:=false.B;postnormDonePending:=false.B;boundPostnorm:=false.B;ffnDonePending:=false.B
    boundMoePhase:=false.B;boundRuntimePrefix:=false.B
    when(envelopeAccepted){
      runtimeTransaction:=runtimeNextTransaction
      when(runtimeNextTransaction===((BigInt(1)<<64)-1).U){runtimeIdentityExhausted:=true.B}
      .otherwise{runtimeNextTransaction:=runtimeNextTransaction+1.U}
    }

    cfg:=l;pc:=0.U;completed:=0.U;status:=0.U;cmd:=0.U;producedCount:=0.U;virtualCount:=0.U;group:=0.U;completingGroup:=false.B
    jobs:=0.U;useful:=0.U;executed:=0.U;written:=0.U;boundFence:=false.B;previousSignal:=0.U
    boundRuntimeFence:=false.B;runtimeResultQualified:=false.B
    clearTransaction() // metadata-only reset for every newly accepted launch; persistent roots untouched
    if(bf16QkNormRope||enableRuntimeQkNorm){qkProjectedValid:=VecInit(Seq.fill(3)(false.B));qkNormalizedValid:=VecInit(Seq.fill(2)(false.B));qkRotatedValid:=VecInit(Seq.fill(2)(false.B))}
    if(bf16AttentionCore||enableRuntimeKvAppend||enableRuntimeGqa){pendingAttentionValid:=false.B;pendingGqaValid:=false.B;boundAttentionAppend:=false.B;boundAttentionGqa:=false.B;boundAttentionFence:=false.B}
    producedValid:=VecInit(Seq.fill(producedCapacity)(false.B));managedHistory:=VecInit(Seq.fill(producedCapacity)(false.B));boundGdn:=false.B
    events:=VecInit(Seq.fill(eventSlots)(false.B));events(0):=true.B
    when(!ok){status:=Status.Bounds.U;state:=finish}.otherwise{state:=fetch}
    if(enableTransposedDown){
      val lease=l.regions(3)
      val workspaceOK=lease.read && lease.write && lease.base<lease.limit &&
        lease.base(5,0)===0.U && lease.limit(5,0)===0.U &&
        lease.limit<=(BigInt(1)<<56).U && lease.limit-lease.base>=64.U &&
        !overlap(lease.base,lease.limit,l.commandBase,l.commandLimit) &&
        !overlap(lease.base,lease.limit,l.descriptorBase,l.descriptorLimit)
      // validRegions and collisions above still check all four public regions.
      when(!workspaceOK){status:=Status.Bounds.U;state:=finish}
    }
    when(!headerOK){runtimeAccepted:=false.B;status:=Status.Unsupported.U;state:=finish}
    .elsewhen(envelopeAccepted && l.profileId=/=0.U && runtimeCheckpointCommitted){
      status:=Status.Unsupported.U;state:=finish
    }
    .elsewhen(envelopeAccepted && !((l.profileId===0.U && officialBf16.B) ||
      (commonRuntimeInstalled.B && l.profileId>=1.U && l.profileId<=4.U))){
      status:=Status.Unsupported.U;state:=finish
    }
  }
  when(state===fetch && reader.io.request.fire){state:=get}
  when(state===get && reader.io.result.fire){
    cmd:=reader.io.result.bits.data
    when(reader.io.result.bits.status=/=0.U){fail(reader.io.result.bits.status)}
    .elsewhen(reader.io.result.bits.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))){fail(Status.Protocol.U)}
    .otherwise{state:=decode}
  }
  when(state===decode){
    val legacySupported=if(s.qwen35GdnOnly) opcode===0x30.U||opcode===0x20.U else if(s.qwen35QkvOnly) opcode===0x20.U||(bf16QkNormRope.B&&(opcode===0x32.U||opcode===0x34.U))||attentionCommandPolicy else
      isMatrix||opcode===0x30.U||opcode===0x32.U||isSoftmax||opcode===0x34.U||opcode===0x35.U||kv
    val supported=legacySupported || (isMoeManifest && (cfg.profileId===3.U || cfg.profileId===4.U))
    val correctEngine=engine===Mux(isMatrix,2.U,Mux(kv,4.U,3.U))
    val rootsOK=roots(0)=/=0xffffff.U&&roots(2)=/=0xffffff.U&&roots(0)<cfg.descriptors&&roots(2)<cfg.descriptors&&
      Mux(isSoftmax,roots(1)===0xffffff.U,roots(1)=/=0xffffff.U&&roots(1)<cfg.descriptors)
    val expectedWait=Mux(group===1.U,qkCommand(55,40),softCommand(55,40))
    val dependency=Mux(group===0.U,events(waitEvent(log2Ceil(eventSlots)-1,0)),waitEvent===expectedWait) &&
      (!((bf16GdnCore||bf16QkNormRope).B || runtimeNormProfile) || ((bf16AttentionCore.B || runtimeGqaCommand) && group=/=0.U) || waitEvent===previousSignal)
    val groupOrder=if(enableResidentFfn)Mux(resident.get.inGroup,
      Mux(group===1.U,opcode===0x20.U,group===2.U && opcode===0x35.U),
      Mux(group===1.U,isSoftmax,Mux(group===2.U,opcode===0x24.U,!isSoftmax && opcode=/=0x24.U)))
    else Mux(group===1.U,isSoftmax,Mux(group===2.U,opcode===0x24.U,!isSoftmax && opcode=/=0x24.U))
    when(!supported|| !correctEngine){fail(Status.Unsupported.U)}
    .elsewhen(cmd(23,11)=/=0.U|| !rootsOK|| !groupOrder){fail(Status.Malformed.U)}
    .elsewhen(waitEvent>=eventSlots.U||signalEvent===0.U||signalEvent>=eventSlots.U|| !dependency||
      events(signalEvent(log2Ceil(eventSlots)-1,0))||signalEvent===waitEvent||
      (group=/=0.U && signalEvent===qkCommand(55,40))){fail(Status.Dependency.U)}
    .otherwise{slot:=0.U;policy:=VecInit(Seq.fill(12)(0.U(128.W)));extendedProjection:=false.B;attentionBlockMatrix:=false.B;runtimeAttentionOutputPolicy:=false.B;state:=tensorIssue}
  }
  when(state===tensorIssue&&tensor.io.request.fire){state:=tensorGet}
  when(state===tensorGet&&tensor.io.result.fire){
    when(tensor.io.result.bits.status=/=0.U){fail(tensor.io.result.bits.status)}
    .otherwise{tensors(slot):=tensor.io.result.bits.tensor
      when(slot===2.U){
        policyIndex:=tensors(0).tail;policySlot:=0.U
        state:=Mux(isMoeManifest,moeScan,Mux(kv && !attentionCommandPolicy,validate,policyIssue))
      }.elsewhen(runtimeNormCommand && runtimeGdnProfile &&
        (((gdnOperation===1.U || gdnOperation===3.U || gdnOperation===4.U) && slot===4.U) ||
          (gdnOperation===5.U && slot===3.U))){state:=validate}
      .elsewhen(qkCommandPolicy && slot===3.U){state:=validate}.elsewhen(bf16Gdn.B && (slot===4.U || (bf16GdnCore.B && slot===3.U && (gdnOperation===4.U || gdnOperation===5.U)))){state:=validate}.otherwise{
        when(slot===0.U&&(isSoftmax||isMoeManifest)){tensors(1):=0.U.asTypeOf(new DecodedTensor);slot:=2.U}.otherwise{slot:=slot+1.U}
        state:=tensorIssue
      }
    }
  }
  // Original parser remains the exclusive owner of the shared readers. The
  // scanner consumes only result handshakes caused by its own fired requests.
  val moeScanOwned=RegInit(false.B)
  val scannerAuthority=Wire(new HostRuntimeAuthoritySnapshotV4)
  scannerAuthority:=io.runtimeAuthority
  // Do NOT feed this scanner's own combinational resetRequired back through
  // authority.currentFault: only independent original-parser faults enter.
  scannerAuthority.currentFault:=poison || reader.io.resetRequired || status=/=Status.Ok.U
  moeWeightScan.io.authority:=scannerAuthority
  moeWeightScan.io.currentFault:=poison || reader.io.resetRequired
  moeWeightScan.io.begin.valid:=state===moeScan && !moeScanOwned && !poison
  moeWeightScan.io.begin.bits.root:=roots(1);moeWeightScan.io.begin.bits.pc:=pc
  when(moeWeightScan.io.begin.fire){moeScanOwned:=true.B}
  moeWeightScan.io.record.ready:=false.B
  moeWeightScan.io.recordResult.valid:=false.B;moeWeightScan.io.recordResult.bits:=reader.io.result.bits
  moeWeightScan.io.tensor.ready:=false.B
  moeWeightScan.io.tensorResult.valid:=false.B;moeWeightScan.io.tensorResult.bits:=tensor.io.result.bits
  // Graph fields are stable while this parser owns the scanner report. The
  // structural predicate is deliberately independent of a late fault: after
  // valid was offered its payload and valid remain until the actual handshake.
  val postnormCurrent=runtimeAccepted && runtimeTransaction===postnormTransaction &&
    cfg.asUInt===postnormHost.asUInt
  val moeGraphFields=postnormCurrent && postnormCommitValid && producedCount<producedCapacity.U &&
    pc+1.U<cfg.commands && !txResidual2Valid &&
    tensors(0).asUInt===postnormOutputTensor.asUInt && live(tensors(0)) &&
    tensors(2).dtype===5.U && tensors(2).rank===2.U &&
    tensors(2).dims(0)===postnormJob.m && tensors(2).dims(1)===2048.U &&
    tensors(2).payloadBytes===postnormJob.writeBytes && readwrite(tensors(2)) && fresh(tensors(2))
  val moeResultIdentity=moeWeightScan.io.done.bits.transactionId===runtimeTransaction &&
    moeWeightScan.io.done.bits.root===roots(1) && moeWeightScan.io.done.bits.pc===pc
  val moeReport=state===moeScan && moeScanOwned && moeWeightScan.io.done.valid
  val moeCandidate=moeReport && moeWeightScan.io.done.bits.status===Status.Ok.U &&
    moeGraphFields && moeResultIdentity && moeWeightScan.io.done.bits.hasPaddedSharedGate
  val phaseOffer=HeldDecoupledOffer(moeCandidate,io.moePhase.ready,io.runtimeAuthority.currentFault)
  val (phaseContext,_)=HostMoePhaseContextV4.fromActualMetadata(io.runtimeAuthority)
  io.moePhase.valid:=phaseOffer.valid
  io.moePhase.bits.context:=phaseContext
  io.moePhase.bits.postnormJob:=postnormJob;io.moePhase.bits.postnormResult:=postnormResult
  io.moePhase.bits.weights:=moeWeightScan.io.done.bits.weights
  // A new bad/faulted report can be rejected. An existing held proposal cannot
  // be consumed as an unrelated error and cannot disappear on a late fault.
  val rejectMoeReport=moeReport && !phaseOffer.valid && !phaseOffer.held &&
    (!moeCandidate || io.runtimeAuthority.currentFault)
  moeWeightScan.io.done.ready:=(phaseOffer.valid && io.moePhase.ready) || rejectMoeReport
  io.runtimeAuthority.moeWeightsAccepted:=moeWeightScan.io.done.fire && io.moePhase.fire &&
    moeWeightScan.io.done.bits.status===Status.Ok.U && moeGraphFields &&
    moeResultIdentity && !io.runtimeAuthority.currentFault
  io.runtimeAuthority.moeWeights:=moeWeightScan.io.done.bits.weights
  io.runtimeAuthority.moeOutput:=tensors(2)
  io.moeSharedGateImage.valid:=io.runtimeAuthority.moeWeightsAccepted && moeWeightScan.io.done.bits.hasPaddedSharedGate
  io.moeSharedGateImage.bits.logicalWeight:=moeWeightScan.io.done.bits.weights(HostMoeWeightRoleV4.SharedGateLogit)
  io.moeSharedGateImage.bits.physicalWeight:=moeWeightScan.io.done.bits.paddedSharedGate
  io.moeSharedGateImage.bits.layoutId:=HostMoeSharedGatePlanV5.LayoutId.U
  when(moeWeightScan.io.done.fire){
    moeScanOwned:=false.B
    when(io.moePhase.fire){
      // Even a late-faulted held offer has a real transport obligation. Wait
      // for its actual parent terminal; never pretend it was cancelled.
      boundMoePhase:=true.B;state:=moeWait
    }.otherwise{
      fail(Mux(moeWeightScan.io.done.bits.status=/=Status.Ok.U,moeWeightScan.io.done.bits.status,
        Mux(io.runtimeAuthority.currentFault,Status.Protocol.U,
          Mux(!moeWeightScan.io.done.bits.hasPaddedSharedGate,Status.Unsupported.U,Status.Dependency.U))))
    }
  }
  val phaseReturnIdentity=io.moePhaseResult.bits.context.asUInt===phaseContext.asUInt
  val phaseFailureIdentity=io.moePhaseFailure.bits.transactionId===runtimeTransaction
  moePhaseUnknown:=(io.moePhaseResult.valid && (state=/=moeWait || !phaseReturnIdentity)) ||
    (io.moePhaseFailure.valid && (state=/=moeWait || !phaseFailureIdentity)) ||
    (io.moePhaseResult.valid && io.moePhaseFailure.valid)
  // Wrong identity never retires the legitimate wait. The sole parent creates
  // this terminal only AFTER actual final merge/writeACK and BOTH allocator /
  // Guard releases, or as an explicit failed phase. A routed result is not it.
  io.moePhaseResult.ready:=state===moeWait && phaseReturnIdentity && !io.moePhaseFailure.valid
  io.moePhaseFailure.ready:=state===moeWait && phaseFailureIdentity && !io.moePhaseResult.valid
  when(io.moePhaseFailure.fire){
    fail(Mux(io.moePhaseFailure.bits.status===Status.Ok.U,Status.Protocol.U,io.moePhaseFailure.bits.status))
  }
  when(io.moePhaseResult.fire){
    val r=io.moePhaseResult.bits
    val fullWrite=r.outputAddress===phaseContext.output.address &&
      r.acknowledgedWriteBytes===phaseContext.output.payloadBytes
    when(r.status=/=Status.Ok.U){fail(r.status)}
    .elsewhen(!r.resourcesRetired || !fullWrite || io.runtimeAuthority.currentFault){fail(Status.Protocol.U)}
    .otherwise{
      useful:=useful+r.usefulMacs;executed:=executed+r.executedMacs
      written:=written+r.acknowledgedWriteBytes
      completingGroup:=false.B;completionIndex:=0.U;state:=complete
    }
  }
  when(state===moeScan){
    tensor.io.request.valid:=moeWeightScan.io.tensor.valid
    tensor.io.request.bits:=moeWeightScan.io.tensor.bits
    moeWeightScan.io.tensor.ready:=tensor.io.request.ready
    moeWeightScan.io.tensorResult.valid:=tensor.io.result.valid
    tensor.io.result.ready:=moeWeightScan.io.tensorResult.ready
    // tensor.record and direct manifest requests are mutually exclusive by
    // the scanner states; never arbitrate based on untrusted response payload.
    val typed=moeWeightScan.io.tensorPath
    reader.io.request.valid:=Mux(typed,tensor.io.record.valid,moeWeightScan.io.record.valid)
    reader.io.request.bits:=Mux(typed,tensor.io.record.bits,moeWeightScan.io.record.bits)
    tensor.io.record.ready:=typed && reader.io.request.ready
    moeWeightScan.io.record.ready:= !typed && reader.io.request.ready
    tensor.io.recordResult.valid:=typed && reader.io.result.valid
    moeWeightScan.io.recordResult.valid:= !typed && reader.io.result.valid
    reader.io.result.ready:=Mux(typed,tensor.io.recordResult.ready,moeWeightScan.io.recordResult.ready)
  }
  when(state===policyIssue&&reader.io.request.fire){state:=policyGet}
  when(state===policyGet&&reader.io.result.fire){
    val r=reader.io.result.bits;policy(policySlot):=r.data;policyIndices(policySlot):=policyIndex
    val next=r.data(55,32)
    val prefixRevisit=(for(t<-0 until 3;i<-0 until 3)yield
      (t.U=/=1.U || !isSoftmax) && tensors(t).prefixIndices(i)===policyIndex).reduce(_||_)
    val policyRevisit=(0 until 12).map(i=>i.U<policySlot && policyIndices(i)===policyIndex).reduce(_||_)
    when(r.status=/=0.U){fail(r.status)}
    .elsewhen(r.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))){fail(Status.Protocol.U)}
    .elsewhen(r.data(31,8)=/=0.U || prefixRevisit || policyRevisit){fail(Status.Malformed.U)}
    .elsewhen(attentionCommandPolicy || (enableRuntimeOutput.B && runtimeAttentionProfile &&
      runtimeNormCommand && policySlot===1.U && r.data(7,0)===0x24.U)){
      // An ordinary runtime RMS PROGRAM may instead point to the ORIGINAL
      // Attention v3 elementwise policy/context. Its public typed kind, never
      // PC or a Host grant, selects this existing decoder branch.
      when(enableRuntimeOutput.B && runtimeAttentionProfile && runtimeNormCommand &&
        policySlot===1.U && r.data(7,0)===0x24.U){runtimeAttentionOutputPolicy:=true.B}
      val expectedKind=Mux(policySlot===attentionContextSlot,0x26.U,Mux(policySlot===attentionPolicySlot,0x24.U,
        Mux(isMatrix,Mux(policySlot===0.U,0x10.U,0x12.U),0x20.U)))
      when(policySlot>attentionContextSlot || r.data(7,0)=/=expectedKind ||
        (policySlot===attentionContextSlot)=/=(next===0xffffff.U)){fail(Status.Malformed.U)}
      .elsewhen(policySlot===attentionContextSlot){state:=validate}
      .otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
    }
    .elsewhen(qkCommandPolicy){
      val expectedKind=Mux(policySlot===0.U,0x20.U,Mux(policySlot===1.U,0x24.U,0x25.U))
      when(policySlot>2.U || r.data(7,0)=/=expectedKind || (policySlot===2.U)=/=(next===0xffffff.U)){fail(Status.Malformed.U)}
      .elsewhen(policySlot===2.U){
        val gate=r.data(79,56);val hasGate=opcode===0x32.U && policy(1)(65,64)===0.U
        when(Mux(hasGate,gate===0xffffff.U||gate>=cfg.descriptors,gate=/=0xffffff.U)){fail(Status.Malformed.U)}
        .elsewhen(hasGate){slot:=3.U;state:=tensorIssue}.otherwise{state:=validate}
      }.otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
    }
    .elsewhen(runtimeProjectionCommand){
      val kind=Mux(policySlot===0.U,0x10.U,Mux(policySlot===1.U,0x12.U,0x21.U))
      when(policySlot>2.U || r.data(7,0)=/=kind || (policySlot===2.U)=/=(next===0xffffff.U)){
        fail(Status.Malformed.U)
      }.elsewhen(policySlot===2.U){state:=validate}
      .otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
    }
    .elsewhen(runtimeNormCommand){
      // Same original reader; bounded PROGRAM->POLICY->at most two extra typed roots.
      // op1 uses HISTORY0x22; op3/4/5 use INPUTS0x23. GatedNorm op5 has
      // exactly one FP32 gamma root; its unused second root MUST be sentinel.
      val kind=Mux(policySlot===0.U,0x20.U,Mux(policySlot===1.U,0x21.U,Mux(gdnOperation===1.U,0x22.U,0x23.U)))
      val normTerminal=policySlot===1.U && (r.data(71,64)===8.U ||
        (enableRuntimeOutput.B && runtimeGdnProfile && r.data(71,64)===6.U) ||
        (enableRuntimeOutput.B && r.data(71,64)===9.U &&
          (runtimeGdnProfile || (cfg.profileId===2.U && r.data(84,82)>=1.U && r.data(84,82)<=2.U))))
      val extraPolicy=policySlot===1.U && runtimeGdnProfile && (r.data(71,64)===1.U || r.data(71,64)===3.U || r.data(71,64)===4.U || r.data(71,64)===5.U)
      when(policySlot>2.U || r.data(7,0)=/=kind ||
        (policySlot===1.U && !(normTerminal || extraPolicy)) ||
        (normTerminal || policySlot===2.U)=/=(next===0xffffff.U) ||
        (policySlot===2.U && (!runtimeGdnProfile || !(gdnOperation===1.U || gdnOperation===3.U || gdnOperation===4.U || gdnOperation===5.U)))){fail(Status.Malformed.U)}
      .elsewhen(normTerminal){state:=validate}
      .elsewhen(policySlot===2.U){
        val hin=r.data(79,56);val hout=r.data(103,80)
        val oneExtra=gdnOperation===5.U
        when(hin===0xffffff.U || hin>=cfg.descriptors ||
          Mux(oneExtra,hout=/=0xffffff.U,hout===0xffffff.U || hout>=cfg.descriptors)){fail(Status.Malformed.U)}
          .otherwise{slot:=3.U;state:=tensorIssue}
      }.otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
    }
    .elsewhen(gdnCommand){
      if(bf16GdnCore){
        val terminalPolicy=policySlot===1.U && r.data(63,56)===(if(bf16GdnBlock)3 else 2).U &&
          (r.data(71,64)===6.U || (bf16GdnBlock.B && (r.data(71,64)===8.U || r.data(71,64)===9.U)))
        val expectedKind=Mux(policySlot===0.U,0x20.U,Mux(policySlot===1.U,0x21.U,Mux(gdnOperation===1.U,0x22.U,0x23.U)))
        when(policySlot>2.U || r.data(7,0)=/=expectedKind || (policySlot===2.U || terminalPolicy)=/=(next===0xffffff.U)){fail(Status.Malformed.U)}
        .elsewhen(terminalPolicy){state:=validate}
        .elsewhen(policySlot===2.U){
          val x=r.data(79,56);val y=r.data(103,80)
          val two=gdnOperation===1.U || gdnOperation===3.U
          when(x===0xffffff.U || x>=cfg.descriptors || Mux(two,y===0xffffff.U || y>=cfg.descriptors,y=/=0xffffff.U)){fail(Status.Malformed.U)}
          .otherwise{slot:=3.U;state:=tensorIssue}
        }.otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
      }else{
      val expectedKind=Mux(policySlot===0.U,0x20.U,Mux(policySlot===1.U,0x21.U,0x22.U))
      when(policySlot>2.U || r.data(7,0)=/=expectedKind || (policySlot===2.U)=/=(next===0xffffff.U)){fail(Status.Malformed.U)}
      .elsewhen(policySlot===2.U){
        val hin=r.data(79,56);val hout=r.data(103,80)
        when(hin===0xffffff.U || hout===0xffffff.U || hin>=cfg.descriptors || hout>=cfg.descriptors){fail(Status.Malformed.U)}
        .otherwise{slot:=3.U;state:=tensorIssue}
      }.otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
      }
    }
    .elsewhen(isMatrix && policySlot===0.U){
      when(r.data(7,0)=/=0x10.U||next===0xffffff.U){fail(Status.Malformed.U)}
      .otherwise{policyIndex:=next;policySlot:=1.U;state:=policyIssue}
    }.elsewhen(bf16Gdn.B && isMatrix && policySlot===1.U){
      when(r.data(7,0)=/=0x12.U || next===0xffffff.U){fail(Status.Malformed.U)}
      .otherwise{policyIndex:=next;policySlot:=2.U;state:=policyIssue}
    }.elsewhen(bf16Gdn.B && isMatrix && policySlot===2.U){
      when(r.data(7,0)=/=0x21.U || next=/=0xffffff.U){fail(Status.Malformed.U)}.otherwise{state:=validate}
    }.elsewhen(isMatrix && policySlot===1.U && next=/=0xffffff.U){
      when(!(bf16V || bf16Qkv).B || opcode=/=0x20.U || r.data(7,0)=/=0x12.U){fail(Status.Unsupported.U)}
      .otherwise{extendedProjection:=true.B;policyIndex:=next;policySlot:=2.U;state:=policyIssue}
    }.elsewhen(bf16AttentionBlock.B && extendedProjection && policySlot===2.U && r.data(7,0)===0x24.U){
      // Ordinary MATRIX_GEMM is discriminated by its public typed policy;
      // never by a private opcode or the expected program counter.
      when(next===0xffffff.U){fail(Status.Malformed.U)}
      .otherwise{attentionBlockMatrix:=true.B;extendedProjection:=false.B;policyIndex:=next;policySlot:=3.U;state:=policyIssue}
    }.elsewhen(extendedProjection){
      val expectedKind=Mux(policySlot===2.U,0x1a.U,0x1b.U)
      when(r.data(7,0)=/=expectedKind || (policySlot===11.U)=/=(next===0xffffff.U)) {fail(Status.Malformed.U)}
      .elsewhen(policySlot===11.U){state:=validate}
      .otherwise{policyIndex:=next;policySlot:=policySlot+1.U;state:=policyIssue}
    }.otherwise{state:=validate}
  }
  when(state===validate){
    val a=tensors(0);val b=tensors(1);val d=tensors(2)
    val m=a.dims(0);val n=d.dims(1)
    val vp=policy(2)
    val role=vp(65,64)
    val projectionN=Mux(role===0.U,4096.U(16.W),512.U(16.W))
    val tokenBase=vp(99,68);val tokenCount=vp(107,100)
    val activeA=a.address+(tokenBase.pad(64)<<11)
    val projectionOffset=Mux(role===0.U,tokenBase.pad(64)<<13,tokenBase.pad(64)<<10)
    val projectionBytes=Mux(role===0.U,tokenCount.pad(64)<<13,tokenCount.pad(64)<<10)
    val activeD=d.address+projectionOffset
    val activeAEnd=activeA+(tokenCount.pad(64)<<11)
    val activeDEnd=activeD+projectionBytes
    val prefixes=tensors.take(3).flatMap(_.prefixIndices)
    val distinctPrefixes=(for(i<-0 until 9;j<-i+1 until 9)yield prefixes(i)=/=prefixes(j)).reduce(_&&_)
    // Version 2 is owner-managed staging. tile16 describes arithmetic tile
    // granularity, not a fixed token batch; the private SRAM chooses contexts.
    val admittedRole=Mux(bf16Qkv.B,role<=2.U,role===2.U)
    val ownerPolicy=extendedProjection && vp(7,0)===0x1a.U && vp(63,56)===2.U && admittedRole &&
      vp(67,66)===3.U && vp(127,108)===0.U && tokenCount>0.U && tokenCount<=128.U &&
      tokenBase.pad(34)+&tokenCount<=m &&
      (0 until 9).map(i=>policy(i+3)(7,0)===0x1b.U && policy(i+3)(127,120)===0.U &&
        policy(i+3)(119,112)===i.U && policy(i+3)(111,56)===0.U).reduce(_&&_)
    val projectionMatrix=policy(0)(127,56)===(m.pad(72)|(projectionN.pad(72)<<16)|(1024.U(72.W)<<32)) &&
      policy(1)(7,0)===0x12.U && policy(1)(127,56)==="h004000040020ffffff".U(72.W)
    // Q columns preserve the official [Q256, gate256] pair for each of 8
    // heads. Dense has no head-wise rearrangement and stores one contiguous D.
    val nativeProjection=(bf16V || bf16Qkv).B && opcode===0x20.U && (!bf16AttentionBlock.B || (m===1.U && tokenBase===0.U && tokenCount===1.U)) && m>0.U && m<=128.U && m<=s.maxTokens.U &&
      shape2(a,m,1024.U)&&shape2(b,1024.U,projectionN)&&shape2(d,m,projectionN)&&
      Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && ownerPolicy && projectionMatrix && distinctPrefixes
    val nativeWeight=bf16Weights.B && opcode===0x20.U && b.dtype===5.U && n(4,0)===0.U
    val validDTypes=nativeProjection || (a.dtype===7.U&&d.dtype===7.U&&(isSoftmax||b.dtype===7.U||nativeWeight))
    val plainTails=(isSoftmax||b.tail===0xffffff.U)&&d.tail===0xffffff.U&&(kv=== (a.tail===0xffffff.U))
    val noAlias= !overlap(d.address,d.paddedEnd,a.address,a.paddedEnd) && (isSoftmax|| !overlap(d.address,d.paddedEnd,b.address,b.paddedEnd))
    val sourceLive=if(enableResidentFfn)Mux(resident.get.inGroup,
      Mux(group===1.U,sameAllocation(a,q)&&live(a)&&live(b),sameAllocation(a,score)&&sameAllocation(b,probability)),
      Mux(nativeProjection,liveSpan(activeA,activeAEnd)&&live(b),Mux(group===1.U,same(a,score),Mux(group===2.U,same(a,probability)&&live(b),live(a)&&live(b)))))
    else Mux(nativeProjection,liveSpan(activeA,activeAEnd)&&live(b),Mux(group===1.U,same(a,score),Mux(group===2.U,same(a,probability)&&live(b),live(a)&&live(b))))
    val shapeBase=m>0.U&&m<=s.maxTokens.U&&n>0.U&&n<=s.maxRow.U&&n(3,0)===0.U
    val shapeSame=shape2(a,m,n)&&shape2(d,m,n)
    val norm=opcode===0x32.U&&shapeBase&&n===s.hidden.U&&shapeSame&&shape2(b,1.U,n)&&sfuPolicy(2)
    val dense=opcode===0x20.U&&shapeBase&&shape2(a,m,a.dims(1))&&shape2(b,a.dims(1),n)&&shape2(d,m,n)&&
      a.dims(1)>0.U&&a.dims(1)<=s.maxRow.U&&a.dims(1)(3,0)===0.U&&matrixPolicy(m,n,a.dims(1),false.B)
    val vector=opcode===0x30.U&&shapeBase&&shapeSame&&(shape2(b,m,n)||shape2(b,1.U,n))&&sfuPolicy(2)
    val rope=opcode===0x34.U&&shapeBase&&shapeSame&&(n===s.hidden.U||n===s.kv.U)&&
      shape3(b,2.U,s.maxTokens.U,(s.headDim/2).U)&&sfuPolicy(2)
    val activation=opcode===0x35.U&&shapeBase&&shapeSame&&shape2(b,m,n)&&n===s.ffn.U&&sfuPolicy(2)
    val append=kv&&m>0.U&&m<=s.maxTokens.U&&shape2(a,m,s.kv.U)&&shape2(b,m,s.kv.U)&&shape3(d,2.U,m,s.kv.U)
    val qk=opcode===0x23.U&&m>0.U&&m<=s.maxTokens.U&&shape2(a,m,s.hidden.U)&&shape2(b,m,s.kv.U)&&
      shape3(d,s.heads.U,m,m)&&matrixPolicy(m,m,s.headDim.U,true.B)
    val sm=isSoftmax&&group===1.U&&same(a,score)&&shape3(d,s.heads.U,q.dims(0),q.dims(0))&&sfuPolicy(1)
    val pv=opcode===0x24.U&&group===2.U&&same(a,probability)&&shape2(b,q.dims(0),s.kv.U)&&
      shape2(d,q.dims(0),s.hidden.U)&&matrixPolicy(q.dims(0),s.headDim.U,q.dims(0),false.B)
    // Qwen2OfficialBf16V2 is the explicit public21 program contract. Neither
    // Dense geometry nor outputBf16 infers a semantic materialization boundary.
    val officialRoleOK=WireDefault(true.B)
    if(officialBf16){
      val o=officialOutputs.get
      val expectedOpcode=VecInit(Seq(0x32,0x20,0x30,0x34,0x20,0x30,0x34,0x20,0x30,0x41,
        0x23,0x33,0x24,0x20,0x30,0x32,0x20,0x20,0x35,0x20,0x30).map(_.U(8.W)))
      def inputA(i:Int):Bool=a.address===o(i)
      def inputB(i:Int):Bool=b.address===o(i)
      val width=Mux(pc===4.U || pc===5.U || pc===6.U || pc===7.U || pc===8.U || pc===9.U,s.kv.U,
        Mux(pc===16.U || pc===17.U || pc===18.U,s.ffn.U,s.hidden.U))
      val ordinaryWidth=pc===9.U || pc===10.U || pc===11.U || pc===12.U || n===width
      val producer=MuxLookup(pc,false.B)(Seq(
        0.U->(norm && readonly(a) && readonly(b)),
        1.U->(dense && inputA(0) && readonly(b)),
        2.U->(vector && inputA(1) && shape2(b,1.U,s.hidden.U) && readonly(b)),
        3.U->(rope && inputA(2) && readonly(b)),
        4.U->(dense && inputA(0) && readonly(b)),
        5.U->(vector && inputA(4) && shape2(b,1.U,s.kv.U) && readonly(b)),
        6.U->(rope && inputA(5) && readonly(b)),
        7.U->(dense && inputA(0) && readonly(b)),
        8.U->(vector && inputA(7) && shape2(b,1.U,s.kv.U) && readonly(b)),
        9.U->(append && inputA(6) && inputB(8)),
        10.U->(qk && inputA(3) && inputB(9)),
        11.U->(sm && inputA(10)),
        12.U->(pv && inputA(11) && b.address===o(9)+officialRows.get.pad(64)*s.kv.U*4.U),
        13.U->(dense && inputA(12) && readonly(b)),
        14.U->(vector && a.address===officialHidden.get && inputB(13) && shape2(b,m,s.hidden.U)),
        15.U->(norm && inputA(14) && readonly(b)),
        16.U->(dense && inputA(15) && readonly(b)),
        17.U->(dense && inputA(15) && readonly(b)),
        18.U->(activation && inputA(16) && inputB(17)),
        19.U->(dense && inputA(18) && readonly(b)),
        20.U->(vector && inputA(14) && inputB(19) && shape2(b,m,s.hidden.U))))
      // Softmax/PV A is a rank-3 virtual tensor; its token dimension is checked
      // by the existing fused typed shape checks against Q, not a.dims(0).
      val rowsOK=Mux(pc===0.U,m===16.U || m===128.U,
        Mux(pc===11.U || pc===12.U,true.B,m===officialRows.get))
      officialRoleOK:=pc<21.U && opcode===expectedOpcode(pc) && producer && ordinaryWidth && rowsOK &&
        waitEvent===pc && signalEvent===pc+1.U &&
        (!dense || (nativeWeight && a.dims(1)===Mux(pc===19.U,s.ffn.U,s.hidden.U)))
    }
    val nativeQkNorm=WireDefault(false.B);val nativePartialRope=WireDefault(false.B)
    val qkLive=WireDefault(false.B);val qkFresh=WireDefault(false.B);val qkDistinct=WireDefault(true.B)
    val ap=policy(1);val ax=policy(2)
    val qkRole=ap(65,64);val qkBase=ap(99,68);val qkCount=ap(107,100)
    // One fixed decoder capacity; only the accepted profile changes Q8/Q16.
    val qkHeads=Mux(qkRole===0.U,Mux(runtimeAttentionProfile,runtimeProfile.attentionHeads.pad(16),8.U(16.W)),2.U(16.W))
    val qkWidth=(qkHeads.pad(16)<<8)(15,0)
    val qkBytes=(qkCount.pad(64)*qkHeads.pad(64)<<9)(63,0)
    val qkOffset=(qkBase.pad(64)*qkHeads.pad(64)<<9)(63,0)
    val qkInputOffset=Mux(opcode===0x32.U && qkRole===0.U,qkOffset<<1,qkOffset)
    val qkActiveA=a.address+qkInputOffset;val qkActiveD=d.address+qkOffset
    if(bf16QkNormRope||enableRuntimeQkNorm){
      val gate=tensors(3);val program=policy(0);val normQ=opcode===0x32.U && qkRole===0.U
      val usedCount=Mux(normQ,4.U,3.U)
      val indices=tensors.take(4).flatMap(_.prefixIndices)++policyIndices.take(3)
      val used=indices.indices.map(i=>if(i<12)(i/3).U<usedCount else true.B)
      qkDistinct:=(for(i<-indices.indices;j<-i+1 until indices.size)yield !used(i)|| !used(j)||indices(i)=/=indices(j)).reduce(_&&_)
      val programOK=program(7,0)===0x20.U && program(55,32)=/=0xffffff.U &&
        program(71,56)===opcode && program(79,72)===2.U && program(87,80)===1.U &&
        program(91,88)===5.U && program(95,92)===5.U && program(103,96)===16.U && program(127,104)===0.U
      val policyOK=ap(7,0)===0x24.U && ap(55,32)=/=0xffffff.U && ap(63,56)===1.U && qkRole<=1.U &&
        ap(67,66)===Mux(opcode===0x32.U,0.U,1.U) &&
        Mux(runtimeQkNormCommand,ap(115,108)==="hc1".U || ap(115,108)==="hc2".U,
          ap(115,108)===Mux(opcode===0x32.U,"hc1".U,"hb1".U)) &&
        ap(127,116)===0.U && qkCount>0.U && qkCount<=128.U && qkBase.pad(34)+&qkCount<=m
      val extraOK=finishRecord(ax,0x25.U) && ax(127,112)===0.U &&
        Mux(normQ,ax(79,56)=/=0xffffff.U,ax(79,56)===0xffffff.U)
      val common=qkCommandPolicy && m>0.U && m<=128.U && (runtimeQkCommand || m<=s.maxTokens.U) &&
        (!runtimeQkCommand || (qkBase===0.U && qkCount===m && txCold && txGeneration===0.U && !attentionCacheValid)) && programOK && policyOK && extraOK &&
        Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && b.tail===0xffffff.U && d.tail===0xffffff.U && shape2(d,m,qkWidth)
      nativeQkNorm:=common && opcode===0x32.U && ax(111,80)===0.U &&
        shape2(a,m,Mux(qkRole===0.U,qkWidth<<1,qkWidth)) && shape2(b,1.U,256.U) &&
        (!normQ || (shape2(gate,m,qkWidth) && gate.dtype===5.U && gate.tail===0xffffff.U))
      nativePartialRope:=common && opcode===0x34.U && shape2(a,m,qkWidth) &&
        b.dims(0)>0.U && shape2(b,b.dims(0),64.U) && ax(111,80).pad(65)+qkCount<=b.dims(0)
      val knownProjection=qkProjectedValid(qkRole) && a.address===qkProjected(qkRole) && (!(bf16AttentionCore.B || runtimeAttentionProfile) || sameAllocation(a,qkProjectedTensor(qkRole))) &&
        m===qkRows(qkRole) && qkBase===qkWindowBase(qkRole) && qkCount===qkWindowCount(qkRole)
      val knownNorm=qkNormalizedValid(qkRole) && a.address===qkNormalized(qkRole) && (!(bf16AttentionCore.B || runtimeAttentionProfile) || sameAllocation(a,qkNormalizedTensor(qkRole))) &&
        m===qkRows(qkRole) && qkBase===qkWindowBase(qkRole) && qkCount===qkWindowCount(qkRole)
      val weightRole=Mux(opcode===0x32.U,4.U+qkRole,6.U)
      val coreOrder=Mux(opcode===0x32.U,
        qkProjectedValid.asUInt.andR && !qkNormalizedValid(qkRole) && Mux(qkRole===0.U,!qkNormalizedValid(1),qkNormalizedValid(0)),
        qkNormalizedValid.asUInt.andR && !qkRotatedValid(qkRole) && Mux(qkRole===0.U,!qkRotatedValid(1),qkRotatedValid(0)))
      val corePosition=opcode=/=0x34.U || (ax(111,80)===Mux(attentionCacheValid,attentionLength,0.U) &&
        (qkRole===0.U || ax(111,80)===qkAbsolutePosition(0)))
      qkLive:=(!(bf16AttentionCore.B || runtimeAttentionProfile) || (coreOrder && corePosition)) && Mux(opcode===0x32.U,knownProjection,knownNorm) && readonly(b) && sourceAllowed(b,weightRole) &&
        liveSpan(qkActiveA,qkActiveA+Mux(normQ,qkBytes<<1,qkBytes))
      val operands=Seq(a,b,d,gate)
      val disjoint=(for(i<-operands.indices;j<-i+1 until operands.size)yield
        (j==3).B && !normQ || !overlap(operands(i).address,operands(i).paddedEnd,operands(j).address,operands(j).paddedEnd)).reduce(_&&_)
      qkFresh:=disjoint && fresh(d) && readwrite(d) && (!normQ || (fresh(gate)&&readwrite(gate)))
    }
    val attentionAppend=WireDefault(false.B);val attentionQk=WireDefault(false.B)
    val attentionSoft=WireDefault(false.B);val attentionPv=WireDefault(false.B);val attentionFence=WireDefault(false.B)
    val attentionLive=WireDefault(false.B);val attentionFresh=WireDefault(false.B);val attentionDistinct=WireDefault(true.B)
    val attentionBlockRms=WireDefault(false.B);val attentionBlockDense=WireDefault(false.B);val attentionBlockElement=WireDefault(false.B)
    val cp=policy(attentionPolicySlot);val cx=policy(attentionContextSlot)
    val attentionOp=cp(67,64);val attentionBase=cp(99,68);val attentionCount=cp(107,100)
    val attentionBlockRole=cp(118,116)
    val attentionCapacity=cx(72,64);val attentionExpectedLength=cx(81,73);val attentionQueryStart=cx(90,82)
    val attentionExpectedGeneration=cx(122,91);val attentionCold=cx(123)
    val attentionNewLength=attentionExpectedLength.pad(33)+attentionCount.pad(33)
    if(bf16AttentionCore||enableRuntimeKvAppend||enableRuntimeGqa){
      val arithmetic=attentionOp>=1.U && attentionOp<=3.U
      val policyOK=cp(7,0)===0x24.U && cp(55,32)=/=0xffffff.U && cp(63,56)===2.U && attentionOp<=(if(bf16AttentionBlock)3 else 4).U &&
        cp(115,108)===Mux(arithmetic,"ha1".U,0.U) && cp(127,116)===0.U && attentionCount>0.U && attentionCount<=128.U
      val contextOK=finishRecord(cx,0x26.U) && cx(63,56)===2.U && cx(127,125)===0.U && cx(124) &&
        attentionCapacity>0.U && attentionCapacity<=256.U && attentionExpectedLength===attentionQueryStart &&
        attentionNewLength<=attentionCapacity && attentionExpectedGeneration=/="hffffffff".U &&
        Mux(attentionCold,attentionExpectedLength===0.U && attentionExpectedGeneration===0.U,
          attentionExpectedLength>0.U && attentionExpectedGeneration>0.U)
      val tails=(isSoftmax || b.tail===0xffffff.U) && d.tail===0xffffff.U
      val typeOK=a.dtype===5.U && d.dtype===5.U && (isSoftmax || b.dtype===5.U)
      val blockWindow=attentionBase===0.U && attentionCount===1.U
      // Runtime mode12 is a cold, whole-window staging append only. The same
      // original policy/context records are decoded without widening the Host
      // ABI or opening legacy GQA/core-only fences for either runtime profile.
      val runtimeAppendContext= !runtimeKvAppendCommand || (attentionOp===0.U && group===0.U &&
        attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U &&
        attentionExpectedGeneration===0.U && attentionQueryStart===0.U &&
        attentionBase===0.U && attentionCount===m && m>0.U && m<=128.U &&
        txCold && txGeneration===0.U && !attentionCacheValid)
      // Same original three-command QK/Softmax/PV fusion. This first common
      // installation admits ONLY cold M128/C128, not decode or partial windows.
      // qkOrder is the pinned profile2/profile4 pair-high-first policy, not a
      // host-selected spare bit; the original A1 public arithmetic record stays.
      val runtimeGqaContext= !runtimeGqaCommand || (attentionOp>=1.U && attentionOp<=3.U &&
        attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U &&
        attentionExpectedGeneration===0.U && attentionQueryStart===0.U &&
        attentionBase===0.U && attentionCount===128.U && qkRows(0)===128.U &&
        txCold && txGeneration===0.U && !attentionCacheValid)
      val attentionHeads=Mux(runtimeGqaCommand,runtimeProfile.attentionHeads.pad(16),8.U(16.W))
      val attentionWidth=attentionHeads<<8
      val common=attentionCommandPolicy && policyOK && contextOK && tails && typeOK &&
        (!bf16AttentionBlock.B || blockWindow) && runtimeAppendContext && runtimeGqaContext
      def matrix(m:UInt,n:UInt,k:UInt,transpose:Bool):Bool={val p=policy(0);val aux=policy(1)
        p(7,0)===0x10.U && p(31,8)===0.U && p(55,32)=/=0xffffff.U && p(71,56)===m && p(87,72)===n &&
          p(111,88)===k && p(114,112)===0.U && p(115)===transpose && p(127,116)===0.U &&
          aux(7,0)===0x12.U && aux(31,8)===0.U && aux(55,32)=/=0xffffff.U && aux(127,56)==="h004000040020ffffff".U(72.W)
      }
      def program(inputs:Int):Bool={val p=policy(0)
        p(7,0)===0x20.U && p(31,8)===0.U && p(55,32)=/=0xffffff.U && p(71,56)===opcode &&
          p(79,72)===inputs.U && p(87,80)===1.U && p(91,88)===5.U && p(95,92)===5.U &&
          p(103,96)===16.U && p(127,104)===0.U
      }
      val rows=qkRows(0);val window=attentionBase===qkWindowBase(0) && attentionCount===qkWindowCount(0) &&
        attentionBase.pad(34)+&attentionCount<=rows
      val cacheD=shape3(d,2.U,attentionCapacity,512.U)
      val cacheB=shape3(b,2.U,attentionCapacity,512.U)
      attentionAppend:=common && kv && attentionOp===0.U && shape2(a,rows,512.U) && shape2(b,rows,512.U) && cacheD
      attentionQk:=common && opcode===0x23.U && attentionOp===1.U && shape2(a,rows,attentionWidth) && cacheB &&
        shape3(d,attentionHeads,attentionCount,attentionNewLength) && matrix(attentionCount,attentionNewLength,256.U,true.B)
      attentionSoft:=common && isSoftmax && attentionOp===2.U && group===1.U &&
        shape3(a,attentionHeads,attentionCount,attentionNewLength) && shape3(d,attentionHeads,attentionCount,attentionNewLength) && program(1)
      attentionPv:=common && opcode===0x24.U && attentionOp===3.U && group===2.U &&
        shape3(a,attentionHeads,attentionCount,attentionNewLength) && cacheB && shape2(d,rows,attentionWidth) &&
        matrix(attentionCount,256.U,attentionNewLength,false.B)
      if(!bf16AttentionBlock){
        attentionFence:=common && opcode===0x30.U && attentionOp===4.U && group===0.U &&
          shape3(a,2.U,attentionCapacity,512.U) && shape2(b,rows,2048.U) && shape2(d,rows,2048.U) && program(2)
      }
      val countPolicy=attentionContextSlot+1.U
      val indices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(4)
      val used=indices.indices.map(i=>if(i<9) !((i/3)==1).B || !isSoftmax else (i-9).U<countPolicy)
      attentionDistinct:=(for(i<-indices.indices;j<-i+1 until indices.size)yield !used(i)|| !used(j)||indices(i)=/=indices(j)).reduce(_&&_)
      val trusted=attentionCold=== !attentionCacheValid && attentionExpectedLength===Mux(attentionCacheValid,attentionLength,0.U) &&
        attentionExpectedGeneration===Mux(attentionCacheValid,attentionGeneration,0.U)
      val staged=pendingAttentionValid && !pendingGqaValid && attentionExpectedLength===pendingAttentionOldLength &&
        attentionExpectedGeneration===pendingAttentionGeneration && attentionCold===pendingAttentionCold &&
        attentionBase===pendingAttentionBase && attentionCount===pendingAttentionCount && attentionNewLength===pendingAttentionLength &&
        attentionCapacity===pendingAttentionCache.dims(1)
      val producers=qkProjectedValid.asUInt.andR && qkNormalizedValid.asUInt.andR && qkRotatedValid.asUInt.andR &&
        qkAbsolutePosition(0)===attentionQueryStart && qkAbsolutePosition(1)===attentionQueryStart &&
        (0 until 3).map(i=>qkRows(i)===rows && qkWindowBase(i)===attentionBase &&
          qkWindowCount(i)===attentionCount).reduce(_&&_)
      val appendLive=producers && !pendingAttentionValid && !pendingGqaValid && trusted &&
        (!bf16AttentionBlock.B || (attentionBlockValid(0) && cx(127,56)===attentionBlockContext)) &&
        sameAllocation(a,qkRotatedTensor(1)) && sameAllocation(b,qkProjectedTensor(2)) &&
        liveSpan(a.address+(attentionBase.pad(64)<<10),a.address+((attentionBase.pad(64)+attentionCount)<<10)) &&
        liveSpan(b.address+(attentionBase.pad(64)<<10),b.address+((attentionBase.pad(64)+attentionCount)<<10)) &&
        (!attentionCacheValid || sameAllocation(d,attentionCache))
      val qkLive=staged && producers && sameAllocation(a,qkRotatedTensor(0)) && sameAllocation(b,pendingAttentionCache)
      val softLive=staged && sameAllocation(a,score)
      val pvLive=staged && sameAllocation(a,probability) && sameAllocation(b,pendingAttentionCache)
      val fenceLive=pendingAttentionValid && pendingGqaValid && attentionExpectedLength===pendingAttentionOldLength &&
        attentionExpectedGeneration===pendingAttentionGeneration && attentionCold===pendingAttentionCold &&
        attentionBase===pendingAttentionBase && attentionCount===pendingAttentionCount && attentionNewLength===pendingAttentionLength &&
        sameAllocation(a,pendingAttentionCache) && sameAllocation(b,qkRotatedTensor(0)) && sameAllocation(d,pendingAttentionContext)
      attentionLive:=window && Mux(attentionAppend,appendLive,Mux(attentionQk,qkLive,Mux(attentionSoft,softLive,Mux(attentionPv,pvLive,fenceLive))))
      val disjoint= !overlap(d.address,d.paddedEnd,a.address,a.paddedEnd) &&
        (isSoftmax || !overlap(d.address,d.paddedEnd,b.address,b.paddedEnd)) &&
        (isSoftmax || !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd))
      val appendFresh=disjoint && readwrite(d) && Mux(attentionCacheValid,reusableAttentionCache(d),fresh(d))
      val freshOutput=disjoint && fresh(d) && readwrite(d)
      attentionFresh:=Mux(attentionAppend,appendFresh,Mux(attentionFence,true.B,freshOutput))
      if(bf16AttentionBlock){
        // ATTENTION_POLICY v3: payload op[11:8], role[62:60], tokenCount=1.
        // Full-record coordinates add 56: op[67:64], role[118:116].
        val role=attentionBlockRole
        val blockPolicy=cp(7,0)===0x24.U && cp(55,32)=/=0xffffff.U && cp(63,56)===3.U &&
          attentionOp>=4.U && attentionOp<=7.U && cp(115,108)===0.U && cp(127,119)===0.U && blockWindow &&
          Mux(attentionOp===4.U,role===0.U,Mux(attentionOp===5.U,role<=1.U,role<=3.U))
        val blockCommon=attentionCommandPolicy && blockPolicy && contextOK && tails && typeOK && group===0.U
        val denseK=Mux(role===0.U,2048.U,Mux(role===3.U,3584.U,1024.U))
        val denseN=Mux(role===0.U || role===3.U,1024.U,3584.U)
        val elementN=Mux(role===0.U,2048.U,Mux(role===2.U,3584.U,1024.U))
        attentionBlockRms:=blockCommon && opcode===0x30.U && attentionOp===5.U && program(2) &&
          shape2(a,1.U,1024.U) && shape2(b,1.U,1024.U) && shape2(d,1.U,1024.U)
        attentionBlockDense:=blockCommon && opcode===0x20.U && attentionOp===6.U &&
          shape2(a,1.U,denseK) && shape2(b,denseK,denseN) && shape2(d,1.U,denseN) && matrix(1.U,denseN,denseK,false.B)
        attentionBlockElement:=blockCommon && opcode===0x30.U && attentionOp===7.U && program(2) &&
          shape2(a,1.U,elementN) && shape2(b,1.U,elementN) && shape2(d,1.U,elementN)
        attentionFence:=blockCommon && opcode===0x30.U && attentionOp===4.U && program(2) &&
          shape3(a,2.U,attentionCapacity,512.U) && shape2(b,1.U,1024.U) && shape2(d,1.U,1024.U)
        def actual(t:DecodedTensor,i:Int):Bool=attentionBlockValid(i) && sameAllocation(t,attentionBlockValues(i)) && live(t)
        val sameContext=cx(127,56)===attentionBlockContext
        val inputRms=role===0.U && !attentionBlockValid.asUInt.orR && !qkProjectedValid.asUInt.orR &&
          !pendingAttentionValid && trusted && readonly(a) && readonly(b) && sourceAllowed(a,0.U) && sourceAllowed(b,7.U)
        val postRms=role===1.U && actual(a,4) && !attentionBlockValid(5) && readonly(b) && sourceAllowed(b,9.U) && sameContext
        val denseProducer=MuxLookup(role,false.B)(Seq(
          0.U->(actual(a,2) && !attentionBlockValid(3)),
          1.U->(actual(a,5) && !attentionBlockValid(6)),
          2.U->(actual(a,5) && attentionBlockValid(6) && !attentionBlockValid(7)),
          3.U->(actual(a,8) && !attentionBlockValid(9))))
        val weightRole=Mux(role===0.U,8.U,role+9.U)
        val elementProducer=MuxLookup(role,false.B)(Seq(
          0.U->(pendingAttentionValid && pendingGqaValid && actual(a,1) && sameAllocation(b,pendingAttentionContext) && live(b) && !attentionBlockValid(2)),
          1.U->(sourceValid(0) && sameAllocation(a,sourceTensor(0)) && live(a) && actual(b,3) && !attentionBlockValid(4)),
          2.U->(actual(a,6) && actual(b,7) && !attentionBlockValid(8)),
          3.U->(actual(a,4) && actual(b,9) && !attentionBlockValid(10))))
        val fullFenceLive=pendingAttentionValid && pendingGqaValid && attentionBlockValid.asUInt.andR && sameContext &&
          sameAllocation(a,pendingAttentionCache) && sourceValid(0) && sameAllocation(b,sourceTensor(0)) && actual(d,10) &&
          (1 until sourceCount).map(i=>sourceValid(i)).reduce(_&&_)
        when(attentionBlockRms || attentionBlockDense || attentionBlockElement || attentionFence){
          attentionLive:=Mux(attentionBlockRms,inputRms||postRms,
            Mux(attentionBlockDense,sameContext && denseProducer && readonly(b) && sourceAllowed(b,weightRole),
            Mux(attentionBlockElement,sameContext && elementProducer,fullFenceLive)))
          attentionFresh:=disjoint && Mux(attentionFence,readwrite(a) && readonly(b) && readwrite(d),fresh(d) && readwrite(d))
        }
      }
    }
    val nativeAttention=attentionAppend||attentionQk||attentionSoft||attentionPv||attentionFence||attentionBlockRms||attentionBlockDense||attentionBlockElement
    val nativeGdn=WireDefault(false.B);val gdnProjection=WireDefault(false.B);val gdnLive=WireDefault(false.B)
    val gdnFresh=WireDefault(false.B);val gdnDistinct=WireDefault(true.B)
    val corePrep=WireDefault(false.B);val coreRecurrent=WireDefault(false.B);val coreNorm=WireDefault(false.B);val coreFence=WireDefault(false.B)
    val blockRmsNorm=WireDefault(false.B);val blockElementwise=WireDefault(false.B)
    if(bf16GdnBlock){
      val x=tensors(3);val y=tensors(4);val program=policy(0);val gp=policy(1);val extra=policy(2)
      val op=gp(71,64);val role=gp(84,82);val cold=gp(80);val generation=gp(119,88)
      val denseRole=policy(2)(84,82)
      val extraCount=Mux(op===1.U || op===3.U,2.U,Mux(op===4.U || op===5.U,1.U,0.U))
      val tensorCount=Mux(gdnCommand,3.U+extraCount,3.U)
      val policyCount=Mux(gdnCommand && (op===6.U || op===8.U || op===9.U),2.U,3.U)
      val allIndices=tensors.flatMap(_.prefixIndices)++policyIndices.take(3)
      val indexUsed=(0 until 18).map(i=>if(i<15)(i/3).U<tensorCount else (i-15).U<policyCount)
      gdnDistinct:=(for(i<-allIndices.indices;j<-i+1 until allIndices.size)yield
        !indexUsed(i) || !indexUsed(j) || allIndices(i)=/=allIndices(j)).reduce(_&&_)
      val denseK=Mux(denseRole===3.U,2048.U,Mux(denseRole===6.U,3584.U,1024.U))
      val denseN=MuxLookup(denseRole,0.U)(Seq(0.U->6144.U,1.U->2048.U,2.U->32.U,
        3.U->1024.U,4.U->3584.U,5.U->3584.U,6.U->1024.U))
      gdnProjection:=opcode===0x20.U && denseRole<=6.U && m===1.U && n===denseN &&
        shape2(a,1.U,denseK) && shape2(b,denseK,denseN) && shape2(d,1.U,denseN) &&
        Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && b.tail===0xffffff.U && d.tail===0xffffff.U &&
        policy(0)(127,56)===(1.U(72.W)|(denseN.pad(72)<<16)|(denseK.pad(72)<<32)) &&
        policy(1)(127,56)==="h004000040020ffffff".U(72.W) &&
        finishRecord(policy(2),0x21.U) && policy(2)(63,56)===3.U && policy(2)(71,64)===2.U &&
        policy(2)(79,72)===0.U && policy(2)(81)=== !policy(2)(80) && policy(2)(87,85)===0.U && policy(2)(127,120)===0.U
      val programOK=program(7,0)===0x20.U && program(55,32)=/=0xffffff.U &&
        program(71,56)===0x30.U && program(79,72)===2.U && program(87,80)===1.U &&
        program(91,88)===Mux(op===4.U,7.U,5.U) && program(95,92)===Mux(op===3.U,7.U,5.U) &&
        program(103,96)===16.U && program(111,104)===1.U && program(127,112)===0.U
      val noExtras=op===6.U || op===8.U || op===9.U
      val roleOK=Mux(op===8.U,role<=1.U,Mux(op===9.U,role<=2.U,role===0.U))
      val policyOK=gp(7,0)===0x21.U && gp(63,56)===3.U && gp(79,72)===0.U && roleOK &&
        gp(87,85)===0.U && gp(127,120)===0.U &&
        Mux(noExtras,gp(55,32)===0xffffff.U,gp(55,32)=/=0xffffff.U) && gp(81)=== !cold
      val extraOK=finishRecord(extra,Mux(op===1.U,0x22.U,0x23.U)) && extra(127,104)===0.U
      val common=gdnCommand && programOK && policyOK && (noExtras || extraOK) && b.tail===0xffffff.U && d.tail===0xffffff.U
      nativeGdn:=common && op===1.U && shape2(a,1.U,6144.U) && shape2(b,6144.U,4.U) && shape2(d,1.U,6144.U) &&
        shape2(x,6144.U,4.U) && shape2(y,6144.U,4.U) && tensors.map(_.dtype===5.U).reduce(_&&_) &&
        x.tail===0xffffff.U && y.tail===0xffffff.U
      corePrep:=common && op===3.U && shape2(a,1.U,6144.U) && shape2(b,1.U,32.U) && shape2(d,1.U,6400.U) &&
        shape2(x,1.U,16.U) && shape2(y,1.U,16.U) && a.dtype===5.U && b.dtype===5.U && d.dtype===7.U &&
        x.dtype===7.U && y.dtype===5.U && x.tail===0xffffff.U && y.tail===0xffffff.U
      coreRecurrent:=common && op===4.U && shape2(a,1.U,6400.U) && shape2(b,2048.U,128.U) && shape2(d,1.U,2048.U) &&
        shape2(x,2048.U,128.U) && a.dtype===7.U && b.dtype===7.U && d.dtype===5.U && x.dtype===7.U && x.tail===0xffffff.U
      coreNorm:=common && op===5.U && shape2(a,1.U,2048.U) && shape2(b,1.U,2048.U) && shape2(d,1.U,2048.U) &&
        shape2(x,1.U,128.U) && Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && x.dtype===7.U && x.tail===0xffffff.U
      blockRmsNorm:=common && op===8.U && shape2(a,1.U,1024.U) && shape2(b,1.U,1024.U) && shape2(d,1.U,1024.U) &&
        Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_)
      val elementWidth=Mux(role===1.U,3584.U,1024.U)
      blockElementwise:=common && op===9.U && shape2(a,1.U,elementWidth) && shape2(b,1.U,elementWidth) &&
        shape2(d,1.U,elementWidth) && Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_)
      coreFence:=common && op===6.U && shape2(a,6144.U,4.U) && shape2(b,2048.U,128.U) && shape2(d,1.U,1024.U) &&
        a.dtype===5.U && b.dtype===7.U && d.dtype===5.U
      val expectedContext=generation===Mux(stateValid,currentGeneration,0.U) && cold=== !stateValid && generation=/="hffffffff".U
      val sameContext=generation===txGeneration && cold===txCold && generation=/="hffffffff".U
      val projectionContext=policy(2)(119,88)===txGeneration && policy(2)(80)===txCold && policy(2)(119,88)=/="hffffffff".U
      val historyLive=Mux(stateValid,!cold && generation===currentGeneration && x.address===currentHistoryAddress && x.paddedEnd===currentHistoryEnd,generation===0.U && cold)
      val recurrentLive=Mux(stateValid,!cold && generation===currentGeneration && b.address===currentStateAddress && b.paddedEnd===currentStateEnd,generation===0.U && cold)
      val projectionProducer=MuxLookup(denseRole,false.B)(Seq(
        0.U->(txInputNormValid && !txQkvValid && a.address===txInputNorm),
        1.U->(txQkvValid && !txZValid && a.address===txInputNorm),
        2.U->(txZValid && !txAbValid && a.address===txInputNorm),
        3.U->(txNormValid && !txOValid && a.address===txNorm),
        4.U->(txPostNormValid && !txGateValid && a.address===txPostNorm),
        5.U->(txGateValid && !txUpValid && a.address===txPostNorm),
        6.U->(txSiluValid && !txDownValid && a.address===txSilu)))
      val rmsProducer=Mux(role===0.U,!txInputValid && !txInputNormValid && expectedContext,
        txResidual1Valid && !txPostNormValid && a.address===txResidual1 && sameContext)
      val elementProducer=MuxLookup(role,false.B)(Seq(
        0.U->(txOValid && !txResidual1Valid && a.address===txInputAddress && a.paddedEnd===txInputEnd && b.address===txO),
        1.U->(txGateValid && txUpValid && !txSiluValid && a.address===txGate && b.address===txUp),
        2.U->(txDownValid && txResidual1Valid && !txResidual2Valid && a.address===txResidual1 && b.address===txDown)))
      gdnLive:=Mux(gdnProjection,txInputValid && live(a) && live(b) && projectionProducer && projectionContext,
        Mux(blockRmsNorm,live(a) && live(b) && rmsProducer,
        Mux(blockElementwise,live(a) && live(b) && elementProducer && sameContext,
        Mux(nativeGdn,txQkvValid && txZValid && txAbValid && !txConvValid && a.address===txQkv && live(a) && live(b) && historyLive && sameContext,
        Mux(corePrep,txConvValid && txAbValid && !txPrepValid && a.address===txConv && b.address===txAb && live(a) && live(b) && live(x) && live(y) && sameContext,
        Mux(coreRecurrent,txPrepValid && !txRecurrentValid && a.address===txPrep && live(a) && recurrentLive && sameContext,
        Mux(coreNorm,txRecurrentValid && txZValid && !txNormValid && a.address===txRecurrent && b.address===txZ && live(a) && live(b) && live(x) && sameContext,
        coreFence && txConvValid && txRecurrentValid && txResidual2Valid && sameContext && live(a) && live(b) && live(d) &&
          a.address===pendingHistoryAddress && a.paddedEnd===pendingHistoryEnd &&
          b.address===pendingStateAddress && b.paddedEnd===pendingStateEnd && d.address===txResidual2)))))))
      val projectionWeightRole=Mux(denseRole<=2.U,denseRole+1.U,Mux(denseRole===3.U,11.U,denseRole+9.U))
      val sourceRoles=Mux(gdnProjection,sourceAllowed(b,projectionWeightRole),
        Mux(blockRmsNorm,Mux(role===0.U,sourceAllowed(a,0.U) && sourceAllowed(b,10.U),sourceAllowed(b,12.U)),
        Mux(nativeGdn,sourceAllowed(b,4.U) && sourceAllowed(x,8.U),
        Mux(corePrep,sourceAllowed(x,5.U) && sourceAllowed(y,6.U),
        Mux(coreRecurrent,sourceAllowed(b,9.U),Mux(coreNorm,sourceAllowed(x,7.U),true.B))))))
      val operands=Seq(a,b,d,x,y)
      val disjoint=(for(i<-operands.indices;j<-i+1 until operands.size)yield
        i.U>=tensorCount || j.U>=tensorCount || !overlap(operands(i).address,operands(i).paddedEnd,operands(j).address,operands(j).paddedEnd)).reduce(_&&_)
      gdnFresh:=disjoint && sourceRoles && Mux(coreFence,readwrite(a) && readwrite(b) && readwrite(d),
        fresh(d) && readwrite(d) && Mux(nativeGdn,fresh(y) && readwrite(y),Mux(coreRecurrent,fresh(x) && readwrite(x),true.B)))
    }else if(bf16GdnCore){
      val x=tensors(3);val y=tensors(4);val program=policy(0);val gp=policy(1);val extra=policy(2)
      val op=gp(71,64);val cold=gp(80);val generation=gp(119,88)
      val extraCount=Mux(op===1.U || op===3.U,2.U,Mux(op===4.U || op===5.U,1.U,0.U))
      val tensorCount=Mux(gdnCommand,3.U+extraCount,3.U)
      val policyCount=Mux(gdnCommand && op===6.U,2.U,3.U)
      val allIndices=tensors.flatMap(_.prefixIndices)++policyIndices.take(3)
      val indexUsed=(0 until 18).map(i=>if(i<15)(i/3).U<tensorCount else (i-15).U<policyCount)
      gdnDistinct:=(for(i<-allIndices.indices;j<-i+1 until allIndices.size)yield
        !indexUsed(i) || !indexUsed(j) || allIndices(i)=/=allIndices(j)).reduce(_&&_)
      val projectionShape=n===6144.U || n===2048.U || n===32.U
      gdnProjection:=opcode===0x20.U && m===1.U && projectionShape &&
        shape2(a,1.U,1024.U) && shape2(b,1024.U,n) && shape2(d,1.U,n) &&
        Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && b.tail===0xffffff.U && d.tail===0xffffff.U &&
        policy(0)(127,56)===(1.U(72.W)|(n.pad(72)<<16)|(1024.U(72.W)<<32)) &&
        policy(1)(127,56)==="h004000040020ffffff".U(72.W) &&
        finishRecord(policy(2),0x21.U) && policy(2)(63,56)===2.U && policy(2)(71,64)===2.U &&
        policy(2)(79,72)===0.U && policy(2)(81)=== !policy(2)(80) && policy(2)(87,82)===0.U && policy(2)(127,120)===0.U
      val programOK=program(7,0)===0x20.U && program(55,32)=/=0xffffff.U &&
        program(71,56)===0x30.U && program(79,72)===2.U && program(87,80)===1.U &&
        program(91,88)===Mux(op===4.U,7.U,5.U) && program(95,92)===Mux(op===3.U,7.U,5.U) &&
        program(103,96)===16.U && program(111,104)===1.U && program(127,112)===0.U
      val policyOK=gp(7,0)===0x21.U && gp(63,56)===2.U && gp(79,72)===0.U &&
        gp(87,82)===0.U && gp(127,120)===0.U &&
        Mux(op===6.U,gp(55,32)===0xffffff.U,gp(55,32)=/=0xffffff.U) &&
        gp(81)=== !cold
      val extraOK=finishRecord(extra,Mux(op===1.U,0x22.U,0x23.U)) && extra(127,104)===0.U
      val common=gdnCommand && programOK && policyOK && (op===6.U || extraOK) && b.tail===0xffffff.U && d.tail===0xffffff.U
      nativeGdn:=common && op===1.U && shape2(a,1.U,6144.U) && shape2(b,6144.U,4.U) && shape2(d,1.U,6144.U) &&
        shape2(x,6144.U,4.U) && shape2(y,6144.U,4.U) && tensors.map(_.dtype===5.U).reduce(_&&_) &&
        x.tail===0xffffff.U && y.tail===0xffffff.U
      corePrep:=common && op===3.U && shape2(a,1.U,6144.U) && shape2(b,1.U,32.U) && shape2(d,1.U,6400.U) &&
        shape2(x,1.U,16.U) && shape2(y,1.U,16.U) && a.dtype===5.U && b.dtype===5.U && d.dtype===7.U &&
        x.dtype===7.U && y.dtype===5.U && x.tail===0xffffff.U && y.tail===0xffffff.U
      coreRecurrent:=common && op===4.U && shape2(a,1.U,6400.U) && shape2(b,2048.U,128.U) && shape2(d,1.U,2048.U) &&
        shape2(x,2048.U,128.U) && a.dtype===7.U && b.dtype===7.U && d.dtype===5.U && x.dtype===7.U && x.tail===0xffffff.U
      coreNorm:=common && op===5.U && shape2(a,1.U,2048.U) && shape2(b,1.U,2048.U) && shape2(d,1.U,2048.U) &&
        shape2(x,1.U,128.U) && Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && x.dtype===7.U && x.tail===0xffffff.U
      coreFence:=common && op===6.U && shape2(a,6144.U,4.U) && shape2(b,2048.U,128.U) && shape2(d,1.U,2048.U) &&
        a.dtype===5.U && b.dtype===7.U && d.dtype===5.U
      val initialHistory=generation===0.U && cold
      val carriedHistory= !cold && generation===currentGeneration && x.address===currentHistoryAddress && x.paddedEnd===currentHistoryEnd
      val historyLive=Mux(stateValid,carriedHistory,initialHistory)
      val initialState=generation===0.U && cold
      val carriedState= !cold && generation===currentGeneration && b.address===currentStateAddress && b.paddedEnd===currentStateEnd
      val recurrentLive=Mux(stateValid,carriedState,initialState)
      val sameGeneration=generation===txGeneration && generation=/="hffffffff".U
      val operands=Seq(a,b,d,x,y)
      val disjoint=(for(i<-operands.indices;j<-i+1 until operands.size)yield
        i.U>=tensorCount || j.U>=tensorCount || !overlap(operands(i).address,operands(i).paddedEnd,operands(j).address,operands(j).paddedEnd)).reduce(_&&_)
      val projectionNew=Mux(n===6144.U,!txQkvValid,Mux(n===2048.U,!txZValid,!txAbValid))
      val projectionSource= !txInputValid || (a.address===txInputAddress && a.paddedEnd===txInputEnd)
      val projectionGeneration=policy(2)(119,88)===Mux(stateValid,currentGeneration,0.U) &&
        policy(2)(119,88)=/="hffffffff".U && policy(2)(80)=== !stateValid &&
        (!txInputValid || (policy(2)(119,88)===txGeneration && policy(2)(80)===txCold))
      gdnLive:=Mux(gdnProjection,live(a) && live(b) && projectionNew && projectionSource && projectionGeneration,
        Mux(nativeGdn,txQkvValid && !txConvValid && a.address===txQkv && live(a) && live(b) && historyLive && sameGeneration && cold===txCold,
        Mux(corePrep,txConvValid && txAbValid && !txPrepValid && a.address===txConv && b.address===txAb && live(a) && live(b) && live(x) && live(y) && sameGeneration && cold===txCold,
        Mux(coreRecurrent,txPrepValid && !txRecurrentValid && a.address===txPrep && live(a) && recurrentLive && sameGeneration && cold===txCold,
        Mux(coreNorm,txRecurrentValid && txZValid && !txNormValid && a.address===txRecurrent && b.address===txZ && live(a) && live(b) && live(x) && sameGeneration && cold===txCold,
        coreFence && txConvValid && txRecurrentValid && txNormValid && sameGeneration && cold===txCold && live(a) && live(b) && live(d) &&
          a.address===pendingHistoryAddress && a.paddedEnd===pendingHistoryEnd &&
          b.address===pendingStateAddress && b.paddedEnd===pendingStateEnd && d.address===txNorm)))))
      val projectionWeightRole=Mux(n===6144.U,1.U,Mux(n===2048.U,2.U,3.U))
      val sourceRoles=Mux(gdnProjection,sourceAllowed(a,0.U) && sourceAllowed(b,projectionWeightRole),
        Mux(nativeGdn,sourceAllowed(b,4.U) && sourceAllowed(x,8.U),
        Mux(corePrep,sourceAllowed(x,5.U) && sourceAllowed(y,6.U),
        Mux(coreRecurrent,sourceAllowed(b,9.U),Mux(coreNorm,sourceAllowed(x,7.U),true.B)))))
      gdnFresh:=disjoint && sourceRoles && Mux(coreFence,readwrite(a) && readwrite(b) && readwrite(d),
        fresh(d) && readwrite(d) && Mux(nativeGdn,fresh(y) && readwrite(y),Mux(coreRecurrent,fresh(x) && readwrite(x),true.B)))
    }else if(bf16Gdn){
      val hin=tensors(3);val hout=tensors(4);val program=policy(0);val gp=policy(1);val gr=policy(2)
      val cold=gp(80);val generation=gp(119,88)
      val allIndices=tensors.flatMap(_.prefixIndices)++policyIndices.take(3)
      val projectionIndices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(3)
      val allDistinct=(for(i<-allIndices.indices;j<-i+1 until allIndices.size)yield allIndices(i)=/=allIndices(j)).reduce(_&&_)
      val projectionDistinct=(for(i<-projectionIndices.indices;j<-i+1 until projectionIndices.size)yield projectionIndices(i)=/=projectionIndices(j)).reduce(_&&_)
      gdnDistinct:=Mux(gdnCommand,allDistinct,projectionDistinct)
      gdnProjection:=opcode===0x20.U && m>0.U && m<=s.maxTokens.U && m<=128.U &&
        shape2(a,m,1024.U) && shape2(b,1024.U,6144.U) && shape2(d,m,6144.U) &&
        Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && b.tail===0xffffff.U && d.tail===0xffffff.U &&
        policy(0)(127,56)===(m.pad(72)|(6144.U(72.W)<<16)|(1024.U(72.W)<<32)) &&
        policy(1)(127,56)==="h004000040020ffffff".U(72.W) &&
        finishRecord(policy(2),0x21.U) && policy(2)(127,56)===0x201.U
      val programOK=program(7,0)===0x20.U && program(55,32)=/=0xffffff.U &&
        program(71,56)===0x30.U && program(79,72)===2.U && program(87,80)===1.U &&
        program(91,88)===5.U && program(95,92)===5.U && program(103,96)===16.U && program(111,104)===1.U && program(127,112)===0.U
      val policyOK=gp(7,0)===0x21.U && gp(55,32)=/=0xffffff.U && gp(63,56)===1.U && gp(71,64)===1.U &&
        gp(79,72)===0.U && gp(87,81)===0.U && gp(127,120)===0.U && finishRecord(gr,0x22.U) && gr(127,104)===0.U
      nativeGdn:=gdnCommand && m>0.U && m<=s.maxTokens.U && m<=128.U &&
        shape2(a,m,6144.U) && shape2(b,6144.U,4.U) && shape2(d,m,6144.U) &&
        shape2(hin,6144.U,4.U) && shape2(hout,6144.U,4.U) && tensors.map(_.dtype===5.U).reduce(_&&_) &&
        Seq(b,d,hin,hout).map(_.tail===0xffffff.U).reduce(_&&_) && programOK && policyOK
      val initialState=generation===0.U && (cold || readonly(hin))
      val carriedState= !cold && generation===currentGeneration && hin.address===currentHistoryAddress && hin.paddedEnd===currentHistoryEnd
      gdnLive:=live(a) && live(b) && generation=/="hffffffff".U && Mux(stateValid,carriedState,initialState)
      // Public GDN tensor ranges are pairwise disjoint, including readonly
      // inputs and cold history whose contents will not be consumed.
      val operands=Seq(a,b,d,hin,hout)
      val disjoint=(for(i<-operands.indices;j<-i+1 until operands.size)yield
        !overlap(operands(i).address,operands(i).paddedEnd,operands(j).address,operands(j).paddedEnd)).reduce(_&&_)
      gdnFresh:=disjoint && fresh(d) && fresh(hout) && readwrite(d) && readwrite(hout)
    }
    // Runtime RMS validation is independent of legacy constructor branches.
    // No readonly/preloaded lookalike can satisfy postnorm's residual producer.
    val rn=policy(1);val rp=policy(0);val rnRole=rn(84,82)
    val rnCold=rn(80);val rnGeneration=rn(119,88)
    val rnProgram=rp(7,0)===0x20.U && rp(31,8)===0.U && rp(55,32)=/=0xffffff.U &&
      rp(71,56)===0x30.U && rp(79,72)===2.U && rp(87,80)===1.U &&
      rp(91,88)===5.U && rp(95,92)===5.U && rp(103,96)===16.U &&
      rp(111,104)===1.U && rp(127,112)===0.U
    val rnPolicy=finishRecord(rn,0x21.U) && rn(63,56)===3.U && rn(71,64)===8.U &&
      rn(79,72)===0.U && rn(81)=== !rnCold && rnRole<=1.U && rn(87,85)===0.U &&
      rnGeneration=/="hffffffff".U && rn(127,120)===0.U
    val runtimeNorm=runtimeNormCommand && group===0.U && rnProgram && rnPolicy &&
      m===128.U && shape2(a,m,runtimeNormHidden) &&
      shape2(b,1.U,runtimeNormHidden) && shape2(d,m,runtimeNormHidden) &&
      Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U
    val rnIndices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(2)
    val rnDistinct=(for(i<-rnIndices.indices;j<-i+1 until rnIndices.size)yield rnIndices(i)=/=rnIndices(j)).reduce(_&&_)
    val rnCheckpointValid=Mux(runtimeGdnProfile,stateValid,attentionCacheValid)
    // Cold M<=128 migration only: persistent weight/state/KV checkpoint
    // installation is not yet unified. Do not authenticate carried generation
    // merely because an old constructor-local generation register matches.
    val rnInitialContext=rnCold && rnGeneration===0.U && !rnCheckpointValid
    val rnSameContext=rnCold===txCold && rnGeneration===txGeneration && sourceValid(0) &&
      sourceTensor(0).dims(0)===m && sourceTensor(0).dims(1)===runtimeNormHidden
    // The input's policy tail intentionally differs from its producer's
    // output tail; bind the complete numerical allocation, not descriptor IDs.
    val rnResidual=txResidual1Valid && sameAllocation(a,txResidual1Tensor) && readwrite(a)
    val rnAttentionResidual=attentionBlockValid(4) && sameAllocation(a,attentionBlockValues(4))
    val rnInputProducer=rnRole===0.U && !txInputValid && !txInputNormValid && rnInitialContext &&
      readonly(a) && sourceAllowed(a,0.U)
    val rnPostProducer=enableRuntimeOutput.B && rnRole===1.U && !txPostNormValid &&
      !postnormDonePending && !postnormCommitValid && rnCold && rnGeneration===0.U &&
      !rnCheckpointValid && rnSameContext && rnResidual &&
      Mux(runtimeGdnProfile,true.B,rnAttentionResidual)
    val rnWeightRole=Mux(runtimeGdnProfile,Mux(rnRole===0.U,10.U,12.U),Mux(rnRole===0.U,7.U,9.U))
    val rnGammaIdentity= !sourceValid(rnWeightRole) || sameAllocation(b,sourceTensor(rnWeightRole))
    val rnLive=live(a) && live(b) && readonly(b) && sourceAllowed(b,rnWeightRole) && rnGammaIdentity &&
      (rnInputProducer || rnPostProducer)
    val rnFresh=fresh(d) && readwrite(d) &&
      !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd) &&
      !overlap(a.address,a.paddedEnd,d.address,d.paddedEnd) &&
      !overlap(b.address,b.paddedEnd,d.address,d.paddedEnd)
    // First three real GDN QKV/Z/AB or Attention Q/K/V projections share the existing Dense service.
    // These flags/addresses originate only in typed records + actual prior ACK.
    val rd=policy(2);val rdRole=rd(84,82)
    val rdGdnWidth=Mux(rdRole===0.U,
      ((runtimeProfile.gdnKeyHeads*runtimeProfile.gdnKeyDim)<<1)+(runtimeProfile.gdnValueHeads*runtimeProfile.gdnValueDim),
      Mux(rdRole===1.U,runtimeProfile.gdnValueHeads*runtimeProfile.gdnValueDim,runtimeProfile.gdnValueHeads<<1))
    val rdAttentionWidth=Mux(rdRole===0.U,(runtimeProfile.attentionHeads.pad(16)<<9),512.U(16.W))
    val rdWidth=Mux(runtimeGdnProfile,rdGdnWidth,rdAttentionWidth)
    val rdMatrix=policy(0)(7,0)===0x10.U && policy(0)(31,8)===0.U && policy(0)(55,32)=/=0xffffff.U &&
      policy(0)(127,56)===(m.pad(72)|(rdWidth.pad(72)<<16)|(runtimeNormHidden.pad(72)<<32)) &&
      policy(1)(7,0)===0x12.U && policy(1)(31,8)===0.U && policy(1)(55,32)=/=0xffffff.U &&
      policy(1)(127,56)==="h004000040020ffffff".U(72.W)
    val rdPolicy=finishRecord(rd,0x21.U) && rd(63,56)===3.U && rd(71,64)===2.U &&
      rd(79,72)===0.U && rd(81)=== !rd(80) && rdRole<=2.U && rd(87,85)===0.U &&
      rd(119,88)===txGeneration && rd(80)===txCold && rd(127,120)===0.U
    val runtimeDenseProjection=runtimeProjectionCommand && group===0.U && rdMatrix && rdPolicy &&
      m>0.U && m<=128.U && shape2(a,m,runtimeNormHidden) && shape2(b,runtimeNormHidden,rdWidth) &&
      shape2(d,m,rdWidth) && Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U
    val rdGdnOrder=MuxLookup(rdRole,false.B)(Seq(
      0.U->(!txQkvValid && !txZValid && !txAbValid),
      1.U->(txQkvValid && !txZValid && !txAbValid),
      2.U->(txQkvValid && txZValid && !txAbValid)))
    val rdAttentionOrder=MuxLookup(rdRole,false.B)(Seq(
      0.U->(!qkProjectedValid.asUInt.orR),
      1.U->(qkProjectedValid(0) && !qkProjectedValid(1) && !qkProjectedValid(2)),
      2.U->(qkProjectedValid(0) && qkProjectedValid(1) && !qkProjectedValid(2))))
    val rdOrder=Mux(runtimeGdnProfile,rdGdnOrder,rdAttentionOrder)
    val rdIndices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(3)
    val rdDistinct=(for(i<-rdIndices.indices;j<-i+1 until rdIndices.size)yield rdIndices(i)=/=rdIndices(j)).reduce(_&&_)
    val rdLive=txInputValid && txInputNormValid && sameAllocation(a,runtimeInputNormTensor) &&
      txCold && txGeneration===0.U && rdOrder && live(a) && live(b) && readonly(b) && sourceAllowed(b,rdRole+1.U)
    val rdFresh=fresh(d) && readwrite(d) &&
      !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd) &&
      !overlap(a.address,a.paddedEnd,d.address,d.paddedEnd) &&
      !overlap(b.address,b.paddedEnd,d.address,d.paddedEnd)
    // Actual cold runtime Conv consumes the exact completed QKV tensor and
    // validated weights/history spans. Readonly data cannot impersonate QKV.
    val rcChannels=((runtimeProfile.gdnKeyHeads*runtimeProfile.gdnKeyDim)<<1)+
      runtimeProfile.gdnValueHeads*runtimeProfile.gdnValueDim
    val rhIn=tensors(3);val rhOut=tensors(4);val rh=policy(2)
    val rcPolicy=rn(7,0)===0x21.U && rn(31,8)===0.U && rn(55,32)=/=0xffffff.U &&
      rn(63,56)===3.U && rn(71,64)===1.U && rn(79,72)===0.U &&
      rnCold && !rn(81) && rn(87,82)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val rcHistory=finishRecord(rh,0x22.U) && rh(127,104)===0.U
    val runtimeConv=runtimeNormCommand && runtimeGdnProfile && group===0.U && rnProgram && rcPolicy && rcHistory &&
      m>=1.U && m<=128.U && (rcChannels===6144.U || rcChannels===8192.U) &&
      shape2(a,m,rcChannels) && shape2(b,rcChannels,4.U) && shape2(d,m,rcChannels) &&
      shape2(rhIn,rcChannels,4.U) && shape2(rhOut,rcChannels,4.U) &&
      tensors.map(_.dtype===5.U).reduce(_&&_) && Seq(b,d,rhIn,rhOut).map(_.tail===0xffffff.U).reduce(_&&_)
    val rcIndices=tensors.flatMap(_.prefixIndices)++policyIndices.take(3)
    val rcDistinct=(for(i<-rcIndices.indices;j<-i+1 until rcIndices.size)yield rcIndices(i)=/=rcIndices(j)).reduce(_&&_)
    val rcLive=txInputNormValid && txQkvValid && txZValid && txAbValid && !txConvValid &&
      sameAllocation(a,runtimeProjectionTensors(0)) && live(a) && live(b) && live(rhIn) &&
      readonly(b) && readonly(rhIn) && sourceAllowed(b,4.U) && sourceAllowed(rhIn,8.U) &&
      txCold && txGeneration===0.U && !stateValid
    val rcOperands=Seq(a,b,d,rhIn,rhOut)
    val rcFresh=(for(i<-rcOperands.indices;j<-i+1 until rcOperands.size)yield
      !overlap(rcOperands(i).address,rcOperands(i).paddedEnd,rcOperands(j).address,rcOperands(j).paddedEnd)).reduce(_&&_) &&
      fresh(d) && fresh(rhOut) && readwrite(d) && readwrite(rhOut)
    // RawPrep consumes EXACT completed Conv and AB tensors. A_log and
    // dtBias are real typed readonly records; their values are read by owner.
    val prepHeads=runtimeProfile.gdnValueHeads
    val prepProgram=rp(7,0)===0x20.U && rp(31,8)===0.U && rp(55,32)=/=0xffffff.U &&
      rp(71,56)===0x30.U && rp(79,72)===2.U && rp(87,80)===1.U &&
      rp(91,88)===5.U && rp(95,92)===7.U && rp(103,96)===16.U &&
      rp(111,104)===1.U && rp(127,112)===0.U
    val prepPolicy=rn(7,0)===0x21.U && rn(31,8)===0.U && rn(55,32)=/=0xffffff.U &&
      rn(63,56)===3.U && rn(71,64)===3.U && rn(79,72)===0.U &&
      rnCold && !rn(81) && rn(87,82)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val prepInputs=finishRecord(rh,0x23.U) && rh(127,104)===0.U
    val runtimePrep=runtimeNormCommand && runtimeGdnProfile && group===0.U && prepProgram && prepPolicy && prepInputs &&
      m>=1.U && m<=128.U && (prepHeads===16.U || prepHeads===32.U) &&
      shape2(a,m,rcChannels) && shape2(b,m,prepHeads<<1) && shape2(d,m,prepHeads*400.U) &&
      shape2(rhIn,1.U,prepHeads) && shape2(rhOut,1.U,prepHeads) &&
      a.dtype===5.U && b.dtype===5.U && d.dtype===7.U && rhIn.dtype===7.U && rhOut.dtype===5.U &&
      Seq(b,d,rhIn,rhOut).map(_.tail===0xffffff.U).reduce(_&&_)
    val prepLive=txConvValid && txAbValid && !txPrepValid && txCold && txGeneration===0.U && !stateValid &&
      sameAllocation(a,runtimeConvTensor) && sameAllocation(b,runtimeProjectionTensors(2)) &&
      Seq(a,b,rhIn,rhOut).map(live).reduce(_&&_) && readonly(rhIn) && readonly(rhOut) &&
      sourceAllowed(rhIn,5.U) && sourceAllowed(rhOut,6.U)
    val prepFresh=(for(i<-rcOperands.indices;j<-i+1 until rcOperands.size)yield
      !overlap(rcOperands(i).address,rcOperands(i).paddedEnd,rcOperands(j).address,rcOperands(j).paddedEnd)).reduce(_&&_) &&
      fresh(d) && readwrite(d)
    // Runtime Chunk op4 uses the SAME five typed operands and original decoder.
    // A=actual RawPrep, B=cold state source, D=BF16 output, extras=stateOut/scratch.
    val chunkStride=Mux(m===128.U,1679360.U(32.W),872448.U(32.W))
    // SHAPE4 dimensions are18-bit. M128's419840 FP32 words/head cannot be
    // encoded as one dimension; rank3 preserves exactly128*3280 words/head.
    // This changes descriptor geometry only, not physical scratch layout/size.
    val chunkScratchShape=Mux(m===128.U,shape3(rhOut,prepHeads,128.U,3280.U),
      shape2(rhOut,prepHeads,chunkStride>>2))
    val chunkProgram=rp(7,0)===0x20.U && rp(31,8)===0.U && rp(55,32)=/=0xffffff.U &&
      rp(71,56)===0x30.U && rp(79,72)===2.U && rp(87,80)===1.U &&
      rp(91,88)===7.U && rp(95,92)===5.U && rp(103,96)===16.U &&
      rp(111,104)===1.U && rp(127,112)===0.U
    val chunkPolicy=rn(7,0)===0x21.U && rn(31,8)===0.U && rn(55,32)=/=0xffffff.U &&
      rn(63,56)===3.U && rn(71,64)===4.U && rn(79,72)===0.U &&
      rnCold && !rn(81) && rn(87,82)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val runtimeChunk=runtimeNormCommand && runtimeGdnProfile && group===0.U && chunkProgram && chunkPolicy && prepInputs &&
      (m===16.U || m===128.U) && (prepHeads===16.U || prepHeads===32.U) &&
      shape2(a,m,prepHeads*400.U) && shape2(b,prepHeads,16384.U) && shape2(d,m,prepHeads*128.U) &&
      shape2(rhIn,prepHeads,16384.U) && chunkScratchShape &&
      a.dtype===7.U && b.dtype===7.U && d.dtype===5.U && rhIn.dtype===7.U && rhOut.dtype===7.U &&
      Seq(b,d,rhIn,rhOut).map(_.tail===0xffffff.U).reduce(_&&_)
    val chunkLive=txPrepValid && !txRecurrentValid && txConvValid && txCold && txGeneration===0.U && !stateValid &&
      sameAllocation(a,runtimePrepTensor) && live(a) && live(b) && readonly(b) && sourceAllowed(b,9.U)
    val chunkFresh=(for(i<-rcOperands.indices;j<-i+1 until rcOperands.size)yield
      !overlap(rcOperands(i).address,rcOperands(i).paddedEnd,rcOperands(j).address,rcOperands(j).paddedEnd)).reduce(_&&_) &&
      Seq(d,rhIn,rhOut).map(t=>fresh(t) && readwrite(t)).reduce(_&&_)
    // GatedNorm op5 consumes exact completed Chunk and Z allocations, never a
    // readonly lookalike. Gamma is the original FP32[128] (no 1+gamma).
    // Its PROGRAM/POLICY/INPUTS route is the original typed decoder, not an
    // externally injected success receipt or another qualification wrapper.
    val gatedWidth=prepHeads*128.U
    val gatedPolicy=rn(7,0)===0x21.U && rn(31,8)===0.U && rn(55,32)=/=0xffffff.U &&
      rn(63,56)===3.U && rn(71,64)===5.U && rn(79,72)===0.U &&
      rnCold && !rn(81) && rn(87,82)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val gatedInputs=finishRecord(rh,0x23.U) && rh(103,80)===0xffffff.U && rh(127,104)===0.U
    val runtimeGatedNorm=runtimeNormCommand && runtimeGdnProfile && group===0.U && rnProgram && gatedPolicy && gatedInputs &&
      (m===16.U || m===128.U) && (prepHeads===16.U || prepHeads===32.U) &&
      shape2(a,m,gatedWidth) && shape2(b,m,gatedWidth) && shape2(d,m,gatedWidth) &&
      shape2(rhIn,1.U,128.U) && Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && rhIn.dtype===7.U &&
      Seq(b,d,rhIn).map(_.tail===0xffffff.U).reduce(_&&_)
    val gatedIndices=tensors.take(4).flatMap(_.prefixIndices)++policyIndices.take(3)
    val gatedDistinct=(for(i<-gatedIndices.indices;j<-i+1 until gatedIndices.size)yield gatedIndices(i)=/=gatedIndices(j)).reduce(_&&_)
    val gatedLive=txInputNormValid && txConvValid && txPrepValid && txRecurrentValid && txZValid && !txNormValid &&
      txCold && txGeneration===0.U && !stateValid &&
      sameAllocation(a,runtimeChunkTensor) && sameAllocation(b,runtimeProjectionTensors(1)) &&
      Seq(a,b,rhIn).map(live).reduce(_&&_) && readonly(rhIn) && sourceAllowed(rhIn,7.U)
    val gatedOperands=Seq(a,b,d,rhIn)
    val gatedFresh=(for(i<-gatedOperands.indices;j<-i+1 until gatedOperands.size)yield
      !overlap(gatedOperands(i).address,gatedOperands(i).paddedEnd,gatedOperands(j).address,gatedOperands(j).paddedEnd)).reduce(_&&_) &&
      fresh(d) && readwrite(d)
    // Real output continuation: original GDN Add and Attention SigmoidMul
    // policies, one common runtime Elementwise owner and the EXISTING Dense.
    // No readonly/preloaded tensor can substitute for any completed producer.
    val outputWidth=Mux(runtimeGdnProfile,gatedWidth,runtimeProfile.attentionHeads.pad(16)<<8)
    val outputRows=Mux(runtimeGdnProfile,m===16.U || m===128.U,m===128.U)
    val outputContext=txCold && txGeneration===0.U && !rnCheckpointValid && sourceValid(0) &&
      sourceTensor(0).dims(0)===m && sourceTensor(0).dims(1)===runtimeNormHidden
    val roMatrix=policy(0)(7,0)===0x10.U && policy(0)(31,8)===0.U && policy(0)(55,32)=/=0xffffff.U &&
      policy(0)(127,56)===(m.pad(72)|(runtimeNormHidden.pad(72)<<16)|(outputWidth.pad(72)<<32)) &&
      policy(1)(7,0)===0x12.U && policy(1)(31,8)===0.U && policy(1)(55,32)=/=0xffffff.U &&
      policy(1)(127,56)==="h004000040020ffffff".U(72.W)
    val roPolicy=finishRecord(rd,0x21.U) && rd(63,56)===3.U && rd(71,64)===2.U &&
      rd(79,72)===0.U && rd(80) && !rd(81) && rdRole===3.U && rd(87,85)===0.U &&
      rd(119,88)===0.U && rd(127,120)===0.U
    val runtimeDenseO=enableRuntimeOutput.B && runtimeProjectionCommand && group===0.U &&
      roMatrix && roPolicy && outputRows && shape2(a,m,outputWidth) &&
      shape2(b,outputWidth,runtimeNormHidden) && shape2(d,m,runtimeNormHidden) &&
      Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && b.tail===0xffffff.U && d.tail===0xffffff.U
    val roLive=outputContext && !txOValid && live(a) && live(b) && readonly(b) &&
      sourceAllowed(b,Mux(runtimeGdnProfile,11.U,8.U)) && Mux(runtimeGdnProfile,
        txNormValid && sameAllocation(a,runtimeGatedNormTensor),
        attentionBlockValid(2) && sameAllocation(a,attentionBlockValues(2)))
    val reGdnPolicy=finishRecord(rn,0x21.U) && rn(63,56)===3.U && rn(71,64)===9.U &&
      rn(79,72)===0.U && rnCold && !rn(81) && rnRole===0.U && rn(87,85)===0.U &&
      rnGeneration===0.U && rn(127,120)===0.U
    val runtimeGdnResidual=enableRuntimeOutput.B && runtimeNormCommand && runtimeGdnProfile &&
      group===0.U && rnProgram && reGdnPolicy && outputRows &&
      Seq(a,b,d).map(t=>t.dtype===5.U && shape2(t,m,runtimeNormHidden)).reduce(_&&_) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U
    val reProgram=rp(7,0)===0x20.U && rp(31,8)===0.U && rp(55,32)=/=0xffffff.U &&
      rp(71,56)===0x30.U && rp(79,72)===2.U && rp(87,80)===1.U &&
      rp(91,88)===5.U && rp(95,92)===5.U && rp(103,96)===16.U && rp(127,104)===0.U
    val reAttentionPolicy=cp(7,0)===0x24.U && cp(31,8)===0.U && cp(55,32)=/=0xffffff.U &&
      cp(63,56)===3.U && attentionOp===7.U && attentionBase===0.U && attentionCount===128.U &&
      cp(115,108)===0.U && attentionBlockRole<=1.U && cp(127,119)===0.U
    val reAttentionContext=finishRecord(cx,0x26.U) && cx(63,56)===2.U && cx(127,125)===0.U && cx(124) &&
      attentionCapacity===128.U && attentionCold && attentionExpectedLength===0.U &&
      attentionExpectedGeneration===0.U && attentionQueryStart===0.U
    val reWidth=Mux(attentionBlockRole===0.U,outputWidth,runtimeNormHidden)
    val runtimeAttentionElement=enableRuntimeOutput.B && runtimeAttentionProfile && runtimeAttentionOutputPolicy &&
      runtimeNormCommand && group===0.U && reProgram && reAttentionPolicy && reAttentionContext && m===128.U &&
      Seq(a,b,d).map(t=>t.dtype===5.U && shape2(t,m,reWidth)).reduce(_&&_) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U
    val rePending=outputContext && pendingAttentionValid && pendingGqaValid && pendingAttentionCold &&
      pendingAttentionOldLength===0.U && pendingAttentionGeneration===0.U && pendingAttentionBase===0.U &&
      pendingAttentionCount===128.U && pendingAttentionLength===128.U && pendingAttentionCache.dims(1)===128.U
    val reGateLive=rePending && attentionBlockValid(1) && !attentionBlockValid(2) &&
      sameAllocation(a,attentionBlockValues(1)) && sameAllocation(b,pendingAttentionContext) && live(a) && live(b)
    val reResidualLive=outputContext && txOValid && !txResidual1Valid &&
      sameAllocation(a,sourceTensor(0)) && sameAllocation(b,runtimeOTensor) && live(a) && live(b)
    val runtimeElementwise=runtimeGdnResidual || runtimeAttentionElement
    val reLive=Mux(runtimeGdnResidual,reResidualLive,
      Mux(attentionBlockRole===0.U,reGateLive,rePending && reResidualLive))
    val reIndices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(3)
    val reDistinct=(for(i<-reIndices.indices;j<-i+1 until reIndices.size)yield
      ((i==11 || j==11).B && runtimeGdnResidual) || reIndices(i)=/=reIndices(j)).reduce(_&&_)
    // Actual Dense0.8 FFN, using the original Matrix op/AUX + v3 POLICY
    // roles4/5/6 and original Elementwise op9 roles1/2. Only runtime geometry
    // changes: no Qwen2 resident H1536/F8960 or FP32 storage policy is reused.
    val runtimeFfnProfile=enableRuntimeOutput.B && (cfg.profileId===1.U || cfg.profileId===2.U)
    val ffnContext=runtimeFfnProfile && outputContext && outputRows && txPostNormValid &&
      postnormCommitValid && postnormCurrent && postnormJob.m===m && postnormJob.n===1024.U &&
      postnormJob.k===1024.U && postnormJob.qkRole===3.U
    val ffnPostSource=io.runtimePostnormReceipt.valid &&
      io.runtimePostnormReceipt.bits.asUInt===postnormPhysicalReceipt.asUInt &&
      postnormPhysicalReceipt.host.asUInt===cfg.asUInt &&
      postnormPhysicalReceipt.transactionId===runtimeTransaction &&
      sameAllocation(a,postnormOutputTensor) && readwrite(a)
    def ffnTensor(t:DecodedTensor,rows:UInt,cols:UInt):Bool={
      val count=rows.pad(64)*cols.pad(64)
      t.dtype===5.U && shape2(t,rows,cols) && t.elementCount===count &&
        t.payloadBytes===(count<<1) && t.address(5,0)===0.U &&
        t.paddedEnd.pad(80)===t.address.pad(80)+(count.pad(80)<<1)
    }
    val ffnDown=rdRole===6.U
    val ffnK=Mux(ffnDown,3584.U(16.W),1024.U(16.W))
    val ffnN=Mux(ffnDown,1024.U(16.W),3584.U(16.W))
    val ffnMatrix=policy(0)(7,0)===0x10.U && policy(0)(31,8)===0.U && policy(0)(55,32)=/=0xffffff.U &&
      policy(0)(127,56)===(m.pad(72)|(ffnN.pad(72)<<16)|(ffnK.pad(72)<<32)) &&
      policy(1)(7,0)===0x12.U && policy(1)(31,8)===0.U && policy(1)(55,32)=/=0xffffff.U &&
      policy(1)(127,56)==="h004000040020ffffff".U(72.W)
    val ffnDensePolicy=finishRecord(rd,0x21.U) && rd(63,56)===3.U && rd(71,64)===2.U &&
      rd(79,72)===0.U && rd(80) && !rd(81) && rdRole>=4.U && rdRole<=6.U &&
      rd(87,85)===0.U && rd(119,88)===0.U && rd(127,120)===0.U
    val runtimeFfnDense=runtimeFfnProfile && runtimeProjectionCommand && group===0.U &&
      ffnMatrix && ffnDensePolicy && outputRows && ffnTensor(a,m,ffnK) &&
      ffnTensor(b,ffnK,ffnN) && ffnTensor(d,m,ffnN) && b.tail===0xffffff.U && d.tail===0xffffff.U
    val ffnWeightRole=Mux(runtimeGdnProfile,rdRole+9.U,rdRole+6.U)
    val ffnWeightIdentity= !sourceValid(ffnWeightRole) || sameAllocation(b,sourceTensor(ffnWeightRole))
    val ffnDenseOrder=MuxLookup(rdRole,false.B)(Seq(
      4.U->(!txGateValid && !txUpValid && !txSiluValid && !txDownValid && !txResidual2Valid && ffnPostSource),
      5.U->(txGateValid && !txUpValid && !txSiluValid && !txDownValid && !txResidual2Valid && ffnPostSource),
      6.U->(txGateValid && txUpValid && txSiluValid && !txDownValid && !txResidual2Valid &&
        sameAllocation(a,runtimeFfnTensors(2)) && readwrite(a))))
    val ffnDenseLive=ffnContext && ffnDenseOrder && live(a) && live(b) && readonly(b) &&
      sourceAllowed(b,ffnWeightRole) && ffnWeightIdentity
    val ffnSilu=rnRole===1.U
    val ffnElementWidth=Mux(ffnSilu,3584.U(16.W),1024.U(16.W))
    val ffnElementPolicy=finishRecord(rn,0x21.U) && rn(63,56)===3.U && rn(71,64)===9.U &&
      rn(79,72)===0.U && rnCold && !rn(81) && rnRole>=1.U && rnRole<=2.U &&
      rn(87,85)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val runtimeFfnElement=runtimeFfnProfile && runtimeNormCommand && group===0.U &&
      rnProgram && ffnElementPolicy && outputRows &&
      Seq(a,b,d).map(t=>ffnTensor(t,m,ffnElementWidth)).reduce(_&&_) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U
    val ffnElementOrder=Mux(ffnSilu,
      txGateValid && txUpValid && !txSiluValid && !txDownValid && !txResidual2Valid &&
        sameAllocation(a,runtimeFfnTensors(0)) && sameAllocation(b,runtimeFfnTensors(1)),
      txGateValid && txUpValid && txSiluValid && txDownValid && !txResidual2Valid && txResidual1Valid &&
        sameAllocation(a,txResidual1Tensor) && sameAllocation(b,runtimeFfnTensors(3)))
    val ffnElementLive=ffnContext && ffnElementOrder && live(a) && live(b) && readwrite(a) && readwrite(b)
    val runtimeFfn=runtimeFfnDense || runtimeFfnElement
    val ffnElementDistinct=(for(i<-rnIndices.indices;j<-i+1 until rnIndices.size)yield rnIndices(i)=/=rnIndices(j)).reduce(_&&_)
    val runtimeQkNorm=runtimeQkNormCommand && nativeQkNorm
    val runtimeRope=runtimeRopeCommand && nativePartialRope
    val runtimeKvAppend=runtimeKvAppendCommand && attentionAppend
    val runtimeGqa=runtimeGqaCommand && (attentionQk || attentionSoft || attentionPv)
    // ORIGINAL terminal fence policies, now selected by runtime profile rather
    // than legacy per-model elaboration flags. No arithmetic job is generated.
    val finalRows=runtimeFinalTensor.dims(0)
    val finalCommon=enableRuntimeOutput.B && runtimeNormCommand && group===0.U &&
      runtimeAccepted && cfg.version===HostCommandLaunchV4.Version.U &&
      !runtimeCheckpointCommitted && txCold && txGeneration===0.U &&
      sourceValid(0) && txInputNormValid && txOValid && txResidual1Valid && txPostNormValid &&
      txResidual2Valid && finalRows===128.U &&
      shape2(d,finalRows,runtimeNormHidden) && d.dtype===5.U &&
      sameAllocation(d,runtimeFinalTensor) && live(d) && readwrite(d) &&
      b.tail===0xffffff.U && d.tail===0xffffff.U &&
      sourceTensor(0).dims(0)===finalRows && sourceTensor(0).dims(1)===runtimeNormHidden
    val finalGdnPolicy=rnProgram && finishRecord(rn,0x21.U) && rn(63,56)===3.U &&
      rn(71,64)===6.U && rn(79,72)===0.U && rnCold && !rn(81) &&
      rn(87,82)===0.U && rnGeneration===0.U && rn(127,120)===0.U
    val runtimeGdnFence=finalCommon && runtimeGdnProfile && finalGdnPolicy &&
      txConvValid && txPrepValid && txRecurrentValid && txNormValid && !stateValid &&
      sameAllocation(a,runtimeHistoryTensor) && sameAllocation(b,runtimeStateTensor) &&
      a.address===pendingHistoryAddress && a.paddedEnd===pendingHistoryEnd &&
      b.address===pendingStateAddress && b.paddedEnd===pendingStateEnd &&
      a.dtype===5.U && b.dtype===7.U && live(a) && live(b) && readwrite(a) && readwrite(b)
    val finalAttentionPolicy=reProgram && cp(7,0)===0x24.U && cp(31,8)===0.U &&
      cp(55,32)=/=0xffffff.U && cp(63,56)===3.U && attentionOp===4.U &&
      attentionBase===0.U && attentionCount===128.U && cp(127,108)===0.U && reAttentionContext
    val runtimeAttentionFence=finalCommon && runtimeAttentionProfile && runtimeAttentionOutputPolicy && finalAttentionPolicy &&
      !attentionCacheValid && pendingAttentionValid && pendingGqaValid &&
      qkProjectedValid.asUInt.andR && qkNormalizedValid.asUInt.andR && qkRotatedValid.asUInt.andR &&
      attentionBlockValid(2) && attentionBlockValid(3) && attentionBlockValid(4) && attentionBlockValid(5) &&
      pendingAttentionCold && pendingAttentionGeneration===0.U && pendingAttentionOldLength===0.U &&
      pendingAttentionBase===0.U && pendingAttentionCount===128.U && pendingAttentionLength===128.U &&
      sameAllocation(a,pendingAttentionCache) && sameAllocation(b,sourceTensor(0)) &&
      readwrite(a) && readonly(b) && live(b) && a.dtype===5.U && b.dtype===5.U
    val runtimeFence=runtimeGdnFence || runtimeAttentionFence
    val fenceIndices=tensors.take(3).flatMap(_.prefixIndices)++policyIndices.take(3)
    val fenceDistinct=(for(i<-fenceIndices.indices;j<-i+1 until fenceIndices.size)yield
      (runtimeGdnFence && (i==11 || j==11).B) || fenceIndices(i)=/=fenceIndices(j)).reduce(_&&_)
    val fenceDisjoint= !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd) &&
      !overlap(a.address,a.paddedEnd,d.address,d.paddedEnd) && !overlap(b.address,b.paddedEnd,d.address,d.paddedEnd)
    val runtimePrefix=runtimeFence || runtimeNorm || runtimeDenseProjection || runtimeConv || runtimePrep || runtimeChunk || runtimeGatedNorm || runtimeQkNorm || runtimeRope || runtimeKvAppend || runtimeGqa || runtimeDenseO || runtimeElementwise || runtimeFfn
    val supportedOrdinary=(validDTypes||nativeQkNorm||nativePartialRope) && plainTails && (!s.projectionOnly.B || nativeProjection||nativeQkNorm||nativePartialRope) &&
      (!extendedProjection || nativeProjection) && (nativeProjection||nativeQkNorm||nativePartialRope||norm||dense||vector||rope||activation||append||qk||sm||pv)
    val residentGate=if(enableResidentFfn)!resident.get.inGroup && group===0.U && dense &&
      (m===16.U || m===128.U) && a.dims(1)===1536.U && n===8960.U && nativeWeight else false.B
    val residentUp=if(enableResidentFfn)resident.get.inGroup && group===1.U else false.B
    val residentAct=if(enableResidentFfn)resident.get.inGroup && group===2.U else false.B
    val residentShape=if(enableResidentFfn)Mux(residentUp,dense && m===q.dims(0) && a.dims(1)===1536.U && n===8960.U && nativeWeight,
      Mux(residentAct,activation && m===q.dims(0) && n===8960.U,true.B))else true.B
    val residentFresh=if(enableResidentFfn){
      val operands=Seq(q,k,resident.get.upWeight,score,probability,d)
      val allDisjoint=(for(i<-operands.indices;j<-i+1 until operands.size)yield
        !overlap(operands(i).address,operands(i).paddedEnd,operands(j).address,operands(j).paddedEnd)).reduce(_&&_)
      val upDisjoint=Seq(q,k,score,b,d)
      val upOK=(for(i<-upDisjoint.indices;j<-i+1 until upDisjoint.size)yield
        !overlap(upDisjoint(i).address,upDisjoint(i).paddedEnd,upDisjoint(j).address,upDisjoint(j).paddedEnd)).reduce(_&&_)
      Mux(residentGate,readwrite(d)&&readonly(b)&& !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd),
        Mux(residentUp,readwrite(d)&&readonly(b)&&upOK,Mux(residentAct,readwrite(d)&&allDisjoint,true.B)))
    }else true.B
    val coreOperation=corePrep || coreRecurrent || coreNorm || coreFence || blockRmsNorm || blockElementwise
    val publicationSlots=Mux(runtimeFence||coreFence||attentionFence||attentionAppend,0.U,Mux(nativeGdn || runtimeConv || runtimeChunk || coreRecurrent || (nativeQkNorm && qkRole===0.U),2.U,1.U))
    val projectionOrder=Mux(role===0.U,!qkProjectedValid.asUInt.orR,
      Mux(role===1.U,qkProjectedValid(0) && !qkProjectedValid(1) && !qkProjectedValid(2),
        qkProjectedValid(0) && qkProjectedValid(1) && !qkProjectedValid(2)))
    val qkProjectionLive=(!bf16AttentionCore.B || projectionOrder) && sourceLive &&
      Mux(bf16AttentionBlock.B,attentionBlockValid(0) && sameAllocation(a,attentionBlockValues(0)),readonly(a) && sourceAllowed(a,0.U)) &&
      readonly(b) && sourceAllowed(b,role+1.U) &&
      !qkProjectedValid(role) && !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd) &&
      (0 until 3).map(i=> !qkProjectedValid(i) || (qkRows(i)===m && qkWindowBase(i)===tokenBase && qkWindowCount(i)===tokenCount)).reduce(_&&_)
    val qkProjectionFresh=noAlias && fresh(d) && readwrite(d)
    val initialValidation=if(enableResidentFfn)when(!residentShape){fail(Status.Unsupported.U)}
    .elsewhen(!residentFresh || ((residentGate || residentUp || residentAct) && virtualCount+&2.U>maxCommands.U)){fail(Status.Permission.U)}
    .elsewhen(!Mux(runtimeNormProfile,runtimePrefix,Mux(s.qwen35GdnOnly.B,nativeGdn||gdnProjection||coreOperation,Mux(attentionCommandPolicy,nativeAttention,supportedOrdinary)))){fail(Status.Unsupported.U)}
    else when(!Mux(runtimeNormProfile,runtimePrefix,Mux(s.qwen35GdnOnly.B,nativeGdn||gdnProjection||coreOperation,Mux(attentionCommandPolicy,nativeAttention,supportedOrdinary)))){fail(Status.Unsupported.U)}
    val validated=initialValidation
    .elsewhen(runtimeNormProfile && ((pc+1.U===cfg.commands) =/= runtimeFence)){fail(Status.Malformed.U)}
    .elsewhen(runtimeFence && !fenceDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeFence && !fenceDisjoint){fail(Status.Permission.U)}
    .elsewhen(runtimeFence && io.runtimeAuthority.currentFault){fail(Status.Protocol.U)}
    .elsewhen(!runtimeNormProfile && !officialRoleOK){fail(Status.Unsupported.U)}
    .elsewhen((runtimeQkNorm || runtimeRope) && !qkDistinct){fail(Status.Malformed.U)}
    .elsewhen((runtimeQkNorm || runtimeRope) && !qkLive){fail(Status.Dependency.U)}
    .elsewhen((runtimeQkNorm || runtimeRope) && !qkFresh){fail(Status.Permission.U)}
    .elsewhen((runtimeKvAppend || runtimeGqa) && !attentionDistinct){fail(Status.Malformed.U)}
    .elsewhen((runtimeKvAppend || runtimeGqa) && !attentionLive){fail(Status.Dependency.U)}
    .elsewhen((runtimeKvAppend || runtimeGqa) && !attentionFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeFfnDense && !rdDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeFfnDense && !ffnDenseLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeFfnDense && !rdFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeFfnElement && !ffnElementDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeFfnElement && !ffnElementLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeFfnElement && !rdFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeDenseO && !rdDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeDenseO && !roLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeDenseO && !rdFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeElementwise && !reDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeElementwise && !reLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeElementwise && !rdFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeDenseProjection && !rdDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeDenseProjection && !rdLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeDenseProjection && !rdFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeConv && !rcDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeConv && !rcLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeConv && !rcFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeChunk && !rcDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeChunk && !chunkLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeChunk && !chunkFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeGatedNorm && !gatedDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeGatedNorm && !gatedLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeGatedNorm && !gatedFresh){fail(Status.Permission.U)}
    .elsewhen(runtimePrep && !rcDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimePrep && !prepLive){fail(Status.Dependency.U)}
    .elsewhen(runtimePrep && !prepFresh){fail(Status.Permission.U)}
    .elsewhen(runtimeNorm && !rnDistinct){fail(Status.Malformed.U)}
    .elsewhen(runtimeNorm && !rnLive){fail(Status.Dependency.U)}
    .elsewhen(runtimeNorm && !rnFresh){fail(Status.Permission.U)}
    .elsewhen(nativeAttention && !attentionDistinct){fail(Status.Malformed.U)}
    .elsewhen((nativeQkNorm||nativePartialRope) && !qkDistinct){fail(Status.Malformed.U)}
    .elsewhen((nativeGdn||gdnProjection||coreOperation) && !gdnDistinct){fail(Status.Malformed.U)}
    .elsewhen(bf16AttentionCore.B && (attentionFence =/= (pc+1.U===cfg.commands))){fail(Status.Malformed.U)}
    .elsewhen(bf16GdnCore.B && (coreFence =/= (pc+1.U===cfg.commands))){fail(Status.Malformed.U)}
    .elsewhen(!runtimePrefix && !Mux(nativeAttention,attentionLive,Mux(nativeGdn||coreOperation||(bf16GdnCore.B && gdnProjection),gdnLive,Mux(nativeQkNorm||nativePartialRope,qkLive,Mux(bf16QkNormRope.B&&nativeProjection,qkProjectionLive,sourceLive))))){fail(Status.Dependency.U)}
    .elsewhen((!runtimePrefix && !Mux(nativeAttention,attentionFresh,Mux(nativeGdn||coreOperation||(bf16GdnCore.B && gdnProjection),gdnFresh,Mux(nativeQkNorm||nativePartialRope,qkFresh,Mux(bf16QkNormRope.B&&nativeProjection,qkProjectionFresh,noAlias && (!gdnProjection || !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd)) &&
      Mux(nativeProjection,freshSpan(activeD,activeDEnd),fresh(d)))))))||
      producedCount+&publicationSlots>producedCapacity.U||virtualCount>=maxCommands.U){fail(Status.Permission.U)}
    val residentValidated=if(enableResidentFfn)validated.elsewhen(residentGate || residentUp){
      if(enableResidentFfn){
        rememberOfficial()
        val j=WireDefault(0.U.asTypeOf(new QwenOwnerJob))
        j.kind:=QwenOwnerKind.Dense.U;j.tag:=Cat(cfg.epoch,pc);j.a:=a.address;j.b:=b.address;j.dst:=d.address
        j.m:=m;j.n:=n;j.k:=a.dims(1);j.weightBf16:=true.B;j.writeBytes:=d.payloadBytes
        j.materializeDenseOutput:=officialMaterializeDense
        when(residentGate){
          resident.get.gateJob:=j;resident.get.inGroup:=true.B
          q:=a;k:=b;score:=d;qkCommand:=cmd;group:=1.U
        }.otherwise{resident.get.upJob:=j;resident.get.upWeight:=b;probability:=d;softCommand:=cmd;group:=2.U}
        nextCommand()
      }
    }
    else validated
    residentValidated
    .elsewhen(runtimeFence){
      // Wait for the original transport/allocator/Guard to retire, not a timer.
      // Validation and exact operands stay live until this private observation.
      when(io.runtimeFinalDrained){
        runtimeFenceHost:=cfg;runtimeFenceTransaction:=runtimeTransaction
        boundRuntimeFence:=true.B;boundRuntimePrefix:=false.B;boundMoePhase:=false.B
        boundAttentionFence:=runtimeAttentionFence;completingGroup:=false.B;completionIndex:=0.U
        state:=complete
      }
    }
    .elsewhen(coreFence||attentionFence){boundFence:=true.B;boundAttentionFence:=attentionFence;state:=complete}
    .elsewhen(qk||attentionQk){rememberOfficial();q:=a;k:=b;score:=d;qkCommand:=cmd;group:=1.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.elsewhen(sm||attentionSoft){rememberOfficial();probability:=d;softCommand:=cmd;group:=2.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.otherwise{
      rememberOfficial()
      bound:=0.U.asTypeOf(new QwenOwnerJob)
      bound.runtimeFfnPhase:=0.U // every legacy/MoE-unrelated ordinary request remains phase0
      // Semantic intent is bound only here, after official public21 producer/PC
      // validation. A persistent Guard physical tag is never a program counter.
      bound.public21Reduction:=officialBf16.B && cfg.profileId===0.U && dense &&
        (pc===1.U || pc===4.U || pc===7.U)
      boundPostnorm:=false.B;boundRuntimePrefix:=runtimePrefix;boundInputTensor:=a
      when(runtimeFfn){
        boundFfnHost:=cfg;boundFfnTransaction:=runtimeTransaction
        boundFfnA:=a;boundFfnB:=b;boundFfnD:=d;ffnDonePending:=false.B
      }
      when(runtimeNorm){
        boundPostnorm:=rnRole===1.U
        when(rnRole===1.U){
          boundPostnormHost:=cfg;boundPostnormTransaction:=runtimeTransaction
          boundPostnormGamma:=b;boundPostnormOutput:=d
          postnormDonePending:=false.B;postnormCommitValid:=false.B
        }
      }
      if(bf16AttentionBlock){when(attentionBlockRms && attentionBlockRole===1.U){boundPostnorm:=true.B}}
      if(bf16GdnBlock){when(blockRmsNorm && policy(1)(84,82)===1.U){boundPostnorm:=true.B}}
      // Qwen2 numerical BF16-in-FP32 is never inferred from a hetero PC collision.
      bound.materializeDenseOutput:=officialMaterializeDense && dense && !runtimeDenseProjection && !runtimeDenseO && !runtimeFfn
      bound.tag:=Cat(cfg.epoch,pc);bound.a:=a.address;bound.b:=b.address;bound.dst:=d.address;bound.writeBytes:=d.payloadBytes
      mainPublishBytes:=d.payloadBytes;boundGdn:=nativeGdn || runtimeConv;boundFence:=false.B;boundAttentionFence:=false.B
      boundAttentionAppend:=attentionAppend;boundAttentionGqa:=attentionPv
      bound.m:=m;bound.n:=n;bound.k:=a.dims(1);bound.weightBf16:=nativeWeight
      bound.kind:=Mux(norm,QwenOwnerKind.Norm.U,Mux(dense||nativeProjection||gdnProjection,QwenOwnerKind.Dense.U,
        Mux(vector,Mux(b.dims(0)===1.U,QwenOwnerKind.Bias.U,QwenOwnerKind.Add.U),
        Mux(rope,QwenOwnerKind.Rope.U,Mux(activation,QwenOwnerKind.Activation.U,
        Mux(append,QwenOwnerKind.KvAppend.U,QwenOwnerKind.Attention.U))))))
      when(runtimeDenseProjection){
        bound.kind:=QwenOwnerKind.Dense.U;bound.m:=m;bound.n:=rdWidth;bound.k:=runtimeNormHidden
        when(runtimeAttentionProfile){bound.qkRole:=rdRole}
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
      }
      when(runtimeDenseO){
        bound.kind:=QwenOwnerKind.Dense.U;bound.m:=m;bound.n:=runtimeNormHidden;bound.k:=outputWidth
        bound.qkRole:=3.U // private common discriminator: never a Q/K/V projection
        bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
      }
      when(runtimeElementwise){
        bound.kind:=QwenOwnerKind.GdnElementwise.U;bound.m:=m;bound.n:=d.dims(1);bound.k:=d.dims(1)
        bound.gdnElementwiseOp:=Mux(runtimeAttentionElement && attentionBlockRole===0.U,2.U,0.U)
        bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
      }
      when(runtimeFfn){
        bound.kind:=Mux(runtimeFfnDense,QwenOwnerKind.Dense.U,QwenOwnerKind.GdnElementwise.U)
        bound.runtimeFfnPhase:=Mux(runtimeFfnDense,Mux(ffnDown,4.U,rdRole-3.U),Mux(ffnSilu,3.U,5.U))
        bound.qkRole:=3.U // DenseO discriminator is further scoped by runtimeFfnPhase==0
        bound.m:=m;bound.n:=Mux(runtimeFfnDense,ffnN,ffnElementWidth)
        bound.k:=Mux(runtimeFfnDense,ffnK,ffnElementWidth)
        bound.gdnElementwiseOp:=Mux(runtimeFfnElement && ffnSilu,GdnElementwiseOp.SiluMul.U,GdnElementwiseOp.Add.U)
        bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
      }
      when(runtimeNorm){
        bound.qkRole:=Mux(rnRole===1.U,3.U,0.U) // distinguish original hidden from postnorm for actual receipt binding
        bound.kind:=QwenOwnerKind.GdnRmsNorm.U;bound.m:=m
        bound.n:=runtimeNormHidden;bound.k:=runtimeNormHidden
        bound.cold:=rnCold;bound.expectedGeneration:=rnGeneration;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
      }
      when(runtimeConv){
        bound.kind:=QwenOwnerKind.GdnConv.U;bound.m:=m;bound.n:=rcChannels;bound.k:=4.U
        bound.c:=rhIn.address;bound.historyOut:=rhOut.address
        bound.cold:=rnCold;bound.expectedGeneration:=rnGeneration;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
        bound.writeBytes:=d.payloadBytes+rhOut.payloadBytes
      }
      when(runtimePrep){
        bound.kind:=QwenOwnerKind.GdnInputPrep.U;bound.m:=m;bound.n:=prepHeads;bound.k:=128.U
        bound.gdnALog:=rhIn.address;bound.gdnDtBias:=rhOut.address;bound.gdnRecurrentMode:=false.B
        bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=false.B;bound.outputBf16:=false.B
        bound.writeBytes:=d.payloadBytes
      }
      when(runtimeChunk){
        bound.kind:=QwenOwnerKind.GdnRecurrent.U;bound.m:=m;bound.n:=prepHeads;bound.k:=128.U
        bound.c:=rhOut.address;bound.gdnStateOut:=rhIn.address;bound.gdnRecurrentMode:=false.B
        bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=false.B;bound.weightBf16:=false.B;bound.outputBf16:=true.B
        bound.writeBytes:=d.payloadBytes+rhIn.payloadBytes
      }
      when(runtimeGatedNorm){
        bound.kind:=QwenOwnerKind.GdnGatedNorm.U;bound.m:=m;bound.n:=prepHeads;bound.k:=128.U
        bound.c:=rhIn.address;bound.cold:=true.B;bound.expectedGeneration:=0.U;bound.currentGeneration:=0.U
        bound.activationBf16:=true.B;bound.weightBf16:=false.B;bound.outputBf16:=true.B
        bound.writeBytes:=d.payloadBytes
      }
      when(nativeProjection){
        bound.a:=activeA;bound.dst:=activeD;bound.m:=tokenCount;bound.n:=projectionN;bound.k:=1024.U
        bound.weightBf16:=true.B;bound.activationBf16:=true.B;bound.outputBf16:=true.B
        bound.writeBytes:=projectionBytes;mainPublishBytes:=projectionBytes
      }
      if(bf16QkNormRope||enableRuntimeQkNorm){when(nativeQkNorm||nativePartialRope){
        bound.kind:=Mux(nativeQkNorm,QwenOwnerKind.QkNorm256.U,QwenOwnerKind.PartialRope64.U)
        bound.a:=qkActiveA;bound.dst:=qkActiveD;bound.m:=qkCount;bound.n:=qkHeads;bound.k:=256.U
        bound.qkRole:=qkRole;bound.qkPositionBase:=ax(111,80);bound.qkTrigTokens:=b.dims(0)
        // Explicit C1/C2/B1 from the existing typed policy. No inferred mode success.
        when(runtimeQkNorm || runtimeRope){bound.qkNormPolicy:=ap(115,108);bound.cold:=true.B}
        bound.c:=Mux(nativeQkNorm && qkRole===0.U,tensors(3).address+qkOffset,0.U)
        bound.activationBf16:=true.B;bound.outputBf16:=true.B;bound.weightBf16:=true.B
        bound.writeBytes:=Mux(nativeQkNorm && qkRole===0.U,qkBytes<<1,qkBytes);mainPublishBytes:=qkBytes
      }}
      if(bf16AttentionCore||enableRuntimeKvAppend||enableRuntimeGqa){when(attentionAppend||attentionPv){
        bound.kind:=Mux(attentionAppend,QwenOwnerKind.KvAppend.U,QwenOwnerKind.Attention.U)
        val queryWidth=Mux(runtimeGqa,runtimeProfile.attentionHeads.pad(16)<<8,2048.U(16.W))
        val queryOffset=(attentionBase.pad(80)*queryWidth.pad(80))<<1
        val outputBytes=(attentionCount.pad(80)*queryWidth.pad(80))<<1
        bound.a:=Mux(attentionAppend,a.address+(attentionBase.pad(64)<<10),(q.address.pad(80)+queryOffset)(63,0))
        bound.b:=b.address+Mux(attentionAppend,attentionBase.pad(64)<<10,0.U)
        bound.dst:=Mux(attentionAppend,d.address,(d.address.pad(80)+queryOffset)(63,0))
        bound.m:=attentionCount;bound.n:=Mux(attentionAppend,512.U,queryWidth);bound.k:=256.U
        // Pinned common profile2/profile4 numerical mapping: pair-high-first.
        // No freely supplied Host order field or changed public job ABI.
        when(runtimeGqa){bound.qkNormPolicy:=1.U;bound.qkRole:=0.U}
        bound.cacheCapacity:=attentionCapacity;bound.cacheLength:=Mux(attentionAppend,attentionExpectedLength,pendingAttentionLength)
        bound.expectedCacheLength:=attentionExpectedLength;bound.queryStart:=attentionQueryStart
        bound.currentGeneration:=Mux(attentionCacheValid,attentionGeneration,0.U);bound.expectedGeneration:=attentionExpectedGeneration;bound.cold:=attentionCold
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
        bound.writeBytes:=Mux(attentionAppend,attentionCount.pad(64)<<11,outputBytes(63,0))
        mainPublishBytes:=Mux(attentionAppend,0.U,outputBytes(63,0))
      }}
      if(bf16AttentionBlock){when(attentionBlockRms || attentionBlockDense || attentionBlockElement){
        bound.kind:=Mux(attentionBlockRms,QwenOwnerKind.GdnRmsNorm.U,Mux(attentionBlockDense,QwenOwnerKind.Dense.U,QwenOwnerKind.GdnElementwise.U))
        bound.m:=1.U;bound.n:=d.dims(1);bound.k:=a.dims(1)
        bound.activationBf16:=true.B;bound.weightBf16:=true.B;bound.outputBf16:=true.B
        when(attentionBlockElement){bound.gdnElementwiseOp:=Mux(attentionBlockRole===0.U,2.U,Mux(attentionBlockRole===2.U,1.U,0.U))}
      }}
      when(gdnProjection){
        bound.n:=n;bound.k:=(if(bf16GdnBlock)a.dims(1) else 1024.U);bound.weightBf16:=true.B;bound.activationBf16:=true.B;bound.outputBf16:=true.B
      }
      if(bf16GdnBlock){
        when(blockRmsNorm){
          bound.kind:=QwenOwnerKind.GdnRmsNorm.U;bound.n:=1024.U;bound.k:=1024.U
          bound.activationBf16:=true.B;bound.outputBf16:=true.B
        }
        when(blockElementwise){
          bound.kind:=QwenOwnerKind.GdnElementwise.U;bound.n:=n;bound.k:=n
          bound.gdnElementwiseOp:=Mux(policy(1)(84,82)===1.U,1.U,0.U)
          bound.activationBf16:=true.B;bound.outputBf16:=true.B
        }
      }
      if(bf16Gdn){when(nativeGdn){
        bound.kind:=QwenOwnerKind.GdnConv.U;bound.c:=tensors(3).address;bound.historyOut:=tensors(4).address
        bound.expectedGeneration:=policy(1)(119,88);bound.currentGeneration:=currentGeneration;bound.cold:=policy(1)(80)
        bound.n:=6144.U;bound.k:=4.U;bound.weightBf16:=true.B;bound.activationBf16:=true.B;bound.outputBf16:=true.B
        bound.writeBytes:=d.payloadBytes+tensors(4).payloadBytes
      }}
      if(bf16GdnCore){
        when(corePrep){
          bound.kind:=QwenOwnerKind.GdnInputPrep.U;bound.gdnALog:=tensors(3).address;bound.gdnDtBias:=tensors(4).address
          bound.gdnRecurrentMode:=policy(1)(81);bound.n:=16.U;bound.k:=128.U
          bound.activationBf16:=true.B
        }
        when(coreRecurrent){
          bound.gdnRecurrentMode:=true.B // explicit legacy mode; runtime Chunk is the distinct false/M16|128 path
          bound.kind:=QwenOwnerKind.GdnRecurrent.U;bound.gdnStateOut:=tensors(3).address
          bound.expectedGeneration:=policy(1)(119,88);bound.currentGeneration:=currentGeneration;bound.cold:=policy(1)(80)
          bound.n:=16.U;bound.k:=128.U;bound.outputBf16:=true.B
          bound.writeBytes:=d.payloadBytes+tensors(3).payloadBytes
        }
        when(coreNorm){
          bound.kind:=QwenOwnerKind.GdnGatedNorm.U;bound.c:=tensors(3).address;bound.n:=16.U;bound.k:=128.U
          bound.activationBf16:=true.B;bound.outputBf16:=true.B
        }
      }
      when(rope){bound.c:=b.address+(s.maxTokens.toLong*s.headDim/2*4).U}
      when(append){bound.n:=s.kv.U}
      when(pv){bound.a:=q.address;bound.b:=k.address;bound.c:=b.address;bound.m:=q.dims(0);bound.n:=s.hidden.U;bound.k:=s.headDim.U}
      state:=issue
      if(enableResidentFfn){
        when(residentAct){resident.get.pending:=true.B;resident.get.scanPc:=0.U;state:=scanFetch;scanAttention.foreach(_:=false.B)}
        if(officialBf16){when(pv){
          resident.get.pending:=false.B;resident.get.scanPc:=0.U;scanAttention.get:=true.B;state:=scanFetch
        }}
      }
    }
    if(enableTransposedDown){
      // Validate the actual owner job dimensions before its DMA can start.
      // Native projection windows use tokenCount, not the declared tensor M.
      val downM=Mux(nativeProjection,tokenCount,m)
      val downN=Mux(nativeProjection,projectionN,n)
      val downK=Mux(nativeProjection,1024.U,a.dims(1))
      val downActivationBf16=nativeProjection || gdnProjection || attentionBlockDense || runtimeDenseProjection || runtimeDenseO || runtimeFfnDense
      val downShapeOK=(downM===16.U || downM===128.U) && downN>0.U && downN(4,0)===0.U &&
        downK>0.U && downK<=8960.U && downK(3,0)===0.U &&
        (!downActivationBf16 || downK(4,0)===0.U)
      val workspaceExtent=cfg.regions(3).limit-cfg.regions(3).base
      val workspaceCapacityOK=downK<=2560.U || workspaceExtent>=(downN.pad(64)>>5)*16384.U
      when(opcode===0x20.U && (!downShapeOK || !workspaceCapacityOK)){fail(Status.Bounds.U)}
    }
  }
  // cfg is captured only on launch.fire and cannot change through owner ACK,
  // completion backpressure or terminal result ACK. The owner snapshots again.
  // Epoch + 1 is an identity tag only, never a persistent checkpoint or proof
  // of freshness after reset. Widen before addition so epoch 65535 maps to 65536.
  if(enableTransposedDown){
    val workspace=io.prefixWorkspace.get
    workspace.valid:=state=/=idle && state=/=locked && status===0.U && !poison
    workspace.base:=cfg.regions(3).base
    workspace.extent:=cfg.regions(3).limit-cfg.regions(3).base
    workspace.generation:=cfg.epoch.pad(32)+1.U(32.W)
    workspace.splitK:=2560.U(12.W)
  }
  // Under the explicitly enabled official binding, an external fault fences
  // all new owner accepts. Metadata already in flight still retires naturally;
  // Legacy issue with no accepted debt terminates. Runtime prefix already
  // exposes job.valid at issue: a late fault MUST NOT retract that offer.
  // Keep the full bound job stable; Guard forbids fresh acceptance and the
  // poisoned transaction remains held until the existing joint reset.
  if(enableResidentFfn && officialBf16){
    when(state===issue && !boundRuntimePrefix && io.resident.get.resetRequired){fail(Status.Protocol.U)}
  }
  // Same actual Guard return as the original done checks, never a Host result.
  // Runtime receipts wait for completion.fire; legacy non-runtime timing stays
  // unchanged. Full cfg/transaction and immutable typed operands survive stalls.
  val runtimePostnormIdentity=runtimeAccepted && runtimeTransaction===boundPostnormTransaction &&
    cfg.asUInt===boundPostnormHost.asUInt && bound.qkRole===3.U && bound.cold &&
    bound.expectedGeneration===0.U && bound.currentGeneration===0.U &&
    boundInputTensor.asUInt===tensors(0).asUInt && boundPostnormGamma.asUInt===tensors(1).asUInt &&
    boundPostnormOutput.asUInt===tensors(2).asUInt && bound.a===boundInputTensor.address &&
    bound.b===boundPostnormGamma.address && bound.dst===boundPostnormOutput.address &&
    bound.writeBytes===boundPostnormOutput.payloadBytes
  val postnormProof=io.runtimePostnormReceipt.bits
  val postnormExpectedPhysical=WireDefault(bound);postnormExpectedPhysical.tag:=postnormProof.job.tag
  val runtimePostnormProof=io.runtimePostnormReceipt.valid &&
    postnormProof.transactionId===runtimeTransaction && postnormProof.host.asUInt===cfg.asUInt &&
    postnormProof.logicalJob.asUInt===bound.asUInt &&
    postnormProof.job.asUInt===postnormExpectedPhysical.asUInt && postnormProof.job.tag=/="hffffffff".U &&
    postnormProof.result.tag===postnormProof.job.tag && postnormProof.result.status===Status.Ok.U &&
    postnormProof.result.writeBytes===bound.writeBytes && postnormProof.result.outputCommitted &&
    postnormProof.result.outputAckBytes===bound.writeBytes && postnormProof.result.resourcesDrained &&
    postnormProof.residual.transactionId===runtimeTransaction && postnormProof.residual.host.asUInt===cfg.asUInt &&
    postnormProof.residual.job.kind===QwenOwnerKind.GdnElementwise.U &&
    postnormProof.residual.job.gdnElementwiseOp===GdnElementwiseOp.Add.U &&
    postnormProof.residual.job.dst===bound.a && postnormProof.residual.job.m===bound.m &&
    postnormProof.residual.job.n===bound.n && postnormProof.residual.job.writeBytes===bound.writeBytes &&
    postnormProof.residual.job.tag<postnormProof.job.tag && postnormProof.residual.job.tag=/="hffffffff".U &&
    postnormProof.residual.result.tag===postnormProof.residual.job.tag &&
    postnormProof.residual.result.status===Status.Ok.U && postnormProof.residual.result.writeBytes===bound.writeBytes
  val ordinaryPostnormAck=io.done.fire && boundPostnorm &&
    bound.kind===QwenOwnerKind.GdnRmsNorm.U && io.done.bits.tag===bound.tag &&
    io.done.bits.status===Status.Ok.U && io.done.bits.writeBytes===bound.writeBytes &&
    status===Status.Ok.U && !poison &&
    (!boundRuntimePrefix || (runtimePostnormIdentity && runtimePostnormProof &&
      postnormProof.result.cycles===io.done.bits.cycles && !io.runtimeAuthority.currentFault))
  val residentFault=if(enableResidentFfn)io.resident.get.resetRequired else false.B
  when(ordinaryPostnormAck && !residentFault){
    postnormCommitValid:= !boundRuntimePrefix;postnormDonePending:=boundRuntimePrefix;postnormJob:=bound
    postnormResult:=io.done.bits;postnormResidual:=boundInputTensor;postnormOutputTensor:=tensors(2)
    postnormHost:=cfg;postnormTransaction:=runtimeTransaction
    when(boundRuntimePrefix){postnormPhysicalReceipt:=postnormProof}
  }
  val runtimePostnormPendingExact=postnormDonePending && postnormCurrent && runtimePostnormIdentity &&
    postnormJob.asUInt===bound.asUInt && postnormResidual.asUInt===boundInputTensor.asUInt &&
    postnormOutputTensor.asUInt===boundPostnormOutput.asUInt && postnormResult.tag===bound.tag &&
    postnormResult.status===Status.Ok.U && postnormResult.writeBytes===bound.writeBytes &&
    runtimePostnormProof && postnormPhysicalReceipt.asUInt===postnormProof.asUInt
  val boundRuntimeFfn=boundRuntimePrefix && bound.runtimeFfnPhase>=1.U && bound.runtimeFfnPhase<=5.U
  val runtimeFfnIdentity=runtimeAccepted && runtimeTransaction===boundFfnTransaction &&
    cfg.asUInt===boundFfnHost.asUInt && (cfg.profileId===1.U || cfg.profileId===2.U) &&
    !bound.public21Reduction && bound.cold && bound.expectedGeneration===0.U && bound.currentGeneration===0.U &&
    boundFfnA.asUInt===tensors(0).asUInt && boundFfnB.asUInt===tensors(1).asUInt &&
    boundFfnD.asUInt===tensors(2).asUInt && bound.a===boundFfnA.address &&
    bound.b===boundFfnB.address && bound.dst===boundFfnD.address && bound.writeBytes===boundFfnD.payloadBytes
  val ffnProof=io.runtimeFfnReceipt.bits
  val ffnExpectedPhysical=WireDefault(bound);ffnExpectedPhysical.tag:=ffnProof.job.tag
  val runtimeFfnProof=io.runtimeFfnReceipt.valid && runtimeFfnIdentity &&
    ffnProof.transactionId===runtimeTransaction && ffnProof.host.asUInt===cfg.asUInt &&
    ffnProof.logicalJob.asUInt===bound.asUInt && ffnProof.job.asUInt===ffnExpectedPhysical.asUInt &&
    ffnProof.job.tag=/="hffffffff".U && ffnProof.result.tag===ffnProof.job.tag &&
    ffnProof.result.status===Status.Ok.U && ffnProof.result.writeBytes===bound.writeBytes
  val ffnLogicalResult=WireDefault(ffnProof.result);ffnLogicalResult.tag:=bound.tag
  val ffnExpectedMacs=bound.m.pad(64)*bound.n.pad(64)*bound.k.pad(64)
  val ffnNumericalCount=bound.kind=/=QwenOwnerKind.Dense.U ||
    (ffnProof.result.usefulMacs===ffnExpectedMacs && ffnProof.result.executedMacs>=ffnProof.result.usefulMacs)
  val runtimeFfnPendingExact=ffnDonePending && runtimeFfnProof && ffnNumericalCount &&
    ffnPhysicalReceipt.asUInt===ffnProof.asUInt
  when(io.done.fire && boundRuntimeFfn && runtimeFfnProof && ffnNumericalCount &&
    io.done.bits.asUInt===ffnLogicalResult.asUInt && !io.runtimeAuthority.currentFault && !residentFault){
    ffnDonePending:=true.B;ffnPhysicalReceipt:=ffnProof
  }
  when(io.runtimeAuthority.currentFault){
    ffnDonePending:=false.B
    // The public private-authority view below is revoked immediately, but the
    // structural committed snapshot must persist for an already held MoE offer.
    // That original interface has no cancellation handshake; only pending
    // completion eligibility is cleared, never the held proposal's intent.
    postnormDonePending:=false.B
  }
  when(postnormCommitValid && !postnormCurrent){
    postnormCommitValid:=false.B
  }
  // Width is explicit before multiplication. n is Qheads*256, so the exact
  // useful count is 2*M*C*Qheads*256 for BOTH Q8 and Q16; never a Q8 shift12.
  val runtimeGqaMacsWide=(bound.m.pad(96)*bound.cacheLength.pad(96)*bound.n.pad(96))<<1
  val runtimeGqaAck=boundRuntimePrefix && bound.kind===QwenOwnerKind.Attention.U
  def badRuntimeGqaMacs(r:QwenOwnerResult):Bool=runtimeGqaAck &&
    (runtimeGqaMacsWide(runtimeGqaMacsWide.getWidth-1,64).orR || r.usefulMacs=/=runtimeGqaMacsWide(63,0))
  // A known-bad physical proof cannot first expose a successful completion.
  // This only changes registered parser state/status after the real done fire.
  def badRuntimePostnormAck(r:QwenOwnerResult):Bool=boundRuntimePrefix && boundPostnorm &&
    (!runtimePostnormIdentity || !runtimePostnormProof || postnormProof.result.cycles=/=r.cycles ||
      io.runtimeAuthority.currentFault)
  def badRuntimeFfnAck(r:QwenOwnerResult):Bool=boundRuntimeFfn &&
    (!runtimeFfnProof || !ffnNumericalCount || r.asUInt=/=ffnLogicalResult.asUInt || io.runtimeAuthority.currentFault)
  when(io.job.fire){jobs:=jobs+1.U;state:=waitDone}
  if(enableResidentFfn){when(io.resident.get.request.fire){jobs:=jobs+1.U;state:=waitDone}}
  if(enableResidentFfn){
  when(io.done.fire || io.resident.get.result.fire){val r=Mux(resident.get.pending,io.resident.get.result.bits,io.done.bits)
    when(io.resident.get.resetRequired && (resident.get.pending || r.status===0.U)){fail(Status.Protocol.U)}
    .elsewhen(r.tag=/=bound.tag){fail(Status.Protocol.U)}
    .elsewhen(r.status=/=0.U){fail(r.status)}
    .elsewhen(r.writeBytes=/=bound.writeBytes || badRuntimeGqaMacs(r) || badRuntimePostnormAck(r) || badRuntimeFfnAck(r)){fail(Status.Protocol.U)}
    .otherwise{
      useful:=useful+r.usefulMacs;executed:=executed+r.executedMacs;written:=written+r.writeBytes
      completingGroup:=group===2.U;completionIndex:=0.U;state:=complete
    }
  }
  }else{
  when(io.done.fire){val r=io.done.bits
    when(r.tag=/=bound.tag){fail(Status.Protocol.U)}
    .elsewhen(r.status=/=0.U){fail(r.status)}
    .elsewhen(r.writeBytes=/=bound.writeBytes || badRuntimeGqaMacs(r) || badRuntimePostnormAck(r) || badRuntimeFfnAck(r)){fail(Status.Protocol.U)}
    .otherwise{
      useful:=useful+r.usefulMacs;executed:=executed+r.executedMacs;written:=written+r.writeBytes
      completingGroup:=group===2.U;completionIndex:=0.U;state:=complete
    }
  }
  }
  when(io.completion.fire){
    when(status=/=0.U){state:=finish}
    .elsewhen(boundRuntimeFence){
      // The terminal host-facing completion handshake is the commit edge,
      // matching the original fence contract. The separate result follows.
      // Held completion bits never change on a late fault; fault vetoes commit.
      val finalIdentity=runtimeAccepted && runtimeTransaction===runtimeFenceTransaction &&
        cfg.asUInt===runtimeFenceHost.asUInt && pc+1.U===cfg.commands
      when(!finalIdentity || io.runtimeAuthority.currentFault || !io.runtimeFinalDrained || runtimeCheckpointCommitted){
        status:=Status.Protocol.U;poison:=true.B;state:=finish
      }.otherwise{
        when(boundAttentionFence){
          attentionCacheValid:=true.B;attentionCache:=pendingAttentionCache
          attentionContext:=runtimeFinalTensor;attentionLength:=pendingAttentionLength
          attentionGeneration:=pendingAttentionGeneration+1.U
          pendingAttentionValid:=false.B;pendingGqaValid:=false.B
        }.otherwise{
          stateValid:=true.B;currentGeneration:=txGeneration+1.U
          currentHistoryAddress:=pendingHistoryAddress;currentHistoryEnd:=pendingHistoryEnd
          currentStateAddress:=pendingStateAddress;currentStateEnd:=pendingStateEnd
        }
        runtimeCheckpointCommitted:=true.B
        events(signalEvent(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U
        previousSignal:=signalEvent;boundRuntimeFence:=false.B;state:=finish
      }
    }
    .elsewhen(boundRuntimePrefix){
      // Preserve the held completion payload; late fault vetoes its publication.
      when(io.runtimeAuthority.currentFault || (boundPostnorm && !runtimePostnormPendingExact) ||
        (boundRuntimeFfn && !runtimeFfnPendingExact)){
        status:=Status.Protocol.U;poison:=true.B;state:=finish
        postnormCommitValid:=false.B;postnormDonePending:=false.B;ffnDonePending:=false.B
      }
      .otherwise{
        // One fused owner finishes all three original commands. Emit each
        // held event in order, but publish the staged output exactly ONCE,
        // after the final PV event; a late fault vetoes that publication.
        events(completionCommand(55,40)(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U
        previousSignal:=completionCommand(55,40)
        when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}
        .otherwise{
        // KV writes only stage a two-plane proposal. Never mark its entire
        // cache allocation (including unwritten rows) as a live tensor.
        when(bound.kind=/=QwenOwnerKind.KvAppend.U){
          val out=producedCount(producedIndexBits-1,0)
          starts(out):=bound.dst;ends(out):=bound.dst+mainPublishBytes
          allocationStarts(out):=tensors(2).address;allocationEnds(out):=tensors(2).paddedEnd
          producedValid(out):=true.B;managedHistory(out):=false.B;producedCount:=producedCount+1.U
        }
        when(boundRuntimeFfn){
          // Every numerical materialization came from the same exact physical
          // done receipt and crossed this original completion.fire. Never let
          // a FFN Dense match the older DenseO/QKV producer cases below.
          val ffnIndex=bound.runtimeFfnPhase-1.U
          runtimeFfnTensors(ffnIndex):=tensors(2);ffnDonePending:=false.B
          switch(bound.runtimeFfnPhase){
            is(1.U){txGateValid:=true.B;txGate:=bound.dst;rememberSource(tensors(1),Mux(runtimeGdnProfile,13.U,10.U))}
            is(2.U){txUpValid:=true.B;txUp:=bound.dst;rememberSource(tensors(1),Mux(runtimeGdnProfile,14.U,11.U))}
            is(3.U){txSiluValid:=true.B;txSilu:=bound.dst}
            is(4.U){txDownValid:=true.B;txDown:=bound.dst;rememberSource(tensors(1),Mux(runtimeGdnProfile,15.U,12.U))}
            is(5.U){txResidual2Valid:=true.B;txResidual2:=bound.dst;runtimeFinalTensor:=tensors(2)}
          }
          when(runtimeAttentionProfile){
            val target=MuxLookup(bound.runtimeFfnPhase,10.U)(Seq(1.U->6.U,2.U->7.U,3.U->8.U,4.U->9.U))
            attentionBlockValues(target):=tensors(2);attentionBlockValid(target):=true.B
          }
          // Residual2 is staged only. No cache/state root or generation commit,
          // final Host launch seal or dual-root fence is opened by this branch.
        }.elsewhen(bound.kind===QwenOwnerKind.GdnConv.U){
          val historyIndex=(producedCount+1.U)(producedIndexBits-1,0)
          starts(historyIndex):=bound.historyOut;ends(historyIndex):=tensors(4).paddedEnd
          allocationStarts(historyIndex):=tensors(4).address;allocationEnds(historyIndex):=tensors(4).paddedEnd
          producedValid(historyIndex):=true.B;managedHistory(historyIndex):=true.B;producedCount:=producedCount+2.U
          txConvValid:=true.B;txConv:=bound.dst;runtimeConvTensor:=tensors(2);runtimeHistoryTensor:=tensors(4)
          rememberSource(tensors(1),4.U);rememberSource(tensors(3),8.U)
          pendingHistoryAddress:=bound.historyOut;pendingHistoryEnd:=tensors(4).paddedEnd
          // This is staged history only. stateValid/currentGeneration and the
          // persistent recurrent root are untouched until a future full fence.
        }.elsewhen(bound.kind===QwenOwnerKind.GdnInputPrep.U){
          txPrepValid:=true.B;txPrep:=bound.dst;runtimePrepTensor:=tensors(2)
          rememberSource(tensors(3),5.U);rememberSource(tensors(4),6.U)
          // Prepared query is already L2-normalized AND scaled once; decay
          // is g, not exp(g). This is only a staged producer, not state commit.
        }.elsewhen(bound.kind===QwenOwnerKind.GdnRecurrent.U){
          // Publish only staged output and stateOut; scratch is private, never a tensor producer.
          val stateIndex=(producedCount+1.U)(producedIndexBits-1,0)
          starts(stateIndex):=bound.gdnStateOut;ends(stateIndex):=tensors(3).paddedEnd
          allocationStarts(stateIndex):=tensors(3).address;allocationEnds(stateIndex):=tensors(3).paddedEnd
          producedValid(stateIndex):=true.B;managedHistory(stateIndex):=true.B;producedCount:=producedCount+2.U
          txRecurrentValid:=true.B;txRecurrent:=bound.dst;runtimeChunkTensor:=tensors(2);rememberSource(tensors(1),9.U)
          pendingStateAddress:=bound.gdnStateOut;pendingStateEnd:=tensors(3).paddedEnd;runtimeStateTensor:=tensors(3)
          // No stateValid/currentGeneration update: final block fence is still required.
        }.elsewhen(bound.kind===QwenOwnerKind.GdnGatedNorm.U){
          txNormValid:=true.B;txNorm:=bound.dst;runtimeGatedNormTensor:=tensors(2)
          rememberSource(tensors(3),7.U)
          // Only the real GatedNorm output ACK publishes this staged tensor.
          // Only private staging; final dual-root publication remains pending.
        }.elsewhen(bound.kind===QwenOwnerKind.QkNorm256.U){
          // Only the real matching owner terminal plus same-cycle fault veto
          // reaches this branch; a preloaded BF16 lookalike is never a producer.
          qkNormalizedValid(bound.qkRole):=true.B;qkNormalized(bound.qkRole):=tensors(2).address
          qkNormalizedTensor(bound.qkRole):=tensors(2);rememberSource(tensors(1),4.U+bound.qkRole)
          when(bound.qkRole===0.U){
            val gateIndex=(producedCount+1.U)(producedIndexBits-1,0)
            starts(gateIndex):=bound.c;ends(gateIndex):=bound.c+mainPublishBytes
            allocationStarts(gateIndex):=tensors(3).address;allocationEnds(gateIndex):=tensors(3).paddedEnd
            producedValid(gateIndex):=true.B;managedHistory(gateIndex):=false.B;producedCount:=producedCount+2.U
            attentionBlockValues(1):=tensors(3);attentionBlockValid(1):=true.B
          }
          // No cache/history/state generation commit occurs at this stage.
        }.elsewhen(bound.kind===QwenOwnerKind.PartialRope64.U){
          // The same Guard/owner terminal above requires the true full writeACK.
          // Publish only this role; K also depends on the already published Q.
          rememberSource(tensors(1),6.U);qkRotatedValid(bound.qkRole):=true.B
          qkRotatedTensor(bound.qkRole):=tensors(2);qkAbsolutePosition(bound.qkRole):=bound.qkPositionBase
          // Cache append is a separate acknowledged staging step; final
          // cache/state publication still requires the complete block fence.
        }.elsewhen(bound.kind===QwenOwnerKind.KvAppend.U){
          // Guard/Kernel already require exact K-RoPE and V-Dense producers,
          // true matching ACKs for BOTH planes and a drained proposal. This
          // private snapshot is NOT a published cache root/length/generation.
          pendingAttentionValid:=true.B;pendingAttentionCache:=tensors(2)
          pendingAttentionOldLength:=bound.cacheLength;pendingAttentionLength:=bound.cacheLength+bound.m
          pendingAttentionGeneration:=bound.expectedGeneration;pendingAttentionCold:=bound.cold
          pendingAttentionBase:=policy(attentionPolicySlot)(99,68);pendingAttentionCount:=bound.m
        }.elsewhen(bound.kind===QwenOwnerKind.Attention.U){
          // This is an actual GQA output ACK, not a cache/state publication.
          // Cache length/generation/root remain private until the full fence.
          pendingGqaValid:=true.B;pendingAttentionContext:=tensors(2)
        }.elsewhen(bound.kind===QwenOwnerKind.GdnElementwise.U){
          when(bound.gdnElementwiseOp===2.U){
            attentionBlockValues(2):=tensors(2);attentionBlockValid(2):=true.B
          }.otherwise{
            txResidual1Valid:=true.B;txResidual1:=bound.dst;txResidual1Tensor:=tensors(2)
            when(runtimeAttentionProfile){attentionBlockValues(4):=tensors(2);attentionBlockValid(4):=true.B}
          }
          // Actual output ACK is only a staged producer. No final/root fence.
        }.elsewhen(bound.kind===QwenOwnerKind.Dense.U && bound.qkRole===3.U){
          txOValid:=true.B;txO:=bound.dst;runtimeOTensor:=tensors(2)
          rememberSource(tensors(1),Mux(runtimeGdnProfile,11.U,8.U))
          when(runtimeAttentionProfile){attentionBlockValues(3):=tensors(2);attentionBlockValid(3):=true.B}
        }.elsewhen(bound.kind===QwenOwnerKind.Dense.U){
          val role=policy(2)(84,82)
          rememberSource(tensors(1),role+1.U)
          when(runtimeGdnProfile){
            runtimeProjectionTensors(role):=tensors(2)
            switch(role){
              is(0.U){txQkvValid:=true.B;txQkv:=bound.dst}
              is(1.U){txZValid:=true.B;txZ:=bound.dst}
              is(2.U){txAbValid:=true.B;txAb:=bound.dst}
            }
          }.otherwise{
            qkProjectedValid(role):=true.B;qkProjected(role):=tensors(2).address
            qkProjectedTensor(role):=tensors(2);qkRows(role):=bound.m
            qkWindowBase(role):=0.U;qkWindowCount(role):=bound.m
          }
        }.elsewhen(bound.kind===QwenOwnerKind.GdnRmsNorm.U && bound.qkRole===0.U && !boundPostnorm){
          txInputValid:=true.B;txInputAddress:=bound.a;txInputEnd:=tensors(0).paddedEnd
          txInputNormValid:=true.B;txInputNorm:=bound.dst;runtimeInputNormTensor:=tensors(2)
          txGeneration:=policy(1)(119,88);txCold:=policy(1)(80)
          rememberSource(tensors(0),0.U)
          rememberSource(tensors(1),Mux(runtimeGdnProfile,10.U,7.U))
          when(!runtimeGdnProfile){attentionBlockValues(0):=tensors(2);attentionBlockValid(0):=true.B}
        }.elsewhen(bound.kind===QwenOwnerKind.GdnRmsNorm.U && bound.qkRole===3.U && boundPostnorm){
          txPostNormValid:=true.B;txPostNorm:=bound.dst
          postnormCommitValid:=true.B;postnormDonePending:=false.B
          rememberSource(tensors(1),Mux(runtimeGdnProfile,12.U,9.U))
          when(!runtimeGdnProfile){attentionBlockValues(5):=tensors(2);attentionBlockValid(5):=true.B}
        }
        boundRuntimePrefix:=false.B;group:=0.U;completingGroup:=false.B
        when(pc+1.U===cfg.commands){state:=finish}.otherwise{pc:=pc+1.U;state:=fetch}
        }
      }
    }
    .elsewhen(boundMoePhase){
      // Held transport payload is never changed for a late fault. A late
      // fault vetoes publication and the final Host result reports Protocol.
      when(io.runtimeAuthority.currentFault){
        status:=Status.Protocol.U;poison:=true.B;state:=finish
      }.otherwise{
        val outputIndex=producedCount(producedIndexBits-1,0)
        starts(outputIndex):=tensors(2).address;ends(outputIndex):=tensors(2).paddedEnd
        allocationStarts(outputIndex):=tensors(2).address;allocationEnds(outputIndex):=tensors(2).paddedEnd
        producedValid(outputIndex):=true.B;managedHistory(outputIndex):=false.B
        producedCount:=producedCount+1.U
        events(signalEvent(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U
        previousSignal:=signalEvent;boundMoePhase:=false.B
        txResidual2Valid:=true.B;txResidual2:=tensors(2).address;runtimeFinalTensor:=tensors(2)
        group:=0.U;completingGroup:=false.B
        when(pc+1.U===cfg.commands){state:=finish}.otherwise{pc:=pc+1.U;state:=fetch}
      }
    }
    .otherwise{
      events(completionCommand(55,40)(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U
      if(bf16GdnCore||bf16QkNormRope){previousSignal:=completionCommand(55,40)}
      when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}
      .otherwise{
        when(!boundFence && !boundAttentionAppend){
          val outputIndex=producedCount(producedIndexBits-1,0)
          starts(outputIndex):=bound.dst;ends(outputIndex):=bound.dst+mainPublishBytes
          producedValid(outputIndex):=true.B;managedHistory(outputIndex):=false.B
          producedCount:=producedCount+1.U
        }
        if(bf16QkNormRope){
          val outputIndex=producedCount(producedIndexBits-1,0)
          allocationStarts(outputIndex):=tensors(2).address;allocationEnds(outputIndex):=tensors(2).paddedEnd
          when(bound.kind===QwenOwnerKind.Dense.U && !attentionBlockMatrix && !boundFence){
            val role=policy(2)(65,64)
            qkProjectedValid(role):=true.B;qkProjected(role):=tensors(2).address;qkProjectedTensor(role):=tensors(2);qkRows(role):=tensors(0).dims(0)
            qkWindowBase(role):=policy(2)(99,68);qkWindowCount(role):=policy(2)(107,100)
            if(!bf16AttentionBlock){rememberSource(tensors(0),0.U)}
            rememberSource(tensors(1),role+1.U)
          }.elsewhen(bound.kind===QwenOwnerKind.QkNorm256.U){
            qkNormalizedValid(bound.qkRole):=true.B;qkNormalized(bound.qkRole):=tensors(2).address;qkNormalizedTensor(bound.qkRole):=tensors(2)
            rememberSource(tensors(1),4.U+bound.qkRole)
            when(bound.qkRole===0.U){
              val gateIndex=(producedCount+1.U)(producedIndexBits-1,0)
              starts(gateIndex):=bound.c;ends(gateIndex):=bound.c+mainPublishBytes
              allocationStarts(gateIndex):=tensors(3).address;allocationEnds(gateIndex):=tensors(3).paddedEnd
              producedValid(gateIndex):=true.B;managedHistory(gateIndex):=false.B;producedCount:=producedCount+2.U
              if(bf16AttentionBlock){attentionBlockValues(1):=tensors(3);attentionBlockValid(1):=true.B}
            }
          }.elsewhen(bound.kind===QwenOwnerKind.PartialRope64.U && !boundFence){
            rememberSource(tensors(1),6.U);qkRotatedValid(bound.qkRole):=true.B
            qkRotatedTensor(bound.qkRole):=tensors(2);qkAbsolutePosition(bound.qkRole):=bound.qkPositionBase
          }
        }
        if(bf16AttentionCore){
          when(boundAttentionFence){
            // Acceptance of the terminal core completion is the sole commit.
            // Append/GQA ACKs only stage a proposal, never alter visible roots.
            when(!attentionCacheValid){for(i<-0 until attentionParameterCount){attentionParameters(i):=sourceTensor(i+1)}}
            attentionCacheValid:=true.B;attentionCache:=pendingAttentionCache
            attentionContext:=(if(bf16AttentionBlock)tensors(2) else pendingAttentionContext)
            attentionLength:=pendingAttentionLength;attentionGeneration:=pendingAttentionGeneration+1.U
            pendingAttentionValid:=false.B;pendingGqaValid:=false.B
          }.elsewhen(boundAttentionAppend){
            pendingAttentionValid:=true.B;pendingAttentionCache:=tensors(2)
            pendingAttentionOldLength:=bound.cacheLength;pendingAttentionLength:=bound.cacheLength+bound.m
            pendingAttentionGeneration:=bound.expectedGeneration;pendingAttentionCold:=bound.cold
            pendingAttentionBase:=policy(attentionPolicySlot)(99,68);pendingAttentionCount:=bound.m
          }.elsewhen(boundAttentionGqa){pendingGqaValid:=true.B;pendingAttentionContext:=tensors(2)}
        }
        if(bf16AttentionBlock){
          when(!boundFence){
            val role=policy(attentionPolicySlot)(118,116)
            when(bound.kind===QwenOwnerKind.GdnRmsNorm.U){
              val target=Mux(role===0.U,0.U,5.U)
              attentionBlockValues(target):=tensors(2);attentionBlockValid(target):=true.B
              when(role===0.U){
                rememberSource(tensors(0),0.U);rememberSource(tensors(1),7.U)
                attentionBlockContext:=policy(attentionContextSlot)(127,56)
              }.otherwise{rememberSource(tensors(1),9.U)}
            }.elsewhen(bound.kind===QwenOwnerKind.Dense.U && attentionBlockMatrix){
              val target=MuxLookup(role,3.U)(Seq(0.U->3.U,1.U->6.U,2.U->7.U,3.U->9.U))
              attentionBlockValues(target):=tensors(2);attentionBlockValid(target):=true.B
              rememberSource(tensors(1),Mux(role===0.U,8.U,role+9.U))
            }.elsewhen(bound.kind===QwenOwnerKind.GdnElementwise.U){
              val target=MuxLookup(role,2.U)(Seq(0.U->2.U,1.U->4.U,2.U->8.U,3.U->10.U))
              attentionBlockValues(target):=tensors(2);attentionBlockValid(target):=true.B
            }
          }
        }
        if(bf16GdnCore){
          when(boundFence){
            // One clock edge publishes BOTH persistent roots and generation.
            // Every producer ACK and the exact final D were validated first.
            when(!stateValid){for((sourceRole,i)<-parameterRoles.zipWithIndex){
              committedParameterStarts(i):=sourceStarts(sourceRole);committedParameterEnds(i):=sourceEnds(sourceRole)
            }}
            stateValid:=true.B;currentGeneration:=txGeneration+1.U
            currentHistoryAddress:=pendingHistoryAddress;currentHistoryEnd:=pendingHistoryEnd
            currentStateAddress:=pendingStateAddress;currentStateEnd:=pendingStateEnd
            clearTransaction()
          }.elsewhen(bound.kind===QwenOwnerKind.Dense.U){
            if(bf16GdnBlock){
              val denseRole=policy(2)(84,82)
              val weightRole=Mux(denseRole<=2.U,denseRole+1.U,Mux(denseRole===3.U,11.U,denseRole+9.U))
              rememberSource(tensors(1),weightRole)
              switch(denseRole){
                is(0.U){txQkvValid:=true.B;txQkv:=bound.dst}
                is(1.U){txZValid:=true.B;txZ:=bound.dst}
                is(2.U){txAbValid:=true.B;txAb:=bound.dst}
                is(3.U){txOValid:=true.B;txO:=bound.dst}
                is(4.U){txGateValid:=true.B;txGate:=bound.dst}
                is(5.U){txUpValid:=true.B;txUp:=bound.dst}
                is(6.U){txDownValid:=true.B;txDown:=bound.dst}
              }
            }else{
              txInputValid:=true.B;txInputAddress:=bound.a;txInputEnd:=tensors(0).paddedEnd
              txGeneration:=policy(2)(119,88);txCold:=policy(2)(80)
              rememberSource(tensors(0),0.U)
              rememberSource(tensors(1),Mux(bound.n===6144.U,1.U,Mux(bound.n===2048.U,2.U,3.U)))
              when(bound.n===6144.U){txQkvValid:=true.B;txQkv:=bound.dst}
              .elsewhen(bound.n===2048.U){txZValid:=true.B;txZ:=bound.dst}
              .otherwise{txAbValid:=true.B;txAb:=bound.dst}
            }
          }.elsewhen(boundGdn){
            val historyIndex=(producedCount+1.U)(producedIndexBits-1,0)
            starts(historyIndex):=bound.historyOut;ends(historyIndex):=tensors(4).paddedEnd
            producedValid(historyIndex):=true.B;managedHistory(historyIndex):=true.B;producedCount:=producedCount+2.U
            txConvValid:=true.B;txConv:=bound.dst
            rememberSource(tensors(1),4.U);rememberSource(tensors(3),8.U)
            pendingHistoryAddress:=bound.historyOut;pendingHistoryEnd:=tensors(4).paddedEnd
          }.elsewhen(bound.kind===QwenOwnerKind.GdnInputPrep.U){
            txPrepValid:=true.B;txPrep:=bound.dst
            rememberSource(tensors(3),5.U);rememberSource(tensors(4),6.U)
          }
          .elsewhen(bound.kind===QwenOwnerKind.GdnRecurrent.U){
            val stateIndex=(producedCount+1.U)(producedIndexBits-1,0)
            starts(stateIndex):=bound.gdnStateOut;ends(stateIndex):=tensors(3).paddedEnd
            producedValid(stateIndex):=true.B;managedHistory(stateIndex):=true.B;producedCount:=producedCount+2.U
            txRecurrentValid:=true.B;txRecurrent:=bound.dst
            rememberSource(tensors(1),9.U)
            pendingStateAddress:=bound.gdnStateOut;pendingStateEnd:=tensors(3).paddedEnd
          }.elsewhen(bound.kind===QwenOwnerKind.GdnGatedNorm.U){
            txNormValid:=true.B;txNorm:=bound.dst;rememberSource(tensors(3),7.U)
          }
          if(bf16GdnBlock){
            when(bound.kind===QwenOwnerKind.GdnRmsNorm.U && !boundFence){
              when(policy(1)(84,82)===0.U){
                txInputValid:=true.B;txInputAddress:=bound.a;txInputEnd:=tensors(0).paddedEnd
                txGeneration:=policy(1)(119,88);txCold:=policy(1)(80)
                txInputNormValid:=true.B;txInputNorm:=bound.dst
                rememberSource(tensors(0),0.U);rememberSource(tensors(1),10.U)
              }.otherwise{txPostNormValid:=true.B;txPostNorm:=bound.dst;rememberSource(tensors(1),12.U)}
            }
            when(bound.kind===QwenOwnerKind.GdnElementwise.U && !boundFence){
              switch(policy(1)(84,82)){
                is(0.U){txResidual1Valid:=true.B;txResidual1:=bound.dst;txResidual1Tensor:=tensors(2)}
                is(1.U){txSiluValid:=true.B;txSilu:=bound.dst}
                is(2.U){txResidual2Valid:=true.B;txResidual2:=bound.dst}
              }
            }
          }
        }else if(bf16Gdn){when(boundGdn){
          // Legacy v1 profile retains its per-Conv publication contract.
          for(i<-0 until producedCapacity){
            when(producedValid(i) && managedHistory(i) && starts(i)===currentHistoryAddress && ends(i)===currentHistoryEnd){producedValid(i):=false.B}
          }
          val historyIndex=(producedCount+1.U)(producedIndexBits-1,0)
          starts(historyIndex):=bound.historyOut;ends(historyIndex):=tensors(4).paddedEnd
          producedValid(historyIndex):=true.B;managedHistory(historyIndex):=true.B
          producedCount:=producedCount+2.U
          stateValid:=true.B;currentGeneration:=bound.expectedGeneration+1.U
          currentHistoryAddress:=bound.historyOut;currentHistoryEnd:=tensors(4).paddedEnd
        }}
        if(enableResidentFfn){resident.get.inGroup:=false.B;resident.get.pending:=false.B}
        group:=0.U;completingGroup:=false.B
        when(pc+1.U===cfg.commands){state:=finish}.otherwise{pc:=pc+1.U;state:=fetch}
      }
    }
  }
  if(enableResidentFfn){when(state===complete && !boundMoePhase && !boundRuntimePrefix && !boundRuntimeFence && status===0.U && io.resident.get.resetRequired){fail(Status.Protocol.U)}}
  if(enableResidentFfn){
    val r=resident.get
    when(state===scanFetch && reader.io.request.fire){state:=scanGet}
    when(state===scanGet && reader.io.result.fire){
      val response=reader.io.result.bits;val c=response.data
      val isSm=c(7,0)===0x33.U
      val rootsOK=c(79,56)<cfg.descriptors && c(127,104)<cfg.descriptors &&
        Mux(isSm,c(103,80)===0xffffff.U,c(103,80)<cfg.descriptors)
      when(response.status=/=0.U){fail(response.status)}
      .elsewhen(response.requestTag=/=Cat(cfg.epoch,r.scanPc,0.U(32.W))){fail(Status.Protocol.U)}
      .elsewhen(!rootsOK){fail(Status.Malformed.U)}
      .elsewhen((r.scanPc===pc-2.U && c=/=qkCommand) || (r.scanPc===pc-1.U && c=/=softCommand) || (r.scanPc===pc && c=/=cmd)){fail(Status.Protocol.U)}
      .otherwise{r.scanCmd:=c;r.scanSlot:=0.U;state:=scanTensorIssue}
    }
    when(state===scanTensorIssue && tensor.io.request.fire){state:=scanTensorGet}
    when(state===scanTensorGet && tensor.io.result.fire){
      val response=tensor.io.result.bits;val t=response.tensor
      val hitsGate=overlap(t.address,t.paddedEnd,score.address,score.paddedEnd)
      val hitsUp=overlap(t.address,t.paddedEnd,probability.address,probability.paddedEnd)
      val gateUse=(r.scanPc===pc-2.U && r.scanSlot===2.U) ||
        Mux(attentionScan,r.scanPc===pc-1.U && r.scanSlot===0.U,r.scanPc===pc && r.scanSlot===0.U)
      val upUse=(r.scanPc===pc-1.U && r.scanSlot===2.U) ||
        (r.scanPc===pc && Mux(attentionScan,r.scanSlot===0.U,r.scanSlot===1.U))
      val exactGate=gateUse && sameAllocation(t,score)
      val exactUp=upUse && sameAllocation(t,probability)
      when(response.status=/=0.U){fail(response.status)}
      .elsewhen((hitsGate && !exactGate) || (hitsUp && !exactUp) || (gateUse && !exactGate) || (upUse && !exactUp)){fail(Status.Dependency.U)}
      .otherwise{
        when(r.scanSlot===2.U){
          when(r.scanPc+1.U===cfg.commands){
            // Capacity is widened; reserve both internal-only FULL allocations
            // atomically only after every public root has passed the preflight.
            // QK/Softmax already reserved these two spans sequentially.
            // FFN reserves its new pair only after this complete typed scan.
            when(attentionScan){state:=issue}
            .elsewhen(virtualCount+&2.U>maxCommands.U){fail(Status.Permission.U)}.otherwise{
              val first=virtualCount(log2Ceil(maxCommands)-1,0)
              val second=(virtualCount+1.U)(log2Ceil(maxCommands)-1,0)
              vStarts(first):=score.address;vEnds(first):=score.paddedEnd
              vStarts(second):=probability.address;vEnds(second):=probability.paddedEnd
              virtualCount:=virtualCount+2.U;state:=issue
            }
          }.otherwise{r.scanPc:=r.scanPc+1.U;state:=scanFetch}
        }.otherwise{r.scanSlot:=Mux(r.scanSlot===0.U && r.scanCmd(7,0)===0x33.U,2.U,r.scanSlot+1.U);state:=scanTensorIssue}
      }
    }
  }
  // No second host authorization or copied table is accepted here. This is
  // the actual validated cfg and semantic source-register view, valid only
  // within this accepted launch. Parent binds its full64 transaction beside
  // this exact snapshot; cfg.epoch alone is NOT globally unique identity.
  io.runtimeAuthority.accepted:=runtimeAccepted
  io.runtimeAuthority.launch:=cfg
  io.runtimeAuthority.transaction:=runtimeTransaction
  io.runtimeAuthority.identityExhausted:=runtimeIdentityExhausted
  io.runtimeAuthority.profile:=runtimeProfile
  io.runtimeAuthority.currentFault:=io.resetRequired || status=/=Status.Ok.U
  io.runtimeAuthority.ownerValidated:=runtimeAccepted && runtimeProfileKnown && cfg.version===HostCommandLaunchV4.Version.U && (state===issue || state===waitDone) && status===Status.Ok.U && !poison
  io.runtimeAuthority.ownerOffered:=io.job.valid
  io.runtimeAuthority.ownerAccepted:=io.job.fire
  io.runtimeAuthority.ownerJob:=io.job.bits
  io.runtimeAuthority.ownerReturned:=io.done.fire
  io.runtimeAuthority.ownerResult:=io.done.bits
  io.runtimeAuthority.ownerPostnormValidated:=io.runtimeAuthority.ownerValidated &&
    boundPostnorm && bound.kind===QwenOwnerKind.GdnRmsNorm.U &&
    (!boundRuntimePrefix || runtimePostnormIdentity)
  io.runtimeAuthority.ownerInputTensor:=boundInputTensor
  io.runtimeAuthority.postnormCommitValid:=postnormCurrent && postnormCommitValid && !io.runtimeAuthority.currentFault
  io.runtimeAuthority.postnormJob:=postnormJob;io.runtimeAuthority.postnormResult:=postnormResult
  io.runtimeAuthority.postnormResidual:=postnormResidual
  io.runtimeAuthority.postnormOutputTensor:=postnormOutputTensor
  io.runtimeAuthority.pc:=pc
  for(i<-0 until 16){
    io.runtimeAuthority.semanticSourceValid(i):=false.B
    io.runtimeAuthority.semanticSource(i):=0.U.asTypeOf(new DecodedTensor)
    if(i<sourceCount){
      io.runtimeAuthority.semanticSourceValid(i):=runtimeAccepted && sourceValid(i)
      io.runtimeAuthority.semanticSource(i):=sourceTensor(i)
    }
  }
  // ownerReturned is a raw actual transport event, NOT successful writeback:
  // parent must still check acceptedJob dst/tag/bytes/status and currentfault.
  when(io.result.fire){runtimeAccepted:=false.B;state:=Mux(poison,locked,idle)}
}
