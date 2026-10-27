// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model
import chisel3._
import chisel3.util._
import heteronpu.continuous.{MatrixResultFifo,MatrixStreamResult}
import chiseltest.simulator.MatrixFifoDifferentialBridge
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import firrtl2.{AnnotationSeq,CircuitState}
import treadle2.TreadleTester

object MatrixFifoTrace {
  private val started=System.nanoTime();private var events=0
  private val os=java.lang.management.ManagementFactory.getOperatingSystemMXBean
    .asInstanceOf[com.sun.management.OperatingSystemMXBean]
  def mark(message:String):Unit={events+=1;require(events<=96,"bounded diagnostic records")
    val cpu=os.getProcessCpuTime;require(cpu>=0,"process CPU clock available")
    println(s"$message cpuNs=$cpu wallNs=${System.nanoTime()-started} marker=$events")}
}
/** One real full-capacity original FIFO and a downstream whole-payload register.
  * That sampler captures pre-edge deq.bits on fire, including simultaneous
  * full pop/push. It is test observation only, not added production storage. */
class MatrixFifoSamplingProbe extends Module {
  val io=IO(new Bundle {
    val enq=Flipped(Decoupled(new MatrixStreamResult(32)))
    val deq=Decoupled(new MatrixStreamResult(32))
    val sampled=Output(UInt(131109.W));val samples=Output(UInt(32.W))
  })
  val fifo=Module(new MatrixResultFifo(32));fifo.io.enq<>io.enq;io.deq<>fifo.io.deq
  val data=Cat(fifo.io.deq.bits.value.reverse.map(r=>Cat(r.reverse)))
  val packed=Cat(fifo.io.deq.bits.error,fifo.io.deq.bits.last,fifo.io.deq.bits.context,
    fifo.io.deq.bits.returnTag.get,data)
  val sampled=RegInit(0.U(131109.W));val samples=RegInit(0.U(32.W))
  when(fifo.io.deq.fire){sampled:=packed;samples:=samples+1.U}
  io.sampled:=sampled;io.samples:=samples
}
class MatrixFifoMemoryDifferentialSpec extends AnyFlatSpec with Matchers {
  import MatrixResultFifoStateModel._
  case class Event(reset:Boolean,valid:Boolean,ready:Boolean,seed:Int)
  case class Observation(ready:Boolean,valid:Boolean,payload:Payload,sampled:BigInt,samples:BigInt)
  private val returnTags=Vector("00000000","ffffffff","80000000","7fffffff","55555555","aaaaaaaa").map(BigInt(_,16))
  private def payload(seed:Int):Payload=Payload(Vector.tabulate(16)(r=>packRow(Vector.tabulate(256)(c=>
    (((seed.toLong&255)<<24)^(r.toLong<<16)^(c.toLong<<1)^1L)&0xffffffffL))),
    returnTags(seed%returnTags.size) | (BigInt(seed&7)<<32) | (BigInt((seed>>3)&1)<<35) | (BigInt((seed>>4)&1)<<36))
  private def packed(p:Payload):BigInt=p.rows.zipWithIndex.foldLeft(p.metadata<<131072){case(a,(r,i))=>a|(r<<(i*8192))}
  //24edges: all capacity/word indexes, both wraps, full stall/pop+push,
  // empty no-flowthrough, invalid bits, and reset writes at oldtail0 AND1.
  private val events=Vector(
    Event(true,false,false,0),Event(false,true,true,17),Event(false,true,false,10),
    Event(false,true,false,31),Event(false,true,true,31),Event(false,false,true,0),
    Event(false,true,true,9),Event(false,false,true,0),Event(false,false,true,0),
    Event(false,true,false,18),Event(true,true,false,23),Event(false,false,false,0),
    Event(false,true,false,1),Event(false,true,false,2),Event(true,false,false,0),
    Event(true,true,true,29),Event(false,false,false,0),Event(false,true,true,14),
    Event(false,false,true,25),Event(false,true,false,7),Event(false,true,true,30),
    Event(false,false,true,0),Event(false,false,true,0),Event(false,false,false,0))
  private def run(p:(CircuitState,AnnotationSeq),name:String):Vector[Observation]={
    MatrixFifoTrace.mark(s"FIFO_PHASE $name.engine.begin")
    val t=new TreadleTester(p._2)
    try {
      MatrixFifoTrace.mark(s"FIFO_PHASE $name.engine.end")
      require(t.engine.ast eq p._1.circuit,"same prepared object")
      val model=new MatrixResultFifoStateModel;var sample=BigInt(0);var samples=BigInt(0)
      val observations=Vector.newBuilder[Observation]
      def read():Observation={
        val rows=Vector.tabulate(16)(r=>packRow(Vector.tabulate(256)(c=>t.peek(s"io_deq_bits_value_${r}_$c").toLong)))
        val meta=t.peek("io_deq_bits_returnTag")|(t.peek("io_deq_bits_context")<<32)|
          (t.peek("io_deq_bits_last")<<35)|(t.peek("io_deq_bits_error")<<36)
        Observation(t.peek("io_enq_ready")!=0,t.peek("io_deq_valid")!=0,Payload(rows,meta),t.peek("io_sampled"),t.peek("io_samples"))
      }
      for((e,index)<-events.zipWithIndex){
        val x=payload(e.seed)
        t.poke("reset",if(e.reset)1 else 0);t.poke("io_enq_valid",if(e.valid)1 else 0);t.poke("io_deq_ready",if(e.ready)1 else 0)
        for(r<-0 until 16;c<-0 until 256)t.poke(s"io_enq_bits_value_${r}_$c",(x.rows(r)>>(c*32))&0xffffffffL)
        t.poke("io_enq_bits_returnTag",x.metadata&0xffffffffL);t.poke("io_enq_bits_context",(x.metadata>>32)&7)
        t.poke("io_enq_bits_last",(x.metadata>>35)&1);t.poke("io_enq_bits_error",(x.metadata>>36)&1)
        val before=read();before.ready shouldBe model.enqReady(e.ready);before.valid shouldBe model.deqValid
        before.payload shouldBe model.deqBits;before.sampled shouldBe sample;before.samples shouldBe samples
        observations+=before
        val transfer=model.edge(e.reset,e.valid,x,e.ready)
        if(e.reset){sample=0;samples=0}else if(transfer.dequeue){sample=packed(transfer.oldHead);samples+=1}
        t.step(1)
        val after=read();after.ready shouldBe model.enqReady(e.ready);after.valid shouldBe model.deqValid
        after.payload shouldBe model.deqBits;after.sampled shouldBe sample;after.samples shouldBe samples
        observations+=after
        MatrixFifoTrace.mark(s"FIFO_EDGE $name completed=${index+1} observations=${2*(index+1)}")
      }
      observations.result()
    } finally {t.finish}
  }
  it should "match original full FIFO and exact17memory storage on every fullpayload pre and post edge" in {
    val (original,memory)=MatrixFifoDifferentialBridge.both(()=>new MatrixFifoSamplingProbe)
    val a=run(original,"original");val b=run(memory,"memory")
    b shouldBe a;a.size shouldBe 48
    MatrixFifoTrace.mark("FIFO_DIFF_PASS edges=24 representations=2 observations=48 wordsPerObservation=4096 metadataBits=37 downstreamSampleBits=131109")
  }
}
