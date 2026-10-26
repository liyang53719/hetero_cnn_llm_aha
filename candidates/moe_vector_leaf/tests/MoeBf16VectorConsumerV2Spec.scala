package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}
import java.security.MessageDigest

/** Numeric leaf harness: one ACTUAL common16-lane bank, no surrogate arithmetic.
  * Ordered contribution stimulus is not the real expert producer or full4096
  * block. Policy corruption is an explicit negative-only interface injection.
  */
class MoeVectorNumericHarnessV2 extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new MoeBf16TileJob))
    val contribution=Flipped(Decoupled(new MoeBf16TileContribution))
    val result=Decoupled(new MoeBf16TileResult)
    val allowRequest=Input(Bool());val allowResponse=Input(Bool())
    val corruptPolicy=Input(Bool())
    val issued=Output(Bool());val request=Output(new UnifiedVectorRequestV2)
    val returned=Output(Bool());val response=Output(new UnifiedVectorResultV2)
    val staleContributionRejected=Output(Bool())
  })
  val consumer=Module(new MoeBf16VectorConsumerV2)
  val bank=Module(new UnifiedVectorBankV2)
  consumer.io.job<>io.job;consumer.io.contribution<>io.contribution;io.result<>consumer.io.result
  consumer.io.sourceFailure.valid:=false.B
  consumer.io.sourceFailure.bits:=0.U.asTypeOf(new MoeBf16SourceFailure)
  bank.io.request.valid:=consumer.io.vectorRequest.valid && io.allowRequest
  bank.io.request.bits:=consumer.io.vectorRequest.bits
  consumer.io.vectorRequest.ready:=bank.io.request.ready && io.allowRequest
  consumer.io.vectorResult.valid:=bank.io.result.valid && io.allowResponse
  consumer.io.vectorResult.bits:=bank.io.result.bits
  when(io.corruptPolicy){consumer.io.vectorResult.bits.policy:=0.U}
  bank.io.result.ready:=consumer.io.vectorResult.ready && io.allowResponse
  io.issued:=bank.io.request.fire;io.request:=bank.io.request.bits
  io.returned:=bank.io.result.fire;io.response:=bank.io.result.bits
  io.staleContributionRejected:=consumer.io.staleContributionRejected
}

