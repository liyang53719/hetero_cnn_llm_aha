package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import UnifiedMoeV2TestData._

class UnifiedMoeProducerBindingV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "actual private MoE producer drained origin"
  def init(d:UnifiedMoeProducerBindingV2):Unit={
    d.clock.setTimeout(2000)
    d.io.start.valid.poke(false.B);lease(d.io.start.bits,10)
    d.io.route.valid.poke(false.B);route(d.io.route.bits,10,0)
    d.io.dispatch.ready.poke(false.B);d.io.returned.valid.poke(false.B);returned(d.io.returned.bits,10,0)
    d.io.contribution.ready.poke(false.B);d.io.drained.ready.poke(false.B)
  }
  def start(d:UnifiedMoeProducerBindingV2,txn:Long,profile:Int=3):Unit={
    lease(d.io.start.bits,txn,profile);d.io.start.valid.poke(true.B);d.io.start.ready.expect(true.B)
    d.clock.step();d.io.start.valid.poke(false.B);lease(d.io.start.bits,999,4,127,63)
  }
  def load(d:UnifiedMoeProducerBindingV2,txn:Long,experts:Vector[Int]=expertLoad):Unit={
    for(e<-experts){route(d.io.route.bits,txn,e);d.io.route.valid.poke(true.B);d.io.route.ready.expect(true.B);d.clock.step()}
    d.io.route.valid.poke(false.B)
  }
  def dispatch(d:UnifiedMoeProducerBindingV2,txn:Long):Unit={
    d.io.dispatch.ready.poke(true.B)
    for(i<-0 until 9){
      d.io.dispatch.valid.expect(true.B);d.io.dispatch.bits.identity.transactionId.expect(txn.U)
      d.io.dispatch.bits.payload.routeTag.expect(i.U);d.io.dispatch.bits.payload.expert.expect(expertLoad(i).U)
      d.clock.step()
    }
    d.io.dispatch.ready.poke(false.B)
  }
  def returns(d:UnifiedMoeProducerBindingV2,txn:Long,tags:Seq[Int]):Unit={
    for(t<-tags){returned(d.io.returned.bits,txn,t,BigInt(t+1));d.io.returned.valid.poke(true.B);d.io.returned.ready.expect(true.B);d.clock.step()}
    d.io.returned.valid.poke(false.B)
  }
  def waitReceipt(d:UnifiedMoeProducerBindingV2):Unit={
    var cycles=0
    while(!d.io.drained.valid.peek().litToBoolean && cycles<30){d.clock.step();cycles+=1}
    d.io.drained.valid.expect(true.B)
  }
  it should "derive success only after all nine real contribution fires and exact shared-last order on both profiles" in {
    test(new UnifiedMoeProducerBindingV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((txn,profile)<-Vector((10L,3),(11L,4))){
        start(d,txn,profile);load(d,txn);dispatch(d,txn);returns(d,txn,(0 until 9).reverse)
        for((tag,index)<-mergeTags.zipWithIndex){
          var n=0
          while(!d.io.contribution.valid.peek().litToBoolean && n<20){d.clock.step();n+=1}
          d.io.contribution.valid.expect(true.B);d.io.drained.valid.expect(false.B)
          d.io.contribution.bits.identity.transactionId.expect(txn.U);d.io.contribution.bits.routeTag.expect(tag.U)
          d.io.contribution.bits.data.expect((tag+1).U)
          d.io.contribution.bits.first.expect((index==0).B);d.io.contribution.bits.last.expect((index==8).B)
          d.clock.step(3);d.io.contribution.bits.routeTag.expect(tag.U);d.io.drained.valid.expect(false.B)
          d.io.contribution.ready.poke(true.B);d.clock.step();d.io.contribution.ready.poke(false.B)
        }
        waitReceipt(d);d.io.observedContributions.expect(9.U)
        d.io.drained.bits.identity.transactionId.expect(txn.U);d.io.drained.bits.status.expect(Status.Ok.U)
        d.io.drained.bits.drained.expect(true.B);d.clock.step(3);d.io.drained.bits.status.expect(Status.Ok.U)
        d.io.drained.ready.poke(true.B);d.clock.step();d.io.drained.ready.poke(false.B)
        d.io.resetRequired.expect(false.B)
      }
    }
  }
  it should "reject missing shared without dispatch and never synthesize completion for only eight loaded routes" in {
    test(new UnifiedMoeProducerBindingV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);start(d,20);load(d,20,(0 until 8).toVector)
      d.clock.step(20);d.io.dispatch.valid.expect(false.B);d.io.drained.valid.expect(false.B)
      load(d,20,Vector(8));waitReceipt(d)
      d.io.dispatch.valid.expect(false.B);d.io.observedContributions.expect(0.U)
      d.io.drained.bits.status.expect(Status.Protocol.U);d.io.drained.bits.drained.expect(true.B)
    }
  }
  it should "not retire a bad or stale reply and wait for all nine genuine current replies before error drain" in {
    test(new UnifiedMoeProducerBindingV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);start(d,30);load(d,30);dispatch(d,30)
      // Old epoch is dropped before the legacy routeTag-only cache.
      returned(d.io.returned.bits,29,0);d.io.returned.valid.poke(true.B)
      d.io.returned.ready.expect(true.B);d.io.faultEvent.expect(true.B);d.clock.step();d.io.returned.valid.poke(false.B)
      // Current but out-of-range tag is rejected by the actual order controller.
      returns(d,30,Seq(15));returns(d,30,0 until 8)
      d.clock.step(20);d.io.drained.valid.expect(false.B);d.io.contribution.valid.expect(false.B)
      returns(d,30,Seq(8));waitReceipt(d)
      d.io.drained.bits.status.expect(Status.Protocol.U);d.io.drained.bits.drained.expect(true.B)
      d.io.observedContributions.expect(0.U);d.io.resetRequired.expect(true.B)
      d.clock.step(3);d.io.drained.bits.status.expect(Status.Protocol.U)
    }
  }
}
