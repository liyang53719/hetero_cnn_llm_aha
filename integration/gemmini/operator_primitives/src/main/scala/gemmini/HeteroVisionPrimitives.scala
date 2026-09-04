package gemmini

import chisel3._
import chisel3.util._

object HeteroMropeAxis {
  val width = 2
  val Temporal = 0.U(width.W)
  val Height = 1.U(width.W)
  val Width = 2.U(width.W)
}

class HeteroMropeMapEntry(val pairBits: Int) extends Bundle {
  val pair = UInt(pairBits.W)
  val axis = UInt(HeteroMropeAxis.width.W)
  val axisPair = UInt(pairBits.W)
  val last = Bool()
}

/** Generates the interleaved MRoPE source-axis map used by Qwen3.5 and
  * Qwen3.8.  For sections [11,11,10], pair positions are T,H,W,T,H,W...;
  * exhausted H/W positions fall back to T exactly as the reference does.
  */
class HeteroMropeSectionMap(val maxPairs: Int = 256) extends Module {
  require(maxPairs > 0)
  private val pairBits = math.max(1, log2Ceil(maxPairs))
  private val countBits = log2Ceil(maxPairs + 1)

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val pairCount = Input(UInt(countBits.W))
    val heightPairs = Input(UInt(countBits.W))
    val widthPairs = Input(UInt(countBits.W))
    val out = Decoupled(new HeteroMropeMapEntry(pairBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val pairCount = Reg(UInt(countBits.W))
  val heightPairs = Reg(UInt(countBits.W))
  val widthPairs = Reg(UInt(countBits.W))
  val pair = RegInit(0.U(pairBits.W))
  val phase = RegInit(0.U(2.W))
  val heightUsed = RegInit(0.U(pairBits.W))
  val widthUsed = RegInit(0.U(pairBits.W))

  val configValid = io.pairCount =/= 0.U && io.pairCount <= maxPairs.U &&
    io.heightPairs <= io.pairCount && io.widthPairs <= io.pairCount
  val chooseHeight = phase === 1.U && heightUsed < heightPairs
  val chooseWidth = phase === 2.U && widthUsed < widthPairs
  val axis = Mux(chooseHeight, HeteroMropeAxis.Height,
    Mux(chooseWidth, HeteroMropeAxis.Width, HeteroMropeAxis.Temporal))
  val axisPair = Mux(chooseHeight, heightUsed, Mux(chooseWidth, widthUsed, pair))
  val last = pair + 1.U >= pairCount

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.pair := pair
  io.out.bits.axis := axis
  io.out.bits.axisPair := axisPair
  io.out.bits.last := last

  when(io.clear) {
    active := false.B
    pair := 0.U
    phase := 0.U
    heightUsed := 0.U
    widthUsed := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      pairCount := io.pairCount
      heightPairs := io.heightPairs
      widthPairs := io.widthPairs
      pair := 0.U
      phase := 0.U
      heightUsed := 0.U
      widthUsed := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(chooseHeight) { heightUsed := heightUsed + 1.U }
      when(chooseWidth) { widthUsed := widthUsed + 1.U }
      when(last) {
        active := false.B
        io.done := true.B
      }.otherwise {
        pair := pair + 1.U
        phase := Mux(phase === 2.U, 0.U, phase + 1.U)
      }
    }
  }
}

class HeteroVisionWindowEntry(val coordBits: Int, val sequenceBits: Int) extends Bundle {
  val temporal = UInt(coordBits.W)
  val y = UInt(coordBits.W)
  val x = UInt(coordBits.W)
  val windowY = UInt(coordBits.W)
  val windowX = UInt(coordBits.W)
  val inWindowY = UInt(coordBits.W)
  val inWindowX = UInt(coordBits.W)
  val sequence = UInt(sequenceBits.W)
  val padding = Bool()
  val firstInWindow = Bool()
  val lastInWindow = Bool()
  val last = Bool()
}

/** Nested-counter raster-to-window layout.  Padded coordinates are emitted
  * with an explicit mask instead of being silently discarded, which preserves
  * positional alignment and enables deterministic inverse layout.
  */
class HeteroVisionWindowAddressGenerator(
    val maxCoordinate: Int = 4096,
    val maxSequence: Int = 1 << 24
) extends Module {
  require(maxCoordinate > 0 && maxSequence > 0)
  private val cb = math.max(1, log2Ceil(maxCoordinate))
  private val ccb = log2Ceil(maxCoordinate + 1)
  private val sb = math.max(1, log2Ceil(maxSequence))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val temporal = Input(UInt(ccb.W))
    val height = Input(UInt(ccb.W))
    val imageWidth = Input(UInt(ccb.W))
    val paddedHeight = Input(UInt(ccb.W))
    val paddedWidth = Input(UInt(ccb.W))
    val windowHeight = Input(UInt(ccb.W))
    val windowWidth = Input(UInt(ccb.W))
    val out = Decoupled(new HeteroVisionWindowEntry(cb, sb))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val temporalCount = Reg(UInt(ccb.W))
  val height = Reg(UInt(ccb.W))
  val width = Reg(UInt(ccb.W))
  val paddedHeight = Reg(UInt(ccb.W))
  val paddedWidth = Reg(UInt(ccb.W))
  val windowHeight = Reg(UInt(ccb.W))
  val windowWidth = Reg(UInt(ccb.W))
  val temporal = RegInit(0.U(cb.W))
  val windowBaseY = RegInit(0.U(cb.W))
  val windowBaseX = RegInit(0.U(cb.W))
  val inY = RegInit(0.U(cb.W))
  val inX = RegInit(0.U(cb.W))
  val sequence = RegInit(0.U(sb.W))

  val configValid = io.temporal =/= 0.U && io.temporal <= maxCoordinate.U &&
    io.height =/= 0.U && io.height <= maxCoordinate.U &&
    io.imageWidth =/= 0.U && io.imageWidth <= maxCoordinate.U &&
    io.paddedHeight >= io.height && io.paddedHeight <= maxCoordinate.U &&
    io.paddedWidth >= io.imageWidth && io.paddedWidth <= maxCoordinate.U &&
    io.windowHeight =/= 0.U && io.windowHeight <= io.paddedHeight &&
    io.windowWidth =/= 0.U && io.windowWidth <= io.paddedWidth

  val y = windowBaseY + inY
  val x = windowBaseX + inX
  val lastInX = inX + 1.U >= windowWidth
  val lastInY = inY + 1.U >= windowHeight
  val lastWindowX = windowBaseX + windowWidth >= paddedWidth
  val lastWindowY = windowBaseY + windowHeight >= paddedHeight
  val lastTemporal = temporal + 1.U >= temporalCount
  val last = lastInX && lastInY && lastWindowX && lastWindowY && lastTemporal

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.temporal := temporal
  io.out.bits.y := y
  io.out.bits.x := x
  io.out.bits.windowY := windowBaseY
  io.out.bits.windowX := windowBaseX
  io.out.bits.inWindowY := inY
  io.out.bits.inWindowX := inX
  io.out.bits.sequence := sequence
  io.out.bits.padding := y >= height || x >= width
  io.out.bits.firstInWindow := inY === 0.U && inX === 0.U
  io.out.bits.lastInWindow := lastInY && lastInX
  io.out.bits.last := last

  when(io.clear) {
    active := false.B
    temporal := 0.U
    windowBaseY := 0.U
    windowBaseX := 0.U
    inY := 0.U
    inX := 0.U
    sequence := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      temporalCount := io.temporal
      height := io.height
      width := io.imageWidth
      paddedHeight := io.paddedHeight
      paddedWidth := io.paddedWidth
      windowHeight := io.windowHeight
      windowWidth := io.windowWidth
      temporal := 0.U
      windowBaseY := 0.U
      windowBaseX := 0.U
      inY := 0.U
      inX := 0.U
      sequence := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(last) {
        active := false.B
        io.done := true.B
      }.otherwise {
        sequence := sequence + 1.U
        when(!lastInX) {
          inX := inX + 1.U
        }.otherwise {
          inX := 0.U
          when(!lastInY) {
            inY := inY + 1.U
          }.otherwise {
            inY := 0.U
            when(!lastWindowX) {
              windowBaseX := windowBaseX + windowWidth
            }.otherwise {
              windowBaseX := 0.U
              when(!lastWindowY) {
                windowBaseY := windowBaseY + windowHeight
              }.otherwise {
                windowBaseY := 0.U
                temporal := temporal + 1.U
              }
            }
          }
        }
      }
    }
  }
}

