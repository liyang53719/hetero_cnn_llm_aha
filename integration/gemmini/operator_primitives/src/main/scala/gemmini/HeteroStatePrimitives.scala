package gemmini

import chisel3._
import chisel3.util._

class HeteroCausalConvTap(
    val addrBits: Int,
    val channelBits: Int,
    val tokenBits: Int,
    val tapBits: Int
) extends Bundle {
  val token = UInt(tokenBits.W)
  val channel = UInt(channelBits.W)
  val tap = UInt(tapBits.W)
  val useCurrent = Bool()
  val historyValid = Bool()
  val historyReadAddress = UInt(addrBits.W)
  val historyWriteAddress = UInt(addrBits.W)
  val first = Bool()
  val lastInSample = Bool()
  val last = Bool()
}

/** External-state address generator for GDN and PLE causal or dilated
  * depthwise convolution. Per-channel history is always external SRAM or DDR;
  * no vector proportional to maxChannels is instantiated as registers.
  */
class HeteroCausalConvAddressGenerator(
    val maxChannels: Int = 16384,
    val maxKernel: Int = 8,
    val maxDilation: Int = 8,
    val addrBits: Int = 64,
    val tokenBits: Int = 32
) extends Module {
  require(maxChannels > 0 && maxKernel >= 2 && maxDilation > 0)
  private val channelBits = math.max(1, log2Ceil(maxChannels))
  private val channelCountBits = log2Ceil(maxChannels + 1)
  private val tapBits = math.max(1, log2Ceil(maxKernel))
  private val kernelBits = log2Ceil(maxKernel + 1)
  private val dilationBits = log2Ceil(maxDilation + 1)
  private val depthMax = (maxKernel - 1) * maxDilation
  private val depthBits = math.max(1, log2Ceil(depthMax + 1))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val tokenCount = Input(UInt(tokenBits.W))
    val channels = Input(UInt(channelCountBits.W))
    val kernel = Input(UInt(kernelBits.W))
    val dilation = Input(UInt(dilationBits.W))
    val initialValidTokens = Input(UInt(depthBits.W))
    val initialWriteSlot = Input(UInt(depthBits.W))
    val historyBase = Input(UInt(addrBits.W))
    val elementBytes = Input(UInt(3.W))
    val out = Decoupled(new HeteroCausalConvTap(addrBits, channelBits, tokenBits, tapBits))
    val finalWriteSlot = Output(UInt(depthBits.W))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val tokens = Reg(UInt(tokenBits.W))
  val channels = Reg(UInt(channelCountBits.W))
  val kernel = Reg(UInt(kernelBits.W))
  val dilation = Reg(UInt(dilationBits.W))
  val initialValid = Reg(UInt(depthBits.W))
  val writeSlot = RegInit(0.U(depthBits.W))
  val base = Reg(UInt(addrBits.W))
  val bytes = Reg(UInt(3.W))
  val token = RegInit(0.U(tokenBits.W))
  val channel = RegInit(0.U(channelBits.W))
  val tap = RegInit(0.U(tapBits.W))

  val requestedDepth = (io.kernel - 1.U) * io.dilation
  val configValid = io.tokenCount =/= 0.U &&
    io.channels =/= 0.U && io.channels <= maxChannels.U &&
    io.kernel >= 2.U && io.kernel <= maxKernel.U &&
    io.dilation =/= 0.U && io.dilation <= maxDilation.U &&
    (io.elementBytes === 2.U || io.elementBytes === 4.U) &&
    io.initialWriteSlot < requestedDepth &&
    io.initialValidTokens <= requestedDepth

  val historyDepth = (kernel - 1.U) * dilation
  val past = tap * dilation
  val availableWide = initialValid +& token
  val available = Mux(availableWide > historyDepth, historyDepth, availableWide)
  val wrappedReadSlot = Mux(writeSlot >= past, writeSlot - past, writeSlot + historyDepth - past)
  val readLinear = wrappedReadSlot * channels + channel
  val writeLinear = writeSlot * channels + channel
  val readByteOffset = Mux(bytes === 2.U, readLinear << 1, readLinear << 2).pad(addrBits)
  val writeByteOffset = Mux(bytes === 2.U, writeLinear << 1, writeLinear << 2).pad(addrBits)

  val lastTap = tap + 1.U >= kernel
  val lastChannel = channel + 1.U >= channels
  val lastToken = token + 1.U >= tokens
  val nextWriteSlot = Mux(writeSlot + 1.U >= historyDepth, 0.U, writeSlot + 1.U)

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.finalWriteSlot := writeSlot
  io.out.valid := active
  io.out.bits.token := token
  io.out.bits.channel := channel
  io.out.bits.tap := tap
  io.out.bits.useCurrent := tap === 0.U
  io.out.bits.historyValid := tap === 0.U || past <= available
  io.out.bits.historyReadAddress := base + readByteOffset
  io.out.bits.historyWriteAddress := base + writeByteOffset
  io.out.bits.first := tap === 0.U
  io.out.bits.lastInSample := lastTap
  io.out.bits.last := lastTap && lastChannel && lastToken

  when(io.clear) {
    active := false.B
    token := 0.U
    channel := 0.U
    tap := 0.U
    writeSlot := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      tokens := io.tokenCount
      channels := io.channels
      kernel := io.kernel
      dilation := io.dilation
      initialValid := io.initialValidTokens
      writeSlot := io.initialWriteSlot
      base := io.historyBase
      bytes := io.elementBytes
      token := 0.U
      channel := 0.U
      tap := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(!lastTap) {
        tap := tap + 1.U
      }.otherwise {
        tap := 0.U
        when(!lastChannel) {
          channel := channel + 1.U
        }.otherwise {
          channel := 0.U
          writeSlot := nextWriteSlot
          when(lastToken) {
            active := false.B
            io.done := true.B
          }.otherwise {
            token := token + 1.U
          }
        }
      }
    }
  }

  when(active) {
    assert(historyDepth =/= 0.U)
    assert(writeSlot < historyDepth)
    assert(channel < channels)
    assert(tap < kernel)
  }
}

