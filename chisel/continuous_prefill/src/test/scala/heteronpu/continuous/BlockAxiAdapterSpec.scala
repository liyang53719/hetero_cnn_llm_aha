// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
class BlockAxiAdapterSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  for(awFirst<-Seq(true,false)){
    "BlockAxiMemoryAdapter" should s"hold split AW/W and commit only after B awFirst=$awFirst" in {
      test(new BlockAxiMemoryAdapter).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        init(d);d.io.request.bits.write.poke(true.B);d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
        d.io.axi.aw.valid.expect(true.B);d.io.axi.w.valid.expect(true.B);d.clock.step(4);d.io.response.valid.expect(false.B)
        if(awFirst)d.io.axi.aw.ready.poke(true.B) else d.io.axi.w.ready.poke(true.B)
        d.clock.step();d.clock.step(3);d.io.response.valid.expect(false.B)
        if(awFirst){d.io.axi.aw.valid.expect(false.B);d.io.axi.w.valid.expect(true.B);d.io.axi.w.ready.poke(true.B)}
        else{d.io.axi.w.valid.expect(false.B);d.io.axi.aw.valid.expect(true.B);d.io.axi.aw.ready.poke(true.B)}
        d.clock.step();d.clock.step(3);d.io.response.valid.expect(false.B);d.io.axi.b.valid.poke(true.B);d.clock.step();d.io.axi.b.valid.poke(false.B)
        d.io.response.valid.expect(true.B);d.io.response.bits.error.expect(false.B);d.io.response.bits.tag.expect(0x1234.U)
        d.clock.step(5);d.io.response.valid.expect(true.B);d.io.response.ready.poke(true.B);d.clock.step();d.io.request.ready.expect(true.B)
      }
    }
  }
  for(fault<-Seq("none","id","resp","last")){
    it should s"check read response identity and quarantine failures fault=$fault" in {
      test(new BlockAxiMemoryAdapter).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        init(d);d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
        d.io.axi.ar.valid.expect(true.B);d.io.axi.ar.bits.addr.expect(BigInt("100000000",16).U);d.io.axi.ar.bits.size.expect(6.U);d.io.axi.ar.bits.len.expect(0.U)
        d.clock.step(4);d.io.axi.ar.ready.poke(true.B);d.clock.step();d.io.axi.r.valid.poke(true.B)
        d.io.axi.r.bits.id.poke((if(fault=="id")0x35 else 0x34).U);d.io.axi.r.bits.resp.poke((if(fault=="resp")2 else 0).U);d.io.axi.r.bits.last.poke((fault!="last").B);d.io.axi.r.bits.data.poke(0x12345678.U)
        d.clock.step();d.io.axi.r.valid.poke(false.B);d.io.response.valid.expect(true.B);d.io.response.bits.error.expect((fault!="none").B);d.io.response.bits.data.expect(0x12345678.U)
        d.io.response.ready.poke(true.B);d.clock.step();d.io.request.ready.expect((fault=="none").B);d.io.resetRequired.expect((fault!="none").B)
      }
    }
  }
  def init(d:BlockAxiMemoryAdapter):Unit={
    d.io.request.valid.poke(false.B);d.io.request.bits.write.poke(false.B);d.io.request.bits.address.poke(BigInt("100000000",16).U);d.io.request.bits.data.poke(BigInt("deadbeef",16).U);d.io.request.bits.mask.poke(BigInt("ffffffffffffffff",16).U);d.io.request.bits.tag.poke(0x1234.U)
    d.io.response.ready.poke(false.B);d.io.axi.aw.ready.poke(false.B);d.io.axi.w.ready.poke(false.B);d.io.axi.ar.ready.poke(false.B)
    d.io.axi.b.valid.poke(false.B);d.io.axi.b.bits.id.poke(0x34.U);d.io.axi.b.bits.resp.poke(0.U)
    d.io.axi.r.valid.poke(false.B);d.io.axi.r.bits.id.poke(0x34.U);d.io.axi.r.bits.resp.poke(0.U);d.io.axi.r.bits.last.poke(true.B);d.io.axi.r.bits.data.poke(0.U)
  }
}
