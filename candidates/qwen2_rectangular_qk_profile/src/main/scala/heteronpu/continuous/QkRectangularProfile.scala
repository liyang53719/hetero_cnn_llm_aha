// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

class QkProfileStart extends Bundle {
  val tag=UInt(32.W);val epoch=UInt(32.W)
  val qbase=UInt(8.W);val tokens=UInt(8.W);val stripeBase=UInt(4.W)
}
class QkProfileOperand extends Bundle {
  val tag=UInt(32.W);val epoch=UInt(32.W);val stripe=UInt(4.W);val step=UInt(3.W)
  val a=Vec(16,UInt(16.W));val b=Vec(256,UInt(16.W))
}
class QkProfileWordTag extends Bundle {
  val tag=UInt(32.W);val epoch=UInt(32.W);val context=UInt(3.W)
  val bank=UInt(4.W);val word=UInt(8.W)
}
class QkProfileWrite extends Bundle {val id=new QkProfileWordTag;val data=UInt(256.W)}
class QkProfileWriteAck extends Bundle {val id=new QkProfileWordTag;val error=Bool()}
class QkProfileFence extends Bundle {
  val tag=UInt(32.W);val epoch=UInt(32.W);val slots=UInt(5.W);val error=Bool()
}

/** Default-off candidate, using the unchanged real MatrixStreamPort ABI.
  * One accepted step at a time; EVERY step emits and really retires a result.
  * The sole captured tile is held through every 32-byte B write commit.
  * External operands, B port arbitration and ordered fold/release are new
  * integration contracts. This module is not wired into the old Host owner.
  */
