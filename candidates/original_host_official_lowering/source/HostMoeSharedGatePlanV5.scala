// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** PRIVATE metadata from TWO actual TypedTensorReader results in the same
  * accepted role7 version2 record. Not a Host permission or a byte verifier.
  * The immutable loader/DDR image supplies the audited layoutID1 mapping:
  * physical[k,0]=logical[k,0], physical[k,1..31]=positive zero, no cast.
  * The ordinary logical4KiB descriptor never grants a physical128KiB range.
  */
class HostMoeSharedGateImageV5 extends Bundle {
  val logicalWeight=new DecodedTensor
  val physicalWeight=new DecodedTensor
  val layoutId=UInt(8.W)
}

/** Only the original parent's actual accepted Dense job + done.fire creates
  * this receipt, after the same phase's shared FFN ACK/drain releases gateOutput
  * for reuse. This is NOT a final phase release or source of allocation rights.
  */
class HostMoeSharedGateCommitV5 extends Bundle {
  val context=new HostMoePhaseContextV4
  val allocationSequence=UInt(64.W)
  val image=new HostMoeSharedGateImageV5
  val acceptedJob=new QwenOwnerJob
  val result=new QwenOwnerResult // original complete physical result unchanged
  val logicalN=UInt(16.W);val physicalN=UInt(16.W)
  val physicalOutputStride=UInt(32.W)
  val logicalWriteBytes=UInt(64.W);val physicalWriteBytes=UInt(64.W)
  val logicalMacs=UInt(64.W) // excludes all31 structural-zero output columns
}

object HostMoeSharedGatePlanV5 {
  val LayoutId=1
  val LogicalN=1;val PhysicalN=32;val K=2048
  val PhysicalOutputStride=64
  def overlap(a:UInt,e:UInt,b:UInt,f:UInt):Bool=a<f && b<e
  def matrix(t:DecodedTensor,k:Int,n:Int):Bool=t.dtype===5.U && t.rank===2.U &&
    t.dims(0)===k.U && t.dims(1)===n.U && t.dims(2)===1.U && t.dims(3)===1.U &&
    t.elementCount===(k*n).U && t.payloadBytes===(k*n*2).U && t.tail==="hffffff".U &&
    t.address(5,0)===0.U && t.paddedEnd.pad(96)===t.address.pad(96)+(k*n*2).U &&
    t.paddedEnd<=(BigInt(1)<<56).U

  /** Structural qualification ONLY. Caller must retain image from the actual
    * clean metadata event with this complete accepted Host/txn. Equal packets
    * cannot establish that provenance or verify the padding bytes by themselves.
    */
  def imageLegal(l:HostMoeRuntimePhaseLeaseV5,i:HostMoeSharedGateImageV5):Bool={
    val h=l.context.host;val p=i.physicalWeight;val s=i.logicalWeight
    val ro=h.regions.map(r=>r.read && !r.write && p.address>=r.base && p.paddedEnd<=r.limit).reduce(_||_)
    val distinct=l.weights.map(w=> !overlap(p.address,p.paddedEnd,w.address,w.paddedEnd)).reduce(_&&_) &&
      !overlap(p.address,p.paddedEnd,h.commandBase,h.commandLimit) &&
      !overlap(p.address,p.paddedEnd,h.descriptorBase,h.descriptorLimit) &&
      !overlap(p.address,p.paddedEnd,l.allocationBase,l.allocationEnd) &&
      Seq(l.context.input,l.context.residual,l.context.output).map(t=>
        !overlap(p.address,p.paddedEnd,t.address,t.paddedEnd)).reduce(_&&_)
    i.layoutId===LayoutId.U && s.asUInt===l.weights(HostMoeWeightRoleV4.SharedGateLogit).asUInt &&
      matrix(s,K,LogicalN) && matrix(p,K,PhysicalN) && ro && distinct
  }

  /** Original Dense job, NOT a new engine. This helper deliberately does not
    * create an offer: actual shared FFN retirement and all corresponding service
    * debts must close in the parent before this reused destination is offered.
    */
  def decode(l:HostMoeRuntimePhaseLeaseV5,i:HostMoeSharedGateImageV5):(QwenOwnerJob,Bool)={
    val j=WireDefault(0.U.asTypeOf(new QwenOwnerJob));val c=l.context
    val sequence=l.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.SharedGateDense.U
    val end=l.gateOutput.pad(96)+(c.tokens.pad(96)<<6)
    j.kind:=QwenOwnerKind.Dense.U;j.m:=c.tokens;j.n:=PhysicalN.U;j.k:=K.U
    j.a:=l.postnormBase;j.b:=i.physicalWeight.address;j.dst:=l.gateOutput;j.tag:=sequence(31,0)
    j.activationBf16:=true.B;j.weightBf16:=true.B;j.outputBf16:=true.B;j.materializeDenseOutput:=false.B
    j.writeBytes:=c.tokens.pad(64)<<6
    val (profile,known)=UnifiedRuntimeProfile.decode(c.host.profileId)
    val legal=known && (c.host.profileId===3.U || c.host.profileId===4.U) &&
      c.profile.asUInt===profile.asUInt && profile.hidden===K.U &&
      HostCommandLaunchV4.known(c.host) && c.version===HostMoePhaseContextV4.Version.U &&
      c.phase===HostMoePhaseContextV4.MoePhase.U && c.tokens>=1.U && c.tokens<=128.U &&
      l.firstOwnerSequence.pad(33)<=HostMoeOwnerRangeV5.MaximumFirst.U(33.W) && sequence<HostMoeOwnerRangeV5.EndLimit.U(33.W) &&
      l.postnormBase===c.input.address && c.input.payloadBytes===(c.tokens.pad(64)<<12) &&
      l.gateOutput(5,0)===0.U && l.gateOutput>=l.allocationBase && end<=l.allocationEnd.pad(96) &&
      end<=(BigInt(1)<<56).U && !overlap(l.gateOutput.pad(96),end,c.input.address.pad(96),c.input.paddedEnd.pad(96)) &&
      imageLegal(l,i)
    (j,legal)
  }

  /** Call outside when to fully drive the packet; capture ONLY on the actual
    * accepted job's matching result.fire, with independent CURRENT fault veto.
    * This helper has no synthetic success flag and does not manufacture a fire.
    */
  def fromActualDense(l:HostMoeRuntimePhaseLeaseV5,i:HostMoeSharedGateImageV5,
      accepted:QwenOwnerJob,result:QwenOwnerResult):(HostMoeSharedGateCommitV5,Bool)={
    val (expected,legal)=decode(l,i)
    val r=WireDefault(0.U.asTypeOf(new HostMoeSharedGateCommitV5))
    r.context:=l.context;r.allocationSequence:=l.allocationSequence;r.image:=i
    r.acceptedJob:=accepted;r.result:=result
    r.logicalN:=LogicalN.U;r.physicalN:=PhysicalN.U;r.physicalOutputStride:=PhysicalOutputStride.U
    r.logicalWriteBytes:=l.context.tokens.pad(64)<<1;r.physicalWriteBytes:=l.context.tokens.pad(64)<<6
    r.logicalMacs:=l.context.tokens.pad(64)*K.U
    (r,legal && accepted.asUInt===expected.asUInt && result.tag===accepted.tag &&
      result.status===Status.Ok.U && result.writeBytes===expected.writeBytes)
  }
}