class MoeBf16VectorConsumerV2Spec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "complete MoE32tile through the actual common V2 vector bank"
  private def golden():ujson.Value={
    val raw=Files.readAllBytes(Paths.get(sys.env("MOE_GOLDEN")))
    MessageDigest.getInstance("SHA-256").digest(raw).map(x=>f"${x&255}%02x").mkString shouldBe
      "2b86f02e0fb78343f4bb611cdf796565c35e4ef22c0ceacebb35be3b03a5b9c0"
    ujson.read(new String(raw,java.nio.charset.StandardCharsets.UTF_8))
  }
  private case class C(expert:Int,tag:Int,shared:Boolean,weight:BigInt,data:BigInt)
  private def contributions(g:ujson.Value):Vector[C]=g("contributions_load_order").arr.zipWithIndex.map{case(x,tag)=>
    C(x("expert").num.toInt,tag,x("shared").bool,BigInt(x("weight_bf16").num.toInt),BigInt(x("data_hex").str,16))
  }.toVector.sortBy(x=>(x.shared,x.expert))
  private def ident(x:MoeBf16TileIdentity,txn:Int):Unit={x.transactionId.poke(txn.U);x.token.poke(21.U);x.tileOrdinal.poke(7.U)}
  private def init(d:MoeVectorNumericHarnessV2):Unit={
    d.clock.setTimeout(10000);d.io.job.valid.poke(false.B);ident(d.io.job.bits.identity,0);d.io.job.bits.contributionCount.poke(9.U)
    d.io.contribution.valid.poke(false.B);ident(d.io.contribution.bits.identity,0)
    d.io.contribution.bits.routeTag.poke(0.U);d.io.contribution.bits.weight.poke(0.U);d.io.contribution.bits.data.poke(0.U)
    d.io.contribution.bits.first.poke(false.B);d.io.contribution.bits.last.poke(false.B)
    d.io.result.ready.poke(false.B);d.io.allowRequest.poke(true.B);d.io.allowResponse.poke(true.B);d.io.corruptPolicy.poke(false.B)
  }
  private def begin(d:MoeVectorNumericHarnessV2,txn:Int,count:Int=9):Unit={
    ident(d.io.job.bits.identity,txn);d.io.job.bits.contributionCount.poke(count.U)
    d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
    ident(d.io.job.bits.identity,999);d.io.job.bits.contributionCount.poke(0.U)
  }
  private def offer(d:MoeVectorNumericHarnessV2,txn:Int,c:C,ordinal:Int):Unit={
    ident(d.io.contribution.bits.identity,txn);d.io.contribution.bits.routeTag.poke(c.tag.U)
    d.io.contribution.bits.weight.poke(c.weight.U);d.io.contribution.bits.data.poke(c.data.U)
    d.io.contribution.bits.first.poke((ordinal==0).B);d.io.contribution.bits.last.poke((ordinal==8).B)
    d.io.contribution.valid.poke(true.B)
  }
  private def consume(d:MoeVectorNumericHarnessV2,status:Int):Unit={
    d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(status.U)
    if(status!=Status.Ok)d.io.result.bits.data.expect(0.U)
    val data=d.io.result.bits.data.peek().litValue
    d.clock.step(4);d.io.result.bits.status.expect(status.U);d.io.result.bits.data.expect(data.U)
    d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
  }
  it should "match every16-lane materialized Mul/Add and all32 outputs of the official synthetic Golden for two jobs then cover distinct nonzero values in every lane" in {
    val g=golden();val cs=contributions(g);val updates=g("actual_expert_updates").arr
    def weighted(ord:Int,lane:Int):BigInt=if(ord==8){if(lane==4)BigInt(0x3f80) else BigInt(0)}
      else BigInt(updates(ord)("weighted_bf16")(lane).num.toInt)
    def accumulated(ord:Int,lane:Int):BigInt=if(ord==8)BigInt(g("output_bf16")(lane).num.toInt)
      else BigInt(updates(ord)("accumulator_bf16")(lane).num.toInt)
    test(new MoeVectorNumericHarnessV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for(txn<-Vector(100,101,102)){
        // Third transaction is an indexing identity check, not a new official
        // model fixture: lane1..32 times1 on expert0, then eight zero products.
        val identityWords=Vector.tabulate(32)(i=>BigInt((java.lang.Float.floatToRawIntBits((i+1).toFloat)>>>16)&65535))
        val identityData=identityWords.zipWithIndex.map{case(x,i)=>x<<(16*i)}.foldLeft(BigInt(0))(_|_)
        val activeCs=if(txn==102)cs.zipWithIndex.map{case(c,i)=>c.copy(weight=if(i==0)BigInt(0x3f80) else BigInt(0),data=if(i==0)identityData else BigInt(0))} else cs
        def weightAt(ord:Int,lane:Int):BigInt=if(txn==102){if(ord==0)identityWords(lane) else BigInt(0)} else weighted(ord,lane)
        def accumAt(ord:Int,lane:Int):BigInt=if(txn==102)identityWords(lane) else accumulated(ord,lane)
        begin(d,txn);var sent=0;var issued=0;var returned=0;var cycle=0
        while(!d.io.result.valid.peek().litToBoolean && cycle<2000){
          d.io.allowRequest.poke((cycle%7!=0).B);d.io.allowResponse.poke((cycle%11!=0).B)
          if(sent<9)offer(d,txn,activeCs(sent),sent) else d.io.contribution.valid.poke(false.B)
          if(d.io.issued.peek().litToBoolean){
            val ord=issued/4;val phase=issued%4;val half=phase/2;val mul=phase%2==0
            d.io.request.policy.expect((if(mul)1 else 2).U);d.io.request.multiply.expect(mul.B)
            for(i<-0 until 16){
              val lane=half*16+i;val input=(activeCs(ord).data>>(16*lane))&65535
              val prior=if(ord==0)BigInt(0) else accumAt(ord-1,lane)
              d.io.request.a(i).expect(((if(mul)input else prior)<<16).U)
              d.io.request.b(i).expect(((if(mul)activeCs(ord).weight else weightAt(ord,lane))<<16).U)
            };issued+=1
          }
          if(d.io.returned.peek().litToBoolean){
            val ord=returned/4;val phase=returned%4;val half=phase/2;val mul=phase%2==0
            d.io.response.error.expect(false.B);d.io.response.policy.expect((if(mul)1 else 2).U)
            for(i<-0 until 16){val lane=half*16+i
              d.io.response.flags(i).expect(0.U)
              d.io.response.value(i).expect(((if(mul)weightAt(ord,lane) else accumAt(ord,lane))<<16).U)
            };returned+=1
          }
          if(d.io.contribution.valid.peek().litToBoolean && d.io.contribution.ready.peek().litToBoolean)sent+=1
          d.clock.step();cycle+=1
        }
        d.io.contribution.valid.poke(false.B);sent shouldBe 9;issued shouldBe 36;returned shouldBe 36
        d.io.result.valid.expect(true.B);d.io.result.bits.identity.transactionId.expect(txn.U)
        d.io.result.bits.identity.token.expect(21.U);d.io.result.bits.identity.tileOrdinal.expect(7.U)
        d.io.result.bits.data.expect((if(txn==102)identityData else BigInt(g("output_hex").str,16)).U);consume(d,Status.Ok)
        println(s"MOE_VECTOR_SYNTHETIC txn=$txn vector_ops=$issued lanes=32 per_lane_materialized_bits=true cycles=$cycle")
      }
    }
  }
  it should "reject noncanonical weights and not spend drain credit on stale or duplicate contributions" in {
    val cs=contributions(golden())
    test(new MoeVectorNumericHarnessV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d,200)
      offer(d,200,cs.head.copy(weight=BigInt("3f800000",16)),0);d.io.contribution.ready.expect(true.B);d.clock.step()
      offer(d,199,cs(1),1);d.io.staleContributionRejected.expect(true.B);d.io.issued.expect(false.B);d.clock.step()
      offer(d,200,cs.head,0);d.io.issued.expect(false.B);d.clock.step() // Duplicate does not retire another slot.
      for(i<-1 until 8){offer(d,200,cs(i),i);d.io.contribution.ready.expect(true.B);d.io.issued.expect(false.B);d.clock.step()}
      d.io.contribution.valid.poke(false.B);d.clock.step(4);d.io.result.valid.expect(false.B)
      offer(d,200,cs(8),8);d.clock.step();d.io.contribution.valid.poke(false.B);consume(d,Status.Numerical)
    }
  }
  it should "reject a wrong returned policy echo only after the real operation returns and drain the remaining eight" in {
    val cs=contributions(golden())
    test(new MoeVectorNumericHarnessV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d);begin(d,300);offer(d,300,cs.head,0);d.clock.step();d.io.contribution.valid.poke(false.B)
      d.io.corruptPolicy.poke(true.B);var ops=0;var replies=0;var cycles=0
      while(!d.io.contribution.ready.peek().litToBoolean && cycles<50){
        if(d.io.issued.peek().litToBoolean)ops+=1
        if(d.io.returned.peek().litToBoolean)replies+=1
        d.clock.step();cycles+=1
      }
      ops shouldBe 1;replies shouldBe 1;d.io.result.valid.expect(false.B);d.io.corruptPolicy.poke(false.B)
      for(i<-1 until 9){offer(d,300,cs(i),i);d.io.contribution.ready.expect(true.B);d.io.issued.expect(false.B);d.clock.step()}
      d.io.contribution.valid.poke(false.B);consume(d,Status.Protocol)
    }
  }
  it should "reject noncomplete contribution counts before any bank operation" in {
    test(new MoeVectorNumericHarnessV2).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      init(d)
      for((count,txn)<-Vector(0,1,8,10,16,31).zipWithIndex){begin(d,400+txn,count);d.io.issued.expect(false.B);consume(d,Status.Malformed)}
    }
  }
}
