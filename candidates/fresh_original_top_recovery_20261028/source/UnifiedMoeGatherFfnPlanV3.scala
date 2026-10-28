// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private original-parent connection, not an allocator, Host API, or new top.
  * Parent retains the exact job accepted by the real Gather owner, the real
  * done.fire receipt, and the accepted-context workspace/weight-role plan.
  * Those packet origins are mandatory: bitwise equality cannot prove origin.
  *
  * Call this at the parent's actual Gather completion capture. Only a legal
  * result may CREATE a new held FFN offer. Once that offer is published, later
  * poison must not retract valid or mutate bits: the parent's ownership/fault
  * protocol must preserve and isolate accepted obligations. Current faults must
  * also be rechecked by the receiving sequencer before a new child start, and
  * by the final block fence. This helper does not claim either wiring exists.
  */
object UnifiedMoeGatherFfnPlanV3 {
  def fromActualGather(accepted:UnifiedMoeActivationGatherJobV2,
      completed:UnifiedMoeGatherCommitV2,reserved:UnifiedMoeFfnGroupJobV3,
      currentFault:Bool):(UnifiedMoeFfnGroupJobV3,Bool)={
    val plan=WireDefault(reserved)
    // The input address comes from the actual ACKed image, never Host data.
    plan.input:=completed.output
    val (_,_,_,ffnLegal)=UnifiedMoeFfnGroupPlanV3.decode(plan)
    val c=accepted.context
    val committedBytes=accepted.group.groupRows.pad(96)*c.profile.hidden*2.U
    val identity=completed.context.asUInt===c.asUInt &&
      completed.group.asUInt===accepted.group.asUInt &&
      completed.gatherOwnerSequence===accepted.gatherOwnerSequence &&
      completed.output===accepted.output &&
      completed.group.transactionId===c.transactionId &&
      completed.group.allocationSequence=/=0.U
    val parentBinding=reserved.context.asUInt===c.asUInt &&
      reserved.expert===accepted.group.expert &&
      reserved.groupRows===accepted.group.groupRows &&
      reserved.input===accepted.output &&
      reserved.allocationEnd===accepted.allocationEnd &&
      reserved.firstOwnerSequence>accepted.gatherOwnerSequence
    val completedOk=completed.status===Status.Ok.U && completed.drained &&
      completed.acknowledgedWriteBytes.pad(96)===committedBytes
    // Map + original postnorm remain live for subsequent expert groups. The
    // sequencer already checks its four writes against gathered input/weights.
    // These two additional known live ranges must not be destroyed either.
    val live=Seq((accepted.metadataBase,16384.U(96.W)),
      (accepted.postnormBase,c.tokens.pad(96)*c.profile.hidden*2.U))
    val groupBytes=accepted.group.groupRows.pad(96)*512.U*2.U
    val writes=Seq((reserved.gateOutput,groupBytes),(reserved.upOutput,groupBytes),
      (reserved.activationOutput,groupBytes),(reserved.downOutput,committedBytes))
    val preserveLive=(for(w<-writes;r<-live)yield
      !(w._1.pad(96)<r._1.pad(96)+r._2 && r._1.pad(96)<w._1.pad(96)+w._2)).reduce(_ && _)
    val liveBounds=live.map{case(base,size)=>base=/=0.U && base(5,0)===0.U &&
      base.pad(96)+size<=(BigInt(1)<<56).U}.reduce(_ && _)
    (plan,!currentFault && identity && parentBinding && completedOk &&
      preserveLive && liveBounds && ffnLegal)
  }
}
