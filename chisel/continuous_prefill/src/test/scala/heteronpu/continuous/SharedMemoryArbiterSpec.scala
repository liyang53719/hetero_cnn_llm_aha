// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class SharedMemoryArbiterSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:SharedMemoryArbiter):Unit={
    for(i<-0 until 3){d.io.requests(i).valid.poke(false.B);d.io.requests(i).bits.write.poke(false.B)
      d.io.requests(i).bits.address.poke((0x1000+i*64).U);d.io.requests(i).bits.data.poke(0.U)
      d.io.requests(i).bits.mask.poke(0.U);d.io.requests(i).bits.tag.poke("hfedcba9876543210".U)
      d.io.responses(i).ready.poke(false.B)}
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
  }
  "SharedMemoryArbiter" should "lock offers, preserve complete colliding client tags, and return only to the captured owner" in {
    test(new SharedMemoryArbiter(3)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);val tags=scala.collection.mutable.Set[BigInt]()
      for(client<-Seq(0,1,2,0,2,1)){
        d.io.requests(client).valid.poke(true.B);d.io.requests(client).ready.expect(true.B)
        d.clock.step();d.io.requests(client).valid.poke(false.B)
        val address=d.io.memory.bits.address.peek().litValue;val transport=d.io.memory.bits.tag.peek().litValue
        tags.contains(transport) shouldBe false;tags+=transport
        d.io.requests(client).bits.tag.poke(7.U)
        for(_<-0 until 5){d.io.memory.valid.expect(true.B);d.io.memory.bits.address.expect(address.U);d.io.memory.bits.tag.expect(transport.U);d.clock.step()}
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        d.io.response.bits.tag.poke(transport.U);d.io.response.bits.data.poke(0xcafe.U);d.io.response.valid.poke(true.B)
        d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
        for(_<-0 until 7){for(i<-0 until 3)d.io.responses(i).valid.expect((i==client).B)
          d.io.responses(client).bits.tag.expect("hfedcba9876543210".U)
          d.io.responses(client).bits.data.expect(0xcafe.U);d.io.responses(client).bits.error.expect(false.B)
          d.io.memory.valid.expect(false.B);d.clock.step()}
        d.io.responses(client).ready.poke(true.B);d.clock.step();d.io.responses(client).ready.poke(false.B)
        d.io.requests(client).bits.tag.poke("hfedcba9876543210".U)
      }
      for(i<-0 until 3){d.io.accepted(i).expect(2.U);d.io.returned(i).expect(2.U)}
    }
  }
  it should "grant continuously competing clients in bounded round-robin order" in {
    test(new SharedMemoryArbiter(3)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);for(i<-0 until 3){d.io.requests(i).valid.poke(true.B);d.io.responses(i).ready.poke(true.B)}
      d.io.memory.ready.poke(true.B)
      val order=scala.collection.mutable.ArrayBuffer[Int]()
      for(_<-0 until 18){
        val chosen=(0 until 3).filter(i=>d.io.requests(i).ready.peek().litToBoolean);chosen.size shouldBe 1;order+=chosen.head
        d.clock.step();val tag=d.io.memory.bits.tag.peek().litValue;d.clock.step()
        d.io.response.valid.poke(true.B);d.io.response.bits.tag.poke(tag.U);d.clock.step();d.io.response.valid.poke(false.B);d.clock.step()
      }
      order.grouped(3).foreach(_.toSet shouldBe Set(0,1,2))
      for(i<-0 until 3){d.io.accepted(i).expect(6.U);d.io.returned(i).expect(6.U)}
    }
  }
  for(wrongTag<-Seq(false,true))it should s"quarantine an error without misrouting or accepting another request wrongTag=$wrongTag" in {
    test(new SharedMemoryArbiter(3)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.requests(1).valid.poke(true.B);d.clock.step();d.io.requests(1).valid.poke(false.B)
      val tag=d.io.memory.bits.tag.peek().litValue;d.io.memory.ready.poke(true.B);d.clock.step()
      d.io.response.bits.tag.poke((if(wrongTag)tag^1 else tag).U);d.io.response.bits.error.poke((!wrongTag).B)
      d.io.response.valid.poke(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      d.io.responses(1).bits.error.expect(true.B);d.io.responses(1).bits.tag.expect("hfedcba9876543210".U)
      d.io.responses(1).ready.poke(true.B);d.clock.step()
      for(i<-0 until 3)d.io.requests(i).valid.poke(true.B)
      for(_<-0 until 10){d.io.resetRequired.expect(true.B);d.io.memory.valid.expect(false.B);for(i<-0 until 3)d.io.requests(i).ready.expect(false.B);d.clock.step()}
      d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.io.resetRequired.expect(false.B)
    }
  }
}
