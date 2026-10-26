package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import UnifiedMoeV2TestData._

class UnifiedScalarOwnerArbiterV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "single physical scalar owner arbiter V2 control"
  def init(d:UnifiedScalarOwnerArbiterV2):Unit={
    d.clock.setTimeout(2000)
    d.io.ownerAcquire.valid.poke(false.B);lease(d.io.ownerAcquire.bits,10)
    d.io.request.valid.poke(false.B);op(d.io.request.bits,10,0)
    d.io.result.ready.poke(false.B);d.io.releaseIntent.valid.poke(false.B);intent(d.io.releaseIntent.bits,10,0)
    d.io.releaseAck.ready.poke(false.B);d.io.ownerFault.valid.poke(false.B);id(d.io.ownerFault.bits,10)
    d.io.externalPoison.poke(false.B);d.io.primitiveRequest.ready.poke(true.B)
    d.io.primitiveResult.valid.poke(false.B);scalar(d.io.primitiveResult.bits)
  }
  def acquire(d:UnifiedScalarOwnerArbiterV2,txn:Long,profile:Int=3,tile:Int=0):Unit={
    lease(d.io.ownerAcquire.bits,txn,profile,tile=tile);d.io.ownerAcquire.valid.poke(true.B)
    d.io.ownerAcquire.ready.expect(true.B);d.clock.step();d.io.ownerAcquire.valid.poke(false.B)
    // Live acquire fields cannot retarget a pending owner.
    lease(d.io.ownerAcquire.bits,999,4,127,63)
  }
  def operation(d:UnifiedScalarOwnerArbiterV2,txn:Long,serial:Int,tile:Int=0):Unit={
    op(d.io.request.bits,txn,serial,tile=tile);d.io.request.valid.poke(true.B)
    d.io.primitiveRequest.ready.poke(false.B)
    d.io.request.ready.expect(true.B);d.io.primitiveRequest.valid.expect(false.B)
    d.clock.step();d.io.request.valid.poke(false.B)
    d.io.primitiveRequest.valid.expect(true.B);d.io.request.ready.expect(false.B)
    d.clock.step(3);d.io.primitiveRequest.bits.a.expect("h3f800000".U)
    d.io.primitiveRequest.ready.poke(true.B);d.io.primitiveRequest.valid.expect(true.B)
    d.clock.step()
    d.io.releaseIntent.ready.expect(false.B);d.clock.step(2)
    scalar(d.io.primitiveResult.bits,BigInt(serial+1));d.io.primitiveResult.valid.poke(true.B)
    d.io.primitiveResult.ready.expect(true.B);d.clock.step();d.io.primitiveResult.valid.poke(false.B)
    d.io.result.valid.expect(true.B);d.io.result.bits.tag.tile.transactionId.expect(txn.U)
    d.io.result.bits.tag.tile.tileOrdinal.expect(tile.U);d.io.result.bits.tag.operationSerial.expect(serial.U)
    d.io.result.bits.payload.value.expect((serial+1).U)
    d.clock.step(4);d.io.result.bits.payload.value.expect((serial+1).U)
    d.io.releaseIntent.ready.expect(false.B)
    d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
  }
  def release(d:UnifiedScalarOwnerArbiterV2,txn:Long,count:Int,tile:Int=0,status:Int=0,reset:Boolean=false):Unit={
    intent(d.io.releaseIntent.bits,txn,count,tile=tile);d.io.releaseIntent.valid.poke(true.B)
    d.io.releaseIntent.ready.expect(true.B);d.io.releaseAck.valid.expect(false.B)
    d.clock.step();d.io.releaseIntent.valid.poke(false.B)
    d.io.releaseAck.valid.expect(true.B);d.io.releaseAck.bits.identity.transactionId.expect(txn.U)
    d.io.releaseAck.bits.status.expect(status.U);d.io.releaseAck.bits.drained.expect(true.B)
    d.io.releaseAck.bits.resetRequired.expect(reset.B)
    d.clock.step(4);d.io.releaseAck.bits.status.expect(status.U)
    d.io.releaseAck.ready.poke(true.B);d.clock.step();d.io.releaseAck.ready.poke(false.B)
  }
  it should "retain each owner across multiple primitive operations and both runtime MoE profiles without reset" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,10,3);operation(d,10,0);operation(d,10,1)
      d.io.issuedOperations.expect(2.U);d.io.completedOperations.expect(2.U);release(d,10,2)
      acquire(d,11,4,63);operation(d,11,0,63);release(d,11,1,63)
      d.io.resetRequired.expect(false.B)
    }
  }
  it should "keep registered held acknowledgments unchanged when poison arrives after commit" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,20);intent(d.io.releaseIntent.bits,20,0)
      d.io.releaseIntent.valid.poke(true.B);d.io.releaseIntent.ready.expect(true.B)
      d.clock.step();d.io.releaseIntent.valid.poke(false.B);d.io.releaseAck.valid.expect(true.B)
      d.io.releaseAck.bits.status.expect(0.U);d.io.releaseAck.bits.resetRequired.expect(false.B)
      d.io.externalPoison.poke(true.B);d.io.resetRequired.expect(true.B);d.clock.step(5)
      d.io.releaseAck.valid.expect(true.B);d.io.releaseAck.bits.status.expect(0.U)
      d.io.releaseAck.bits.resetRequired.expect(false.B)
      d.io.releaseAck.ready.poke(true.B);d.clock.step();d.io.releaseAck.ready.poke(false.B)
      d.io.externalPoison.poke(false.B);lease(d.io.ownerAcquire.bits,21)
      d.io.ownerAcquire.valid.poke(true.B);d.io.ownerAcquire.ready.expect(false.B)
    }
  }
  it should "not spend pending credit on a duplicate serial and release only after the genuine primitive result" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,30);op(d.io.request.bits,30,0);d.io.request.valid.poke(true.B)
      d.io.request.ready.expect(true.B);d.clock.step();d.io.request.valid.poke(false.B)
      d.io.primitiveRequest.valid.expect(true.B);d.clock.step()
      op(d.io.request.bits,30,0);d.io.request.valid.poke(true.B)
      d.io.request.ready.expect(false.B);d.io.primitiveRequest.valid.expect(false.B);d.io.resetRequired.expect(true.B)
      d.clock.step();d.io.request.valid.poke(false.B);d.io.issuedOperations.expect(1.U);d.io.completedOperations.expect(0.U)
      intent(d.io.releaseIntent.bits,30,1);d.io.releaseIntent.ready.expect(false.B)
      scalar(d.io.primitiveResult.bits,3);d.io.primitiveResult.valid.poke(true.B);d.clock.step();d.io.primitiveResult.valid.poke(false.B)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      release(d,30,1,status=Status.Protocol,reset=true)
    }
  }
  it should "reject unknown untagged primitive data instead of relabeling it as a new owner response" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.primitiveResult.valid.poke(true.B);scalar(d.io.primitiveResult.bits,9)
      d.io.primitiveResult.ready.expect(false.B);d.io.result.valid.expect(false.B);d.io.resetRequired.expect(true.B)
      d.io.ownerAcquire.valid.poke(true.B);d.io.ownerAcquire.ready.expect(false.B);d.clock.step(5)
      d.io.result.valid.expect(false.B);d.io.releaseAck.valid.expect(false.B)
    }
  }
  it should "reject reuse and state the current lexicographic qualification constraint explicitly" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,40,3,0);release(d,40,0,0)
      acquire(d,40,3,1);release(d,40,0,1)
      lease(d.io.ownerAcquire.bits,40,3,tile=0);d.io.ownerAcquire.valid.poke(true.B)
      d.io.ownerAcquire.ready.expect(false.B);d.io.resetRequired.expect(true.B)
      d.io.primitiveRequest.valid.expect(false.B);d.clock.step()
    }
  }
  it should "block a fresh request when unknown primitive data is already valid on the same acceptance edge" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,50);op(d.io.request.bits,50,0);d.io.request.valid.poke(true.B)
      scalar(d.io.primitiveResult.bits,BigInt(99));d.io.primitiveResult.valid.poke(true.B)
      d.io.request.ready.expect(false.B);d.io.primitiveRequest.valid.expect(false.B)
      d.io.primitiveResult.ready.expect(false.B);d.io.responseQuarantined.expect(true.B)
      d.clock.step(6)
      d.io.issuedOperations.expect(0.U);d.io.completedOperations.expect(0.U)
      d.io.result.valid.expect(false.B);d.io.releaseAck.valid.expect(false.B)
      intent(d.io.releaseIntent.bits,50,0);d.io.releaseIntent.valid.poke(true.B)
      d.io.releaseIntent.ready.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }
  it should "preserve an already held offer across a conflicting intent and quarantine unknown data on its physical fire edge" in {
    test(new UnifiedScalarOwnerArbiterV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);acquire(d,60);d.io.primitiveRequest.ready.poke(false.B)
      op(d.io.request.bits,60,0);d.io.request.valid.poke(true.B);d.io.request.ready.expect(true.B)
      d.clock.step();d.io.request.valid.poke(false.B)
      d.io.primitiveRequest.valid.expect(true.B);d.io.primitiveRequest.bits.a.expect("h3f800000".U)
      intent(d.io.releaseIntent.bits,60,0);d.io.releaseIntent.valid.poke(true.B)
      d.io.releaseIntent.ready.expect(false.B);d.clock.step(4)
      d.io.primitiveRequest.valid.expect(true.B);d.io.primitiveRequest.bits.a.expect("h3f800000".U)
      d.io.primitiveRequest.bits.op.expect(ScalarOp.Add.U);d.io.primitiveRequest.bits.b.expect(0.U)
      d.io.issuedOperations.expect(0.U)
      scalar(d.io.primitiveResult.bits,BigInt(123));d.io.primitiveResult.valid.poke(true.B)
      d.io.primitiveRequest.ready.poke(true.B)
      d.io.primitiveRequest.valid.expect(true.B);d.io.primitiveResult.ready.expect(false.B)
      d.clock.step() // The irrevocable request fires; the unknown response does NOT.
      d.io.issuedOperations.expect(1.U);d.io.completedOperations.expect(0.U)
      d.io.responseQuarantined.expect(true.B);d.io.primitiveResult.ready.expect(false.B)
      d.clock.step(6)
      d.io.result.valid.expect(false.B);d.io.completedOperations.expect(0.U)
      d.io.releaseIntent.ready.expect(false.B);d.io.releaseAck.valid.expect(false.B)
      d.io.primitiveResult.valid.poke(false.B);d.io.releaseIntent.valid.poke(false.B)
      d.clock.step(3);d.io.responseQuarantined.expect(true.B)
      // Unknown valid dropping is not isolation/reset. A later payload also
      // cannot be used to retire the now-uncorrelatable genuine request.
      scalar(d.io.primitiveResult.bits,BigInt(456));d.io.primitiveResult.valid.poke(true.B)
      d.io.primitiveResult.ready.expect(false.B);d.clock.step(3)
      d.io.completedOperations.expect(0.U);d.io.result.valid.expect(false.B)
      d.io.releaseAck.valid.expect(false.B)
    }
  }

}
