package heteronpu.p0
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.collection.mutable
import scala.util.Random

class SharedL2FabricSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val mask512=(BigInt(1)<<512)-1;val mask64=(BigInt(1)<<64)-1
  def init(d:SharedL2Fabric):Unit={d.io.rd_valid_i.poke(0.U);d.io.rd_addr_i.poke(0.U);d.io.rd_resp_ready_i.poke(0.U);d.io.wr_valid_i.poke(false.B);d.io.wr_addr_i.poke(0.U);d.io.wr_data_i.poke(0.U);d.io.wr_be_i.poke(0.U)}
  def write(d:SharedL2Fabric,addr:Int,data:BigInt,mask:BigInt):Unit={
    d.io.wr_addr_i.poke(addr.U);d.io.wr_data_i.poke(data.U);d.io.wr_be_i.poke(mask.U);d.io.wr_valid_i.poke(true.B)
    var n=0;while(!d.io.wr_ready_o.peek().litToBoolean && n<10){d.clock.step();n+=1};n should be < 10;d.clock.step();d.io.wr_valid_i.poke(false.B)
  }
  it should "reject encoding-valid rows beyond physical depth and retain diagnostics until reset" in {
    test(new SharedL2Fabric(LocalSramConfig(6,3))).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);write(d,11,BigInt(0x1234),mask64)
      d.io.rd_addr_i.poke((BigInt(12)|(BigInt(63)<<6)).U);d.io.rd_valid_i.poke(3.U);d.io.wr_addr_i.poke(12.U);d.io.wr_valid_i.poke(true.B)
      for(_<-0 until 5){d.io.rd_ready_o.expect(0.U);d.io.wr_ready_o.expect(false.B);d.clock.step()}
      d.io.address_error_o.expect(7.U);d.io.read_count_o.expect(0.U);d.io.write_count_o.expect(1.U)
      init(d);d.clock.step(3);d.io.address_error_o.expect(7.U);d.reset.poke(true.B);d.clock.step();d.reset.poke(false.B);d.io.address_error_o.expect(0.U)
    }
  }
  it should "hold the last legal read data across unrelated writes and response backpressure" in {
    test(new SharedL2Fabric(LocalSramConfig(6,3))).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);val expected=mask512^BigInt(37);write(d,11,expected,mask64)
      d.io.rd_addr_i.poke(11.U);d.io.rd_valid_i.poke(1.U);d.io.rd_ready_o.expect(1.U);d.clock.step();d.io.rd_valid_i.poke(0.U)
      d.io.rd_resp_valid_o.expect(1.U);d.io.rd_data_o.expect(expected.U)
      for(i<-0 until 8){write(d,3,BigInt(i),mask64);d.io.rd_resp_valid_o.expect(1.U);d.io.rd_data_o.expect(expected.U)}
      d.io.rd_resp_ready_i.poke(1.U);d.clock.step();d.io.rd_resp_valid_o.expect(0.U)
    }
  }
  it should "round-robin read0 read1 and write when all request the same bank group" in {
    test(new SharedL2Fabric(LocalSramConfig(6,3))).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);write(d,0,BigInt(0),mask64);d.io.rd_addr_i.poke(0.U);d.io.rd_valid_i.poke(3.U);d.io.rd_resp_ready_i.poke(3.U)
      d.io.wr_addr_i.poke(0.U);d.io.wr_valid_i.poke(true.B);d.io.wr_be_i.poke(mask64.U)
      val counts=Array(0,0,0)
      for(_<-0 until 30){val r=d.io.rd_ready_o.peek().litValue.toInt;val w=d.io.wr_ready_o.peek().litToBoolean
        Integer.bitCount(r)+(if(w)1 else 0) shouldBe 1
        for(p<-0 until 2)if((r&(1<<p))!=0)counts(p)+=1;if(w)counts(2)+=1;d.clock.step()}
      counts.toSeq shouldBe Seq(10,10,10)
    }
  }
  for(seed<-Seq(3,17,71,501)) it should s"match a byte-masked scoreboard under random dual-read traffic seed=$seed" in {
    test(new SharedL2Fabric(LocalSramConfig(6,5))).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.clock.setTimeout(10000);val rng=new Random(seed);val mem=Array.fill[BigInt](20)(0)
      for(a<-mem.indices){mem(a)=BigInt(512,rng);write(d,a,mem(a),mask64)}
      val expect=Array.fill(2)(mutable.Queue.empty[BigInt]);val req=Array.fill[Option[Int]](2)(None)
      var wreq:Option[(Int,BigInt,BigInt)]=None;val held=Array.fill[Option[BigInt]](2)(None)
      for(tick<-0 until 600){
        for(p<-0 until 2)if(req(p).isEmpty && tick<500 && rng.nextBoolean())req(p)=Some(rng.nextInt(20))
        if(wreq.isEmpty && tick<500 && rng.nextBoolean())wreq=Some((rng.nextInt(20),BigInt(512,rng),BigInt(64,rng)))
        val rv=(if(req(0).nonEmpty)1 else 0)|(if(req(1).nonEmpty)2 else 0)
        val addresses=BigInt(req(0).getOrElse(0))|(BigInt(req(1).getOrElse(0))<<6)
        val ready=(if(tick>=500||rng.nextBoolean())1 else 0)|(if(tick>=500||rng.nextBoolean())2 else 0)
        d.io.rd_valid_i.poke(rv.U);d.io.rd_addr_i.poke(addresses.U);d.io.rd_resp_ready_i.poke(ready.U)
        d.io.wr_valid_i.poke(wreq.nonEmpty.B);d.io.wr_addr_i.poke(wreq.map(_._1).getOrElse(0).U)
        d.io.wr_data_i.poke(wreq.map(_._2).getOrElse(BigInt(0)).U);d.io.wr_be_i.poke(wreq.map(_._3).getOrElse(BigInt(0)).U)
        val valid=d.io.rd_resp_valid_o.peek().litValue.toInt;val data=d.io.rd_data_o.peek().litValue
        for(p<-0 until 2)if((valid&(1<<p))!=0){
          expect(p).nonEmpty shouldBe true;val word=(data>>(512*p))&mask512;word shouldBe expect(p).front;held(p).foreach(_ shouldBe word)
          if((ready&(1<<p))!=0){expect(p).dequeue();held(p)=None}else held(p)=Some(word)
        }
        val grant=d.io.rd_ready_o.peek().litValue.toInt
        for(p<-0 until 2)if((grant&(1<<p))!=0){expect(p).enqueue(mem(req(p).get));req(p)=None}
        if(d.io.wr_ready_o.peek().litToBoolean){val(a,v,m)=wreq.get
          for(b<-0 until 64)if(m.testBit(b))mem(a)=(mem(a)&~(BigInt(255)<<(8*b)))|(((v>>(8*b))&255)<<(8*b));wreq=None}
        d.clock.step()
      }
      expect.forall(_.isEmpty) shouldBe true;req.forall(_.isEmpty) shouldBe true;wreq shouldBe None;d.io.address_error_o.expect(0.U)
    }
  }
}
