// Source-review candidate. Requires real external providers; no execution authorized.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import scala.collection.mutable
import java.nio.file.{Files,Paths}
class ProductionQk16KernelSpec extends AnyFlatSpec with ChiselScalatestTester {
  "Original production Kernel" should "execute one pinned synthetic Attention through real iDMA and Matrix" in {
    val input=Paths.get(sys.props("fixture"));val fixture=ujson.read(Files.readString(input))
    val selected=sys.props("selected") match {case "0"=>false;case "1"=>true;case _=>throw new IllegalArgumentException("selected 0|1")}
    val m=fixture("m").num.toInt;require(Set(1,17).contains(m))
    val addresses=fixture("addresses");val ram=mutable.Map.empty[BigInt,Int]
    def addr(n:String)=BigInt(addresses(n).num.toLong)
    for(n<-Seq("q","k","v");(word,i)<-fixture(n).arr.zipWithIndex;b<-0 until 4)
      ram(addr(n)+4*i+b)=((word.num.toLong>>(8*b))&255).toInt
    val expected=fixture("final_output_reference").arr.map(x=>BigInt(x.num.toLong)).toVector
    test(new ProductionQk16KernelBench(selected)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      println("KERNEL_SIM_READY") // First callback statement; absolute startup marker.
      var cycles=0L;val cap=2000000L
      case class Read(base:BigInt,id:BigInt,beats:Int,var beat:Int=0)
      case class Write(base:BigInt,id:BigInt,beats:Int)
      var rd:Option[Read]=None;var aw:Option[Write]=None
      val writes=mutable.Queue.empty[(BigInt,BigInt,Boolean)]
      var bvalid=false;var bid=BigInt(0)
      var ars=0;var rlasts=0;var aws=0;var bs=0;var wbeats=0
      var terminalSeen=false
      def word(address:BigInt)= (0 until 64).foldLeft(BigInt(0))((x,i)=>x|(BigInt(ram.getOrElse(address+i,throw new IllegalStateException("uninitialized read "+(address+i))))<<(8*i)))
      def step():Unit={
        require(cycles<cap,"cycle watchdog")
        // Only the external RAM is scripted; all arithmetic/services are real.
        d.io.axi.ar.ready.poke((rd.isEmpty&&cycles%7!=0).B)
        d.io.axi.aw.ready.poke((aw.isEmpty && !bvalid&&cycles%5!=0).B)
        d.io.axi.w.ready.poke((writes.size<256 && !bvalid&&cycles%3!=0).B)
        d.io.axi.r.valid.poke(rd.nonEmpty.B)
        rd match {
          case Some(r)=>d.io.axi.r.bits.id.poke(r.id.U);d.io.axi.r.bits.data.poke(word(r.base+64*r.beat).U);d.io.axi.r.bits.resp.poke(0.U);d.io.axi.r.bits.last.poke((r.beat+1==r.beats).B)
          case None=>d.io.axi.r.bits.id.poke(0.U);d.io.axi.r.bits.data.poke(0.U);d.io.axi.r.bits.resp.poke(0.U);d.io.axi.r.bits.last.poke(false.B)
        }
        d.io.axi.b.valid.poke(bvalid.B);d.io.axi.b.bits.id.poke(bid.U);d.io.axi.b.bits.resp.poke(0.U)
        def fire(v:Bool,r:Bool)=v.peek().litToBoolean&&r.peek().litToBoolean
        val arf=fire(d.io.axi.ar.valid,d.io.axi.ar.ready);val rf=fire(d.io.axi.r.valid,d.io.axi.r.ready)
        val awf=fire(d.io.axi.aw.valid,d.io.axi.aw.ready);val wf=fire(d.io.axi.w.valid,d.io.axi.w.ready);val bf=fire(d.io.axi.b.valid,d.io.axi.b.ready)
        if(terminalSeen){require(!arf && !rf && !awf && !wf && !bf,"traffic after terminal success");d.io.axi.ar.valid.expect(false.B);d.io.axi.aw.valid.expect(false.B);d.io.axi.w.valid.expect(false.B)}
        val nr=if(arf){d.io.axi.ar.bits.size.expect(6.U);d.io.axi.ar.bits.burst.expect(1.U);Some(Read(d.io.axi.ar.bits.addr.peek().litValue,d.io.axi.ar.bits.id.peek().litValue,d.io.axi.ar.bits.len.peek().litValue.toInt+1))}else None
        val nw=if(awf){d.io.axi.aw.bits.size.expect(6.U);d.io.axi.aw.bits.burst.expect(1.U);Some(Write(d.io.axi.aw.bits.addr.peek().litValue,d.io.axi.aw.bits.id.peek().litValue,d.io.axi.aw.bits.len.peek().litValue.toInt+1))}else None
        val wd=if(wf)Some((d.io.axi.w.bits.data.peek().litValue,d.io.axi.w.bits.strb.peek().litValue,d.io.axi.w.bits.last.peek().litToBoolean))else None
        d.io.resetRequired.expect(false.B);d.clock.step();cycles+=1
        if(rf){val r=rd.get;r.beat+=1;if(r.beat==r.beats){rd=None;rlasts+=1}}
        if(arf){require(rd.isEmpty);rd=nr;ars+=1}
        if(bf){require(bvalid);bvalid=false;bs+=1}
        if(awf){require(aw.isEmpty);aw=nw;aws+=1}
        wd.foreach{x=>writes.enqueue(x);wbeats+=1}
        aw.foreach{a=>if(writes.size>=a.beats){
          require(!bvalid)
          for(i<-0 until a.beats){val (data,strb,last)=writes.dequeue();require(last==(i+1==a.beats),"WLAST")
            for(b<-0 until 64 if strb.testBit(b)){val at=a.base+64*i+b;require(at>=addr("dst")&&at<addr("dst")+m*1536*4,"write outside output");ram(at)=((data>>(8*b))&255).toInt}}
          bid=a.id;bvalid=true;aw=None
        }}
        if(Set(1L,64L,4096L).contains(cycles)||cycles%65536==0)println("KERNEL_CYCLE "+cycles)
      }
      d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B)
      def zero(x:Data):Unit=x match {case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U);case r:Record=>r.elements.values.foreach(zero);case v:Vec[_]=>v.foreach(x=>zero(x));case _=>throw new IllegalArgumentException("unsupported init")}
      zero(d.io.job.bits)
      step();d.io.job.ready.expect(true.B)
      d.io.job.bits.kind.poke(QwenOwnerKind.Attention.U);d.io.job.bits.m.poke(m.U);d.io.job.bits.n.poke(1536.U);d.io.job.bits.k.poke(128.U)
      d.io.job.bits.a.poke(addr("q").U);d.io.job.bits.b.poke(addr("k").U);d.io.job.bits.c.poke(addr("v").U);d.io.job.bits.dst.poke(addr("dst").U)
      d.io.job.bits.writeBytes.poke((m*1536*4).U);d.io.job.bits.tag.poke(17.U);d.io.job.valid.poke(true.B);step();d.io.job.valid.poke(false.B)
      while(!d.io.done.valid.peek().litToBoolean)step()
      // Check completion obligations at first visibility, before any ACK delay.
      d.io.done.bits.status.expect(0.U);d.io.done.bits.tag.expect(17.U)
      require(rd.isEmpty&&aw.isEmpty&&writes.isEmpty && !bvalid&&ars==rlasts&&aws==bs,"early success before AXI retirement")
      assert(d.io.accepted(1).peek().litValue==d.io.returned(1).peek().litValue,"early success before hub retirement")
      for(i<-expected.indices){val actual=(0 until 4).foldLeft(BigInt(0))((x,b)=>x|(BigInt(ram.getOrElse(addr("dst")+4*i+b,throw new IllegalStateException("early success missing output")))<<(8*b)));assert(actual==expected(i),s"first terminal output word $i")}
      terminalSeen=true
      val trafficAtTerminal=(ars,rlasts,aws,bs,wbeats)
      def donePayload=d.io.done.bits.elements.toSeq.map{case(n,x)=>(n,x.asInstanceOf[UInt].peek().litValue)}
      val held=donePayload
      for(_<-0 until 127){d.io.done.valid.expect(true.B);assert(donePayload==held);step()}
      assert((ars,rlasts,aws,bs,wbeats)==trafficAtTerminal)
      d.io.done.bits.status.expect(0.U);d.io.done.bits.tag.expect(17.U);d.io.done.bits.writeBytes.expect((m*1536*4).U)
      require(rd.isEmpty&&aw.isEmpty&&writes.isEmpty && !bvalid&&ars==rlasts&&aws==bs,"AXI retirement")
      for(i<-expected.indices){val actual=(0 until 4).foldLeft(BigInt(0))((x,b)=>x|(BigInt(ram.getOrElse(addr("dst")+4*i+b,throw new IllegalStateException("missing output")))<<(8*b)));assert(actual==expected(i),s"output word $i got $actual expected ${expected(i)}")}
      d.io.accepted(0).expect(0.U);d.io.returned(0).expect(0.U);assert(d.io.accepted(1).peek().litValue==d.io.returned(1).peek().litValue)
      d.io.done.ready.poke(true.B);step();d.io.done.ready.poke(false.B);for(_<-0 until 8){d.io.done.valid.expect(false.B);step()}
      println(s"KERNEL_NORMAL_PASS selected=$selected m=$m cycles=$cycles ar=$ars aw=$aws wbeats=$wbeats")
    }
  }
}