object HeteroGdnStatePass {
  val width = 2
  val Decay = 0.U(width.W)
  val KeyReadout = 1.U(width.W)
  val OuterUpdate = 2.U(width.W)
  val QueryReadout = 3.U(width.W)
}

class HeteroGdnStateAddress(
    val addrBits: Int,
    val headBits: Int,
    val dimBits: Int
) extends Bundle {
  val address = UInt(addrBits.W)
  val head = UInt(headBits.W)
  val keyIndex = UInt(dimBits.W)
  val valueIndex = UInt(dimBits.W)
  val pass = UInt(HeteroGdnStatePass.width.W)
  val write = Bool()
  val lastInPass = Bool()
  val last = Bool()
}

/** Four-pass Gated-Delta recurrent-state walker M[head][K][V]. A running
  * linear index replaces runtime three-dimensional address multiplication.
  */
class HeteroGdnStateAddressGenerator(
    val maxHeads: Int = 64,
    val maxDim: Int = 256,
    val addrBits: Int = 64
) extends Module {
  require(maxHeads > 0 && maxDim > 0)
  private val headBits = math.max(1, log2Ceil(maxHeads))
  private val headCountBits = log2Ceil(maxHeads + 1)
  private val dimBits = math.max(1, log2Ceil(maxDim))
  private val dimCountBits = log2Ceil(maxDim + 1)
  private val linearBits = math.max(1, log2Ceil(maxHeads * maxDim * maxDim))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val baseAddress = Input(UInt(addrBits.W))
    val heads = Input(UInt(headCountBits.W))
    val keyDim = Input(UInt(dimCountBits.W))
    val valueDim = Input(UInt(dimCountBits.W))
    val out = Decoupled(new HeteroGdnStateAddress(addrBits, headBits, dimBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val base = Reg(UInt(addrBits.W))
  val heads = Reg(UInt(headCountBits.W))
  val keyDim = Reg(UInt(dimCountBits.W))
  val valueDim = Reg(UInt(dimCountBits.W))
  val pass = RegInit(HeteroGdnStatePass.Decay)
  val head = RegInit(0.U(headBits.W))
  val key = RegInit(0.U(dimBits.W))
  val value = RegInit(0.U(dimBits.W))
  val linear = RegInit(0.U(linearBits.W))

  val configValid = io.heads =/= 0.U && io.heads <= maxHeads.U &&
    io.keyDim =/= 0.U && io.keyDim <= maxDim.U &&
    io.valueDim =/= 0.U && io.valueDim <= maxDim.U
  val lastValue = value + 1.U >= valueDim
  val lastKey = key + 1.U >= keyDim
  val lastHead = head + 1.U >= heads
  val lastPass = pass === HeteroGdnStatePass.QueryReadout
  val lastInPass = lastValue && lastKey && lastHead
  val byteOffset = (linear << 2).pad(addrBits)

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.address := base + byteOffset
  io.out.bits.head := head
  io.out.bits.keyIndex := key
  io.out.bits.valueIndex := value
  io.out.bits.pass := pass
  io.out.bits.write := pass === HeteroGdnStatePass.Decay || pass === HeteroGdnStatePass.OuterUpdate
  io.out.bits.lastInPass := lastInPass
  io.out.bits.last := lastInPass && lastPass

  when(io.clear) {
    active := false.B
    pass := HeteroGdnStatePass.Decay
    head := 0.U
    key := 0.U
    value := 0.U
    linear := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      base := io.baseAddress
      heads := io.heads
      keyDim := io.keyDim
      valueDim := io.valueDim
      pass := HeteroGdnStatePass.Decay
      head := 0.U
      key := 0.U
      value := 0.U
      linear := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(!lastValue) {
        value := value + 1.U
        linear := linear + 1.U
      }.otherwise {
        value := 0.U
        when(!lastKey) {
          key := key + 1.U
          linear := linear + 1.U
        }.otherwise {
          key := 0.U
          when(!lastHead) {
            head := head + 1.U
            linear := linear + 1.U
          }.otherwise {
            head := 0.U
            linear := 0.U
            when(lastPass) {
              active := false.B
              io.done := true.B
            }.otherwise {
              pass := pass + 1.U
            }
          }
        }
      }
    }
  }

  when(active) {
    assert(head < heads)
    assert(key < keyDim)
    assert(value < valueDim)
  }
}

object HeteroNormMode {
  val width = 2
  val Rms = 0.U(width.W)
  val GroupRms = 1.U(width.W)
  val LayerNorm = 2.U(width.W)
  val L2Norm = 3.U(width.W)
}
object HeteroNormPass {
  val width = 2
  val Sum = 0.U(width.W)
  val SquareSum = 1.U(width.W)
  val Normalize = 2.U(width.W)
}

class HeteroNormElementAddress(
    val addrBits: Int,
    val groupBits: Int,
    val elementBits: Int
) extends Bundle {
  val inputAddress = UInt(addrBits.W)
  val weightAddress = UInt(addrBits.W)
  val biasAddress = UInt(addrBits.W)
  val outputAddress = UInt(addrBits.W)
  val group = UInt(groupBits.W)
  val element = UInt(elementBits.W)
  val mode = UInt(HeteroNormMode.width.W)
  val pass = UInt(HeteroNormPass.width.W)
  val accumulate = Bool()
  val writeOutput = Bool()
  val lastInGroup = Bool()
  val last = Bool()
}

/** Variable-shape RMSNorm, group-RMSNorm, LayerNorm and L2Norm scheduler.
  * A monotonically increasing element index keeps runtime address generation
  * off the normalization arithmetic path.
  */
class HeteroNormAddressGenerator(
    val maxGroups: Int = 8,
    val maxElements: Int = 16384,
    val addrBits: Int = 64
) extends Module {
  require(maxGroups > 0 && maxElements > 0)
  private val groupBits = math.max(1, log2Ceil(maxGroups))
  private val groupCountBits = log2Ceil(maxGroups + 1)
  private val elementBits = math.max(1, log2Ceil(maxElements))
  private val elementCountBits = log2Ceil(maxElements + 1)
  private val linearBits = math.max(1, log2Ceil(maxGroups * maxElements))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val mode = Input(UInt(HeteroNormMode.width.W))
    val groups = Input(UInt(groupCountBits.W))
    val elementsPerGroup = Input(UInt(elementCountBits.W))
    val inputBase = Input(UInt(addrBits.W))
    val weightBase = Input(UInt(addrBits.W))
    val biasBase = Input(UInt(addrBits.W))
    val outputBase = Input(UInt(addrBits.W))
    val elementBytes = Input(UInt(3.W))
    val affinePerGroup = Input(Bool())
    val out = Decoupled(new HeteroNormElementAddress(addrBits, groupBits, elementBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val mode = Reg(UInt(HeteroNormMode.width.W))
  val groups = Reg(UInt(groupCountBits.W))
  val elements = Reg(UInt(elementCountBits.W))
  val inputBase = Reg(UInt(addrBits.W))
  val weightBase = Reg(UInt(addrBits.W))
  val biasBase = Reg(UInt(addrBits.W))
  val outputBase = Reg(UInt(addrBits.W))
  val bytes = Reg(UInt(3.W))
  val affinePerGroup = Reg(Bool())
  val pass = RegInit(HeteroNormPass.SquareSum)
  val group = RegInit(0.U(groupBits.W))
  val element = RegInit(0.U(elementBits.W))
  val linear = RegInit(0.U(linearBits.W))

  val configValid = io.mode <= HeteroNormMode.L2Norm &&
    io.groups =/= 0.U && io.groups <= maxGroups.U &&
    io.elementsPerGroup =/= 0.U && io.elementsPerGroup <= maxElements.U &&
    (io.elementBytes === 2.U || io.elementBytes === 4.U)
  val lastElement = element + 1.U >= elements
  val lastGroup = group + 1.U >= groups
  val lastPass = pass === HeteroNormPass.Normalize
  val affineIndex = Mux(affinePerGroup, linear, element)
  val dataOffset = Mux(bytes === 2.U, linear << 1, linear << 2).pad(addrBits)
  val affineOffset = Mux(bytes === 2.U, affineIndex << 1, affineIndex << 2).pad(addrBits)

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.inputAddress := inputBase + dataOffset
  io.out.bits.weightAddress := weightBase + affineOffset
  io.out.bits.biasAddress := biasBase + affineOffset
  io.out.bits.outputAddress := outputBase + dataOffset
  io.out.bits.group := group
  io.out.bits.element := element
  io.out.bits.mode := mode
  io.out.bits.pass := pass
  io.out.bits.accumulate := pass =/= HeteroNormPass.Normalize
  io.out.bits.writeOutput := pass === HeteroNormPass.Normalize
  io.out.bits.lastInGroup := lastElement
  io.out.bits.last := lastElement && lastGroup && lastPass

  when(io.clear) {
    active := false.B
    pass := HeteroNormPass.SquareSum
    group := 0.U
    element := 0.U
    linear := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      mode := io.mode
      groups := io.groups
      elements := io.elementsPerGroup
      inputBase := io.inputBase
      weightBase := io.weightBase
      biasBase := io.biasBase
      outputBase := io.outputBase
      bytes := io.elementBytes
      affinePerGroup := io.affinePerGroup
      pass := Mux(io.mode === HeteroNormMode.LayerNorm, HeteroNormPass.Sum, HeteroNormPass.SquareSum)
      group := 0.U
      element := 0.U
      linear := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(!lastElement) {
        element := element + 1.U
        linear := linear + 1.U
      }.otherwise {
        element := 0.U
        when(!lastGroup) {
          group := group + 1.U
          linear := linear + 1.U
        }.otherwise {
          group := 0.U
          linear := 0.U
          when(lastPass) {
            active := false.B
            io.done := true.B
          }.elsewhen(pass === HeteroNormPass.Sum) {
            pass := HeteroNormPass.SquareSum
          }.otherwise {
            pass := HeteroNormPass.Normalize
          }
        }
      }
    }
  }

  when(active) {
    assert(group < groups)
    assert(element < elements)
  }
}

object HeteroGatedResidualMode {
  val width = 1
  val ReadMix = 0.U(width.W)
  val WriteInject = 1.U(width.W)
}

class HeteroGatedResidualAddress(
    val branchBits: Int,
    val dimBits: Int,
    val indexBits: Int
) extends Bundle {
  val mode = UInt(HeteroGatedResidualMode.width.W)
  val branch = UInt(branchBits.W)
  val dimension = UInt(dimBits.W)
  val hyperIndex = UInt(indexBits.W)
  val blockIndex = UInt(indexBits.W)
  val firstBranch = Bool()
  val lastBranch = Bool()
  val last = Bool()
}

class HeteroGatedResidualAddressGenerator(
    val maxBranches: Int = 8,
    val maxHidden: Int = 16384,
    val indexBits: Int = 32
) extends Module {
  require(maxBranches > 0 && maxHidden > 0)
  private val branchBits = math.max(1, log2Ceil(maxBranches))
  private val branchCountBits = log2Ceil(maxBranches + 1)
  private val dimBits = math.max(1, log2Ceil(maxHidden))
  private val dimCountBits = log2Ceil(maxHidden + 1)
  private val linearBits = math.max(1, log2Ceil(maxBranches * maxHidden))

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val mode = Input(UInt(HeteroGatedResidualMode.width.W))
    val branches = Input(UInt(branchCountBits.W))
    val hidden = Input(UInt(dimCountBits.W))
    val out = Decoupled(new HeteroGatedResidualAddress(branchBits, dimBits, indexBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val active = RegInit(false.B)
  val mode = Reg(UInt(HeteroGatedResidualMode.width.W))
  val branches = Reg(UInt(branchCountBits.W))
  val hidden = Reg(UInt(dimCountBits.W))
  val branch = RegInit(0.U(branchBits.W))
  val dimension = RegInit(0.U(dimBits.W))
  val linear = RegInit(0.U(linearBits.W))

  val configValid = io.branches =/= 0.U && io.branches <= maxBranches.U &&
    io.hidden =/= 0.U && io.hidden <= maxHidden.U
  val lastDimension = dimension + 1.U >= hidden
  val lastBranch = branch + 1.U >= branches

  io.startReady := !active
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := active
  io.done := false.B
  io.out.valid := active
  io.out.bits.mode := mode
  io.out.bits.branch := branch
  io.out.bits.dimension := dimension
  io.out.bits.hyperIndex := linear.pad(indexBits)
  io.out.bits.blockIndex := dimension.pad(indexBits)
  io.out.bits.firstBranch := branch === 0.U
  io.out.bits.lastBranch := lastBranch
  io.out.bits.last := lastDimension && lastBranch

  when(io.clear) {
    active := false.B
    branch := 0.U
    dimension := 0.U
    linear := 0.U
  }.otherwise {
    when(io.start && io.startReady && configValid) {
      mode := io.mode
      branches := io.branches
      hidden := io.hidden
      branch := 0.U
      dimension := 0.U
      linear := 0.U
      active := true.B
    }
    when(io.out.fire) {
      when(io.out.bits.last) {
        active := false.B
        io.done := true.B
      }.elsewhen(lastDimension) {
        dimension := 0.U
        branch := branch + 1.U
        linear := linear + 1.U
      }.otherwise {
        dimension := dimension + 1.U
        linear := linear + 1.U
      }
    }
  }

  when(active) {
    assert(branch < branches)
    assert(dimension < hidden)
  }
}

object HeteroStateTxnOp {
  val width = 2
  val Begin = 0.U(width.W)
  val MarkDirty = 1.U(width.W)
  val Commit = 2.U(width.W)
  val Rollback = 3.U(width.W)
}

class HeteroStateTxnCommand(val txnBits: Int, val domainBits: Int) extends Bundle {
  val op = UInt(HeteroStateTxnOp.width.W)
  val txnId = UInt(txnBits.W)
  val domain = UInt(domainBits.W)
}
class HeteroStateTxnEvent(
    val txnBits: Int,
    val generationBits: Int,
    val domainCount: Int
) extends Bundle {
  val op = UInt(HeteroStateTxnOp.width.W)
  val txnId = UInt(txnBits.W)
  val generation = UInt(generationBits.W)
  val dirtyMask = UInt(domainCount.W)
}

/** Transaction shell shared by MTP and all recurrent/selection state domains. */
class HeteroStateTransaction(
    val domainCount: Int = 16,
    val txnBits: Int = 16,
    val generationBits: Int = 16
) extends Module {
  require(domainCount > 0 && domainCount <= 64)
  private val domainBits = math.max(1, log2Ceil(domainCount))
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val cmd = Flipped(Decoupled(new HeteroStateTxnCommand(txnBits, domainBits)))
    val event = Decoupled(new HeteroStateTxnEvent(txnBits, generationBits, domainCount))
    val active = Output(Bool())
    val activeTxn = Output(UInt(txnBits.W))
    val generation = Output(UInt(generationBits.W))
    val dirtyMask = Output(UInt(domainCount.W))
    val protocolError = Output(Bool())
  })

  val active = RegInit(false.B)
  val transaction = RegInit(0.U(txnBits.W))
  val generation = RegInit(0.U(generationBits.W))
  val dirty = RegInit(0.U(domainCount.W))
  val error = RegInit(false.B)
  val eventValid = RegInit(false.B)
  val event = Reg(new HeteroStateTxnEvent(txnBits, generationBits, domainCount))

  io.cmd.ready := !eventValid
  io.event.valid := eventValid
  io.event.bits := event
  io.active := active
  io.activeTxn := transaction
  io.generation := generation
  io.dirtyMask := dirty
  io.protocolError := error

  when(io.clear) {
    active := false.B
    transaction := 0.U
    generation := 0.U
    dirty := 0.U
    error := false.B
    eventValid := false.B
  }.otherwise {
    when(eventValid && io.event.ready) { eventValid := false.B }
    when(io.cmd.fire) {
      val transactionMatches = active && io.cmd.bits.txnId === transaction
      switch(io.cmd.bits.op) {
        is(HeteroStateTxnOp.Begin) {
          when(active) {
            error := true.B
          }.otherwise {
            active := true.B
            transaction := io.cmd.bits.txnId
            dirty := 0.U
            eventValid := true.B
            event.op := HeteroStateTxnOp.Begin
            event.txnId := io.cmd.bits.txnId
            event.generation := generation
            event.dirtyMask := 0.U
          }
        }
        is(HeteroStateTxnOp.MarkDirty) {
          when(!transactionMatches || io.cmd.bits.domain >= domainCount.U) {
            error := true.B
          }.otherwise {
            dirty := dirty | UIntToOH(io.cmd.bits.domain, domainCount)
          }
        }
        is(HeteroStateTxnOp.Commit) {
          when(!transactionMatches) {
            error := true.B
          }.otherwise {
            val nextGeneration = generation + 1.U
            eventValid := true.B
            event.op := HeteroStateTxnOp.Commit
            event.txnId := transaction
            event.generation := nextGeneration
            event.dirtyMask := dirty
            generation := nextGeneration
            active := false.B
            dirty := 0.U
          }
        }
        is(HeteroStateTxnOp.Rollback) {
          when(!transactionMatches) {
            error := true.B
          }.otherwise {
            val nextGeneration = generation + 1.U
            eventValid := true.B
            event.op := HeteroStateTxnOp.Rollback
            event.txnId := transaction
            event.generation := nextGeneration
            event.dirtyMask := dirty
            generation := nextGeneration
            active := false.B
            dirty := 0.U
          }
        }
      }
    }
  }
}

class HeteroMtpTokenPair(val tokenBits: Int, val stepBits: Int) extends Bundle {
  val draft = UInt(tokenBits.W)
  val target = UInt(tokenBits.W)
  val step = UInt(stepBits.W)
  val last = Bool()
}
class HeteroMtpVerifyResult(val stepBits: Int) extends Bundle {
  val acceptedCount = UInt(stepBits.W)
  val mismatchStep = UInt(stepBits.W)
  val allMatch = Bool()
  val rollback = Bool()
}

class HeteroMtpVerify(val maxSteps: Int = 32, val tokenBits: Int = 32) extends Module {
  require(maxSteps > 0)
  private val stepBits = log2Ceil(maxSteps + 1)
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val stepCount = Input(UInt(stepBits.W))
    val in = Flipped(Decoupled(new HeteroMtpTokenPair(tokenBits, stepBits)))
    val out = Decoupled(new HeteroMtpVerifyResult(stepBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
    val protocolError = Output(Bool())
  })

  val active = RegInit(false.B)
  val count = Reg(UInt(stepBits.W))
  val step = RegInit(0.U(stepBits.W))
  val accepted = RegInit(0.U(stepBits.W))
  val mismatchSeen = RegInit(false.B)
  val mismatchStep = RegInit(0.U(stepBits.W))
  val error = RegInit(false.B)
  val outValid = RegInit(false.B)
  val result = Reg(new HeteroMtpVerifyResult(stepBits))

  val configValid = io.stepCount =/= 0.U && io.stepCount <= maxSteps.U
  io.startReady := !active && !outValid
  io.invalidConfig := io.start && io.startReady && !configValid
  io.in.ready := active
  io.out.valid := outValid
  io.out.bits := result
  io.busy := active || outValid
  io.done := false.B
  io.protocolError := error

  when(io.clear) {
    active := false.B
    step := 0.U
    accepted := 0.U
    mismatchSeen := false.B
    mismatchStep := 0.U
    error := false.B
    outValid := false.B
  }.otherwise {
    when(outValid && io.out.ready) {
      outValid := false.B
      io.done := true.B
    }
    when(io.start && io.startReady && configValid) {
      active := true.B
      count := io.stepCount
      step := 0.U
      accepted := 0.U
      mismatchSeen := false.B
      mismatchStep := 0.U
      error := false.B
    }
    when(io.in.fire) {
      val expectedLast = step + 1.U >= count
      val matchNow = io.in.bits.draft === io.in.bits.target
      val firstMismatch = !mismatchSeen && !matchNow
      val acceptedNext = Mux(!mismatchSeen && matchNow, accepted + 1.U, accepted)
      val mismatchSeenNext = mismatchSeen || !matchNow
      val mismatchStepNext = Mux(firstMismatch, step, mismatchStep)
      when(io.in.bits.step =/= step || io.in.bits.last =/= expectedLast) { error := true.B }
      accepted := acceptedNext
      mismatchSeen := mismatchSeenNext
      mismatchStep := mismatchStepNext
      step := step + 1.U
      when(expectedLast) {
        active := false.B
        result.acceptedCount := acceptedNext
        result.mismatchStep := Mux(mismatchSeenNext, mismatchStepNext, count)
        result.allMatch := !mismatchSeenNext
        result.rollback := mismatchSeenNext
        outValid := true.B
      }
    }
  }
}
