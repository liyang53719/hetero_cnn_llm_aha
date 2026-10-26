package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import gemmini._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}
import java.security.MessageDigest

class TaggedMoeResult extends Bundle {val identity=new MoeBf16TileIdentity;val value=new HeteroMoeResult(512,4)}
/** Test-only wiring to one real pre-existing scalar service. No matrix hardware
  * is replaced or resized; this is not a full4096-hardware test top. */
class MoeNumericTestHarness extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new MoeBf16TileJob))
    val route=Flipped(Decoupled(new HeteroMoeRoute(10,32)))
    val dispatch=Decoupled(new HeteroMoeDispatchEntry(32,10,32,4))
    val returned=Flipped(Decoupled(new TaggedMoeResult))
    val out=Decoupled(new MoeBf16TileResult)
    val allowRequest=Input(Bool());val allowResponse=Input(Bool())
    val scalarIssued=Output(Bool());val scalarRequest=Output(new ScalarRequest)
    val scalarReturned=Output(Bool());val scalarFlags=Output(UInt(5.W));val scalarError=Output(Bool())
    val staleRejected=Output(Bool());val routeError=Output(Bool())
    val injectFailure=Flipped(Decoupled(new MoeBf16SourceFailure)) // negative tests only
    val rejectedFailure=Output(Bool())
  })
  val order=Module(new HeteroRuntimeMoeMerge)
  val consumer=Module(new MoeBf16ScalarConsumer)
  val scalar=Module(new BlockScalarFloat)
  val identity=Reg(new MoeBf16TileIdentity)
  val rejected=RegInit(false.B);val failurePending=RegInit(false.B)
  val moeCount=io.job.bits.contributionCount===8.U || io.job.bits.contributionCount===9.U
  io.job.ready:=order.io.startReady && consumer.io.job.ready && !rejected && !failurePending
  when(io.job.fire && !moeCount){rejected:=true.B}
  when(rejected && io.out.fire){rejected:=false.B}
  when(io.job.fire){identity:=io.job.bits.identity}
  order.io.clear:=reset.asBool;order.io.start:=io.job.fire && moeCount;order.io.token:=io.job.bits.identity.token
  order.io.routeCount:=io.job.bits.contributionCount;order.io.expertCount:=256.U;order.io.mergeByExpert:=true.B
  consumer.io.job.valid:=io.job.valid && order.io.startReady && moeCount && !rejected && !failurePending;consumer.io.job.bits:=io.job.bits
  order.io.routeIn<>io.route;io.dispatch<>order.io.dispatchOut
  val current=io.returned.bits.identity.asUInt===identity.asUInt
  io.returned.ready:=consumer.io.busy && Mux(current,order.io.resultIn.ready,true.B)
  order.io.resultIn.valid:=io.returned.valid && current && consumer.io.busy
  order.io.resultIn.bits:=io.returned.bits.value
  io.staleRejected:=io.returned.fire && !current;io.routeError:=order.io.protocolError
  // Real producer terminal pulse, not its early/bare sticky error signal.
  when(order.io.done && order.io.protocolError){failurePending:=true.B}
  consumer.io.sourceFailure.valid:=failurePending || io.injectFailure.valid
  consumer.io.sourceFailure.bits:=io.injectFailure.bits
  when(failurePending){
    consumer.io.sourceFailure.bits.identity:=identity
    consumer.io.sourceFailure.bits.status:=Status.Protocol.U
    consumer.io.sourceFailure.bits.drained:=true.B
  }
  when(failurePending && consumer.io.sourceFailure.fire){failurePending:=false.B}
  io.injectFailure.ready:=consumer.io.sourceFailure.ready && !failurePending
  io.rejectedFailure:=consumer.io.rejectedFailure
  consumer.io.contribution.valid:=order.io.mergeOut.valid
  order.io.mergeOut.ready:=consumer.io.contribution.ready
  consumer.io.contribution.bits.identity:=identity
  consumer.io.contribution.bits.routeTag:=order.io.mergeOut.bits.routeTag
  consumer.io.contribution.bits.weight:=order.io.mergeOut.bits.weight
  consumer.io.contribution.bits.data:=order.io.mergeOut.bits.data
  consumer.io.contribution.bits.first:=order.io.mergeOut.bits.first
  consumer.io.contribution.bits.last:=order.io.mergeOut.bits.last
  scalar.io.request.valid:=consumer.io.scalarRequest.valid && io.allowRequest
  scalar.io.request.bits:=consumer.io.scalarRequest.bits
  consumer.io.scalarRequest.ready:=scalar.io.request.ready && io.allowRequest
  consumer.io.scalarResult.valid:=scalar.io.result.valid && io.allowResponse
  consumer.io.scalarResult.bits:=scalar.io.result.bits
  consumer.io.scalarError:=scalar.io.error
  scalar.io.result.ready:=consumer.io.scalarResult.ready && io.allowResponse
  io.scalarIssued:=scalar.io.request.fire;io.scalarRequest:=scalar.io.request.bits
  io.scalarReturned:=scalar.io.result.fire;io.scalarFlags:=scalar.io.primitiveFlags;io.scalarError:=scalar.io.error
  io.out.valid:=rejected || consumer.io.result.valid
  io.out.bits:=consumer.io.result.bits
  when(rejected){io.out.bits.identity:=identity;io.out.bits.data:=0.U;io.out.bits.status:=Status.Malformed.U}
  consumer.io.result.ready:=io.out.ready && !rejected
}

