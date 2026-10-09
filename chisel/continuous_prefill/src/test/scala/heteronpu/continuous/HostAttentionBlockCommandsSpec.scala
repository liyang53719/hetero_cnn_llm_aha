// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Path, Paths}
import scala.sys.process._

/** CONTROL_ONLY: mocked owner receipts; no owner arithmetic or payload DMA. */
class AttentionBlockFrontendControlHarness(val blockEnabled:Boolean=true) extends HostBlockCommands(
  QwenBlockShape.qwen35Qkv(),eventSlots=64,maxCommands=22,bf16Weights=true,
  bf16Qkv=true,bf16QkNormRope=true,bf16AttentionCore=true,bf16AttentionBlock=blockEnabled) {
  val checkpointValid=IO(Output(Bool()));checkpointValid:=attentionCacheValid
  val checkpointLength=IO(Output(UInt(32.W)));checkpointLength:=attentionLength
  val checkpointGeneration=IO(Output(UInt(32.W)));checkpointGeneration:=attentionGeneration
  val checkpointCache=IO(Output(new DecodedTensor));checkpointCache:=attentionCache
  val checkpointOutput=IO(Output(new DecodedTensor));checkpointOutput:=attentionContext
  val checkpointParameters=IO(Output(Vec(attentionParameterCount,new DecodedTensor)));checkpointParameters:=attentionParameters
  val stagedAppend=IO(Output(Bool()));stagedAppend:=pendingAttentionValid
  val stagedGqa=IO(Output(Bool()));stagedGqa:=pendingGqaValid
}

class HostAttentionBlockCommandsSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val cb=BigInt(0x1000);val db=BigInt(0x3000);val epoch=11
  lazy val root:Path=sys.env.get("ATTENTION_BLOCK_REPO").map(Paths.get(_)).getOrElse(
    Iterator.iterate(Paths.get("").toAbsolutePath)(_.getParent).takeWhile(_!=null)
      .find(p=>Files.isRegularFile(p.resolve("chisel/continuous_prefill/tests/host_attention_block_control_vectors.py")))
      .getOrElse(throw new IllegalArgumentException("ATTENTION_BLOCK_REPO required")))
  def program(old:Int=0,generation:Int=0,mode:String="block"):ujson.Value=ujson.read(
    Seq(sys.env.getOrElse("ATTENTION_BLOCK_PYTHON","python3"),
      root.resolve("chisel/continuous_prefill/tests/host_attention_block_control_vectors.py").toString,old.toString,generation.toString,mode).!!)
  case class Snapshot(valid:Boolean,length:BigInt,generation:BigInt,cache:DecodedTensor,output:DecodedTensor,parameters:Vector[DecodedTensor])
  def snapshot(d:AttentionBlockFrontendControlHarness):Snapshot=Snapshot(d.checkpointValid.peek().litToBoolean,
    d.checkpointLength.peek().litValue,d.checkpointGeneration.peek().litValue,d.checkpointCache.peek(),d.checkpointOutput.peek(),
    (0 until d.attentionParameterCount).map(i=>d.checkpointParameters(i).peek()).toVector)
  def unchanged(d:AttentionBlockFrontendControlHarness,s:Snapshot):Unit={
    d.checkpointValid.expect(s.valid.B);d.checkpointLength.expect(s.length.U);d.checkpointGeneration.expect(s.generation.U)
    d.checkpointCache.expect(s.cache);d.checkpointOutput.expect(s.output)
    s.parameters.zipWithIndex.foreach{case(t,i)=>d.checkpointParameters(i).expect(t)}
  }
  case class Result(status:Int,jobs:Int,completed:Int,failedPc:Int)
  def run(d:AttentionBlockFrontendControlHarness,p:ujson.Value,reset:Boolean=true,faultPc:Int = -1):Result={
    val commands=p("commands").arr.map(v=>BigInt(v.str)).toVector
    val records=p("records").arr.map(v=>BigInt(v.str)).toVector
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);d.io.response.bits.error.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U)
    d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)}
    val l=d.io.launch.bits
    l.commandBase.poke(cb.U);l.commandLimit.poke((cb+0x1000).U);l.commands.poke(commands.size.U)
    l.descriptorBase.poke(db.U);l.descriptorLimit.poke((db+0x2000).U);l.descriptors.poke(records.size.U);l.epoch.poke(epoch.U)
    val rawEnd=if(d.blockEnabled)0x2800800 else 0x2801000
    val regions=Seq((0x1000,0x8000,true,false),(0x100000,0x2800000,true,false),
      (0x2800000,rawEnd,true,false),(rawEnd,0x3200000,true,true))
    for((r,i)<-regions.zipWithIndex){l.regions(i).base.poke(r._1.U);l.regions(i).limit.poke(r._2.U);l.regions(i).read.poke(r._3.B);l.regions(i).write.poke(r._4.B)}
    var saved=snapshot(d);var jobs=0;var completed=0;var ticks=0;var written=BigInt(0)
    d.io.launch.ready.expect(true.B);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    // Accepted launch context must not follow subsequently changed host pins.
    l.commandBase.poke(0.U);l.descriptorBase.poke(0.U);l.commands.poke(1.U);l.epoch.poke(99.U)
    while(!d.io.result.valid.peek().litToBoolean && ticks<20000){
      unchanged(d,saved)
      if(d.io.memory.valid.peek().litToBoolean){
        val address=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        assert(address>=cb && address<db+0x2000,"CONTROL_ONLY frontend requested payload DDR")
        d.io.memory.bits.write.expect(false.B);d.io.memory.bits.mask.expect(0.U)
        d.clock.step(2);unchanged(d,saved);d.io.memory.bits.address.expect(address.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val isCommand=address<db;val table=if(isCommand)commands else records
        val offset=((address-(if(isCommand)cb else db))/16).toInt
        val data=(0 until 4).map(i=>table.lift(offset+i).getOrElse(BigInt(0))<<(128*i)).reduce(_|_)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke(tag.U);d.io.response.valid.poke(true.B)
        d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        val expected=p("jobs").arr(jobs);val pc=expected("pc").num.toInt;val tag=(BigInt(epoch)<<16)|pc
        def value(name:String):BigInt=expected.obj.get(name).map(v=>BigInt(v.num.toLong)).getOrElse(BigInt(0))
        val j=d.io.job.bits
        d.io.pc.expect(pc.U)
        for((name,actual)<-Seq("kind"->j.kind,"a"->j.a,"b"->j.b,"c"->j.c,"dst"->j.dst,"m"->j.m,"n"->j.n,"k"->j.k,
          "writeBytes"->j.writeBytes,"qkRole"->j.qkRole,"qkPositionBase"->j.qkPositionBase,"qkTrigTokens"->j.qkTrigTokens,
          "cacheCapacity"->j.cacheCapacity,"cacheLength"->j.cacheLength,"expectedCacheLength"->j.expectedCacheLength,
          "queryStart"->j.queryStart,"expectedGeneration"->j.expectedGeneration,"currentGeneration"->j.currentGeneration,
          "gdnElementwiseOp"->j.gdnElementwiseOp))actual.expect(value(name).U)
        j.tag.expect(tag.U);j.cold.expect(expected.obj.get("cold").exists(_.bool).B)
        j.activationBf16.expect(true.B);j.weightBf16.expect(true.B);j.outputBf16.expect(true.B)
        if(pc==11 && d.blockEnabled){completed shouldBe 9;d.stagedAppend.expect(true.B);d.stagedGqa.expect(false.B)}
        if(pc==12 && d.blockEnabled){
          // Independent role assertion: SigmoidMul consumes gate first.
          j.a.expect(p("gate").num.toLong.U);j.b.expect(p("context").num.toLong.U);j.gdnElementwiseOp.expect(2.U)
        }
        val captured=j.peek()
        for(_<-0 until 3){unchanged(d,saved);j.expect(captured);d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B)
        d.io.done.bits.tag.poke(tag.U);d.io.done.bits.writeBytes.poke(value("writeBytes").U)
        for(_<-0 until 3){unchanged(d,saved);d.io.completion.valid.expect(false.B);d.clock.step()}
        val failed=pc==faultPc
        d.io.done.bits.status.poke((if(failed)Status.Memory else Status.Ok).U)
        d.io.done.bits.writeBytes.poke((value("writeBytes")-(if(failed)64 else 0)).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
        if(!failed)written+=value("writeBytes")
        jobs+=1
      }else if(d.io.completion.valid.peek().litToBoolean){
        val word=d.io.completion.bits.peek().litValue;val pc=(word&((BigInt(1)<<29)-1)).toInt
        val ok=((word>>32)&255)==Status.Ok;val fence=ok && pc==commands.size-1
        if(ok)pc shouldBe completed
        if(fence){
          jobs shouldBe (if(d.blockEnabled)19 else 9)
          completed shouldBe commands.size-1;d.stagedAppend.expect(true.B);d.stagedGqa.expect(true.B)
        }
        // Full-block commit must remain unchanged while its terminal completion
        // is backpressured, even after every physical producer ACK succeeded.
        for(_<-0 until (if(fence)16 else 2)){
          unchanged(d,saved);d.io.completion.bits.expect(word.U);d.io.job.valid.expect(false.B);d.clock.step()
        }
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
        if(ok)completed+=1
        if(fence){
          d.checkpointValid.expect(true.B);d.checkpointLength.expect((p("old").num.toInt+1).U)
          d.checkpointGeneration.expect((p("generation").num.toInt+1).U)
          d.checkpointCache.address.expect(p("cache").num.toLong.U)
          d.checkpointOutput.address.expect(p("final").num.toLong.U)
          d.checkpointOutput.dims(0).expect(1.U);d.checkpointOutput.dims(1).expect(p("finalWidth").num.toInt.U)
          d.checkpointOutput.payloadBytes.expect((p("finalWidth").num.toInt*2).U)
          for((v,i)<-p("parameters").arr.zipWithIndex)d.checkpointParameters(i).address.expect(v.num.toLong.U)
          d.stagedAppend.expect(false.B);d.stagedGqa.expect(false.B);saved=snapshot(d)
        }
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.completed.expect(completed.U);d.io.issuedJobs.expect(jobs.U)
    d.io.writeBytes.expect(written.U);d.io.result.bits.epoch.expect(epoch.U)
    val result=Result(d.io.result.bits.status.peek().litValue.toInt,jobs,completed,d.io.result.bits.failedPc.peek().litValue.toInt)
    unchanged(d,saved)
    d.io.resetRequired.expect((result.status!=Status.Ok && result.status!=Status.Bounds).B)
    d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
    unchanged(d,saved);result
  }

  "Attention block CONTROL_ONLY" should "commit only its terminal fence and retain the checkpoint on final-residual failure" in {
    test(new AttentionBlockFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val cold=run(d,program());cold.status shouldBe Status.Ok;cold.jobs shouldBe 19;cold.completed shouldBe 22
      val carry=run(d,program(1,1),reset=false);carry.status shouldBe Status.Ok;carry.completed shouldBe 22
      val saved=snapshot(d)
      val failed=run(d,program(2,2),reset=false,faultPc=20)
      failed shouldBe Result(Status.Memory,19,20,20);unchanged(d,saved)
      d.io.launch.ready.expect(false.B)
    }
  }
  it should "reject readonly raw hidden as a substitute for the acknowledged input RMS output" in {
    test(new AttentionBlockFrontendControlHarness).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      run(d,program(mode="preloaded")) shouldBe Result(Status.Dependency,1,1,1)
      d.checkpointValid.expect(false.B);d.checkpointGeneration.expect(0.U)
      // Equal tensor shapes must not make reversed sigmoid operands legal.
      run(d,program(mode="reversed_sigmoid")) shouldBe Result(Status.Dependency,10,12,12)
      d.checkpointValid.expect(false.B);d.checkpointGeneration.expect(0.U)
    }
  }
  it should "retain the default-off twelve-command v2 contract" in {
    test(new AttentionBlockFrontendControlHarness(blockEnabled=false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val old=run(d,program(mode="core"));old.status shouldBe Status.Ok;old.jobs shouldBe 9;old.completed shouldBe 12
      val saved=snapshot(d)
      val rejected=run(d,program(),reset=false);rejected.status shouldBe Status.Bounds;rejected.jobs shouldBe 0;rejected.completed shouldBe 0
      unchanged(d,saved)
    }
  }
}
