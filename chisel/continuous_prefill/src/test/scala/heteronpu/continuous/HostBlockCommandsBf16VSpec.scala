// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Real Host decoder control tests. No owner arithmetic is claimed here. */
class HostBlockCommandsBf16VSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val cb=BigInt(0x1000);val db=BigInt(0x2000);val actBase=BigInt(0x10000)
  val b=BigInt(0x100000);val dst=BigInt(0x300000);val dst2=BigInt(0x340000)
  val nil=BigInt(0xffffff)
  case class Program(commands:Vector[BigInt],records:Vector[BigInt],windows:Vector[(BigInt,BigInt,Int)])
  def rec(kind:Int,next:BigInt,payload:BigInt)=BigInt(kind)|(next<<32)|(payload<<56)
  def tensor(address:BigInt)= (address&((BigInt(1)<<48)-1))|(BigInt(0x2050)<<48)|((address>>48)<<64)
  def shape(m:Int,n:Int)=BigInt(m)|(BigInt(n)<<18)|(BigInt(1)<<36)|(BigInt(1)<<54)
  def binding(m:Int=8,base:Int=2,count:Int=4,act:BigInt=actBase,out:BigInt=dst,start:Int=0,wait:Int=0,signal:Int=1):Program={
    var ds=Vector.fill(21)(BigInt(0))
    for((offset,rows,cols,address)<-Seq((0,m,1024,act),(15,1024,512,b),(18,m,512,out))){
      ds=ds.updated(offset,rec(1,start+offset+1,tensor(address)))
        .updated(offset+1,rec(2,start+offset+2,shape(rows,cols)))
        .updated(offset+2,rec(3,if(offset==0)BigInt(start+3)else nil,BigInt(cols)|(BigInt(1)<<24)|(BigInt(1)<<48)))
    }
    ds=ds.updated(3,rec(0x10,start+4,BigInt(m)|(BigInt(512)<<16)|(BigInt(1024)<<32)))
      .updated(4,rec(0x12,start+5,BigInt("004000040020ffffff",16)))
      .updated(5,rec(0x1a,start+6,BigInt(2)|(BigInt(2)<<8)|(BigInt(3)<<10)|(BigInt(base)<<12)|(BigInt(count)<<44)))
    for(i<-0 until 9)ds=ds.updated(6+i,rec(0x1b,if(i==8)nil else BigInt(start+7+i),BigInt(i)<<56))
    val cmd=BigInt(0x220)|(BigInt(wait)<<24)|(BigInt(signal)<<40)|(BigInt(start)<<56)|(BigInt(start+15)<<80)|(BigInt(start+18)<<104)
    Program(Vector(cmd),ds,Vector((act+base*2048,out+base*1024,count)))
  }
  def combine(x:Program,y:Program)=Program(x.commands++y.commands,x.records++y.records,x.windows++y.windows)
  def field(word:BigInt,lo:Int,width:Int,value:BigInt)=(word&~(((BigInt(1)<<width)-1)<<lo))|(value<<lo)
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
    for((r,i)<-Seq((cb,BigInt(0x4000),true,false),(actBase,dst,true,false),(dst,BigInt(0x400000),true,true),(BigInt(0),BigInt(0),false,false)).zipWithIndex){
      l.regions(i).base.poke(r._1.U);l.regions(i).limit.poke(r._2.U);l.regions(i).read.poke(r._3.B);l.regions(i).write.poke(r._4.B)
    }
  }
  def run(d:HostBlockCommands,p:Program,doneFault:Int=0,readFault:Int=0,mutatePins:Boolean=false):(Int,Int,Int)={
    initialize(d,p);d.io.launch.valid.poke(true.B);d.io.launch.ready.expect(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    if(mutatePins){d.io.launch.bits.commandBase.poke(0.U);d.io.launch.bits.epoch.poke(99.U)}
    var jobs=0;var completions=0;var ticks=0
    while(!d.io.result.valid.peek().litToBoolean && ticks<2000){
      if(d.io.memory.valid.peek().litToBoolean){
        val addr=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        d.io.memory.bits.write.expect(false.B);d.clock.step(3);d.io.memory.bits.address.expect(addr.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val table=if(addr<db)p.commands else p.records;val off=((addr-(if(addr<db)cb else db))/16).toInt
        val data=(0 until 4).map(i=>table.lift(off+i).getOrElse(BigInt(0))<<(128*i)).reduce(_|_)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke((if(readFault==2)tag^1 else tag).U);d.io.response.bits.error.poke((readFault==1).B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        val (aa,dd,mm)=p.windows(jobs);val tag=d.io.job.bits.tag.peek().litValue
        d.io.job.bits.kind.expect(QwenOwnerKind.Dense.U);d.io.job.bits.a.expect(aa.U);d.io.job.bits.b.expect(b.U);d.io.job.bits.dst.expect(dd.U)
        d.io.job.bits.m.expect(mm.U);d.io.job.bits.n.expect(512.U);d.io.job.bits.k.expect(1024.U)
        d.io.job.bits.activationBf16.expect(true.B);d.io.job.bits.weightBf16.expect(true.B);d.io.job.bits.outputBf16.expect(true.B)
        d.io.job.bits.writeBytes.expect((mm*1024).U)
        val saved=Seq(d.io.job.bits.a,d.io.job.bits.b,d.io.job.bits.dst,d.io.job.bits.tag,d.io.job.bits.m,d.io.job.bits.writeBytes).map(x=>(x,x.peek().litValue))
        for(_<-0 until 5){d.io.completion.valid.expect(false.B);saved.foreach{case(x,v)=>x.expect(v.U)};d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B);jobs+=1
        for(_<-0 until 7){d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.done.bits.tag.poke((if(doneFault==2)tag^1 else tag).U);d.io.done.bits.status.poke((if(doneFault==1)Status.Memory else 0).U)
        d.io.done.bits.writeBytes.poke((mm*1024-(if(doneFault==3)64 else 0)).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
      }else if(d.io.completion.valid.peek().litToBoolean){
        val c=d.io.completion.bits.peek().litValue
        for(_<-0 until 4){d.io.job.valid.expect(false.B);d.io.completion.bits.expect(c.U);d.clock.step()}
        if(((c>>32)&255)==0)completions+=1
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.epoch.expect(7.U);d.io.result.bits.completed.expect(completions.U)
    val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.issuedJobs.expect(jobs.U);if(status!=0)d.io.resetRequired.expect(true.B)
    (status,jobs,completions)
  }
  def dut(enabled:Boolean=true)=new HostBlockCommands(QwenBlockShape.qwen35V(),bf16Weights=true,bf16V=enabled)
  "Host native BF16 V" should "remain disabled by default" in {
    test(dut(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>val r=run(d,binding());r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}
  }
  it should "snapshot a valid nonzero token window and expose all three native storage flags" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for((m,base,count)<-Seq((1,0,1),(15,0,15),(17,1,16),(81,1,80),(128,0,128),(128,47,81)))
        run(d,binding(m,base,count),mutatePins=true) shouldBe (0,1,1)
    }
  }
  it should "reject Q K unknown versions reserved fields malformed chains and unsafe full tensor ranges before any job" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val p=binding();val ds=p.records
      val edits=Seq(
        (5,field(ds(5),64,2,0)),(5,field(ds(5),64,2,1)),(5,field(ds(5),56,8,1)),(5,field(ds(5),56,8,3)),
        (5,ds(5)|(BigInt(1)<<108)),(5,ds(5)|(BigInt(1)<<127)),(5,field(ds(5),66,2,0)),
        (5,field(ds(5),68,32,BigInt("ffffffff",16))),(5,field(ds(5),100,8,0)),(5,field(ds(5),100,8,129)),
        (5,field(ds(5),32,24,5)),(8,field(ds(8),32,24,6)),(14,field(ds(14),32,24,15)),
        (4,field(ds(4),32,24,nil)),(7,field(ds(7),32,24,nil)),(3,field(ds(3),32,24,99)),
        (6,ds(6)|(BigInt(64)<<56)),(6,ds(6)|(BigInt(1)<<120)),(7,field(ds(7),112,8,8)),
        (2,field(ds(2),32,24,0)),(1,field(ds(1),32,24,1)),(2,ds(2)|(BigInt(1)<<8)),
        (0,field(ds(0),56,48,actBase+2)),(15,field(ds(15),56,48,b+2)),(18,field(ds(18),56,48,dst+2)),
        (18,field(ds(18),56,48,actBase)),(1,field(ds(1),56,18,129)),(0,field(ds(0),56,48,dst-64)),
        (4,ds(4)|(BigInt(1)<<(56+26))), (3,ds(3)|(BigInt(1)<<115)))
      for((i,w)<-edits){val r=run(d,p.copy(records=ds.updated(i,w)));withClue(s"record $i word ${w.toString(16)}: "){r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}}
      for((lo,width,value)<-Seq((0,8,BigInt(0x23)),(8,3,BigInt(3)),(11,13,BigInt(1)),(80,24,BigInt(0)))){
        val r=run(d,p.copy(commands=p.commands.updated(0,field(p.commands(0),lo,width,value))));r._1 should not be 0;r._2 shouldBe 0
      }
    }
  }
  it should "publish only the ACKed window and reject untouched prefix suffix and overlapping writes" in {
    test(dut()).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      val first=binding()
      val exact=combine(first,binding(4,1,2,act=dst,out=dst2,start=21,wait=1,signal=2))
      run(d,exact) shouldBe (0,2,2)
      for(base<-Seq(0,3)){val p=combine(first,binding(4,base,1,act=dst,out=dst2,start=21,wait=1,signal=2));run(d,p) shouldBe (Status.Dependency,1,1)}
      run(d,combine(first,binding(8,0,2,start=21,wait=1,signal=2))) shouldBe (0,2,2)
      run(d,combine(first,binding(8,3,2,start=21,wait=1,signal=2))) shouldBe (Status.Permission,1,1)
      for(fault<-1 to 3){val r=run(d,exact,doneFault=fault);r._1 should not be 0;r._2 shouldBe 1;r._3 shouldBe 0}
      for(fault<-1 to 2){val r=run(d,first,readFault=fault);r._1 should not be 0;r._2 shouldBe 0;r._3 shouldBe 0}
    }
  }
  it should "separate hidden context and packed Q layout widths without enabling a full block" in {
    val s=QwenBlockShape.qwen35V();s.hidden shouldBe 1024;s.q shouldBe 2048;s.packedQ shouldBe 4096;s.kv shouldBe 512;s.maxRow shouldBe 4096
    val regions=new QwenBlockLayout(s).regions.map(r=>r.name->r.words).toMap
    regions("wq") shouldBe 1024L*4096;regions("wo") shouldBe 2048L*1024;regions("q") shouldBe 128L*2048;regions("qr") shouldBe 128L*4096
    QwenBlockShape(64,128,2,1,32,1024,true).maxRow shouldBe 128
  }
}
