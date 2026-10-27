// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

/** Coordinator-only DUT. Leaf completion fixtures are synthetic control
  * receipts, not executed arithmetic or fullblock numerical qualification. */
class GdnChunkCoordinatorFaultSpec extends AnyFlatSpec with ChiselScalatestTester {
  val tag=BigInt("88776655",16)
  def zero(x:Data):Unit=x match {
    case b:Bool=>b.poke(false.B)
    case u:UInt=>u.poke(0.U)
    case b:Bundle=>b.elements.values.foreach(zero)
    case v:Vec[_]=>v.foreach(x=>zero(x))
    case _=>throw new IllegalArgumentException("unsupported fixture field")
  }
  def context(x:GdnChunkJob):Unit={
    x.tag.poke(tag.U);x.tokens.poke(16.U);x.cold.poke(true.B);x.expectedGeneration.poke(0.U);x.vectorPolicy.poke(1.U)
    x.input.poke("h10000000".U);x.stateIn.poke("h20000000".U);x.stateOut.poke("h30000000".U)
    x.output.poke("h40000000".U);x.scratch.poke("h50000000".U)
  }
  def layout(x:GdnRuntimeChunkLayout):Unit={x.keyHeads.poke(16.U);x.valueHeads.poke(16.U);x.layoutId.poke(0.U);x.layoutVersion.poke(1.U);x.rowBytes.poke(25600.U)}
  def receipt(x:GdnChunkStageReceipt,phase:Int,bytes:Int,output:Boolean=false):Unit={
    x.tag.poke(tag.U);x.expectedGeneration.poke(0.U);x.head.poke(0.U);x.chunk.poke(0.U);x.phase.poke(phase.U);x.status.poke(Status.Ok.U);x.drained.poke(true.B)
    x.scratchAckBytes.poke((if(output)0 else bytes).U);x.outputAckBytes.poke((if(output)bytes else 0).U);x.stateAckBytes.poke(0.U)
  }
  def decay(x:GdnRuntimeChunkPrivateDecay):Unit={context(x.context);layout(x.layout);x.head.poke(0.U);x.chunk.poke(0.U);x.value.poke("h3f800000".U);x.valid.poke(true.B)}
  def init(d:GdnRuntimeChunkCoordinator):Unit={
    zero(d.io.job.bits);zero(d.io.committed);zero(d.io.prepDone.bits);zero(d.io.stateDone.bits)
    zero(d.io.loadDone.bits);zero(d.io.derivedDone.bits);zero(d.io.transposeDone.bits);zero(d.io.executeDone.bits)
    d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.prepDone.valid.poke(false.B)
    d.io.stateDone.valid.poke(false.B);d.io.loadDone.valid.poke(false.B);d.io.derivedDone.valid.poke(false.B);d.io.transposeDone.valid.poke(false.B);d.io.executeDone.valid.poke(false.B)
    d.io.stateJob.ready.poke(false.B);d.io.loadJob.ready.poke(false.B);d.io.derivedJob.ready.poke(false.B);d.io.transposeJob.ready.poke(false.B);d.io.executeJob.ready.poke(false.B)
    d.io.fabricFault.poke(false.B);d.io.fabricFaultStatus.poke(Status.Protocol.U);d.io.fabricDrained.poke(true.B)
    d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);d.clock.step()
    context(d.io.job.bits.context);layout(d.io.job.bits.layout)
    d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
    val r=d.io.prepDone.bits;val a=r.accepted
    a.tokens.poke(16.U);layout(a.layout);a.output.poke("h10000000".U);a.tag.poke(tag.U)
    a.conv.poke("h60000000".U);a.ab.poke("h61000000".U);a.aLog.poke("h62000000".U);a.dtBias.poke("h63000000".U)
    r.tag.poke(tag.U);r.status.poke(Status.Ok.U);r.writeBytes.poke(409600.U);r.outputCommitted.poke(true.B)
    d.io.prepDone.valid.poke(true.B);d.io.prepDone.ready.expect(true.B);d.clock.step();d.io.prepDone.valid.poke(false.B)
    d.io.stateJob.valid.expect(true.B)
  }
  def stateReply(d:GdnRuntimeChunkCoordinator,op:Int,wrong:Boolean=false):Unit={
    val r=d.io.stateDone.bits;r.tag.poke((if(wrong)tag^1 else tag).U);r.expectedGeneration.poke(0.U);r.head.poke(0.U);r.operation.poke(op.U)
    r.status.poke(Status.Ok.U);r.readBytes.poke((if(op==0)0 else 65536).U);r.writeBytes.poke(65536.U);r.transferComplete.poke(true.B);r.localDrained.poke(true.B)
    d.io.stateDone.valid.poke(true.B);d.io.stateDone.ready.expect(true.B);d.clock.step();d.io.stateDone.valid.poke(false.B)
  }
  it should "hold initialization offer and retain owned debt on wrong identity after fault" in {
    test(new GdnRuntimeChunkCoordinator){d=>
      init(d);d.clock.step();d.io.fabricFault.poke(true.B)
      for(_<-0 until 4){d.io.stateJob.valid.expect(true.B);d.io.stateJob.bits.operation.expect(0.U);d.io.stateJob.bits.context.tag.expect(tag.U);d.clock.step()}
      d.io.stateJob.ready.poke(true.B);d.clock.step();d.io.stateJob.ready.poke(false.B);d.io.fabricFault.poke(false.B)
      stateReply(d,0,wrong=true);d.clock.step(4)
      d.io.resetRequired.expect(true.B);d.io.done.valid.expect(false.B);d.io.stateDone.ready.expect(true.B)
      d.io.loadJob.valid.expect(false.B) // wrong response did not discharge actual pending initialization.
    }
  }
  it should "retain export operation identity through poisonWait and keep terminal held" in {
    test(new GdnRuntimeChunkCoordinator){d=>
      init(d);d.io.stateJob.ready.poke(true.B);d.clock.step();d.io.stateJob.ready.poke(false.B);stateReply(d,0)
      d.io.loadJob.valid.expect(true.B);d.io.loadJob.ready.poke(true.B);d.clock.step();d.io.loadJob.ready.poke(false.B)
      val l=d.io.loadDone.bits;receipt(l.receipt,1,102400);l.readBytes.poke(25600.U);l.addRequests.poke(64.U);l.addResults.poke(64.U);l.stageComplete.poke(true.B)
      d.io.loadDone.valid.poke(true.B);d.clock.step();d.io.loadDone.valid.poke(false.B)
      d.io.derivedJob.valid.expect(true.B);d.io.derivedJob.ready.poke(true.B);d.clock.step();d.io.derivedJob.ready.poke(false.B)
      val r=d.io.derivedDone.bits;receipt(r.receipt,2,180224);decay(r.decay);r.readBytes.poke(235584.U)
      r.expRequests.poke(2209.U);r.expResults.poke(2209.U);r.addRequests.poke(2144.U);r.addResults.poke(2144.U);r.mulRequests.poke(2560.U);r.mulResults.poke(2560.U);r.stageComplete.poke(true.B)
      d.io.derivedDone.valid.poke(true.B);d.clock.step();d.io.derivedDone.valid.poke(false.B)
      d.io.transposeJob.valid.expect(true.B);d.io.transposeJob.ready.poke(true.B);d.clock.step();d.io.transposeJob.ready.poke(false.B)
      val t=d.io.transposeDone.bits;receipt(t.phase3,3,32768);receipt(t.phase4,4,32768);decay(t.decay)
      t.phase3ReadBytes.poke(32768.U);t.phase4ReadBytes.poke(32768.U);t.phase3Complete.poke(true.B);t.phase4Complete.poke(true.B);t.stageComplete.poke(true.B);t.drained.poke(true.B);t.status.poke(Status.Ok.U)
      d.io.transposeDone.valid.poke(true.B);d.clock.step();d.io.transposeDone.valid.poke(false.B)
      for(p<-5 to 17){
        d.io.executeJob.valid.expect(true.B);d.io.executeJob.bits.phase.expect(p.U);d.io.executeJob.ready.poke(true.B);d.clock.step();d.io.executeJob.ready.poke(false.B)
        val e=d.io.executeDone.bits;context(e.context);layout(e.layout)
        val bytes=if(p==17)4096 else if(p>=14)65536 else if(p<=6)16384 else 32768
        receipt(e.receipt,p,bytes,output=p==17);e.stageComplete.poke(true.B)
        d.io.executeDone.valid.poke(true.B);d.clock.step();d.io.executeDone.valid.poke(false.B)
      }
      d.io.stateJob.valid.expect(true.B);d.io.stateJob.bits.operation.expect(1.U);d.clock.step()
      d.io.fabricFault.poke(true.B)
      for(_<-0 until 4){d.io.stateJob.valid.expect(true.B);d.io.stateJob.bits.operation.expect(1.U);d.io.stateJob.bits.head.expect(0.U);d.clock.step()}
      d.io.stateJob.ready.poke(true.B);d.clock.step();d.io.stateJob.ready.poke(false.B)
      d.io.fabricFault.poke(false.B);stateReply(d,1);d.clock.step()
      d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(Status.Protocol.U);d.io.done.bits.stagedComplete.expect(false.B);d.io.done.bits.drained.expect(true.B)
      d.io.done.bits.jobsIssued.expect(18.U);d.io.done.bits.jobsCompleted.expect(18.U)
      d.io.fabricFaultStatus.poke(Status.Memory.U);d.io.fabricFault.poke(true.B);d.clock.step(3)
      d.io.done.valid.expect(true.B);d.io.done.bits.status.expect(Status.Protocol.U);d.io.done.bits.jobsCompleted.expect(18.U);d.io.resetRequired.expect(true.B)
    }
  }
}
