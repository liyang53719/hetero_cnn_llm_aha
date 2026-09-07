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
class HostBlockCommands(s:QwenBlockShape,eventSlots:Int=256,maxCommands:Int=64) extends Module {
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
  val tensors=Reg(Vec(3,new DecodedTensor));val slot=RegInit(0.U(2.W))
  val policy=Reg(Vec(2,UInt(128.W)));val policySlot=RegInit(false.B);val policyIndex=Reg(UInt(24.W))
  val bound=Reg(new QwenOwnerJob)
  val group=RegInit(0.U(2.W));val qkCommand=Reg(UInt(128.W));val softCommand=Reg(UInt(128.W))
  val q=Reg(new DecodedTensor);val k=Reg(new DecodedTensor);val score=Reg(new DecodedTensor);val probability=Reg(new DecodedTensor)
  val completingGroup=RegInit(false.B);val completionIndex=RegInit(0.U(2.W))
  val producedCount=RegInit(0.U(8.W));val starts=Reg(Vec(maxCommands,UInt(64.W)));val ends=Reg(Vec(maxCommands,UInt(64.W)))
  val virtualCount=RegInit(0.U(8.W));val vStarts=Reg(Vec(maxCommands,UInt(64.W)));val vEnds=Reg(Vec(maxCommands,UInt(64.W)))
  val jobs=RegInit(0.U(16.W));val useful=RegInit(0.U(64.W));val executed=RegInit(0.U(64.W));val written=RegInit(0.U(64.W))
  io.pc:=pc;io.issuedJobs:=jobs;io.usefulMacs:=useful;io.executedMacs:=executed;io.writeBytes:=written
  val roots=VecInit(Seq(cmd(79,56),cmd(103,80),cmd(127,104)))
  val opcode=cmd(7,0);val engine=cmd(10,8);val waitEvent=cmd(39,24);val signalEvent=cmd(55,40)
  val isMatrix=opcode===0x20.U||opcode===0x23.U||opcode===0x24.U
  val isSoftmax=opcode===0x33.U;val kv=opcode===0x41.U
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
  tensor.io.request.bits.root:=roots(slot);tensor.io.request.bits.regions:=cfg.regions;tensor.io.request.bits.writeAccess:=slot===2.U
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
  def fail(code:UInt):Unit={status:=code;poison:=true.B;completingGroup:=false.B;state:=complete}
  def overlap(a:UInt,e:UInt,b:UInt,f:UInt):Bool=a<f && b<e
  def intersectsVirtual(t:DecodedTensor):Bool=(0 until maxCommands).map(i=>i.U<virtualCount && overlap(t.address,t.paddedEnd,vStarts(i),vEnds(i))).reduce(_||_)
  def live(t:DecodedTensor):Bool={
    val initial=cfg.regions.map(r=>r.read && !r.write && r.base<=t.address && t.paddedEnd<=r.limit).reduce(_||_)
    val published=(0 until maxCommands).map(i=>i.U<producedCount && starts(i)<=t.address && t.paddedEnd<=ends(i)).reduce(_||_)
    (initial||published) && !intersectsVirtual(t)
  }
  def fresh(t:DecodedTensor):Bool= !intersectsVirtual(t) && !(0 until maxCommands).map(i=>i.U<producedCount && overlap(t.address,t.paddedEnd,starts(i),ends(i))).reduce(_||_)
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
    val ok=l.commands>0.U && l.commands<=maxCommands.U && l.descriptors>0.U && l.descriptors<=0xffffff.U &&
      Seq(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit).map(_(5,0)===0.U).reduce(_&&_) &&
      l.commandBase<l.commandLimit && l.descriptorBase<l.descriptorLimit && cmdEnd<=l.commandLimit && descEnd<=l.descriptorLimit &&
      !overlap(l.commandBase,l.commandLimit,l.descriptorBase,l.descriptorLimit) && validRegions && !collisions &&
      roTable(l.commandBase,l.commandLimit) && roTable(l.descriptorBase,l.descriptorLimit)
    cfg:=l;pc:=0.U;completed:=0.U;status:=0.U;cmd:=0.U;producedCount:=0.U;virtualCount:=0.U;group:=0.U;completingGroup:=false.B
    jobs:=0.U;useful:=0.U;executed:=0.U;written:=0.U
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
    val supported=isMatrix||opcode===0x30.U||opcode===0x32.U||isSoftmax||opcode===0x34.U||opcode===0x35.U||kv
    val correctEngine=engine===Mux(isMatrix,2.U,Mux(kv,4.U,3.U))
    val rootsOK=roots(0)=/=0xffffff.U&&roots(2)=/=0xffffff.U&&roots(0)<cfg.descriptors&&roots(2)<cfg.descriptors&&
      Mux(isSoftmax,roots(1)===0xffffff.U,roots(1)=/=0xffffff.U&&roots(1)<cfg.descriptors)
    val expectedWait=Mux(group===1.U,qkCommand(55,40),softCommand(55,40))
    val dependency=Mux(group===0.U,events(waitEvent(log2Ceil(eventSlots)-1,0)),waitEvent===expectedWait)
    val groupOrder=Mux(group===1.U,isSoftmax,Mux(group===2.U,opcode===0x24.U,!isSoftmax && opcode=/=0x24.U))
    when(!supported|| !correctEngine){fail(Status.Unsupported.U)}
    .elsewhen(cmd(23,11)=/=0.U|| !rootsOK|| !groupOrder){fail(Status.Malformed.U)}
    .elsewhen(waitEvent>=eventSlots.U||signalEvent===0.U||signalEvent>=eventSlots.U|| !dependency||
      events(signalEvent(log2Ceil(eventSlots)-1,0))||signalEvent===waitEvent||
      (group=/=0.U && signalEvent===qkCommand(55,40))){fail(Status.Dependency.U)}
    .otherwise{slot:=0.U;policy:=VecInit(Seq.fill(2)(0.U(128.W)));state:=tensorIssue}
  }
  when(state===tensorIssue&&tensor.io.request.fire){state:=tensorGet}
  when(state===tensorGet&&tensor.io.result.fire){
    when(tensor.io.result.bits.status=/=0.U){fail(tensor.io.result.bits.status)}
    .otherwise{tensors(slot):=tensor.io.result.bits.tensor
      when(slot===2.U){
        policyIndex:=tensors(0).tail;policySlot:=false.B
        state:=Mux(kv,validate,policyIssue)
      }.otherwise{
        when(slot===0.U&&isSoftmax){tensors(1):=0.U.asTypeOf(new DecodedTensor);slot:=2.U}.otherwise{slot:=slot+1.U}
        state:=tensorIssue
      }
    }
  }
  when(state===policyIssue&&reader.io.request.fire){state:=policyGet}
  when(state===policyGet&&reader.io.result.fire){
    val r=reader.io.result.bits;policy(policySlot):=r.data
    when(r.status=/=0.U){fail(r.status)}
    .elsewhen(r.requestTag=/=Cat(cfg.epoch,pc,0.U(32.W))){fail(Status.Protocol.U)}
    .elsewhen(isMatrix && !policySlot){
      when(r.data(7,0)=/=0x10.U||r.data(31,8)=/=0.U||r.data(55,32)===tensors(0).tail){fail(Status.Malformed.U)}
      .otherwise{policyIndex:=r.data(55,32);policySlot:=true.B;state:=policyIssue}
    }.otherwise{state:=validate}
  }
  when(state===validate){
    val a=tensors(0);val b=tensors(1);val d=tensors(2)
    val m=a.dims(0);val n=d.dims(1)
    val allFP32=a.dtype===7.U&&d.dtype===7.U&&(isSoftmax||b.dtype===7.U)
    val plainTails=(isSoftmax||b.tail===0xffffff.U)&&d.tail===0xffffff.U&&(kv=== (a.tail===0xffffff.U))
    val noAlias= !overlap(d.address,d.paddedEnd,a.address,a.paddedEnd) && (isSoftmax|| !overlap(d.address,d.paddedEnd,b.address,b.paddedEnd))
    val sourceLive=Mux(group===1.U,same(a,score),Mux(group===2.U,same(a,probability)&&live(b),live(a)&&live(b)))
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
    when(!allFP32|| !plainTails|| !(norm||dense||vector||rope||activation||append||qk||sm||pv)){fail(Status.Unsupported.U)}
    .elsewhen(!sourceLive){fail(Status.Dependency.U)}
    .elsewhen(!noAlias|| !fresh(d)||producedCount>=maxCommands.U||virtualCount>=maxCommands.U){fail(Status.Permission.U)}
    .elsewhen(qk){q:=a;k:=b;score:=d;qkCommand:=cmd;group:=1.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.elsewhen(sm){probability:=d;softCommand:=cmd;group:=2.U
      vStarts(virtualCount(log2Ceil(maxCommands)-1,0)):=d.address;vEnds(virtualCount(log2Ceil(maxCommands)-1,0)):=d.paddedEnd;virtualCount:=virtualCount+1.U;nextCommand()
    }.otherwise{
      bound:=0.U.asTypeOf(new QwenOwnerJob)
      bound.tag:=Cat(cfg.epoch,pc);bound.a:=a.address;bound.b:=b.address;bound.dst:=d.address;bound.writeBytes:=d.payloadBytes
      bound.m:=m;bound.n:=n;bound.k:=a.dims(1)
      bound.kind:=Mux(norm,QwenOwnerKind.Norm.U,Mux(dense,QwenOwnerKind.Dense.U,
        Mux(vector,Mux(b.dims(0)===1.U,QwenOwnerKind.Bias.U,QwenOwnerKind.Add.U),
        Mux(rope,QwenOwnerKind.Rope.U,Mux(activation,QwenOwnerKind.Activation.U,
        Mux(append,QwenOwnerKind.KvAppend.U,QwenOwnerKind.Attention.U))))))
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
      when(completingGroup && completionIndex<2.U){completionIndex:=completionIndex+1.U}
      .otherwise{
        starts(producedCount(log2Ceil(maxCommands)-1,0)):=tensors(2).address;ends(producedCount(log2Ceil(maxCommands)-1,0)):=tensors(2).paddedEnd;producedCount:=producedCount+1.U
        group:=0.U;completingGroup:=false.B
        when(pc+1.U===cfg.commands){state:=finish}.otherwise{pc:=pc+1.U;state:=fetch}
      }
    }
  }
  when(io.result.fire){state:=Mux(poison,locked,idle)}
}
