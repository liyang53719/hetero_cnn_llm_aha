package gemmini
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Fixed physical control-only DUT. Data are opaque 512-bit payloads, not FP hardware. */
class HeteroRuntimeMoeMergeSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "fixed runtime MoE contribution order"
  private case class Route(expert:Int, shared:Boolean=false)
  private val routed=Vector(0,2,1,7,4,6,3,5).map(Route(_))
  private val withShared=Vector(Route(256,true))++routed // shared intentionally arrives first
  private def init(d:HeteroRuntimeMoeMerge):Unit={
    d.clock.setTimeout(10000);d.io.clear.poke(true.B);d.io.start.poke(false.B)
    d.io.token.poke(0.U);d.io.routeCount.poke(0.U);d.io.expertCount.poke(256.U);d.io.mergeByExpert.poke(false.B)
    d.io.routeIn.valid.poke(false.B);d.io.routeIn.bits.expert.poke(0.U);d.io.routeIn.bits.weight.poke(0.U);d.io.routeIn.bits.shared.poke(false.B)
    d.io.dispatchOut.ready.poke(false.B);d.io.resultIn.valid.poke(false.B);d.io.resultIn.bits.routeTag.poke(0.U);d.io.resultIn.bits.data.poke(0.U)
    d.io.mergeOut.ready.poke(false.B);d.clock.step();d.io.clear.poke(false.B)
  }
  private def weight(i:Int)=BigInt("3e000000",16)+i
  private def payload(token:Int,i:Int)=(BigInt(token)<<480)|(BigInt(i)<<256)|(BigInt(1)<<255)|BigInt(0x100+i)
  private def start(d:HeteroRuntimeMoeMerge,token:Int,count:Int,mode:Boolean):Unit={
    d.io.startReady.expect(true.B);d.io.start.poke(true.B);d.io.token.poke(token.U)
    d.io.routeCount.poke(count.U);d.io.mergeByExpert.poke(mode.B);d.io.expertCount.poke(256.U)
    d.io.invalidConfig.expect(false.B);d.clock.step();d.io.start.poke(false.B)
    // All live config pins are deliberately invalid / different after admission.
    d.io.token.poke(0xffffffffL.U);d.io.routeCount.poke(0.U);d.io.mergeByExpert.poke((!mode).B);d.io.expertCount.poke(0.U)
  }
  private def load(d:HeteroRuntimeMoeMerge,r:Vector[Route]):Unit={
    for(i<-r.indices){
      d.io.routeIn.valid.poke(true.B);d.io.routeIn.bits.expert.poke(r(i).expert.U)
      d.io.routeIn.bits.weight.poke(weight(i).U);d.io.routeIn.bits.shared.poke(r(i).shared.B)
      d.io.routeIn.ready.expect(true.B);d.io.dispatchOut.valid.expect(false.B);d.clock.step()
    }
    d.io.routeIn.valid.poke(false.B);d.io.routeIn.bits.expert.poke(1023.U);d.io.routeIn.bits.weight.poke(0.U);d.io.routeIn.bits.shared.poke(true.B)
  }
  private def issue(d:HeteroRuntimeMoeMerge,r:Vector[Route],token:Int):Unit={
    for(i<-r.indices){
      d.io.dispatchOut.ready.poke(false.B)
      def check():Unit={d.io.dispatchOut.valid.expect(true.B);d.io.dispatchOut.bits.routeTag.expect(i.U)
        d.io.dispatchOut.bits.expert.expect(r(i).expert.U);d.io.dispatchOut.bits.shared.expect(r(i).shared.B)
        d.io.dispatchOut.bits.weight.expect(weight(i).U);d.io.dispatchOut.bits.token.expect(token.U)
        d.io.dispatchOut.bits.last.expect((i==r.size-1).B)}
      check();d.clock.step(2);check();d.io.dispatchOut.ready.poke(true.B);d.clock.step()
    }
    d.io.dispatchOut.ready.poke(false.B);d.io.dispatchOut.valid.expect(false.B)
  }
  private def response(d:HeteroRuntimeMoeMerge,tag:Int,data:BigInt):Unit={
    d.io.resultIn.valid.poke(true.B);d.io.resultIn.bits.routeTag.poke(tag.U);d.io.resultIn.bits.data.poke(data.U)
    d.io.resultIn.ready.expect(true.B);d.io.mergeOut.valid.expect(false.B);d.clock.step();d.io.resultIn.valid.poke(false.B)
  }
  private def waitMerge(d:HeteroRuntimeMoeMerge):Unit={
    var n=0;while(!d.io.mergeOut.valid.peek().litToBoolean && n<40){d.io.done.expect(false.B);d.clock.step();n+=1}
    d.io.mergeOut.valid.expect(true.B)
  }
  private def finish(d:HeteroRuntimeMoeMerge,r:Vector[Route],token:Int,mode:Boolean):Vector[Int]={
    val expected=if(mode)r.indices.sortBy(i=>(r(i).shared,r(i).expert,i)).toVector else r.indices.toVector
    var got=Vector.empty[Int]
    for(rank<-r.indices){
      d.io.mergeOut.ready.poke(false.B);waitMerge(d)
      val tag=expected(rank)
      def check():Unit={d.io.mergeOut.valid.expect(true.B);d.io.mergeOut.bits.routeTag.expect(tag.U)
        d.io.mergeOut.bits.weight.expect(weight(tag).U);d.io.mergeOut.bits.data.expect(payload(token,tag).U)
        d.io.mergeOut.bits.first.expect((rank==0).B);d.io.mergeOut.bits.last.expect((rank==r.size-1).B)}
      check();d.io.done.expect(false.B);d.clock.step(3);check()
      d.io.mergeOut.ready.poke(true.B);got:+=d.io.mergeOut.bits.routeTag.peek().litValue.toInt
      d.io.done.expect((rank==r.size-1).B);d.clock.step()
    }
    d.io.mergeOut.ready.poke(false.B);d.io.busy.expect(false.B);d.io.protocolError.expect(false.B)
    d.io.done.expect(false.B);d.io.mergeOut.valid.expect(false.B);d.clock.step(3);d.io.mergeOut.valid.expect(false.B)
    got.distinct.size shouldBe r.size;got shouldBe expected;got
  }
  it should "switch legacy to expert to legacy to expert without reset while locking accepted config and holding opaque identities" in {
    test(new HeteroRuntimeMoeMerge).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      val jobs=Vector((11,withShared,false),(12,withShared,true),(13,Vector.tabulate(16)(i=>Route(1023-i)),false),(14,routed,true))
      for((token,r,mode)<-jobs){
        start(d,token,r.size,mode);load(d,r);issue(d,r,token)
        for(i<-r.indices.reverse)response(d,i,payload(token,i))
        val got=finish(d,r,token,mode)
        println(s"RUNTIME_MOE_JOB token=$token expertOrder=$mode count=${r.size} tags=${got.mkString(",")} experts=${got.map(r(_).expert).mkString(",")} opaque_data_verified=true")
      }
    }
  }
  it should "reject malformed runtime counts and duplicate or out of range routed and shared experts before dispatch" in {
    test(new HeteroRuntimeMoeMerge).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((count,experts)<-Vector((0,256),(7,256),(10,256),(16,256),(8,255),(9,0))){
        d.io.start.poke(true.B);d.io.mergeByExpert.poke(true.B);d.io.routeCount.poke(count.U);d.io.expertCount.poke(experts.U)
        d.io.invalidConfig.expect(true.B);d.clock.step();d.io.start.poke(false.B);d.io.busy.expect(false.B);d.io.dispatchOut.valid.expect(false.B)
      }
      val bad=Vector(routed.updated(0,Route(256)),routed.updated(0,Route(1023)),routed.updated(0,routed(1)),
        withShared.updated(0,Route(255,true)),routed.updated(0,Route(256,true)),withShared.updated(1,Route(256,true)))
      for((r,n)<-bad.zipWithIndex){
        start(d,100+n,r.size,true);load(d,r);d.io.protocolError.expect(true.B)
        d.io.dispatchOut.valid.expect(false.B);d.io.mergeOut.valid.expect(false.B);d.io.done.expect(true.B)
        d.clock.step();d.io.startReady.expect(true.B);d.io.done.expect(false.B)
      }
      // A valid job after rejected jobs must not inherit sticky error into a new admission.
      start(d,199,routed.size,true);load(d,routed);issue(d,routed,199)
      for(i<-routed.indices.reverse)response(d,i,payload(199,i))
      finish(d,routed,199,true)
      println("RUNTIME_MOE_REJECT cfg=6 route=6 valid_recovery=true")
    }
  }
  it should "drain valid results after duplicate and invalid result tags without exposing any merge" in {
    test(new HeteroRuntimeMoeMerge).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);start(d,33,routed.size,true);load(d,routed);issue(d,routed,33)
      response(d,7,payload(33,7));response(d,7,BigInt(0xbad));response(d,15,BigInt(0xbad))
      d.io.protocolError.expect(true.B)
      for(i<-(0 until 7).reverse)response(d,i,payload(33,i))
      d.io.done.expect(true.B);d.io.mergeOut.valid.expect(false.B);d.clock.step()
      d.io.busy.expect(false.B);d.io.protocolError.expect(true.B);d.clock.step(3);d.io.mergeOut.valid.expect(false.B)
      println("RUNTIME_MOE_RESPONSE_REJECT duplicate=1 out_of_range=1 valid_drained=8 merge=0")
    }
  }
  it should "accept same-cycle issued results and preserve the full sixteen-slot legacy boundary" in {
    test(new HeteroRuntimeMoeMerge).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);val r=Vector.tabulate(16)(i=>Route(i));start(d,44,16,false);load(d,r)
      for(i<-r.indices){
        d.io.dispatchOut.ready.poke(true.B);d.io.dispatchOut.valid.expect(true.B);d.io.dispatchOut.bits.routeTag.expect(i.U)
        d.io.dispatchOut.bits.last.expect((i==15).B);d.io.resultIn.valid.poke(true.B);d.io.resultIn.bits.routeTag.poke(i.U)
        d.io.resultIn.bits.data.poke(payload(44,i).U);d.io.resultIn.ready.expect(true.B);d.clock.step()
      }
      d.io.dispatchOut.ready.poke(false.B);d.io.resultIn.valid.poke(false.B);d.io.protocolError.expect(false.B)
      finish(d,r,44,false);println("RUNTIME_MOE_SAME_CYCLE issued=16 returned=16 merged=16")
    }
  }
}
