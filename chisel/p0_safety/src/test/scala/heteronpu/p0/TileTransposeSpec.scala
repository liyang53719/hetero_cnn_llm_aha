package heteronpu.p0
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.util.Random

class TileTransposeSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:TileTranspose):Unit={
    d.io.request_valid_i.poke(false.B);d.io.source_i.poke(0x1000.U);d.io.destination_i.poke(0x80000.U);d.io.source_stride_i.poke(128.U)
    d.io.rows_i.poke(3.U);d.io.depth_i.poke(33.U);d.io.rd_ready_i.poke(false.B);d.io.rsp_valid_i.poke(false.B);d.io.rsp_data_i.poke(0.U);d.io.rsp_error_i.poke(false.B)
    d.io.wr_ready_i.poke(false.B);d.io.completion_ready_i.poke(false.B)
  }
  for(kind<-Seq("source_end","destination_end","overlap","stride","unaligned","zero","overflow")) it should s"reject $kind before reading SRAM" in {
    test(new TileTranspose).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d)
      kind match {
        case "source_end"=>d.io.source_i.poke(0x180000.U)
        case "destination_end"=>d.io.destination_i.poke(0x17ffc0.U)
        case "overlap"=>d.io.destination_i.poke(0x1000.U)
        case "stride"=>d.io.source_stride_i.poke(64.U)
        case "unaligned"=>d.io.source_i.poke(0x1002.U)
        case "zero"=>d.io.depth_i.poke(0.U)
        case "overflow"=>d.io.source_i.poke(((BigInt(1)<<64)-64).U)
      }
      d.io.request_valid_i.poke(true.B);d.clock.step();d.io.request_valid_i.poke(false.B)
      for(_<-0 until 6){d.io.completion_valid_o.expect(true.B);d.io.status_o.expect(5.U);d.io.rd_valid_o.expect(false.B);d.io.wr_valid_o.expect(false.B);d.clock.step()}
      d.io.completion_ready_i.poke(true.B);d.clock.step();d.io.request_ready_o.expect(true.B)
    }
  }
  for((rows,depth)<-Seq((1,1),(3,17),(16,32),(16,33),(5,65),(16,128))) it should s"transpose ${rows}x${depth} with read and write backpressure" in {
    test(new TileTranspose).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.clock.setTimeout(100000)
      val stride=((depth+31)/32)*64;val destination=0x180000-depth*64
      d.io.rows_i.poke(rows.U);d.io.depth_i.poke(depth.U);d.io.source_stride_i.poke(stride.U);d.io.destination_i.poke(destination.U)
      val rng=new Random(7700+rows+depth)
      def word(r:Int,k:Int)=BigInt((r*941+k*7+11)&0xffff)
      def packed(xs:Seq[BigInt])=xs.zipWithIndex.foldLeft(BigInt(0)){case(x,(v,i))=>x|(v<<(16*i))}
      d.io.request_valid_i.poke(true.B);d.clock.step();d.io.request_valid_i.poke(false.B)
      var response:Option[(BigInt,Int)]=None;var writes=0;var reads=0;var ticks=0;var held:Option[(BigInt,BigInt)]=None
      while(!d.io.completion_valid_o.peek().litToBoolean && ticks<100000){
        val ready=rng.nextInt(4)!=0;val wready=rng.nextBoolean();d.io.rd_ready_i.poke(ready.B);d.io.wr_ready_i.poke(wready.B)
        val rv=response.exists(_._2==0);d.io.rsp_valid_i.poke(rv.B);d.io.rsp_data_i.poke(response.map(_._1).getOrElse(BigInt(0)).U)
        if(d.io.rd_valid_o.peek().litToBoolean && ready){
          val byte=d.io.rd_addr_o.peek().litValue.toInt*64-0x1000;val row=byte/stride;val kb=(byte%stride)/64*32
          row should be < rows;response=Some((packed((0 until 32).map(i=>word(row,kb+i))),2));reads+=1
        }
        if(rv && d.io.rsp_ready_o.peek().litToBoolean)response=None
        if(d.io.wr_valid_o.peek().litToBoolean){
          val data=d.io.wr_data_o.peek().litValue;val addr=d.io.wr_addr_o.peek().litValue
          held.foreach(_ shouldBe ((addr,data)));addr shouldBe BigInt(destination/64+writes)
          data shouldBe packed((0 until rows).map(r=>word(r,writes)));d.io.wr_be_o.expect(((BigInt(1)<<64)-1).U)
          if(wready){writes+=1;held=None}else held=Some((addr,data))
        }
        d.clock.step();ticks+=1;response=response.map{case(x,n)=>(x,math.max(0,n-1))}
      }
      ticks should be < 100000;writes shouldBe depth;reads shouldBe rows*((depth+31)/32)
      d.io.status_o.expect(0.U);d.io.read_beats_o.expect(reads.U);d.io.write_beats_o.expect(depth.U)
      for(_<-0 until 3){d.io.completion_valid_o.expect(true.B);d.clock.step()}
    }
  }
  it should "propagate a read error without a write" in {
    test(new TileTranspose).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.request_valid_i.poke(true.B);d.clock.step();d.io.request_valid_i.poke(false.B)
      d.io.rd_ready_i.poke(true.B);d.clock.step();d.io.rsp_valid_i.poke(true.B);d.io.rsp_error_i.poke(true.B);d.clock.step()
      d.io.completion_valid_o.expect(true.B);d.io.status_o.expect(3.U);d.io.wr_valid_o.expect(false.B);d.io.write_beats_o.expect(0.U)
    }
  }
}
