// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Two register-backed wide results. Keep row structure instead of inferring a
  * 131077-bit memory word, which has neither a useful SRAM mapping nor a portable
  * simulation representation. These are two bounded 16-KiB output tile buffers.
  */
class MatrixResultFifo extends Module {
  val io=IO(new Bundle {
    val enq=Flipped(Decoupled(new MatrixStreamResult))
    val deq=Decoupled(new MatrixStreamResult)
  })
  val storage=Reg(Vec(2,new MatrixStreamResult))
  val head=RegInit(false.B);val tail=RegInit(false.B);val count=RegInit(0.U(2.W))
  io.deq.valid:=count=/=0.U;io.deq.bits:=storage(head)
  io.enq.ready:=count<2.U||io.deq.fire
  when(io.enq.fire){storage(tail):=io.enq.bits;tail:= !tail}
  when(io.deq.fire){head:= !head}
  when(io.enq.fire=/=io.deq.fire){count:=Mux(io.enq.fire,count+1.U,count-1.U)}
}

/** One command per group of independent output contexts, not per K step.
  * The unchanged retained endpoint owns all five FP32 accumulator contexts.
  * Accepted steps are tracked through an eight-entry metadata FIFO. The
  * command-last indication follows the RETURNING step, never the live input.
  * Partial sums may be discarded; final values are credit-buffered. No step
  * waits for its own result when a different legal context can issue.
  */
class MatrixPipelineService extends Module {
  val io=IO(new Bundle {
    val port=Flipped(new MatrixStreamPort)
    val acceptedSteps=Output(UInt(64.W)) // physical 512-MAC slice issues
    val wideSteps=Output(UInt(64.W))
    val stallCycles=Output(UInt(64.W))
    val resetRequired=Output(Bool())
  })
  val idle :: command :: running :: ending :: finish :: draining :: locked :: Nil=Enum(7)
  val state=RegInit(idle)
  val group=Reg(new MatrixStreamGroup)
  val event=RegInit(0.U(16.W))
  val poison=RegInit(false.B)
  val endIssued=RegInit(false.B)
  val seen=RegInit(0.U(5.W));val closed=RegInit(0.U(5.W))
  val steps=RegInit(0.U(64.W));val wideSteps=RegInit(0.U(64.W));val stalls=RegInit(0.U(64.W))
  io.acceptedSteps:=steps;io.wideSteps:=wideSteps;io.stallCycles:=stalls;io.resetRequired:=poison
  class Meta extends Bundle {val context=UInt(3.W);val last=Bool();val finish=Bool();val emit=Bool()}
  val tags=Module(new Queue(new Meta,8,pipe=true))
  val values=Module(new MatrixResultFifo)
  tags.io.enq.valid:=false.B;tags.io.enq.bits:=0.U.asTypeOf(new Meta)
  tags.io.deq.ready:=false.B
  values.io.enq.valid:=false.B;values.io.enq.bits:=0.U.asTypeOf(new MatrixStreamResult)
  io.port.result<>values.io.deq
  io.port.group.ready:=state===idle && !poison
  io.port.step.ready:=false.B
  io.port.done.valid:=state===finish && !values.io.deq.valid
  io.port.done.bits.tag:=group.tag;io.port.done.bits.error:=poison

  val leaves=Seq.fill(8)(Module(new RetainedMatrixEndpoint))
  val selected=(0 until 8).map(i=>group.sliceMask(i))
  val allCommandReady=(0 until 8).map(i=> !selected(i)||leaves(i).io.cmd_ready_o).reduce(_&&_)
  val allStepReady=(0 until 8).map(i=> !selected(i)||leaves(i).io.step_ready_o).reduce(_&&_)
  val allOutValid=(0 until 8).map(i=> !selected(i)||leaves(i).io.out_valid_o).reduce(_&&_)
  val allCompletion=(0 until 8).map(i=> !selected(i)||leaves(i).io.completion_valid_o).reduce(_&&_)
  val x=io.port.step.bits
  val legalContext=x.context<5.U
  val legalStep=legalContext && x.clear=== !seen(x.context) && !closed(x.context) && (!x.finish||(x.last && ((closed|UIntToOH(x.context,5))===(seen|UIntToOH(x.context,5)))))
  val work=state===running && !endIssued && !io.port.abort
  val consumeOutput=(state===running||state===ending||state===draining) && tags.io.deq.valid && allOutValid &&
    (state===draining|| !tags.io.deq.bits.emit||values.io.enq.ready)
  val outputBad=(0 until 8).map(i=>selected(i)&&
    (leaves(i).io.out_context_o=/=tags.io.deq.bits.context||leaves(i).io.out_last_o=/=tags.io.deq.bits.last)).reduce(_||_)
  val endpointError=(0 until 8).map(i=>selected(i)&&leaves(i).io.protocol_error_o).reduce(_||_)
  val completionBad=(0 until 8).map(i=>selected(i)&&
    (leaves(i).io.completion_data_o(55,40)=/=event||leaves(i).io.completion_data_o(39,32)=/=0.U||leaves(i).io.completion_data_o(31,29)=/=2.U)).reduce(_||_)
  for(i<-0 until 8){
    val e=leaves(i).io
    val gate=Module(new RetainedMatrixClockGate)
    gate.io.clk_i:=clock;gate.io.test_en_i:=false.B
    gate.io.en_i:=selected(i) && state=/=idle && state=/=finish && state=/=locked
    e.clk_i:=gate.io.clk_o;e.rst_ni:= !reset.asBool
    e.cmd_valid_i:=state===command && selected(i) && allCommandReady
    e.cmd_i:=Cat(0.U(72.W),event,0.U(16.W),0.U(13.W),2.U(3.W),group.opcode)
    e.step_valid_i:=work && legalStep && io.port.step.valid && tags.io.enq.ready && allStepReady && selected(i)
    e.step_context_i:=x.context;e.step_clear_i:=x.clear;e.step_last_i:=x.last
    e.step_a_i:=x.a.asUInt;e.step_b_i:=VecInit((0 until 32).map(j=>x.b(i*32+j))).asUInt
    e.command_last_tile_i:=tags.io.deq.valid && tags.io.deq.bits.finish && state=/=draining
    e.out_ready_i:=consumeOutput && selected(i)
    e.completion_ready_i:=state===ending && allCompletion && selected(i)
    for(r<-0 until 16;c<-0 until 32){
      values.io.enq.bits.value(r)(i*32+c):=Mux(selected(i),e.out_acc_o((r*32+c)*32+31,(r*32+c)*32),0.U)
    }
  }
  io.port.step.ready:=work && Mux(legalStep,tags.io.enq.ready && allStepReady,true.B)
  tags.io.enq.valid:=io.port.step.fire && legalStep
  tags.io.enq.bits.context:=x.context;tags.io.enq.bits.last:=x.last
  tags.io.enq.bits.finish:=x.finish;tags.io.enq.bits.emit:=x.emit
  tags.io.deq.ready:=consumeOutput
  values.io.enq.valid:=consumeOutput && tags.io.deq.bits.emit && state=/=draining
  values.io.enq.bits.context:=tags.io.deq.bits.context;values.io.enq.bits.last:=tags.io.deq.bits.last
  values.io.enq.bits.error:=outputBad||poison

