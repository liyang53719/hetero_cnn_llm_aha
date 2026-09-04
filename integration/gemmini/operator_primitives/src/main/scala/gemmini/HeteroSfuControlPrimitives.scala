package gemmini

import chisel3._
import chisel3.util._

/** Composite transcendental/activation contracts built from the fixed SFU
  * primitives already present in rtl/sfu.  This block is deliberately a
  * sequencer rather than another floating-point implementation: it preserves
  * one implementation of FP32 add/multiply/exp2/reciprocal while making the
  * Qwen3.5 and Qwen3.8 algebra explicit to the command compiler.
  */
object HeteroCompositeFunction {
  val width = 3
  val NaturalExp = 0.U(width.W)
  val Sigmoid = 1.U(width.W)
  val Softplus = 2.U(width.W)
  val Silu = 3.U(width.W)
  val Gelu = 4.U(width.W)
  val SignedSqrt = 5.U(width.W)
}

/** Scratch selectors used by HeteroCompositeActivationSequencer.
  * The executor binds them to a small transaction-local FP32 register file.
  */
object HeteroActivationValue {
  val width = 4
  val Input = 0.U(width.W)
  val Zero = 1.U(width.W)
  val One = 2.U(width.W)
  val Log2E = 3.U(width.W)
  val Epsilon = 4.U(width.W)
  val T0 = 5.U(width.W)
  val T1 = 6.U(width.W)
  val T2 = 7.U(width.W)
  val T3 = 8.U(width.W)
  val Output = 9.U(width.W)
}

class HeteroActivationStep extends Bundle {
  val opcode = UInt(HeteroPrimitiveOpcode.width.W)
  val phase = UInt(5.W)
  val src0 = UInt(HeteroActivationValue.width.W)
  val src1 = UInt(HeteroActivationValue.width.W)
  val dst = UInt(HeteroActivationValue.width.W)
  val variant = UInt(8.W)
  val first = Bool()
  val last = Bool()
}

