// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.CancelAfterFailure
import scala.collection.mutable.ArrayBuffer

/** Test-only observation ports on the actual owner, without replacement logic. */
class AHoldProbe(reuse:Boolean) extends TransposedDenseDownOwner(
  burstWrites=true,enableFfnTiles=true,enableFfnWindow=true,
  enableFfnDrain=true,enableKWindow=true,enableDenseDrain=true,
  enableRawKv=true,enableAHold=reuse) {
  val probe=IO(new Bundle {
    val readFire=Output(Bool());val readA=Output(Bool())
    val response=Output(Bool());val pendingContext=Output(UInt(3.W))
    val reserved=Output(UInt(4.W));val holdValid=Output(Bool())
    val dmaOutstanding=Output(Bool());val queueEmpty=Output(Bool())
  })
  probe.readFire:=banks.io.read.fire
  probe.readA:=banks.io.read.bits.readActivation.getOrElse(true.B)
  probe.response:=banks.io.response.valid;probe.pendingContext:=pendingContext
  probe.reserved:=operands.io.count+&banks.io.response.valid.asUInt
  probe.holdValid:=heldAValid.getOrElse(false.B)
  probe.dmaOutstanding:=burstOutstanding;probe.queueEmpty:= !operands.io.deq.valid
}

/** Prepared bounded handshake tests. Explicitly not executed by prepare.py.
  * All data is synthetic finite ingress; Matrix arithmetic is not instantiated.
  * Successful packet tests abort after observation and prove accepted debt drain.
  */
