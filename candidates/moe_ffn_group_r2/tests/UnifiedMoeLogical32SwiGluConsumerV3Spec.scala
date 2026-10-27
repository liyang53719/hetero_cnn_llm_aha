// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Control-only mocks. These tests do not instantiate arithmetic and cannot
  * qualify P7/Torch equality,32lane throughput,DDR provenance,or a fullblock.
  * Prepared source only: no compile/run has yet been authorized. */
class UnifiedMoeLogical32SwiGluConsumerV3Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "zeroALU logical32 SwiGLU transaction sequencing"
  private def init(d:UnifiedMoeLogical32SwiGluConsumerV3):Unit={
    d.clock.setTimeout(4000)
    d.io.begin.valid.poke(false.B);d.io.begin.bits.gate.poke(0.U);d.io.begin.bits.up.poke(0.U)
    d.io.externalPoison.poke(false.B);d.io.result.ready.poke(false.B)
    d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
    d.io.scalar.result.bits.policy.poke(0.U);d.io.scalar.result.bits.value.poke(0.U)
    d.io.scalar.result.bits.flags.poke(0.U);d.io.scalar.result.bits.primitiveFlagsValid.poke(true.B)
    d.io.scalar.result.bits.error.poke(false.B)
    d.io.formatRequest.ready.poke(false.B);d.io.formatResult.valid.poke(false.B)
    d.io.formatResult.bits.value.poke(0.U);d.io.formatResult.bits.error.poke(false.B)
  }
  it should "preserve six separate scalar nodes and two format boundaries for every logical element" in {
    test(new UnifiedMoeLogical32SwiGluConsumerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(true.B);d.clock.step();d.io.begin.valid.poke(false.B)
      val ops=Seq(ScalarOp.ExpNegative,ScalarOp.Add,ScalarOp.Div,ScalarOp.MulIeeeRne,ScalarOp.MulIeeeRne,ScalarOp.MulIeeeRne)
      val expectedA=Seq(BigInt("80000000",16),BigInt("3f800000",16),BigInt("3f800000",16),BigInt("3f800000",16),BigInt(0),BigInt(0))
      val expectedB=Seq(BigInt(0),BigInt("3f800000",16),BigInt("40000000",16),BigInt("3f000000",16),BigInt("3f000000",16),BigInt(0))
      val replies=Seq(BigInt("3f800000",16),BigInt("40000000",16),BigInt("3f000000",16),BigInt("3f000000",16),BigInt(0),BigInt(0))
      var pending:Option[(Int,BigInt)]=None;var pendingFormat=false
      var issued=0;var returned=0;var formatted=0;var formatReturned=0;var cycle=0
      while(!d.io.result.valid.peek().litToBoolean && cycle<3000){
        d.io.scalar.request.ready.poke((cycle%3!=0).B)
        d.io.formatRequest.ready.poke((cycle%4!=0).B)
        d.io.scalar.result.valid.poke(pending.nonEmpty.B)
        pending.foreach{case(policy,value)=>d.io.scalar.result.bits.policy.poke(policy.U);d.io.scalar.result.bits.value.poke(value.U)}
        d.io.formatResult.valid.poke(pendingFormat.B)
        val scalarDone=pending.nonEmpty && d.io.scalar.result.ready.peek().litToBoolean
        val formatDone=pendingFormat && d.io.formatResult.ready.peek().litToBoolean
        val scalarFire=d.io.scalar.request.valid.peek().litToBoolean && cycle%3!=0
        val formatFire=d.io.formatRequest.valid.peek().litToBoolean && cycle%4!=0
        var next=pending;var nextFormat=pendingFormat
        if(scalarDone){next=None;returned+=1};if(formatDone){nextFormat=false;formatReturned+=1}
        if(scalarFire){
          next shouldBe None
          val node=issued%6;val policy=if(node==0)1 else 0
          d.io.scalar.request.bits.policy.expect(policy.U);d.io.scalar.request.bits.payload.op.expect(ops(node).U)
          d.io.scalar.request.bits.payload.a.expect(expectedA(node).U);d.io.scalar.request.bits.payload.b.expect(expectedB(node).U)
          // No nextlane is issued until both preceding format returns retired.
          if(node==0)formatReturned shouldBe (issued/6)*2
          if(node==5)formatReturned shouldBe (issued/6)*2+1
          next=Some((policy,replies(node)));issued+=1
        }
        if(formatFire){nextFormat shouldBe false;d.io.formatRequest.bits.value.expect(0.U);nextFormat=true;formatted+=1}
        d.clock.step();pending=next;pendingFormat=nextFormat;cycle+=1
      }
      d.io.scalar.result.valid.poke(false.B);d.io.formatResult.valid.poke(false.B)
      cycle should be < 3000;issued shouldBe 192;returned shouldBe 192;formatted shouldBe 64;formatReturned shouldBe 64
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Ok.U);d.io.result.bits.drained.expect(true.B)
      d.io.result.bits.data.expect(0.U);d.io.result.bits.scalarIssued.expect(192.U);d.io.result.bits.scalarReturned.expect(192.U)
      d.io.result.bits.formatIssued.expect(64.U);d.io.result.bits.formatReturned.expect(64.U)
      d.clock.step(4);d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Ok.U)
      d.io.result.bits.drained.expect(true.B);d.io.result.bits.data.expect(0.U)
      d.io.result.bits.scalarIssued.expect(192.U);d.io.result.bits.scalarReturned.expect(192.U)
      d.io.result.bits.formatIssued.expect(64.U);d.io.result.bits.formatReturned.expect(64.U)
      d.io.result.bits.primitiveFlags.expect(0.U);d.io.result.bits.primitiveFlagResponses.expect(192.U)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.valid.expect(false.B)
    }
  }
  it should "reject unknown raw response before accepting a new logical tile" in {
    test(new UnifiedMoeLogical32SwiGluConsumerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.begin.valid.poke(true.B);d.io.scalar.result.valid.poke(true.B)
      d.io.begin.ready.expect(false.B);d.io.scalar.result.ready.expect(false.B);d.clock.step(3)
      d.io.resetRequired.expect(true.B);d.io.quarantine.expect(true.B)
      d.io.scalar.request.valid.expect(false.B);d.io.result.valid.expect(false.B)
      d.io.scalar.result.valid.poke(false.B);d.clock.step();d.io.begin.ready.expect(false.B)
    }
  }
  it should "quarantine a mismatched policy without retiring its pending scalar credit" in {
    test(new UnifiedMoeLogical32SwiGluConsumerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.begin.valid.poke(true.B);d.clock.step();d.io.begin.valid.poke(false.B)
      d.io.scalar.request.ready.poke(true.B);var cycles=0
      while(!d.io.scalar.request.valid.peek().litToBoolean && cycles<8){d.clock.step();cycles+=1}
      cycles should be < 8;d.io.scalar.request.bits.policy.expect(1.U);d.clock.step()
      d.io.scalar.result.valid.poke(true.B);d.io.scalar.result.bits.policy.poke(0.U)
      d.io.scalar.result.bits.value.poke("h3f800000".U);d.io.scalar.result.ready.expect(true.B);d.clock.step()
      d.io.scalar.result.valid.poke(false.B)
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Protocol.U)
      d.io.result.bits.drained.expect(false.B);d.io.result.bits.data.expect(0.U)
      d.io.result.bits.scalarIssued.expect(1.U);d.io.result.bits.scalarReturned.expect(0.U)
      d.io.result.bits.primitiveFlagResponses.expect(0.U);d.io.quarantine.expect(true.B)
      d.io.result.bits.formatIssued.expect(0.U);d.io.resetRequired.expect(true.B)
      d.clock.step(4);d.io.result.valid.expect(true.B);d.io.result.bits.drained.expect(false.B)
      d.io.result.bits.scalarReturned.expect(0.U);d.io.result.bits.status.expect(Status.Protocol.U)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.valid.expect(false.B)
      d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(false.B);d.io.quarantine.expect(true.B)
    }
  }
  it should "retire a current-policy arithmetic error without treating it as an identity mismatch" in {
    test(new UnifiedMoeLogical32SwiGluConsumerV3).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.begin.valid.poke(true.B);d.clock.step();d.io.begin.valid.poke(false.B)
      d.io.scalar.request.ready.poke(true.B);var cycles=0
      while(!d.io.scalar.request.valid.peek().litToBoolean && cycles<8){d.clock.step();cycles+=1}
      cycles should be < 8;d.io.scalar.request.bits.policy.expect(1.U);d.clock.step()
      d.io.scalar.result.valid.poke(true.B);d.io.scalar.result.bits.policy.poke(1.U)
      d.io.scalar.result.bits.value.poke(0.U);d.io.scalar.result.bits.error.poke(true.B)
      d.io.scalar.result.bits.primitiveFlagsValid.poke(false.B)
      d.io.scalar.result.ready.expect(true.B);d.clock.step();d.io.scalar.result.valid.poke(false.B)
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Numerical.U)
      d.io.result.bits.drained.expect(true.B);d.io.result.bits.data.expect(0.U)
      d.io.result.bits.scalarIssued.expect(1.U);d.io.result.bits.scalarReturned.expect(1.U)
      d.io.result.bits.primitiveFlagResponses.expect(0.U);d.io.quarantine.expect(false.B)
      d.io.result.bits.formatIssued.expect(0.U);d.io.resetRequired.expect(true.B)
    }
  }
}