class HeteroCompositeActivationSequencer extends Module {
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val function = Input(UInt(HeteroCompositeFunction.width.W))
    val out = Decoupled(new HeteroActivationStep)
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidFunction = Output(Bool())
  })

  val active = RegInit(false.B)
  val function = Reg(UInt(HeteroCompositeFunction.width.W))
  val phase = RegInit(0.U(5.W))

  def phaseCount(fn: UInt): UInt = {
    MuxLookup(fn, 0.U(5.W))(Seq(
      HeteroCompositeFunction.NaturalExp -> 2.U,
      HeteroCompositeFunction.Sigmoid -> 8.U,
      HeteroCompositeFunction.Softplus -> 1.U,
      HeteroCompositeFunction.Silu -> 9.U,
      HeteroCompositeFunction.Gelu -> 1.U,
      HeteroCompositeFunction.SignedSqrt -> 5.U
    ))
  }

  val requestedCount = phaseCount(io.function)
  val count = phaseCount(function)
  io.startReady := !active
  io.invalidFunction := io.start && io.startReady && requestedCount === 0.U
  io.busy := active
  io.done := false.B
  io.out.valid := active

  val step = Wire(new HeteroActivationStep)
  step.opcode := HeteroPrimitiveOpcode.Barrier
  step.phase := phase
  step.src0 := HeteroActivationValue.Input
  step.src1 := HeteroActivationValue.Zero
  step.dst := HeteroActivationValue.Output
  step.variant := 0.U
  step.first := phase === 0.U
  step.last := phase + 1.U >= count

  switch(function) {
    is(HeteroCompositeFunction.NaturalExp) {
      // exp(x) = exp2(x * log2(e)).
      when(phase === 0.U) {
        step.opcode := HeteroPrimitiveOpcode.SfuMul
        step.src0 := HeteroActivationValue.Input
        step.src1 := HeteroActivationValue.Log2E
        step.dst := HeteroActivationValue.T0
      }.otherwise {
        step.opcode := HeteroPrimitiveOpcode.SfuExp2
        step.src0 := HeteroActivationValue.T0
      }
    }
    is(HeteroCompositeFunction.Sigmoid) {
      // Overflow-safe sigmoid:
      // z=exp(-abs(x)); r=1/(1+z); n=z*r; y=x>=0 ? r : n.
      switch(phase) {
        is(0.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuAbs
          step.dst := HeteroActivationValue.T0
        }
        is(1.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuNegate
          step.src0 := HeteroActivationValue.T0
          step.dst := HeteroActivationValue.T1
        }
        is(2.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuMul
          step.src0 := HeteroActivationValue.T1
          step.src1 := HeteroActivationValue.Log2E
          step.dst := HeteroActivationValue.T2
        }
        is(3.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuExp2
          step.src0 := HeteroActivationValue.T2
          step.dst := HeteroActivationValue.T0
        }
        is(4.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuAdd
          step.src0 := HeteroActivationValue.One
          step.src1 := HeteroActivationValue.T0
          step.dst := HeteroActivationValue.T1
        }
        is(5.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuReciprocal
          step.src0 := HeteroActivationValue.T1
          step.dst := HeteroActivationValue.T2
        }
        is(6.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuMul
          step.src0 := HeteroActivationValue.T0
          step.src1 := HeteroActivationValue.T2
          step.dst := HeteroActivationValue.T3
        }
        is(7.U) {
          step.opcode := HeteroPrimitiveOpcode.SfuCompareSelect
          step.src0 := HeteroActivationValue.T2
          step.src1 := HeteroActivationValue.T3
          step.dst := HeteroActivationValue.Output
          step.variant := 1.U // predicate: original input >= +0.0
        }
      }
    }
    is(HeteroCompositeFunction.Softplus) {
      // Piecewise contract includes the stable x>20 and x<-20 tails.
      step.opcode := HeteroPrimitiveOpcode.SfuPwl
      step.variant := 1.U
    }
    is(HeteroCompositeFunction.Silu) {
      // First eight phases are the leaf sigmoid sequence; final phase multiplies x.
      when(phase < 8.U) {
        switch(phase) {
          is(0.U) { step.opcode := HeteroPrimitiveOpcode.SfuAbs; step.dst := HeteroActivationValue.T0 }
          is(1.U) { step.opcode := HeteroPrimitiveOpcode.SfuNegate; step.src0 := HeteroActivationValue.T0; step.dst := HeteroActivationValue.T1 }
          is(2.U) { step.opcode := HeteroPrimitiveOpcode.SfuMul; step.src0 := HeteroActivationValue.T1; step.src1 := HeteroActivationValue.Log2E; step.dst := HeteroActivationValue.T2 }
          is(3.U) { step.opcode := HeteroPrimitiveOpcode.SfuExp2; step.src0 := HeteroActivationValue.T2; step.dst := HeteroActivationValue.T0 }
          is(4.U) { step.opcode := HeteroPrimitiveOpcode.SfuAdd; step.src0 := HeteroActivationValue.One; step.src1 := HeteroActivationValue.T0; step.dst := HeteroActivationValue.T1 }
          is(5.U) { step.opcode := HeteroPrimitiveOpcode.SfuReciprocal; step.src0 := HeteroActivationValue.T1; step.dst := HeteroActivationValue.T2 }
          is(6.U) { step.opcode := HeteroPrimitiveOpcode.SfuMul; step.src0 := HeteroActivationValue.T0; step.src1 := HeteroActivationValue.T2; step.dst := HeteroActivationValue.T3 }
          is(7.U) { step.opcode := HeteroPrimitiveOpcode.SfuCompareSelect; step.src0 := HeteroActivationValue.T2; step.src1 := HeteroActivationValue.T3; step.dst := HeteroActivationValue.T0; step.variant := 1.U }
        }
      }.otherwise {
        step.opcode := HeteroPrimitiveOpcode.SfuMul
        step.src0 := HeteroActivationValue.Input
        step.src1 := HeteroActivationValue.T0
        step.dst := HeteroActivationValue.Output
      }
    }
    is(HeteroCompositeFunction.Gelu) {
      // Vision MLP GELU uses a separately characterized PWL table.
      step.opcode := HeteroPrimitiveOpcode.SfuPwl
      step.variant := 2.U
    }
    is(HeteroCompositeFunction.SignedSqrt) {
      // copysign(sqrt(max(abs(x), eps)), x) using rsqrt to share hardware.
      switch(phase) {
        is(0.U) { step.opcode := HeteroPrimitiveOpcode.SfuAbs; step.dst := HeteroActivationValue.T0 }
        is(1.U) { step.opcode := HeteroPrimitiveOpcode.SfuMax; step.src0 := HeteroActivationValue.T0; step.src1 := HeteroActivationValue.Epsilon; step.dst := HeteroActivationValue.T1 }
        is(2.U) { step.opcode := HeteroPrimitiveOpcode.SfuRsqrt; step.src0 := HeteroActivationValue.T1; step.dst := HeteroActivationValue.T2 }
        is(3.U) { step.opcode := HeteroPrimitiveOpcode.SfuMul; step.src0 := HeteroActivationValue.T1; step.src1 := HeteroActivationValue.T2; step.dst := HeteroActivationValue.T3 }
        is(4.U) { step.opcode := HeteroPrimitiveOpcode.SfuCompareSelect; step.src0 := HeteroActivationValue.T3; step.src1 := HeteroActivationValue.T3; step.dst := HeteroActivationValue.Output; step.variant := 2.U }
      }
    }
  }
  io.out.bits := step

  when(io.clear) {
    active := false.B
    phase := 0.U
  }.otherwise {
    when(io.start && io.startReady && requestedCount =/= 0.U) {
      function := io.function
      phase := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(step.last) {
        active := false.B
        phase := 0.U
        io.done := true.B
      }.otherwise {
        phase := phase + 1.U
      }
    }
  }
}

