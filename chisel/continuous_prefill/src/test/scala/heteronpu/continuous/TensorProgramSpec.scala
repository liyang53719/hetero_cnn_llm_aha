// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
class TensorProgramSpec extends AnyFlatSpec with ChiselScalatestTester {
  val c=ChainConfig(tileElements=32,tensorSlots=8,programDepth=8)
  def init(d:TensorProgram):Unit={
    d.io.regionWrite.valid.poke(false.B);d.io.tensorWrite.valid.poke(false.B);d.io.programWrite.valid.poke(false.B)
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)
    for((i,base)<-Seq(0->BigInt("100000000",16),1->BigInt("200000000",16))){
      d.io.regionWrite.bits.index.poke(i.U);d.io.regionWrite.bits.value.base.poke(base.U);d.io.regionWrite.bits.value.limit.poke((base+0x100000).U)
      d.io.regionWrite.bits.value.read.poke(true.B);d.io.regionWrite.bits.value.write.poke((i==1).B);d.io.regionWrite.valid.poke(true.B);d.clock.step()
    };d.io.regionWrite.valid.poke(false.B)
    for(i<-0 until 4){
      val t=d.io.tensorWrite.bits.value
      d.io.tensorWrite.bits.index.poke(i.U);t.base.poke((BigInt(if(i<2)"100000000" else "200000000",16)+(i%2)*0x1000).U)
      t.elementCount.poke(32.U);t.bf16.poke(false.B);t.region.poke((if(i<2)0 else 1).U);t.external.poke((i<2).B)
      d.io.tensorWrite.valid.poke(true.B);d.clock.step()
    };d.io.tensorWrite.valid.poke(false.B)
  }
  def word(d:TensorProgram,i:Int,a:Int,b:Int,dst:Int,av:Int=0,bv:Int=0):Unit={
    val x=d.io.programWrite.bits.value
    d.io.programWrite.bits.index.poke(i.U);x.op.poke(ElemOp.Add.U);x.a.poke(a.U);x.b.poke(b.U);x.dst.poke(dst.U)
    x.aVersion.poke(av.U);x.bVersion.poke(bv.U);x.dstVersion.poke(1.U)
    d.io.programWrite.valid.poke(true.B);d.clock.step();d.io.programWrite.valid.poke(false.B)
  }
  def start(d:TensorProgram,n:Int=1):Unit={d.io.launch.bits.commands.poke(n.U);d.io.launch.bits.epoch.poke(1.U);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)}
  def waitFor(d:TensorProgram,p: => Boolean):Unit={var n=0;while(!p&&n<30){d.clock.step();n+=1};assert(p)}
  def completion(d:TensorProgram,tag:BigInt,bytes:Int=128,status:Int=0):Unit={
    d.io.done.bits.tag.poke(tag.U);d.io.done.bits.status.poke(status.U);d.io.done.bits.elementCount.poke(32.U);d.io.done.bits.writeBytes.poke(bytes.U)
    d.io.done.valid.poke(true.B);d.clock.step();d.io.done.valid.poke(false.B)
  }
  it should "publish only matched writeback, block config while active, and feed consumer the producer address" in {
    test(new TensorProgram(c)){d=>init(d);word(d,0,0,1,2);word(d,1,2,1,3,av=1);start(d,2)
      waitFor(d,d.io.job.valid.peek().litToBoolean);val snapshot=d.io.job.bits.a.peek().litValue
      for(_<-0 until 5){d.io.job.bits.a.expect(snapshot.U);d.io.regionWrite.ready.expect(false.B);d.clock.step()}
      val tag=d.io.job.bits.tag.peek().litValue;d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B)
      for(_<-0 until 5){d.io.job.valid.expect(false.B);d.io.committed.expect(false.B);d.clock.step()}
      completion(d,tag);waitFor(d,d.io.job.valid.peek().litToBoolean)
      d.io.job.bits.a.expect(BigInt("200000000",16).U);val next=d.io.job.bits.tag.peek().litValue
      d.io.job.ready.poke(true.B);d.clock.step();completion(d,next)
      waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.bits.completed.expect(2.U);d.io.result.bits.status.expect(0.U)
      for(_<-0 until 5){d.io.result.valid.expect(true.B);d.io.result.bits.completed.expect(2.U);d.clock.step()}
    }
  }
  for((label,a,av,expect)<-Seq(("missing producer",2,1,6),("stale source version",0,1,6))){
    it should s"reject $label without issuing" in {test(new TensorProgram(c)){d=>init(d);word(d,0,a,1,3,av=av);start(d);waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.bits.status.expect(expect.U);d.io.job.valid.expect(false.B)}}
  }
  for((label,tagDelta,bytes,error)<-Seq(("bad tag",1,128,0),("short write",0,64,0),("memory failure",0,128,3))){
    it should s"not publish after $label" in {test(new TensorProgram(c)){d=>init(d);word(d,0,0,1,2);word(d,1,2,1,3,av=1);start(d,2)
      waitFor(d,d.io.job.valid.peek().litToBoolean);val tag=d.io.job.bits.tag.peek().litValue
      d.io.job.ready.poke(true.B);d.clock.step();completion(d,tag+tagDelta,bytes,error)
      waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.bits.completed.expect(0.U);d.io.resetRequired.expect(true.B)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.launch.ready.expect(false.B);d.io.job.valid.expect(false.B)
    }}
  }
  it should "reject source/destination alias even under different tensor IDs" in {test(new TensorProgram(c)){d=>init(d)
    d.io.tensorWrite.bits.index.poke(3.U);d.io.tensorWrite.bits.value.base.poke(BigInt("100000000",16).U)
    d.io.tensorWrite.bits.value.elementCount.poke(32.U);d.io.tensorWrite.bits.value.bf16.poke(false.B);d.io.tensorWrite.bits.value.region.poke(0.U);d.io.tensorWrite.bits.value.external.poke(false.B)
    d.io.tensorWrite.valid.poke(true.B);d.clock.step();d.io.tensorWrite.valid.poke(false.B);word(d,0,0,1,3);start(d)
    waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.bits.status.expect(5.U)
  }}
  it should "invalidate non-external generations between request epochs" in {test(new TensorProgram(c)){d=>init(d);word(d,0,0,1,2);start(d)
    waitFor(d,d.io.job.valid.peek().litToBoolean);val tag=d.io.job.bits.tag.peek().litValue;d.io.job.ready.poke(true.B);d.clock.step();completion(d,tag)
    waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.ready.poke(true.B);d.clock.step();word(d,0,2,1,3,av=1)
    d.io.launch.bits.commands.poke(1.U);d.io.launch.bits.epoch.poke(2.U);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    waitFor(d,d.io.result.valid.peek().litToBoolean);d.io.result.bits.status.expect(6.U)
  }}
}
