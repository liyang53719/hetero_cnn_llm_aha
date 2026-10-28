// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

final case class HostMoeDenseRoutingSignalsV5(resourcesDrained:Bool,localFault:Bool)

/** Private connection INSIDE the original Top. Three numerical control clients
  * borrow the SAME original Guard -> Kernel -> Dense -> Matrix service. This
  * creates only one held QwenOwnerJob/result and routing state, never a second Dense.
  * Client index is retained from actual request.fire through matching returned
  * result.fire. Physical ownerSequence is already reserved by the original
  * Guard; no local counter fabricates IDs or maps a Host address into authority.
  */
object HostMoeDenseRoutingV5 {
  def connect(guard:HostRuntimeOwnerGuardV5,loop:UnifiedMoeRuntimeExpertLoopV4,
      sigmoid:UnifiedMoeSharedGateSigmoidOwnerV5,
      lease:HostMoeRuntimePhaseLeaseV5,phaseOwned:Bool,currentFault:Bool):HostMoeDenseRoutingSignalsV5={
    val requests=Seq(loop.io.routerDenseJob,loop.io.ffnDenseJob,sigmoid.io.denseJob)
    val results=Seq(loop.io.routerDenseResult,loop.io.ffnDenseResult,sigmoid.io.denseResult)
    val idle::offer::pending::report::Nil=Enum(4)
    val state=RegInit(idle);val selected=Reg(UInt(2.W));val job=Reg(new QwenOwnerJob)
    val reply=Reg(new QwenOwnerResult)
    val quarantine=RegInit(false.B);val poison=RegInit(false.B)
    val hasRequest=requests.map(_.valid).reduce(_||_)
    val chosen=PriorityEncoder(VecInit(requests.map(_.valid)).asUInt)
    val rangeEnd=lease.firstOwnerSequence.pad(33)+HostMoeOwnerRangeV5.Count.U
    val invalidRequest=requests.map(r=>r.valid && (!phaseOwned ||
      r.bits.kind=/=QwenOwnerKind.Dense.U || r.bits.tag<lease.firstOwnerSequence ||
      r.bits.tag.pad(33)>=rangeEnd)).reduce(_||_)
    val unknownResult=guard.io.phaseDone.valid && state=/=pending
    val wrongResult=guard.io.phaseDone.valid && state===pending && guard.io.phaseDone.bits.tag=/=job.tag
    val lostOwner=state=/=idle && !phaseOwned
    val localNow=invalidRequest || unknownResult || wrongResult || lostOwner
    when(localNow){quarantine:=true.B;poison:=true.B}
    when(currentFault){poison:=true.B}
    val localFault=quarantine || poison || localNow
    for(i<-requests.indices){
      requests(i).ready:=state===idle && phaseOwned && !localFault && !currentFault && chosen===i.U
      results(i).valid:=state===report && selected===i.U
      results(i).bits:=reply
      when(requests(i).fire){job:=requests(i).bits;selected:=i.U;state:=offer}
      when(results(i).fire){state:=idle}
    }
    // An already accepted job remains offered under late faults. Only the
    // original Guard decides whether/when that accepted obligation can issue.
    guard.io.phaseJob.valid:=state===offer
    guard.io.phaseJob.bits.context:=lease.context
    guard.io.phaseJob.bits.allocationSequence:=lease.allocationSequence
    guard.io.phaseJob.bits.job:=job
    when(guard.io.phaseJob.fire){state:=pending}
    guard.io.phaseDone.ready:=state===pending && !unknownResult && !wrongResult && !lostOwner
    when(guard.io.phaseDone.fire){reply:=guard.io.phaseDone.bits;state:=report}
    // Faults do not mutate the original returned payload; consumer live-fault
    // fences veto promotion. Unknown identity never consumes a pending credit.
    // Break raw request.valid -> local fault -> same child's offer.valid
    // combinational feedback. Parent still sees the immediate local fault.
    val childPoison=RegNext(currentFault || localFault,false.B)
    loop.io.routerDenseResetRequired:=childPoison
    loop.io.ffnDenseResetRequired:=childPoison
    sigmoid.io.denseResetRequired:=childPoison
    HostMoeDenseRoutingSignalsV5(state===idle && !hasRequest && !guard.io.phaseDone.valid &&
      !localFault && !currentFault,localFault)
  }
}
