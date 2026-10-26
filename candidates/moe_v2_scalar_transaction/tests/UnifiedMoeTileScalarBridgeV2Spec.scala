package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import UnifiedMoeV2TestData._

/** Bridge-only handshake tests use private mock peers. The actual producer
  * origin is separately tested by UnifiedMoeProducerBindingV2Spec and the
  * connected client tests; these stimuli are not a public host-drain port. */
class UnifiedMoeTileScalarBridgeV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "immutable owner and release offers with independent fault sideband"
  def init(d:UnifiedMoeTileScalarBridgeV2):Unit={
    d.clock.setTimeout(1000)
    d.io.begin.valid.poke(false.B);lease(d.io.begin.bits,10);d.io.externalProtocolFault.poke(false.B)
    d.io.ownerAcquire.ready.poke(false.B);d.io.releaseIntent.ready.poke(false.B)
    d.io.releaseAck.valid.poke(false.B);id(d.io.releaseAck.bits.identity,10)
    d.io.releaseAck.bits.status.poke(0.U);d.io.releaseAck.bits.drained.poke(false.B);d.io.releaseAck.bits.resetRequired.poke(false.B)
    d.io.producerReady.poke(true.B);d.io.contribution.valid.poke(false.B)
    id(d.io.contribution.bits.identity,10);d.io.contribution.bits.routeTag.poke(0.U)
    d.io.contribution.bits.weight.poke(0.U);d.io.contribution.bits.data.poke(0.U)
    d.io.contribution.bits.first.poke(false.B);d.io.contribution.bits.last.poke(false.B)
    d.io.producerDrained.valid.poke(false.B);id(d.io.producerDrained.bits.identity,10)
    d.io.producerDrained.bits.status.poke(0.U);d.io.producerDrained.bits.drained.poke(false.B)
    d.io.scalarRequest.ready.poke(true.B);d.io.scalarResult.valid.poke(false.B)
    id(d.io.scalarResult.bits.tag.tile,10);d.io.scalarResult.bits.tag.operationSerial.poke(0.U);scalar(d.io.scalarResult.bits.payload)
    d.io.result.ready.poke(false.B)
  }
  def waitIntent(d:UnifiedMoeTileScalarBridgeV2):Unit={
    var n=0;while(!d.io.releaseIntent.valid.peek().litToBoolean && n<20){d.clock.step();n+=1}
    d.io.releaseIntent.valid.expect(true.B)
  }
  def ack(d:UnifiedMoeTileScalarBridgeV2,status:Int,reset:Boolean):Unit={
    id(d.io.releaseAck.bits.identity,10);d.io.releaseAck.bits.status.poke(status.U)
    d.io.releaseAck.bits.drained.poke(true.B);d.io.releaseAck.bits.resetRequired.poke(reset.B)
    d.io.releaseAck.valid.poke(true.B);d.io.releaseAck.ready.expect(true.B)
    d.clock.step();d.io.releaseAck.valid.poke(false.B)
  }
  it should "not withdraw an acquisition after a late fault and return only the provably unstarted empty owner" in {
    test(new UnifiedMoeTileScalarBridgeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(true.B);d.clock.step();d.io.begin.valid.poke(false.B)
      d.io.ownerAcquire.valid.expect(true.B);d.io.ownerAcquire.bits.identity.transactionId.expect(10.U)
      d.io.externalProtocolFault.poke(true.B);d.clock.step(4)
      d.io.ownerAcquire.valid.expect(true.B);d.io.ownerAcquire.bits.identity.transactionId.expect(10.U)
      d.io.producerStart.expect(false.B);d.io.scalarRequest.valid.expect(false.B)
      d.io.ownerAcquire.ready.poke(true.B);d.clock.step();d.io.ownerAcquire.ready.poke(false.B)
      waitIntent(d);d.io.producerStart.expect(false.B)
      d.io.releaseIntent.bits.status.expect(Status.Protocol.U);d.io.releaseIntent.bits.issuedOperations.expect(0.U)
      d.io.releaseIntent.bits.completedOperations.expect(0.U);d.io.releaseIntent.bits.drained.expect(true.B)
      d.clock.step(4);d.io.releaseIntent.valid.expect(true.B);d.io.releaseIntent.bits.status.expect(Status.Protocol.U)
      d.io.releaseIntent.ready.poke(true.B);d.clock.step();d.io.releaseIntent.ready.poke(false.B)
      ack(d,Status.Protocol,true);d.io.result.valid.expect(true.B)
      d.io.result.bits.status.expect(Status.Protocol.U);d.io.result.bits.data.expect(0.U)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      d.io.begin.ready.expect(false.B);d.io.resetRequired.expect(true.B)
    }
  }
  it should "freeze the diagnostic intent while fault changes and require a matching drained registered acknowledgment" in {
    test(new UnifiedMoeTileScalarBridgeV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);d.io.ownerAcquire.ready.poke(true.B);d.io.begin.valid.poke(true.B)
      d.clock.step();d.io.begin.valid.poke(false.B);d.clock.step(2)
      for(i<-0 until 9){
        d.io.contribution.valid.poke(true.B);d.io.contribution.bits.routeTag.poke(i.U)
        d.io.contribution.bits.weight.poke((if(i==0)BigInt("3f800000",16) else BigInt(0)).U)
        d.io.contribution.bits.first.poke((i==0).B);d.io.contribution.bits.last.poke((i==8).B)
        d.io.contribution.ready.expect(true.B);d.io.scalarRequest.valid.expect(false.B);d.clock.step()
      }
      d.io.contribution.valid.poke(false.B)
      d.io.producerDrained.valid.poke(true.B);d.io.producerDrained.bits.drained.poke(true.B)
      d.io.producerDrained.ready.expect(true.B);d.clock.step();d.io.producerDrained.valid.poke(false.B)
      waitIntent(d);d.io.releaseIntent.bits.status.expect(Status.Numerical.U)
      d.io.externalProtocolFault.poke(true.B);d.clock.step(4)
      d.io.releaseIntent.valid.expect(true.B);d.io.releaseIntent.bits.status.expect(Status.Numerical.U)
      d.io.releaseIntent.bits.identity.transactionId.expect(10.U);d.io.ownerFault.valid.expect(true.B)
      d.io.releaseIntent.ready.poke(true.B);d.clock.step();d.io.releaseIntent.ready.poke(false.B)
      id(d.io.releaseAck.bits.identity,9);d.io.releaseAck.bits.drained.poke(true.B);d.io.releaseAck.valid.poke(true.B)
      d.clock.step();d.io.result.valid.expect(false.B)
      id(d.io.releaseAck.bits.identity,10);d.io.releaseAck.bits.drained.poke(false.B)
      d.clock.step();d.io.result.valid.expect(false.B);d.io.releaseAck.valid.poke(false.B)
      ack(d,Status.Protocol,true);d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Protocol.U)
      d.clock.step(4);d.io.result.bits.status.expect(Status.Protocol.U);d.io.result.bits.data.expect(0.U)
    }
  }
}
