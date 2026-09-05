package heteronpu.p0
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class NormTileLoaderSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:NormTileLoader):Unit={
    d.io.start.poke(false.B);d.io.base.poke(0x10000000.U);d.io.token.poke(16.U)
    d.io.dma.ready.poke(false.B);d.io.dma.response.poke(false.B);d.io.dma.error.poke(false.B)
    d.io.memory.readReady.poke(false.B);d.io.memory.response.poke(false.B);d.io.memory.data.poke(0.U);d.io.memory.writeReady.poke(false.B)
  }
  it should "reject a DDR byte range overflow before DMA" in {
    test(new NormTileLoader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.base.poke(((BigInt(1)<<64)-64).U);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B)
      d.io.done.expect(true.B);d.io.status.expect(5.U);d.io.dma.valid.expect(false.B);d.io.memory.read.expect(false.B)
    }
  }
  it should "propagate a DMA error without starting the transpose" in {
    test(new NormTileLoader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B);d.io.dma.source.expect((0x10000000+16*3072).U)
      d.io.dma.ready.poke(true.B);d.clock.step();d.io.dma.response.poke(true.B);d.io.dma.error.poke(true.B);d.clock.step()
      d.io.done.expect(true.B);d.io.status.expect(3.U);d.io.memory.read.expect(false.B);d.io.memory.write.expect(false.B);d.io.bytes.expect(0.U)
    }
  }
  it should "run its actual Chisel transpose after one successful 16-row DMA" in {
    test(new NormTileLoader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.clock.setTimeout(20000);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B)
      d.io.dma.rowBytes.expect(3072.U);d.io.dma.rows.expect(16.U);d.io.dma.ready.poke(true.B);d.clock.step();d.io.dma.response.poke(true.B);d.clock.step();d.io.dma.response.poke(false.B)
      var pending:Option[BigInt]=None;var writes=0;var reads=0;var cycles=0
      while(!d.io.done.peek().litToBoolean && cycles<20000){
        d.io.memory.readReady.poke(true.B);d.io.memory.writeReady.poke(true.B)
        d.io.memory.response.poke(pending.nonEmpty.B);d.io.memory.data.poke(pending.getOrElse(BigInt(0)).U)
        if(pending.nonEmpty && d.io.memory.responseReady.peek().litToBoolean)pending=None
        if(d.io.memory.read.peek().litToBoolean){val b=d.io.memory.readAddress.peek().litValue.toInt*64-0x60000;val r=b/3072;val k=(b%3072)/2
          pending=Some((0 until 32).foldLeft(BigInt(0)){case(v,i)=>v|(BigInt(r*1536+k+i)<<(16*i))});reads+=1}
        if(d.io.memory.write.peek().litToBoolean){
          d.io.memory.writeAddress.expect((0x80000/64+writes).U)
          val expected=(0 until 16).foldLeft(BigInt(0)){case(v,r)=>v|(BigInt(r*1536+writes)<<(16*r))}
          d.io.memory.writeData.expect(expected.U);writes+=1
        }
        d.clock.step();cycles+=1
      }
      cycles should be < 20000;reads shouldBe 768;writes shouldBe 1536;d.io.status.expect(0.U);d.io.bytes.expect(49152.U)
    }
  }
}
