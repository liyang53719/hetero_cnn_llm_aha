// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Real owner control/address/DDR-copy test. The external scalar service is a
  * deterministic protocol responder, not HardFloat arithmetic qualification.
  * No Matrix is instantiated or replaced by a smaller Matrix. No block claim. */
class GdnRuntimeChunkLoadPrepSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "fixed-max32 prepared chunk64 load phase"
  private val in = BigInt("01000000",16)
  private val si = BigInt("02000000",16)
  private val so = BigInt("03000000",16)
  private val out = BigInt("04000000",16)
  private val sc = BigInt("08000000",16)
  private val tag = BigInt("23456789",16)
  private val full = (BigInt(1)<<64)-1
  private def bits(f:Float):BigInt=BigInt(java.lang.Float.floatToRawIntBits(f).toLong & 0xffffffffL)
  private def packed(words:Seq[BigInt]):BigInt=words.zipWithIndex.map{case(w,i)=>w<<(32*i)}.sum
  private def init(d:GdnRuntimeChunkLoadPrepOwner,heads:Int,chunk:Int,tokens:Int=128,reset:Boolean=true):Unit={
    d.clock.setTimeout(150000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B); d.io.memory.ready.poke(false.B)
    d.io.response.valid.poke(false.B); d.io.response.bits.tag.poke(0.U); d.io.response.bits.data.poke(0.U); d.io.response.bits.error.poke(false.B)
    d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B);d.io.scalar.result.bits.poke(0.U);d.io.scalar.error.poke(false.B)
    val j=d.io.job.bits; val c=j.context
    c.tag.poke(tag.U);c.tokens.poke(tokens.U);c.cold.poke(true.B);c.expectedGeneration.poke(0.U);c.vectorPolicy.poke(0.U)
    c.input.poke(in.U);c.stateIn.poke(si.U);c.stateOut.poke(so.U);c.output.poke(out.U);c.scratch.poke(sc.U)
    j.keyHeads.poke(16.U);j.valueHeads.poke(heads.U);j.head.poke((heads-1).U);j.chunk.poke(chunk.U)
    val p=j.prepReady;p.tag.poke(tag.U);p.expectedGeneration.poke(0.U);p.tokens.poke(tokens.U);p.input.poke(in.U)
    p.status.poke(0.U);p.writeBytes.poke((tokens*heads*1600).U);p.preparedComplete.poke(true.B);p.drained.poke(true.B);p.recurrentMode.poke(false.B)
    p.layoutId.poke(0.U);p.layoutVersion.poke(1.U);p.rowBytes.poke((heads*1600).U);p.keyHeads.poke(16.U);p.valueHeads.poke(heads.U)
    for((r,phase)<-Seq((j.initialReady,0),(j.previousStateReady,16),(j.previousOutputReady,17))){
      r.tag.poke(tag.U);r.expectedGeneration.poke(0.U);r.head.poke((heads-1).U);r.chunk.poke(0.U);r.phase.poke(phase.U);r.status.poke(0.U);r.drained.poke(true.B)
      r.scratchAckBytes.poke((if(phase==17)0 else 65536).U);r.outputAckBytes.poke((if(phase==17)16384 else 0).U);r.stateAckBytes.poke(0.U)
    }
    d.io.committed.valid.poke(false.B);d.io.committed.generation.poke(0.U);d.io.committed.state.poke(0.U)
    if(reset){d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()}
    assert(j.head.getWidth==5 && d.io.done.bits.receipt.head.getWidth==5)
  }
  private def launch(d:GdnRuntimeChunkLoadPrepOwner):Unit={d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)}
  private def run(d:GdnRuntimeChunkLoadPrepOwner,heads:Int,chunk:Int,tokens:Int=128,reset:Boolean=true,lastWriteError:Boolean=false):Unit={
    init(d,heads,chunk,tokens,reset);launch(d)
    val h=heads-1;val rowBytes=heads*1600;val roleBytes=heads*512
    val base=sc+h*(if(tokens==128)1679360 else 872448)+65536+chunk*806912
    var seq=0;var readCount=0;var writeCount=0
    def memory(write:Boolean,address:BigInt,data:BigInt,error:Boolean=false):Unit={
      // Busy input perturbations cannot change a job accepted earlier.
      d.io.job.bits.valueHeads.poke((if(seq%2==0)0 else 16).U);d.io.job.bits.head.poke(0.U);d.io.job.bits.context.input.poke(0.U)
      d.io.job.ready.expect(false.B);d.io.memory.valid.expect(true.B);d.io.memory.bits.write.expect(write.B)
      d.io.memory.bits.address.expect(address.U);d.io.memory.bits.data.expect((if(write)data else BigInt(0)).U)
      d.io.memory.bits.mask.expect((if(write)full else BigInt(0)).U);d.io.memory.bits.tag.expect(((tag<<32)|seq).U)
      if(seq%257==0){d.clock.step();d.io.memory.bits.address.expect(address.U);d.io.done.valid.expect(false.B)}
      d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
      d.io.response.ready.expect(true.B);d.io.memory.valid.expect(false.B)
      d.io.response.bits.tag.poke(((tag<<32)|seq).U);d.io.response.bits.data.poke(data.U);d.io.response.bits.error.poke(error.B)
      if(seq%257==0){d.clock.step();d.io.done.valid.expect(false.B)}
      d.io.response.valid.poke(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      if(write)writeCount+=1 else readCount+=1;seq+=1
    }
    for(row<-0 until 64){
      val token=chunk*64+row;val valid=token<tokens
      val gate=if(valid)packed(Seq(bits(-0.125f),bits(0.5f))++Seq.fill(14)(BigInt(0))) else BigInt(0)
      if(valid)memory(false,in+token*rowBytes+3*roleBytes+h*64,gate)
      d.io.scalar.request.valid.expect(true.B);d.io.scalar.request.bits.op.expect(ScalarOp.Add.U)
      val preceding=math.min(row,math.max(0,tokens-chunk*64));val included=math.min(row+1,math.max(0,tokens-chunk*64))
      d.io.scalar.request.bits.a.expect((if(preceding==0)BigInt(0) else bits(-0.125f*preceding)).U);d.io.scalar.request.bits.b.expect((if(valid)bits(-0.125f) else BigInt(0)).U)
      d.io.scalar.request.ready.poke(true.B);d.clock.step();d.io.scalar.request.ready.poke(false.B)
      d.io.scalar.result.ready.expect(true.B);d.io.scalar.result.bits.poke(bits(-0.125f*included).U);d.io.scalar.result.valid.poke(true.B);d.clock.step();d.io.scalar.result.valid.poke(false.B)
      memory(true,base+row*64,packed(Seq(bits(-0.125f*included),if(valid)bits(0.5f) else BigInt(0))++Seq.fill(14)(BigInt(0))))
      for(role<-0 until 3; beat<-0 until 8){
        // Correct prepared contents preserve official Q/K repeat order. An
        // erroneous second head//2 read accesses a different prepared slot.
        val sourceHead=if(role<2)h/(heads/16) else h
        val data=if(valid)packed((0 until 16).map(i=>bits((1+role*512+sourceHead*16+beat+i).toFloat))) else BigInt(0)
        if(valid)memory(false,in+token*rowBytes+role*roleBytes+h*512+beat*64,data)
        val error=lastWriteError && row==63 && role==2 && beat==7
        memory(true,base+Seq(4096,36864,69632)(role)+row*512+beat*64,data,error)
      }
    }
    d.io.done.valid.expect(true.B);d.io.done.bits.receipt.head.expect(h.U);d.io.done.bits.receipt.chunk.expect(chunk.U)
    d.io.done.bits.receipt.status.expect((if(lastWriteError)Status.Memory else Status.Ok).U)
    d.io.done.bits.stageComplete.expect((!lastWriteError).B);d.io.done.bits.receipt.drained.expect((!lastWriteError).B)
    d.io.done.bits.readBytes.expect((math.min(64,math.max(0,tokens-chunk*64))*1600).U)
    d.io.done.bits.receipt.scratchAckBytes.expect((102400-(if(lastWriteError)64 else 0)).U)
    d.io.done.bits.addRequests.expect(64.U);d.io.done.bits.addResults.expect(64.U)
    assert(readCount==math.min(64,math.max(0,tokens-chunk*64))*25 && writeCount==1600)
    val cycles=d.io.done.bits.cycles.peek().litValue
    for(_<-0 until 3){d.clock.step();d.io.done.valid.expect(true.B);d.io.done.bits.cycles.expect(cycles.U);d.io.memory.valid.expect(false.B)}
    d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B);d.io.job.ready.expect((!lastWriteError).B)
  }
  it should "execute both M128 chunks through one fixed DUT for runtime16 then32 then16" in {
    test(new GdnRuntimeChunkLoadPrepOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      var reset=true
      for(heads<-Seq(16,32,16);chunk<-0 until 2){run(d,heads,chunk,reset=reset);reset=false}
    }
  }
  it should "preserve M16 padding without reading nonexistent tokens" in {
    test(new GdnRuntimeChunkLoadPrepOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>run(d,32,0,tokens=16)}
  }
  it should "reject compact layouts stale dependencies invalid heads and widened-span aliases before I/O" in {
    test(new GdnRuntimeChunkLoadPrepOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      val j=d.io.job.bits
      val cases=Seq[(Int,()=>Unit)](
        (Status.Bounds,()=>j.keyHeads.poke(32.U)),(Status.Bounds,()=>j.valueHeads.poke(17.U)),
        (Status.Bounds,()=>{j.valueHeads.poke(16.U);j.head.poke(16.U)}),
        (Status.Dependency,()=>j.prepReady.layoutId.poke(1.U)),(Status.Dependency,()=>j.prepReady.layoutVersion.poke(0.U)),
        (Status.Dependency,()=>j.prepReady.rowBytes.poke(34816.U)),
        (Status.Dependency,()=>j.prepReady.writeBytes.poke((128*34816).U)),
        (Status.Dependency,()=>j.prepReady.keyHeads.poke(32.U)),(Status.Dependency,()=>j.prepReady.valueHeads.poke(16.U)),
        (Status.Dependency,()=>j.previousStateReady.head.poke(15.U)),(Status.Dependency,()=>j.previousOutputReady.drained.poke(false.B)),
        (Status.Bounds,()=>j.context.stateOut.poke((si+1048576).U)),
        (Status.Bounds,()=>j.context.stateOut.poke((sc+30*1024*1024).U)),
        (Status.Bounds,()=>j.context.input.poke(((BigInt(1)<<56)-128*25600).U)))
      for((status,change)<-cases){init(d,32,1);change();launch(d);d.io.done.valid.expect(true.B);d.io.done.bits.receipt.status.expect(status.U);d.io.done.bits.stageComplete.expect(false.B);d.io.memory.valid.expect(false.B);d.io.scalar.request.valid.expect(false.B);d.io.done.bits.receipt.scratchAckBytes.expect(0.U)}
    }
  }
  it should "withhold completion and lock if the last of1600 write ACKs fails" in {
    test(new GdnRuntimeChunkLoadPrepOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>run(d,32,1,lastWriteError=true)}
  }
}