class HeteroVisionPatchMergeEntry(val coordBits: Int, val memberBits: Int, val outputBits: Int) extends Bundle {
  val temporal = UInt(coordBits.W)
  val sourceY = UInt(coordBits.W)
  val sourceX = UInt(coordBits.W)
  val member = UInt(memberBits.W)
  val outputPatch = UInt(outputBits.W)
  val sourceValid = Bool()
  val firstMember = Bool()
  val lastMember = Bool()
  val last = Bool()
}

/** Patch-merger coordinate generator.  Partial edge groups remain explicit via
  * sourceValid, allowing either zero padding or a compiler-selected crop.
  */
class HeteroVisionPatchMergeAddressGenerator(
    val maxCoordinate: Int = 4096,
    val maxMerge: Int = 8,
    val maxOutputPatches: Int = 1 << 24
) extends Module {
  require(maxCoordinate > 0 && maxMerge > 0 && maxOutputPatches > 0)
  private val cb = math.max(1, log2Ceil(maxCoordinate))
  private val ccb = log2Ceil(maxCoordinate + 1)
  private val mb = math.max(1, log2Ceil(maxMerge * maxMerge))
  private val ob = math.max(1, log2Ceil(maxOutputPatches))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val temporal = Input(UInt(ccb.W))
    val height = Input(UInt(ccb.W))
    val imageWidth = Input(UInt(ccb.W))
    val mergeHeight = Input(UInt(log2Ceil(maxMerge + 1).W))
    val mergeWidth = Input(UInt(log2Ceil(maxMerge + 1).W))
    val out = Decoupled(new HeteroVisionPatchMergeEntry(cb, mb, ob))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val temporalCount = Reg(UInt(ccb.W))
  val height = Reg(UInt(ccb.W))
  val width = Reg(UInt(ccb.W))
  val mergeHeight = Reg(UInt(log2Ceil(maxMerge + 1).W))
  val mergeWidth = Reg(UInt(log2Ceil(maxMerge + 1).W))
  val temporal = RegInit(0.U(cb.W))
  val baseY = RegInit(0.U(cb.W))
  val baseX = RegInit(0.U(cb.W))
  val inY = RegInit(0.U(log2Ceil(maxMerge + 1).W))
  val inX = RegInit(0.U(log2Ceil(maxMerge + 1).W))
  val outputPatch = RegInit(0.U(ob.W))

  val configValid = io.temporal =/= 0.U && io.temporal <= maxCoordinate.U &&
    io.height =/= 0.U && io.height <= maxCoordinate.U &&
    io.imageWidth =/= 0.U && io.imageWidth <= maxCoordinate.U &&
    io.mergeHeight =/= 0.U && io.mergeHeight <= maxMerge.U &&
    io.mergeWidth =/= 0.U && io.mergeWidth <= maxMerge.U
  val sourceY = baseY + inY
  val sourceX = baseX + inX
  val lastInX = inX + 1.U >= mergeWidth
  val lastInY = inY + 1.U >= mergeHeight
  val lastBaseX = baseX + mergeWidth >= width
  val lastBaseY = baseY + mergeHeight >= height
  val lastTemporal = temporal + 1.U >= temporalCount
  val last = lastInX && lastInY && lastBaseX && lastBaseY && lastTemporal

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.temporal := temporal
  io.out.bits.sourceY := sourceY
  io.out.bits.sourceX := sourceX
  io.out.bits.member := (inY * mergeWidth + inX)(mb - 1, 0)
  io.out.bits.outputPatch := outputPatch
  io.out.bits.sourceValid := sourceY < height && sourceX < width
  io.out.bits.firstMember := inY === 0.U && inX === 0.U
  io.out.bits.lastMember := lastInY && lastInX
  io.out.bits.last := last

  when(io.clear) {
    active := false.B
    temporal := 0.U
    baseY := 0.U
    baseX := 0.U
    inY := 0.U
    inX := 0.U
    outputPatch := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      temporalCount := io.temporal
      height := io.height
      width := io.imageWidth
      mergeHeight := io.mergeHeight
      mergeWidth := io.mergeWidth
      temporal := 0.U
      baseY := 0.U
      baseX := 0.U
      inY := 0.U
      inX := 0.U
      outputPatch := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(last) {
        active := false.B
        io.done := true.B
      }.elsewhen(!lastInX) {
        inX := inX + 1.U
      }.otherwise {
        inX := 0.U
        when(!lastInY) {
          inY := inY + 1.U
        }.otherwise {
          inY := 0.U
          outputPatch := outputPatch + 1.U
          when(!lastBaseX) {
            baseX := baseX + mergeWidth
          }.otherwise {
            baseX := 0.U
            when(!lastBaseY) {
              baseY := baseY + mergeHeight
            }.otherwise {
              baseY := 0.U
              temporal := temporal + 1.U
            }
          }
        }
      }
    }
  }
}

