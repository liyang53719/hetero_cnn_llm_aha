package gemmini

import chisel3._
import chisel3.util._
import heteronpu.operator.{LeafCapabilities, PrimitiveCompletion, PrimitiveKind, TensorMicroOp}

class HeteroV3TerminalRequest extends Bundle {
  val owner = UInt(HeteroPrimitiveOwner.width.W)
  val opcode = UInt(HeteroPrimitiveOpcode.width.W)
  val tag = UInt(16.W)
  val parentPhase = UInt(8.W)
  val terminalPhase = UInt(8.W)
  val flags = UInt(16.W)
  val mode = UInt(8.W)
  val src0 = UInt(24.W)
  val src1 = UInt(24.W)
  val src2 = UInt(24.W)
  val dst = UInt(24.W)
  val rows = UInt(16.W)
  val columns = UInt(16.W)
  val depth = UInt(16.W)
  val index0 = UInt(16.W)
  val index1 = UInt(16.W)
  val scratchValid = Bool()
  val scratchSrc0 = UInt(HeteroActivationValue.width.W)
  val scratchSrc1 = UInt(HeteroActivationValue.width.W)
  val scratchDst = UInt(HeteroActivationValue.width.W)
  val variant = UInt(8.W)
  val first = Bool()
  val last = Bool()
}

class HeteroV3TerminalCompletion extends Bundle {
  val tag = UInt(16.W)
  val parentPhase = UInt(8.W)
  val terminalPhase = UInt(8.W)
  val status = UInt(8.W)
  val predicate = Bool()
}

/** Routes one checked terminal transaction to one of the eight hardware owner
  * endpoints. The selected owner must return a completion; the router never
  * manufactures successful completion for an accepted request.
  */
class HeteroV3TerminalOwnerRouter extends Module {
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val in = Flipped(Decoupled(new HeteroV3TerminalRequest))
    val owner = Vec(8, Decoupled(new HeteroV3TerminalRequest))
    val ownerCompletion = Flipped(Vec(8, Decoupled(new HeteroV3TerminalCompletion)))
    val completion = Decoupled(new HeteroV3TerminalCompletion)
    val busy = Output(Bool())
    val protocolError = Output(Bool())
  })

  val sIdle :: sIssue :: sWait :: sReport :: Nil = Enum(4)
  val state = RegInit(sIdle)
  val request = Reg(new HeteroV3TerminalRequest)
  val selected = RegInit(0.U(3.W))
  val result = RegInit(0.U.asTypeOf(new HeteroV3TerminalCompletion))
  val protocolErrorReg = RegInit(false.B)

  io.in.ready := state === sIdle
  for (index <- 0 until 8) {
    io.owner(index).valid := state === sIssue && selected === index.U
    io.owner(index).bits := request
    io.ownerCompletion(index).ready := state === sWait && selected === index.U
  }
  io.completion.valid := state === sReport
  io.completion.bits := result
  io.busy := state =/= sIdle
  io.protocolError := protocolErrorReg

  when(io.clear) {
    state := sIdle
    result := 0.U.asTypeOf(new HeteroV3TerminalCompletion)
    protocolErrorReg := false.B
  }.otherwise {
    when(state === sIdle && io.in.fire) {
      request := io.in.bits
      protocolErrorReg := false.B
      when(io.in.bits.owner <= HeteroPrimitiveOwner.Vision) {
        selected := io.in.bits.owner(2, 0)
        state := sIssue
      }.otherwise {
        result.tag := io.in.bits.tag
        result.parentPhase := io.in.bits.parentPhase
        result.terminalPhase := io.in.bits.terminalPhase
        result.status := 4.U
        result.predicate := false.B
        state := sReport
      }
    }
    when(state === sIssue && io.owner(selected).fire) {
      state := sWait
    }
    when(state === sWait && io.ownerCompletion(selected).fire) {
      val response = io.ownerCompletion(selected).bits
      val tagMismatch = response.tag =/= request.tag
      val phaseMismatch = response.parentPhase =/= request.parentPhase ||
        response.terminalPhase =/= request.terminalPhase
      result := response
      when(tagMismatch || phaseMismatch) {
        result.status := Mux(tagMismatch, "he1".U, "he2".U)
        protocolErrorReg := true.B
      }
      state := sReport
    }
    when(state === sReport && io.completion.fire) {
      state := sIdle
    }
  }
}

/** Bridges the canonical 18-root protocol to the terminal owner/opcode layer.
  * A root completion is emitted only after the accepted terminal request (or
  * every request of a composite expansion) has returned a checked completion.
  */
