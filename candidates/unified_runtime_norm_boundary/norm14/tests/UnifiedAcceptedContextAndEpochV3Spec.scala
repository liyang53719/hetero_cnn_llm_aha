// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Control probe only. Production authority is the actual admission instance. */
class UnifiedAcceptedContextDenseProbeV3 extends Module {
  val io=IO(new Bundle {
    val active=Input(Bool());val acceptedTxn=Input(UInt(64.W));val offeredTxn=Input(UInt(64.W))
    val acceptedTag=Input(UInt(32.W));val offeredTag=Input(UInt(32.W));val profile=Input(UInt(3.W))
    val matches=Output(Bool());val decodeLegal=Output(Bool());val mayOffer=Output(Bool())
  })
  val accepted=WireDefault(0.U.asTypeOf(new UnifiedBlockDispatchV1))
  val (shape,_)=UnifiedRuntimeProfile.decode(io.profile)
  accepted.profile:=shape;accepted.transactionId:=io.acceptedTxn
  accepted.launch.profileId:=io.profile;accepted.launch.version:=1.U;accepted.launch.opcode:=0.U
  accepted.launch.tokens:=128.U;accepted.launch.tag:=io.acceptedTag
  val offered=WireDefault(accepted);offered.transactionId:=io.offeredTxn;offered.launch.tag:=io.offeredTag
  val c=WireDefault(0.U.asTypeOf(new UnifiedRuntimeDenseCommandV2));c.context:=offered
  c.role:=UnifiedDenseRoleV2.MixerInput.U;c.firstOwnerSequence:=0.U
  c.input:="h01000000".U;c.weight:="h02000000".U;c.output:="h04000000".U
  val p=UnifiedRuntimeDensePlanV2.decode(c)
  io.matches:=UnifiedAcceptedContextV3.matches(io.active,accepted,offered)
  io.decodeLegal:=p.valid;io.mayOffer:=io.matches && p.valid
}

class UnifiedAcceptedContextAndEpochV3Spec extends AnyFlatSpec with ChiselScalatestTester {
  it should "accept actual first transaction zero and later identities only with the entire active context" in {
    test(new UnifiedAcceptedContextDenseProbeV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.io.acceptedTag.poke(91.U);d.io.offeredTag.poke(91.U);d.io.active.poke(true.B)
      for(profile<-0 until 5;txn<-Seq(BigInt(0),BigInt(1),BigInt("100000001",16))){
        d.io.profile.poke(profile.U);d.io.acceptedTxn.poke(txn.U);d.io.offeredTxn.poke(txn.U)
        d.io.decodeLegal.expect(true.B);d.io.matches.expect(true.B);d.io.mayOffer.expect(true.B)
        d.io.active.poke(false.B);d.io.mayOffer.expect(false.B);d.io.active.poke(true.B)
        d.io.offeredTxn.poke((txn^1).U);d.io.mayOffer.expect(false.B);d.io.offeredTxn.poke(txn.U)
        d.io.offeredTag.poke(92.U);d.io.mayOffer.expect(false.B);d.io.offeredTag.poke(91.U)
      }
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
