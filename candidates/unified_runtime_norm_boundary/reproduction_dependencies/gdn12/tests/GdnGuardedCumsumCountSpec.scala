// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** Actual LoadPrepV2 DUT control/count test, not a numerical qualification.
  * Memory and Scalar replies are deterministic zero fixtures. No HardFloat
  * arithmetic is instantiated or claimed. Every64-row stage performs all
  *1600 reads/1600 ACKed writes and64 or832 actual scalar request/result fires.
  */
class GdnGuardedCumsumCountSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "GdnRuntimeChunkLoadPrepV2Owner exact cumsum issue counters"
  it should "complete legacy then guarded832 then legacy in one fixed DUT" in {
    test(new GdnRuntimeChunkLoadPrepV2Owner){d=>
      val tag=BigInt("77221100",16)
      d.clock.setTimeout(60000)
      d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B)
      d.io.memory.ready.poke(false.B);d.io.response.valid.poke(false.B)
      d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(0.U);d.io.response.bits.error.poke(false.B)
      d.io.scalar.request.ready.poke(false.B);d.io.scalar.result.valid.poke(false.B)
      d.io.scalar.result.bits.policy.poke(0.U);d.io.scalar.result.bits.value.poke(0.U)
      d.io.scalar.result.bits.flags.poke(0.U);d.io.scalar.result.bits.primitiveFlagsValid.poke(true.B);d.io.scalar.result.bits.error.poke(false.B)
      d.io.committed.valid.poke(false.B);d.io.committed.generation.poke(0.U);d.io.committed.state.poke(0.U)
      d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);d.clock.step()
      def receipt(r:GdnChunkStageReceipt,h:Int,p:Int,bytes:Int,output:Boolean=false):Unit={
        r.tag.poke(tag.U);r.expectedGeneration.poke(0.U);r.head.poke(h.U);r.chunk.poke(0.U)
        r.phase.poke(p.U);r.status.poke(Status.Ok.U);r.drained.poke(true.B)
        r.scratchAckBytes.poke((if(output)0 else bytes).U);r.outputAckBytes.poke((if(output)bytes else 0).U);r.stateAckBytes.poke(0.U)
      }
      for((heads,h,chunk,mode)<-Seq((16,15,0,0),(32,31,1,1),(16,15,0,0))){
        val j=d.io.job.bits;val c=j.context
        c.tag.poke(tag.U);c.tokens.poke(128.U);c.cold.poke(true.B);c.expectedGeneration.poke(0.U);c.vectorPolicy.poke(1.U)
        c.input.poke("h10000000".U);c.stateIn.poke("h20000000".U);c.stateOut.poke("h30000000".U);c.output.poke("h40000000".U);c.scratch.poke("h50000000".U)
        j.numeric.cumsum.poke(mode.U);j.numeric.decay.poke(1.U)
        j.keyHeads.poke(16.U);j.valueHeads.poke(heads.U);j.head.poke(h.U);j.chunk.poke(chunk.U)
        val p=j.prepReady;p.tag.poke(tag.U);p.expectedGeneration.poke(0.U);p.tokens.poke(128.U);p.input.poke("h10000000".U)
        p.status.poke(Status.Ok.U);p.writeBytes.poke((128L*heads*1600).U);p.preparedComplete.poke(true.B);p.drained.poke(true.B);p.recurrentMode.poke(false.B)
        p.layoutId.poke(0.U);p.layoutVersion.poke(1.U);p.rowBytes.poke((heads*1600).U);p.keyHeads.poke(16.U);p.valueHeads.poke(heads.U)
        receipt(j.initialReady,h,0,65536);receipt(j.previousStateReady,h,16,65536);receipt(j.previousOutputReady,h,17,16384,true)
        d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
        var reads=0;var writes=0;var adds=0;var quiet=0;var steps=0
        while(!d.io.done.valid.peek().litToBoolean && steps<12000){
          if(d.io.memory.valid.peek().litToBoolean){
            quiet=0;val write=d.io.memory.bits.write.peek().litToBoolean;val t=d.io.memory.bits.tag.peek().litValue
            if(write){d.io.memory.bits.mask.expect(((BigInt(1)<<64)-1).U);writes+=1}else{d.io.memory.bits.mask.expect(0.U);reads+=1}
            d.io.memory.ready.poke(true.B);d.clock.step();steps+=1;d.io.memory.ready.poke(false.B)
            d.io.response.bits.data.poke(0.U);d.io.response.bits.tag.poke(t.U);d.io.response.valid.poke(true.B)
            d.io.response.ready.expect(true.B);d.clock.step();steps+=1;d.io.response.valid.poke(false.B)
          }else if(d.io.scalar.request.valid.peek().litToBoolean){
            quiet=0;d.io.scalar.request.bits.policy.expect(UnifiedScalarPolicyV2.Legacy.U)
            d.io.scalar.request.bits.payload.op.expect(ScalarOp.Add.U)
            d.io.scalar.request.ready.poke(true.B);d.clock.step();steps+=1;d.io.scalar.request.ready.poke(false.B)
            d.io.scalar.result.valid.poke(true.B);d.io.scalar.result.ready.expect(true.B)
            d.clock.step();steps+=1;d.io.scalar.result.valid.poke(false.B);adds+=1
          }else{d.clock.step();steps+=1;quiet+=1;assert(quiet<=32,"mock-service-only gap exceeded32; no real fabric latency claim")}
        }
        val expected=if(mode==1)832 else 64
        assert(reads==1600 && writes==1600 && adds==expected,s"full64-row count mode=$mode reads=$reads writes=$writes adds=$adds")
        d.io.done.valid.expect(true.B);d.io.done.bits.receipt.status.expect(Status.Ok.U);d.io.done.bits.stageComplete.expect(true.B)
        d.io.done.bits.numeric.cumsum.expect(mode.U);d.io.done.bits.addRequests.expect(expected.U);d.io.done.bits.addResults.expect(expected.U)
        d.io.done.bits.receipt.scratchAckBytes.expect(102400.U);d.io.done.bits.readBytes.expect(102400.U)
        d.clock.step(3);d.io.done.valid.expect(true.B);d.io.done.bits.addRequests.expect(expected.U);d.io.done.bits.addResults.expect(expected.U)
        d.io.done.ready.poke(true.B);d.clock.step();d.io.done.ready.poke(false.B)
      }
    }
  }
}