class HeteroV3TerminalBridge extends Module {
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val in = Flipped(Decoupled(new TensorMicroOp()))
    val terminal = Decoupled(new HeteroV3TerminalRequest)
    val terminalCompletion = Flipped(Decoupled(new HeteroV3TerminalCompletion))
    val completion = Decoupled(new PrimitiveCompletion())
    val busy = Output(Bool())
    val unsupported = Output(Bool())
    val protocolError = Output(Bool())
  })

  val sIdle :: sClassify :: sSimpleIssue :: sCompositeStart :: sCompositeIssue :: sWaitCompletion :: sReport :: Nil = Enum(7)
  val state = RegInit(sIdle)
  val base = Reg(new TensorMicroOp())
  val completionStatus = RegInit(0.U(8.W))
  val completionPredicate = RegInit(false.B)
  val expectedTerminalPhase = RegInit(0.U(8.W))
  val acceptedLast = RegInit(false.B)
  val acceptedComposite = RegInit(false.B)
  val unsupportedReg = RegInit(false.B)
  val protocolErrorReg = RegInit(false.B)

  val mappedOwner = WireDefault(HeteroPrimitiveOwner.Control)
  val mappedOpcode = WireDefault(HeteroPrimitiveOpcode.Nop)
  val mappedValid = VecInit(LeafCapabilities.all.map(capability =>
    base.kind === capability.kind.U)).asUInt.orR
  val compositeRequested = WireDefault(false.B)
  val compositeFunction = WireDefault(HeteroCompositeFunction.NaturalExp)

  switch(base.kind) {
    is(PrimitiveKind.DmaRead.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaRead }
    is(PrimitiveKind.DmaWrite.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaWrite }
    is(PrimitiveKind.MatrixGemm.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixGemm }
    is(PrimitiveKind.MatrixGemv.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixGemv }
    is(PrimitiveKind.MatrixOuter.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixOuter }
    is(PrimitiveKind.MatrixConv.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixConv }
    is(PrimitiveKind.MatrixQk.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixQk }
    is(PrimitiveKind.MatrixPv.U) { mappedOwner := HeteroPrimitiveOwner.Matrix; mappedOpcode := HeteroPrimitiveOpcode.MatrixPv }
    is(PrimitiveKind.VectorAdd.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuAdd }
    is(PrimitiveKind.VectorSub.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuSub }
    is(PrimitiveKind.VectorMul.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuMul }
    is(PrimitiveKind.VectorFma.U) { mappedOwner := HeteroPrimitiveOwner.Selection; mappedOpcode := HeteroPrimitiveOpcode.SelectMerge }
    is(PrimitiveKind.VectorCompare.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuCompareSelect }
    is(PrimitiveKind.VectorSelect.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuCompareSelect }
    is(PrimitiveKind.VectorGather.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaGather }
    is(PrimitiveKind.VectorScatter.U) {
      mappedOwner := Mux(base.flags(7), HeteroPrimitiveOwner.Selection, HeteroPrimitiveOwner.Dma)
      mappedOpcode := Mux(base.flags(7), HeteroPrimitiveOpcode.SelectRoute, HeteroPrimitiveOpcode.DmaScatter)
    }
    is(PrimitiveKind.VectorBroadcast.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuBroadcast }
    is(PrimitiveKind.LayoutTransform.U) { mappedOwner := HeteroPrimitiveOwner.Vision; mappedOpcode := HeteroPrimitiveOpcode.VisionWindow }
    is(PrimitiveKind.ApplyMask.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuCausalMask }
    is(PrimitiveKind.ReduceSum.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuReduceSum }
    is(PrimitiveKind.ReduceMax.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuReduceMax }
    is(PrimitiveKind.StableTopK.U) { mappedOwner := HeteroPrimitiveOwner.Selection; mappedOpcode := HeteroPrimitiveOpcode.SelectTopK }
    is(PrimitiveKind.StableSort.U) { mappedOwner := HeteroPrimitiveOwner.Selection; mappedOpcode := HeteroPrimitiveOpcode.SelectExpand }
    is(PrimitiveKind.SparseGatherRun.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaGather }
    is(PrimitiveKind.Argmax.U) { mappedOwner := HeteroPrimitiveOwner.Selection; mappedOpcode := HeteroPrimitiveOpcode.SelectTopK }
    is(PrimitiveKind.RmsNorm.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuRmsNorm }
    is(PrimitiveKind.GroupRmsNorm.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuGroupRmsNorm }
    is(PrimitiveKind.LayerNorm.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuLayerNorm }
    is(PrimitiveKind.L2Norm.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuL2Norm }
    is(PrimitiveKind.Rope.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuRope }
    is(PrimitiveKind.OnlineSoftmax.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuOnlineSoftmax }
    is(PrimitiveKind.Exp2.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuExp2 }
    is(PrimitiveKind.Reciprocal.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuReciprocal }
    is(PrimitiveKind.Rsqrt.U) { mappedOwner := HeteroPrimitiveOwner.Sfu; mappedOpcode := HeteroPrimitiveOpcode.SfuRsqrt }
    is(PrimitiveKind.Softplus.U) { compositeRequested := true.B; compositeFunction := HeteroCompositeFunction.Softplus }
    is(PrimitiveKind.Sigmoid.U) { compositeRequested := true.B; compositeFunction := HeteroCompositeFunction.Sigmoid }
    is(PrimitiveKind.Silu.U) { compositeRequested := true.B; compositeFunction := HeteroCompositeFunction.Silu }
    is(PrimitiveKind.Gelu.U) { compositeRequested := true.B; compositeFunction := HeteroCompositeFunction.Gelu }
    is(PrimitiveKind.SignedSqrt.U) { compositeRequested := true.B; compositeFunction := HeteroCompositeFunction.SignedSqrt }
    is(PrimitiveKind.ConfiguredGateAct.U) {
      compositeRequested := true.B
      compositeFunction := Mux(base.mode(0), HeteroCompositeFunction.Sigmoid, HeteroCompositeFunction.Silu)
    }
    is(PrimitiveKind.DepthwiseConv.U) { mappedOwner := HeteroPrimitiveOwner.State; mappedOpcode := HeteroPrimitiveOpcode.StateConvWindow }
    is(PrimitiveKind.EmbeddingLookup.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaGather }
    is(PrimitiveKind.NgramHash.U) { mappedOwner := HeteroPrimitiveOwner.Vision; mappedOpcode := HeteroPrimitiveOpcode.PleHash }
    is(PrimitiveKind.BilinearPosition.U) { mappedOwner := HeteroPrimitiveOwner.Vision; mappedOpcode := HeteroPrimitiveOpcode.VisionPosInterp }
    is(PrimitiveKind.SpatialMerge.U) { mappedOwner := HeteroPrimitiveOwner.Vision; mappedOpcode := HeteroPrimitiveOpcode.VisionPatchMerge }
    is(PrimitiveKind.MultimodalScatter.U) { mappedOwner := HeteroPrimitiveOwner.Dma; mappedOpcode := HeteroPrimitiveOpcode.DmaScatter }
    is(PrimitiveKind.KvAppend.U) { mappedOwner := HeteroPrimitiveOwner.KvMemory; mappedOpcode := HeteroPrimitiveOpcode.KvAppend }
    is(PrimitiveKind.KvGather.U) { mappedOwner := HeteroPrimitiveOwner.KvMemory; mappedOpcode := HeteroPrimitiveOpcode.KvGather }
    is(PrimitiveKind.StateRead.U) { mappedOwner := HeteroPrimitiveOwner.State; mappedOpcode := HeteroPrimitiveOpcode.StateRead }
    is(PrimitiveKind.StateWrite.U) { mappedOwner := HeteroPrimitiveOwner.State; mappedOpcode := HeteroPrimitiveOpcode.StateWrite }
    is(PrimitiveKind.StateCommit.U) { mappedOwner := HeteroPrimitiveOwner.State; mappedOpcode := HeteroPrimitiveOpcode.StateCommit }
    is(PrimitiveKind.StateResolve.U) {
      mappedOwner := HeteroPrimitiveOwner.State
      mappedOpcode := Mux(base.flags(14), HeteroPrimitiveOpcode.StateRollback, HeteroPrimitiveOpcode.StateCommit)
    }
    is(PrimitiveKind.MtpCompare.U) { mappedOwner := HeteroPrimitiveOwner.Selection; mappedOpcode := HeteroPrimitiveOpcode.SelectMtpVerify }
  }

  val composite = Module(new HeteroCompositeActivationSequencer)
  composite.io.clear := io.clear
  composite.io.start := state === sCompositeStart
  composite.io.function := compositeFunction
  composite.io.out.ready := state === sCompositeIssue && io.terminal.ready

  io.in.ready := state === sIdle
  io.terminal.valid := state === sSimpleIssue || (state === sCompositeIssue && composite.io.out.valid)
  io.terminal.bits.owner := Mux(state === sCompositeIssue, HeteroPrimitiveOwner.Sfu, mappedOwner)
  io.terminal.bits.opcode := Mux(state === sCompositeIssue, composite.io.out.bits.opcode, mappedOpcode)
  io.terminal.bits.tag := base.tag
  io.terminal.bits.parentPhase := base.phase
  io.terminal.bits.terminalPhase := Mux(state === sCompositeIssue, composite.io.out.bits.phase, base.phase)
  io.terminal.bits.flags := base.flags
  io.terminal.bits.mode := base.mode
  io.terminal.bits.src0 := base.src0
  io.terminal.bits.src1 := base.src1
  io.terminal.bits.src2 := base.src2
  io.terminal.bits.dst := base.dst
  io.terminal.bits.rows := base.m
  io.terminal.bits.columns := base.n
  io.terminal.bits.depth := base.k
  io.terminal.bits.index0 := base.index0
  io.terminal.bits.index1 := base.index1
  io.terminal.bits.scratchValid := state === sCompositeIssue
  io.terminal.bits.scratchSrc0 := composite.io.out.bits.src0
  io.terminal.bits.scratchSrc1 := composite.io.out.bits.src1
  io.terminal.bits.scratchDst := composite.io.out.bits.dst
  io.terminal.bits.variant := Mux(state === sCompositeIssue, composite.io.out.bits.variant, base.index0(7, 0))
  io.terminal.bits.first := Mux(state === sCompositeIssue, composite.io.out.bits.first, true.B)
  io.terminal.bits.last := Mux(state === sCompositeIssue, composite.io.out.bits.last, true.B)

  io.terminalCompletion.ready := state === sWaitCompletion
  io.completion.valid := state === sReport
  io.completion.bits.tag := base.tag
  io.completion.bits.phase := base.phase
  io.completion.bits.status := completionStatus
  io.completion.bits.predicate := completionPredicate
  io.busy := state =/= sIdle
  io.unsupported := unsupportedReg
  io.protocolError := protocolErrorReg

  when(io.clear) {
    state := sIdle
    completionStatus := 0.U
    completionPredicate := false.B
    unsupportedReg := false.B
    protocolErrorReg := false.B
  }.otherwise {
    when(state === sIdle && io.in.fire) {
      base := io.in.bits
      completionStatus := 0.U
      completionPredicate := false.B
      unsupportedReg := false.B
      protocolErrorReg := false.B
      state := sClassify
    }
    when(state === sClassify) {
      val resolveFlagsValid = base.kind =/= PrimitiveKind.StateResolve.U || base.flags(9) ^ base.flags(14)
      when(!mappedValid || !resolveFlagsValid) {
        completionStatus := 4.U
        unsupportedReg := true.B
        state := sReport
      }.elsewhen(compositeRequested) {
        state := sCompositeStart
      }.otherwise {
        state := sSimpleIssue
      }
    }
    when(state === sCompositeStart && composite.io.start && composite.io.startReady) {
      state := sCompositeIssue
    }
    when(io.terminal.fire) {
      expectedTerminalPhase := io.terminal.bits.terminalPhase
      acceptedLast := io.terminal.bits.last
      acceptedComposite := state === sCompositeIssue
      state := sWaitCompletion
    }
    when(state === sWaitCompletion && io.terminalCompletion.fire) {
      val tagMismatch = io.terminalCompletion.bits.tag =/= base.tag
      val phaseMismatch = io.terminalCompletion.bits.parentPhase =/= base.phase ||
        io.terminalCompletion.bits.terminalPhase =/= expectedTerminalPhase
      when(tagMismatch || phaseMismatch) {
        completionStatus := Mux(tagMismatch, "he1".U, "he2".U)
        completionPredicate := false.B
        protocolErrorReg := true.B
        state := sReport
      }.elsewhen(io.terminalCompletion.bits.status =/= 0.U) {
        completionStatus := io.terminalCompletion.bits.status
        completionPredicate := false.B
        state := sReport
      }.elsewhen(acceptedComposite && !acceptedLast) {
        state := sCompositeIssue
      }.otherwise {
        completionStatus := 0.U
        completionPredicate := io.terminalCompletion.bits.predicate
        state := sReport
      }
    }
    when(state === sReport && io.completion.fire) {
      state := sIdle
    }
  }

  when(io.terminal.valid) {
    assert(HeteroPrimitiveCapability.terminal(io.terminal.bits.owner, io.terminal.bits.opcode))
  }
}

object EmitHeteroV3TerminalBridge extends App {
  require(args.length == 1, "usage: <output-systemverilog-path>")
  val output = java.nio.file.Paths.get(args(0))
  val systemVerilog = _root_.circt.stage.ChiselStage.emitSystemVerilog(new HeteroV3TerminalBridge).stripTrailing + "\n"
  Option(output.getParent).foreach(java.nio.file.Files.createDirectories(_))
  java.nio.file.Files.writeString(output, systemVerilog, java.nio.charset.StandardCharsets.UTF_8)
}

object EmitHeteroV3TerminalOwnerRouter extends App {
  require(args.length == 1, "usage: <output-systemverilog-path>")
  val output = java.nio.file.Paths.get(args(0))
  val systemVerilog = _root_.circt.stage.ChiselStage.emitSystemVerilog(new HeteroV3TerminalOwnerRouter).stripTrailing + "\n"
  Option(output.getParent).foreach(java.nio.file.Files.createDirectories(_))
  java.nio.file.Files.writeString(output, systemVerilog, java.nio.charset.StandardCharsets.UTF_8)
}
