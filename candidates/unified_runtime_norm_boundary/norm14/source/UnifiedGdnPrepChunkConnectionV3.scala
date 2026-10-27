// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private original-scheduler assignment. region is the SAME accepted Host
  * region3 snapshot, not a host-writable grant Boolean. This component retains
  * actual admission context and issues norm with its exact input/dst/sequence,
  * then accepts only the real norm result handshake;
  * the one runtime fixed-bank norm owner below performs all arithmetic through
  * shared resources; there is no external host completion input. */
class UnifiedGdnOriginalAssignmentV3 extends Bundle {
  val block=new UnifiedBlockDispatchV1
  val workspace=new Region
  val qkvWeight=UInt(64.W);val abWeight=UInt(64.W)
  val normWeight=UInt(64.W);val convWeight=UInt(64.W);val aLog=UInt(64.W);val dtBias=UInt(64.W)
  val historyIn=UInt(64.W)
  val firstOwnerSequence=UInt(32.W)
}
class UnifiedGdnOriginalStagedResultV3 extends Bundle {
  val transactionId=UInt(64.W);val status=UInt(8.W)
  val chunk=new UnifiedGdnBoundResultV3
  val conv=new GdnConv4Result
  val nextOwnerSequence=UInt(32.W)
  val drained=Bool();val resetRequired=Bool()
}

/** Real command/data path back into the original single Dense feeder:
  * actual norm job/result ACK -> QKV Dense write ACK -> AB Dense write ACK -> actual Conv4 owner -> actual
  * RawPrepV2 owner -> actual chunk router/collection. This owns NO Matrix,
  * Scalar or Vector instance. denseCommand/result must connect to the ONE
  * existing UnifiedOriginalDenseClientV2, not a second feeder per profile.
  * Four resource-client ports join the common epoch/scalar arbiters; their
  * actual live drain feeds the final fence. Output is private staged completion,
  * NOT final GDN gatednorm/projection/residual or a complete block result.
  */
