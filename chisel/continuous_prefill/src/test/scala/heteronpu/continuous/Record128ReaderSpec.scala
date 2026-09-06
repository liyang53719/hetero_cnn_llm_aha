// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class Record128ReaderSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private val base = BigInt("100001000",16)
  private def init(d:Record128Reader):Unit = {
    d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
  }
  private def launch(d:Record128Reader,index:Int,count:Int=7,start:BigInt=base,limit:BigInt=base+128):Unit = {
    d.io.request.ready.expect(true.B)
    d.io.request.bits.tableBase.poke(start.U);d.io.request.bits.tableLimit.poke(limit.U)
    d.io.request.bits.entryCount.poke(count.U);d.io.request.bits.index.poke(index.U)
    d.io.request.bits.requestTag.poke((BigInt("deadbeef00000000",16)+index).U)
    d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
  }
  "Record128Reader" should "select all record lanes above 4GiB, hold both interfaces and avoid stale caching" in {
    test(new Record128Reader).withAnnotations(Seq(VerilatorBackendAnnotation)){ d =>
      init(d)
      for(index <- Seq(0,1,2,3,4,5,6,0)) {
        launch(d,index)
        val address=base+(index/4)*64;val serial=d.io.memory.bits.tag.peek().litValue
        for(_<-0 until 4){d.io.memory.valid.expect(true.B);d.io.memory.bits.address.expect(address.U);d.io.memory.bits.tag.expect(serial.U);d.clock.step()}
        d.io.memory.bits.write.expect(false.B);d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        d.io.result.valid.expect(false.B);d.clock.step(3)
        val words=(0 until 4).map(i=>(BigInt(1)<<100)+(serial<<32)+i)
        val beat=words.zipWithIndex.map{case(w,i)=>w<<(128*i)}.reduce(_|_)
        d.io.response.bits.data.poke(beat.U);d.io.response.bits.tag.poke(serial.U);d.io.response.valid.poke(true.B)
        d.clock.step();d.io.response.valid.poke(false.B)
        for(_<-0 until 5){d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(0.U);d.io.result.bits.data.expect(words(index%4).U)
          d.io.result.bits.requestTag.expect((BigInt("deadbeef00000000",16)+index).U);d.io.request.ready.expect(false.B);d.clock.step()}
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B);d.io.resetRequired.expect(false.B)
      }
    }
  }
  for((label,index,count,start,limit)<-Seq(
    ("empty",0,0,base,base+128),("past-last",7,7,base,base+128),
    ("null-index",0xffffff,0xffffff,base,base+(BigInt(1)<<28)),
    ("bad-base",0,7,base+16,base+256),("missing-beat-padding",0,7,base,base+112),
    ("address-overflow",0,1,(BigInt(1)<<64)-64,(BigInt(1)<<64)-1),
    ("unmapped-high",0,1,BigInt(1)<<56,(BigInt(1)<<56)+64))) {
    it should s"reject $label before any memory request and permit corrected admission" in {
      test(new Record128Reader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        init(d);launch(d,index,count,start,limit)
        d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(Status.Bounds.U);d.io.memory.valid.expect(false.B)
        d.clock.step(4);d.io.result.bits.data.expect(0.U);d.io.resetRequired.expect(false.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B);launch(d,0)
        d.io.memory.valid.expect(true.B)
      }
    }
  }
  for(wrongTag<-Seq(false,true)) {
    it should s"quarantine failed responses and suppress fabricated descriptor data wrongTag=$wrongTag" in {
      test(new Record128Reader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        init(d);launch(d,2);val serial=d.io.memory.bits.tag.peek().litValue
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        d.io.response.valid.poke(true.B);d.io.response.bits.error.poke((!wrongTag).B)
        d.io.response.bits.tag.poke((serial+(if(wrongTag)1 else 0)).U);d.io.response.bits.data.poke(((BigInt(1)<<512)-1).U)
        d.clock.step();d.io.response.valid.poke(false.B);d.io.result.bits.status.expect((if(wrongTag)Status.Protocol else Status.Memory).U)
        d.io.result.bits.data.expect(0.U);d.io.resetRequired.expect(true.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.request.valid.poke(true.B)
        for(_<-0 until 5){d.io.request.ready.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
        d.io.request.valid.poke(false.B);d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);init(d)
        d.io.request.ready.expect(true.B);d.io.resetRequired.expect(false.B)
      }
    }
  }
}
