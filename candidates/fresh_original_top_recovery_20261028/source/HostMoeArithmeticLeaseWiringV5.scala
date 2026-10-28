// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private event wiring, not a new dispatcher or a Host permission interface.
  * Every acquisition is an ACTUAL numerical child begin/job.fire inside the
  * original Top. Every retirement is its matching real terminal fire. Format
  * shares the physical Vector resource but has its own actual owner operation
  * serial. The side ledger also binds full allocation64 and accepted Host epoch.
  * Fixed token/tile/head/chunk/phase zero means WHOLE GROUP, not fake per-tile
  * identity. Original consumers keep their real token/tile pending identities.
  */
object HostMoeArithmeticLeaseWiringV5 {
  val RouterStage=64;val ActivationStage=65;val SigmoidStage=66
  val MergeStage=67;val ResidualStage=68
  def connect(a:UnifiedMoeSharedArithmeticAdapterV5,
      l:HostMoeRuntimePhaseLeaseV5,phaseOwned:Bool,
      loop:UnifiedMoeRuntimeExpertLoopV4,sigmoid:UnifiedMoeSharedGateSigmoidOwnerV5,
      merge:UnifiedMoePhaseMergeOwnerV5,residual:UnifiedMoePhaseResidualOwnerV5):(Bool,Bool)={
    def packet(owner:UInt,stage:Int,resource:Int,expected:UInt):UnifiedMoeArithmeticLeaseV5={
      val p=WireDefault(0.U.asTypeOf(new UnifiedMoeArithmeticLeaseV5))
      p.lease.identity.transactionId:=l.context.transactionId
      p.lease.identity.ownerSequence:=owner;p.lease.identity.stage:=stage.U
      p.lease.resource:=resource.U;p.lease.expectedOperations:=expected
      p.allocationSequence:=l.allocationSequence;p.hostEpoch:=l.context.host.epoch
      p
    }
    val m=l.context.tokens.pad(32);val ffn=loop.io.actualFfnJob
    val rows=ffn.groupRows.pad(32)
    val activationOwner=ffn.firstOwnerSequence+2.U
    val sigmoidOwner=l.firstOwnerSequence+HostMoeOwnerRangeV5.SharedSigmoid.U
    val mergeOwner=l.firstOwnerSequence+HostMoeOwnerRangeV5.Merge.U
    val residualOwner=l.firstOwnerSequence+HostMoeOwnerRangeV5.Residual.U
    val packets=Seq(
      packet(l.firstOwnerSequence,RouterStage,2,m*1040.U),
      packet(activationOwner,ActivationStage,2,rows*3072.U),
      packet(sigmoidOwner,SigmoidStage,2,m*4.U),
      packet(l.firstOwnerSequence,RouterStage,1,m*8.U),
      packet(activationOwner,ActivationStage,1,rows*1024.U),
      packet(sigmoidOwner,SigmoidStage,1,m),
      packet(mergeOwner,MergeStage,1,m*2304.U),
      packet(residualOwner,ResidualStage,1,m*128.U))
    val start=Seq(loop.io.begin.fire,loop.io.actualFfnStart,sigmoid.io.begin.fire,
      loop.io.begin.fire,loop.io.actualFfnStart,sigmoid.io.begin.fire,
      merge.io.begin.fire,residual.io.begin.fire)
    val ffnSource=ffn.context.asUInt===l.context.asUInt && ffn.groupRows>=1.U && ffn.groupRows<=128.U &&
      ffn.firstOwnerSequence>l.firstOwnerSequence &&
      ffn.firstOwnerSequence.pad(33)+3.U<l.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Count.U
    val eligible=Seq(loop.io.begin.bits.asUInt===l.asUInt,ffnSource,sigmoid.io.begin.bits.lease.asUInt===l.asUInt,
      loop.io.begin.bits.asUInt===l.asUInt,ffnSource,sigmoid.io.begin.bits.lease.asUInt===l.asUInt,
      merge.io.begin.bits.lease.asUInt===l.asUInt,residual.io.begin.bits.lease.asUInt===l.asUInt)
    val activationRetired=loop.io.actualDownFire || loop.io.actualSharedDownFire
    val finish=Seq(loop.io.done.fire,activationRetired,sigmoid.io.done.fire,
      loop.io.done.fire,activationRetired,sigmoid.io.done.fire,
      merge.io.done.fire,residual.io.done.fire)
    val status=Seq(loop.io.done.bits.status,Status.Ok.U(8.W),sigmoid.io.done.bits.status,
      loop.io.done.bits.status,Status.Ok.U(8.W),sigmoid.io.done.bits.status,
      merge.io.done.bits.status,residual.io.done.bits.status)
    val routedExact=loop.io.done.bits.transactionId===l.context.transactionId &&
      loop.io.done.bits.allocationSequence===l.allocationSequence
    val activationExact=loop.io.actualDown.context.asUInt===l.context.asUInt &&
      loop.io.actualDown.ownerSequence===ffn.firstOwnerSequence+3.U && loop.io.actualDown.stage===2.U
    val sigmoidExact=sigmoid.io.done.bits.context.asUInt===l.context.asUInt &&
      sigmoid.io.done.bits.allocationSequence===l.allocationSequence && sigmoid.io.done.bits.ownerSequence===sigmoidOwner
    val mergeExact=merge.io.done.bits.context.asUInt===l.context.asUInt &&
      merge.io.done.bits.allocationSequence===l.allocationSequence && merge.io.done.bits.ownerSequence===mergeOwner
    val residualExact=residual.io.done.bits.context.asUInt===l.context.asUInt &&
      residual.io.done.bits.allocationSequence===l.allocationSequence && residual.io.done.bits.ownerSequence===residualOwner
    val finishExact=Seq(routedExact,activationExact,sigmoidExact,routedExact,activationExact,sigmoidExact,mergeExact,residualExact)
    val badEvent=(0 until 8).map(i=>(start(i) && (!phaseOwned || !eligible(i))) ||
      (finish(i) && (!phaseOwned || !finishExact(i)))).reduce(_||_)
    val poison=RegInit(false.B);when(badEvent){poison:=true.B}
    // Keep the actual accepted lease, never recompute a retirement from changed
    // child pins or copy an adapter's own echo as evidence of its producer.
    val accepted=Reg(Vec(8,new UnifiedMoeArithmeticLeaseV5))
    // Preserve actual acquire/retire event order through ONE registered stage.
    // Only16 event bits+64 status bits are new; accepted is the existing lease
    // snapshot. No raw arithmetic payload/result is copied or acknowledged here.
    val acquirePending=RegInit(VecInit(Seq.fill(8)(false.B)))
    val retirePending=RegInit(VecInit(Seq.fill(8)(false.B)))
    val retireStatus=Reg(Vec(8,UInt(8.W)))
    val reuseFault=WireDefault(false.B)
    for(i<-0 until 8){
      val acquireEvent=start(i) && phaseOwned && eligible(i) && !poison
      val retireEvent=finish(i) && phaseOwned && finishExact(i)
      val busy=acquirePending(i) || retirePending(i) ||
        a.io.status(i).active || a.io.status(i).retiring
      when(acquireEvent && busy){reuseFault:=true.B}
      acquirePending(i):=acquireEvent && !busy
      retirePending(i):=retireEvent
      when(acquireEvent && !busy){accepted(i):=packets(i)}
      when(retireEvent){retireStatus(i):=status(i)}
      a.io.acquire(i).valid:=acquirePending(i)
      a.io.acquire(i).bits:=accepted(i)
      a.io.retire(i).valid:=retirePending(i)
      a.io.retire(i).bits.lease:=accepted(i)
      a.io.retire(i).bits.status:=retireStatus(i)
    }
    when(reuseFault){poison:=true.B}
    val eventsPending=acquirePending.asUInt.orR || retirePending.asUInt.orR
    a.io.scalar(0)<>loop.io.routerScalar;a.io.scalar(1)<>loop.io.activationScalar
    a.io.scalar(2)<>sigmoid.io.scalar
    a.io.formatRequest(0)<>loop.io.routerFormatRequest;loop.io.routerFormatResult<>a.io.formatResult(0)
    a.io.formatRequest(1)<>loop.io.activationFormatRequest;loop.io.activationFormatResult<>a.io.formatResult(1)
    a.io.formatRequest(2)<>sigmoid.io.formatRequest;sigmoid.io.formatResult<>a.io.formatResult(2)
    a.io.vectorRequest(0)<>merge.io.vectorRequest;merge.io.vectorResult<>a.io.vectorResult(0)
    a.io.vectorRequest(1)<>residual.io.vectorRequest;residual.io.vectorResult<>a.io.vectorResult(1)
    (poison || badEvent || reuseFault,eventsPending)
  }
}
