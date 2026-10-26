package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import UnifiedMoeV2TestData._

/** These are controller/wiring tests. The primitive result port is an explicit
  * MOCK, not a new ALU, numerical oracle, or complete4096 hardware substitute.
  * Numeric qualification must reconnect the actual shared primitive later. */
class UnifiedMoeSharedScalarClientV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "real producer consumer owner wiring with external scalar port"
  def init(d:UnifiedMoeSharedScalarClientV2):Unit={
    d.clock.setTimeout(20000)
    d.io.begin.valid.poke(false.B);lease(d.io.begin.bits,10)
    d.io.route.valid.poke(false.B);route(d.io.route.bits,10,0)
    d.io.dispatch.ready.poke(false.B);d.io.returned.valid.poke(false.B);returned(d.io.returned.bits,10,0)
    d.io.result.ready.poke(false.B);d.io.primitiveRequest.ready.poke(true.B)
    d.io.primitiveResult.valid.poke(false.B);scalar(d.io.primitiveResult.bits)
  }
  def begin(d:UnifiedMoeSharedScalarClientV2,txn:Long,profile:Int=3):Unit={
    lease(d.io.begin.bits,txn,profile);d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(true.B)
    d.clock.step();d.io.begin.valid.poke(false.B);lease(d.io.begin.bits,999,4,127,63)
    var n=0
    // Route readiness becomes true only after real owner grant and atomic child start.
    route(d.io.route.bits,txn,256)
    while(!d.io.route.ready.peek().litToBoolean && n<20){d.clock.step();n+=1}
  }
  def routeAndDispatch(d:UnifiedMoeSharedScalarClientV2,txn:Long,badWeight:Boolean):Unit={
    for(e<-expertLoad){
      route(d.io.route.bits,txn,e,if(badWeight && e==0)BigInt("3f800000",16) else BigInt(0))
      d.io.route.valid.poke(true.B)
      var n=0;while(!d.io.route.ready.peek().litToBoolean && n<20){d.clock.step();n+=1}
      d.io.route.ready.expect(true.B);d.clock.step()
    }
    d.io.route.valid.poke(false.B);d.io.dispatch.ready.poke(true.B)
    for(i<-0 until 9){
      d.io.dispatch.valid.expect(true.B);d.io.dispatch.bits.payload.routeTag.expect(i.U)
      d.io.dispatch.bits.identity.transactionId.expect(txn.U);d.clock.step()
    }
    d.io.dispatch.ready.poke(false.B)
  }
  def returns(d:UnifiedMoeSharedScalarClientV2,txn:Long,tags:Seq[Int]):Unit={
    for(t<-tags){returned(d.io.returned.bits,txn,t);d.io.returned.valid.poke(true.B);d.io.returned.ready.expect(true.B);d.clock.step()}
    d.io.returned.valid.poke(false.B)
  }
  it should "propagate canonical weight failure through actual nine-contribution drain and real zero-operation owner fence" in {
    test(new UnifiedMoeSharedScalarClientV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((txn,profile)<-Vector((10L,3),(11L,4))){
        begin(d,txn,profile);routeAndDispatch(d,txn,badWeight=true);returns(d,txn,(0 until 9).reverse)
        var n=0
        while(!d.io.result.valid.peek().litToBoolean && n<300){d.io.primitiveRequest.valid.expect(false.B);d.clock.step();n+=1}
        d.io.result.valid.expect(true.B);d.io.result.bits.identity.transactionId.expect(txn.U)
        d.io.result.bits.status.expect(Status.Numerical.U);d.io.result.bits.data.expect(0.U)
        d.io.issuedOperations.expect(0.U);d.io.completedOperations.expect(0.U);d.io.resetRequired.expect(false.B)
        d.clock.step(4);d.io.result.bits.status.expect(Status.Numerical.U)
        if(txn==11L){
          // Fault after commit must not rewrite this already-held tile result.
          returned(d.io.returned.bits,10,0);d.io.returned.valid.poke(true.B);d.io.returned.ready.expect(true.B)
          d.clock.step(2);d.io.returned.valid.poke(false.B);d.io.resetRequired.expect(true.B)
          d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Numerical.U);d.io.result.bits.data.expect(0.U)
        }
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
      d.io.resetRequired.expect(true.B)
      lease(d.io.begin.bits,12);d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(false.B)
    }
  }
  it should "wait for real current expert replies and 576 mocked service completions before a poisoned error fence" in {
    test(new UnifiedMoeSharedScalarClientV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d,20);routeAndDispatch(d,20,badWeight=false)
      // Wrong full identity cannot be counted as a valid current expert result.
      returns(d,19,Seq(0));returns(d,20,0 until 8)
      d.clock.step(30);d.io.result.valid.expect(false.B);d.io.primitiveRequest.valid.expect(false.B)
      returns(d,20,Seq(8))
      var pendingDelay = -1;var requests=0;var responses=0;var cycles=0
      while(!d.io.result.valid.peek().litToBoolean && cycles<10000){
        d.io.primitiveRequest.ready.poke((cycles%7!=0).B)
        d.io.primitiveResult.valid.poke((pendingDelay==0).B);scalar(d.io.primitiveResult.bits,BigInt(0))
        val req=d.io.primitiveRequest.valid.peek().litToBoolean && d.io.primitiveRequest.ready.peek().litToBoolean
        val rsp=d.io.primitiveResult.valid.peek().litToBoolean && d.io.primitiveResult.ready.peek().litToBoolean
        if(req){pendingDelay shouldBe -1;requests+=1;pendingDelay=3}
        if(rsp){responses+=1;pendingDelay = -1}
        else if(pendingDelay>0){pendingDelay-=1}
        d.clock.step();cycles+=1
      }
      d.io.primitiveResult.valid.poke(false.B)
      d.io.result.valid.expect(true.B);requests shouldBe 576;responses shouldBe 576
      d.io.issuedOperations.expect(576.U);d.io.completedOperations.expect(576.U)
      d.io.result.bits.identity.transactionId.expect(20.U);d.io.result.bits.status.expect(Status.Protocol.U)
      d.io.result.bits.data.expect(0.U);d.io.resetRequired.expect(true.B)
      d.clock.step(4);d.io.result.bits.status.expect(Status.Protocol.U)
    }
  }
  it should "reject token and final hidden tile boundaries before acquiring or launching any primitive work" in {
    test(new UnifiedMoeSharedScalarClientV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((token,tile)<-Vector((128,0),(0,64))){
        lease(d.io.begin.bits,30,3,token,tile);d.io.begin.valid.poke(true.B);d.io.begin.ready.expect(true.B)
        d.clock.step();d.io.begin.valid.poke(false.B)
        d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Malformed.U)
        d.io.dispatch.valid.expect(false.B);d.io.primitiveRequest.valid.expect(false.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      }
    }
  }
}
