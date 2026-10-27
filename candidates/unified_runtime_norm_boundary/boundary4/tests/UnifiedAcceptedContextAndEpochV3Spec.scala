// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Actual admission control, not a host-shaped fabricated accepted packet.
  * The completion input is an explicit control-test driver, NOT numeric done. */
class UnifiedAcceptedContextDenseProbeV3 extends Module {
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new UnifiedBlockLaunchV1))
    val completion=Flipped(Decoupled(new UnifiedBlockCompletionV1))
    val result=Decoupled(new UnifiedBlockResultV1)
    val dispatchReady=Input(Bool());val dispatchValid=Output(Bool())
    val offeredTxn=Input(UInt(64.W));val offeredTag=Input(UInt(32.W));val corruptProfile=Input(Bool())
    val corruptGeneration=Input(Bool());val corruptInput=Input(Bool())
    val active=Output(Bool());val context=Output(new UnifiedBlockDispatchV1)
    val matches=Output(Bool());val decodeLegal=Output(Bool());val mayOffer=Output(Bool())
  })
  val admission=Module(new UnifiedBlockAdmission)
  admission.io.launch<>io.launch;admission.io.completion<>io.completion;io.result<>admission.io.result
  admission.io.dispatch.ready:=io.dispatchReady;io.dispatchValid:=admission.io.dispatch.valid
  // active also covers holding rejected launches. Only the real dispatch fire
  // creates this test owner's authority; a retained/terminal packet cannot.
  val dispatchOwned=RegInit(false.B)
  when(admission.io.dispatch.fire){dispatchOwned:=true.B}
  when(admission.io.result.fire){dispatchOwned:=false.B}
  val accepted=admission.io.context
  val offered=WireDefault(accepted);offered.transactionId:=io.offeredTxn;offered.launch.tag:=io.offeredTag
  when(io.corruptProfile){offered.profile.hidden:=32.U}
  when(io.corruptGeneration){offered.launch.expectedGeneration:=accepted.launch.expectedGeneration ^ 1.U}
  when(io.corruptInput){offered.launch.input:=accepted.launch.input + 64.U}
  val c=WireDefault(0.U.asTypeOf(new UnifiedRuntimeDenseCommandV2));c.context:=offered
  c.role:=UnifiedDenseRoleV2.MixerInput.U;c.firstOwnerSequence:=0.U
  c.input:=accepted.launch.input;c.weight:=accepted.launch.weights;c.output:=accepted.launch.output
  val p=UnifiedRuntimeDensePlanV2.decode(c)
  io.active:=admission.io.active;io.context:=accepted
  io.matches:=UnifiedAcceptedContextV3.matches(admission.io.active,accepted,offered)
  io.decodeLegal:=p.valid
  io.mayOffer:=dispatchOwned && io.matches && p.valid && !admission.io.result.valid && !admission.io.resetRequired
}
class UnifiedAcceptedContextAndEpochV3Spec extends AnyFlatSpec with ChiselScalatestTester {
  it should "accept real admission first transaction zero and later identities only with the entire active context" in {
    test(new UnifiedAcceptedContextDenseProbeV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.io.launch.valid.poke(false.B);d.io.dispatchReady.poke(false.B);d.io.result.ready.poke(false.B)
      d.io.completion.valid.poke(false.B);d.io.corruptProfile.poke(false.B)
      d.io.corruptGeneration.poke(false.B);d.io.corruptInput.poke(false.B)
      d.io.completion.bits.transactionId.poke(0.U);d.io.completion.bits.tag.poke(0.U)
      d.io.completion.bits.profileId.poke(0.U);d.io.completion.bits.status.poke(0.U)
      d.io.completion.bits.acknowledgedWriteBytes.poke(0.U);d.io.completion.bits.issuedSliceSteps.poke(0.U)
      d.io.completion.bits.drained.poke(true.B);d.io.completion.bits.resetRequired.poke(false.B)
      for(profile<-0 until 5){
        val txn=BigInt(profile);val tag=91+profile
        d.io.offeredTxn.poke(txn.U);d.io.offeredTag.poke(tag.U)
        d.io.active.expect(false.B);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B)
        val l=d.io.launch.bits
        l.version.poke(1.U);l.opcode.poke(0.U);l.profileId.poke(profile.U);l.tag.poke(tag.U)
        l.tokens.poke(128.U);l.positionBase.poke(0.U);l.cacheLength.poke(0.U)
        l.cacheCapacity.poke((if(Set(0,2,4)(profile))128 else 0).U)
        l.expectedGeneration.poke(0.U);l.cold.poke(true.B)
        l.input.poke("h01000000".U);l.weights.poke("h02000000".U);l.output.poke("h04000000".U)
        l.scratch.poke("h08000000".U);l.stateIn.poke("h10000000".U);l.stateOut.poke("h11000000".U)
        l.kvK.poke("h12000000".U);l.kvV.poke("h13000000".U)
        d.io.launch.valid.poke(true.B);d.io.launch.ready.expect(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
        d.io.dispatchValid.expect(true.B);d.io.active.expect(true.B);d.io.context.transactionId.expect(txn.U)
        d.io.context.launch.tag.expect(tag.U);d.io.decodeLegal.expect(true.B);d.io.matches.expect(true.B);d.io.mayOffer.expect(false.B)
        // Mutating unaccepted launch wires must not rewrite the actual snapshot.
        l.tag.poke(999.U);l.tokens.poke(1.U);d.clock.step()
        d.io.context.launch.tag.expect(tag.U);d.io.context.launch.tokens.expect(128.U);d.io.mayOffer.expect(false.B)
        d.io.dispatchReady.poke(true.B);d.io.dispatchValid.expect(true.B);d.clock.step();d.io.dispatchReady.poke(false.B)
        d.io.dispatchValid.expect(false.B);d.io.decodeLegal.expect(true.B);d.io.matches.expect(true.B);d.io.mayOffer.expect(true.B)
        d.io.offeredTxn.poke((txn^1).U);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B);d.io.offeredTxn.poke(txn.U)
        d.io.offeredTag.poke(999.U);d.io.mayOffer.expect(false.B);d.io.offeredTag.poke(tag.U)
        d.io.corruptProfile.poke(true.B);d.io.decodeLegal.expect(false.B);d.io.matches.expect(false.B);d.io.corruptProfile.poke(false.B)
        // Same tag/transaction and legal shape cannot authorize a different launch snapshot.
        d.io.corruptGeneration.poke(true.B);d.io.decodeLegal.expect(true.B);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B)
        d.io.corruptGeneration.poke(false.B);d.io.corruptInput.poke(true.B)
        d.io.decodeLegal.expect(true.B);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B)
        d.io.corruptInput.poke(false.B);d.io.matches.expect(true.B);d.io.mayOffer.expect(true.B)
        // Private control-only completion to retire this admission before next profile.
        d.io.completion.bits.transactionId.poke(txn.U);d.io.completion.bits.tag.poke(tag.U)
        d.io.completion.bits.profileId.poke(profile.U);d.io.completion.valid.poke(true.B)
        d.io.completion.ready.expect(true.B);d.clock.step();d.io.completion.valid.poke(false.B)
        d.io.result.valid.expect(true.B);d.io.result.bits.transactionId.expect(txn.U);d.io.result.bits.status.expect(0.U)
        d.io.mayOffer.expect(false.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
        // The retained valid packet (including txn0) is not authority after actual retirement.
        d.io.decodeLegal.expect(true.B);d.io.active.expect(false.B);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B)
      }
      // Illegal cache capacity is rejected by real Admission although dense shape
      // decode and active/full-context equality alone are both true in holding.
      d.io.launch.bits.profileId.poke(0.U);d.io.launch.bits.tag.poke(196.U)
      d.io.launch.bits.tokens.poke(128.U);d.io.launch.bits.cacheCapacity.poke(0.U)
      d.io.offeredTxn.poke(5.U);d.io.offeredTag.poke(196.U)
      d.io.launch.valid.poke(true.B);d.io.launch.ready.expect(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
      d.io.context.transactionId.expect(5.U);d.io.dispatchValid.expect(false.B);d.io.result.valid.expect(true.B)
      d.io.result.bits.status.expect(1.U);d.io.active.expect(true.B);d.io.matches.expect(true.B)
      d.io.decodeLegal.expect(true.B);d.io.mayOffer.expect(false.B)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      d.io.active.expect(false.B);d.io.matches.expect(false.B);d.io.mayOffer.expect(false.B)
    }
  }
  it should "map original memory tags through a nonreused physical epoch and quarantine a late prior reply without current credit" in {
    test(new UnifiedOriginalMemoryEpochFenceV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.io.parentPoison.poke(false.B);d.io.memory.ready.poke(false.B);d.io.returned.valid.poke(false.B)
      d.io.returned.bits.data.poke(0.U);d.io.returned.bits.tag.poke(0.U);d.io.returned.bits.error.poke(false.B)
      for(i<-0 until 8){
        d.io.request(i).valid.poke(false.B);d.io.response(i).ready.poke(false.B)
        d.io.request(i).bits.write.poke(false.B);d.io.request(i).bits.address.poke((0x10000+64*i).U)
        d.io.request(i).bits.data.poke(0.U);d.io.request(i).bits.mask.poke(0.U);d.io.request(i).bits.tag.poke(77.U)
      }
      def issue():BigInt={
        d.io.request(0).valid.poke(true.B);var cycles=0
        while(!d.io.request(0).ready.peek().litToBoolean && cycles<16){d.clock.step();cycles+=1}
        assert(cycles<16);d.clock.step();d.io.request(0).valid.poke(false.B)
        cycles=0;while(!d.io.memory.valid.peek().litToBoolean && cycles<16){d.clock.step();cycles+=1};assert(cycles<16)
        val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B);tag
      }
      val first=issue();assert(first==0)
      d.io.returned.bits.tag.poke(first.U);d.io.returned.bits.data.poke("h123456789abcdef".U);d.io.returned.valid.poke(true.B)
      d.io.returned.ready.expect(true.B);d.clock.step();d.io.returned.valid.poke(false.B)
      d.io.response(0).valid.expect(true.B);d.io.response(0).bits.tag.expect(77.U)
      for(_<-0 until 2){d.io.response(0).bits.data.expect("h123456789abcdef".U);d.io.response(0).bits.error.expect(false.B);d.clock.step()}
      d.io.response(0).ready.poke(true.B);d.clock.step();d.io.response(0).ready.poke(false.B)
      d.io.retired(0).expect(1.U);d.io.resourcesDrained.expect(true.B)
      val second=issue();assert(second==1 && second!=first)
      // A duplicate from the retired first request never becomes current success/error data.
      d.io.returned.bits.tag.poke(first.U);d.io.returned.valid.poke(true.B)
      d.io.returned.ready.expect(false.B);d.io.quarantined.expect(true.B);d.io.resetRequired.expect(true.B)
      d.io.resourcesDrained.expect(false.B);d.clock.step();d.io.returned.valid.poke(false.B)
      d.io.accepted(0).expect(2.U);d.io.retired(0).expect(1.U);d.io.response(0).valid.expect(false.B)
      // Correct later reply cannot undo quarantine without real external isolation/reset.
      d.io.returned.bits.tag.poke(second.U);d.io.returned.valid.poke(true.B);d.io.returned.ready.expect(false.B)
      d.clock.step();d.io.retired(0).expect(1.U);d.io.resourcesDrained.expect(false.B)
    }
  }
}
