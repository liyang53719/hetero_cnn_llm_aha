// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Production Host frontend CONTROL ONLY: the owner is a test double, and
  * metadata is served by the test. These tests establish admission, binding,
  * completion and publication, not Dense arithmetic, payload DMA or ACKs. */
class HostBlockCommandsBf16QkvSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val cb=BigInt(0x1000);val db=BigInt(0x2000);val actBase=BigInt(0x10000)
  val weights=Vector(BigInt(0x100000),BigInt(0x900000),BigInt(0xa00000))
  val outputs=Vector(BigInt(0x1000000),BigInt(0x1200000),BigInt(0x1400000))
  val roEnd=BigInt(0xc00000);val rwEnd=BigInt(0x2000000);val nil=BigInt(0xffffff)
  case class Expected(a:BigInt,b:BigInt,dst:BigInt,m:Int,n:Int) { val bytes:BigInt=BigInt(m)*n*2 }
  case class Program(commands:Vector[BigInt],records:Vector[BigInt],expected:Vector[Expected])
  def rec(kind:Int,next:BigInt,payload:BigInt):BigInt=BigInt(kind)|(next<<32)|(payload<<56)
  def tensor(address:BigInt):BigInt=(address&((BigInt(1)<<48)-1))|(BigInt(0x2050)<<48)|((address>>48)<<64)
  def shape(m:Int,n:Int):BigInt=BigInt(m)|(BigInt(n)<<18)|(BigInt(1)<<36)|(BigInt(1)<<54)
  def field(word:BigInt,lo:Int,width:Int,value:BigInt):BigInt=(word&~(((BigInt(1)<<width)-1)<<lo))|(value<<lo)
  def binding(role:Int=0,m:Int=8,base:Int=2,count:Int=4,act:BigInt=actBase,out:BigInt=outputs(0),
              start:Int=0,wait:Int=0,signal:Int=1):Program={
    val n=if(role==0)4096 else 512;val weight=weights(math.min(role,2))
    var ds=Vector.fill(21)(BigInt(0))
    for((offset,rows,cols,address)<-Seq((0,m,1024,act),(15,1024,n,weight),(18,m,n,out))){
      ds=ds.updated(offset,rec(1,start+offset+1,tensor(address)))
        .updated(offset+1,rec(2,start+offset+2,shape(rows,cols)))
        .updated(offset+2,rec(3,if(offset==0)BigInt(start+3)else nil,BigInt(cols)|(BigInt(1)<<24)|(BigInt(1)<<48)))
    }
    ds=ds.updated(3,rec(0x10,start+4,BigInt(m)|(BigInt(n)<<16)|(BigInt(1024)<<32)))
      .updated(4,rec(0x12,start+5,BigInt("004000040020ffffff",16)))
      .updated(5,rec(0x1a,start+6,BigInt(2)|(BigInt(role)<<8)|(BigInt(3)<<10)|(BigInt(base)<<12)|(BigInt(count)<<44)))
    for(i<-0 until 9)ds=ds.updated(6+i,rec(0x1b,if(i==8)nil else BigInt(start+7+i),BigInt(i)<<56))
    val cmd=BigInt(0x220)|(BigInt(wait)<<24)|(BigInt(signal)<<40)|(BigInt(start)<<56)|(BigInt(start+15)<<80)|(BigInt(start+18)<<104)
    Program(Vector(cmd),ds,Vector(Expected(act+base*2048,weight,out+BigInt(base)*n*2,count,n)))
  }
  def combine(ps:Program*):Program=Program(ps.toVector.flatMap(_.commands),ps.toVector.flatMap(_.records),ps.toVector.flatMap(_.expected))
  def edit(p:Program,index:Int,lo:Int,width:Int,value:BigInt):Program=p.copy(records=p.records.updated(index,field(p.records(index),lo,width,value)))
  def initialize(d:HostBlockCommands,p:Program):Unit={
    d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    val l=d.io.launch.bits;l.commandBase.poke(cb.U);l.commandLimit.poke((cb+0x1000).U);l.commands.poke(p.commands.size.U)
    l.descriptorBase.poke(db.U);l.descriptorLimit.poke((db+0x2000).U);l.descriptors.poke(p.records.size.U);l.epoch.poke(7.U)
    for((r,i)<-Seq((cb,BigInt(0x4000),true,false),(actBase,roEnd,true,false),
                  (outputs(0),rwEnd,true,true),(BigInt(0),BigInt(0),false,false)).zipWithIndex){
      l.regions(i).base.poke(r._1.U);l.regions(i).limit.poke(r._2.U);l.regions(i).read.poke(r._3.B);l.regions(i).write.poke(r._4.B)
    }
  }
  def run(d:HostBlockCommands,p:Program,doneFault:Int=0,readFault:Int=0,mutatePins:Boolean=false):(Int,Int,Int)={
    initialize(d,p);d.io.launch.valid.poke(true.B);d.io.launch.ready.expect(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    if(mutatePins){d.io.launch.bits.commandBase.poke(0.U);d.io.launch.bits.epoch.poke(99.U);d.io.launch.bits.regions(2).write.poke(false.B)}
    var jobs=0;var completions=0;var acceptedCompletions=0;var ticks=0;var written=BigInt(0)
    while(!d.io.result.valid.peek().litToBoolean && ticks<3000){
      if(d.io.memory.valid.peek().litToBoolean){
        val addr=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        // A frontend-only DUT may read tables, never payload memory.
        assert((addr>=cb && addr<cb+0x1000)||(addr>=db && addr<db+0x2000))
        d.io.memory.bits.write.expect(false.B);d.clock.step(3);d.io.memory.bits.address.expect(addr.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val table=if(addr<db)p.commands else p.records;val off=((addr-(if(addr<db)cb else db))/16).toInt
        val data=(0 until 4).map(i=>table.lift(off+i).getOrElse(BigInt(0))<<(128*i)).reduce(_|_)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke((if(readFault==2)tag^1 else tag).U);d.io.response.bits.error.poke((readFault==1).B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        val e=p.expected(jobs);val tag=BigInt(7<<16)|jobs
        d.io.job.bits.kind.expect(QwenOwnerKind.Dense.U);d.io.job.bits.a.expect(e.a.U);d.io.job.bits.b.expect(e.b.U);d.io.job.bits.dst.expect(e.dst.U)
        d.io.job.bits.c.expect(0.U);d.io.job.bits.tag.expect(tag.U);d.io.job.bits.m.expect(e.m.U);d.io.job.bits.n.expect(e.n.U);d.io.job.bits.k.expect(1024.U)
        d.io.job.bits.activationBf16.expect(true.B);d.io.job.bits.weightBf16.expect(true.B);d.io.job.bits.outputBf16.expect(true.B)
        d.io.job.bits.writeBytes.expect(e.bytes.U)
        val saved=Seq(d.io.job.bits.a,d.io.job.bits.b,d.io.job.bits.c,d.io.job.bits.dst,d.io.job.bits.tag,d.io.job.bits.m,
          d.io.job.bits.n,d.io.job.bits.k,d.io.job.bits.kind,d.io.job.bits.writeBytes).map(x=>(x,x.peek().litValue))
        for(_<-0 until 5){d.io.completion.valid.expect(false.B);saved.foreach{case(x,v)=>x.expect(v.U)};d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B);jobs+=1
        // Stand-in for an owner that has not finished; no publication or next
        // descriptor fetch can occur while the owner holds its result back.
        for(_<-0 until 7){d.io.completion.valid.expect(false.B);d.io.job.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
        d.io.done.bits.tag.poke((if(doneFault==2)tag^1 else tag).U);d.io.done.bits.status.poke((if(doneFault==1)Status.Memory else 0).U)
        val reported=e.bytes+(if(doneFault==3)-64 else if(doneFault==4)64 else 0)
        d.io.done.bits.writeBytes.poke(reported.U);d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
      }else if(d.io.completion.valid.peek().litToBoolean){
        val c=d.io.completion.bits.peek().litValue;val command=p.commands(acceptedCompletions)
        (c&((BigInt(1)<<29)-1)) shouldBe BigInt(acceptedCompletions)
        // A failed first metadata read has not decoded any command identity.
        ((c>>29)&7) shouldBe (if(readFault!=0)BigInt(0)else (command>>8)&7)
        (c>>40) shouldBe (if(readFault!=0)BigInt(0)else (command>>40)&65535)
        for(_<-0 until 4){d.io.job.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.io.completion.bits.expect(c.U);d.clock.step()}
        if(((c>>32)&255)==0){written+=p.expected(acceptedCompletions).bytes;completions+=1}
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B);acceptedCompletions+=1
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.epoch.expect(7.U);d.io.result.bits.completed.expect(completions.U)
    val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.issuedJobs.expect(jobs.U);d.io.writeBytes.expect(written.U)
    d.io.resetRequired.expect((status!=0).B)
    for(_<-0 until 3){d.io.result.bits.status.expect(status.U);d.io.result.bits.completed.expect(completions.U);d.io.job.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
    d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B);d.io.launch.ready.expect((status==0).B)
    (status,jobs,completions)
  }
  def dut(enabled:Boolean=true)=new HostBlockCommands(QwenBlockShape.qwen35Qkv(),bf16Weights=true,bf16Qkv=enabled)

  "Host native BF16 QKV control" should "bind all complete projection widths and mixed command tags with nonzero windows" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(role<-0 to 2;(m,base,count)<-Seq((1,0,1),(16,0,16),(128,127,1),(128,0,128),(128,47,81)))
        withClue(s"role=$role M=$m base=$base count=$count: "){run(d,binding(role,m,base,count),mutatePins=true) shouldBe (0,1,1)}
      val p=combine((0 to 2).map(r=>binding(r,128,17,16,out=outputs(r),start=r*21,wait=r,signal=r+1)):_*)
      run(d,p,mutatePins=true) shouldBe (0,3,3)
    }
  }
  it should "publish exactly Q or KV active bytes only after matching owner result and completion acceptance" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(role<-0 to 2){
        val first=binding(role)
        // Deliberate shape reinterpretation isolates the contiguous publication
        // contract; no inference is made about a real network successor.
        val rows=if(role==0)32 else 4;val firstLive=if(role==0)8 else 1;val afterLive=if(role==0)24 else 3
        val exact=combine(first,binding(1,rows,firstLive,afterLive-firstLive,act=outputs(0),out=outputs(1),start=21,wait=1,signal=2))
        run(d,exact) shouldBe (0,2,2)
        for(base<-Seq(firstLive-1,afterLive)){
          val p=combine(first,binding(1,rows,base,1,act=outputs(0),out=outputs(1),start=21,wait=1,signal=2))
          run(d,p) shouldBe (Status.Dependency,1,1)
        }
        run(d,combine(first,binding(role,8,0,2,start=21,wait=1,signal=2))) shouldBe (0,2,2)
        run(d,combine(first,binding(role,8,6,2,start=21,wait=1,signal=2))) shouldBe (0,2,2)
        run(d,combine(first,binding(role,8,3,2,start=21,wait=1,signal=2))) shouldBe (Status.Permission,1,1)
        // Exact bytes include both the Q and gate portions of all eight heads.
        for(fault<-1 to 4)run(d,exact,doneFault=fault) shouldBe (if(fault==1)Status.Memory else Status.Protocol,1,0)
      }
      for(fault<-1 to 2){val r=run(d,binding(),readFault=fault);r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}
      // Every run resets; a valid job after a poisoned run must work again.
      run(d,binding()) shouldBe (0,1,1)
    }
  }
  it should "reject malformed policies shapes storage flags ranges aliases and all nonprojection commands before owner issue" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val p=binding();val ds=p.records
      val edits=Seq(
        (5,64,2,BigInt(3)),(5,56,8,BigInt(1)),(5,56,8,BigInt(3)),(5,66,2,BigInt(0)),
        (5,108,8,BigInt(0xc1)),(5,127,1,BigInt(1)),(5,68,32,BigInt("ffffffff",16)),(5,100,8,BigInt(0)),(5,100,8,BigInt(129)),
        (5,32,24,BigInt(5)),(8,32,24,BigInt(6)),(14,32,24,BigInt(15)),(4,32,24,nil),(7,32,24,nil),(3,32,24,BigInt(99)),
        (6,56,56,BigInt(64)),(6,120,8,BigInt(1)),(7,112,8,BigInt(8)),
        (2,32,24,BigInt(0)),(1,32,24,BigInt(1)),(2,8,24,BigInt(1)),(17,32,24,BigInt(5)),(20,32,24,BigInt(5)),
        (0,56,48,actBase+2),(15,56,48,weights(0)+2),(18,56,48,outputs(0)+2),
        (1,56,18,BigInt(129)),(1,74,18,BigInt(512)),(16,74,18,BigInt(512)),(19,74,18,BigInt(512)),
        (3,72,16,BigInt(512)),(3,88,24,BigInt(512)),(3,115,1,BigInt(1)),(4,82,1,BigInt(1)),
        (0,108,4,BigInt(7)),(15,108,4,BigInt(7)),(18,108,4,BigInt(7)),(0,112,4,BigInt(1)),(0,104,4,BigInt(1)),
        (2,56,24,BigInt(2048)),(17,56,24,BigInt(8192)),(20,56,24,BigInt(8192)),
        // Allocation checks cover inactive suffixes, not only the active window.
        (0,56,48,roEnd-64),(15,56,48,roEnd-64),(18,56,48,rwEnd-64),
        (18,56,48,actBase),(0,56,48,outputs(0)),(15,56,48,outputs(0)),
        (0,56,48,(BigInt(1)<<48)-64),(0,120,8,BigInt(255)))
      for((i,lo,width,value)<-edits){val changed=edit(p,i,lo,width,value)
        withClue(s"record=$i bit=$lo value=$value: "){val r=run(d,changed);r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}}
      // Cross-root repeated prefixes are rejected even if shape and permissions
      // could otherwise match a projection.
      for((lo,width,value)<-Seq((0,8,BigInt(0x23)),(0,8,BigInt(0x24)),(0,8,BigInt(0x30)),(0,8,BigInt(0x32)),
          (0,8,BigInt(0x33)),(0,8,BigInt(0x34)),(0,8,BigInt(0x35)),(0,8,BigInt(0x41)),(0,8,BigInt(0xff)),
          (8,3,BigInt(3)),(11,13,BigInt(1)),(80,24,BigInt(0)),(40,16,BigInt(0)),(24,16,BigInt(2)))){
        val r=run(d,p.copy(commands=Vector(field(p.commands.head,lo,width,value))));r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0
      }
      // Version-2 Q shape cannot be relabeled K/V or vice versa.
      for(role<-1 to 2){val r=run(d,edit(p,5,64,2,role));r._1 should not be 0;r._2 shouldBe 0}
      val k=binding(1);val wrongQ=run(d,edit(k,5,64,2,0));wrongQ._1 should not be 0;wrongQ._2 shouldBe 0
    }
  }
  it should "remain disabled unless the distinct QKV feature is explicitly enabled" in {
    test(dut(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(role<-0 to 2){val r=run(d,binding(role));r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}
    }
    val v=QwenBlockShape.qwen35V();v.qwen35VOnly shouldBe true;v.qwen35QkvOnly shouldBe false
    val s=QwenBlockShape.qwen35Qkv();s.qwen35VOnly shouldBe false;s.qwen35QkvOnly shouldBe true
    s.hidden shouldBe 1024;s.packedQ shouldBe 4096;s.kv shouldBe 512;s.maxTokens shouldBe 128
    QwenBlockShape().projectionOnly shouldBe false
    assertThrows[IllegalArgumentException](QwenBlockShape.qwen35Qkv(129))
  }
}