class HeteroVisionBilinearResult(val coordinateBits: Int, val fractionBits: Int) extends Bundle {
  val y0 = UInt(coordinateBits.W)
  val y1 = UInt(coordinateBits.W)
  val x0 = UInt(coordinateBits.W)
  val x1 = UInt(coordinateBits.W)
  val yFraction = UInt(fractionBits.W)
  val xFraction = UInt(fractionBits.W)
}

/** Align-corners bilinear interpolation index generator. Runtime multiply and
  * divide are both iterative, keeping the control path friendly to 800 MHz.
  */
class HeteroVisionBilinearIndex(
    val coordinateBits: Int = 24,
    val fractionBits: Int = 16
) extends Module {
  require(coordinateBits > 1 && fractionBits > 0 && coordinateBits + fractionBits <= 64)
  private val workBits = 32
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val destinationY = Input(UInt(coordinateBits.W))
    val destinationX = Input(UInt(coordinateBits.W))
    val sourceHeight = Input(UInt(coordinateBits.W))
    val sourceWidth = Input(UInt(coordinateBits.W))
    val destinationHeight = Input(UInt(coordinateBits.W))
    val destinationWidth = Input(UInt(coordinateBits.W))
    val out = Decoupled(new HeteroVisionBilinearResult(coordinateBits, fractionBits))
    val busy = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val yMultiply = Module(new HeteroUnsignedMultiply(workBits))
  val xMultiply = Module(new HeteroUnsignedMultiply(workBits))
  val yDivide = Module(new HeteroUnsignedDivide(64))
  val xDivide = Module(new HeteroUnsignedDivide(64))
  val sIdle :: sMultiply :: sDivideStart :: sDivide :: sOutput :: Nil = Enum(5)
  val state = RegInit(sIdle)
  val sourceHeight = Reg(UInt(coordinateBits.W))
  val sourceWidth = Reg(UInt(coordinateBits.W))
  val destinationHeight = Reg(UInt(coordinateBits.W))
  val destinationWidth = Reg(UInt(coordinateBits.W))
  val yProduct = Reg(UInt(64.W))
  val xProduct = Reg(UInt(64.W))
  val result = Reg(new HeteroVisionBilinearResult(coordinateBits, fractionBits))
  val outValid = RegInit(false.B)

  val configValid = io.sourceHeight =/= 0.U && io.sourceWidth =/= 0.U &&
    io.destinationHeight =/= 0.U && io.destinationWidth =/= 0.U &&
    io.destinationY < io.destinationHeight && io.destinationX < io.destinationWidth
  val launch = io.start && io.startReady && configValid

  yMultiply.io.clear := io.clear
  xMultiply.io.clear := io.clear
  yMultiply.io.start := launch
  xMultiply.io.start := launch
  yMultiply.io.left := io.destinationY.pad(workBits)
  yMultiply.io.right := (io.sourceHeight - 1.U).pad(workBits)
  xMultiply.io.left := io.destinationX.pad(workBits)
  xMultiply.io.right := (io.sourceWidth - 1.U).pad(workBits)
  val productsReady = yMultiply.io.out.valid && xMultiply.io.out.valid
  yMultiply.io.out.ready := state === sMultiply && productsReady
  xMultiply.io.out.ready := state === sMultiply && productsReady

  yDivide.io.clear := io.clear
  xDivide.io.clear := io.clear
  val launchDivide = state === sDivideStart && yDivide.io.startReady && xDivide.io.startReady
  yDivide.io.start := launchDivide
  xDivide.io.start := launchDivide
  yDivide.io.dividend := (yProduct << fractionBits)(63, 0)
  xDivide.io.dividend := (xProduct << fractionBits)(63, 0)
  yDivide.io.divisor := Mux(destinationHeight <= 1.U, 1.U, destinationHeight - 1.U).pad(64)
  xDivide.io.divisor := Mux(destinationWidth <= 1.U, 1.U, destinationWidth - 1.U).pad(64)
  val divisionsReady = yDivide.io.out.valid && xDivide.io.out.valid && !outValid
  yDivide.io.out.ready := state === sDivide && divisionsReady
  xDivide.io.out.ready := state === sDivide && divisionsReady

  io.startReady := state === sIdle && yMultiply.io.startReady && xMultiply.io.startReady && !outValid
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := state =/= sIdle
  io.out.valid := outValid
  io.out.bits := result

  when(io.clear) {
    state := sIdle
    outValid := false.B
  }.otherwise {
    when(outValid && io.out.ready) {
      outValid := false.B
      state := sIdle
    }
    switch(state) {
      is(sIdle) {
        when(launch) {
          sourceHeight := io.sourceHeight
          sourceWidth := io.sourceWidth
          destinationHeight := io.destinationHeight
          destinationWidth := io.destinationWidth
          state := sMultiply
        }
      }
      is(sMultiply) {
        when(productsReady) {
          yProduct := yMultiply.io.out.bits.product
          xProduct := xMultiply.io.out.bits.product
          state := sDivideStart
        }
      }
      is(sDivideStart) {
        when(launchDivide) { state := sDivide }
      }
      is(sDivide) {
        when(divisionsReady) {
          val yFixed = yDivide.io.out.bits.quotient
          val xFixed = xDivide.io.out.bits.quotient
          val y0Wide = yFixed >> fractionBits
          val x0Wide = xFixed >> fractionBits
          val y0 = y0Wide(coordinateBits - 1, 0)
          val x0 = x0Wide(coordinateBits - 1, 0)
          result.y0 := y0
          result.x0 := x0
          result.y1 := Mux(y0 + 1.U < sourceHeight, y0 + 1.U, y0)
          result.x1 := Mux(x0 + 1.U < sourceWidth, x0 + 1.U, x0)
          result.yFraction := yFixed(fractionBits - 1, 0)
          result.xFraction := xFixed(fractionBits - 1, 0)
          outValid := true.B
          state := sOutput
        }
      }
      is(sOutput) { }
    }
  }
}