class HeteroPwlSegmentResult(val segmentBits: Int) extends Bundle {
  val segment = UInt(segmentBits.W)
  val input = UInt(32.W)
  val isNaN = Bool()
}

/** Sequential FP32 breakpoint search.  Only one comparison lies on the cycle
  * path, so increasing the number of PWL segments does not build a long mux
  * or priority chain. Breakpoints must be monotonically increasing.
  */
class HeteroFp32PwlSegmentSearch(val maxSegments: Int = 64) extends Module {
  require(maxSegments >= 2)
  private val segmentBits = log2Ceil(maxSegments)
  private val countBits = log2Ceil(maxSegments + 1)
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val input = Input(UInt(32.W))
    val segmentCount = Input(UInt(countBits.W))
    val breakpoints = Input(Vec(maxSegments - 1, UInt(32.W)))
    val out = Decoupled(new HeteroPwlSegmentResult(segmentBits))
    val busy = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val input = Reg(UInt(32.W))
  val count = Reg(UInt(countBits.W))
  val breakpoints = Reg(Vec(maxSegments - 1, UInt(32.W)))
  val index = RegInit(0.U(segmentBits.W))
  val outValid = RegInit(false.B)
  val result = Reg(new HeteroPwlSegmentResult(segmentBits))

  val configValid = io.segmentCount >= 2.U && io.segmentCount <= maxSegments.U
  io.startReady := !active && !outValid
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active || outValid
  io.out.valid := outValid
  io.out.bits := result

  val inputKey = HeteroFp32Order.key(input)
  val breakpointKey = HeteroFp32Order.key(breakpoints(index))
  val inputIsNaN = HeteroFp32Order.isNaN(input)
  val belowBreakpoint = !inputIsNaN && inputKey < breakpointKey
  val lastBreakpoint = index + 2.U >= count

