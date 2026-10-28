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
class HostBlockTopV4(s:QwenBlockShape, weightReadBeats:Int=1,pipelined:Boolean=false,burstWrites:Boolean=false,commitTailRead:Boolean=false,overlapSilu:Boolean=false,bf16V:Boolean=false,bf16Qkv:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false,bf16QkNormRope:Boolean=false,bf16AttentionCore:Boolean=false,bf16AttentionBlock:Boolean=false,enableTransposedDown:Boolean=false,enableResidentFfn:Boolean=false,enablePublic21QkvReduction:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableProductionPackedQk16:Boolean=false,enableOrderedVectorQkFold:Boolean=false) extends Module {
  require(!enableOrderedVectorQkFold || enableProductionPackedQk16,"ordered vector QK fold requires packed QK16")
  require(!enablePublic21QkvReduction || (pipelined && enableResidentFfn && enableTransposedDown && Qwen2NumericPolicy.official(numericPolicy)),"public21 reduction requires the official resident profile")
  Qwen2NumericPolicy.checkShape(numericPolicy,s)
  require(!Qwen2NumericPolicy.official(numericPolicy) || (enableResidentFfn && pipelined && !bf16V && !bf16Qkv && !bf16Gdn && !bf16QkNormRope && !bf16AttentionCore),
    "official BF16 numerical policy requires the validated public21 Qwen2 chain")
  require(!enableResidentFfn || (enableTransposedDown && !overlapSilu && !bf16V && !bf16Qkv && !bf16Gdn && !bf16QkNormRope),
    "resident FFN is an explicit serial legacy Qwen2 execution profile")
  require(!enableTransposedDown || (pipelined && weightReadBeats==16 && !bf16Gdn && !bf16QkNormRope),
    "transposed Down requires the existing pipelined weight16 Qwen2 or V/QKV profile")
  require(!bf16AttentionBlock || bf16AttentionCore,"Attention block requires the explicit core profile")
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
    val launch=Flipped(Decoupled(new HostCommandLaunchV4));val result=Decoupled(new HostCommandResult)
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
  val cmd=Module(new HostBlockCommandsV4(s,bf16Weights=pipelined,bf16V=bf16V,bf16Qkv=bf16Qkv,bf16Gdn=bf16Gdn,bf16GdnCore=bf16GdnCore,bf16GdnBlock=bf16GdnBlock,bf16QkNormRope=bf16QkNormRope,bf16AttentionCore=bf16AttentionCore,bf16AttentionBlock=bf16AttentionBlock,enableTransposedDown=enableTransposedDown,enableResidentFfn=enableResidentFfn,numericPolicy=numericPolicy,enableRuntimeQkNorm=true,enableRuntimeRope=true,enableRuntimeKvAppend=true,enableRuntimeGqa=true,enableRuntimeOutput=true));val owner=Module(new QwenOwnerKernel(s,pipelined,burstWrites,overlapSilu,bf16Gdn,bf16GdnCore,bf16GdnBlock,bf16QkNormRope,bf16AttentionCore,bf16AttentionBlock,enableTransposedDense=enableTransposedDown,enableTransposedSeed=enableTransposedDown,enableTransposedDown=enableTransposedDown,enableFfnTiles=enableResidentFfn,enableFfnWindow=enableResidentFfn,enableFfnDrain=enableResidentFfn,enableResidentFfn=enableResidentFfn,enablePublic21QkvReduction=enablePublic21QkvReduction,numericPolicy=numericPolicy,enableProductionPackedQk16=enableProductionPackedQk16,enableOrderedVectorQkFold=enableOrderedVectorQkFold,enableUnifiedScalarService=true,enableRuntimeRmsNorm=true,enableRuntimeConv=true,enableRuntimeRawPrep=true,enableRuntimeChunk=true,enableRuntimeGatedNorm=true,enableRuntimeQkNorm=true,enableRuntimeRope=true,enableRuntimeKvAppend=true,enableRuntimeGqa=true,enableRuntimeElementwise=true))
  // Same ONE physical memory port/arbiter and one outstanding DMA transfer.
  // Five actual Chunk leaf users raise logical clients12->17 (5-bit selector).
  val hub=Module(new SharedMemoryArbiter(17))
  val moeLoop=Module(new UnifiedMoeRuntimeExpertLoopV4)
  val moeSigmoid=Module(new UnifiedMoeSharedGateSigmoidOwnerV5)
  val moeMerge=Module(new UnifiedMoePhaseMergeOwnerV5)
  val moeResidual=Module(new UnifiedMoePhaseResidualOwnerV5)
  val moeArithmetic=Module(new UnifiedMoeSharedArithmeticAdapterV5)
  val moeSelection=Module(new HostMoeSelectionServiceV5)
  moeArithmetic.io.coreScalar<>owner.io.sharedScalar.get
  moeSelection.io.client<>moeLoop.io.selection
  val phaseRoutingFault=Wire(Bool());val phaseArithmeticLeaseFault=Wire(Bool())
  val phaseArithmeticEventsPending=Wire(Bool())
  val phaseControlFault=Wire(Bool())
  val normAuthorityFault=Wire(Bool());val normMemoryFault=Wire(Bool())
  val normResourcesDrained=Wire(Bool());val normEventsPending=Wire(Bool())
  val chunkAuthorityFault=Wire(Bool());val chunkResourcesDrained=Wire(Bool());val chunkEventsPending=Wire(Bool())
  val phaseArithmeticDrained=moeArithmetic.io.resourcesDrained && !phaseArithmeticEventsPending &&
    !normEventsPending && normResourcesDrained && !chunkEventsPending && chunkResourcesDrained
  val phaseMemoryFault=Wire(Bool());val phaseMemoryPoison=RegInit(false.B)
  when(phaseMemoryFault){phaseMemoryPoison:=true.B}
  val phaseDenseDrained=Wire(Bool())
  val dmaPoison=Wire(Bool())
  val dmaDrained=Wire(Bool())
  if(enablePublic21QkvReduction){owner.io.public21BackendReset.get:=hub.io.resetRequired || dmaPoison}
  // Replace the ONE old guard, not parallel dispatch or duplicated resources.
  // The sole allocator consumes the original Commands' actual metadata event.
  val runtimeGuard=Module(new HostRuntimeOwnerGuardV5)
  val phaseAllocator=Module(new HostRuntimeMoePhaseAllocatorV5)
  HostMoePhaseControlV5.connectMetadata(cmd,runtimeGuard,phaseAllocator)
  // The second physical image comes from the SAME actual accepted metadata
  // event, never a Host pointer or a synthetic padding/grant flag. The logical
  // view remains in the actual lease; do not copy a full context or weight set.
  val n1ImageValid=RegInit(false.B)
  val n1PhysicalImage=Reg(new DecodedTensor)
  when(io.launch.fire){n1ImageValid:=false.B}
  when(cmd.io.moeSharedGateImage.valid){
    n1PhysicalImage:=cmd.io.moeSharedGateImage.bits.physicalWeight;n1ImageValid:=true.B
  }
  // Tail numerical owner installation must consume these only with this same
  // retained allocator lease and current fault veto, and clear on final release.

