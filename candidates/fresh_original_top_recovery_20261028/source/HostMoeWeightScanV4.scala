// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private scanner input from the ORIGINAL decoder's current Command128.
  * These are indices, not physical pointers or host-created permission bits. */
class HostMoeWeightScanBeginV4 extends Bundle {
  val root=UInt(24.W);val pc=UInt(16.W)
}
class HostMoeWeightScanResultV4 extends Bundle {
  val transactionId=UInt(64.W);val root=UInt(24.W);val pc=UInt(16.W)
  val status=UInt(8.W);val weights=Vec(8,new DecodedTensor)
  val hasPaddedSharedGate=Bool();val paddedSharedGate=new DecodedTensor
}

/** Eight records, ascending role0..7. Each record is the existing 128-bit
  * descriptor envelope, with a NEW typed kind0x60 and versionVALUE1:
  * [7:0]kind, [31:8]zero, [55:32]next24 (last=ffffff),
  * [63:56]version1, [66:64]role, [90:67]tensorRoot24, [127:91]zero.
  * All tensor roots use the UNCHANGED base/shape/stride prefix and actual
  * TypedTensorReader. Linear weights are [K,N], expert weights [256,K,N],
  * BF16 bytes without hidden transpose/cast/padding. Role7 logicalN1 is read
  * metadata, NOT a claim the current Dense owner supports its computation.
  * Explicit role7 version2 additionally encodes [114:91] physicalTensorRoot24,
  * [122:115] layoutID1, [127:123] zero. It reads BOTH logical[K,1] and a distinct
  * physical[K,32] typed view through the SAME reader. Version1 still has zero
  * reserved bits and never implies padding rights or a complete N1 path.
  * Existing public128 opcode/descriptor meanings are never reinterpreted.
  */
object HostMoeWeightRecordV4 {
  val Kind=0x60;val Version=1;val Count=8
  def tensorLegal(t:DecodedTensor,role:UInt):Bool={
    val expert=role>=1.U && role<=3.U
    val k=Mux(role===3.U || role===6.U,512.U,2048.U)
    val n=Mux(role===0.U,256.U,Mux(role===3.U || role===6.U,2048.U,Mux(role===7.U,1.U,512.U)))
    val count=k.pad(64)*n*Mux(expert,256.U,1.U)
    val geometry=Mux(expert,t.rank===3.U && t.dims(0)===256.U && t.dims(1)===k && t.dims(2)===n && t.dims(3)===1.U,
      t.rank===2.U && t.dims(0)===k && t.dims(1)===n && t.dims(2)===1.U && t.dims(3)===1.U)
    role<8.U && geometry && t.dtype===5.U && t.tail==="hffffff".U &&
      t.elementCount===count && t.payloadBytes===(count<<1) &&
      t.address(5,0)===0.U && t.address<t.paddedEnd &&
      t.paddedEnd.pad(96)===t.address.pad(96)+(((t.payloadBytes.pad(96)+63.U)>>6)<<6) &&
      t.paddedEnd<=(BigInt(1)<<56).U
  }
}

/** Control only. Owns NO reader, memory, arithmetic, or payload cache.
  * record and tensor ports connect through the original Commands mux to its
  * SINGLE Record128Reader and SINGLE TypedTensorReader; while busy no legacy
  * request may interleave. TypedTensorReader internally uses that same record
  * reader. Both are registered/nonzero-latency services. A matching result
  * without a fired request cannot create source authority. Physical epoch/
  * same-tag stale isolation remains the parent service's separate duty.
  */
