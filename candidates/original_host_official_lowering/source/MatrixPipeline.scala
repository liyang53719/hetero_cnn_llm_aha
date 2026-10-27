// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Two register-backed wide results. Keep row structure instead of inferring a
  * 131077-bit memory word, which has neither a useful SRAM mapping nor a portable
  * simulation representation. These are two bounded 16-KiB output tile buffers.
  */
class MatrixResultFifo(returnTagBits:Int=0) extends Module {
  val io=IO(new Bundle {
    val enq=Flipped(Decoupled(new MatrixStreamResult(returnTagBits)))
    val deq=Decoupled(new MatrixStreamResult(returnTagBits))
  })
  val storage=Reg(Vec(2,new MatrixStreamResult(returnTagBits)))
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
class MatrixPipelineService(returnTagBits:Int=0,enableTransposedDense:Boolean=false,enableAccumulatorSeed:Boolean=false,enablePackedDrainStatus:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val port=Flipped(new MatrixStreamPort(returnTagBits,enableTransposedDense,enableAccumulatorSeed))
    val acceptedSteps=Output(UInt(64.W)) // physical 512-MAC slice issues
    val wideSteps=Output(UInt(64.W))
    val stallCycles=Output(UInt(64.W))
    val resetRequired=Output(Bool())
    val resourcesDrained=Output(Bool()) // private all-leaf/queue/seed retirement
    val packedStepsDrained=if(enablePackedDrainStatus)Some(Output(Bool()))else None
  })
  val idle :: command :: running :: ending :: finish :: draining :: locked :: Nil=Enum(7)
  val state=RegInit(idle)
  val group=Reg(new MatrixStreamGroup(enableTransposedDense,enableAccumulatorSeed))
  val event=RegInit(0.U(16.W))
  val poison=RegInit(false.B)
  val endIssued=RegInit(false.B)
  val seen=RegInit(0.U(5.W));val closed=RegInit(0.U(5.W))
  val steps=RegInit(0.U(64.W));val wideSteps=RegInit(0.U(64.W));val stalls=RegInit(0.U(64.W))
  io.acceptedSteps:=steps;io.wideSteps:=wideSteps;io.stallCycles:=stalls;io.resetRequired:=poison
  class Meta extends Bundle {
    val context=UInt(3.W);val last=Bool();val finish=Bool();val emit=Bool()
    val returnTag=if(returnTagBits>0)Some(UInt(returnTagBits.W))else None
  }
  val tags=Module(new Queue(new Meta,8,pipe=true))
  val values=Module(new MatrixResultFifo(returnTagBits))
  tags.io.enq.valid:=false.B;tags.io.enq.bits:=0.U.asTypeOf(new Meta)
  tags.io.deq.ready:=false.B
  values.io.enq.valid:=false.B;values.io.enq.bits:=0.U.asTypeOf(new MatrixStreamResult(returnTagBits))
  io.port.result<>values.io.deq
  io.port.group.ready:=state===idle && !poison
  io.port.step.ready:=false.B
  io.port.done.valid:=state===finish && !values.io.deq.valid
  io.port.done.bits.tag:=group.tag;io.port.done.bits.error:=poison

  val leaves=Seq.fill(8)(Module(new RetainedMatrixEndpoint(enableAccumulatorSeed)))
  // A seed is distinct from a first arithmetic issue. Finish must close every
  // seeded context, including a seeded context which has not issued yet.
  val seeded=if(enableAccumulatorSeed)Some(RegInit(0.U(5.W)))else None
  val seedController=if(enableAccumulatorSeed)Some(Module(new MatrixAccumulatorSeedController))else None
  val seedBlocks=seedController.map(_.io.blockIssue).getOrElse(false.B)
  val seedPoison=seedController.map(_.io.resetRequired).getOrElse(false.B)
  val seedTransportQuiet=WireDefault(true.B)
  val selected=(0 until 8).map(i=>group.sliceMask(i))
  val allCommandReady=(0 until 8).map(i=> !selected(i)||leaves(i).io.cmd_ready_o).reduce(_&&_)
  val allStepReady=(0 until 8).map(i=> !selected(i)||leaves(i).io.step_ready_o).reduce(_&&_)
  val allOutValid=(0 until 8).map(i=> !selected(i)||leaves(i).io.out_valid_o).reduce(_&&_)
  val allCompletion=(0 until 8).map(i=> !selected(i)||leaves(i).io.completion_valid_o).reduce(_&&_)
  val x=io.port.step.bits
  val legalContext=x.context<5.U
  val legalStep=if(enableAccumulatorSeed){legalContext && x.clear=== !(seen|seeded.getOrElse(0.U(5.W)))(x.context) && !closed(x.context) && (!x.finish||(x.last && ((closed|UIntToOH(x.context,5))===(seen|seeded.getOrElse(0.U(5.W))|UIntToOH(x.context,5)))))}else{legalContext && x.clear=== !seen(x.context) && !closed(x.context) && (!x.finish||(x.last && ((closed|UIntToOH(x.context,5))===(seen|UIntToOH(x.context,5)))))}
  val work=if(enableAccumulatorSeed){state===running && !endIssued && !io.port.abort && !seedBlocks && !seedPoison}else{state===running && !endIssued && !io.port.abort}
  // Existing metadata owns retirement; no new debt counter or payload.
  if(enablePackedDrainStatus){io.packedStepsDrained.get:=work && !tags.io.deq.valid && !io.port.step.valid && !poison}
  val consumeOutput=(state===running||state===ending||state===draining) && tags.io.deq.valid && allOutValid &&
    (state===draining|| !tags.io.deq.bits.emit||values.io.enq.ready)
  val outputBad=(0 until 8).map(i=>selected(i)&&
    (leaves(i).io.out_context_o=/=tags.io.deq.bits.context||leaves(i).io.out_last_o=/=tags.io.deq.bits.last)).reduce(_||_)
  val endpointError=(0 until 8).map(i=>selected(i)&&leaves(i).io.protocol_error_o).reduce(_||_)
  val completionBad=(0 until 8).map(i=>selected(i)&&
    (leaves(i).io.completion_data_o(55,40)=/=event||leaves(i).io.completion_data_o(39,32)=/=0.U||leaves(i).io.completion_data_o(31,29)=/=2.U)).reduce(_||_)
  // Keep retained arithmetic clocks stopped while only DDR or output storage
  // is waiting. A group may retain accumulator state indefinitely without
  // toggling all 4096 MACs. Reopen for accepted input, in-flight pipeline drain,
  // returned-output consumption, and command/completion handshakes.
  val canIssue=work && legalStep && io.port.step.valid && tags.io.enq.ready && allStepReady
  val needsClock=if(enableAccumulatorSeed){seedBlocks || seedPoison || state===command || state===ending || state===draining ||
    (state===running && (canIssue || (tags.io.deq.valid && (!allOutValid || consumeOutput))))}else{state===command || state===ending || state===draining ||
    (state===running && (canIssue || (tags.io.deq.valid && (!allOutValid || consumeOutput))))}
  // Mode comes only from the accepted group register. Share the upper weight
  // mux across four existing endpoints; no payload register or wider lane.
  val upperWeights=if(enableTransposedDense)Some(Mux(group.transposedDense.get,
    VecInit((128 until 144).map(j=>x.b(j))).asUInt,x.a.asUInt))else None
  if(enableAccumulatorSeed){
    val ctl=seedController.get.io
    ctl.seed<>io.port.seed.get
    // The accepted group has a separate retained command handshake. Do not
    // consume begin until the service reaches running and leaves are active.
    ctl.seed.begin.valid:=io.port.seed.get.begin.valid && state===running
    io.port.seed.get.begin.ready:=ctl.seed.begin.ready && state===running
    ctl.groupActive:=state===running && !endIssued && !poison && group.transposedDense.getOrElse(false.B)
    ctl.groupTag:=group.tag;ctl.groupSequence:=group.groupSequence.get;ctl.sliceMask:=group.sliceMask
    ctl.freeContexts:= ~(seen|closed|seeded.get)
    ctl.quiescent:= !tags.io.deq.valid && !values.io.deq.valid && (0 until 8).map(i=>
      !selected(i)||(!leaves(i).io.arithmetic_busy_o.get.orR && !leaves(i).io.arithmetic_out_valid_o.get)).reduce(_&&_)
    ctl.abort:=io.port.abort||poison
    // Uniform seed-capable service successor: independently accepted broadcast.
    // VALID must not depend on READY: the retained provider's seed READY depends
    // on seed-valid's arithmetic-issue block through its real quiescence logic.
    // Ten control bits, no seed data/identity buffer: ctl holds its accepted req
    // unchanged until terminal ACK (or coordinated reset after failure).
    val broadcastAccepted=RegInit(0.U(8.W))
    val broadcastActive=RegInit(false.B)
    val broadcastCommit=RegInit(false.B)
    val broadcastOffered=ctl.leafBegin.valid || ctl.leafCommit.valid
    val broadcastLive=broadcastActive || broadcastOffered
    val isCommit=Mux(broadcastActive,broadcastCommit,ctl.leafCommit.valid)
    val broadcastMask=Mux(isCommit,ctl.leafCommit.bits.sliceMask,ctl.leafBegin.bits.sliceMask)
    val broadcastValid=Wire(Vec(8,Bool()))
    val broadcastFires=Wire(Vec(8,Bool()))
    for(i<-0 until 8){
      broadcastValid(i):=broadcastLive && broadcastMask(i) && !broadcastAccepted(i)
      broadcastFires(i):=broadcastValid(i) && Mux(isCommit,
        leaves(i).io.seed_commit_ready_o.get,leaves(i).io.seed_begin_ready_o.get)
    }
    val broadcastComplete=broadcastLive && broadcastMask.orR &&
      ((broadcastAccepted|broadcastFires.asUInt)&broadcastMask)===broadcastMask
    ctl.leafBegin.ready:=broadcastComplete && !isCommit
    ctl.leafCommit.ready:=broadcastComplete && isCommit
    // A previously offered leaf VALID survives late abort/poison, even if no
    // leaf accepted yet. Remaining obligations are never silently cancelled.
    // A failed controller cannot issue another req; the service's existing
    // poison/seed_abort isolation and coordinated reset retire this quarantine.
    when(broadcastLive){
      broadcastActive:=true.B;broadcastCommit:=isCommit
      broadcastAccepted:=broadcastAccepted|broadcastFires.asUInt
    }
    // Last leaf's actual handshake completes the controller handshake in this
    // same cycle. Clearing only on that fire prevents cross-phase mask reuse.
    when(ctl.leafBegin.fire || ctl.leafCommit.fire){
      broadcastActive:=false.B;broadcastCommit:=false.B;broadcastAccepted:=0.U
    }
    ctl.leafBeat.ready:=MuxLookup(ctl.leafBeat.bits.slice,false.B)((0 until 8).map(i=>i.U->leaves(i).io.seed_beat_ready_o.get))
    for(i<-0 until 8){
      val e=leaves(i).io
      e.seed_begin_valid_i.get:=broadcastValid(i) && !isCommit
      e.seed_group_tag_i.get:=ctl.leafBegin.bits.groupTag
      e.seed_group_sequence_i.get:=ctl.leafBegin.bits.groupSequence
      e.seed_source_generation_i.get:=ctl.leafBegin.bits.sourceGeneration
      e.seed_context_i.get:=ctl.leafBegin.bits.context
      e.seed_beat_valid_i.get:=ctl.leafBeat.valid && ctl.leafBeat.bits.slice===i.U
      e.seed_cluster_i.get:=ctl.leafBeat.bits.cluster;e.seed_data_i.get:=ctl.leafBeat.bits.data
      e.seed_commit_valid_i.get:=broadcastValid(i) && isCommit
      // A selected leaf may ACK its registered commit before the remaining
      // selected leaves accept. Hold only ACKs for our actually accepted commit
      // bits at the existing endpoint, without a new payload register/credit.
      // When the aggregate commit fires, the controller enters collect on the
      // next edge and all held ACKs become visible with their original fields.
      // Unknown/unaccepted/wrong-phase ACKs remain visible to unexpectedAck.
      val holdAcceptedCommitAck=broadcastActive && broadcastCommit && broadcastAccepted(i)
      ctl.leafAck(i).valid:=e.seed_ack_valid_o.get && !holdAcceptedCommitAck
      e.seed_ack_ready_i.get:=ctl.leafAck(i).ready && !holdAcceptedCommitAck
      ctl.leafAck(i).bits.groupTag:=e.seed_ack_group_tag_o.get
      ctl.leafAck(i).bits.groupSequence:=e.seed_ack_group_sequence_o.get
      ctl.leafAck(i).bits.sourceGeneration:=e.seed_ack_source_generation_o.get
      ctl.leafAck(i).bits.context:=e.seed_ack_context_o.get;ctl.leafAck(i).bits.error:=e.seed_ack_error_o.get
      e.seed_abort_i.get:=selected(i) && (io.port.abort || poison || ctl.invalidate.valid)
    }
    when(ctl.committed.valid){seeded.get:=seeded.get|UIntToOH(ctl.committed.bits.context,5)}
    when(io.port.group.fire){seeded.get:=0.U}
    seedTransportQuiet:= !broadcastActive && !broadcastAccepted.orR && !ctl.blockIssue &&
      !ctl.seed.ack.valid && !leaves.map(_.io.seed_ack_valid_o.get).reduce(_||_) &&
      !leaves.map(_.io.arithmetic_busy_o.get.orR).reduce(_||_) &&
      !leaves.map(_.io.arithmetic_out_valid_o.get).reduce(_||_)
    val leafPoison=leaves.map(_.io.seed_reset_required_o.get).reduce(_||_)
    when(ctl.resetRequired||leafPoison){poison:=true.B;when(state=/=finish && state=/=locked){state:=draining}}
  }
  // Do not restrict this fence to the previous selected mask: an idle stale
  // output/terminal on ANY physical slice blocks reuse and requires isolation.
  val anyLeafReturn=leaves.map(x=>x.io.out_valid_o || x.io.completion_valid_o).reduce(_||_)
  val anyLeafFault=leaves.map(_.io.protocol_error_o).reduce(_||_)
  val idleUnexpected=state===idle && (anyLeafReturn || tags.io.deq.valid || values.io.deq.valid)
  val lifetimeQuarantine=RegInit(false.B)
  when(idleUnexpected){lifetimeQuarantine:=true.B}
  io.resetRequired:=poison || lifetimeQuarantine || idleUnexpected || anyLeafFault || seedPoison
  io.port.group.ready:=state===idle && !io.resetRequired
  io.resourcesDrained:=state===idle && !io.resetRequired && seedTransportQuiet &&
    !anyLeafReturn && !tags.io.deq.valid && !values.io.deq.valid &&
    !io.port.group.valid && !io.port.step.valid && !io.port.seed.map(_.begin.valid).getOrElse(false.B) &&
    !io.port.seed.map(_.beat.valid).getOrElse(false.B)
  for(i<-0 until 8){
    val e=leaves(i).io
    val gate=Module(new RetainedMatrixClockGate)
    gate.io.clk_i:=clock;gate.io.test_en_i:=false.B
    gate.io.en_i:=selected(i) && needsClock
    e.clk_i:=gate.io.clk_o;e.rst_ni:= !reset.asBool
    e.cmd_valid_i:=state===command && selected(i) && allCommandReady
    e.cmd_i:=Cat(0.U(72.W),event,0.U(16.W),0.U(13.W),2.U(3.W),group.opcode)
    e.step_valid_i:=work && legalStep && io.port.step.valid && tags.io.enq.ready && allStepReady && selected(i)
    e.step_context_i:=x.context;e.step_clear_i:=x.clear;e.step_last_i:=x.last
    if(enableTransposedDense && i>=4){
      e.step_a_i:=upperWeights.get
      e.step_b_i:=Mux(group.transposedDense.get,
        VecInit((0 until 32).map(j=>x.b((i%4)*32+j))).asUInt,
        VecInit((0 until 32).map(j=>x.b(i*32+j))).asUInt)
    }else{
      e.step_a_i:=x.a.asUInt;e.step_b_i:=VecInit((0 until 32).map(j=>x.b(i*32+j))).asUInt
    }
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
  if(returnTagBits>0){tags.io.enq.bits.returnTag.get:=x.returnTag.get}
  tags.io.deq.ready:=consumeOutput
  values.io.enq.valid:=consumeOutput && tags.io.deq.bits.emit && state=/=draining
  values.io.enq.bits.context:=tags.io.deq.bits.context;values.io.enq.bits.last:=tags.io.deq.bits.last
  // Follow the RETURNING accepted step, never live input pins.
  if(returnTagBits>0){values.io.enq.bits.returnTag.get:=tags.io.deq.bits.returnTag.get}
  values.io.enq.bits.error:=outputBad||poison

  when(io.port.group.fire){
    group:=io.port.group.bits;event:=event+1.U;seen:=0.U;closed:=0.U;endIssued:=false.B
    val g=io.port.group.bits
    when(if(enableTransposedDense){
      !g.sliceMask.orR || !(g.opcode===0x20.U||g.opcode===0x21.U||g.opcode===0x23.U||g.opcode===0x24.U) ||
        (g.transposedDense.get && (g.opcode=/=0x20.U || g.sliceMask=/=0xff.U))
    }else{
      !g.sliceMask.orR || !(g.opcode===0x20.U||g.opcode===0x21.U||g.opcode===0x23.U||g.opcode===0x24.U)
    }){
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
  // A held abort must not override the draining -> finish transition.
  when((io.port.abort||endpointError||(consumeOutput&&outputBad)) && state=/=idle && state=/=finish && state=/=locked && state=/=draining){
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