  val physicalFault=owner.io.resetRequired || hub.io.resetRequired || dmaPoison
  val physicalDrained=owner.io.resourcesDrained && hub.io.resourcesDrained && dmaDrained
  // Only registered event-derived lease faults feed admission. This avoids
  // begin.fire -> currentFault -> held-offer.valid -> begin.fire cycles.
  val arithmeticLeasePoison=RegNext(phaseArithmeticLeaseFault,false.B)
  val numericalFault=moeArithmetic.io.resetRequired || moeSelection.io.resetRequired ||
    phaseRoutingFault || arithmeticLeasePoison || phaseMemoryPoison || normAuthorityFault || normMemoryFault || chunkAuthorityFault
  val phaseFault=physicalFault || numericalFault || phaseControlFault || phaseMemoryFault
  // No reflected localFault -> authority.currentFault -> same localFault loop.
  cmd.io.moePhaseFault:=phaseFault || runtimeGuard.io.localFault || phaseAllocator.io.localFault
  runtimeGuard.io.transportDrained:=physicalDrained && phaseDenseDrained
  phaseAllocator.io.priorPhaseDrained:=physicalDrained && cmd.io.metadataDrained &&
    phaseArithmeticDrained && moeSelection.io.resourcesDrained
  phaseAllocator.io.physicalDrained:=physicalDrained && phaseDenseDrained &&
    phaseArithmeticDrained && moeSelection.io.resourcesDrained
  phaseAllocator.io.currentFault:=phaseFault
  val lifetime=HostMoePhaseLifetimeWiringV5.connect(cmd,runtimeGuard,phaseAllocator,
    moeLoop,moeSigmoid,moeMerge,moeResidual,n1ImageValid,n1PhysicalImage,
    physicalDrained && phaseDenseDrained,
    phaseArithmeticDrained && moeSelection.io.resourcesDrained,
    physicalFault || numericalFault)
  phaseControlFault:=lifetime.localFault
  val denseRouting=HostMoeDenseRoutingV5.connect(runtimeGuard,moeLoop,moeSigmoid,
    lifetime.lease,lifetime.active,physicalFault || arithmeticLeasePoison)
  phaseRoutingFault:=denseRouting.localFault;phaseDenseDrained:=denseRouting.resourcesDrained
  val arithmeticEvents=HostMoeArithmeticLeaseWiringV5.connect(moeArithmetic,
    lifetime.lease,lifetime.active,moeLoop,moeSigmoid,moeMerge,moeResidual)
  phaseArithmeticLeaseFault:=arithmeticEvents._1
  phaseArithmeticEventsPending:=arithmeticEvents._2
  // Fault feedback to numerical resource adapters is registered. Accepted/held
  // requests and replies still obey their own exact debt/identity contracts.
  moeArithmetic.io.externalPoison:=RegNext(physicalFault || lifetime.localFault || phaseRoutingFault,false.B)
  moeSelection.io.currentFault:=RegNext(physicalFault || lifetime.localFault || phaseRoutingFault,false.B)
  val routerAuthority=RegInit(false.B)
  when(moeLoop.io.acceptedLeaseFire){routerAuthority:=true.B}
  when(moeLoop.io.done.fire){routerAuthority:=false.B}
  moeSelection.io.authorityValid:=lifetime.active && routerAuthority
  moeSelection.io.authority:=0.U.asTypeOf(new UnifiedSharedOwnerIdentityV3)
  moeSelection.io.authority.transactionId:=lifetime.lease.context.transactionId
  moeSelection.io.authority.ownerSequence:=lifetime.lease.firstOwnerSequence
  moeSelection.io.authority.stage:=HostMoeArithmeticLeaseWiringV5.RouterStage.U
  // The N1 typed image remains live through residual/final dual release; no
  // internal FFN capture pulse or routed-only result clears it.
  when(cmd.io.moePhaseResult.fire && cmd.io.moePhaseResult.bits.resourcesRetired){n1ImageValid:=false.B}
  // Every constructor path gets the SAME two-sided launch poison gate. A new
  // launch may not enter while an earlier owner fault/unknown reply is live.
  // Held owner offers/results below remain stable and are not cancelled.
  val launchPoison=cmd.io.resetRequired||owner.io.resetRequired||hub.io.resetRequired||dmaPoison||runtimeGuard.io.resetRequired||phaseAllocator.io.resetRequired||phaseFault
  cmd.io.launch.valid:=io.launch.valid && !launchPoison
  cmd.io.launch.bits:=io.launch.bits
  io.launch.ready:=cmd.io.launch.ready && !launchPoison
  if(enableTransposedDown){owner.io.prefixWorkspace.get:=cmd.io.prefixWorkspace.get}
  io.result<>cmd.io.result;io.completion<>cmd.io.completion
  runtimeGuard.io.authority:=cmd.io.runtimeAuthority
  runtimeGuard.io.globalFault:=cmd.io.resetRequired || owner.io.resetRequired || hub.io.resetRequired || dmaPoison || numericalFault || phaseControlFault
  runtimeGuard.io.job<>cmd.io.job;cmd.io.done<>runtimeGuard.io.done
  owner.io.job<>runtimeGuard.io.physicalJob;runtimeGuard.io.physicalDone<>owner.io.done
  // Exclude ONLY the current arithmetic adapter reflection: it already gates
  // new captures internally. All unrelated current faults remain immediate.
  // Commands exposes its actual local/sticky parser terms, not a Host grant.
  val ordinaryAdmissionFault=physicalFault || moeSelection.io.resetRequired || phaseRoutingFault ||
    arithmeticLeasePoison || phaseMemoryPoison || phaseMemoryFault || phaseControlFault ||
    phaseAllocator.io.localFault || normMemoryFault || cmd.io.parserLocalFault
  // Current fault vetoes FIRST Matrix publication, not a held group/step.
  // Read-only private input; no Host grant or second Matrix exists.
  owner.io.runtimeGqaMatrixFault.get:=ordinaryAdmissionFault || runtimeGuard.io.localFault || cmd.io.runtimeAuthority.currentFault
  val prefixScalar=Wire(new UnifiedScalarClientV2)
  val chunkStaged=Wire(Valid(new GdnRuntimeChunkStagedReceiptV10))
  val normLease=HostRuntimePrefixLeaseWiringV8.connect(moeArithmetic,runtimeGuard,cmd.io.runtimeAuthority,owner,
    ordinaryAdmissionFault,prefixScalar,chunkStaged)
  cmd.io.runtimePostnormReceipt:=normLease.postnormReceipt
  owner.io.runtimeChunk.get.committed:=cmd.io.runtimeChunkCommitted
  val chunkLease=HostRuntimeChunkWiringV9.connect(moeArithmetic,runtimeGuard,cmd.io.runtimeAuthority,owner,
    normLease,prefixScalar,hub,ordinaryAdmissionFault)
  chunkStaged:=chunkLease.stagedReceipt
  chunkAuthorityFault:=chunkLease.localFault;chunkResourcesDrained:=chunkLease.resourcesDrained
  chunkEventsPending:=chunkLease.eventsPending
  normAuthorityFault:=normLease.localFault;normResourcesDrained:=normLease.resourcesDrained
  normEventsPending:=normLease.eventsPending
  // Error reflection is registered; the independent Top memory and arithmetic
  // admission fences below stop fresh effects immediately, preserving held ones.
  owner.io.runtimeRms.get.parentFault:=RegNext(phaseFault || runtimeGuard.io.localFault,false.B)
  if(enableResidentFfn){
    owner.io.resident.get<>cmd.io.resident.get
    owner.io.resident.get.abort:=cmd.io.resident.get.abort || RegNext(hub.io.resetRequired || dmaPoison,false.B)
    cmd.io.resident.get.resetRequired:=owner.io.resident.get.resetRequired || owner.io.resetRequired || hub.io.resetRequired || dmaPoison
  }
  hub.io.requests(0)<>cmd.io.memory;cmd.io.response<>hub.io.responses(0)
  // Original non-prefix owner path stays direct. Runtime RMS/Conv/RawPrep writes gain the
  // same first-publication/held distinction as the already-installed phase.
  val nr=owner.io.memory;val nj=normLease.job
  val naddr=nr.bits.address.pad(80);val nend=naddr+64.U
  val prepJob=nj.kind===QwenOwnerKind.GdnInputPrep.U
  val gatedJob=nj.kind===QwenOwnerKind.GdnGatedNorm.U
  val qkNormJob=nj.kind===QwenOwnerKind.QkNorm256.U
  val ropeJob=nj.kind===QwenOwnerKind.PartialRope64.U
  val kvJob=nj.kind===QwenOwnerKind.KvAppend.U
  val gqaJob=nj.kind===QwenOwnerKind.Attention.U
  val elementJob=nj.kind===QwenOwnerKind.GdnElementwise.U
  val rmsJob=nj.kind===QwenOwnerKind.GdnRmsNorm.U
  val gqaCacheBytes=nj.cacheCapacity.pad(80)<<11
  val kvPlaneBytes=nj.m.pad(80)<<10
  val kvPlaneStride=nj.cacheCapacity.pad(80)<<10
  val kvTailOffset=nj.queryStart.pad(80)<<10
  val ropeTrigBytes=nj.qkTrigTokens.pad(80)<<7
  val qkNormBytes=(nj.m.pad(80)*nj.n.pad(80))<<9
  val nbytes=Mux(qkNormJob || ropeJob,qkNormBytes,Mux(gatedJob,(nj.m.pad(80)*nj.n.pad(80))<<8,
    Mux(prepJob,nj.m.pad(80)*nj.n.pad(80)*1600.U,(nj.m.pad(80)*nj.n.pad(80))<<1)))
  val rawPrepBytes=(nj.m.pad(80)*(nj.n.pad(80)+32.U))<<8
  val prepAbBytes=(nj.m.pad(80)*nj.n.pad(80))<<2
  val prepALogBytes=nj.n.pad(80)<<2
  val convJob=nj.kind===QwenOwnerKind.GdnConv.U
  val stateBytes=nj.n.pad(80)<<3;val wbytes=Mux(convJob,stateBytes,nj.n.pad(80)<<1)
  def nwithin(base:UInt,bytes:UInt):Bool=naddr>=base.pad(80) && nend<=base.pad(80)+bytes
  val nrights=normLease.host.regions.map(r=>naddr>=r.base.pad(80) && nend<=r.limit.pad(80) &&
    Mux(nr.bits.write,r.write,r.read)).reduce(_||_)
  val nlegal=normLease.owned && nr.bits.address(5,0)===0.U && nend<=(BigInt(1)<<56).U &&
    nr.bits.tag(63,32)===nj.tag && nrights &&
    Mux(nr.bits.write,(Mux(kvJob,
      nwithin(nj.dst.pad(80)+kvTailOffset,kvPlaneBytes) || nwithin(nj.dst.pad(80)+kvPlaneStride+kvTailOffset,kvPlaneBytes),
      nwithin(nj.dst,nbytes)) || (qkNormJob && nj.qkRole===0.U && nwithin(nj.c,qkNormBytes)) || (convJob && nwithin(nj.historyOut,stateBytes))) && nr.bits.mask.andR,
      Mux(elementJob,nwithin(nj.a,nbytes) || nwithin(nj.b,nbytes),
      Mux(gqaJob,nwithin(nj.a,nbytes) || nwithin(nj.b,gqaCacheBytes),
      Mux(kvJob,nwithin(nj.a,kvPlaneBytes) || nwithin(nj.b,kvPlaneBytes),
      Mux(ropeJob,nwithin(nj.a,qkNormBytes) || nwithin(nj.b,ropeTrigBytes),
      Mux(qkNormJob,nwithin(nj.a,Mux(nj.qkRole===0.U,qkNormBytes<<1,qkNormBytes)) || nwithin(nj.b,512.U),
      Mux(gatedJob,nwithin(nj.a,nbytes) || nwithin(nj.b,nbytes) || nwithin(nj.c,512.U),
      Mux(prepJob,
        nwithin(nj.a,rawPrepBytes) || nwithin(nj.b,prepAbBytes) || nwithin(nj.gdnALog,prepALogBytes) || nwithin(nj.gdnDtBias,64.U),
        nwithin(nj.a,nbytes) || nwithin(nj.b,wbytes) || (convJob && !nj.cold && nwithin(nj.c,stateBytes))))))))) && nr.bits.mask===0.U)
  normMemoryFault:=normLease.owned && nr.valid && !nlegal
  val normPublish=HeldDecoupledOffer(normLease.owned && nr.valid && nlegal,hub.io.requests(1).ready,
    phaseFault || runtimeGuard.io.localFault || cmd.io.runtimeAuthority.currentFault)
  hub.io.requests(1).valid:=Mux(normLease.owned,normPublish.valid,nr.valid)
  hub.io.requests(1).bits:=nr.bits
  nr.ready:=hub.io.requests(1).ready && Mux(normLease.owned,normPublish.valid,true.B)
  owner.io.response<>hub.io.responses(1)
  // Read-only observations of the actual existing service-port visibility.
  // A suppressed local intent is not a held external obligation.
  owner.io.runtimeGqaPublished.get.memory:=normLease.owned && gqaJob && hub.io.requests(1).valid
  owner.io.runtimeGqaPublished.get.scalar:=normLease.owned && gqaJob && moeArithmetic.io.scalar(3).request.valid
  owner.io.runtimeRmsPublished.get.memory:=normLease.owned && rmsJob && hub.io.requests(1).valid
  owner.io.runtimeRmsPublished.get.scalar:=normLease.owned && rmsJob && moeArithmetic.io.scalar(3).request.valid
  owner.io.runtimeRmsPublished.get.format:=normLease.owned && rmsJob && moeArithmetic.io.formatRequest(3).valid
  owner.io.runtimeElementwisePublished.get.memory:=normLease.owned && elementJob && hub.io.requests(1).valid
  owner.io.runtimeElementwisePublished.get.scalar:=normLease.owned && elementJob && moeArithmetic.io.scalar(3).request.valid
  owner.io.runtimeElementwisePublished.get.format:=normLease.owned && elementJob && moeArithmetic.io.formatRequest(3).valid
  // Ten real phase clients use that SAME arbiter. Original client tags can
  // repeat locally: the arbiter owns nonreused physical transport tags and
  // restores each original tag only to the captured client on real response.
  val phaseMemory=Seq(moeLoop.io.routerReadMemory,moeLoop.io.routeMapMemory,
    moeLoop.io.gatherMemory,moeLoop.io.activationMemory,moeLoop.io.descriptorMemory,
    moeSigmoid.io.memory,moeMerge.io.metadataMemory,moeMerge.io.dataMemory,
    moeMerge.io.memory,moeResidual.io.memory)
  val phaseResponse=Seq(moeLoop.io.routerReadResponse,moeLoop.io.routeMapResponse,
    moeLoop.io.gatherResponse,moeLoop.io.activationResponse,moeLoop.io.descriptorResponse,
    moeSigmoid.io.response,moeMerge.io.metadataResponse,moeMerge.io.dataResponse,
    moeMerge.io.response,moeResidual.io.response)
  // Real accepted region rights AND actual fixed phase views. These checks
  // never turn a Host base or matching packet into a lease. The same retained
  // lease and leaf-held payload must persist until an exposed request fires.
  val memoryLegal=phaseMemory.map{r=>
    val address=r.bits.address.pad(80);val end=address+64.U
    val l=lifetime.lease
    val rights=l.context.host.regions.map(g=>address>=g.base.pad(80) && end<=g.limit.pad(80) &&
      Mux(r.bits.write,g.write,g.read)).reduce(_||_)
    val scratch=HostMoePhaseLayoutV4.Regions.map{case(o,n)=>
      address>=l.allocationBase.pad(80)+o.U && end<=l.allocationBase.pad(80)+(o+n).U}.reduce(_||_)
    def within(t:DecodedTensor):Bool=address>=t.address.pad(80) && end<=t.paddedEnd.pad(80)
    val liveView=within(l.context.output) || (!r.bits.write &&
      (within(l.context.input)||within(l.context.residual)))
    lifetime.active && r.bits.address(5,0)===0.U && end<=(BigInt(1)<<56).U && rights && (scratch||liveView)
  }
  phaseMemoryFault:=phaseMemory.indices.map(i=>phaseMemory(i).valid && !memoryLegal(i)).reduce(_||_)
  // Distinguish a real previously published hub offer from a leaf-local
  // request created after fault (for example prepareWrite -> offerMemory).
  // Ten existing HeldDecoupledOffer bits, no copied payload or new queue:
  // current faults veto FIRST visibility, not an already-visible held offer.
  val newMemoryFault=phaseFault || phaseArithmeticLeaseFault || phaseMemoryFault ||
    runtimeGuard.io.localFault || phaseAllocator.io.localFault ||
    cmd.io.runtimeAuthority.currentFault || moeLoop.io.resetRequired ||
    moeSigmoid.io.resetRequired || moeMerge.io.resetRequired || moeResidual.io.resetRequired
  for(i<-phaseMemory.indices){
    val requestOffer=HeldDecoupledOffer(phaseMemory(i).valid && memoryLegal(i),
      hub.io.requests(i+2).ready,newMemoryFault)
    hub.io.requests(i+2).valid:=requestOffer.valid
    hub.io.requests(i+2).bits:=phaseMemory(i).bits
    phaseMemory(i).ready:=hub.io.requests(i+2).ready && requestOffer.valid
    phaseResponse(i)<>hub.io.responses(i+2)
  }
  val transportReset=hub.io.resetRequired || dmaPoison
  moeLoop.io.routerReadResetRequired:=transportReset;moeLoop.io.routeMapResetRequired:=transportReset
  moeLoop.io.gatherResetRequired:=transportReset;moeLoop.io.activationResetRequired:=transportReset
  moeLoop.io.descriptorResetRequired:=transportReset;moeSigmoid.io.memoryResetRequired:=transportReset
  moeMerge.io.metadataResetRequired:=transportReset;moeMerge.io.dataResetRequired:=transportReset
  moeMerge.io.memoryResetRequired:=transportReset;moeResidual.io.memoryResetRequired:=transportReset

