package gemmini

import chisel3._
import chisel3.util._

/** Synthesizable owner/opcode registry for the operator-primitive boundary.
  * Composite activation opcodes are legal only before leaf expansion; every
  * terminal micro-op must match exactly one registered owner family below.
  */
object HeteroPrimitiveCapability {
  private def oneOf(value: UInt, choices: Seq[UInt]): Bool = {
    choices.map(value === _).reduce(_ || _)
  }

  def composite(owner: UInt, opcode: UInt): Bool = {
    owner === HeteroPrimitiveOwner.Sfu && HeteroCompositeOpcode.isComposite(opcode)
  }

  def terminal(owner: UInt, opcode: UInt): Bool = {
    val control = owner === HeteroPrimitiveOwner.Control && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.Nop,
      HeteroPrimitiveOpcode.Barrier
    ))
    val dma = owner === HeteroPrimitiveOwner.Dma && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.DmaRead,
      HeteroPrimitiveOpcode.DmaWrite,
      HeteroPrimitiveOpcode.DmaGather,
      HeteroPrimitiveOpcode.DmaScatter
    ))
    val matrix = owner === HeteroPrimitiveOwner.Matrix && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.MatrixGemm,
      HeteroPrimitiveOpcode.MatrixGemv,
      HeteroPrimitiveOpcode.MatrixQk,
      HeteroPrimitiveOpcode.MatrixPv,
      HeteroPrimitiveOpcode.MatrixOuter,
      HeteroPrimitiveOpcode.MatrixConv,
      HeteroPrimitiveOpcode.MatrixLowRank
    ))
    val sfu = owner === HeteroPrimitiveOwner.Sfu && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.SfuAdd,
      HeteroPrimitiveOpcode.SfuSub,
      HeteroPrimitiveOpcode.SfuMul,
      HeteroPrimitiveOpcode.SfuScale,
      HeteroPrimitiveOpcode.SfuReduceSum,
      HeteroPrimitiveOpcode.SfuReduceMax,
      HeteroPrimitiveOpcode.SfuRsqrt,
      HeteroPrimitiveOpcode.SfuReciprocal,
      HeteroPrimitiveOpcode.SfuExp2,
      HeteroPrimitiveOpcode.SfuRmsNorm,
      HeteroPrimitiveOpcode.SfuGroupRmsNorm,
      HeteroPrimitiveOpcode.SfuRope,
      HeteroPrimitiveOpcode.SfuOnlineSoftmax,
      HeteroPrimitiveOpcode.SfuGate,
      HeteroPrimitiveOpcode.SfuL2Norm,
      HeteroPrimitiveOpcode.SfuAbs,
      HeteroPrimitiveOpcode.SfuMax,
      HeteroPrimitiveOpcode.SfuCompareSelect,
      HeteroPrimitiveOpcode.SfuNegate,
      HeteroPrimitiveOpcode.SfuPwl,
      HeteroPrimitiveOpcode.SfuBroadcast,
      HeteroPrimitiveOpcode.SfuCausalMask,
      HeteroPrimitiveOpcode.SfuLayerNorm
    ))
    val kv = owner === HeteroPrimitiveOwner.KvMemory && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.KvAppend,
      HeteroPrimitiveOpcode.KvGather,
      HeteroPrimitiveOpcode.KvAlloc,
      HeteroPrimitiveOpcode.KvFree
    ))
    val state = owner === HeteroPrimitiveOwner.State && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.StateRead,
      HeteroPrimitiveOpcode.StateWrite,
      HeteroPrimitiveOpcode.StateDecay,
      HeteroPrimitiveOpcode.StateConvWindow,
      HeteroPrimitiveOpcode.StateBegin,
      HeteroPrimitiveOpcode.StateCommit,
      HeteroPrimitiveOpcode.StateRollback
    ))
    val selection = owner === HeteroPrimitiveOwner.Selection && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.SelectTopK,
      HeteroPrimitiveOpcode.SelectExpand,
      HeteroPrimitiveOpcode.SelectRoute,
      HeteroPrimitiveOpcode.SelectMerge,
      HeteroPrimitiveOpcode.SelectBlockPool,
      HeteroPrimitiveOpcode.SelectMtpVerify
    ))
    val vision = owner === HeteroPrimitiveOwner.Vision && oneOf(opcode, Seq(
      HeteroPrimitiveOpcode.VisionWindow,
      HeteroPrimitiveOpcode.VisionPatchMerge,
      HeteroPrimitiveOpcode.VisionPosInterp,
      HeteroPrimitiveOpcode.PleHash,
      HeteroPrimitiveOpcode.VisionPatch3d,
      HeteroPrimitiveOpcode.VisionMropeMap
    ))
    control || dma || matrix || sfu || kv || state || selection || vision
  }

  def source(owner: UInt, opcode: UInt): Bool = terminal(owner, opcode) || composite(owner, opcode)
}

class HeteroPrimitiveCapabilityDecode extends Module {
  val io = IO(new Bundle {
    val owner = Input(UInt(HeteroPrimitiveOwner.width.W))
    val opcode = Input(UInt(HeteroPrimitiveOpcode.width.W))
    val sourceSupported = Output(Bool())
    val terminalSupported = Output(Bool())
    val composite = Output(Bool())
  })

  io.composite := HeteroPrimitiveCapability.composite(io.owner, io.opcode)
  io.terminalSupported := HeteroPrimitiveCapability.terminal(io.owner, io.opcode)
  io.sourceSupported := HeteroPrimitiveCapability.source(io.owner, io.opcode)
  assert(PopCount(Seq(io.composite, io.terminalSupported)) <= 1.U)
}