class HostMoeWeightScanV4 extends Module {
  val io=IO(new Bundle {
    val authority=Input(new HostRuntimeAuthoritySnapshotV4)
    val begin=Flipped(Decoupled(new HostMoeWeightScanBeginV4))
    val record=Decoupled(new Record128Request);val recordResult=Flipped(Decoupled(new Record128Result))
    val tensor=Decoupled(new TensorReadRequest);val tensorResult=Flipped(Decoupled(new TensorReadResult))
    val done=Decoupled(new HostMoeWeightScanResultV4)
    val currentFault=Input(Bool())
    val busy=Output(Bool());val resetRequired=Output(Bool());val resourcesDrained=Output(Bool())
    val tensorPath=Output(Bool()) // pure registered-state route, NEVER ready/valid-derived
  })
  val idle::rIssue::rWait::tIssue::tWait::report::locked::Nil=Enum(7)
  val state=RegInit(idle);val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val cfg=Reg(new HostCommandLaunchV4);val txn=Reg(UInt(64.W));val pc=Reg(UInt(16.W))
  val role=RegInit(0.U(3.W));val index=Reg(UInt(24.W));val tensorRoot=Reg(UInt(24.W));val next=Reg(UInt(24.W))
  val physicalRoot=Reg(UInt(24.W));val paddedExpected=RegInit(false.B);val physicalRead=RegInit(false.B)
  val seen=Reg(Vec(8,UInt(24.W)))
  val rolesSeen=RegInit(0.U(8.W))
  val result=Reg(new HostMoeWeightScanResultV4)
  val active=state=/=idle && state=/=locked
  val recordTag=Cat(cfg.epoch,pc,"h4d4f45".U(24.W),0.U(5.W),role)
  val unknownRecord=io.recordResult.valid && (state=/=rWait || io.recordResult.bits.requestTag=/=recordTag)
  val unknownTensor=io.tensorResult.valid && state=/=tWait
  val unknown=unknownRecord || unknownTensor
  val contextChanged=active && (!io.authority.accepted || io.authority.transaction=/=txn || io.authority.launch.asUInt=/=cfg.asUInt)
  val fault=io.currentFault || unknown || contextChanged || (active && io.authority.currentFault)
  when(fault){poison:=true.B};when(unknown){quarantine:=true.B}
  io.resetRequired:=poison || fault || quarantine
  io.busy:=state=/=idle || poison || quarantine
  io.tensorPath:=state===tIssue || state===tWait
  io.begin.ready:=state===idle && !poison && !fault && !quarantine
  io.done.valid:=state===report;io.done.bits:=result
  when(io.done.fire){state:=Mux(poison || fault || quarantine,locked,idle)}
  val quiet= !io.recordResult.valid && !io.tensorResult.valid
  io.resourcesDrained:=(state===idle || state===report || state===locked) && quiet && !quarantine && !unknown
  val rh=HeldDecoupledOffer(state===rIssue,io.record.ready,poison || fault || quarantine)
  val th=HeldDecoupledOffer(state===tIssue,io.tensor.ready,poison || fault || quarantine)
  io.record.valid:=rh.valid;io.record.bits.tableBase:=cfg.descriptorBase;io.record.bits.tableLimit:=cfg.descriptorLimit
  io.record.bits.entryCount:=cfg.descriptors;io.record.bits.index:=index;io.record.bits.requestTag:=recordTag
  io.tensor.valid:=th.valid;io.tensor.bits.tableBase:=cfg.descriptorBase;io.tensor.bits.tableLimit:=cfg.descriptorLimit
  io.tensor.bits.entryCount:=cfg.descriptors;io.tensor.bits.root:=tensorRoot
  io.tensor.bits.writeAccess:=false.B;io.tensor.bits.regions:=cfg.regions
  io.recordResult.ready:=state===rWait && !quarantine && !unknownRecord
  io.tensorResult.ready:=state===tWait && !quarantine && !unknownTensor
  when(io.record.fire){state:=rWait};when(io.tensor.fire){state:=tWait}
  def fail(code:UInt):Unit={result.status:=code;state:=report}
  when((poison || fault) && !quarantine && !unknown){
    when(state===rIssue && !rh.held && !io.record.fire){fail(Status.Protocol.U)}
    when(state===tIssue && !th.held && !io.tensor.fire){fail(Status.Protocol.U)}
  }
  when(io.begin.fire){
    cfg:=io.authority.launch;txn:=io.authority.transaction;pc:=io.begin.bits.pc
    index:=io.begin.bits.root;role:=0.U;rolesSeen:=0.U;paddedExpected:=false.B;physicalRead:=false.B
    result:=0.U.asTypeOf(new HostMoeWeightScanResultV4)
    result.transactionId:=io.authority.transaction;result.root:=io.begin.bits.root;result.pc:=io.begin.bits.pc
    val a=io.authority;val l=a.launch
    val (shape,known)=UnifiedRuntimeProfile.decode(l.profileId)
    when(!a.accepted || !HostCommandLaunchV4.known(l) || !known || shape.asUInt=/=a.profile.asUInt ||
      !(l.profileId===3.U || l.profileId===4.U)){fail(Status.Unsupported.U)}
    .elsewhen(io.begin.bits.pc=/=a.pc || io.begin.bits.pc>=l.commands || io.begin.bits.root>=l.descriptors ||
      io.begin.bits.root==="hffffff".U){fail(Status.Bounds.U)}
    .otherwise{state:=rIssue}
  }
  when(io.recordResult.fire){
    val r=io.recordResult.bits;val w=r.data;val last=role===7.U;val nr=w(55,32);val tr=w(90,67)
    val previous=(0 until 8).map(i=>i.U<role && (seen(i)===index ||
      result.weights(i).prefixIndices.map(_===index).reduce(_||_))).reduce(_||_)
    val padded=last && w(63,56)===2.U
    val pr=w(114,91)
    val versionOK=Mux(padded,w(122,115)===HostMoeSharedGatePlanV5.LayoutId.U && w(127,123)===0.U &&
      pr=/="hffffff".U && pr<cfg.descriptors && pr=/=tr && pr=/=index,
      w(63,56)===1.U && w(127,91)===0.U)
    val recordBad=w(7,0)=/=HostMoeWeightRecordV4.Kind.U || w(31,8)=/=0.U ||
      !versionOK || w(66,64)=/=role ||
      last=/=(nr==="hffffff".U) || (!last && (nr>=cfg.descriptors || nr===index)) ||
      tr==="hffffff".U || tr>=cfg.descriptors || tr===index || previous || rolesSeen(role)
    when(poison || fault){fail(Status.Protocol.U)}
    .elsewhen(r.status=/=Status.Ok.U){fail(r.status)}
    .elsewhen(recordBad){fail(Status.Malformed.U)}
    .otherwise{seen(role):=index;rolesSeen:=rolesSeen|UIntToOH(role,8);tensorRoot:=tr;next:=nr
      physicalRoot:=pr;paddedExpected:=padded;physicalRead:=false.B;state:=tIssue}
  }
  when(io.tensorResult.fire){
    val r=io.tensorResult.bits;val t=r.tensor
    val prefixCollision=t.prefixIndices.map(x=>(0 until 8).map(i=>i.U<=role && x===seen(i)).reduce(_||_) ||
      (0 until 8).map(i=>(i.U<role || (physicalRead && i.U===role)) && result.weights(i).prefixIndices.map(_===x).reduce(_||_)).reduce(_||_)).reduce(_||_)
    def overlap(b:UInt,e:UInt,c:UInt,d:UInt):Bool=b<d && c<e
    val ro=cfg.regions.map(x=>x.read && !x.write && x.base<=t.address && t.paddedEnd<=x.limit).reduce(_||_)
    val tableAlias=overlap(t.address,t.paddedEnd,cfg.commandBase,cfg.commandLimit) ||
      overlap(t.address,t.paddedEnd,cfg.descriptorBase,cfg.descriptorLimit)
    val weightAlias=(0 until 8).map(i=>(i.U<role || (physicalRead && i.U===role)) &&
      overlap(t.address,t.paddedEnd,result.weights(i).address,result.weights(i).paddedEnd)).reduce(_||_)
    val tensorLegal=Mux(physicalRead,role===7.U && paddedExpected &&
      HostMoeSharedGatePlanV5.matrix(t,HostMoeSharedGatePlanV5.K,HostMoeSharedGatePlanV5.PhysicalN),
      HostMoeWeightRecordV4.tensorLegal(t,role))
    when(poison || fault){fail(Status.Protocol.U)}
    .elsewhen(r.status=/=Status.Ok.U){fail(r.status)}
    .elsewhen(prefixCollision){fail(Status.Malformed.U)}
    .elsewhen(!tensorLegal || tableAlias || weightAlias){fail(Status.Bounds.U)}
    .elsewhen(!ro){fail(Status.Permission.U)}
    .otherwise{
      when(physicalRead){
        result.paddedSharedGate:=t;result.hasPaddedSharedGate:=true.B
        result.status:=Mux(rolesSeen===255.U,Status.Ok.U,Status.Protocol.U);state:=report
      }.otherwise{
        result.weights(role):=t
        when(role===7.U && paddedExpected){tensorRoot:=physicalRoot;physicalRead:=true.B;state:=tIssue}
        .elsewhen(role===7.U){result.status:=Mux(rolesSeen===255.U,Status.Ok.U,Status.Protocol.U);state:=report}
        .otherwise{role:=role+1.U;index:=next;state:=rIssue}
      }
    }
  }
}
