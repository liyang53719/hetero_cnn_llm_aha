// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

class UnifiedRuntimeDensePlanProbeV2 extends Module {
  val io=IO(new Bundle {
    val profileId=Input(UInt(3.W));val tokens=Input(UInt(16.W));val role=Input(UInt(4.W))
    val corrupt=Input(Bool());val input=Input(UInt(64.W));val weight=Input(UInt(64.W));val output=Input(UInt(64.W))
    val sequence=Input(UInt(32.W));val plan=Output(new UnifiedRuntimeDensePlanV2)
  })
  val c=WireDefault(0.U.asTypeOf(new UnifiedRuntimeDenseCommandV2))
  val (profile,_)=UnifiedRuntimeProfile.decode(io.profileId)
  c.context.profile:=profile;c.context.transactionId:=11.U
  when(io.corrupt){c.context.profile.hidden:=32.U}
  c.context.launch.version:=1.U;c.context.launch.profileId:=io.profileId;c.context.launch.tokens:=io.tokens
  c.role:=io.role;c.input:=io.input;c.weight:=io.weight;c.output:=io.output;c.firstOwnerSequence:=io.sequence
  io.plan:=UnifiedRuntimeDensePlanV2.decode(c)
}

/** These are targeted real Chisel control tests, NOT five-block numerical
  * regressions. The bridge return packets are explicit test inputs. */