  when(io.port.group.fire){
    group:=io.port.group.bits;event:=event+1.U;seen:=0.U;closed:=0.U;endIssued:=false.B
    val g=io.port.group.bits
    when(!g.sliceMask.orR || !(g.opcode===0x20.U||g.opcode===0x21.U||g.opcode===0x23.U||g.opcode===0x24.U)){
      poison:=true.B;state:=finish
    }.otherwise{state:=command}
  }
  when(state===command&&allCommandReady){state:=running}
  when(io.port.step.valid&&work && !io.port.step.ready){stalls:=stalls+1.U}
  when(io.port.step.fire){
    when(!legalStep){poison:=true.B;state:=draining}
    .otherwise{
      seen:=seen|UIntToOH(x.context,5);when(x.last){closed:=closed|UIntToOH(x.context,5)}
      steps:=steps+PopCount(group.sliceMask);wideSteps:=wideSteps+1.U
      when(x.finish){endIssued:=true.B}
    }
  }
  when(consumeOutput&&tags.io.deq.bits.finish&&state=/=draining){state:=ending}
  when(state===ending&&allCompletion){
    when(completionBad){poison:=true.B}
    state:=finish
  }
  when(state===draining && !tags.io.deq.valid){state:=finish}
  when(io.port.done.fire){state:=Mux(poison,locked,idle)}
  when((io.port.abort||endpointError||(consumeOutput&&outputBad)) && state=/=idle && state=/=finish && state=/=locked){
    poison:=true.B;state:=draining
  }
}

/** Compatibility client for the non-Dense owners; no arithmetic is instantiated.
  * QK/PV retain their original lane mapping and increasing reduction sequence.
  */
class LegacyMatrixStreamClient extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new WideMatrixStep(256)))
    val result=Decoupled(new WideMatrixResult(256))
    val port=new MatrixStreamPort
    val resetRequired=Output(Bool())
  })
  val idle::begin::issue::waitResult::waitDone::reply::locked::Nil=Enum(7)
  val state=RegInit(idle);val req=Reg(new WideMatrixStep(256));val result=Reg(new WideMatrixResult(256))
  val active=RegInit(false.B);val poison=RegInit(false.B);val tag=RegInit(0.U(32.W))
  io.request.ready:=state===idle && !poison
  io.result.valid:=state===reply;io.result.bits:=result;io.resetRequired:=poison
  io.port.group.valid:=state===begin;io.port.group.bits.opcode:=req.opcode
  io.port.group.bits.sliceMask:=req.sliceMask;io.port.group.bits.tag:=tag
  io.port.step.valid:=state===issue;io.port.step.bits.a:=req.a;io.port.step.bits.b:=req.b
  io.port.step.bits.context:=0.U;io.port.step.bits.clear:=req.clear;io.port.step.bits.last:=req.last
  io.port.step.bits.finish:=req.last;io.port.step.bits.emit:=true.B
  io.port.result.ready:=state===waitResult
  // An aborted group can return an error without a partial result. Consume
  // that terminal error rather than waiting forever for a suppressed tensor.
  io.port.done.ready:=state===waitDone || (state===waitResult && io.port.done.bits.error)
  io.port.abort:=false.B
  when(io.request.fire){
    req:=io.request.bits;result.error:=false.B
    when(io.request.bits.clear===active){poison:=true.B;result.error:=true.B;state:=reply}
    .elsewhen(io.request.bits.clear){tag:=tag+1.U;state:=begin}
    .otherwise{state:=issue}
  }
  when(io.port.group.fire){active:=true.B;state:=issue}
  when(io.port.step.fire){state:=waitResult}
  when(io.port.result.fire){
    result.value:=io.port.result.bits.value;result.error:=io.port.result.bits.error
    when(io.port.result.bits.error){poison:=true.B}
    state:=Mux(req.last||io.port.result.bits.error,waitDone,reply)
  }
  when(io.port.done.fire){
    active:=false.B
    when(io.port.done.bits.error||io.port.done.bits.tag=/=tag){poison:=true.B;result.error:=true.B}
    state:=reply
  }
  when(io.result.fire){state:=Mux(poison,locked,idle)}
}