class MoeBf16ScalarConsumerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "shared scalar BF16 expert merge numeric path"
  private val pin="2b86f02e0fb78343f4bb611cdf796565c35e4ef22c0ceacebb35be3b03a5b9c0"
  private def golden():ujson.Value={
    val bytes=Files.readAllBytes(Paths.get(sys.env("MOE_GOLDEN")))
    MessageDigest.getInstance("SHA-256").digest(bytes).map(x=>f"${x&255}%02x").mkString shouldBe pin
    ujson.read(new String(bytes,java.nio.charset.StandardCharsets.UTF_8))
  }
  private case class C(expert:Int,shared:Boolean,weight:BigInt,data:BigInt)
  private def bits(packed:BigInt,lane:Int)=(packed>>(16*lane))&65535
  private def pack(raw:ujson.Value)=raw.arr.zipWithIndex.map{case(x,i)=>BigInt(x.num.toInt)<<(16*i)}.foldLeft(BigInt(0))(_|_)
  private def id(d:MoeNumericTestHarness,txn:Int,token:Int,tile:Int):Unit={
    d.io.job.bits.identity.transactionId.poke(txn.U);d.io.job.bits.identity.token.poke(token.U);d.io.job.bits.identity.tileOrdinal.poke(tile.U)
    d.io.returned.bits.identity.transactionId.poke(txn.U);d.io.returned.bits.identity.token.poke(token.U);d.io.returned.bits.identity.tileOrdinal.poke(tile.U)
  }
  private def init(d:MoeNumericTestHarness):Unit={
    d.clock.setTimeout(30000);d.io.job.valid.poke(false.B);id(d,0,0,0);d.io.job.bits.contributionCount.poke(9.U)
    d.io.route.valid.poke(false.B);d.io.route.bits.expert.poke(0.U);d.io.route.bits.weight.poke(0.U);d.io.route.bits.shared.poke(false.B)
    d.io.dispatch.ready.poke(false.B);d.io.returned.valid.poke(false.B);d.io.returned.bits.value.routeTag.poke(0.U);d.io.returned.bits.value.data.poke(0.U)
    d.io.out.ready.poke(false.B);d.io.allowRequest.poke(true.B);d.io.allowResponse.poke(true.B)
    d.io.injectFailure.valid.poke(false.B);d.io.injectFailure.bits.identity.transactionId.poke(0.U)
    d.io.injectFailure.bits.identity.token.poke(21.U);d.io.injectFailure.bits.identity.tileOrdinal.poke(7.U)
    d.io.injectFailure.bits.status.poke(Status.Protocol.U);d.io.injectFailure.bits.drained.poke(false.B)
  }
  private def loadAndReturn(d:MoeNumericTestHarness,c:Vector[C],txn:Int,injectStale:Boolean):Unit={
    id(d,txn,21,7);d.io.job.bits.contributionCount.poke(c.size.U);d.io.job.valid.poke(true.B)
    d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
    // Mutate live job fields after fire, not the locked test parent identity.
    d.io.job.bits.identity.transactionId.poke(999.U);d.io.job.bits.identity.token.poke(999.U);d.io.job.bits.contributionCount.poke(0.U)
    for(x<-c){d.io.route.valid.poke(true.B);d.io.route.bits.expert.poke(x.expert.U);d.io.route.bits.weight.poke(x.weight.U);d.io.route.bits.shared.poke(x.shared.B);d.io.route.ready.expect(true.B);d.clock.step()}
    d.io.route.valid.poke(false.B);d.io.dispatch.ready.poke(true.B)
    for(i<-c.indices){d.io.dispatch.valid.expect(true.B);d.io.dispatch.bits.routeTag.expect(i.U);d.io.dispatch.bits.expert.expect(c(i).expert.U);d.io.dispatch.bits.token.expect(21.U);d.clock.step()}
    d.io.dispatch.ready.poke(false.B)
    if(injectStale){
      d.io.returned.valid.poke(true.B);d.io.returned.bits.identity.transactionId.poke((txn-1).U)
      d.io.returned.bits.value.routeTag.poke(0.U);d.io.returned.bits.value.data.poke(0.U)
      d.io.returned.ready.expect(true.B);d.io.staleRejected.expect(true.B);d.clock.step();d.io.returned.bits.identity.transactionId.poke(txn.U)
    }
    for(i<-c.indices.reverse){d.io.returned.valid.poke(true.B);d.io.returned.bits.value.routeTag.poke(i.U);d.io.returned.bits.value.data.poke(c(i).data.U);d.io.returned.ready.expect(true.B);d.clock.step()}
    d.io.returned.valid.poke(false.B)
    if(injectStale){
      // Before the first contribution, reject bad failure receipts without
      // killing the current legitimate numeric result or spending its credit.
      d.io.injectFailure.valid.poke(true.B);d.io.injectFailure.bits.identity.transactionId.poke((txn-1).U)
      d.io.injectFailure.bits.drained.poke(true.B);d.io.injectFailure.ready.expect(true.B)
      d.io.rejectedFailure.expect(true.B);d.clock.step()
      d.io.injectFailure.bits.identity.transactionId.poke(txn.U);d.io.injectFailure.bits.drained.poke(false.B)
      d.io.injectFailure.ready.expect(true.B);d.io.rejectedFailure.expect(true.B);d.clock.step()
      d.io.injectFailure.bits.drained.poke(true.B);d.io.injectFailure.bits.status.poke(Status.Ok.U)
      d.io.injectFailure.ready.expect(true.B);d.io.rejectedFailure.expect(true.B);d.clock.step()
      d.io.injectFailure.bits.status.poke(255.U);d.io.injectFailure.ready.expect(true.B)
      d.io.rejectedFailure.expect(true.B);d.clock.step()
      d.io.injectFailure.valid.poke(false.B);d.io.injectFailure.bits.status.poke(Status.Protocol.U)
    }
  }
  it should "match all32 lanes of pinned official eager MoE and every BF16 materialized Add operand through the actual scalar circuit" in {
    val g=golden();val all=g("contributions_load_order").arr.map(x=>C(x("expert").num.toInt,x("shared").bool,BigInt(x("weight_bf16").num.toInt),BigInt(x("data_hex").str,16))).toVector
    val updates=g("actual_expert_updates").arr.toVector
    test(new MoeNumericTestHarness).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      // Two jobs, one DUT, no reset: full MoE incl shared, then routed-only.
      for((c,txn)<-Vector((all,100),(all.filterNot(_.shared),101))){
        loadAndReturn(d,c,txn,injectStale=true)
        val ordered=c.sortBy(x=>(x.shared,x.expert));var issued=0;var elapsed=0;var returned=0
        var subnormalAdds=0
        while(!d.io.out.valid.peek().litToBoolean && elapsed<18000){
          d.io.allowRequest.poke((elapsed%7!=0).B);d.io.allowResponse.poke((elapsed%11!=0).B)
          if(d.io.scalarIssued.peek().litToBoolean){
            val ordinal=issued/64;val lane=(issued%64)/2;val mul=(issued%2)==0;val x=ordered(ordinal)
            d.io.scalarRequest.op.expect((if(mul)ScalarOp.MulIeeeRne else ScalarOp.Add).U)
            val prior=if(ordinal==0)BigInt(0) else BigInt(updates(ordinal-1)("accumulator_bf16")(lane).num.toInt)
            // Shared fixture is observed preweight2 on lane4, weight.5; native full forward result confirms +1.
            val weighted=if(x.shared){if(lane==4)BigInt(0x3f80) else BigInt(0)} else BigInt(updates(x.expert)("weighted_bf16")(lane).num.toInt)
            d.io.scalarRequest.a.expect(((if(mul)bits(x.data,lane) else prior)<<16).U)
            d.io.scalarRequest.b.expect(((if(mul)x.weight else weighted)<<16).U)
            if(!mul && lane==2 && weighted!=0)subnormalAdds+=1
            issued+=1
          }
          if(d.io.scalarReturned.peek().litToBoolean){d.io.scalarError.expect(false.B);returned+=1}
          d.io.routeError.expect(false.B);d.clock.step();elapsed+=1
        }
        d.io.out.valid.expect(true.B);issued shouldBe c.size*64;returned shouldBe issued
        subnormalAdds shouldBe 2
        val expected=if(c.size==9)BigInt(g("output_hex").str,16) else pack(updates.last("accumulator_bf16"))
        d.io.out.bits.data.expect(expected.U);d.io.out.bits.status.expect(Status.Ok.U)
        d.io.out.bits.identity.transactionId.expect(txn.U);d.io.out.bits.identity.token.expect(21.U);d.io.out.bits.identity.tileOrdinal.expect(7.U)
        d.io.job.ready.expect(false.B);d.clock.step(4);d.io.out.bits.data.expect(expected.U)
        d.io.out.ready.poke(true.B);d.clock.step();d.io.out.ready.poke(false.B);d.io.job.ready.expect(true.B)
        println(s"MOE_NUMERIC txn=$txn contributions=${c.size} lanes=32 scalar_ops=$issued cycles=$elapsed exact_all_lanes=true bf16_intermediate_operands=true stale_rejected=true")
      }
    }
  }
  it should "reject noncanonical weight encoding and drain remaining contributions without issuing arithmetic" in {
    val g=golden();val all=g("contributions_load_order").arr.map(x=>C(x("expert").num.toInt,x("shared").bool,BigInt(x("weight_bf16").num.toInt),BigInt(x("data_hex").str,16))).toVector
    // Invalid expert0 weight is selected first, regardless of loaded route position.
    val bad=all.map(x=>if(x.expert==0)x.copy(weight=BigInt("3f800000",16)) else x)
    test(new MoeNumericTestHarness).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);loadAndReturn(d,bad,200,injectStale=false);var n=0
      while(!d.io.out.valid.peek().litToBoolean && n<200){d.io.scalarIssued.expect(false.B);d.clock.step();n+=1}
      d.io.out.valid.expect(true.B);d.io.out.bits.status.expect(Status.Numerical.U);d.io.out.bits.data.expect(0.U)
      d.io.out.ready.poke(true.B);d.clock.step();d.io.job.ready.expect(true.B)
      println("MOE_NUMERIC_GATEWAY noncanonical_high16_rejected=true remaining8_drained=true scalar_ops=0")
    }
  }
  it should "reject nonMoE counts atomically without starting either child" in {
    test(new MoeNumericTestHarness).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for(count<-Vector(0,1,7,10,16,17,31)){
        id(d,300+count,21,7);d.io.job.bits.contributionCount.poke(count.U);d.io.job.valid.poke(true.B)
        d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
        d.io.out.valid.expect(true.B);d.io.out.bits.status.expect(Status.Malformed.U)
        d.io.out.bits.identity.transactionId.expect((300+count).U)
        d.io.dispatch.valid.expect(false.B);d.io.route.ready.expect(false.B);d.io.scalarIssued.expect(false.B)
        d.io.job.ready.expect(false.B);d.clock.step(3);d.io.out.valid.expect(true.B)
        d.io.out.ready.poke(true.B);d.clock.step();d.io.out.ready.poke(false.B);d.io.job.ready.expect(true.B)
      }
      println("MOE_GATEWAY count_reject=7 no_partial_child_admission=true")
    }
  }
  it should "drop stale identities in Load and Drain without spending current unique contribution credit" in {
    test(new MoeBf16ScalarConsumer).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      d.clock.setTimeout(500)
      d.io.job.valid.poke(false.B);d.io.job.bits.identity.transactionId.poke(400.U)
      d.io.job.bits.identity.token.poke(21.U);d.io.job.bits.identity.tileOrdinal.poke(7.U);d.io.job.bits.contributionCount.poke(2.U)
      d.io.contribution.valid.poke(false.B);d.io.contribution.bits.identity.transactionId.poke(400.U)
      d.io.contribution.bits.identity.token.poke(21.U);d.io.contribution.bits.identity.tileOrdinal.poke(7.U)
      d.io.contribution.bits.routeTag.poke(0.U);d.io.contribution.bits.weight.poke(0.U);d.io.contribution.bits.data.poke(0.U)
      d.io.contribution.bits.first.poke(true.B);d.io.contribution.bits.last.poke(false.B)
      d.io.result.ready.poke(false.B);d.io.scalarRequest.ready.poke(true.B);d.io.scalarResult.valid.poke(false.B)
      d.io.sourceFailure.valid.poke(false.B);d.io.sourceFailure.bits.identity.transactionId.poke(400.U)
      d.io.sourceFailure.bits.identity.token.poke(21.U);d.io.sourceFailure.bits.identity.tileOrdinal.poke(7.U)
      d.io.sourceFailure.bits.status.poke(Status.Protocol.U);d.io.sourceFailure.bits.drained.poke(false.B)
      d.io.scalarResult.bits.poke(0.U);d.io.scalarError.poke(false.B)
      d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
      def beat(txn:Int,tag:Int,weight:BigInt,stale:Boolean):Unit={
        d.io.contribution.valid.poke(true.B);d.io.contribution.bits.identity.transactionId.poke(txn.U)
        d.io.contribution.bits.routeTag.poke(tag.U);d.io.contribution.bits.weight.poke(weight.U)
        d.io.contribution.ready.expect(true.B);d.io.staleContributionRejected.expect(stale.B)
        d.io.scalarRequest.valid.expect(false.B);d.clock.step();d.io.contribution.valid.poke(false.B)
      }
      beat(399,0,0,true);d.io.result.valid.expect(false.B) // Stale while in Load.
      beat(400,0,BigInt("3f800000",16),false);d.io.result.valid.expect(false.B) // One current slot, numerical failure.
      beat(399,1,0,true);d.io.result.valid.expect(false.B) // Stale while in Drain.
      beat(400,0,0,false);d.io.result.valid.expect(false.B) // Duplicate current slot, no credit.
      beat(400,15,0,false);d.io.result.valid.expect(false.B) // Out-of-range current slot, no credit.
      d.clock.step(3);d.io.result.valid.expect(false.B);d.io.scalarRequest.valid.expect(false.B)
      beat(400,1,0,false);d.io.result.valid.expect(true.B) // Only this legitimate remaining slot completes drain.
      d.io.result.bits.identity.transactionId.expect(400.U);d.io.result.bits.status.expect(Status.Numerical.U)
      d.io.result.bits.data.expect(0.U);d.clock.step(3);d.io.result.valid.expect(true.B)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.job.ready.expect(true.B)
      println("MOE_CONSUMER identity_drop_load=1 identity_drop_drain=1 duplicate_drop=1 out_of_range_drop=1 legitimate_unique_retired=2 scalar_ops=0")
    }
  }

  it should "finish bad route and bad reply jobs only through the real producer drained failure receipt" in {
    val g=golden();val all=g("contributions_load_order").arr.map(x=>C(x("expert").num.toInt,x("shared").bool,BigInt(x("weight_bf16").num.toInt),BigInt(x("data_hex").str,16))).toVector
    test(new MoeNumericTestHarness).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((badRoute,txn)<-Vector((true,500),(false,501))){
        id(d,txn,21,7);d.io.job.bits.contributionCount.poke(9.U);d.io.job.valid.poke(true.B)
        d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
        for((x,i)<-all.zipWithIndex){
          d.io.route.valid.poke(true.B);d.io.route.bits.expert.poke((if(badRoute && i==1)1023 else x.expert).U)
          d.io.route.bits.weight.poke(x.weight.U);d.io.route.bits.shared.poke(x.shared.B)
          d.io.route.ready.expect(true.B);d.clock.step();d.io.scalarIssued.expect(false.B)
        }
        d.io.route.valid.poke(false.B)
        if(!badRoute){
          d.io.dispatch.ready.poke(true.B)
          for(i<-all.indices){d.io.dispatch.valid.expect(true.B);d.io.dispatch.bits.routeTag.expect(i.U);d.clock.step()}
          d.io.dispatch.ready.poke(false.B)
          // Out-of-range reply does not retire a legal result; all9 must drain.
          d.io.returned.valid.poke(true.B);d.io.returned.bits.value.routeTag.poke(15.U);d.io.returned.bits.value.data.poke(0.U)
          d.io.returned.ready.expect(true.B);d.clock.step();d.io.routeError.expect(true.B)
          d.io.returned.valid.poke(false.B);d.clock.step(3);d.io.out.valid.expect(false.B)
          for(i<-all.indices.reverse){
            d.io.returned.valid.poke(true.B);d.io.returned.bits.value.routeTag.poke(i.U);d.io.returned.bits.value.data.poke(all(i).data.U)
            d.io.returned.ready.expect(true.B);d.io.out.valid.expect(false.B);d.clock.step()
          }
          d.io.returned.valid.poke(false.B)
        }
        var n=0
        while(!d.io.out.valid.peek().litToBoolean && n<30){d.io.scalarIssued.expect(false.B);d.clock.step();n+=1}
        d.io.out.valid.expect(true.B);d.io.out.bits.status.expect(Status.Protocol.U);d.io.out.bits.data.expect(0.U)
        d.io.out.bits.identity.transactionId.expect(txn.U);d.io.dispatch.valid.expect(false.B);d.io.scalarIssued.expect(false.B)
        d.clock.step(3);d.io.out.valid.expect(true.B);d.io.out.bits.status.expect(Status.Protocol.U)
        d.io.out.ready.poke(true.B);d.clock.step();d.io.out.ready.poke(false.B);d.io.job.ready.expect(true.B)
        println(s"MOE_DRAINED_FAILURE txn=$txn bad_route=$badRoute real_producer_done=true scalar_ops=0 numeric_output_published=false")
      }
    }
  }

}
