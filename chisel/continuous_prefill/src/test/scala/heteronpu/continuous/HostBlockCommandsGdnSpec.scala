// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** CONTROL_ONLY: the owner is a stand-in. This suite proves public descriptor
  * admission, exact owner binding, state lifetime and Host publication. It does
  * not establish Dense/Conv arithmetic or payload DMA/ACK correctness. */
class GdnFrontendControlHarness(enabled:Boolean) extends HostBlockCommands(
  QwenBlockShape.qwen35Gdn(),eventSlots=32,maxCommands=21,bf16Gdn=enabled) {
  val committedValid=IO(Output(Bool()));committedValid:=stateValid
  val committedGeneration=IO(Output(UInt(32.W)));committedGeneration:=currentGeneration
  val committedHistory=IO(Output(UInt(64.W)));committedHistory:=currentHistoryAddress
}
class HostBlockCommandsGdnSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val nil=BigInt(0xffffff);val cb=BigInt(0x1000);val db=BigInt(0x2000)
  val inputBase=BigInt(0x10000);val convInput=BigInt(0x400000);val w=BigInt(0x20000);val initial=BigInt(0x30000)
  val matrixW=BigInt(0x100000);val output=BigInt(0x1000000)
  val h0=BigInt(0x1f00000);val h1=BigInt(0x1f10000);val roEnd=BigInt(0xf00000);val rwEnd=BigInt(0x3000000)
  val historyBytes=BigInt(6144*4*2)
  case class Expected(kind:Int,a:BigInt,b:BigInt,dst:BigInt,m:Int,hin:BigInt=0,hout:BigInt=0,
                      generation:BigInt=0,cold:Boolean=false) {
    val bytes=BigInt(m)*6144*2+(if(kind==QwenOwnerKind.GdnConv)historyBytes else BigInt(0))
  }
  case class Program(commands:Vector[BigInt],records:Vector[BigInt],expected:Vector[Expected])
  def rec(kind:Int,next:BigInt,payload:BigInt):BigInt=BigInt(kind)|(next<<32)|(payload<<56)
  def field(word:BigInt,lo:Int,width:Int,value:BigInt):BigInt=(word&~(((BigInt(1)<<width)-1)<<lo))|(value<<lo)
  def tensor(address:BigInt):BigInt=(address&((BigInt(1)<<48)-1))|(BigInt(0x2050)<<48)|((address>>48)<<64)
  def shape(m:Int,n:Int):BigInt=BigInt(m)|(BigInt(n)<<18)|(BigInt(1)<<36)|(BigInt(1)<<54)
  def prefix(address:BigInt,m:Int,n:Int,start:Int,tail:BigInt):Vector[BigInt]=Vector(
    rec(1,start+1,tensor(address)),rec(2,start+2,shape(m,n)),rec(3,tail,BigInt(n)|(BigInt(1)<<24)|(BigInt(1)<<48)))
  def conv(m:Int=1,src:BigInt=convInput,dst:BigInt=output,hin:BigInt=initial,hout:BigInt=h0,
           generation:BigInt=0,cold:Boolean=true,start:Int=0,wait:Int=0,signal:Int=1):Program={
    val ds=prefix(src,m,6144,start,start+9)++prefix(w,6144,4,start+3,nil)++prefix(dst,m,6144,start+6,nil)++Vector(
      rec(0x20,start+10,BigInt(0x30)|(BigInt(2)<<16)|(BigInt(1)<<24)|(BigInt(5)<<32)|(BigInt(5)<<36)|(BigInt(16)<<40)|(BigInt(1)<<48)),
      rec(0x21,start+11,BigInt(0x101)|(BigInt(if(cold)1 else 0)<<24)|(generation<<32)),
      rec(0x22,nil,BigInt(start+12)|(BigInt(start+15)<<24)))++
      prefix(hin,6144,4,start+12,nil)++prefix(hout,6144,4,start+15,nil)
    val cmd=BigInt(0x330)|(BigInt(wait)<<24)|(BigInt(signal)<<40)|(BigInt(start)<<56)|(BigInt(start+3)<<80)|(BigInt(start+6)<<104)
    Program(Vector(cmd),ds,Vector(Expected(QwenOwnerKind.GdnConv,src,w,dst,m,hin,hout,generation,cold)))
  }
  def dense(m:Int=1,src:BigInt=inputBase,dst:BigInt=output,start:Int=0,wait:Int=0,signal:Int=1):Program={
    val ds=prefix(src,m,1024,start,start+9)++prefix(matrixW,1024,6144,start+3,nil)++prefix(dst,m,6144,start+6,nil)++Vector(
      rec(0x10,start+10,BigInt(m)|(BigInt(6144)<<16)|(BigInt(1024)<<32)),
      rec(0x12,start+11,BigInt("004000040020ffffff",16)),rec(0x21,nil,BigInt(0x201)))
    val cmd=BigInt(0x220)|(BigInt(wait)<<24)|(BigInt(signal)<<40)|(BigInt(start)<<56)|(BigInt(start+3)<<80)|(BigInt(start+6)<<104)
    Program(Vector(cmd),ds,Vector(Expected(QwenOwnerKind.Dense,src,matrixW,dst,m)))
  }
  def combine(ps:Program*):Program=Program(ps.toVector.flatMap(_.commands),ps.toVector.flatMap(_.records),ps.toVector.flatMap(_.expected))
  def edit(p:Program,i:Int,lo:Int,width:Int,v:BigInt):Program=p.copy(records=p.records.updated(i,field(p.records(i),lo,width,v)))
  def setup(d:GdnFrontendControlHarness,p:Program,reset:Boolean):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.completion.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);d.io.job.ready.poke(false.B);d.io.done.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.done.bits.tag.poke(0.U);d.io.done.bits.status.poke(0.U);d.io.done.bits.writeBytes.poke(0.U)
    d.io.done.bits.cycles.poke(0.U);d.io.done.bits.usefulMacs.poke(0.U);d.io.done.bits.executedMacs.poke(0.U)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B)}
    val l=d.io.launch.bits;l.commandBase.poke(cb.U);l.commandLimit.poke((cb+0x1000).U);l.commands.poke(p.commands.size.U)
    l.descriptorBase.poke(db.U);l.descriptorLimit.poke((db+0x4000).U);l.descriptors.poke(p.records.size.U);l.epoch.poke(9.U)
    for((r,i)<-Seq((cb,BigInt(0x6000),true,false),(inputBase,roEnd,true,false),
      (output,rwEnd,true,true),(BigInt(0),BigInt(0),false,false)).zipWithIndex){
      l.regions(i).base.poke(r._1.U);l.regions(i).limit.poke(r._2.U);l.regions(i).read.poke(r._3.B);l.regions(i).write.poke(r._4.B)
    }
  }
  def run(d:GdnFrontendControlHarness,p:Program,reset:Boolean=true,doneFault:Int=0,readFault:Boolean=false,writeOnly:Boolean=false):(Int,Int,Int)={
    setup(d,p,reset);var gen=d.committedGeneration.peek().litValue;var hist=d.committedHistory.peek().litValue
    var valid=d.committedValid.peek().litToBoolean
    if(writeOnly)d.io.launch.bits.regions(2).read.poke(false.B)
    d.io.launch.ready.expect(true.B);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
    // Admission snapshots the launch. Later caller pin changes have no effect.
    d.io.launch.bits.epoch.poke(99.U);d.io.launch.bits.regions(2).write.poke(false.B)
    var jobs=0;var completions=0;var accepted=0;var ticks=0;var written=BigInt(0)
    def stateUnchanged():Unit={d.committedGeneration.expect(gen.U);d.committedHistory.expect(hist.U);d.committedValid.expect(valid.B)}
    while(!d.io.result.valid.peek().litToBoolean && ticks<15000){
      if(d.io.memory.valid.peek().litToBoolean){
        val addr=d.io.memory.bits.address.peek().litValue;val tag=d.io.memory.bits.tag.peek().litValue
        assert(addr>=cb && addr<db+0x4000);d.io.memory.bits.write.expect(false.B)
        d.clock.step(2);d.io.memory.bits.address.expect(addr.U);d.io.memory.bits.tag.expect(tag.U)
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
        val table=if(addr<db)p.commands else p.records;val offset=((addr-(if(addr<db)cb else db))/16).toInt
        val data=(0 until 4).map(i=>table.lift(offset+i).getOrElse(BigInt(0))<<(128*i)).reduce(_|_)
        d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke(tag.U);d.io.response.bits.error.poke(readFault.B)
        d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      }else if(d.io.job.valid.peek().litToBoolean){
        val e=p.expected(jobs);val tag=BigInt(9<<16)|jobs
        d.io.job.bits.kind.expect(e.kind.U);d.io.job.bits.a.expect(e.a.U);d.io.job.bits.b.expect(e.b.U);d.io.job.bits.dst.expect(e.dst.U)
        d.io.job.bits.m.expect(e.m.U);d.io.job.bits.n.expect(6144.U);d.io.job.bits.k.expect((if(e.kind==QwenOwnerKind.Dense)1024 else 4).U)
        d.io.job.bits.c.expect(e.hin.U);d.io.job.bits.historyOut.expect(e.hout.U);d.io.job.bits.expectedGeneration.expect(e.generation.U)
        d.io.job.bits.currentGeneration.expect((if(e.kind==QwenOwnerKind.GdnConv)gen else BigInt(0)).U)
        d.io.job.bits.cold.expect(e.cold.B);d.io.job.bits.tag.expect(tag.U);d.io.job.bits.writeBytes.expect(e.bytes.U)
        d.io.job.bits.weightBf16.expect(true.B);d.io.job.bits.activationBf16.expect(true.B);d.io.job.bits.outputBf16.expect(true.B)
        val saved=Seq(d.io.job.bits.a,d.io.job.bits.b,d.io.job.bits.c,d.io.job.bits.dst,d.io.job.bits.tag,
          d.io.job.bits.m,d.io.job.bits.n,d.io.job.bits.k,d.io.job.bits.kind,d.io.job.bits.writeBytes,
          d.io.job.bits.historyOut,d.io.job.bits.expectedGeneration,d.io.job.bits.currentGeneration).map(x=>(x,x.peek().litValue))
        for(_<-0 until 3){stateUnchanged();saved.foreach{case(x,v)=>x.expect(v.U)};d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.job.ready.poke(true.B);d.clock.step();d.io.job.ready.poke(false.B);jobs+=1
        for(_<-0 until 3){stateUnchanged();d.io.memory.valid.expect(false.B);d.io.completion.valid.expect(false.B);d.clock.step()}
        d.io.done.bits.tag.poke((if(doneFault==2)tag^1 else tag).U);d.io.done.bits.status.poke((if(doneFault==1)Status.Memory else 0).U)
        d.io.done.bits.writeBytes.poke((e.bytes+(if(doneFault==3)-64 else if(doneFault==4)64 else 0)).U)
        d.io.done.valid.poke(true.B);d.io.done.ready.expect(true.B);d.clock.step();d.io.done.valid.poke(false.B)
        if(doneFault==0)written+=e.bytes
      }else if(d.io.completion.valid.peek().litToBoolean){
        val word=d.io.completion.bits.peek().litValue;val ok=((word>>32)&255)==0
        for(_<-0 until 4){stateUnchanged();d.io.completion.bits.expect(word.U);d.io.job.valid.expect(false.B);d.io.memory.valid.expect(false.B);d.clock.step()}
        d.io.completion.ready.poke(true.B);d.clock.step();d.io.completion.ready.poke(false.B)
        if(ok){val e=p.expected(accepted);completions+=1;if(e.kind==QwenOwnerKind.GdnConv){gen=e.generation+1;hist=e.hout;valid=true}}
        stateUnchanged();accepted+=1
      }else d.clock.step()
      ticks+=1
    }
    d.io.result.valid.expect(true.B);d.io.result.bits.completed.expect(completions.U);d.io.result.bits.epoch.expect(9.U)
    val status=d.io.result.bits.status.peek().litValue.toInt
    d.io.issuedJobs.expect(jobs.U);d.io.writeBytes.expect(written.U);d.io.resetRequired.expect((status!=0).B);stateUnchanged()
    d.clock.step(2);d.io.result.ready.poke(true.B);d.clock.step();d.io.result.ready.poke(false.B)
    d.io.launch.ready.expect((status==0).B)
    (status,jobs,completions)
  }
  "Host GDN CONTROL_ONLY" should "bind native projections and guard Conv4 state publication, lifetime and all descriptor roots" in {
    test(new GdnFrontendControlHarness(true)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(m<-Seq(1,3,128))run(d,conv(m=m)) shouldBe (0,1,1)
      // Real command dataflow: Dense publication is the Conv source, and the
      // carried command must consume the preceding committed history exactly.
      val flow=combine(dense(),conv(src=output,dst=output+0x20000,start=12,wait=1,signal=2),
        dense(dst=output+0x40000,start=30,wait=2,signal=3),
        conv(src=output+0x40000,dst=output+0x60000,hin=h0,hout=h1,generation=1,cold=false,start=42,wait=3,signal=4),
        conv(dst=output+0x80000,hin=h1,hout=h0,generation=2,cold=false,start=60,wait=4,signal=5))
      run(d,flow) shouldBe (0,5,5)
      // Context survives launch boundaries. Only managed history survives as
      // a special input; the user must still provide readable allocation maps.
      run(d,conv(hin=h0,hout=h1,generation=3,cold=false),reset=false) shouldBe (0,1,1)
      run(d,conv(hin=h1,hout=h0,generation=4,cold=false),reset=false) shouldBe (0,1,1)
      run(d,dense(dst=h0),reset=false) shouldBe (Status.Permission,0,0) // Dense cannot overwrite persistent current state
      run(d,conv(cold=false)) shouldBe (0,1,1) // explicit read-only state import
      run(d,conv(hin=h1,cold=false)) shouldBe (Status.Dependency,0,0)
      // Cold still validates the ignored history allocation and may use a
      // valid read/write allocation that has never been published.
      run(d,conv(hin=h1)) shouldBe (0,1,1)
      for(changed<-Seq(conv(generation=1),conv(generation=BigInt("ffffffff",16))))
        run(d,changed) shouldBe (Status.Dependency,0,0)
      for(changed<-Seq(conv(hin=h0,hout=h1,generation=1,cold=true),
        conv(hin=h0,hout=h1,generation=0,cold=false),conv(hin=initial,hout=h1,generation=1,cold=false))){
        run(d,conv()) shouldBe (0,1,1);run(d,changed,reset=false) shouldBe (Status.Dependency,0,0)
      }
      // Never publish the gap after D using the sum of two noncontiguous writes.
      run(d,combine(conv(),conv(src=output+6144*2,dst=output+0x20000,hin=h0,hout=h1,generation=1,cold=false,start=18,wait=1,signal=2))) shouldBe (Status.Dependency,1,1)
      // Ordinary D remains live after history retirement; it cannot be reused.
      run(d,combine(conv(),conv(dst=output,hin=h0,hout=h1,generation=1,cold=false,start=18,wait=1,signal=2))) shouldBe (Status.Permission,1,1)
      // Both publication entries are reserved, including a full maxCommands run.
      val full=(0 until 21).map(i=>conv(dst=output+BigInt(i)*0x20000,hin=if(i==0)initial else if(i%2==1)h0 else h1,
        hout=if(i%2==0)h0 else h1,generation=i,cold=i==0,start=i*18,wait=i,signal=i+1))
      run(d,combine(full:_*)) shouldBe (0,21,21)
      for(fault<-1 to 4){
        run(d,conv()) shouldBe (0,1,1)
        run(d,conv(hin=h0,hout=h1,generation=1,cold=false),reset=false,doneFault=fault) shouldBe (if(fault==1)Status.Memory else Status.Protocol,1,0)
      }
      val p=conv()
      // Five independent typed readers enforce storage, strides and full bounds.
      for(root<-Seq(0,3,6,12,15);(lo,width,value)<-Seq((108,4,BigInt(7)),(56,48,BigInt(0x80)))){
        val r=run(d,edit(p,root,lo,width,value));r._1 should not be 0;r._2 shouldBe 0
      }
      for(stride<-Seq(2,5,8,14,17)){val r=run(d,edit(p,stride,56,24,BigInt(2)));r._1 should not be 0;r._2 shouldBe 0}
      val malformed=Seq((9,56,16,BigInt(0x32)),(9,96,8,BigInt(8)),(10,56,8,BigInt(2)),(10,64,8,BigInt(2)),
        (10,72,8,BigInt(1)),(10,81,7,BigInt(1)),(10,120,8,BigInt(1)),(11,104,24,BigInt(1)),
        (11,32,24,BigInt(9)),(11,56,24,BigInt(3)),(11,80,24,BigInt(12)),
        (14,32,24,BigInt(9)),(17,32,24,BigInt(9)),(12,56,48,roEnd-64),(15,56,48,rwEnd-64))
      for((i,lo,width,value)<-malformed){withClue(s"record=$i bit=$lo: "){val r=run(d,edit(p,i,lo,width,value));r._1 should not be 0;r._2 shouldBe 0}}
      for(changed<-Seq(conv(dst=h0),conv(hout=output),conv(hin=h0),conv(hout=inputBase),conv(dst=inputBase))){val r=run(d,changed);r._1 should not be 0;r._2 shouldBe 0}
      run(d,conv(src=output+0x20000)) shouldBe (Status.Dependency,0,0)
      run(d,edit(p,3,56,48,output+0x20000)) shouldBe (Status.Dependency,0,0)
      run(d,conv(),writeOnly=true) shouldBe (Status.Permission,0,0)
      // Public GDN ranges are pairwise disjoint even when both are readonly.
      // These independently exercise Dense A/B and Conv A/B, A/Hin, B/Hin.
      for(changed<-Seq(dense(src=matrixW),conv(src=w),conv(src=initial),conv(hin=w)))
        run(d,changed) shouldBe (Status.Permission,0,0)
      val projection=dense()
      for((i,lo,width,value)<-Seq((11,56,8,BigInt(2)),(11,64,8,BigInt(1)),(11,72,8,BigInt(1)),
        (11,80,1,BigInt(1)),(11,88,32,BigInt(1)),(4,74,18,BigInt(512)),(7,74,18,BigInt(512)),(11,32,24,BigInt(9)))){
        val r=run(d,edit(projection,i,lo,width,value));r._1 should not be 0;r._2 shouldBe 0
      }
      val read=run(d,p,readFault=true);read._1 should not be 0;read._2 shouldBe 0
      // Reset clears poison and the committed context, allowing cold gen0 again.
      run(d,conv()) shouldBe (0,1,1)
    }
  }
  it should "remain explicitly disabled in the GDN profile unless enabled" in {
    test(new GdnFrontendControlHarness(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      for(p<-Seq(conv(),dense())){val r=run(d,p);r._1 should not be 0;r._2 shouldBe 0}
    }
  }
}
