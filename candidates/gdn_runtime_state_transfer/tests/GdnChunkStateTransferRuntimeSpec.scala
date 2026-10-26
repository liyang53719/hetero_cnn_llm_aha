package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec

/** Actual bitwise transport for the 32-head private state span, not chunk
  * arithmetic, producer provenance, external DDR, or complete block commit. */
class GdnChunkStateTransferRuntimeSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "fixed-max32 runtime16_32 private state transfer"
  private val input = BigInt("01000000",16)
  private val stateIn = BigInt("02000000",16)
  private val stateOut = BigInt("03000000",16)
  private val output = BigInt("04000000",16)
  private val scratch = BigInt("08000000",16)
  private val tag = BigInt("aabbccdd",16)
  private val stride = BigInt(1679360)
  private val bytesPerHead = BigInt(65536)
  private val fullMask = (BigInt(1)<<64)-1
  private def initialize(d: GdnChunkStateTransferOwner, operation: Int, cold: Boolean, activeHeads: Int = 32, resetHardware: Boolean = true): Unit = {
    d.clock.setTimeout(100000)
    d.io.job.valid.poke(false.B); d.io.done.ready.poke(false.B)
    d.io.memory.ready.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.response.bits.tag.poke(0.U); d.io.response.bits.data.poke(0.U); d.io.response.bits.error.poke(false.B)
    val j=d.io.job.bits; val c=j.context
    c.tag.poke(tag.U); c.tokens.poke(128.U); c.cold.poke(cold.B)
    c.expectedGeneration.poke((if(cold)0 else 7).U); c.vectorPolicy.poke(0.U)
    c.input.poke(input.U); c.stateIn.poke(stateIn.U); c.stateOut.poke(stateOut.U)
    c.output.poke(output.U); c.scratch.poke(scratch.U)
    j.activeHeads.poke(activeHeads.U); j.head.poke((activeHeads-1).U); j.operation.poke(operation.U)
    for ((r,phase)<-Seq((j.nextStateReady,16),(j.outputReady,17))) {
      r.tag.poke(tag.U); r.expectedGeneration.poke((if(cold)0 else 7).U)
      r.head.poke((activeHeads-1).U); r.chunk.poke(1.U); r.phase.poke(phase.U)
      r.status.poke(0.U); r.scratchAckBytes.poke((if(phase==16)65536 else 0).U)
      r.outputAckBytes.poke((if(phase==17)16384 else 0).U); r.stateAckBytes.poke(0.U); r.drained.poke(true.B)
    }
    d.io.committed.valid.poke((!cold).B); d.io.committed.generation.poke((if(cold)0 else 7).U)
    d.io.committed.state.poke((if(cold)BigInt(0) else stateIn).U)
    if(resetHardware){d.reset.poke(true.B); d.clock.step(2); d.reset.poke(false.B); d.clock.step()}
    assert(j.nextStateReady.head.getWidth==5 && j.outputReady.head.getWidth==5)
  }
  private def launch(d:GdnChunkStateTransferOwner):Unit={
    d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
  }
  private def run(d:GdnChunkStateTransferOwner, operation:Int,cold:Boolean,lastError:Boolean=false, activeHeads:Int=32, resetHardware:Boolean=true, perturbBusyConfig:Boolean=false):Unit={
    initialize(d,operation,cold,activeHeads,resetHardware); launch(d)
    var sequence=0
    def request(write:Boolean,address:BigInt,data:BigInt):Unit={
      d.io.memory.valid.expect(true.B);d.io.memory.bits.write.expect(write.B)
      d.io.memory.bits.address.expect(address.U);d.io.memory.bits.data.expect((if(write)data else BigInt(0)).U)
      d.io.memory.bits.mask.expect((if(write)fullMask else BigInt(0)).U)
      d.io.memory.bits.tag.expect(((tag<<32)|sequence).U)
      d.io.response.ready.expect(false.B);d.io.done.valid.expect(false.B)
    }
    def transfer(write:Boolean,address:BigInt,data:BigInt,error:Boolean):Unit={
      d.io.memory.ready.poke(false.B);request(write,address,data);d.clock.step();request(write,address,data)
      d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
      d.io.memory.valid.expect(false.B);d.io.response.ready.expect(true.B)
      d.io.response.bits.tag.poke(((tag<<32)|sequence).U);d.io.response.bits.data.poke(data.U)
      d.io.response.bits.error.poke(error.B);d.io.response.valid.poke(false.B);d.clock.step()
      d.io.done.valid.expect(false.B);d.io.response.valid.poke(true.B);d.clock.step();d.io.response.valid.poke(false.B)
      sequence+=1
    }
    for(i<-0 until 1024){
      if(perturbBusyConfig){
        // No job is valid; unrelated configuration pin changes must not alter
        // the accepted transaction's latched addresses or terminal identity.
        d.io.job.bits.activeHeads.poke((if(i%2==0)0 else 16).U)
        d.io.job.bits.head.poke((if(i%2==0)0 else 15).U)
        d.io.job.ready.expect(false.B)
      }
      val value=if(cold&&operation==0)BigInt(0) else (BigInt(i+1)<<480)|BigInt(i+17)
      val source=if(operation==0)stateIn+(activeHeads-1)*bytesPerHead else scratch+(activeHeads-1)*stride+1613824
      val target=if(operation==0)scratch+(activeHeads-1)*stride else stateOut+(activeHeads-1)*bytesPerHead
      if(!(cold&&operation==0))transfer(false,source+i*64,value,false)
      transfer(true,target+i*64,value,lastError&&i==1023)
    }
    d.io.done.valid.expect(true.B);d.io.done.bits.head.expect((activeHeads-1).U)
    d.io.done.bits.expectedGeneration.expect((if(cold)0 else 7).U)
    d.io.done.bits.readBytes.expect((if(cold&&operation==0)0 else 65536).U)
    d.io.done.bits.writeBytes.expect((if(lastError)65472 else 65536).U)
    d.io.done.bits.status.expect((if(lastError)Status.Memory else Status.Ok).U)
    d.io.done.bits.transferComplete.expect((!lastError).B);d.io.done.bits.localDrained.expect((!lastError).B)
    d.io.resetRequired.expect(lastError.B)
    val cycles=d.io.done.bits.cycles.peek().litValue
    for(_<-0 until 4){d.io.done.valid.expect(true.B);d.io.done.bits.cycles.expect(cycles.U);d.io.memory.valid.expect(false.B);d.clock.step()}
    d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B)
    d.io.job.ready.expect((!lastError).B);d.io.done.valid.expect(false.B)
  }
  it should "switch runtime16 and runtime32 cold warm export without reset or re-elaboration" in {
    test(new GdnChunkStateTransferOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      run(d,0,true,activeHeads=16)
      run(d,0,true,activeHeads=32,resetHardware=false,perturbBusyConfig=true)
      run(d,0,false,activeHeads=16,resetHardware=false)
      run(d,0,false,activeHeads=32,resetHardware=false,perturbBusyConfig=true)
      run(d,1,false,activeHeads=16,resetHardware=false)
      run(d,1,false,activeHeads=32,resetHardware=false,perturbBusyConfig=true)
    }
  }
  it should "withhold completion and lock after the final write ACK reports an error" in {
    test(new GdnChunkStateTransferOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>run(d,0,true,lastError=true)}
  }
  it should "reject widened-span aliases head overflow and receipt truncation before memory requests" in {
    test(new GdnChunkStateTransferOwner).withAnnotations(Seq(TreadleBackendAnnotation)){d=>
      val cases=Seq[(Int,()=>Unit)](
        (Status.Bounds,()=>d.io.job.bits.activeHeads.poke(0.U)),
        (Status.Bounds,()=>d.io.job.bits.activeHeads.poke(17.U)),
        (Status.Bounds,()=>d.io.job.bits.activeHeads.poke(33.U)),
        (Status.Bounds,()=>d.io.job.bits.head.poke(32.U)),
        (Status.Bounds,()=>{d.io.job.bits.activeHeads.poke(16.U);d.io.job.bits.head.poke(16.U)}),
        (Status.Bounds,()=>d.io.job.bits.context.stateOut.poke((stateIn+1048576).U)),
        (Status.Bounds,()=>d.io.job.bits.context.stateOut.poke((scratch+30*1024*1024).U)),
        (Status.Bounds,()=>d.io.job.bits.context.stateOut.poke(((BigInt(1)<<56)-1048576).U)),
        (Status.Dependency,()=>d.io.job.bits.nextStateReady.head.poke(15.U)),
        (Status.Dependency,()=>d.io.job.bits.outputReady.head.poke(15.U)))
      for((status,change)<-cases){
        initialize(d,1,false);change();launch(d)
        d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(status.U)
        d.io.done.bits.transferComplete.expect(false.B);d.io.done.bits.writeBytes.expect(0.U)
        d.io.memory.valid.expect(false.B);d.io.response.ready.expect(false.B)
      }
    }
  }
}
