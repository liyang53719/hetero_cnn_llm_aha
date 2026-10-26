// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Control/address regression only. Exp/loan results are protocol responders,
  * NOT HardFloat or Vector numerical verification. Each run is one head/chunk,
  * not all heads, a full GDN block, or physical4096 acceptance. */
class GdnRuntimeChunkPhases234Spec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "fixed-max32 runtime GDN phases2/3/4"
  private val input=BigInt("01000000",16);private val si=BigInt("02000000",16)
  private val so=BigInt("03000000",16);private val output=BigInt("04000000",16)
  private val scratch=BigInt("08000000",16);private val tag=BigInt("13456789",16)
  private val full=(BigInt(1)<<64)-1;private val one=BigInt("3f800000",16)
  private def pack(words:Seq[BigInt]):BigInt=words.zipWithIndex.map{case(w,i)=>w<<(32*i)}.sum
  private def layout(p:GdnRuntimeChunkLayout,h:Int):Unit={p.keyHeads.poke(16.U);p.valueHeads.poke(h.U);p.layoutId.poke(0.U);p.layoutVersion.poke(1.U);p.rowBytes.poke((h*1600).U)}
  private def context(c:GdnChunkJob):Unit={
    c.tag.poke(tag.U);c.tokens.poke(128.U);c.cold.poke(true.B);c.expectedGeneration.poke(0.U);c.vectorPolicy.poke(0.U)
    c.input.poke(input.U);c.stateIn.poke(si.U);c.stateOut.poke(so.U);c.output.poke(output.U);c.scratch.poke(scratch.U)
  }
  private def receipt(p:GdnChunkStageReceipt,h:Int,c:Int,phase:Int,bytes:Int):Unit={
    p.tag.poke(tag.U);p.expectedGeneration.poke(0.U);p.head.poke((h-1).U);p.chunk.poke(c.U);p.phase.poke(phase.U);p.status.poke(0.U)
    p.scratchAckBytes.poke(bytes.U);p.outputAckBytes.poke(0.U);p.stateAckBytes.poke(0.U);p.drained.poke(true.B)
  }
  private def phase1(p:GdnRuntimeChunkLoadPrepResult,h:Int,c:Int):Unit={
    receipt(p.receipt,h,c,1,102400);p.readBytes.poke(102400.U);p.addRequests.poke(64.U);p.addResults.poke(64.U);p.cycles.poke(0.U);p.stageComplete.poke(true.B)
  }
  private def phase2(p:GdnRuntimeChunkDerivedAndPairResult,h:Int,c:Int):Unit={
    receipt(p.receipt,h,c,2,180224);context(p.decay.context);layout(p.decay.layout,h);p.decay.head.poke((h-1).U);p.decay.chunk.poke(c.U);p.decay.value.poke(one.U);p.decay.valid.poke(true.B)
    p.readBytes.poke(235584.U);p.expRequests.poke(2209.U);p.expResults.poke(2209.U);p.addRequests.poke(2144.U);p.addResults.poke(2144.U);p.mulRequests.poke(2560.U);p.mulResults.poke(2560.U);p.cycles.poke(0.U);p.stageComplete.poke(true.B)
  }
  private def initD(d:GdnRuntimeChunkDerivedAndPairOwner,h:Int,c:Int,reset:Boolean=true):Unit={
    d.clock.setTimeout(250000);d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B);d.io.scalar.result.bits.poke(0.U);d.io.scalar.error.poke(false.B)
    d.io.loan.request.ready.poke(false.B);d.io.loan.result.valid.poke(false.B);d.io.loan.result.bits.tag.poke(0.U);d.io.loan.result.bits.status.poke(0.U);d.io.loan.result.bits.value.poke(0.U);d.io.loan.busy.poke(false.B);d.io.loan.resetRequired.poke(false.B)
    d.io.committed.valid.poke(false.B);d.io.committed.generation.poke(0.U);d.io.committed.state.poke(0.U)
    val j=d.io.job.bits;context(j.context);layout(j.layout,h);j.head.poke((h-1).U);j.chunk.poke(c.U);context(j.phase1Context);layout(j.phase1Layout,h);phase1(j.phase1Ready,h,c)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()}
    assert(j.head.getWidth==5 && d.io.done.bits.decay.head.getWidth==5)
  }
  private def initT(d:GdnRuntimeChunkTransposeOwner,h:Int,c:Int,reset:Boolean=true):Unit={
    d.clock.setTimeout(100000);d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
    d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.committed.valid.poke(false.B);d.io.committed.generation.poke(0.U);d.io.committed.state.poke(0.U)
    val j=d.io.job.bits;context(j.context);layout(j.layout,h);j.head.poke((h-1).U);j.chunk.poke(c.U);phase2(j.phase2Ready,h,c)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()}
    assert(j.head.getWidth==5 && d.io.done.bits.decay.head.getWidth==5)
  }
  private def launch(d:GdnRuntimeChunkDerivedAndPairOwner):Unit={d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)}
  private def launch(d:GdnRuntimeChunkTransposeOwner):Unit={d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)}
  private case class Mem(write:Boolean,offset:Int,data:BigInt=BigInt(0))
  private def derivedMemory:Vector[Mem]={
    val b=Vector.newBuilder[Mem];b+=Mem(false,63*64)
    for(row<-0 until 64){
      b+=Mem(false,row*64)
      for(beat<-0 until 8){val off=row*512+beat*64;b+=Mem(false,36864+off);b+=Mem(false,4096+off)
        for(start<-Seq(102400,167936,200704,233472))b+=Mem(true,start+off)}
      for(beat<-0 until 8){val off=row*512+beat*64;b+=Mem(false,69632+off);b+=Mem(true,135168+off)}
      for(beat<-0 until 4){for(earlier<-beat*16 until math.min(row+1,(beat+1)*16))b+=Mem(false,earlier*64)
        b+=Mem(true,331776+row*256+beat*64,pack((0 until 16).map(i=>if(beat*16+i<=row)one else BigInt(0))))}
    };b.result()
  }
  private def runD(d:GdnRuntimeChunkDerivedAndPairOwner,h:Int,c:Int,reset:Boolean,lastError:Boolean=false):Unit={
    initD(d,h,c,reset);launch(d);val expected=derivedMemory;val base=scratch+(h-1)*1679360+65536+c*806912
    var mem=0;var exp=0;var adds=0;var muls=0;var loan=0;var ticks=0
    while(!d.io.done.valid.peek().litToBoolean && ticks<100000){
      d.io.job.bits.layout.valueHeads.poke(0.U);d.io.job.bits.head.poke(0.U);d.io.job.bits.context.scratch.poke(0.U)
      d.io.job.ready.expect(false.B);d.io.loan.abort.expect(false.B);d.io.loan.resetLoan.expect(false.B)
      if(d.io.memory.valid.peek().litToBoolean){
        assert(mem<expected.size);val e=expected(mem);d.io.memory.bits.write.expect(e.write.B);d.io.memory.bits.address.expect((base+e.offset).U)
        d.io.memory.bits.data.expect((if(e.write)e.data else BigInt(0)).U);d.io.memory.bits.mask.expect((if(e.write)full else BigInt(0)).U);d.io.memory.bits.tag.expect(((tag<<32)|mem).U)
        if(mem%521==0){d.clock.step();d.io.memory.bits.address.expect((base+e.offset).U)}
        d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B);d.io.response.ready.expect(true.B)
        d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(((tag<<32)|mem).U);d.io.response.bits.error.poke((lastError && mem==expected.size-1).B)
        d.io.response.valid.poke(true.B);d.clock.step();d.io.response.valid.poke(false.B);mem+=1
      } else if(d.io.scalar.request.valid.peek().litToBoolean){
        d.io.scalar.request.bits.op.expect(ScalarOp.ExpNegative.U);d.io.scalar.request.bits.a.expect(0.U);d.io.scalar.request.bits.b.expect(0.U)
        d.io.scalar.request.ready.poke(true.B);d.clock.step();d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.ready.expect(true.B)
        d.io.scalar.result.bits.poke(one.U);d.io.scalar.result.valid.poke(true.B);d.clock.step();d.io.scalar.result.valid.poke(false.B);exp+=1
      } else if(d.io.loan.request.valid.peek().litToBoolean){
        val op=d.io.loan.request.bits.op.peek().litValue;assert(op==1 || op==2);if(op==1)adds+=1 else muls+=1
        d.io.loan.request.bits.tag.expect((tag^loan).U);d.io.loan.request.ready.poke(true.B);d.clock.step();d.io.loan.request.ready.poke(false.B)
        d.io.loan.result.ready.expect(true.B);d.io.loan.result.bits.tag.poke((tag^loan).U);d.io.loan.result.bits.status.poke(0.U);d.io.loan.result.bits.value.poke(0.U)
        d.io.loan.result.valid.poke(true.B);d.clock.step();d.io.loan.result.valid.poke(false.B);loan+=1
      } else {d.clock.step()};ticks+=1
    }
    assert(mem==6497 && exp==2209 && adds==2144 && muls==2560)
    d.io.done.valid.expect(true.B);d.io.done.bits.receipt.head.expect((h-1).U);d.io.done.bits.receipt.chunk.expect(c.U)
    d.io.done.bits.decay.layout.valueHeads.expect(h.U);d.io.done.bits.decay.layout.rowBytes.expect((h*1600).U);d.io.done.bits.decay.head.expect((h-1).U)
    d.io.done.bits.stageComplete.expect((!lastError).B);d.io.done.bits.decay.valid.expect((!lastError).B)
    d.io.done.bits.receipt.status.expect((if(lastError)Status.Memory else Status.Ok).U);d.io.done.bits.receipt.scratchAckBytes.expect((180224-(if(lastError)64 else 0)).U)
    d.io.done.bits.readBytes.expect(235584.U);d.io.done.bits.expResults.expect(2209.U);d.io.done.bits.addResults.expect(2144.U);d.io.done.bits.mulResults.expect(2560.U)
    val cycles=d.io.done.bits.cycles.peek().litValue;for(_<-0 until 3){d.clock.step();d.io.done.bits.cycles.expect(cycles.U);d.io.memory.valid.expect(false.B)}
    d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B);d.io.job.ready.expect((!lastError).B)
  }
  private def runT(d:GdnRuntimeChunkTransposeOwner,h:Int,c:Int,reset:Boolean,lastError:Boolean=false):Unit={
    initT(d,h,c,reset);launch(d);val base=scratch+(h-1)*1679360+65536+c*806912;var seq=0
    def word(p:Int,row:Int,col:Int):BigInt=BigInt("3f000000",16)+p*16384+row*128+col // finite and coordinate-distinct
    def transfer(write:Boolean,address:BigInt,data:BigInt,error:Boolean=false):Unit={
      d.io.job.bits.layout.valueHeads.poke(0.U);d.io.job.bits.head.poke(0.U);d.io.job.bits.context.scratch.poke(0.U)
      d.io.memory.valid.expect(true.B);d.io.memory.bits.write.expect(write.B);d.io.memory.bits.address.expect(address.U)
      d.io.memory.bits.data.expect((if(write)data else BigInt(0)).U);d.io.memory.bits.mask.expect((if(write)full else BigInt(0)).U);d.io.memory.bits.tag.expect(((tag<<32)|seq).U)
      if(seq%257==0){d.clock.step();d.io.memory.bits.address.expect(address.U)}
      d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B);d.io.response.ready.expect(true.B)
      d.io.response.bits.data.poke(data.U);d.io.response.bits.tag.poke(((tag<<32)|seq).U);d.io.response.bits.error.poke(error.B)
      d.io.response.valid.poke(true.B);d.clock.step();d.io.response.valid.poke(false.B);seq+=1
    }
    for(p<-0 until 2;tr<-0 until 4;tc<-0 until 8){
      for(i<-0 until 16)transfer(false,base+Seq(36864,233472)(p)+(tr*16+i)*512+tc*64,pack((0 until 16).map(k=>word(p,tr*16+i,tc*16+k))))
      for(i<-0 until 16)transfer(true,base+Seq(266240,299008)(p)+(tc*16+i)*256+tr*64,pack((0 until 16).map(k=>word(p,tr*16+k,tc*16+i))),lastError && p==1 && tr==3 && tc==7 && i==15)
    }
    assert(seq==2048);d.io.done.valid.expect(true.B);d.io.done.bits.stageComplete.expect((!lastError).B);d.io.done.bits.phase3Complete.expect(true.B)
    d.io.done.bits.phase3.scratchAckBytes.expect(32768.U);d.io.done.bits.phase4.scratchAckBytes.expect((32768-(if(lastError)64 else 0)).U)
    d.io.done.bits.decay.layout.valueHeads.expect(h.U);d.io.done.bits.decay.head.expect((h-1).U);d.io.done.bits.decay.chunk.expect(c.U)
    d.io.done.bits.decay.valid.expect((!lastError).B);d.io.done.bits.status.expect((if(lastError)Status.Memory else Status.Ok).U)
    val cycles=d.io.done.bits.cycles.peek().litValue;for(_<-0 until 3){d.clock.step();d.io.done.bits.cycles.expect(cycles.U);d.io.memory.valid.expect(false.B)}
    d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B);d.io.job.ready.expect((!lastError).B)
  }
  it should "complete phase2 on one DUT for16 then32 then16 without reset between jobs" in {
    test(new GdnRuntimeChunkDerivedAndPairOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      runD(d,16,0,reset=true);runD(d,32,1,reset=false);runD(d,16,1,reset=false)
    }
  }
  it should "transpose real finite bits on one DUT for16 then32 then16" in {
    test(new GdnRuntimeChunkTransposeOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      runT(d,16,0,reset=true);runT(d,32,1,reset=false);runT(d,16,1,reset=false)
    }
  }
  it should "reject malformed runtime layouts stale phase1 leases head overflow and widened spans before phase2 I/O" in {
    test(new GdnRuntimeChunkDerivedAndPairOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      val j=d.io.job.bits;val cases=Seq[(Int,()=>Unit)](
        (Status.Bounds,()=>j.layout.keyHeads.poke(32.U)),(Status.Bounds,()=>j.layout.valueHeads.poke(17.U)),
        (Status.Bounds,()=>j.layout.layoutId.poke(1.U)),(Status.Bounds,()=>j.layout.layoutVersion.poke(0.U)),(Status.Bounds,()=>j.layout.rowBytes.poke(34816.U)),
        (Status.Bounds,()=>{layout(j.layout,16);j.head.poke(16.U)}),
        (Status.Dependency,()=>j.phase1Layout.valueHeads.poke(16.U)),(Status.Dependency,()=>j.phase1Ready.receipt.head.poke(15.U)),
        (Status.Dependency,()=>j.phase1Ready.receipt.chunk.poke(0.U)),(Status.Dependency,()=>j.phase1Context.scratch.poke(0.U)),
        (Status.Bounds,()=>j.context.stateOut.poke((si+1048576).U)),(Status.Bounds,()=>j.context.stateOut.poke((scratch+30*1024*1024).U)))
      for((status,change)<-cases){initD(d,32,1);change();launch(d);d.io.done.valid.expect(true.B);d.io.done.bits.receipt.status.expect(status.U);d.io.done.bits.stageComplete.expect(false.B);d.io.memory.valid.expect(false.B);d.io.scalar.request.valid.expect(false.B);d.io.loan.request.valid.expect(false.B)}
    }
  }
  it should "reject phase2-decay layout/head truncation and preserve phase3 ACK checkpoint after final phase4 failure" in {
    test(new GdnRuntimeChunkTransposeOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      val j=d.io.job.bits;val cases=Seq[(Int,()=>Unit)](
        (Status.Dependency,()=>j.phase2Ready.decay.layout.valueHeads.poke(16.U)),(Status.Dependency,()=>j.phase2Ready.decay.layout.rowBytes.poke(25600.U)),
        (Status.Dependency,()=>j.phase2Ready.decay.head.poke(15.U)),(Status.Dependency,()=>j.phase2Ready.receipt.head.poke(15.U)),
        (Status.Dependency,()=>j.phase2Ready.decay.context.scratch.poke(0.U)),(Status.Dependency,()=>j.phase2Ready.mulResults.poke(2559.U)),
        (Status.Bounds,()=>j.layout.keyHeads.poke(32.U)),(Status.Bounds,()=>j.layout.valueHeads.poke(17.U)),
        (Status.Bounds,()=>j.layout.layoutId.poke(1.U)),(Status.Bounds,()=>j.layout.rowBytes.poke(34816.U)),
        (Status.Bounds,()=>j.context.stateOut.poke((si+1048576).U)),(Status.Bounds,()=>j.context.stateOut.poke((scratch+30*1024*1024).U)))
      for((status,change)<-cases){initT(d,32,1);change();launch(d);d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(status.U);d.io.done.bits.stageComplete.expect(false.B);d.io.memory.valid.expect(false.B)}
      runT(d,32,1,reset=true,lastError=true)
    }
  }
}
