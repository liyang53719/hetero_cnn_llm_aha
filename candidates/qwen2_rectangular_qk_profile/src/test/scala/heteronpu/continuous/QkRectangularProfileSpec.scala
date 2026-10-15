// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

/** CONTROL_ONLY: synthetic Matrix returns, actual candidate control and ports.
  * No Matrix arithmetic is instantiated in this Verilator probe. */
class QkProfileProbe(enabled:Boolean) extends Module {
  val io=IO(new Bundle {
    val oldIdle=Input(Bool());val abort=Input(Bool());val start=Input(Bool());val startReady=Output(Bool())
    val base=Input(UInt(8.W));val tokens=Input(UInt(8.W));val stripeBase=Input(UInt(4.W))
    val operand=Input(Bool());val operandReady=Output(Bool());val stripe=Input(UInt(4.W));val step=Input(UInt(3.W))
    val groupReady=Input(Bool());val groupValid=Output(Bool());val stepReady=Input(Bool());val stepValid=Output(Bool())
    val context=Output(UInt(3.W));val clear=Output(Bool());val last=Output(Bool());val finish=Output(Bool());val emit=Output(Bool())
    val badPadding=Output(Bool())
    val resultValid=Input(Bool());val resultReady=Output(Bool());val resultContext=Input(UInt(3.W));val resultLast=Input(Bool())
    val infRow=Input(UInt(5.W));val infCol=Input(UInt(8.W));val injectInf=Input(Bool())
    val matrixDone=Input(Bool());val matrixDoneReady=Output(Bool());val matrixDoneTag=Input(UInt(32.W));val matrixDoneError=Input(Bool())
    val matrixAbort=Output(Bool())
    val writeReady=Input(Bool());val writeValid=Output(Bool());val writeId=Output(new QkProfileWordTag);val writeData=Output(UInt(256.W))
    val ack=Input(Bool());val ackReady=Output(Bool());val ackId=Input(new QkProfileWordTag);val ackError=Input(Bool())
    val doneReady=Input(Bool());val done=Output(Bool());val error=Output(Bool());val poisoned=Output(Bool())
    val slots=Output(UInt(5.W));val returned=Output(UInt(8.W));val committed=Output(UInt(12.W))
    val release=Input(Bool());val releaseReady=Output(Bool());val releaseSlots=Input(UInt(5.W))
  })
  val d=Module(new QkRectangularProfile(enabled))
  d.io.oldOwnersIdle:=io.oldIdle;d.io.abort:=io.abort
  d.io.start.valid:=io.start;io.startReady:=d.io.start.ready
  d.io.start.bits.tag:=1.U;d.io.start.bits.epoch:=7.U;d.io.start.bits.qbase:=io.base
  d.io.start.bits.tokens:=io.tokens;d.io.start.bits.stripeBase:=io.stripeBase
  d.io.operand.valid:=io.operand;io.operandReady:=d.io.operand.ready
  d.io.operand.bits.tag:=1.U;d.io.operand.bits.epoch:=7.U
  d.io.operand.bits.stripe:=io.stripe;d.io.operand.bits.step:=io.step
  for(r<-0 until 16)d.io.operand.bits.a(r):="h3f80".U
  for(c<-0 until 256)d.io.operand.bits.b(c):="h3f80".U
  d.io.matrix.group.ready:=io.groupReady;io.groupValid:=d.io.matrix.group.valid
  d.io.matrix.step.ready:=io.stepReady;io.stepValid:=d.io.matrix.step.valid
  io.context:=d.io.matrix.step.bits.context;io.clear:=d.io.matrix.step.bits.clear
  io.last:=d.io.matrix.step.bits.last;io.finish:=d.io.matrix.step.bits.finish;io.emit:=d.io.matrix.step.bits.emit
  // Test uses one real query/token, so all other rows/keys must be zeroed.
  io.badPadding:=d.io.matrix.step.bits.a.drop(1).map(_=/=0.U).reduce(_||_) ||
    d.io.matrix.step.bits.b.drop(1).map(_=/=0.U).reduce(_||_)
  d.io.matrix.result.valid:=io.resultValid;io.resultReady:=d.io.matrix.result.ready
  d.io.matrix.result.bits.context:=io.resultContext;d.io.matrix.result.bits.last:=io.resultLast
  d.io.matrix.result.bits.error:=false.B
  for(r<-0 until 16;c<-0 until 256){
    val value=(BigInt("3f800000",16)+r*256+c).U(32.W)
    d.io.matrix.result.bits.value(r)(c):=Mux(io.injectInf && io.infRow===r.U && io.infCol===c.U,"h7f800000".U,value)
  }
  d.io.matrix.done.valid:=io.matrixDone;d.io.matrix.done.bits.tag:=io.matrixDoneTag
  d.io.matrix.done.bits.error:=io.matrixDoneError;io.matrixDoneReady:=d.io.matrix.done.ready;io.matrixAbort:=d.io.matrix.abort
  d.io.write.ready:=io.writeReady;io.writeValid:=d.io.write.valid;io.writeId:=d.io.write.bits.id;io.writeData:=d.io.write.bits.data
  d.io.writeAck.valid:=io.ack;d.io.writeAck.bits.id:=io.ackId;d.io.writeAck.bits.error:=io.ackError;io.ackReady:=d.io.writeAck.ready
  d.io.done.ready:=io.doneReady;io.done:=d.io.done.valid;io.error:=d.io.done.bits.error;io.poisoned:=d.io.resetRequired
  io.slots:=d.io.slotValid;io.returned:=d.io.returnedSteps;io.committed:=d.io.committedWords
  d.io.release.valid:=io.release;d.io.release.bits.tag:=1.U;d.io.release.bits.epoch:=7.U
  d.io.release.bits.slots:=io.releaseSlots;d.io.release.bits.error:=false.B;io.releaseReady:=d.io.release.ready
}

class QkRectangularProfileSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:QkProfileProbe):Unit={
    d.io.oldIdle.poke(true.B);d.io.abort.poke(false.B);d.io.start.poke(false.B)
    d.io.base.poke(0.U);d.io.tokens.poke(1.U);d.io.stripeBase.poke(0.U)
    d.io.operand.poke(false.B);d.io.stripe.poke(0.U);d.io.step.poke(0.U)
    d.io.groupReady.poke(false.B);d.io.stepReady.poke(false.B)
    d.io.resultValid.poke(false.B);d.io.resultContext.poke(0.U);d.io.resultLast.poke(false.B)
    d.io.injectInf.poke(false.B);d.io.infRow.poke(0.U);d.io.infCol.poke(0.U)
    d.io.matrixDone.poke(false.B);d.io.matrixDoneTag.poke(1.U);d.io.matrixDoneError.poke(false.B)
    d.io.writeReady.poke(false.B);d.io.ack.poke(false.B);d.io.ackError.poke(false.B)
    d.io.ackId.tag.poke(1.U);d.io.ackId.epoch.poke(7.U);d.io.ackId.context.poke(0.U);d.io.ackId.bank.poke(0.U);d.io.ackId.word.poke(0.U)
    d.io.doneReady.poke(false.B);d.io.release.poke(false.B);d.io.releaseSlots.poke(0.U)
  }
  def begin(d:QkProfileProbe,sb:Int=0):Unit={
    d.io.stripeBase.poke(sb.U);d.io.startReady.expect(true.B);d.io.start.poke(true.B);d.clock.step();d.io.start.poke(false.B)
    d.io.groupValid.expect(true.B);d.clock.step(2);d.io.groupReady.poke(true.B);d.clock.step();d.io.groupReady.poke(false.B)
  }
  def step(d:QkProfileProbe,ctx:Int,t:Int,sb:Int=0):Unit={
    d.io.stripe.poke((sb+ctx).U);d.io.step.poke(t.U);d.io.operand.poke(true.B)
    d.io.stepValid.expect(true.B);d.io.operandReady.expect(false.B);d.io.context.expect(ctx.U)
    d.io.clear.expect((t==0).B);d.io.last.expect((t==7).B);d.io.emit.expect(true.B);d.io.badPadding.expect(false.B)
    d.io.finish.expect((t==7 && (ctx==4 || sb==15)).B)
    d.io.stepReady.poke(true.B);d.clock.step();d.io.operand.poke(false.B);d.io.stepReady.poke(false.B)
    d.io.resultContext.poke(ctx.U);d.io.resultLast.poke((t==7).B)
  }
  def result(d:QkProfileProbe):Unit={d.io.resultValid.poke(true.B);d.io.resultReady.expect(true.B);d.clock.step();d.io.resultValid.poke(false.B)}
  def ackId(d:QkProfileProbe,ctx:Int,bank:Int,word:Int):Unit={
    d.io.ackId.tag.poke(1.U);d.io.ackId.epoch.poke(7.U);d.io.ackId.context.poke(ctx.U)
    d.io.ackId.bank.poke(bank.U);d.io.ackId.word.poke(word.U)
  }
  "default-off QK profile" should "drive no Matrix or B request" in {
    test(new QkProfileProbe(false)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.start.poke(true.B);d.io.operand.poke(true.B);d.io.groupReady.poke(true.B);d.io.stepReady.poke(true.B)
      for(_<-0 until 5){d.io.startReady.expect(false.B);d.io.groupValid.expect(false.B);d.io.stepValid.expect(false.B);d.io.writeValid.expect(false.B);d.clock.step()}
    }
  }
  "enabled QK profile" should "retire forty real returns and fence five exact B slots before ordered-fold release" in {
    test(new QkProfileProbe(true)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);d.io.oldIdle.poke(false.B);d.io.startReady.expect(false.B);d.io.oldIdle.poke(true.B);begin(d)
      for(t<-0 until 8;ctx<-0 until 5){
        step(d,ctx,t)
        // A future causal-mask lane is nonfinite on EVERY return; legal (0,0) stays finite.
        d.io.injectInf.poke(true.B);d.io.infCol.poke(31.U);result(d);d.io.injectInf.poke(false.B)
        if(t==7){
          for(bank<-0 until 16;chunk<-0 until 4){
            val word=ctx*32+chunk
            d.io.writeValid.expect(true.B);d.io.writeId.bank.expect(bank.U);d.io.writeId.word.expect(word.U)
            val expected=(0 until 8).map(i=>{
              val c=chunk*8+i
              val x=if(bank==0 && c==31)BigInt("7f800000",16) else BigInt("3f800000",16)+bank*256+c
              x<<(32*i)
            }).reduce(_|_)
            d.io.writeData.expect(expected.U)
            d.io.operandReady.expect(false.B);d.clock.step();d.io.writeData.expect(expected.U)
            d.io.writeReady.poke(true.B);d.clock.step();d.io.writeReady.poke(false.B)
            d.io.writeValid.expect(false.B);d.io.slots.expect(((1<<ctx)-1).U)
            if(ctx==4 && bank==15 && chunk==3){d.io.matrixDone.poke(true.B);d.io.matrixDoneReady.expect(false.B);d.io.done.expect(false.B)}
            ackId(d,ctx,bank,word);d.clock.step(2);d.io.ack.poke(true.B);d.io.ackReady.expect(true.B);d.clock.step();d.io.ack.poke(false.B)
          }
          d.io.slots.expect(((1<<(ctx+1))-1).U)
        }
      }
      d.io.returned.expect(40.U);d.io.committed.expect(320.U);d.io.matrixDoneReady.expect(true.B);d.clock.step();d.io.matrixDone.poke(false.B)
      d.io.done.expect(true.B);d.io.error.expect(false.B);d.io.startReady.expect(false.B)
      d.io.doneReady.poke(true.B);d.clock.step();d.io.doneReady.poke(false.B)
      d.io.startReady.expect(false.B);d.io.releaseSlots.poke(31.U);d.io.release.poke(true.B);d.io.releaseReady.expect(true.B);d.clock.step();d.io.release.poke(false.B)
      d.io.startReady.expect(true.B);d.io.slots.expect(0.U)
    }
  }
  it should "poison bad return identity, selected nonfinite and lost or wrong B ACK without premature success" in {
    test(new QkProfileProbe(true)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      def reset():Unit={d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);init(d)}
      def drainDone():Unit={
        d.io.matrixDone.poke(true.B);d.io.matrixDoneError.poke(true.B);d.io.matrixDoneReady.expect(true.B);d.clock.step();d.io.matrixDone.poke(false.B)
        d.io.done.expect(true.B);d.io.error.expect(true.B);d.io.doneReady.poke(true.B);d.clock.step();d.io.startReady.expect(false.B)
      }
      init(d);begin(d,15);step(d,0,0,15)
      d.io.resultContext.poke(1.U);d.io.resultValid.poke(true.B);d.io.resultReady.expect(false.B);d.clock.step();d.io.poisoned.expect(true.B)
      d.io.resultContext.poke(0.U);result(d);drainDone()
      reset();begin(d,15);step(d,0,0,15);d.io.injectInf.poke(true.B);d.io.infCol.poke(0.U);result(d)
      d.io.poisoned.expect(true.B);d.io.writeValid.expect(false.B);drainDone()
      reset();begin(d,15)
      for(t<-0 until 8){step(d,0,t,15);result(d)}
      d.io.writeReady.poke(true.B);d.clock.step();d.io.writeReady.poke(false.B)
      d.clock.step(7);d.io.done.expect(false.B);d.io.slots.expect(0.U);d.io.operandReady.expect(false.B)
      ackId(d,0,0,0);d.io.ackId.epoch.poke(8.U);d.io.ack.poke(true.B);d.io.ackReady.expect(false.B);d.clock.step();d.io.poisoned.expect(true.B)
      d.io.ackId.epoch.poke(7.U);d.io.ackReady.expect(true.B);d.clock.step();d.io.ack.poke(false.B)
      d.io.committed.expect(1.U);d.io.slots.expect(0.U);drainDone()
      reset();begin(d,15);step(d,0,0,15);d.io.abort.poke(true.B);d.clock.step();d.io.abort.poke(false.B)
      // Production abort may suppress the pending output, but real done drains its metadata.
      drainDone()
      reset();begin(d,15);step(d,0,0,15)
      // An independent endpoint/output fault can suppress output without our abort.
      d.io.matrixDone.poke(true.B);d.io.matrixDoneError.poke(true.B);d.io.matrixDoneTag.poke(99.U)
      d.io.matrixDoneReady.expect(false.B);d.clock.step();d.io.poisoned.expect(true.B);d.io.done.expect(false.B)
      d.io.matrixDoneTag.poke(1.U);drainDone()
      reset();begin(d,15);step(d,0,0,15)
      drainDone() // Matching independent error terminal is sufficient, no result or local abort.
      reset();begin(d,15) // No operand or step has been accepted yet.
      d.io.matrixDone.poke(true.B);d.io.matrixDoneError.poke(true.B);d.clock.step()
      d.io.operandReady.expect(false.B);drainDone()
      reset();begin(d,15)
      for(t<-0 until 8){step(d,0,t,15);result(d)}
      d.io.writeReady.poke(true.B);d.clock.step();d.io.writeReady.poke(false.B)
      d.io.matrixDone.poke(true.B);d.io.matrixDoneError.poke(true.B);d.clock.step(3)
      d.io.matrixDoneReady.expect(false.B);d.io.done.expect(false.B);d.io.poisoned.expect(true.B)
      ackId(d,0,0,0);d.io.ack.poke(true.B);d.clock.step();d.io.ack.poke(false.B)
      d.io.committed.expect(1.U);d.io.slots.expect(0.U);drainDone()
    }
  }
}
