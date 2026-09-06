// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

object DescriptorFixture {
  val Null=BigInt(0xffffff)
  def rec(kind:Int,next:BigInt,payload:BigInt):BigInt=BigInt(kind)|(next<<32)|(payload<<56)
  def base(addr:BigInt,dtype:Int=7,rank:Int=2,next:BigInt=1):BigInt=rec(1,next,(addr&((BigInt(1)<<48)-1))|(BigInt(dtype)<<52)|(BigInt(rank)<<60)|((addr>>48)<<64))
  def shape(d:Seq[Int],next:BigInt=2):BigInt=rec(2,next,d.zipWithIndex.map{case(n,i)=>BigInt(n)<<(18*i)}.reduce(_|_))
  def stride(d:Seq[Int],next:BigInt=Null):BigInt=rec(3,next,d.zipWithIndex.map{case(n,i)=>(BigInt(n)&0xffffff)<<(24*i)}.reduce(_|_))
}
class TypedTensorReaderSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  import DescriptorFixture._
  def run(d:TypedTensorReader,records:Map[Int,BigInt],write:Boolean=false,readPermission:Boolean=true,writePermission:Boolean=true,
          regionLimit:BigInt=0x10000,recordError:Boolean=false,tagError:Boolean=false):Int={
    d.io.request.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.record.ready.poke(false.B);d.io.recordResult.valid.poke(false.B)
    d.io.recordResult.bits.data.poke(0.U);d.io.recordResult.bits.requestTag.poke(0.U);d.io.recordResult.bits.status.poke(0.U)
    d.io.request.bits.tableBase.poke(0x1000.U);d.io.request.bits.tableLimit.poke(0x2000.U);d.io.request.bits.entryCount.poke(256.U);d.io.request.bits.root.poke(0.U)
    d.io.request.bits.writeAccess.poke(write.B)
    for(i<-0 until 4){val r=d.io.request.bits.regions(i);r.base.poke(0.U);r.limit.poke((if(i==0)regionLimit else BigInt(0)).U);r.read.poke((i==0&&readPermission).B);r.write.poke((i==0&&writePermission).B)}
    d.io.request.valid.poke(true.B);d.clock.step();d.io.request.valid.poke(false.B)
    var steps=0
    while(!d.io.result.valid.peek().litToBoolean && steps<40){
      if(d.io.record.valid.peek().litToBoolean){
        val idx=d.io.record.bits.index.peek().litValue.toInt;val tag=d.io.record.bits.requestTag.peek().litValue
        d.clock.step(2);d.io.record.ready.poke(true.B);d.clock.step();d.io.record.ready.poke(false.B)
        d.io.recordResult.bits.data.poke(records.getOrElse(idx,BigInt(0)).U)
        d.io.recordResult.bits.requestTag.poke((if(tagError)tag^1 else tag).U)
        d.io.recordResult.bits.status.poke((if(recordError || !records.contains(idx))3 else 0).U)
        d.io.recordResult.valid.poke(true.B);d.io.recordResult.ready.expect(true.B);d.clock.step();d.io.recordResult.valid.poke(false.B)
      }else d.clock.step()
      steps+=1
    }
    d.io.result.valid.expect(true.B);val status=d.io.result.bits.status.peek().litValue.toInt
    d.clock.step(4);d.io.result.bits.status.expect(status.U)
    status
  }
  "TypedTensorReader" should "decode public FP32 and BF16 tensors and preserve the linked policy index" in {
    test(new TypedTensorReader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(dtype<-Seq(5,7)){
        val r=Map(0->base(0x4000,dtype),1->shape(Seq(2,16,1,1)),2->stride(Seq(16,1,1),17))
        run(d,r) shouldBe 0
        d.io.result.bits.tensor.elementCount.expect(32.U);d.io.result.bits.tensor.payloadBytes.expect((if(dtype==5)64 else 128).U)
        d.io.result.bits.tensor.dtype.expect(dtype.U);d.io.result.bits.tensor.tail.expect(17.U)
        d.io.result.ready.poke(true.B);d.clock.step()
      }
    }
  }
  it should "reject malformed, unsupported, cyclic and incomplete descriptor prefixes" in {
    test(new TypedTensorReader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val good=Map(0->base(0x4000),1->shape(Seq(2,16,1,1)),2->stride(Seq(16,1,1)))
      val cases=Seq(
        (good.updated(0,base(0x4000)|0x100),2),
        (good.updated(0,base(0x4000,dtype=6)),4),
        (good.updated(0,base(0x4000,rank=0)),4),
        (good.updated(0,base(0x4000)|(BigInt(1)<<104)),4),
        (good.updated(0,base(0x4000,next=0)),2),
        (good.updated(1,shape(Seq(2,16,1,1),0)),2),
        (good.updated(1,shape(Seq(2,16,1,1),0xffffff)),3),
        (good.updated(1,shape(Seq(2,0,1,1))),5),
        (good.updated(1,shape(Seq(2,16,2,1))),5),
        (good.updated(2,stride(Seq(-16,1,1))),4),
        (good.updated(2,stride(Seq(17,1,1))),4),
        (good.updated(0,base(0x4001)),5))
      for((r,expected)<-cases){run(d,r) shouldBe expected;d.io.result.ready.poke(true.B);d.clock.step()}
    }
  }
  it should "bound the whole padded beat range and enforce read versus write permissions" in {
    test(new TypedTensorReader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val r=Map(0->base(0x4000,rank=1),1->shape(Seq(1,1,1,1)),2->stride(Seq(1,1,1)))
      run(d,r,regionLimit=0x4004) shouldBe 9;d.io.result.ready.poke(true.B);d.clock.step()
      run(d,r,write=true,writePermission=false) shouldBe 9;d.io.result.ready.poke(true.B);d.clock.step()
      run(d,r,readPermission=false) shouldBe 9;d.io.result.ready.poke(true.B);d.clock.step()
      run(d,r,regionLimit=0x4040) shouldBe 0;d.io.result.bits.tensor.paddedEnd.expect(0x4040.U)
    }
  }
  it should "reject product overflow and response identity failures" in {
    test(new TypedTensorReader).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val huge=Map(0->base(0x4000,rank=4),1->shape(Seq(262143,262143,262143,262143)),2->stride(Seq(1,1,1)))
      run(d,huge) shouldBe 5;d.io.result.ready.poke(true.B);d.clock.step()
      val r=Map(0->base(0x4000),1->shape(Seq(2,16,1,1)),2->stride(Seq(16,1,1)))
      run(d,r,recordError=true) shouldBe 3;d.io.result.ready.poke(true.B);d.clock.step()
      run(d,r,tagError=true) shouldBe 7
    }
  }
}
