// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class HostResidualCommandsSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  import DescriptorFixture._
  val goodCommand:BigInt=BigInt(0x330)|(BigInt(1)<<40)|(BigInt(0)<<56)|(BigInt(4)<<80)|(BigInt(7)<<104)
  val goodRecords:Map[Int,BigInt]=Map(
    0->base(0x4000),1->shape(Seq(2,16,1,1)),2->stride(Seq(16,1,1),3),
    3->rec(0x20,Null,BigInt(0x30)|(BigInt(2)<<16)|(BigInt(1)<<24)|(BigInt(7)<<32)|(BigInt(7)<<36)|(BigInt(16)<<40)),
    4->base(0x5000,next=5),5->shape(Seq(2,16,1,1),6),6->stride(Seq(16,1,1)),
    7->base(0x6000,next=8),8->shape(Seq(2,16,1,1),9),9->stride(Seq(16,1,1)))
  def initialize(d:HostResidualCommands):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B);d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.elementCount.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    val l=d.io.launch.bits;l.commandBase.poke(0x1000.U);l.commandLimit.poke(0x1040.U);l.commands.poke(1.U)
    l.descriptorBase.poke(0x2000.U);l.descriptorLimit.poke(0x2100.U);l.descriptors.poke(10.U);l.epoch.poke(11.U)
    for((base,limit,rd,wr,i)<-Seq((0x1000,0x3000,true,false,0),(0x4000,0x6000,true,false,1),(0x6000,0x8000,true,true,2),(0,0,false,false,3))){
      val r=l.regions(i);r.base.poke(base.U);r.limit.poke(limit.U);r.read.poke(rd.B);r.write.poke(wr.B)
    }
  }
  // Actual Record128Reader and typed decoder DUT; only memory and the arithmetic
  // owner's completion are environment-driven in these CONTROL tests.
  def drive(d:HostResidualCommands,cmd:BigInt=goodCommand,recs:Map[Int,BigInt]=goodRecords,
              doneError:Int=0,shortWrite:Boolean=false,wrongTag:Boolean=false,fetchError:Boolean=false): (Int,Int)={
    d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    var ticks=0;var jobs=0
    while(!d.io.completion.valid.peek().litToBoolean && !d.io.result.valid.peek().litToBoolean && ticks<2000){
      if(d.io.memory.valid.peek().litToBoolean){
        val address=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.bits.write.expect(false.B);d.clock.step(2);d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val data=if(address==0x1000)cmd else {
          val ix=((address-0x2000)/16).toInt
          (0 until 4).map(i=>recs.getOrElse(ix+i,BigInt(0))<<(128*i)).reduce(_|_)
        }
        d.clock.step(2);d.io.response.bits.tag.poke(tag.U);d.io.response.bits.data.poke(data.U);d.io.response.bits.error.poke(fetchError.B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        jobs+=1;d.io.job.bits.a.expect(0x4000.U);d.io.job.bits.b.expect(0x5000.U);d.io.job.bits.dst.expect(0x6000.U)
        d.io.job.bits.elementCount.expect(32.U);d.io.job.bits.op.expect(1.U)
        val tag=d.io.job.bits.tag.peek().litValue
        for(_<-0 until 6){d.io.job.valid.expect(true.B);d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B)
        for(_<-0 until 8){d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.done.bits.tag.poke((if(wrongTag)tag^1 else tag).U);d.io.done.bits.status.poke(doneError.U)
        d.io.done.bits.elementCount.poke(32.U);d.io.done.bits.writeBytes.poke((if(shortWrite)64 else 128).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
      }else d.clock.step()
      ticks+=1
    }
    if(d.io.completion.valid.peek().litToBoolean){
      val word=d.io.completion.bits.peek().litValue
      for(_<-0 until 6){d.io.result.valid.expect(false.B);d.io.completion.bits.expect(word.U);d.clock.step()}
      d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
    }
    d.io.result.valid.expect(true.B)
    val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.result.bits.completed.expect((if(status==0)1 else 0).U)
    d.io.result.bits.epoch.expect(11.U)
    (status,jobs)
  }
  "HostResidualCommands" should "decode actual Command128 and all ten descriptor records before issuing the existing owner" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>initialize(d);drive(d) shouldBe (0,1)}
  }
  it should "reject unsupported envelopes and invalid event dependencies before any payload job" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val cases=Seq((goodCommand^0x10,4),(goodCommand^0x100,4),(goodCommand|(BigInt(1)<<11),2),
        ((goodCommand&~(BigInt(0xffffff)<<56))|(Null<<56),2),
        (goodCommand|(BigInt(2)<<24),6),(goodCommand&~(BigInt(0xffff)<<40),6),
        ((goodCommand&~(BigInt(0xffff)<<40))|(BigInt(256)<<40),6))
      for((c,code)<-cases){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);initialize(d);drive(d,c) shouldBe (code,0)}
    }
  }
  it should "reject shape, program, reserved bits, tail and destination alias violations" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val cases=Seq(
        (goodRecords.updated(8,shape(Seq(1,32,1,1),9)).updated(9,stride(Seq(32,1,1))),4),
        (goodRecords.updated(3,goodRecords(3)^(BigInt(1)<<56)),4),
        (goodRecords.updated(3,goodRecords(3)|(BigInt(1)<<120)),4),
        (goodRecords.updated(6,stride(Seq(16,1,1),3)),4),
        (goodRecords.updated(7,base(0x4000,next=8)),9),
        (goodRecords.updated(7,base(0x2040,next=8)),9))
      for((r,code)<-cases){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);initialize(d);drive(d,recs=r) shouldBe (code,0)}
    }
  }
  it should "never publish successful completion on failed, short or mistagged owner writeback" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for((err,short,tag,expected)<-Seq((3,false,false,3),(0,true,false,7),(0,false,true,7))){
        d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);initialize(d)
        drive(d,doneError=err,shortWrite=short,wrongTag=tag) shouldBe (expected,1)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
        d.io.launch.valid.poke(true.B);d.clock.step(8);d.io.launch.ready.expect(false.B);d.io.resetRequired.expect(true.B)
      }
    }
  }
  it should "propagate real record-reader fetch errors and remain reset-required" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>initialize(d);drive(d,fetchError=true) shouldBe (3,0);d.io.resetRequired.expect(true.B)}
  }
  it should "reject writable command tables and overlapping regions at launch" in {
    test(new HostResidualCommands).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d);d.io.launch.bits.regions(0).write.poke(true.B);drive(d) shouldBe (5,0)
      d.io.result.ready.poke(true.B);d.clock.step();initialize(d)
      d.io.launch.bits.regions(1).base.poke(0x2000.U);drive(d) shouldBe (5,0)
    }
  }
}