class QkRectangularProfile(enabled:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val oldOwnersIdle=Input(Bool());val abort=Input(Bool())
    val start=Flipped(Decoupled(new QkProfileStart))
    val operand=Flipped(Decoupled(new QkProfileOperand))
    val matrix=new MatrixStreamPort
    val write=Decoupled(new QkProfileWrite)
    val writeAck=Flipped(Decoupled(new QkProfileWriteAck))
    val done=Decoupled(new QkProfileFence)
    // This ACK comes only after an external ordered fold has consumed all slots.
    val release=Flipped(Decoupled(new QkProfileFence))
    val slotValid=Output(UInt(5.W));val resetRequired=Output(Bool())
    val returnedSteps=Output(UInt(8.W));val committedWords=Output(UInt(12.W))
  })
  val idle::begin::operand::result::write::ack::terminal::reply::release::locked::Nil=Enum(10)
  val state=RegInit(idle);val g=Reg(new QkProfileStart)
  val rows=Reg(UInt(5.W));val columns=Reg(UInt(8.W));val contexts=Reg(UInt(3.W))
  val ctx=RegInit(0.U(3.W));val t=RegInit(0.U(3.W))
  val bank=RegInit(0.U(4.W));val chunk=RegInit(0.U(5.W))
  val captured=Reg(Vec(16,Vec(256,UInt(32.W)))) // one 16-KiB finalValue candidate
  val poison=RegInit(false.B);val slots=RegInit(0.U(5.W))
  val returned=RegInit(0.U(8.W));val committed=RegInit(0.U(12.W))
  val groupAccepted=RegInit(false.B)
  val nextTag=RegInit(1.U(32.W));val epochValid=RegInit(false.B);val epoch=Reg(UInt(32.W))
  io.slotValid:=Mux(poison,0.U,slots);io.resetRequired:=poison
  io.returnedSteps:=returned;io.committedWords:=committed
  val lastContext=ctx===contexts-1.U
  val expectedId=Wire(new QkProfileWordTag)
  expectedId.tag:=g.tag;expectedId.epoch:=g.epoch;expectedId.context:=ctx
  expectedId.bank:=bank;expectedId.word:=Cat(ctx,0.U(5.W))+chunk
  val operandGood=io.operand.bits.tag===g.tag && io.operand.bits.epoch===g.epoch &&
    io.operand.bits.stripe===(g.stripeBase+ctx) && io.operand.bits.step===t
  val resultGood=io.matrix.result.bits.context===ctx && io.matrix.result.bits.last===(t===7.U)
  val ackGood=io.writeAck.bits.id.asUInt===expectedId.asUInt
  val doneGood=io.matrix.done.bits.tag===g.tag
  val selectedNonfinite=(for(r<-0 until 16;c<-0 until 128)yield
    r.U<rows && c.U<(g.qbase+&r.U+1.U) && io.matrix.result.bits.value(r)(c)(30,23)==="hff".U).reduce(_||_)
  val abortNow=io.abort || (state=/=idle && state=/=locked && !io.oldOwnersIdle)
  val serviceError=groupAccepted && io.matrix.done.valid && io.matrix.done.bits.error
  val failed=poison||abortNow||serviceError
  io.start.ready:=enabled.B && state===idle && io.oldOwnersIdle && !poison && !io.abort
  io.matrix.group.valid:=state===begin && !failed
  io.matrix.group.bits.opcode:="h23".U;io.matrix.group.bits.tag:=g.tag
  io.matrix.group.bits.sliceMask:=MuxLookup(columns,1.U)(Seq(32.U->1.U,64.U->3.U,96.U->7.U,128.U->15.U))
  io.matrix.step.valid:=state===operand && io.operand.valid && operandGood && !failed
  io.matrix.step.bits.context:=ctx;io.matrix.step.bits.clear:=t===0.U
  io.matrix.step.bits.last:=t===7.U;io.matrix.step.bits.finish:=t===7.U && lastContext
  io.matrix.step.bits.emit:=true.B
  for(r<-0 until 16)io.matrix.step.bits.a(r):=Mux(r.U<rows,io.operand.bits.a(r),0.U)
  for(c<-0 until 256)io.matrix.step.bits.b(c):=Mux(c.U<g.tokens && c.U<columns,io.operand.bits.b(c),0.U)
  io.operand.ready:=state===operand && !failed && Mux(operandGood,io.matrix.step.ready,true.B)
  io.matrix.result.ready:=state===result && resultGood
  io.matrix.abort:=groupAccepted && failed
  io.write.valid:=state===write && !failed
  io.write.bits.id:=expectedId
  io.write.bits.data:=VecInit((0 until 8).map(i=>captured(bank)(Cat(chunk,0.U(3.W))+i.U))).asUInt
  io.writeAck.ready:=state===ack && ackGood
  // A real service abort terminal certifies all accepted step metadata drained,
  // including in-flight non-enqueued results suppressed by MatrixPipeline.
  io.matrix.done.ready:=doneGood && ((state===terminal) || (state===result && failed))
  io.done.valid:=state===reply
  io.done.bits.tag:=g.tag;io.done.bits.epoch:=g.epoch;io.done.bits.slots:=Mux(failed,0.U,slots);io.done.bits.error:=failed
  val releaseGood=io.release.bits.tag===g.tag && io.release.bits.epoch===g.epoch &&
    io.release.bits.slots===slots && !io.release.bits.error
  io.release.ready:=state===release && releaseGood && !failed

  def advance():Unit={
    when(lastContext){ctx:=0.U;t:=t+1.U}.otherwise{ctx:=ctx+1.U}
    state:=operand
  }
  when(io.start.fire){
    g:=io.start.bits;ctx:=0.U;t:=0.U;slots:=0.U;returned:=0.U;committed:=0.U
    val x=io.start.bits;val remaining=x.tokens-x.qbase
    rows:=Mux(remaining<16.U,remaining,16.U)
    val end=Mux(remaining<16.U,x.tokens,x.qbase+16.U)
    columns:=((end+&31.U)>>5)<<5
    contexts:=Mux(x.stripeBase===15.U,1.U,5.U)
    val legal=x.tag===nextTag && x.tag=/="hffffffff".U && (!epochValid || x.epoch===epoch) && x.tokens>=1.U && x.tokens<=128.U && x.qbase<x.tokens && x.qbase(3,0)===0.U &&
      (x.stripeBase===0.U||x.stripeBase===5.U||x.stripeBase===10.U||x.stripeBase===15.U)
    when(legal){nextTag:=nextTag+1.U;epoch:=x.epoch;epochValid:=true.B;state:=begin}.otherwise{poison:=true.B;state:=reply}
  }
  when(io.matrix.group.fire){groupAccepted:=true.B;state:=operand}
  when(io.operand.fire){
    when(operandGood){state:=result}.otherwise{poison:=true.B;state:=terminal}
  }
  when(state===result && io.matrix.result.valid && !resultGood){poison:=true.B}
  when(io.matrix.result.fire){
    returned:=returned+1.U
    when(failed || io.matrix.result.bits.error || selectedNonfinite){
      poison:=true.B;state:=terminal
    }.elsewhen(t===7.U){captured:=io.matrix.result.bits.value;bank:=0.U;chunk:=0.U;state:=write}
    .otherwise{advance()}
  }
  when(io.write.fire){state:=ack}
  when(state===ack && io.writeAck.valid && !ackGood){poison:=true.B}
  when(io.writeAck.fire){
    when(!io.writeAck.bits.error){committed:=committed+1.U}
    when(failed || io.writeAck.bits.error){poison:=true.B;state:=terminal}
    .elsewhen(chunk===(columns>>3)-1.U){
      chunk:=0.U
      when(bank===15.U){
        slots:=slots|UIntToOH(ctx,5)
        when(lastContext){state:=terminal}.otherwise{ctx:=ctx+1.U;state:=operand}
      }.otherwise{bank:=bank+1.U;state:=write}
    }.otherwise{chunk:=chunk+1.U;state:=write}
  }
  when(io.matrix.done.valid && (state===terminal || (state===result && failed)) && !doneGood){poison:=true.B}
  when(io.matrix.done.fire){
    groupAccepted:=false.B
    when(io.matrix.done.bits.error){poison:=true.B}
    state:=reply
  }
  when(io.done.fire){state:=Mux(failed,locked,release)}
  when(state===release && io.release.valid && !releaseGood){poison:=true.B;state:=locked}
  when(io.release.fire){slots:=0.U;state:=idle}
  when(abortNow && state=/=idle && state=/=locked){
    poison:=true.B
    when(state===release){state:=locked}
    .elsewhen(state===begin){state:=reply}
    .elsewhen(state===operand || state===write){state:=terminal}
  }
  when(serviceError){
    poison:=true.B
    when(state===operand || state===write){state:=terminal}
  }
  when(failed){slots:=0.U}
}