  if(weightReadBeats==1){
    val dma=Module(new RetainedIdmaMemoryAdapter)
    dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
    dmaPoison:=dma.io.resetRequired;dmaDrained:=dma.io.resourcesDrained;io.idmaTransfers:=dma.io.transfers
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
    if(enableResidentFfn){when(owner.io.residentHandoff.get.valid){
      val job=owner.io.residentHandoff.get.bits
      val weightBytes=Mux(job.weightBf16,2.U(3.W),4.U(3.W))
      val end=job.b.pad(66)+(job.n.pad(66)*job.k.pad(66)*weightBytes)
      window.enable:=job.kind===QwenOwnerKind.Dense.U && end<=(BigInt(1)<<56).U
      window.base:=job.b;window.limit:=end(63,0)
    }}
    dma.io.window:=window
    if(pipelined){dma.io.streamRequest.get<>owner.io.burst.get;owner.io.burstResponse.get<>dma.io.streamResponse.get}
    if(burstWrites){dma.io.streamWriteRequest.get<>owner.io.writeRequest.get;dma.io.streamWriteData.get<>owner.io.writeData.get;owner.io.writeResponse.get<>dma.io.streamWriteResponse.get}
    io.idmaStreamedWriteBeats:=dma.io.streamedWriteBeats
    io.idmaStreamedBeats:=dma.io.streamedBeats
    dma.io.flush:=io.launch.fire||owner.io.job.fire||owner.io.done.fire
    if(enableResidentFfn){dma.io.flush:=io.launch.fire||owner.io.job.fire||owner.io.done.fire||owner.io.residentHandoff.get.valid}
    dma.io.request<>hub.io.memory;hub.io.response<>dma.io.response;io.axi<>dma.io.axi
    dmaPoison:=dma.io.resetRequired;dmaDrained:=dma.io.resourcesDrained;io.idmaTransfers:=dma.io.transfers
    io.idmaReadBursts:=dma.io.readBursts;io.idmaReadBeats:=dma.io.readBeats;io.idmaCacheHits:=dma.io.cacheHits
  }
  io.resetRequired:=cmd.io.resetRequired||owner.io.resetRequired||hub.io.resetRequired||dmaPoison||runtimeGuard.io.resetRequired||phaseAllocator.io.resetRequired||phaseFault||phaseArithmeticLeaseFault||phaseMemoryFault
  io.pc:=cmd.io.pc;io.issuedJobs:=cmd.io.issuedJobs
  io.usefulMacs:=cmd.io.usefulMacs;io.executedMacs:=cmd.io.executedMacs;io.writeBytes:=cmd.io.writeBytes
  io.pipelineIssues:=owner.io.pipelineIssues;io.pipelineStalls:=owner.io.pipelineStalls
  // Preserve the external two-bucket diagnostic ABI: metadata vs ALL compute.
  // Wider sums expose saturation rather than silently wrapping. These are
  // diagnostics, never credits, permissions, or a resource-drained proof.
  def computeTotal(v:Vec[UInt]):UInt={
    val wide=v.drop(1).map(_.pad(68)).reduce(_+_)
    Mux(wide>"hffffffffffffffff".U(68.W),"hffffffffffffffff".U(64.W),wide(63,0))
  }
  io.memoryAccepted(0):=hub.io.accepted(0);io.memoryReturned(0):=hub.io.returned(0)
  io.memoryAccepted(1):=computeTotal(hub.io.accepted);io.memoryReturned(1):=computeTotal(hub.io.returned)
}