class UnifiedRuntimeDenseIntegrationV2Spec extends AnyFlatSpec with ChiselScalatestTester {
  private def zero(x:Data):Unit=x match {
    case b:Bool=>b.poke(false.B)
    case u:UInt=>u.poke(0.U)
    case v:Vec[_]=>v.getElements.foreach(zero)
    case r:Record=>r.elements.values.foreach(zero)
    case _=>throw new IllegalArgumentException("test input")
  }
  private def snap(x:Data):Seq[BigInt]=x match {
    case b:Bool=>Seq(b.peek().litValue)
    case u:UInt=>Seq(u.peek().litValue)
    case v:Vec[_]=>v.getElements.toSeq.flatMap(snap)
    case r:Record=>r.elements.values.toSeq.flatMap(snap)
    case _=>throw new IllegalArgumentException("test snapshot")
  }
  behavior of "Original feeder runtime integration"
  it should "decode five profiles in one DUT without changing hardware or Qwen2 numerical boundaries" in {
    test(new UnifiedRuntimeDensePlanProbeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.io.corrupt.poke(false.B);d.io.sequence.poke(0.U)
      d.io.input.poke(BigInt("100000",16).U);d.io.weight.poke(BigInt("1000000",16).U);d.io.output.poke(BigInt("10000000",16).U)
      val hidden=Seq(1536,1024,1024,2048,2048)
      val mixer=Seq(1536,6144,4096,8192,8192)
      val outK=Seq(1536,2048,2048,4096,4096)
      val ffn=Seq(8960,3584,3584,0,0)
      for(pid<-0 until 5;m<-Seq(16,128);role<-0 until 16){
        d.io.profileId.poke(pid.U);d.io.tokens.poke(m.U);d.io.role.poke(role.U)
        val gdn=pid==1||pid==3
        val legal=role==0||role==3||((role==1||role==2)&& !gdn)||((role>=4&&role<=6)&&pid<3)||((role==7||role==8)&&gdn)
        val (k,n)=role match {
          case 0=>(hidden(pid),mixer(pid))
          case 1|2=>(hidden(pid),if(pid==0)256 else 512)
          case 3=>(outK(pid),hidden(pid))
          case 4|5=>(hidden(pid),ffn(pid))
          case 6=>(ffn(pid),hidden(pid))
          case 7=>(hidden(pid),outK(pid))
          case 8=>(hidden(pid),if(pid==1)32 else 64)
          case _=>(0,0)
        }
        d.io.plan.valid.expect(legal.B)
        d.io.plan.route.expect((if(pid==0)1 else 0).U)
        if(legal){
          d.io.plan.job.m.expect(m.U);d.io.plan.job.n.expect(n.U);d.io.plan.job.k.expect(k.U)
          d.io.plan.job.activationBf16.expect((pid!=0).B);d.io.plan.job.outputBf16.expect((pid!=0).B)
          d.io.plan.job.materializeDenseOutput.expect((pid==0&&role>=3&&role<=6).B)
          d.io.plan.job.writeBytes.expect((BigInt(m)*n*(if(pid==0)4 else 2)).U)
          d.io.plan.qwen2Boundary.requiresOrderedQkvReduction.expect((pid==0&&role<=2).B)
        }
        d.clock.step()
      }
      d.io.profileId.poke(0.U);d.io.role.poke(0.U);d.io.tokens.poke(1.U);d.io.plan.valid.expect(false.B)
      d.io.tokens.poke(128.U);d.io.corrupt.poke(true.B);d.io.plan.valid.expect(false.B);d.io.corrupt.poke(false.B)
      for(pid<-5 until 8){d.io.profileId.poke(pid.U);d.io.plan.valid.expect(false.B)}
      d.io.profileId.poke(3.U)
      for(m<-Seq(0,129)){d.io.tokens.poke(m.U);d.io.plan.valid.expect(false.B)}
      d.io.tokens.poke(128.U);d.io.output.poke(BigInt("100000",16).U);d.io.plan.valid.expect(false.B)
      d.io.output.poke(BigInt("10000000",16).U);d.io.input.poke(BigInt("100001",16).U);d.io.plan.valid.expect(false.B)
      d.io.input.poke(BigInt("ffffffffffffc0",16).U);d.io.plan.valid.expect(false.B)
      d.io.input.poke(BigInt("100000",16).U);d.io.sequence.poke(BigInt("ffffffff",16).U);d.io.plan.valid.expect(false.B)
      // 128x8192 needs at most8*32=256 groups. Reject a base leaving only255.
      d.io.sequence.poke(BigInt("ffffff00",16).U);d.io.plan.valid.expect(false.B)
      d.io.sequence.poke(BigInt("fffffeff",16).U);d.io.plan.valid.expect(true.B)
      d.io.plan.maximumMatrixGroups.expect(256.U)
    }
  }
  it should "retain two real group identities and never turn an undrained error into reusable ownership" in {
    test(new UnifiedDenseGroupLeaseBridgeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      Seq(d.io.start.bits,d.io.feeder.group.bits,d.io.feeder.step.bits,d.io.result.bits,d.io.done.bits).foreach(zero)
      Seq(d.io.start.valid,d.io.feeder.group.valid,d.io.feeder.step.valid,d.io.feeder.abort,d.io.result.valid,d.io.done.valid,d.io.finish,d.io.lease.ready,d.io.group.ready,d.io.step.ready,d.io.feeder.done.ready).foreach(_.poke(false.B))
      d.io.feeder.result.ready.poke(true.B)
      d.io.start.bits.valid.poke(true.B);d.io.start.bits.context.transactionId.poke(11.U);d.io.start.bits.firstOwnerSequence.poke(7.U)
      d.io.start.valid.poke(true.B);d.io.start.ready.expect(true.B);d.clock.step();d.io.start.valid.poke(false.B)
      for(seq<-Seq(7,8)){
        d.io.feeder.group.bits.tag.poke(91.U);d.io.feeder.group.bits.opcode.poke(32.U);d.io.feeder.group.bits.sliceMask.poke(255.U)
        d.io.feeder.group.valid.poke(true.B);d.io.feeder.group.ready.expect(true.B);d.clock.step();d.io.feeder.group.valid.poke(false.B)
        d.io.lease.valid.expect(true.B);d.io.lease.bits.ownerSequence.expect(seq.U);d.io.lease.bits.transactionId.expect(11.U)
        val held=snap(d.io.lease.bits);d.clock.step(3);assert(snap(d.io.lease.bits)==held)
        d.io.lease.ready.poke(true.B);d.clock.step();d.io.lease.ready.poke(false.B)
        d.io.group.valid.expect(true.B);d.io.group.bits.tag.expect(91.U)
        d.io.group.ready.poke(true.B);d.clock.step();d.io.group.ready.poke(false.B)
        d.io.feeder.step.valid.poke(true.B);d.io.feeder.step.bits.context.poke(2.U);d.io.step.ready.poke(true.B)
        d.io.step.valid.expect(true.B);d.io.step.bits.context.expect(2.U);d.clock.step();d.io.feeder.step.valid.poke(false.B)
        zero(d.io.done.bits);d.io.done.bits.lease.transactionId.poke(11.U);d.io.done.bits.lease.ownerSequence.poke(seq.U);d.io.done.bits.lease.stage.poke(1.U)
        d.io.done.bits.drained.poke((seq==7).B);d.io.done.bits.status.poke((if(seq==7)0 else 2).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
        d.io.feeder.done.valid.expect(true.B);d.io.feeder.done.bits.tag.expect(91.U);d.io.feeder.done.bits.error.expect((seq==8).B)
        val reply=snap(d.io.feeder.done.bits);d.io.finish.poke(true.B);d.clock.step(2);assert(snap(d.io.feeder.done.bits)==reply);d.io.finish.poke(false.B)
        d.io.feeder.done.ready.poke(true.B);d.clock.step();d.io.feeder.done.ready.poke(false.B)
      }
      d.io.resetRequired.expect(true.B);d.io.allGroupsReturned.expect(false.B);d.io.start.ready.expect(false.B)
      d.io.nextOwnerSequence.expect(9.U)
    }
  }
  it should "include a present-cycle stray return or abort in terminal drain and new-accept gates" in {
    test(new UnifiedDenseGroupLeaseBridgeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      def init():Unit={
        Seq(d.io.start.bits,d.io.feeder.group.bits,d.io.feeder.step.bits,d.io.result.bits,d.io.done.bits).foreach(zero)
        Seq(d.io.start.valid,d.io.feeder.group.valid,d.io.feeder.step.valid,d.io.feeder.abort,d.io.result.valid,d.io.done.valid,d.io.finish,d.io.lease.ready,d.io.group.ready,d.io.step.ready,d.io.feeder.done.ready).foreach(_.poke(false.B))
        d.io.feeder.result.ready.poke(true.B)
      }
      // Test isolation only; it does not attest isolation of a real DDR/Matrix.
      for(abort<-Seq(false,true)){
        init();d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
        d.io.start.bits.valid.poke(true.B);d.io.start.bits.context.transactionId.poke(11.U);d.io.start.bits.firstOwnerSequence.poke(7.U)
        d.io.start.valid.poke(true.B);d.io.start.ready.expect(true.B);d.clock.step();d.io.start.valid.poke(false.B)
        d.io.allGroupsReturned.expect(true.B);d.io.resetRequired.expect(false.B)
        d.io.finish.poke(true.B);d.io.feeder.group.valid.poke(true.B)
        if(abort)d.io.feeder.abort.poke(true.B) else d.io.done.valid.poke(true.B)
        // This is the exact cycle a real feeder terminal would be sampled.
        d.io.allGroupsReturned.expect(false.B);d.io.resetRequired.expect(true.B)
        d.io.feeder.group.ready.expect(false.B);d.clock.step()
        d.io.finish.poke(false.B);d.io.feeder.group.valid.poke(false.B)
        d.io.feeder.abort.poke(false.B);d.io.done.valid.poke(false.B)
        d.io.resetRequired.expect(true.B);d.io.start.ready.expect(false.B)
      }
      init();d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
      d.io.start.valid.poke(true.B);d.io.feeder.abort.poke(true.B)
      d.io.start.ready.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }
  it should "retain held offers and report error after a prior wrong-identity completion" in {
    test(new UnifiedDenseGroupLeaseBridgeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      for(abortDuringHeldLease<-Seq(false,true)){
      Seq(d.io.start.bits,d.io.feeder.group.bits,d.io.feeder.step.bits,d.io.result.bits,d.io.done.bits).foreach(zero)
      Seq(d.io.start.valid,d.io.feeder.group.valid,d.io.feeder.step.valid,d.io.feeder.abort,d.io.result.valid,d.io.done.valid,d.io.finish,d.io.lease.ready,d.io.group.ready,d.io.step.ready,d.io.feeder.done.ready).foreach(_.poke(false.B))
      d.io.feeder.result.ready.poke(true.B)
      // Independent fault scenarios, test reset only (not physical isolation).
      d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
      d.io.start.bits.valid.poke(true.B);d.io.start.bits.context.transactionId.poke(11.U);d.io.start.bits.firstOwnerSequence.poke(7.U)
      d.io.start.valid.poke(true.B);d.io.start.ready.expect(true.B);d.clock.step();d.io.start.valid.poke(false.B)
      d.io.feeder.group.bits.tag.poke(91.U);d.io.feeder.group.valid.poke(true.B)
      d.io.feeder.group.ready.expect(true.B);d.clock.step();d.io.feeder.group.valid.poke(false.B)
      // A new fault cannot retract a lease offer that was already valid.
      val lease=snap(d.io.lease.bits);d.io.lease.valid.expect(true.B)
      d.io.feeder.abort.poke(abortDuringHeldLease.B);d.clock.step();d.io.feeder.abort.poke(false.B)
      d.io.lease.valid.expect(true.B);assert(snap(d.io.lease.bits)==lease)
      d.io.lease.ready.poke(true.B);d.clock.step();d.io.lease.ready.poke(false.B)
      val group=snap(d.io.group.bits);d.clock.step(2)
      d.io.group.valid.expect(true.B);assert(snap(d.io.group.bits)==group)
      d.io.group.ready.poke(true.B);d.clock.step();d.io.group.ready.poke(false.B)
      d.io.done.bits.lease.transactionId.poke(11.U);d.io.done.bits.lease.ownerSequence.poke(8.U);d.io.done.bits.lease.stage.poke(1.U)
      d.io.done.bits.drained.poke(true.B);d.io.done.valid.poke(true.B)
      d.io.done.ready.expect(false.B);d.io.resetRequired.expect(true.B);d.clock.step()
      // A real current-lease reply may drain but can no longer report success.
      d.io.done.bits.lease.ownerSequence.poke(7.U);d.io.done.ready.expect(true.B)
      d.clock.step();d.io.done.valid.poke(false.B)
      d.io.feeder.done.valid.expect(true.B);d.io.feeder.done.bits.tag.expect(91.U);d.io.feeder.done.bits.error.expect(true.B)
      val result=snap(d.io.feeder.done.bits);d.clock.step(2)
      assert(snap(d.io.feeder.done.bits)==result);d.io.feeder.done.valid.expect(true.B)
      d.io.feeder.done.ready.poke(true.B);d.clock.step()
      d.io.allGroupsReturned.expect(false.B);d.io.resetRequired.expect(true.B);d.io.start.ready.expect(false.B)
      }
    }
  }

}
