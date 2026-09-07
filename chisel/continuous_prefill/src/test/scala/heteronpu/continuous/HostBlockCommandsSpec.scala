// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}

/** Actual command/descriptor decoder DUT. Memory and owner completion are
  * controlled in this suite; numerical claims belong to host_block_commands.cpp.
  */
class HostBlockCommandsSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val dir=Paths.get(sys.env.getOrElse("OWNER_FIXTURE",throw new IllegalArgumentException("OWNER_FIXTURE required")))
  val manifest=ujson.read(Files.readString(dir.resolve("manifest.json")))
  def integer(k:String):BigInt=BigInt(manifest(k).num.toLong)
  def word(bytes:Array[Byte],i:Int):BigInt=BigInt(1,bytes.slice(16*i,16*i+16).reverse)
  val commandBytes=Files.readAllBytes(dir.resolve("host_commands.bin"))
  val descriptorBytes=Files.readAllBytes(dir.resolve("host_descriptors.bin"))
  val commands=(0 until integer("commands").toInt).map(word(commandBytes,_)).toVector
  val descriptors=(0 until integer("descriptors").toInt).map(word(descriptorBytes,_)).toVector
  def reset(d:HostBlockCommands):Unit={d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);initialize(d)}
  def initialize(d:HostBlockCommands):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    val l=d.io.launch.bits
    l.commandBase.poke(integer("commandBase").U);l.commandLimit.poke(integer("commandLimit").U);l.commands.poke(integer("commands").U)
    l.descriptorBase.poke(integer("descriptorBase").U);l.descriptorLimit.poke(integer("descriptorLimit").U);l.descriptors.poke(integer("descriptors").U);l.epoch.poke(7.U)
    val r=Seq((integer("base"),integer("metadataLimit"),true,false),(integer("metadataLimit"),integer("scratchBase"),true,false),(integer("scratchBase"),integer("limit"),true,true),(BigInt(0),BigInt(0),false,false))
    for((v,i)<-r.zipWithIndex){l.regions(i).base.poke(v._1.U);l.regions(i).limit.poke(v._2.U);l.regions(i).read.poke(v._3.B);l.regions(i).write.poke(v._4.B)}
  }
  def run(d:HostBlockCommands,cs:Vector[BigInt]=commands,ds:Vector[BigInt]=descriptors,
          failJob:Int = -1,doneError:Int=0,badTag:Boolean=false,short:Boolean=false,readError:Boolean=false):(Int,Int,Int)={
    d.io.launch.valid.poke(true.B);d.io.launch.ready.expect(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    var ticks=0;var jobs=0;var success=0;var memory=0;var completionError=false
    while(!d.io.result.valid.peek().litToBoolean && ticks<5000){
      if(d.io.memory.valid.peek().litToBoolean){
        val a=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.bits.write.expect(false.B)
        d.clock.step(3);d.io.memory.bits.address.expect(a.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val cm=a<integer("metadataLimit")&&a<integer("descriptorBase")
        val offset=((a-(if(cm)integer("commandBase") else integer("descriptorBase")))/16).toInt
        val table=if(cm)cs else ds
        val data=(0 until 4).map(j=>table.lift(offset+j).getOrElse(BigInt(0))<<(128*j)).reduce(_|_)
        d.clock.step(2);d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke(tag.U);d.io.response.bits.error.poke(readError.B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B);memory+=1
      }else if(d.io.job.valid.peek().litToBoolean){
        val pc=d.io.pc.peek().litValue.toInt;val tag=d.io.job.bits.tag.peek().litValue;val bytes=d.io.job.bits.writeBytes.peek().litValue
        val destination=BigInt(manifest("tensors")(manifest("schedule")(pc)("dst").str)("address").num.toLong)
        d.io.job.bits.dst.expect(destination.U);d.io.job.bits.m.expect(integer("tokens").U)
        if(pc%21==12){d.io.job.bits.kind.expect(QwenOwnerKind.Attention.U);success shouldBe pc-2}
        val saved=Seq(d.io.job.bits.a,d.io.job.bits.b,d.io.job.bits.dst,d.io.job.bits.tag,d.io.job.bits.m,d.io.job.bits.n,d.io.job.bits.k).map(x=>(x,x.peek().litValue))
        for(_<-0 until 5){d.io.completion.valid.expect(false.B);saved.foreach{case(x,v)=>x.expect(v.U)};d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B);jobs+=1
        for(_<-0 until 9){d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.done.bits.tag.poke((if(pc==failJob&&badTag)tag^1 else tag).U)
        d.io.done.bits.status.poke((if(pc==failJob)doneError else 0).U)
        d.io.done.bits.writeBytes.poke((if(pc==failJob&&short)bytes-64 else bytes).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
      }else if(d.io.completion.valid.peek().litToBoolean){
        val c=d.io.completion.bits.peek().litValue;val status=((c>>32)&255).toInt
        if(status==0){(c&((BigInt(1)<<29)-1)).toInt shouldBe success;((c>>40)&65535).toInt shouldBe success+1;success+=1}else completionError=true
        for(_<-0 until 4){d.io.job.valid.expect(false.B);d.io.completion.bits.expect(c.U);d.clock.step()}
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.result.bits.completed.expect(success.U);d.io.result.bits.epoch.expect(7.U)
    if(status==0){memory shouldBe (integer("commands")+integer("descriptors")).toInt;completionError shouldBe false}else{completionError shouldBe true;d.io.resetRequired.expect(true.B)}
    (status,jobs,success)
  }
  def dut=new HostBlockCommands(QwenBlockShape(64,128,2,1,32,1024,true))
  "HostBlockCommands" should "stay idle without Host launch, decode the complete supplied command graph and delay every completion until owner ACK" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>initialize(d);d.clock.step(30);d.io.memory.valid.expect(false.B);d.io.job.valid.expect(false.B);run(d) shouldBe (0,integer("commands").toInt/21*19,integer("commands").toInt)}
  }
  it should "reject an omitted Bias, wrong dependency and unknown opcode instead of running an implicit phase" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for((cs,prior)<-Seq((commands.updated(0,(commands(0)&~BigInt(255))|255),0),(commands.updated(2,commands(2)&~BigInt(255)),2),(commands.updated(1,(commands(1)&~(BigInt(65535)<<24))|(BigInt(99)<<24)),1))){reset(d);val r=run(d,cs);r._1 should not be 0;r._3 shouldBe prior}
    }
  }
  it should "reject unsupported SFU and Matrix policy fields before starting that owner" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val matrixRoot=((commands(1)>>56)&0xffffff).toInt
      val cases=Seq((descriptors.updated(3,descriptors(3)^(BigInt(1)<<56)),0),(descriptors.updated(matrixRoot+3,descriptors(matrixRoot+3)|(BigInt(1)<<117)),1))
      for((ds,prior)<-cases){reset(d);val r=run(d,ds=ds);r._1 should not be 0;r._3 shouldBe prior}
    }
  }
  it should "not publish a failed short or mistagged GEMM result or issue its consumer" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for((error,tag,short)<-Seq((3,false,false),(0,true,false),(0,false,true))){reset(d);val r=run(d,failJob=1,doneError=error,badTag=tag,short=short);r._1 should not be 0;r._2 shouldBe 2;r._3 shouldBe 1
        d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B);d.io.launch.valid.poke(true.B);d.clock.step(8);d.io.launch.ready.expect(false.B)}
    }
  }
  it should "validate the Softmax and PV group before any attention arithmetic or QK event" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      reset(d);val r=run(d,commands.updated(11,(commands(11)&~BigInt(255))|0x30));r._1 should not be 0;r._2 shouldBe 10;r._3 shouldBe 10
    }
  }
  it should "fail closed on metadata read errors without a payload owner" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>initialize(d);val r=run(d,readError=true);r._1 shouldBe 3;r._2 shouldBe 0;r._3 shouldBe 0}
  }
  it should "clear previous-request producer visibility without requiring reset" in {
    test(dut).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d)
      run(d) shouldBe (0,integer("commands").toInt/21*19,integer("commands").toInt)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
      initialize(d) // Host pins only. No reset and no poke of DUT internal state.
      // Try to consume the previous request's scratch n0 as the FIRST operation.
      // Set wait=0 so rejection must come from producer-lifetime protection,
      // not merely an unsignalled event. A new request cannot inherit n0.
      val stale=(commands(1)&~(BigInt(65535)<<24))
      val result=run(d,commands.updated(0,stale))
      result._1 shouldBe Status.Dependency;result._2 shouldBe 0;result._3 shouldBe 0
    }
  }

}
