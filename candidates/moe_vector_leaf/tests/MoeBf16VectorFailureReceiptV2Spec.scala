package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Consumer receipt/control test with explicit error-response injection.
  * Not a numeric result model and not proof of actual producer-fence origin. */
class MoeBf16VectorFailureReceiptV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "vector consumer identity-bound safe failure receipt"
  private def id(x:MoeBf16TileIdentity,txn:Int):Unit={x.transactionId.poke(txn.U);x.token.poke(0.U);x.tileOrdinal.poke(0.U)}
  it should "drop bad receipts without current credit and never abort a held or pending bank operation" in {
    test(new MoeBf16VectorConsumerV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.clock.setTimeout(2000);d.io.job.valid.poke(false.B);id(d.io.job.bits.identity,10);d.io.job.bits.contributionCount.poke(9.U)
      d.io.contribution.valid.poke(false.B);id(d.io.contribution.bits.identity,10)
      d.io.contribution.bits.routeTag.poke(0.U);d.io.contribution.bits.weight.poke("h3f80".U);d.io.contribution.bits.data.poke(0.U)
      d.io.contribution.bits.first.poke(true.B);d.io.contribution.bits.last.poke(false.B)
      d.io.result.ready.poke(false.B);d.io.vectorRequest.ready.poke(false.B)
      d.io.vectorResult.valid.poke(false.B);d.io.vectorResult.bits.policy.poke(1.U);d.io.vectorResult.bits.error.poke(true.B)
      for(i<-0 until 16){d.io.vectorResult.bits.value(i).poke(0.U);d.io.vectorResult.bits.flags(i).poke(0.U)}
      d.io.sourceFailure.valid.poke(false.B);id(d.io.sourceFailure.bits.identity,10)
      d.io.sourceFailure.bits.status.poke(Status.Protocol.U);d.io.sourceFailure.bits.drained.poke(true.B)
      d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
      for((txn,status,drained)<-Vector((9,Status.Protocol,true),(10,Status.Protocol,false),(10,Status.Ok,true),(10,255,true))){
        id(d.io.sourceFailure.bits.identity,txn);d.io.sourceFailure.bits.status.poke(status.U);d.io.sourceFailure.bits.drained.poke(drained.B)
        d.io.sourceFailure.valid.poke(true.B);d.io.sourceFailure.ready.expect(true.B);d.io.rejectedFailure.expect(true.B)
        d.clock.step();d.io.result.valid.expect(false.B);d.io.contribution.ready.expect(true.B)
      }
      id(d.io.sourceFailure.bits.identity,10);d.io.sourceFailure.bits.status.poke(Status.Protocol.U);d.io.sourceFailure.bits.drained.poke(true.B)
      // Competing legitimate contribution wins; a valid failure cannot eat it.
      d.io.contribution.valid.poke(true.B);d.io.sourceFailure.ready.expect(false.B);d.clock.step();d.io.contribution.valid.poke(false.B)
      d.io.vectorRequest.valid.expect(true.B);d.io.sourceFailure.ready.expect(false.B)
      d.clock.step(3);d.io.vectorRequest.valid.expect(true.B);d.io.vectorRequest.bits.policy.expect(1.U)
      d.io.vectorRequest.ready.poke(true.B);d.clock.step();d.io.vectorRequest.ready.poke(false.B)
      d.io.sourceFailure.ready.expect(false.B);d.io.result.valid.expect(false.B)
      d.io.vectorResult.valid.poke(true.B);d.io.vectorResult.ready.expect(true.B);d.clock.step();d.io.vectorResult.valid.poke(false.B)
      // Only after the real accepted operation has returned is the consumer in
      // Drain, where the authenticated private failure may end remaining wait.
      d.io.sourceFailure.ready.expect(true.B);d.clock.step();d.io.sourceFailure.valid.poke(false.B)
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Numerical.U);d.io.result.bits.data.expect(0.U)
      d.clock.step(3);d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Numerical.U)
    }
  }
}
