package gemmini

import chisel3._
import chisel3.util._

/** Terminal micro-op plus activation scratch metadata.
  *
  * The original descriptor roots and 32-bit aux field remain intact in
  * `microOp`. Composite activation expansion only fills the explicit scratch
  * selectors below, avoiding the earlier ambiguity where descriptor metadata
  * could be overwritten by transaction-local register selectors.
  */
class HeteroTerminalPrimitiveMicroOp extends Bundle {
  val microOp = new HeteroPrimitiveMicroOp
  val parentOpcode = UInt(HeteroPrimitiveOpcode.width.W)
  val parentPhase = UInt(8.W)
  val parentVariant = UInt(8.W)
  val scratchValid = Bool()
  val scratchSrc0 = UInt(HeteroActivationValue.width.W)
  val scratchSrc1 = UInt(HeteroActivationValue.width.W)
  val scratchDst = UInt(HeteroActivationValue.width.W)
  val scratchVariant = UInt(8.W)
}

object HeteroCompositeOpcode {
  def isComposite(opcode: UInt): Bool = {
    opcode === HeteroPrimitiveOpcode.SfuExp ||
    opcode === HeteroPrimitiveOpcode.SfuSigmoid ||
    opcode === HeteroPrimitiveOpcode.SfuSoftplus ||
    opcode === HeteroPrimitiveOpcode.SfuSilu ||
    opcode === HeteroPrimitiveOpcode.SfuGelu
  }

  def function(opcode: UInt): UInt = {
    MuxLookup(opcode, HeteroCompositeFunction.NaturalExp)(Seq(
      HeteroPrimitiveOpcode.SfuExp -> HeteroCompositeFunction.NaturalExp,
      HeteroPrimitiveOpcode.SfuSigmoid -> HeteroCompositeFunction.Sigmoid,
      HeteroPrimitiveOpcode.SfuSoftplus -> HeteroCompositeFunction.Softplus,
      HeteroPrimitiveOpcode.SfuSilu -> HeteroCompositeFunction.Silu,
      HeteroPrimitiveOpcode.SfuGelu -> HeteroCompositeFunction.Gelu
    ))
  }
}

/** Expands composite activation opcodes into terminal SFU arithmetic opcodes.
  * Non-composite micro-ops pass through unchanged. After this block,
  * exp/sigmoid/softplus/SiLU/GELU never remain as unresolved pseudo-opcodes.
  */