  when(io.clear) {
    active := false.B
    outValid := false.B
    index := 0.U
  }.otherwise {
    when(outValid && io.out.ready) { outValid := false.B }
    when(io.start && io.startReady && configValid) {
      input := io.input
      count := io.segmentCount
      for (i <- 0 until maxSegments - 1) { breakpoints(i) := io.breakpoints(i) }
      index := 0.U
      active := true.B
    }
    when(active) {
      when(belowBreakpoint || lastBreakpoint || inputIsNaN) {
        result.segment := Mux(belowBreakpoint, index, Mux(inputIsNaN, (count - 1.U)(segmentBits - 1, 0), index + 1.U))
        result.input := input
        result.isNaN := inputIsNaN
        active := false.B
        outValid := true.B
      }.otherwise {
        index := index + 1.U
      }
    }
  }
}

class HeteroBlockPoolAddress(val blockBits: Int, val tokenBits: Int, val dimBits: Int) extends Bundle {
  val block = UInt(blockBits.W)
  val token = UInt(tokenBits.W)
  val dimension = UInt(dimBits.W)
  val firstToken = Bool()
  val lastToken = Bool()
  val lastDimension = Bool()
  val last = Bool()
}

/** Address/loop primitive for QSA block-average summaries. */
class HeteroBlockPoolAddressGenerator(
    val maxBlocks: Int = 262144,
    val maxRatio: Int = 16,
    val maxDimensions: Int = 256
) extends Module {
  require(maxBlocks > 0 && maxRatio > 0 && maxDimensions > 0)
  private val blockBits = math.max(1, log2Ceil(maxBlocks))
  private val blockCountBits = log2Ceil(maxBlocks + 1)
  private val tokenBits = math.max(1, log2Ceil(maxBlocks * maxRatio))
  private val ratioBits = log2Ceil(maxRatio + 1)
  private val dimBits = math.max(1, log2Ceil(maxDimensions))
  private val dimCountBits = log2Ceil(maxDimensions + 1)

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val blocks = Input(UInt(blockCountBits.W))
    val ratio = Input(UInt(ratioBits.W))
    val dimensions = Input(UInt(dimCountBits.W))
    val out = Decoupled(new HeteroBlockPoolAddress(blockBits, tokenBits, dimBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val blocks = Reg(UInt(blockCountBits.W))
  val ratio = Reg(UInt(ratioBits.W))
  val dimensions = Reg(UInt(dimCountBits.W))
  val block = RegInit(0.U(blockBits.W))
  val blockTokenBase = RegInit(0.U(tokenBits.W))
  val within = RegInit(0.U(ratioBits.W))
  val dimension = RegInit(0.U(dimBits.W))

  val configValid = io.blocks =/= 0.U && io.blocks <= maxBlocks.U &&
    io.ratio =/= 0.U && io.ratio <= maxRatio.U &&
    io.dimensions =/= 0.U && io.dimensions <= maxDimensions.U

  val lastWithin = within + 1.U >= ratio
  val lastDimension = dimension + 1.U >= dimensions
  val lastBlock = block + 1.U >= blocks

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.block := block
  io.out.bits.token := blockTokenBase + within
  io.out.bits.dimension := dimension
  io.out.bits.firstToken := within === 0.U
  io.out.bits.lastToken := lastWithin
  io.out.bits.lastDimension := lastDimension
  io.out.bits.last := lastWithin && lastDimension && lastBlock

  when(io.clear) {
    active := false.B
    block := 0.U
    blockTokenBase := 0.U
    within := 0.U
    dimension := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      blocks := io.blocks
      ratio := io.ratio
      dimensions := io.dimensions
      block := 0.U
      blockTokenBase := 0.U
      within := 0.U
      dimension := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(io.out.bits.last) {
        active := false.B
        io.done := true.B
      }.elsewhen(lastWithin) {
        within := 0.U
        when(lastDimension) {
          dimension := 0.U
          block := block + 1.U
          blockTokenBase := blockTokenBase + ratio
        }.otherwise {
          dimension := dimension + 1.U
        }
      }.otherwise {
        within := within + 1.U
      }
    }
  }
}