class UnifiedGdnPrepChunkConnectionV3 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedGdnOriginalAssignmentV3))
    val contextActive=Input(Bool()) // actual original admission, never host authorization
    val activeContext=Input(new UnifiedBlockDispatchV1)
    val denseCommand=Decoupled(new UnifiedRuntimeDenseCommandV2)
    val denseResult=Flipped(Decoupled(new UnifiedRuntimeDenseResultV2))
    val committed=Input(new GdnChunkCommittedState)
    val convCommitted=Input(new GdnChunkCommittedState) // actual independent history root
    val memory=Vec(4,new GdnRuntimeChunkMemoryClient) // Conv,RawPrep,Chunk,Norm
    val scalar=Vec(4,new UnifiedScalarClientV2)
    val formatRequest=Decoupled(new UnifiedRawFp32FormatRequestV3)
    val formatResult=Flipped(Decoupled(new UnifiedRawFp32FormatResultV3))
    val vectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    val transportDrained=Input(Bool()) // actual common memory/scalar/vector debts, NOT !block.busy
    val currentFabricFault=Input(Bool())
    val done=Decoupled(new UnifiedGdnOriginalStagedResultV3)
    val reserved=Output(Bool());val resetRequired=Output(Bool())
  })
  val norm=Module(new GdnRuntimeRmsNormOwnerV3) // replaces original GDN RMS owner, never a parallel numeric unit
  val conv=Module(new GdnRuntimeConv4Owner)
  val prep=Module(new GdnRuntimeInputPrepScalarV2Owner)
  val chunk=Module(new UnifiedGdnRuntimeRouterV3)
  val states=Enum(15)
  val idle=states(0);val qIssue=states(1);val qWait=states(2);val abIssue=states(3);val abWait=states(4)
  val convIssue=states(5);val convWait=states(6);val chunkIssue=states(7);val prepIssue=states(8)
  val running=states(9);val failureDrain=states(10);val report=states(11);val locked=states(12)
  val normIssue=states(13);val normWait=states(14)
  val state=RegInit(idle);val accepted=Reg(new UnifiedGdnOriginalAssignmentV3)
  val plan=Reg(new UnifiedGdnScratchPlanV3);val nextSequence=Reg(UInt(32.W))
  val convResult=Reg(new GdnConv4Result);val prepReceipt=Reg(new GdnRuntimeInputPrepResult)
  val prepHeld=RegInit(false.B);val terminal=Reg(new UnifiedGdnOriginalStagedResultV3)
  val historySnapshot=Reg(new GdnChunkCommittedState)
  val normOwned=RegInit(false.B);val denseOwned=RegInit(false.B)
  val convOwned=RegInit(false.B);val prepOwned=RegInit(false.B);val chunkOwned=RegInit(false.B)
  val prepPublished=RegInit(false.B)
  val normActivated=RegInit(false.B);val chunkActivated=RegInit(false.B)
  val anyOwned=normOwned || denseOwned || convOwned || prepOwned || chunkOwned
  val poison=RegInit(false.B);val failureStatus=RegInit(Status.Ok.U(8.W))
  val rawUnknownNorm=norm.io.done.valid && (!normOwned || state=/=normWait || norm.io.done.bits.tag=/=nextSequence)
  val rawUnknownConv=conv.io.done.valid && (!convOwned || state=/=convWait || conv.io.done.bits.tag=/=accepted.block.launch.tag)
  val rawUnknownPrep=prep.io.done.valid && (!prepOwned || state=/=running || prep.io.done.bits.tag=/=accepted.block.launch.tag || prep.io.done.bits.accepted.asUInt=/=prep.io.job.bits.asUInt)
  val rawUnknownChunk=chunk.io.done.valid && (!chunkOwned || !(state===prepIssue || state===running) ||
    chunk.io.done.bits.transactionId=/=accepted.block.transactionId ||
    chunk.io.done.bits.profileId=/=accepted.block.launch.profileId ||
    chunk.io.done.bits.result.accepted.asUInt=/=chunk.io.begin.bits.job.asUInt)
  val contextChanged=state=/=idle && state=/=locked &&
    !UnifiedAcceptedContextV3.matches(io.contextActive,io.activeContext,accepted.block)
  val expectedDenseRole=Mux(state===abWait,UnifiedDenseRoleV2.GdnAB.U,UnifiedDenseRoleV2.MixerInput.U)
  val rawUnknownDense=io.denseResult.valid && (!denseOwned || !(state===qWait || state===abWait) ||
    io.denseResult.bits.transactionId=/=accepted.block.transactionId || io.denseResult.bits.result.tag=/=nextSequence || io.denseResult.bits.role=/=expectedDenseRole)
  val historyChanged=state=/=idle && state=/=locked && io.convCommitted.asUInt=/=historySnapshot.asUInt
  val currentFault=io.currentFabricFault || contextChanged || historyChanged || rawUnknownNorm || rawUnknownConv || rawUnknownPrep || rawUnknownChunk || norm.io.resetRequired || rawUnknownDense || conv.io.resetRequired || prep.io.resetRequired || chunk.io.resetRequired
  when(currentFault){poison:=true.B}
  io.resetRequired:=poison || currentFault
  io.reserved:=state=/=idle || io.begin.valid
  io.begin.ready:=state===idle && !poison && !currentFault
  io.done.valid:=state===report;io.done.bits:=terminal
  val b=io.begin.bits;val decoded=UnifiedGdnScratchPlanV3.decode(b.block)
  val acceptedContextOK=UnifiedAcceptedContextV3.matches(io.contextActive,io.activeContext,b.block)
  val arena=b.workspace
  val historyOK=Mux(b.block.launch.cold,!io.convCommitted.valid && io.convCommitted.generation===0.U,
    io.convCommitted.valid && io.convCommitted.generation===b.block.launch.expectedGeneration && io.convCommitted.state===b.historyIn)
  val arenaOK=arena.read && arena.write && arena.base<=b.block.launch.scratch &&
    arena.limit>=decoded.end && arena.base<arena.limit && arena.limit<=(BigInt(1)<<56).U &&
    arena.base(5,0)===0.U && arena.limit(5,0)===0.U
  // Exact protected spans. Full typed weight/region permissions and norm-source
  // authority remain required at the original Host decoder, not inferred here.
  val h=b.block.profile.hidden;val heads=b.block.profile.gdnValueHeads;val m=b.block.launch.tokens
  val channels=(heads+&32.U)<<7
  val protectedSpans=Seq(
    (b.block.launch.input,(m.pad(80)*h)<<1),(b.block.launch.output,(m.pad(80)*h)<<1),
    (b.block.launch.stateIn,heads.pad(80)<<16),(b.block.launch.stateOut,heads.pad(80)<<16),
    (b.qkvWeight,(h.pad(80)*channels)<<1),(b.abWeight,(h.pad(80)*heads)<<2),
    (b.normWeight,h.pad(80)<<1),(b.convWeight,channels.pad(80)<<3),(b.aLog,heads.pad(80)<<2),(b.dtBias,64.U(80.W)),
    (b.historyIn,channels.pad(80)<<3))
  val protectedOK=protectedSpans.map{case(base,size)=>base(5,0)===0.U &&
    base.pad(80)+size<=(BigInt(1)<<56).U &&
    !(base.pad(80)<decoded.end.pad(80) && b.block.launch.scratch.pad(80)<base.pad(80)+size)}.reduce(_&&_)
  when(io.begin.fire){
    accepted:=b;historySnapshot:=io.convCommitted;plan:=decoded;nextSequence:=b.firstOwnerSequence;prepHeld:=false.B;prepPublished:=false.B;normActivated:=false.B;chunkActivated:=false.B
    terminal:=0.U.asTypeOf(new UnifiedGdnOriginalStagedResultV3);terminal.transactionId:=b.block.transactionId
    when(!acceptedContextOK){terminal.status:=Status.Dependency.U;terminal.drained:=true.B;state:=report}
      .elsewhen(!decoded.boundsLegal || !arenaOK || !protectedOK || !historyOK || b.firstOwnerSequence==="hffffffff".U){terminal.status:=Status.Bounds.U;terminal.drained:=true.B;state:=report}
      .elsewhen(!decoded.implementedRecipe){terminal.status:=Status.Unsupported.U;terminal.drained:=true.B;state:=report}
      .otherwise{state:=normIssue}
  }
  val normOffer=HeldDecoupledOffer(state===normIssue,norm.io.job.ready,poison || currentFault)
  norm.io.job.valid:=normOffer.valid
  norm.io.job.bits.reductionRecipe:=1.U // accepted GDN CPU-default8lane/4residue recipe, never host-selected
  norm.io.job.bits.tokens:=accepted.block.launch.tokens;norm.io.job.bits.hiddenWidth:=accepted.block.profile.hidden
  norm.io.job.bits.input:=accepted.block.launch.input;norm.io.job.bits.weight:=accepted.normWeight
  norm.io.job.bits.output:=plan.normalized;norm.io.job.bits.tag:=nextSequence
  when(norm.io.job.fire){normOwned:=true.B;normActivated:=true.B;state:=normWait}
  norm.io.done.ready:=state===normWait && normOwned && !rawUnknownNorm && io.transportDrained
  when(norm.io.done.fire){
    normOwned:=false.B
    val n=norm.io.done.bits
    val bytes=(accepted.block.launch.tokens.pad(64)*accepted.block.profile.hidden)<<1
    val bad=n.tag=/=nextSequence || n.status=/=Status.Ok.U || !n.outputCommitted ||
      n.writeBytes=/=bytes || poison || currentFault || nextSequence==="hfffffffe".U
    when(bad){poison:=true.B;failureStatus:=Status.Protocol.U;state:=failureDrain}
      .otherwise{nextSequence:=nextSequence+1.U;state:=qIssue}
  }
  val denseOffer=HeldDecoupledOffer(state===qIssue || state===abIssue,io.denseCommand.ready,poison || currentFault)
  io.denseCommand.valid:=denseOffer.valid
  io.denseCommand.bits.context:=accepted.block
  io.denseCommand.bits.role:=Mux(state===abIssue,UnifiedDenseRoleV2.GdnAB.U,UnifiedDenseRoleV2.MixerInput.U)
  io.denseCommand.bits.input:=plan.normalized
  io.denseCommand.bits.weight:=Mux(state===abIssue,accepted.abWeight,accepted.qkvWeight)
  io.denseCommand.bits.output:=Mux(state===abIssue,plan.ab,plan.projection)
  io.denseCommand.bits.firstOwnerSequence:=nextSequence
  when(io.denseCommand.fire){denseOwned:=true.B;state:=Mux(state===abIssue,abWait,qWait)}
  io.denseResult.ready:=(state===qWait || state===abWait) && denseOwned && !rawUnknownDense
  when(io.denseResult.fire){
    denseOwned:=false.B
    val r=io.denseResult.bits
    val expectedRole=Mux(state===abWait,UnifiedDenseRoleV2.GdnAB.U,UnifiedDenseRoleV2.MixerInput.U)
    val n=Mux(state===abWait,accepted.block.profile.gdnValueHeads<<1,(accepted.block.profile.gdnValueHeads+&32.U)<<7)
    val bytes=(accepted.block.launch.tokens.pad(64)*n)<<1
    val bad=r.transactionId=/=accepted.block.transactionId || r.role=/=expectedRole || r.result.tag=/=nextSequence ||
      r.result.status=/=Status.Ok.U || r.result.writeBytes=/=bytes || !r.drained || r.resetRequired || poison || currentFault
    when(bad){poison:=true.B;failureStatus:=Status.Protocol.U;state:=failureDrain}
      .otherwise{nextSequence:=r.nextOwnerSequence;state:=Mux(state===abWait,convIssue,abIssue)}
  }
  val convOffer=HeldDecoupledOffer(state===convIssue,conv.io.job.ready,poison || currentFault)
  conv.io.job.valid:=convOffer.valid;conv.io.job.bits:=0.U.asTypeOf(new GdnConv4Job)
  conv.io.job.bits.tokens:=accepted.block.launch.tokens
  conv.io.job.bits.channels:=(accepted.block.profile.gdnValueHeads+&32.U)<<7
  conv.io.job.bits.input:=plan.projection;conv.io.job.bits.weight:=accepted.convWeight
  conv.io.job.bits.historyIn:=accepted.historyIn;conv.io.job.bits.historyOut:=plan.historyOut
  conv.io.job.bits.output:=plan.convolved;conv.io.job.bits.cold:=accepted.block.launch.cold
  conv.io.job.bits.expectedGeneration:=accepted.block.launch.expectedGeneration;conv.io.job.bits.tag:=accepted.block.launch.tag
  conv.io.currentGeneration:=io.convCommitted.generation
  when(conv.io.job.fire){convOwned:=true.B;state:=convWait}
  conv.io.done.ready:=state===convWait && convOwned && !rawUnknownConv && io.transportDrained
  when(conv.io.done.fire){
    convOwned:=false.B
    convResult:=conv.io.done.bits
    val ch=(accepted.block.profile.gdnValueHeads.pad(64)+32.U)<<7
    val bytes=(accepted.block.launch.tokens.pad(64)*ch<<1)+(ch<<3)
    val bad=conv.io.done.bits.tag=/=accepted.block.launch.tag || conv.io.done.bits.status=/=Status.Ok.U ||
      !conv.io.done.bits.historyCommitted || conv.io.done.bits.writeBytes=/=bytes || poison || currentFault
    when(bad){poison:=true.B;failureStatus:=Status.Protocol.U;state:=failureDrain}.otherwise{state:=chunkIssue}
  }
  val chunkOffer=HeldDecoupledOffer(state===chunkIssue,chunk.io.begin.ready,poison || currentFault)
  chunk.io.begin.valid:=chunkOffer.valid;chunk.io.begin.bits:=0.U.asTypeOf(new UnifiedGdnBoundJobV3)
  chunk.io.begin.bits.block:=accepted.block
  val j=chunk.io.begin.bits.job
  j.context.tag:=accepted.block.launch.tag;j.context.tokens:=accepted.block.launch.tokens
  j.context.cold:=accepted.block.launch.cold;j.context.expectedGeneration:=accepted.block.launch.expectedGeneration
  j.context.vectorPolicy:=plan.vectorContextPolicy;j.context.input:=plan.prepared
  j.context.stateIn:=accepted.block.launch.stateIn;j.context.stateOut:=accepted.block.launch.stateOut
  j.context.output:=plan.core;j.context.scratch:=plan.chunk
  j.layout:=plan.layout;j.numeric:=plan.numeric;j.prepReductionPolicy:=plan.prepReduction;j.prepGatePolicy:=plan.prepGate
  when(chunk.io.begin.fire){chunkOwned:=true.B;chunkActivated:=true.B;state:=prepIssue}
  // Do not create new prep work when the already-started chunk reports an
  // early rejection. An offer already held cannot be canceled by this gate.
  // If rejection races such a held offer, keep its debt and require explicit
  // isolation; never consume/drop a held preparation receipt to invent drain.
  val prepOffer=HeldDecoupledOffer(state===prepIssue,prep.io.job.ready,poison || currentFault || chunk.io.done.valid)
  prep.io.job.valid:=prepOffer.valid;prep.io.job.bits:=0.U.asTypeOf(new GdnRuntimeInputPrepJob)
  prep.io.job.bits.tokens:=accepted.block.launch.tokens;prep.io.job.bits.layout:=plan.layout
  prep.io.job.bits.reductionPolicy:=plan.prepReduction;prep.io.job.bits.gatePolicy:=plan.prepGate
  prep.io.job.bits.conv:=plan.convolved;prep.io.job.bits.ab:=plan.ab
  prep.io.job.bits.aLog:=accepted.aLog;prep.io.job.bits.dtBias:=accepted.dtBias
  prep.io.job.bits.output:=plan.prepared;prep.io.job.bits.tag:=accepted.block.launch.tag
  when(prep.io.job.fire){prepOwned:=true.B;state:=running}
  prep.io.done.ready:=state===running && prepOwned && !rawUnknownPrep && !prepHeld && io.transportDrained
  when(prep.io.done.fire){prepOwned:=false.B;prepReceipt:=prep.io.done.bits;prepHeld:=true.B}
  chunk.io.prepDone.valid:=prepHeld;chunk.io.prepDone.bits:=prepReceipt
  when(chunk.io.prepDone.fire){prepHeld:=false.B;prepPublished:=true.B}
  chunk.io.committed:=io.committed;chunk.io.parentPoison:=poison
  chunk.io.done.ready:=(state===prepIssue || state===running) && chunkOwned && !rawUnknownChunk && !prepOwned && !prepHeld && !prep.io.job.valid && io.transportDrained
  // Physical quiet is not a leaf quarantine fence. A never-activated child
  // has no job debt only while it also exposes no current/sticky fault or
  // terminal. Once activated (including after its done.fire), its own live
  // resource fence is mandatory. Late unsolicited format replies therefore
  // cannot turn into drained=true after the norm receipt has retired.
  val normLocalDrained=norm.io.resourcesDrained ||
    (!normActivated && !normOwned && !norm.io.resetRequired && !norm.io.done.valid)
  val chunkLocalDrained=chunk.io.resourcesDrained ||
    (!chunkActivated && !chunkOwned && !chunk.io.resetRequired && !chunk.io.done.valid)
  val childResourcesDrained=normLocalDrained && chunkLocalDrained
  when(chunk.io.done.fire){
    chunkOwned:=false.B
    terminal.transactionId:=accepted.block.transactionId;terminal.chunk:=chunk.io.done.bits;terminal.conv:=convResult
    terminal.nextOwnerSequence:=nextSequence
    val bad=poison || currentFault || !prepPublished || normOwned || denseOwned || convOwned || !childResourcesDrained || chunk.io.done.bits.resetRequired ||
      chunk.io.done.bits.transactionId=/=accepted.block.transactionId || !chunk.io.done.bits.result.drained
    terminal.status:=Mux(bad,Status.Protocol.U,chunk.io.done.bits.result.status)
    terminal.resetRequired:=bad;terminal.drained:= !bad && io.transportDrained
    state:=report
  }
  val noTerminal= !norm.io.done.valid && !io.denseResult.valid && !conv.io.done.valid && !prep.io.done.valid && !chunk.io.done.valid
  val noHeldOffer= !norm.io.job.valid && !io.denseCommand.valid && !conv.io.job.valid && !prep.io.job.valid && !chunk.io.begin.valid
  val beforeChildIssue=state===normIssue || state===qIssue || state===abIssue || state===convIssue || state===chunkIssue
  when(beforeChildIssue && (poison || currentFault) && !anyOwned && noHeldOffer && noTerminal && io.transportDrained){
    failureStatus:=Status.Protocol.U;state:=failureDrain
  }
  when(state===failureDrain && !anyOwned && !prepHeld && noHeldOffer && noTerminal && io.transportDrained){
    terminal.transactionId:=accepted.block.transactionId;terminal.status:=failureStatus
    // An unrecoverable child quarantine may report an error, but NEVER a
    // false drain. Keep the held result immutable; resetRequired/live parent
    // fence still blocks publication and reuse until real isolation/reset.
    terminal.resetRequired:=true.B;terminal.drained:=childResourcesDrained;state:=report
  }
  when(io.done.fire){state:=Mux(terminal.resetRequired || poison || currentFault,locked,idle)}
  for((r,i)<-Seq(conv.io.memory,prep.io.memory,chunk.io.memory,norm.io.memory).zipWithIndex)io.memory(i).request<>r
  for((r,i)<-Seq(conv.io.response,prep.io.response,chunk.io.response,norm.io.response).zipWithIndex)r<>io.memory(i).response
  io.scalar(0)<>conv.io.scalar;io.scalar(1)<>prep.io.scalar;io.scalar(2)<>chunk.io.scalar;io.scalar(3)<>norm.io.scalar
  io.formatRequest<>norm.io.formatRequest;norm.io.formatResult<>io.formatResult
  norm.io.parentFault:=poison // registered; no combinational fault/reset feedback
  io.vectorRequest<>chunk.io.vectorRequest;chunk.io.vectorResult<>io.vectorResult
}