class HeteroVisionPatch3dEntry(val coordBits: Int, val channelBits: Int, val tapBits: Int) extends Bundle {
  val outputTemporal = UInt(coordBits.W)
  val outputY = UInt(coordBits.W)
  val outputX = UInt(coordBits.W)
  val inputTemporal = UInt(coordBits.W)
  val inputY = UInt(coordBits.W)
  val inputX = UInt(coordBits.W)
  val channel = UInt(channelBits.W)
  val kernelTemporal = UInt(tapBits.W)
  val kernelY = UInt(tapBits.W)
  val kernelX = UInt(tapBits.W)
  val firstTap = Bool()
  val lastTap = Bool()
  val last = Bool()
}

/** Conv3D patch/tubelet coordinate generator.  Coordinates rather than a
  * monolithic flattened address keep runtime dimension products out of the
  * critical path; the DMA descriptor layer performs the final stride sum.
  */
class HeteroVisionPatch3dAddressGenerator(
    val maxCoordinate: Int = 4096,
    val maxChannels: Int = 8,
    val maxKernel: Int = 16
) extends Module {
  require(maxCoordinate > 0 && maxChannels > 0 && maxKernel > 0)
  private val cb = math.max(1, log2Ceil(maxCoordinate * maxKernel))
  private val ccb = log2Ceil(maxCoordinate + 1)
  private val chb = math.max(1, log2Ceil(maxChannels))
  private val chcb = log2Ceil(maxChannels + 1)
  private val kb = math.max(1, log2Ceil(maxKernel))
  private val kcb = log2Ceil(maxKernel + 1)

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val outputTemporal = Input(UInt(ccb.W))
    val outputHeight = Input(UInt(ccb.W))
    val outputWidth = Input(UInt(ccb.W))
    val channels = Input(UInt(chcb.W))
    val kernelTemporal = Input(UInt(kcb.W))
    val kernelHeight = Input(UInt(kcb.W))
    val kernelWidth = Input(UInt(kcb.W))
    val strideTemporal = Input(UInt(kcb.W))
    val strideHeight = Input(UInt(kcb.W))
    val strideWidth = Input(UInt(kcb.W))
    val out = Decoupled(new HeteroVisionPatch3dEntry(cb, chb, kb))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val outTCount = Reg(UInt(ccb.W))
  val outHCount = Reg(UInt(ccb.W))
  val outWCount = Reg(UInt(ccb.W))
  val channelCount = Reg(UInt(chcb.W))
  val ktCount = Reg(UInt(kcb.W))
  val khCount = Reg(UInt(kcb.W))
  val kwCount = Reg(UInt(kcb.W))
  val strideT = Reg(UInt(kcb.W))
  val strideH = Reg(UInt(kcb.W))
  val strideW = Reg(UInt(kcb.W))
  val outT = RegInit(0.U(cb.W))
  val outY = RegInit(0.U(cb.W))
  val outX = RegInit(0.U(cb.W))
  val channel = RegInit(0.U(chb.W))
  val kt = RegInit(0.U(kb.W))
  val kh = RegInit(0.U(kb.W))
  val kw = RegInit(0.U(kb.W))
  val baseT = RegInit(0.U(cb.W))
  val baseY = RegInit(0.U(cb.W))
  val baseX = RegInit(0.U(cb.W))

  val configValid = io.outputTemporal =/= 0.U && io.outputTemporal <= maxCoordinate.U &&
    io.outputHeight =/= 0.U && io.outputHeight <= maxCoordinate.U &&
    io.outputWidth =/= 0.U && io.outputWidth <= maxCoordinate.U &&
    io.channels =/= 0.U && io.channels <= maxChannels.U &&
    io.kernelTemporal =/= 0.U && io.kernelTemporal <= maxKernel.U &&
    io.kernelHeight =/= 0.U && io.kernelHeight <= maxKernel.U &&
    io.kernelWidth =/= 0.U && io.kernelWidth <= maxKernel.U &&
    io.strideTemporal =/= 0.U && io.strideHeight =/= 0.U && io.strideWidth =/= 0.U

  val lastKw = kw + 1.U >= kwCount
  val lastKh = kh + 1.U >= khCount
  val lastKt = kt + 1.U >= ktCount
  val lastChannel = channel + 1.U >= channelCount
  val lastOutX = outX + 1.U >= outWCount
  val lastOutY = outY + 1.U >= outHCount
  val lastOutT = outT + 1.U >= outTCount
  val lastTap = lastKw && lastKh && lastKt && lastChannel
  val last = lastTap && lastOutX && lastOutY && lastOutT

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.outputTemporal := outT
  io.out.bits.outputY := outY
  io.out.bits.outputX := outX
  io.out.bits.inputTemporal := baseT + kt
  io.out.bits.inputY := baseY + kh
  io.out.bits.inputX := baseX + kw
  io.out.bits.channel := channel
  io.out.bits.kernelTemporal := kt
  io.out.bits.kernelY := kh
  io.out.bits.kernelX := kw
  io.out.bits.firstTap := kt === 0.U && kh === 0.U && kw === 0.U && channel === 0.U
  io.out.bits.lastTap := lastTap
  io.out.bits.last := last

  when(io.clear) {
    active := false.B
    outT := 0.U; outY := 0.U; outX := 0.U
    channel := 0.U; kt := 0.U; kh := 0.U; kw := 0.U
    baseT := 0.U; baseY := 0.U; baseX := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      outTCount := io.outputTemporal
      outHCount := io.outputHeight
      outWCount := io.outputWidth
      channelCount := io.channels
      ktCount := io.kernelTemporal
      khCount := io.kernelHeight
      kwCount := io.kernelWidth
      strideT := io.strideTemporal
      strideH := io.strideHeight
      strideW := io.strideWidth
      outT := 0.U; outY := 0.U; outX := 0.U
      channel := 0.U; kt := 0.U; kh := 0.U; kw := 0.U
      baseT := 0.U; baseY := 0.U; baseX := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(last) {
        active := false.B
        io.done := true.B
      }.elsewhen(!lastKw) {
        kw := kw + 1.U
      }.otherwise {
        kw := 0.U
        when(!lastKh) {
          kh := kh + 1.U
        }.otherwise {
          kh := 0.U
          when(!lastKt) {
            kt := kt + 1.U
          }.otherwise {
            kt := 0.U
            when(!lastChannel) {
              channel := channel + 1.U
            }.otherwise {
              channel := 0.U
              when(!lastOutX) {
                outX := outX + 1.U
                baseX := baseX + strideW
              }.otherwise {
                outX := 0.U
                baseX := 0.U
                when(!lastOutY) {
                  outY := outY + 1.U
                  baseY := baseY + strideH
                }.otherwise {
                  outY := 0.U
                  baseY := 0.U
                  outT := outT + 1.U
                  baseT := baseT + strideT
                }
              }
            }
          }
        }
      }
    }
  }
}