class AHoldUnit extends AnyFlatSpec with ChiselScalatestTester with CancelAfterFailure {
  private def yes(b:Bool)=b.peek().litToBoolean
  private def num(u:UInt)=u.peek().litValue
  private def zero(d:Data):Unit=d match {
    case b:Bool=>b.poke(false.B)
    case u:UInt=>u.poke(0.U)
    case s:SInt=>s.poke(0.S)
    case v:Vec[_]=>v.foreach(zero)
    case r:Record=>r.elements.values.foreach(zero)
    case _=>throw new IllegalArgumentException("unsupported input")
  }
  private val abase=BigInt(0x100000);private val bbase=BigInt(0x200000)
  private def a(row:Int,k:Int)=BigInt(0x3f800000L)+(BigInt((row*5+k)&31)<<16)
  private def w(k:Int,col:Int)=BigInt(0x40000000L)+(BigInt((k*3+col)&31)<<16)
  private def pack(words:Seq[BigInt])=words.zipWithIndex.foldLeft(BigInt(0)){
    case(sum,(word,i))=>sum|(word<<(32*i))
  }
  private def defaults(d:AHoldProbe):Unit={
    d.io.job.valid.poke(false.B);zero(d.io.job.bits);d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B);zero(d.io.response.bits)
    d.io.burst.ready.poke(false.B);d.io.burstResponse.valid.poke(false.B);zero(d.io.burstResponse.bits)
    d.io.writeRequest.get.ready.poke(false.B);d.io.writeData.get.ready.poke(false.B)
    d.io.writeResponse.get.valid.poke(false.B);zero(d.io.writeResponse.get.bits)
    zero(d.io.prefixWorkspace.get);d.io.physicalSteps.poke(0.U)
    d.io.matrix.group.ready.poke(false.B);d.io.matrix.step.ready.poke(false.B)
    d.io.matrix.result.valid.poke(false.B);zero(d.io.matrix.result.bits)
    d.io.matrix.done.valid.poke(false.B);zero(d.io.matrix.done.bits)
    val s=d.io.matrix.seed.get
    s.begin.ready.poke(false.B);s.beat.ready.poke(false.B);s.ack.valid.poke(false.B);zero(s.ack.bits)
    val t=d.io.tiles.get
    t.control.valid.poke(false.B);zero(t.control.bits);t.write.valid.poke(false.B);zero(t.write.bits)
    t.read.valid.poke(false.B);zero(t.read.bits);t.response.ready.poke(false.B);t.abort.poke(false.B)
    val win=d.io.window.get
    win.request.valid.poke(false.B);zero(win.request.bits);win.result.ready.poke(false.B);win.invalidateLease.poke(false.B)
    val drain=d.io.drain.get
    drain.request.valid.poke(false.B);zero(drain.request.bits);drain.result.ready.poke(false.B);drain.abort.poke(false.B)
    val raw=d.io.rawKv.get
    raw.acquire.valid.poke(false.B);raw.acquire.bits.poke(0.U)
    raw.release.valid.poke(false.B);raw.release.bits.poke(0.U)
    raw.request.valid.poke(false.B);zero(raw.request.bits);raw.ack.valid.poke(false.B);zero(raw.ack.bits)
    raw.abort.poke(false.B);raw.softReset.poke(false.B)
  }
  private def exercise(d:AHoldProbe,reuse:Boolean,k:Int,injectDma:Boolean):Unit={
    defaults(d);d.clock.step(2)
    val ws=d.io.prefixWorkspace.get
    ws.valid.poke(true.B);ws.base.poke(0x400000.U);ws.extent.poke((5*16384).U)
    ws.generation.poke(7.U);ws.splitK.poke(256.U)
    val j=d.io.job.bits
    j.kind.poke(QwenOwnerKind.Dense.U);j.m.poke(16.U);j.n.poke(160.U);j.k.poke(k.U)
    j.a.poke(abase.U);j.b.poke(bbase.U);j.dst.poke(0x300000.U)
    j.writeBytes.poke((16*160*4).U);j.tag.poke(11.U)
    d.io.job.valid.poke(true.B);d.io.job.ready.expect(true.B);d.clock.step();d.io.job.valid.poke(false.B)
    case class Read(address:BigInt,tag:BigInt,due:Int)
    var pending:Option[Read]=None
    var accepted=0;var returned=0;var gathered=0;var aReads=0;var steps=0
    var fault=false;var matrixDone=false;var done=false;var cycle=0;var blockedUntil= -1
    var sawFull=false;var sawBypass=false;var held:Option[Seq[BigInt]]=None
    val packets=ArrayBuffer.empty[Seq[BigInt]]
    while(!done && cycle<20000){
      d.io.burst.ready.poke(true.B);d.io.matrix.group.ready.poke(true.B)
      if(!injectDma && !fault && steps==k*5){
        assert(gathered==k*5 && aReads==(if(reuse)k else k*5))
        if(reuse){assert(sawBypass);d.probe.holdValid.expect(false.B)}
        assert(sawFull);d.io.window.get.invalidateLease.poke(true.B);fault=true
      }
      // Long initial blockage plus periodic stalls exercise reserved RAM credit.
      val ready=cycle%13<8 && cycle>=blockedUntil
      d.io.matrix.step.ready.poke(ready.B)
      d.io.burstResponse.valid.poke(pending.exists(_.due<=cycle).B)
      d.io.burstResponse.bits.error.poke(false.B)
      pending.foreach{r=>
        val first=if(r.address<bbase)((r.address-abase)/4).toInt else ((r.address-bbase)/4).toInt
        val words=(0 until 16).map{i=>
          if(r.address<bbase)a((first+i)/k,(first+i)%k)else w((first+i)/160,(first+i)%160)
        }
        d.io.burstResponse.bits.data.poke(pack(words).U)
        d.io.burstResponse.bits.tag.poke(r.tag.U);d.io.burstResponse.bits.last.poke(true.B)
      }
      val inject=injectDma && !fault && pending.exists(_.due<=cycle) && yes(d.probe.response) && yes(d.probe.readFire)
      if(inject){
        d.io.burstResponse.bits.error.poke(true.B)
        d.probe.readFire.expect(false.B);d.io.matrix.step.valid.expect(false.B)
        fault=true
      }
      val readFire=yes(d.probe.readFire)
      if(fault)assert(!readFire,"fault edge issued new bank work")
      if(readFire){if(gathered==0)blockedUntil=cycle+25;gathered+=1;if(yes(d.probe.readA))aReads+=1}
      if(reuse && readFire && !yes(d.probe.readA) && yes(d.probe.response) && num(d.probe.pendingContext)==0){sawBypass=true}
      val reserved=num(d.probe.reserved).toInt
      assert(reserved<=(if(reuse)3 else 4));if(reserved==(if(reuse)3 else 4))sawFull=true
      val valid=yes(d.io.matrix.step.valid)
      if(valid){
        val s=d.io.matrix.step.bits
        val bits=s.a.map(num).toSeq++s.b.map(num).toSeq++Seq(num(s.context),BigInt(if(yes(s.clear))1 else 0),BigInt(if(yes(s.last))1 else 0),BigInt(if(yes(s.finish))1 else 0),BigInt(if(yes(s.emit))1 else 0))
        held.foreach(old=>assert(old==bits,"queued private A changed under backpressure"))
        if(ready){
          val logicalK=steps/5;val context=steps%5
          s.context.expect(context.U);s.clear.expect((logicalK==0).B)
          s.last.expect((logicalK+1==k).B);s.emit.expect((logicalK+1==k).B)
          s.finish.expect((logicalK+1==k && context==4).B)
          for(i<-0 until 16){s.a(i).expect((w(logicalK,context*32+i)>>16).U)
            s.b(i).expect((a(i,logicalK)>>16).U);s.b(128+i).expect((w(logicalK,context*32+16+i)>>16).U)}
          for(i<-16 until 128)s.b(i).expect(0.U)
          for(i<-144 until 256)s.b(i).expect(0.U)
          packets+=bits;steps+=1;held=None
        }else held=Some(bits)
      }else if(fault)held=None
      if(yes(d.io.matrix.abort) && !matrixDone){
        d.io.matrix.done.valid.poke(true.B);d.io.matrix.done.bits.tag.poke(11.U);d.io.matrix.done.bits.error.poke(true.B)
      }else d.io.matrix.done.valid.poke(false.B)
      val ret=yes(d.io.burstResponse.valid)&&yes(d.io.burstResponse.ready)
      val req=yes(d.io.burst.valid)&&yes(d.io.burst.ready)
      val newRead=if(req)Some(Read(num(d.io.burst.bits.address),num(d.io.burst.bits.tag),cycle+2))else None
      if(req){d.io.burst.bits.beats.expect(1.U);assert(pending.isEmpty || ret);accepted+=1}
      if(ret){assert(pending.nonEmpty);returned+=1;pending=None}
      if(newRead.nonEmpty)pending=newRead
      if(yes(d.io.matrix.done.valid)&&yes(d.io.matrix.done.ready))matrixDone=true
      if(yes(d.io.done.valid)){
        assert(fault && matrixDone && pending.isEmpty && accepted==returned)
        assert(num(d.io.done.bits.status)!=0);d.probe.dmaOutstanding.expect(false.B)
        d.probe.queueEmpty.expect(true.B);d.probe.response.expect(false.B);d.probe.holdValid.expect(false.B)
        d.io.done.ready.poke(true.B);done=true
      }
      d.clock.step();cycle+=1
    }
    assert(done,"bounded owner handshake did not drain")
    d.io.job.ready.expect(false.B)
  }
  for(reuse<-Seq(false,true)){
    it should s"preserve every packet and private A copy with reuse=$reuse" in {
      test(new AHoldProbe(reuse)){d=>exercise(d,reuse,32,false)}
    }
  }
  it should "suppress same-edge bank work on an accepted malformed DMA return and drain debt" in {
    test(new AHoldProbe(true)){d=>exercise(d,true,256,true)}
  }
}