class HeteroPrimitiveLeafExpander extends Module {
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val in = Flipped(Decoupled(new HeteroPrimitiveMicroOp))
    val out = Decoupled(new HeteroTerminalPrimitiveMicroOp)
    val busy = Output(Bool())
    val done = Output(Bool())
  })

  val sIdle :: sPass :: sCompositeStart :: sCompositeRun :: Nil = Enum(4)
  val state = RegInit(sIdle)
  val base = RegInit(0.U.asTypeOf(new HeteroPrimitiveMicroOp))
  val function = RegInit(HeteroCompositeFunction.NaturalExp)
  val composite = Module(new HeteroCompositeActivationSequencer)

  composite.io.clear := io.clear
  composite.io.start := state === sCompositeStart
  composite.io.function := function
  composite.io.out.ready := state === sCompositeRun && io.out.ready

  io.in.ready := state === sIdle
  io.busy := state =/= sIdle
  io.done := false.B

  val terminal = Wire(new HeteroTerminalPrimitiveMicroOp)
  terminal.microOp := base
  terminal.parentOpcode := base.opcode
  terminal.parentPhase := base.phase
  terminal.parentVariant := base.variant
  terminal.scratchValid := false.B
  terminal.scratchSrc0 := HeteroActivationValue.Zero
  terminal.scratchSrc1 := HeteroActivationValue.Zero
  terminal.scratchDst := HeteroActivationValue.Zero
  terminal.scratchVariant := 0.U

  io.out.valid := state === sPass
  io.out.bits := terminal

  when(state === sCompositeRun) {
    io.out.valid := composite.io.out.valid
    io.out.bits.microOp.owner := HeteroPrimitiveOwner.Sfu
    io.out.bits.microOp.opcode := composite.io.out.bits.opcode
    io.out.bits.microOp.phase := composite.io.out.bits.phase
    io.out.bits.microOp.variant := composite.io.out.bits.variant
    io.out.bits.microOp.first := base.first && composite.io.out.bits.first
    io.out.bits.microOp.last := base.last && composite.io.out.bits.last
    io.out.bits.scratchValid := true.B
    io.out.bits.scratchSrc0 := composite.io.out.bits.src0
    io.out.bits.scratchSrc1 := composite.io.out.bits.src1
    io.out.bits.scratchDst := composite.io.out.bits.dst
    io.out.bits.scratchVariant := composite.io.out.bits.variant
  }

  when(io.clear) {
    state := sIdle
    base := 0.U.asTypeOf(new HeteroPrimitiveMicroOp)
    function := HeteroCompositeFunction.NaturalExp
  }.otherwise {
    switch(state) {
      is(sIdle) {
        when(io.in.fire) {
          base := io.in.bits
          when(HeteroCompositeOpcode.isComposite(io.in.bits.opcode)) {
            function := HeteroCompositeOpcode.function(io.in.bits.opcode)
            state := sCompositeStart
          }.otherwise {
            state := sPass
          }
        }
      }
      is(sPass) {
        when(io.out.fire) {
          state := sIdle
          io.done := true.B
        }
      }
      is(sCompositeStart) {
        when(composite.io.start && composite.io.startReady) {
          state := sCompositeRun
        }
      }
      is(sCompositeRun) {
        when(io.out.fire && composite.io.out.bits.last) {
          state := sIdle
          io.done := true.B
        }
      }
    }
  }

  when(state === sCompositeRun && io.out.valid) {
    assert(!HeteroCompositeOpcode.isComposite(io.out.bits.microOp.opcode))
    assert(io.out.bits.microOp.owner === HeteroPrimitiveOwner.Sfu)
    assert(io.out.bits.scratchValid)
  }
}

/** End-to-end source-level primitive frontend.
  *
  * It accepts one model-level operator, decomposes it, recursively expands
  * composite activation opcodes, and does not accept the next command until
  * the final terminal micro-op of the current command has retired. This is the
  * integration boundary used by the local-agent RTL differential tests.
  */
class HeteroTerminalModelOperatorFrontend extends Module {
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val command = Flipped(Decoupled(new HeteroOperatorCommand))
    val microOp = Decoupled(new HeteroTerminalPrimitiveMicroOp)
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidOperator = Output(Bool())
  })

  val model = Module(new HeteroModelOperatorSequencer)
  val leaf = Module(new HeteroPrimitiveLeafExpander)
  val finalInFlight = RegInit(false.B)

  model.io.clear := io.clear
  leaf.io.clear := io.clear

  val mayAcceptCommand = !leaf.io.busy && !finalInFlight
  model.io.command.valid := io.command.valid && mayAcceptCommand
  model.io.command.bits := io.command.bits
  io.command.ready := model.io.command.ready && mayAcceptCommand

  leaf.io.in.valid := model.io.microOp.valid
  leaf.io.in.bits := model.io.microOp.bits
  model.io.microOp.ready := leaf.io.in.ready

  io.microOp.valid := leaf.io.out.valid
  io.microOp.bits := leaf.io.out.bits
  leaf.io.out.ready := io.microOp.ready

  io.busy := model.io.busy || leaf.io.busy || finalInFlight
  io.invalidOperator := model.io.invalidOperator
  io.done := false.B

  when(io.clear) {
    finalInFlight := false.B
  }.otherwise {
    when(leaf.io.in.fire && leaf.io.in.bits.last) {
      finalInFlight := true.B
    }
    when(leaf.io.done && finalInFlight) {
      finalInFlight := false.B
      io.done := true.B
    }
  }

  when(io.microOp.valid) {
    assert(!HeteroCompositeOpcode.isComposite(io.microOp.bits.microOp.opcode))
    assert(HeteroPrimitiveCapability.terminal(
      io.microOp.bits.microOp.owner,
      io.microOp.bits.microOp.opcode
    ))
  }
  when(finalInFlight) {
    assert(!io.command.ready)
  }
}
