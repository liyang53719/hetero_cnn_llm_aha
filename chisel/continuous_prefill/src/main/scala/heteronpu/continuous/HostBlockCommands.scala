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
class HostBlockCommands(s:QwenBlockShape,eventSlots:Int=256,maxCommands:Int=64,bf16Weights:Boolean=false,bf16V:Boolean=false,bf16Qkv:Boolean=false,bf16Gdn:Boolean=false,bf16GdnCore:Boolean=false,bf16GdnBlock:Boolean=false) extends Module {
  require(!bf16V || s.qwen35VOnly, "native V requires the explicit Qwen3.5 V-only profile")
  require(!bf16Qkv || s.qwen35QkvOnly, "native QKV requires the explicit Qwen3.5 QKV-only profile")
  require(!bf16GdnBlock || bf16GdnCore, "native full GDN block requires bf16GdnCore")
  require(!bf16GdnCore || bf16Gdn, "native GDN core requires bf16Gdn")
  require(!bf16Gdn || s.qwen35GdnOnly, "native GDN requires the explicit Qwen3.5 GDN-only profile")
  require(Seq(bf16V,bf16Qkv,bf16Gdn).count(identity)<=1, "native V-only, QKV and GDN features are distinct")
  require(eventSlots>=4 && isPow2(eventSlots) && maxCommands>=21 && maxCommands<=255)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunch));val result=Decoupled(new HostCommandResult)
    val completion=Decoupled(UInt(56.W))
    val job=Decoupled(new QwenOwnerJob);val done=Flipped(Decoupled(new QwenOwnerResult))
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val resetRequired=Output(Bool());val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W))
    val usefulMacs=Output(UInt(64.W));val executedMacs=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
  })
  val idle::fetch::get::decode::tensorIssue::tensorGet::policyIssue::policyGet::validate::issue::waitDone::complete::finish::locked::Nil=Enum(14)
  val state=RegInit(idle);val cfg=Reg(new HostCommandLaunch);val cmd=RegInit(0.U(128.W))
  val pc=RegInit(0.U(16.W));val completed=RegInit(0.U(16.W));val status=RegInit(0.U(8.W));val poison=RegInit(false.B)
  val events=RegInit(VecInit(Seq.fill(eventSlots)(false.B)))
  val tensorSlots=if(bf16Gdn)5 else 3
  val tensors=Reg(Vec(tensorSlots,new DecodedTensor));val slot=RegInit(0.U(log2Ceil(tensorSlots).W))
  val policy=Reg(Vec(12,UInt(128.W)));val policySlot=RegInit(0.U(4.W));val policyIndex=Reg(UInt(24.W))
  val policyIndices=Reg(Vec(12,UInt(24.W)));val extendedProjection=RegInit(false.B)
  val bound=Reg(new QwenOwnerJob)
  // The owner acknowledges both writes, but D and history are separate spans.
  val mainPublishBytes=Reg(UInt(64.W));val boundGdn=RegInit(false.B)
  // One explicit layer-0 / stream-0 context. Host launches never reset it.
  val stateValid=RegInit(false.B);val currentGeneration=RegInit(0.U(32.W))
  val currentHistoryAddress=RegInit(0.U(64.W));val currentHistoryEnd=RegInit(0.U(64.W))
  // Core v2 stages write fresh allocations. Only the terminal fence commits
  // the history and recurrent roots together; Host launches retain both roots.
  val currentStateAddress=RegInit(0.U(64.W));val currentStateEnd=RegInit(0.U(64.W))
  val txInputValid=RegInit(false.B);val txInputAddress=Reg(UInt(64.W));val txInputEnd=Reg(UInt(64.W))
  val txQkvValid=RegInit(false.B);val txZValid=RegInit(false.B);val txAbValid=RegInit(false.B)
  val txQkv=Reg(UInt(64.W));val txZ=Reg(UInt(64.W));val txAb=Reg(UInt(64.W))
  val txConvValid=RegInit(false.B);val txPrepValid=RegInit(false.B);val txRecurrentValid=RegInit(false.B);val txNormValid=RegInit(false.B)
  val txConv=Reg(UInt(64.W));val txPrep=Reg(UInt(64.W));val txRecurrent=Reg(UInt(64.W));val txNorm=Reg(UInt(64.W))
  // Full v3 block values are published only after their exact owner ACK.
  val txInputNormValid=RegInit(false.B);val txInputNorm=Reg(UInt(64.W))
  val txOValid=RegInit(false.B);val txO=Reg(UInt(64.W))
  val txResidual1Valid=RegInit(false.B);val txResidual1=Reg(UInt(64.W))
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
  val sourceCount=if(bf16GdnBlock)16 else 10
  val parameterRoles=if(bf16GdnBlock)(1 to 7)++(10 to 15) else (1 to 7)
  val sourceValid=RegInit(VecInit(Seq.fill(sourceCount)(false.B)))
  val sourceStarts=Reg(Vec(sourceCount,UInt(64.W)));val sourceEnds=Reg(Vec(sourceCount,UInt(64.W)))
  // The seven core (thirteen full-block) bindings belong to the committed checkpoint.
  // Hidden changes with each token; carried state cannot change its weights.
  val committedParameterStarts=Reg(Vec(parameterRoles.size,UInt(64.W)));val committedParameterEnds=Reg(Vec(parameterRoles.size,UInt(64.W)))
  val previousSignal=RegInit(0.U(16.W))
  def clearTransaction():Unit={
    txInputValid:=false.B;txQkvValid:=false.B;txZValid:=false.B;txAbValid:=false.B
    txConvValid:=false.B;txPrepValid:=false.B;txRecurrentValid:=false.B;txNormValid:=false.B
    txInputNormValid:=false.B;txOValid:=false.B;txResidual1Valid:=false.B;txPostNormValid:=false.B
    txGateValid:=false.B;txUpValid:=false.B;txSiluValid:=false.B;txDownValid:=false.B;txResidual2Valid:=false.B
    sourceValid:=VecInit(Seq.fill(sourceCount)(false.B))
  }
  val group=RegInit(0.U(2.W));val qkCommand=Reg(UInt(128.W));val softCommand=Reg(UInt(128.W))
  val q=Reg(new DecodedTensor);val k=Reg(new DecodedTensor);val score=Reg(new DecodedTensor);val probability=Reg(new DecodedTensor)
  val completingGroup=RegInit(false.B);val completionIndex=RegInit(0.U(2.W))
  val producedCapacity=if(bf16Gdn)2*maxCommands else maxCommands
  val producedIndexBits=log2Ceil(producedCapacity)
  val producedCount=RegInit(0.U(log2Ceil(producedCapacity+1).W))
  val starts=Reg(Vec(producedCapacity,UInt(64.W)));val ends=Reg(Vec(producedCapacity,UInt(64.W)))
  val producedValid=RegInit(VecInit(Seq.fill(producedCapacity)(false.B)))
  val managedHistory=RegInit(VecInit(Seq.fill(producedCapacity)(false.B)))
  val virtualCount=RegInit(0.U(8.W));val vStarts=Reg(Vec(maxCommands,UInt(64.W)));val vEnds=Reg(Vec(maxCommands,UInt(64.W)))
  val jobs=RegInit(0.U(16.W));val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W));val written=RegInit(0.U(64.W))
  io.pc:=pc;io.issuedJobs:=jobs;io.usefulMacs:=useful;io.executedMacs:=executed;io.writeBytes:=written
  val roots=VecInit(Seq(cmd(79,56),cmd(103,80),cmd(127,104)))
  val opcode=cmd(7,0);val engine=cmd(10,8);val waitEvent=cmd(39,24);val signalEvent=cmd(55,40)
  val isMatrix=opcode===0x20.U||opcode===0x23.U||opcode===0x24.U
  val isSoftmax=opcode===0x33.U;val kv=opcode===0x41.U
  val gdnCommand=bf16Gdn.B && opcode===0x30.U
  val reader=Module(new Record128Reader);val tensor=Module(new TypedTensorReader)
  io.memory<>reader.io.memory;reader.io.response<>io.response
  val tensorMode=state===tensorIssue||state===tensorGet
  reader.io.request.valid:=Mux(tensorMode,tensor.io.record.valid,state===fetch||state===policyIssue)
  reader.io.request.bits:=tensor.io.record.bits
  when(!tensorMode){
    reader.io.request.bits.tableBase:=Mux(state===fetch,cfg.commandBase,cfg.descriptorBase)
    reader.io.request.bits.tableLimit:=Mux(state===fetch,cfg.commandLimit,cfg.descriptorLimit)
    reader.io.request.bits.entryCount:=Mux(state===fetch,cfg.commands,cfg.descriptors)
    reader.io.request.bits.index:=Mux(state===fetch,pc,policyIndex)
    reader.io.request.bits.requestTag:=Cat(cfg.epoch,pc,0.U(32.W))
  }
  tensor.io.record.ready:=reader.io.request.ready&&tensorMode
  tensor.io.recordResult.valid:=reader.io.result.valid&&tensorMode;tensor.io.recordResult.bits:=reader.io.result.bits
  reader.io.result.ready:=Mux(tensorMode,tensor.io.recordResult.ready,state===get||state===policyGet)
  tensor.io.request.valid:=state===tensorIssue;tensor.io.request.bits.tableBase:=cfg.descriptorBase
  tensor.io.request.bits.tableLimit:=cfg.descriptorLimit;tensor.io.request.bits.entryCount:=cfg.descriptors
  tensor.io.request.bits.root:=roots(slot(1,0))
  if(bf16Gdn){when(slot>=3.U){tensor.io.request.bits.root:=Mux(slot===3.U,policy(2)(79,56),policy(2)(103,80))}}
  tensor.io.request.bits.regions:=cfg.regions
  val gdnOperation=policy(1)(71,64)
  val extraWrite=if(bf16GdnCore) (slot===4.U && gdnOperation===1.U)||(slot===3.U && gdnOperation===4.U) else bf16Gdn.B && slot===4.U
  tensor.io.request.bits.writeAccess:=slot===2.U || extraWrite
  tensor.io.result.ready:=state===tensorGet
  io.launch.ready:=state===idle && !poison
  io.result.valid:=state===finish;io.result.bits.status:=status;io.result.bits.completed:=completed
  io.result.bits.failedPc:=pc;io.result.bits.epoch:=cfg.epoch
  val completionCommand=Mux(completingGroup,Mux(completionIndex===0.U,qkCommand,Mux(completionIndex===1.U,softCommand,cmd)),cmd)
  val completionPc=Mux(completingGroup,pc-2.U+completionIndex,pc)
  io.completion.valid:=state===complete
  io.completion.bits:=Cat(completionCommand(55,40),status,completionCommand(10,8),completionPc.pad(29))
  io.job.valid:=state===issue;io.job.bits:=bound;io.done.ready:=state===waitDone
  io.resetRequired:=poison||reader.io.resetRequired
  def fail(code:UInt):Unit={status:=code;poison:=true.B;completingGroup:=false.B;state:=complete;if(bf16GdnCore){clearTransaction()}}
  def overlap(a:UInt,e:UInt,b:UInt,f:UInt):Bool=a<f && b<e
  def intersectsVirtual(t:DecodedTensor):Bool=(0 until maxCommands).map(i=>i.U<virtualCount && overlap(t.address,t.paddedEnd,vStarts(i),vEnds(i))).reduce(_||_)
  def liveSpan(address:UInt,end:UInt):Bool={
    val initial=cfg.regions.map(r=>r.read && !r.write && r.base<=address && end<=r.limit).reduce(_||_)
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
    val source=bf16GdnCore.B && (0 until sourceCount).map(i=>sourceValid(i) && overlap(address,end,sourceStarts(i),sourceEnds(i))).reduce(_||_)
    val parameter=bf16GdnCore.B && stateValid && parameterRoles.indices.map(i=>
      overlap(address,end,committedParameterStarts(i),committedParameterEnds(i))).reduce(_||_)
    !(published || virtual || current || recurrent || source || parameter)
  }
  def fresh(t:DecodedTensor):Bool=freshSpan(t.address,t.paddedEnd)
  def sourceAllowed(t:DecodedTensor,role:UInt):Bool={
    val roles=(0 until sourceCount).map(i=> !sourceValid(i) || Mux(i.U===role,
      t.address===sourceStarts(i) && t.paddedEnd===sourceEnds(i),
      !overlap(t.address,t.paddedEnd,sourceStarts(i),sourceEnds(i)))).reduce(_&&_)
    val published=(0 until producedCapacity).map(i=>producedValid(i) && overlap(t.address,t.paddedEnd,starts(i),ends(i))).reduce(_||_)
    // Old state roots are valid sources only in their dedicated semantic role.
    val oldHistory=stateValid && role=/=8.U && overlap(t.address,t.paddedEnd,currentHistoryAddress,currentHistoryEnd)
    val oldState=stateValid && role=/=9.U && overlap(t.address,t.paddedEnd,currentStateAddress,currentStateEnd)
    val checkpointParameters=parameterRoles.zipWithIndex.map{case(sourceRole,i)=> !stateValid || Mux(role===sourceRole.U,
      t.address===committedParameterStarts(i) && t.paddedEnd===committedParameterEnds(i),
      !overlap(t.address,t.paddedEnd,committedParameterStarts(i),committedParameterEnds(i)))}.reduce(_&&_)
    roles && !published && !oldHistory && !oldState && checkpointParameters
  }
  def rememberSource(t:DecodedTensor,role:UInt):Unit={
    sourceValid(role.pad(4)):=true.B;sourceStarts(role.pad(4)):=t.address;sourceEnds(role.pad(4)):=t.paddedEnd
  }
  def readonly(t:DecodedTensor):Bool=cfg.regions.map(r=>r.read && !r.write && r.base<=t.address && t.paddedEnd<=r.limit).reduce(_||_)
  def readwrite(t:DecodedTensor):Bool=cfg.regions.map(r=>r.read && r.write && r.base<=t.address && t.paddedEnd<=r.limit).reduce(_||_)
  def same(a:DecodedTensor,b:DecodedTensor):Bool=a.address===b.address && a.rank===b.rank && a.dtype===b.dtype && a.dims.asUInt===b.dims.asUInt
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
    def roTable(b:UInt,e:UInt):Bool=l.regions.map(r=>r.read && !r.write && r.base<=b && e<=r.limit).reduce(_||_)
    val validRegions=l.regions.map(r=>(r.base===r.limit && !r.read && !r.write)||
      (r.base<r.limit && r.base(5,0)===0.U && r.limit(5,0)===0.U && r.limit<=(BigInt(1)<<56).U)).reduce(_&&_)
    val collisions=(for(i<-0 until 4;j<-i+1 until 4)yield l.regions(i).base<l.regions(i).limit && l.regions(j).base<l.regions(j).limit && overlap(l.regions(i).base,l.regions(i).limit,l.regions(j).base,l.regions(j).limit)).reduce(_||_)
    val cmdEnd=l.commandBase.pad(80)+(((l.commands.pad(80)*16.U+63.U)>>6)<<6)
    val descEnd=l.descriptorBase.pad(80)+(((l.descriptors.pad(80)*16.U+63.U)>>6)<<6)
    val ok=(!bf16GdnBlock.B || l.commands===17.U) && l.commands>0.U && l.commands<=maxCommands.U && l.descriptors>0.U && l.descriptors<=0xffffff.U &&
      Seq(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit).map(_(5,0)===0.U).reduce(_&&_) &&
      l.commandBase<l.commandLimit && l.descriptorBase<l.descriptorLimit && cmdEnd<=l.commandLimit && descEnd<=l.descriptorLimit &&
      !overlap(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit) && validRegions && !collisions &&
      roTable(l.commandBase,l.commandLimit) && roTable(l.descriptorBase,l.descriptorLimit)
    cfg:=l;pc:=0.U;completed:=0.U;status:=0.U;cmd:=0.U;producedCount:=0.U;virtualCount:=0.U;group:=0.U;completingGroup:=false.B
    jobs:=0.U;useful:=0.U;executed:=0.U;written:=0.U;boundFence:=false.B;previousSignal:=0.U
    if(bf16GdnCore){clearTransaction()}
    producedValid:=VecInit(Seq.fill(producedCapacity)(false.B));managedHistory:=VecInit(Seq.fill(producedCapacity)(false.B));boundGdn:=false.B
    events:=VecInit(Seq.fill(eventSlots)(false.B));events(0):=true.B
    when(!ok){status:=Status.Bounds.U;state:=finish}.otherwise{state:=fetch}
  }
  when(state===fetch && reader.io.request.fire){state:=get}
  when(state===get && reader.io.result.fire){
    cmd:=reader.io.result.bits.data
    when(reader.io.result.bits.status=/=0.U){fail(reader.io.result.bits.status)}
    .elsewhen(reader.io.result.bits.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))){fail(Status.Protocol.U)}
    .otherwise{state:=decode}
  }
  when(state===decode){
    val supported=if(s.qwen35GdnOnly) opcode===0x30.U||opcode===0x20.U else if(s.qwen35QkvOnly) opcode===0x20.U else
      isMatrix||opcode===0x30.U||opcode===0x32.U||isSoftmax||opcode===0x34.U||opcode===0x35.U||kv
    val correctEngine=engine===Mux(isMatrix,2.U,Mux(kv,4.U,3.U))
    val rootsOK=roots(0)=/=0xffffff.U&&roots(2)=/=0xffffff.U&&roots(0)<cfg.descriptors&&roots(2)<cfg.descriptors&&
      Mux(isSoftmax,roots(1)===0xffffff.U,roots(1)=/=0xffffff.U&&roots(1)<cfg.descriptors)
    val expectedWait=Mux(group===1.U,qkCommand(55,40),softCommand(55,40))
    val dependency=Mux(group===0.U,events(waitEvent(log2Ceil(eventSlots)-1,0)),waitEvent===expectedWait) &&
      (!bf16GdnCore.B || waitEvent===previousSignal)
    val groupOrder=Mux(group===1.U,isSoftmax,Mux(group===2.U,opcode===0x24.U,!isSoftmax && opcode=/=0x24.U))
    when(!supported|| !correctEngine){fail(Status.Unsupported.U)}
    .elsewhen(cmd(23,11)=/=0.U|| !rootsOK|| !groupOrder){fail(Status.Malformed.U)}
    .elsewhen(waitEvent>=eventSlots.U||signalEvent===0.U||signalEvent>=eventSlots.U|| !dependency||
      events(signalEvent(log2Ceil(eventSlots)-1,0))||signalEvent===waitEvent||
      (group=/=0.U && signalEvent===qkCommand(55,40))){fail(Status.Dependency.U)}
    .otherwise{slot:=0.U;policy:=VecInit(Seq.fill(12)(0.U(128.W)));extendedProjection:=false.B;state:=tensorIssue}
  }
  when(state===tensorIssue&&tensor.io.request.fire){state:=tensorGet}
  when(state===tensorGet&&tensor.io.result.fire){
    when(tensor.io.result.bits.status=/=0.U){fail(tensor.io.result.bits.status)}
    .otherwise{tensors(slot):=tensor.io.result.bits.tensor
      when(slot===2.U){
        policyIndex:=tensors(0).tail;policySlot:=0.U
        state:=Mux(kv,validate,policyIssue)
      }.elsewhen(bf16Gdn.B && (slot===4.U || (bf16GdnCore.B && slot===3.U && (gdnOperation===4.U || gdnOperation===5.U)))){state:=validate}.otherwise{
        when(slot===0.U&&isSoftmax){tensors(1):=0.U.asTypeOf(new DecodedTensor);slot:=2.U}.otherwise{slot:=slot+1.U}
        state:=tensorIssue
      }
    }
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
    val nativeProjection=(bf16V || bf16Qkv).B && opcode===0x20.U && m>0.U && m<=128.U && m<=s.maxTokens.U &&
      shape2(a,m,1024.U)&&shape2(b,1024.U,projectionN)&&shape2(d,m,projectionN)&&
      Seq(a,b,d).map(_.dtype===5.U).reduce(_&&_) && ownerPolicy && projectionMatrix && distinctPrefixes
    val nativeWeight=bf16Weights.B && opcode===0x20.U && b.dtype===5.U && n(4,0)===0.U
    val validDTypes=nativeProjection || (a.dtype===7.U&&d.dtype===7.U&&(isSoftmax||b.dtype===7.U||nativeWeight))
    val plainTails=(isSoftmax||b.tail===0xffffff.U)&&d.tail===0xffffff.U&&(kv=== (a.tail===0xffffff.U))
    val noAlias= !overlap(d.address,d.paddedEnd,a.address,a.paddedEnd) && (isSoftmax|| !overlap(d.address,d.paddedEnd,b.address,b.paddedEnd))
    val sourceLive=Mux(nativeProjection,liveSpan(activeA,activeAEnd)&&live(b),Mux(group===1.U,same(a,score),Mux(group===2.U,same(a,probability)&&live(b),live(a)&&live(b))))
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
    val supportedOrdinary=validDTypes && plainTails && (!s.projectionOnly.B || nativeProjection) &&
      (!extendedProjection || nativeProjection) && (nativeProjection||norm||dense||vector||rope||activation||append||qk||sm||pv)
    val coreOperation=corePrep || coreRecurrent || coreNorm || coreFence || blockRmsNorm || blockElementwise
    val publicationSlots=Mux(coreFence,0.U,Mux(nativeGdn || coreRecurrent,2.U,1.U))
    when(!Mux(s.qwen35GdnOnly.B,nativeGdn||gdnProjection||coreOperation,supportedOrdinary)){fail(Status.Unsupported.U)}
    .elsewhen((nativeGdn||gdnProjection||coreOperation) && !gdnDistinct){fail(Status.Malformed.U)}
    .elsewhen(bf16GdnCore.B && (coreFence =/= (pc+1.U===cfg.commands))){fail(Status.Malformed.U)}
    .elsewhen(!Mux(nativeGdn||coreOperation||(bf16GdnCore.B && gdnProjection),gdnLive,sourceLive)){fail(Status.Dependency.U)}
    .elsewhen(!Mux(nativeGdn||coreOperation||(bf16GdnCore.B && gdnProjection),gdnFresh,noAlias && (!gdnProjection || !overlap(a.address,a.paddedEnd,b.address,b.paddedEnd)) &&
      Mux(nativeProjection,freshSpan(activeD,activeDEnd),fresh(d)))||
      producedCount+&publicationSlots>producedCapacity.U||virtualCount>=maxCommands.U){fail(Status.Permission.U)}
    .elsewhen(coreFence){boundFence:=true.B;state:=complete}
    .elsewhen(qk){q:=a;k:=b;score:=d;qkCommand:=cmd;group:=1.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.elsewhen(sm){probability:=d;softCommand:=cmd;group:=2.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.otherwise{
      bound:=0.U.asTypeOf(new QwenOwnerJob)
      bound.tag:=Cat(cfg.epoch,pc);bound.a:=a.address;bound.b:=b.address;bound.dst:=d.address;bound.writeBytes:=d.payloadBytes
      mainPublishBytes:=d.payloadBytes;boundGdn:=nativeGdn;boundFence:=false.B
      bound.m:=m;bound.n:=n;bound.k:=a.dims(1);bound.weightBf16:=nativeWeight
      bound.kind:=Mux(norm,QwenOwnerKind.Norm.U,Mux(dense||nativeProjection||gdnProjection,QwenOwnerKind.Dense.U,
        Mux(vector,Mux(b.dims(0)===1.U,QwenOwnerKind.Bias.U,QwenOwnerKind.Add.U),
        Mux(rope,QwenOwnerKind.Rope.U,Mux(activation,QwenOwnerKind.Activation.U,
        Mux(append,QwenOwnerKind.KvAppend.U,QwenOwnerKind.Attention.U))))))
      when(nativeProjection){
        bound.a:=activeA;bound.dst:=activeD;bound.m:=tokenCount;bound.n:=projectionN;bound.k:=1024.U
        bound.weightBf16:=true.B;bound.activationBf16:=true.B;bound.outputBf16:=true.B
        bound.writeBytes:=projectionBytes;mainPublishBytes:=projectionBytes
      }
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
    }
  }
  when(io.job.fire){jobs:=jobs+1.U;state:=waitDone}
  when(io.done.fire){val r=io.done.bits
    when(r.tag=/=bound.tag){fail(Status.Protocol.U)}
    .elsewhen(r.status=/=0.U){fail(r.status)}
    .elsewhen(r.writeBytes=/=bound.writeBytes){fail(Status.Protocol.U)}
    .otherwise{
      useful:=useful+r.usefulMacs;executed:=executed+r.executedMacs;written:=written+r.writeBytes
      completingGroup:=group===2.U;completionIndex:=0.U;state:=complete
    }
  }
  when(io.completion.fire){
    when(status=/=0.U){state:=finish}
    .otherwise{
      events(completionCommand(55,40)(log2Ceil(eventSlots)-1,0)):=true.B;completed:=completed+1.U
      if(bf16GdnCore){previousSignal:=completionCommand(55,40)}
      when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}
      .otherwise{
        when(!boundFence){
          val outputIndex=producedCount(producedIndexBits-1,0)
          starts(outputIndex):=bound.dst;ends(outputIndex):=bound.dst+mainPublishBytes
          producedValid(outputIndex):=true.B;managedHistory(outputIndex):=false.B
          producedCount:=producedCount+1.U
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
                is(0.U){txResidual1Valid:=true.B;txResidual1:=bound.dst}
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
        group:=0.U;completingGroup:=false.B
        when(pc+1.U===cfg.commands){state:=finish}.otherwise{pc:=pc+1.U;state:=fetch}
      }
    }
  }
  when(io.result.fire){state:=Mux(poison,locked,idle)}
}
