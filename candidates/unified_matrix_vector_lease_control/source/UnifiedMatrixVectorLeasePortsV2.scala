// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class UnifiedOverlapOwnerFaultV2 extends Bundle {
  val resource=UInt(2.W);val lease=new UnifiedOverlapLeaseV2;val reason=UInt(8.W)
}

/** First real port-control slice for concurrent Matrix/vector owners.
  * No arithmetic/storage feeder is instantiated here: bind the physical ports
  * to the ONE existing MatrixPipelineService and ONE existing16lane bank.
  * Independent leases may both be owned under one accepted block context.
  * This slice does not implement a fullblock scheduler or claim throughput.
  * Matrix tag derives from per-block nonwrapping ownerSequence; the child must
  * obey its real completion/drain contract. DDR/epoch routing remains separate.
  */
class UnifiedMatrixVectorLeasePortsV2 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedBlockDispatchV1))
    val end=Flipped(Decoupled(UInt(64.W)))
    val context=Output(new UnifiedBlockDispatchV1);val active=Output(Bool())
    val resetRequired=Output(Bool());val allResourcesDrained=Output(Bool())
    val matrixLease=Flipped(Decoupled(new UnifiedOverlapLeaseV2))
    val matrixGroup=Flipped(Decoupled(new MatrixStreamGroup(false,false)))
    val matrixStep=Flipped(Decoupled(new MatrixStreamStep(0)))
    val matrixResult=Decoupled(new MatrixStreamResult(0));val matrixDone=Decoupled(new UnifiedOverlapDoneV2)
    val physicalMatrix=new MatrixStreamPort(0,false,false)
    val physicalMatrixResetRequired=Input(Bool());val physicalMatrixAcceptedSteps=Input(UInt(64.W))
    val vectorLease=Flipped(Decoupled(new UnifiedOverlapLeaseV2))
    val vectorRequest=Flipped(Decoupled(new UnifiedOverlapVectorRequestV2))
    val vectorResult=Decoupled(new UnifiedOverlapVectorResultV2)
    val physicalVectorRequest=Decoupled(new UnifiedVectorRequestV2)
    val physicalVectorResult=Flipped(Decoupled(new UnifiedVectorResultV2))
    // These two inputs are PRIVATE accepted-consumer and actual-order bindings.
    // Never expose producerFence to Host or synthesize it from an arbitrary Bool.
    val vectorRelease=Flipped(Decoupled(new UnifiedOverlapReleaseIntentV2))
    val producerFence=Flipped(Decoupled(new UnifiedOverlapProducerFenceV2))
    val vectorDone=Decoupled(new UnifiedOverlapDoneV2)
    // Sticky private producer/consumer fault, never an ownership-credit return.
    val ownerFault=Flipped(Valid(new UnifiedOverlapOwnerFaultV2))
  })
  val context=Reg(new UnifiedBlockDispatchV1);val active=RegInit(false.B);val poison=RegInit(false.B)
  val idle::owned::report::locked::Nil=Enum(4)
  val ms=RegInit(idle);val vs=RegInit(idle)
  val ml=Reg(new UnifiedOverlapLeaseV2);val vl=Reg(new UnifiedOverlapLeaseV2)
  val md=Reg(new UnifiedOverlapDoneV2);val vd=Reg(new UnifiedOverlapDoneV2)
  val mNext=RegInit(0.U(32.W));val vNext=RegInit(0.U(32.W));val groupIssued=RegInit(false.B)
  val vIssued=RegInit(0.U(17.W));val vReturned=RegInit(0.U(17.W))
  val pending=RegInit(false.B);val pendingTag=Reg(new UnifiedOverlapTagV2)
  val vError=RegInit(false.B);val fenceSeen=RegInit(false.B);val fenceStatus=Reg(UInt(8.W))
  val mBase=Reg(UInt(64.W));val groupOffered=RegInit(false.B);val stepOffered=RegInit(false.B)
  val groupOfferBits=Reg(new MatrixStreamGroup(false,false));val stepOfferBits=Reg(new MatrixStreamStep(0))
  val vOffer=RegInit(false.B);val vOfferBits=Reg(new UnifiedOverlapVectorRequestV2)
  val vectorQuarantine=RegInit(false.B);val matrixQuarantine=RegInit(false.B)
  val faultNow=WireDefault(false.B)
  when(io.ownerFault.valid){poison:=true.B;faultNow:=true.B;when(io.ownerFault.bits.resource===1.U){vError:=true.B}}
  val noDebt=ms===idle && vs===idle && !pending && !vOffer && !groupOffered && !stepOffered
  io.context:=context;io.active:=active;io.resetRequired:=poison||io.physicalMatrixResetRequired
  io.allResourcesDrained:=active && noDebt && !io.resetRequired && !faultNow
  io.begin.ready:= !active && noDebt && !io.resetRequired
  val (decoded,known)=UnifiedRuntimeProfile.decode(io.begin.bits.launch.profileId)
  when(io.begin.fire){
    context:=io.begin.bits;active:=true.B;mNext:=0.U;vNext:=0.U
    when(!known || decoded.asUInt=/=io.begin.bits.profile.asUInt){poison:=true.B;faultNow:=true.B}
  }
  io.end.ready:=active && noDebt && !io.resetRequired && !faultNow && io.end.bits===context.transactionId
  when(io.end.fire){active:=false.B}
  when(io.end.valid && active && io.end.bits=/=context.transactionId){poison:=true.B;faultNow:=true.B}
  def sameLease(a:UnifiedOverlapLeaseV2,b:UnifiedOverlapLeaseV2):Bool=a.asUInt===b.asUInt
  def admitted(l:UnifiedOverlapLeaseV2,next:UInt):Bool=
    l.transactionId===context.transactionId && l.ownerSequence===next && next=/="hffffffff".U
  // Stage1 is raw Matrix resource qualification. Stage2 is the planned36-op
  // 32BF16 MoE merge tile. No other operators silently become supported.
  val mLegal=admitted(io.matrixLease.bits,mNext) && io.matrixLease.bits.stage===1.U && io.matrixLease.bits.expectedOperations===0.U && io.matrixLease.bits.token===0.U && io.matrixLease.bits.tileOrdinal===0.U
  val vLegal=admitted(io.vectorLease.bits,vNext) && io.vectorLease.bits.stage===2.U && io.vectorLease.bits.expectedOperations===36.U && context.profile.mlp===1.U && io.vectorLease.bits.token<context.launch.tokens && (io.vectorLease.bits.tileOrdinal.pad(32)<<5)<context.profile.hidden && context.profile.hidden(4,0)===0.U
  // End has priority over new acquire: no accepted owner may outlive context.
  io.matrixLease.ready:=active && ms===idle && !io.end.valid && !io.resetRequired && !faultNow && mLegal
  io.vectorLease.ready:=active && vs===idle && !io.end.valid && !io.resetRequired && !faultNow && vLegal
  when(active && ms===idle && io.matrixLease.valid && !mLegal){poison:=true.B;faultNow:=true.B}
  when(active && vs===idle && io.vectorLease.valid && !vLegal){poison:=true.B;faultNow:=true.B}
  when(io.matrixLease.fire){ml:=io.matrixLease.bits;ms:=owned;mNext:=mNext+1.U;groupIssued:=false.B;mBase:=io.physicalMatrixAcceptedSteps}
  when(io.vectorLease.fire){vl:=io.vectorLease.bits;vs:=owned;vNext:=vNext+1.U;vIssued:=0.U;vReturned:=0.U;vError:=false.B;fenceSeen:=false.B}

  val mOwn=active && ms===owned
  val mUnknownNow=(io.physicalMatrix.result.valid || io.physicalMatrix.done.valid) && (!mOwn || !groupIssued)
  // Owned skid registers preserve accepted offers even if the old feeder
  // withdraws its unaccepted queue output on a local error. Step is elastic:
  // a real physical fire may refill the same register without adding II2.
  io.matrixGroup.ready:=mOwn && !groupIssued && !groupOffered && !mUnknownNow && !matrixQuarantine && !io.physicalMatrixResetRequired
  io.physicalMatrix.group.valid:=groupOffered
  io.physicalMatrix.group.bits:=groupOfferBits
  when(io.matrixGroup.fire){groupOffered:=true.B;groupOfferBits:=io.matrixGroup.bits;groupOfferBits.tag:=ml.ownerSequence}
  when(io.physicalMatrix.group.fire){groupIssued:=true.B;groupOffered:=false.B}
  io.matrixStep.ready:=mOwn && groupIssued && (!stepOffered || io.physicalMatrix.step.ready) && !io.physicalMatrix.done.valid && !mUnknownNow && !matrixQuarantine && !io.physicalMatrixResetRequired
  io.physicalMatrix.step.valid:=stepOffered
  io.physicalMatrix.step.bits:=stepOfferBits
  when(io.physicalMatrix.step.fire){stepOffered:=false.B}
  when(io.matrixStep.fire){stepOffered:=true.B;stepOfferBits:=io.matrixStep.bits}
  // Already-held physical offers remain owned by latched ml through an
  // undrained error report/locked state until their real fire or isolation reset.
  // No fresh upstream offer may enter on terminal commit.
  // Existing accepted returns must still drain if another resource poisons.
  io.matrixResult.valid:=mOwn && groupIssued && !matrixQuarantine && io.physicalMatrix.result.valid
  io.matrixResult.bits:=io.physicalMatrix.result.bits
  io.physicalMatrix.result.ready:=mOwn && groupIssued && !matrixQuarantine && io.matrixResult.ready
  io.physicalMatrix.abort:=false.B
  io.physicalMatrix.done.ready:=mOwn && groupIssued && !matrixQuarantine
  when(io.physicalMatrix.done.fire){
    val bad=io.physicalMatrix.done.bits.error || io.physicalMatrix.done.bits.tag=/=ml.ownerSequence || io.physicalMatrixResetRequired || io.physicalMatrixAcceptedSteps<mBase || groupOffered || stepOffered || io.physicalMatrix.group.valid || io.physicalMatrix.step.valid || io.physicalMatrix.result.valid
    val failed=bad||poison||faultNow
    md:=0.U.asTypeOf(new UnifiedOverlapDoneV2);md.lease:=ml;md.status:=Mux(failed,2.U,0.U)
    md.issuedSliceSteps:=Mux(bad,0.U,io.physicalMatrixAcceptedSteps-mBase);md.drained:= !bad;md.resetRequired:=failed;ms:=report
    when(bad){poison:=true.B;faultNow:=true.B}
  }
  when(mUnknownNow){poison:=true.B;faultNow:=true.B;matrixQuarantine:=true.B}
  io.matrixDone.valid:=ms===report;io.matrixDone.bits:=md
  when(io.matrixDone.fire){ms:=Mux(md.resetRequired,locked,idle)}

  val vOwn=active && vs===owned
  val t=io.vectorRequest.bits.identity
  // Accepted-but-not-yet-physical offer owns the next serial already.
  val vAccepted=vIssued+vOffer.asUInt
  val vIdentity=t.transactionId===context.transactionId && t.resource===1.U && t.ownerSequence===vl.ownerSequence && t.stage===vl.stage &&
    t.serial===vAccepted(15,0) && t.token===vl.token && t.tileOrdinal===vl.tileOrdinal
  val vCanIssue=vOwn && !pending && !vOffer && !vectorQuarantine && !io.physicalVectorResult.valid && vIssued<vl.expectedOperations
  io.vectorRequest.ready:=vCanIssue && vIdentity && !io.vectorRelease.valid
  when(io.vectorRequest.fire){vOffer:=true.B;vOfferBits:=io.vectorRequest.bits}
  // Accepted offer remains owned/stable through poison until physical fire/reset.
  io.physicalVectorRequest.valid:=vOffer
  io.physicalVectorRequest.bits:=vOfferBits.payload
  when(vOwn && io.vectorRequest.valid && (!vIdentity || vAccepted>=vl.expectedOperations)){poison:=true.B;faultNow:=true.B;vError:=true.B}
  when(io.physicalVectorRequest.fire){vOffer:=false.B;pending:=true.B;pendingTag:=vOfferBits.identity;vIssued:=vIssued+1.U}
  io.vectorResult.valid:=vOwn && pending && !vectorQuarantine && io.physicalVectorResult.valid
  io.vectorResult.bits.identity:=pendingTag;io.vectorResult.bits.payload:=io.physicalVectorResult.bits
  io.physicalVectorResult.ready:=vOwn && pending && !vectorQuarantine && io.vectorResult.ready
  when(io.vectorResult.fire){pending:=false.B;vReturned:=vReturned+1.U;when(io.physicalVectorResult.bits.error){vError:=true.B}}
  when(io.physicalVectorResult.valid && !pending){poison:=true.B;faultNow:=true.B;vError:=true.B;vectorQuarantine:=true.B}
  val fenceIdentity=sameLease(io.producerFence.bits.lease,vl)
  io.producerFence.ready:=vOwn && !fenceSeen && fenceIdentity && io.producerFence.bits.drained
  when(vOwn && io.producerFence.valid && (!fenceIdentity || !io.producerFence.bits.drained)){poison:=true.B;faultNow:=true.B;vError:=true.B}
  when(io.producerFence.fire){fenceSeen:=true.B;fenceStatus:=io.producerFence.bits.status}
  val releaseIdentity=sameLease(io.vectorRelease.bits.lease,vl)
  val countsMatch=io.vectorRelease.bits.issued===vIssued && io.vectorRelease.bits.returned===vReturned
  io.vectorRelease.ready:=vOwn && releaseIdentity && countsMatch && !pending && !vOffer && !vectorQuarantine && !io.physicalVectorResult.valid && vIssued===vReturned && fenceSeen
  when(vOwn && io.vectorRelease.valid && (!releaseIdentity || !countsMatch)){poison:=true.B;faultNow:=true.B;vError:=true.B}
  when(io.vectorRelease.fire){
    val bad=poison||faultNow||vError||fenceStatus=/=0.U||io.vectorRelease.bits.diagnosticStatus=/=0.U||vIssued=/=vl.expectedOperations
    vd:=0.U.asTypeOf(new UnifiedOverlapDoneV2);vd.lease:=vl;vd.operationCountsValid:=true.B;vd.issued:=vIssued;vd.returned:=vReturned
    vd.status:=Mux(bad,2.U,0.U);vd.drained:=true.B;vd.resetRequired:=bad;vs:=report
    when(bad){poison:=true.B}
  }
  io.vectorDone.valid:=vs===report;io.vectorDone.bits:=vd
  when(io.vectorDone.fire){vs:=Mux(vd.resetRequired,locked,idle)}
}
