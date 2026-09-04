package gemmini

import chisel3._
import chisel3.util._

class HeteroDivideResult(val width: Int) extends Bundle { val quotient = UInt(width.W); val remainder = UInt(width.W) }

/** One restoring-division bit per cycle; no inferred runtime divider or barrel shifter. */
class HeteroUnsignedDivide(val width: Int = 64) extends Module {
  require(width > 1)
  private val countBits = math.max(1, log2Ceil(width + 1))
  val io = IO(new Bundle {
    val clear = Input(Bool()); val start = Input(Bool()); val startReady = Output(Bool())
    val dividend = Input(UInt(width.W)); val divisor = Input(UInt(width.W))
    val out = Decoupled(new HeteroDivideResult(width)); val busy = Output(Bool()); val divideByZero = Output(Bool())
  })
  val active = RegInit(false.B); val dividend = Reg(UInt(width.W)); val divisor = Reg(UInt(width.W))
  val quotient = RegInit(0.U(width.W)); val remainder = RegInit(0.U((width + 1).W))
  val remaining = RegInit(0.U(countBits.W)); val outValid = RegInit(false.B)
  val outBits = Reg(new HeteroDivideResult(width)); val div0 = RegInit(false.B)
  io.startReady := !active && !outValid; io.busy := active || outValid; io.divideByZero := div0
  io.out.valid := outValid; io.out.bits := outBits
  when(io.clear) {
    active := false.B; dividend := 0.U; divisor := 0.U; quotient := 0.U; remainder := 0.U
    remaining := 0.U; outValid := false.B; div0 := false.B
  }.otherwise {
    when(outValid && io.out.ready) { outValid := false.B }
    when(io.start && io.startReady) {
      div0 := io.divisor === 0.U
      when(io.divisor === 0.U) {
        outBits.quotient := Fill(width, 1.U(1.W)); outBits.remainder := io.dividend; outValid := true.B
      }.otherwise {
        active := true.B; dividend := io.dividend; divisor := io.divisor
        quotient := 0.U; remainder := 0.U; remaining := width.U
      }
    }
    when(active) {
      val shiftedRemainder = Cat(remainder(width - 1, 0), dividend(width - 1))
      val subtract = shiftedRemainder >= divisor
      val nextRemainder = Mux(subtract, shiftedRemainder - divisor, shiftedRemainder)
      val nextQuotient = Cat(quotient(width - 2, 0), subtract)
      dividend := Cat(dividend(width - 2, 0), 0.U(1.W)); remainder := nextRemainder; quotient := nextQuotient
      when(remaining === 1.U) {
        active := false.B; remaining := 0.U; outBits.quotient := nextQuotient
        outBits.remainder := nextRemainder(width - 1, 0); outValid := true.B
      }.otherwise { remaining := remaining - 1.U }
    }
  }
  assert(!(active && outValid))
}

class HeteroTopKEntry(val indexBits: Int) extends Bundle { val valid = Bool(); val score = UInt(32.W); val index = UInt(indexBits.W) }

/** Deterministic sequential Top-K for MoE (K<=10), QSA (K<=512), and logits.
  * SyncReadMem plus one comparison/shift per cycle avoids a 512-way sort path.
  */
class HeteroStreamingTopK(val maxK: Int = 512, val indexBits: Int = 32, val itemCountBits: Int = 20) extends Module {
  require(maxK > 0)
  private val rankBits = math.max(1, log2Ceil(maxK + 1)); private val addrBits = math.max(1, log2Ceil(maxK))
  val io = IO(new Bundle {
    val clear = Input(Bool()); val start = Input(Bool()); val startReady = Output(Bool())
    val itemCount = Input(UInt(itemCountBits.W)); val k = Input(UInt(rankBits.W))
    val in = Flipped(Decoupled(new HeteroScoreIndex(32, indexBits)))
    val out = Decoupled(new HeteroRankedScore(32, indexBits, rankBits))
    val busy = Output(Bool()); val done = Output(Bool()); val invalidConfig = Output(Bool())
  })
  val sIdle :: sClear :: sInput :: sScanReq :: sScanResp :: sShiftReq :: sShiftResp :: sInsert :: sEmitReq :: sEmitResp :: Nil = Enum(10)
  val state = RegInit(sIdle); val table = SyncReadMem(maxK, new HeteroTopKEntry(indexBits))
  val readAddr = WireDefault(0.U(addrBits.W)); val readEnable = WireDefault(false.B); val readData = table.read(readAddr, readEnable)
  val itemCount = Reg(UInt(itemCountBits.W)); val k = Reg(UInt(rankBits.W)); val accepted = RegInit(0.U(itemCountBits.W))
  val clearIndex = RegInit(0.U(rankBits.W)); val scanIndex = RegInit(0.U(rankBits.W)); val insertIndex = RegInit(0.U(rankBits.W))
  val shiftIndex = RegInit(0.U(rankBits.W)); val emitRank = RegInit(0.U(rankBits.W)); val candidate = Reg(new HeteroScoreIndex(32,indexBits))
  val candidateLast = RegInit(false.B); val outputEntry = Reg(new HeteroTopKEntry(indexBits)); val outputValid = RegInit(false.B)
  val cfgValid = io.itemCount =/= 0.U && io.k =/= 0.U && io.k <= maxK.U && io.k <= io.itemCount
  io.startReady := state === sIdle; io.busy := state =/= sIdle; io.done := false.B
  io.invalidConfig := io.start && io.startReady && !cfgValid; io.in.ready := state === sInput
  io.out.valid := outputValid; io.out.bits.score := outputEntry.score; io.out.bits.index := outputEntry.index
  io.out.bits.rank := emitRank; io.out.bits.last := emitRank + 1.U >= k
  when(state === sScanReq) { readAddr := scanIndex(addrBits-1,0); readEnable := true.B }
    .elsewhen(state === sShiftReq) { readAddr := (shiftIndex - 1.U)(addrBits-1,0); readEnable := true.B }
    .elsewhen(state === sEmitReq) { readAddr := emitRank(addrBits-1,0); readEnable := true.B }
  def finishCandidate(): Unit = { when(candidateLast) { emitRank := 0.U; state := sEmitReq }.otherwise { state := sInput } }
  when(io.clear) { state := sIdle; outputValid := false.B; accepted := 0.U }
  .otherwise { switch(state) {
    is(sIdle) { outputValid := false.B; accepted := 0.U; when(io.start && cfgValid) { itemCount := io.itemCount; k := io.k; clearIndex := 0.U; state := sClear } }
    is(sClear) {
      val empty = Wire(new HeteroTopKEntry(indexBits)); empty.valid := false.B; empty.score := 0.U; empty.index := 0.U
      table.write(clearIndex(addrBits-1,0), empty)
      when(clearIndex + 1.U >= k) { state := sInput }.otherwise { clearIndex := clearIndex + 1.U }
    }
    is(sInput) { when(io.in.fire) { candidate := io.in.bits; candidateLast := accepted + 1.U >= itemCount; accepted := accepted + 1.U; scanIndex := 0.U; state := sScanReq } }
    is(sScanReq) { state := sScanResp }
    is(sScanResp) {
      val insert = !readData.valid || HeteroFp32Order.better(candidate.score,candidate.index,readData.score,readData.index)
      when(insert) { insertIndex := scanIndex; shiftIndex := k - 1.U; when(k - 1.U > scanIndex) { state := sShiftReq }.otherwise { state := sInsert } }
      .elsewhen(scanIndex + 1.U < k) { scanIndex := scanIndex + 1.U; state := sScanReq }.otherwise { finishCandidate() }
    }
    is(sShiftReq) { state := sShiftResp }
    is(sShiftResp) {
      table.write(shiftIndex(addrBits-1,0), readData)
      when(shiftIndex - 1.U > insertIndex) { shiftIndex := shiftIndex - 1.U; state := sShiftReq }.otherwise { state := sInsert }
    }
    is(sInsert) {
      val entry = Wire(new HeteroTopKEntry(indexBits)); entry.valid := true.B; entry.score := candidate.score; entry.index := candidate.index
      table.write(insertIndex(addrBits-1,0), entry); finishCandidate()
    }
    is(sEmitReq) { state := sEmitResp }
    is(sEmitResp) {
      when(!outputValid) { outputEntry := readData; outputValid := true.B }
      when(outputValid && io.out.ready) {
        outputValid := false.B; assert(outputEntry.valid)
        when(io.out.bits.last) { state := sIdle; io.done := true.B }.otherwise { emitRank := emitRank + 1.U; state := sEmitReq }
      }
    }
  }}
  when(outputValid) { assert(outputEntry.valid); assert(emitRank < k) }
}

class HeteroGatherRequest(val addrBits:Int,val tagBits:Int,val generationBits:Int) extends Bundle { val address=UInt(addrBits.W);val tag=UInt(tagBits.W);val generation=UInt(generationBits.W);val last=Bool() }
class HeteroGatherMemoryRequest(val addrBits:Int,val slotBits:Int) extends Bundle { val address=UInt(addrBits.W);val slot=UInt(slotBits.W) }
class HeteroGatherMemoryResponse(val dataBits:Int,val slotBits:Int) extends Bundle { val data=UInt(dataBits.W);val slot=UInt(slotBits.W) }
class HeteroGatherResponse(val dataBits:Int,val tagBits:Int,val generationBits:Int) extends Bundle { val data=UInt(dataBits.W);val tag=UInt(tagBits.W);val generation=UInt(generationBits.W);val last=Bool() }

/** OOO memory-response reorder primitive shared by PLE and QSA sparse gather. */
class HeteroTaggedGatherReorder(val maxOutstanding:Int=32,val addrBits:Int=64,val dataBits:Int=512,val tagBits:Int=32,val generationBits:Int=16) extends Module {
  require(maxOutstanding>=2 && isPow2(maxOutstanding)); private val slotBits=log2Ceil(maxOutstanding);private val countBits=log2Ceil(maxOutstanding+1)
  val io=IO(new Bundle{val clear=Input(Bool());val in=Flipped(Decoupled(new HeteroGatherRequest(addrBits,tagBits,generationBits)));val memReq=Decoupled(new HeteroGatherMemoryRequest(addrBits,slotBits));val memResp=Flipped(Decoupled(new HeteroGatherMemoryResponse(dataBits,slotBits)));val out=Decoupled(new HeteroGatherResponse(dataBits,tagBits,generationBits));val outstanding=Output(UInt(countBits.W));val protocolError=Output(Bool())})
  val valid=RegInit(VecInit(Seq.fill(maxOutstanding)(false.B)));val responseValid=RegInit(VecInit(Seq.fill(maxOutstanding)(false.B)))
  val tags=Reg(Vec(maxOutstanding,UInt(tagBits.W)));val generations=Reg(Vec(maxOutstanding,UInt(generationBits.W)));val lasts=Reg(Vec(maxOutstanding,Bool()));val data=Reg(Vec(maxOutstanding,UInt(dataBits.W)))
  val alloc=RegInit(0.U(slotBits.W));val retire=RegInit(0.U(slotBits.W));val count=RegInit(0.U(countBits.W));val error=RegInit(false.B)
  def next(p:UInt)=Mux(p===(maxOutstanding-1).U,0.U,p+1.U)
  val allocOk=count<maxOutstanding.U&&!valid(alloc);io.memReq.valid:=io.in.valid&&allocOk;io.memReq.bits.address:=io.in.bits.address;io.memReq.bits.slot:=alloc;io.in.ready:=io.memReq.ready&&allocOk
  val justAllocated=io.in.fire&&io.memResp.bits.slot===alloc
  val legal=(valid(io.memResp.bits.slot)||justAllocated)&&!responseValid(io.memResp.bits.slot)
  io.memResp.ready:=true.B;val respFire=io.memResp.fire&&legal
  io.out.valid:=count=/=0.U&&responseValid(retire);io.out.bits.data:=data(retire);io.out.bits.tag:=tags(retire);io.out.bits.generation:=generations(retire);io.out.bits.last:=lasts(retire)
  io.outstanding:=count;io.protocolError:=error
  when(io.clear){alloc:=0.U;retire:=0.U;count:=0.U;error:=false.B;for(i<-0 until maxOutstanding){valid(i):=false.B;responseValid(i):=false.B}}
  .otherwise{
    when(io.memResp.fire&&!legal){error:=true.B}
    when(io.in.fire){valid(alloc):=true.B;responseValid(alloc):=false.B;tags(alloc):=io.in.bits.tag;generations(alloc):=io.in.bits.generation;lasts(alloc):=io.in.bits.last;alloc:=next(alloc)}
    when(respFire){data(io.memResp.bits.slot):=io.memResp.bits.data;responseValid(io.memResp.bits.slot):=true.B}
    when(io.out.fire){valid(retire):=false.B;responseValid(retire):=false.B;retire:=next(retire)}
    switch(Cat(io.in.fire,io.out.fire)){is("b10".U){count:=count+1.U};is("b01".U){count:=count-1.U}}
  }
  assert(count<=maxOutstanding.U)
}

class HeteroMoeRoute(val expertBits:Int,val weightBits:Int) extends Bundle{val expert=UInt(expertBits.W);val weight=UInt(weightBits.W);val shared=Bool()}
class HeteroMoeDispatchEntry(val tokenBits:Int,val expertBits:Int,val weightBits:Int,val routeBits:Int) extends Bundle{val token=UInt(tokenBits.W);val expert=UInt(expertBits.W);val weight=UInt(weightBits.W);val routeTag=UInt(routeBits.W);val shared=Bool();val last=Bool()}
class HeteroMoeResult(val dataBits:Int,val routeBits:Int) extends Bundle{val routeTag=UInt(routeBits.W);val data=UInt(dataBits.W)}
class HeteroMoeMergeContribution(val dataBits:Int,val weightBits:Int,val routeBits:Int) extends Bundle{val routeTag=UInt(routeBits.W);val weight=UInt(weightBits.W);val data=UInt(dataBits.W);val first=Bool();val last=Bool()}

/** Route-order dispatch, arbitrary completion, deterministic weighted merge. */
class HeteroMoeRouteDispatch(val maxRoutes:Int=16,val tokenBits:Int=32,val expertBits:Int=10,val weightBits:Int=32,val dataBits:Int=512) extends Module{
  require(maxRoutes>=2&&isPow2(maxRoutes));private val routeBits=log2Ceil(maxRoutes);private val countBits=log2Ceil(maxRoutes+1)
  val io=IO(new Bundle{val clear=Input(Bool());val start=Input(Bool());val startReady=Output(Bool());val token=Input(UInt(tokenBits.W));val routeCount=Input(UInt(countBits.W));val routeIn=Flipped(Decoupled(new HeteroMoeRoute(expertBits,weightBits)));val dispatchOut=Decoupled(new HeteroMoeDispatchEntry(tokenBits,expertBits,weightBits,routeBits));val resultIn=Flipped(Decoupled(new HeteroMoeResult(dataBits,routeBits)));val mergeOut=Decoupled(new HeteroMoeMergeContribution(dataBits,weightBits,routeBits));val busy=Output(Bool());val done=Output(Bool());val invalidConfig=Output(Bool());val protocolError=Output(Bool())})
  val sIdle::sLoad::sDispatch::sWait::sMerge::Nil=Enum(5);val state=RegInit(sIdle);val token=Reg(UInt(tokenBits.W));val routes=Reg(UInt(countBits.W));val load=RegInit(0.U(countBits.W));val dispatch=RegInit(0.U(routeBits.W));val merge=RegInit(0.U(routeBits.W));val returned=RegInit(0.U(countBits.W))
  val experts=Reg(Vec(maxRoutes,UInt(expertBits.W)));val weights=Reg(Vec(maxRoutes,UInt(weightBits.W)));val shared=Reg(Vec(maxRoutes,Bool()));val issued=RegInit(VecInit(Seq.fill(maxRoutes)(false.B)));val resultValid=RegInit(VecInit(Seq.fill(maxRoutes)(false.B)));val resultData=Reg(Vec(maxRoutes,UInt(dataBits.W)));val error=RegInit(false.B)
  val cfg=io.routeCount=/=0.U&&io.routeCount<=maxRoutes.U;io.startReady:=state===sIdle;io.invalidConfig:=io.start&&io.startReady&&!cfg;io.busy:=state=/=sIdle;io.done:=false.B;io.protocolError:=error;io.routeIn.ready:=state===sLoad
  io.dispatchOut.valid:=state===sDispatch;io.dispatchOut.bits.token:=token;io.dispatchOut.bits.expert:=experts(dispatch);io.dispatchOut.bits.weight:=weights(dispatch);io.dispatchOut.bits.routeTag:=dispatch;io.dispatchOut.bits.shared:=shared(dispatch);io.dispatchOut.bits.last:=dispatch+1.U>=routes
  val justIssued=io.dispatchOut.fire&&io.resultIn.bits.routeTag===dispatch;val legal=io.resultIn.bits.routeTag<routes&&(issued(io.resultIn.bits.routeTag)||justIssued)&&!resultValid(io.resultIn.bits.routeTag);io.resultIn.ready:=state===sDispatch||state===sWait;val resp=io.resultIn.fire&&legal
  io.mergeOut.valid:=state===sMerge;io.mergeOut.bits.routeTag:=merge;io.mergeOut.bits.weight:=weights(merge);io.mergeOut.bits.data:=resultData(merge);io.mergeOut.bits.first:=merge===0.U;io.mergeOut.bits.last:=merge+1.U>=routes
  when(io.clear){state:=sIdle;error:=false.B;returned:=0.U;for(i<-0 until maxRoutes){issued(i):=false.B;resultValid(i):=false.B}}
  .otherwise{
    when(io.resultIn.fire&&!legal){error:=true.B};when(resp){resultData(io.resultIn.bits.routeTag):=io.resultIn.bits.data;resultValid(io.resultIn.bits.routeTag):=true.B;returned:=returned+1.U}
    switch(state){
      is(sIdle){when(io.start&&cfg){token:=io.token;routes:=io.routeCount;load:=0.U;dispatch:=0.U;merge:=0.U;returned:=0.U;error:=false.B;for(i<-0 until maxRoutes){issued(i):=false.B;resultValid(i):=false.B};state:=sLoad}}
      is(sLoad){when(io.routeIn.fire){experts(load):=io.routeIn.bits.expert;weights(load):=io.routeIn.bits.weight;shared(load):=io.routeIn.bits.shared;when(load+1.U>=routes){state:=sDispatch}.otherwise{load:=load+1.U}}}
      is(sDispatch){when(io.dispatchOut.fire){issued(dispatch):=true.B;when(io.dispatchOut.bits.last){state:=sWait}.otherwise{dispatch:=dispatch+1.U}}}
      is(sWait){when(returned+Mux(resp,1.U,0.U)>=routes){merge:=0.U;state:=sMerge}}
      is(sMerge){when(io.mergeOut.fire){assert(resultValid(merge));when(io.mergeOut.bits.last){state:=sIdle;io.done:=true.B}.otherwise{merge:=merge+1.U}}}
    }
  }
}

class HeteroTokenWithPosition(val tokenBits:Int,val positionBits:Int) extends Bundle{val token=UInt(tokenBits.W);val position=UInt(positionBits.W);val last=Bool()}
class HeteroHashedRow(val rowBits:Int,val headBits:Int,val positionBits:Int) extends Bundle{val row=UInt(rowBits.W);val head=UInt(headBits.W);val position=UInt(positionBits.W);val lastHead=Bool();val lastToken=Bool()}

/** Exact PLE n-gram wraparound-XOR hash.  Both 64-bit products and modulo
  * are iterative, preventing a runtime 64x64 multiplier or divider from
  * becoming an 800 MHz critical path.
  */
class HeteroPleNgramHash(
    val maxHeads: Int = 16,
    val maxNgram: Int = 3,
    val tokenBits: Int = 32,
    val rowBits: Int = 32,
    val positionBits: Int = 32
) extends Module {
  require(maxHeads > 0 && maxNgram >= 2 && tokenBits <= 64 && rowBits <= 64)
  private val headBits = math.max(1, log2Ceil(maxHeads))
  private val headCountBits = log2Ceil(maxHeads + 1)
  private val ngramBits = log2Ceil(maxNgram + 1)

  val io = IO(new Bundle {
    val clear = Input(Bool())
    val ngramSize = Input(UInt(ngramBits.W))
    val headsPerNgram = Input(UInt(headCountBits.W))
    val headCount = Input(UInt(headCountBits.W))
    val sentinel = Input(UInt(tokenBits.W))
    val multipliers = Input(Vec(maxNgram, UInt(64.W)))
    val headSizes = Input(Vec(maxHeads, UInt(rowBits.W)))
    val headOffsets = Input(Vec(maxHeads, UInt(rowBits.W)))
    val in = Flipped(Decoupled(new HeteroTokenWithPosition(tokenBits, positionBits)))
    val out = Decoupled(new HeteroHashedRow(rowBits, headBits, positionBits))
    val invalidConfig = Output(Bool())
    val protocolError = Output(Bool())
  })

  val history = RegInit(VecInit(Seq.fill(maxNgram - 1)(0.U(tokenBits.W))))
  val historyCount = RegInit(0.U(ngramBits.W))
  val previous = Reg(Vec(maxNgram - 1, UInt(64.W)))
  val factors = Reg(Vec(maxNgram, UInt(64.W)))
  val mixes = Reg(Vec(maxNgram - 1, UInt(64.W)))
  val sizes = Reg(Vec(maxHeads, UInt(rowBits.W)))
  val offsets = Reg(Vec(maxHeads, UInt(rowBits.W)))

  val sIdle :: sMultiplyStart :: sMultiplyWait :: sDivideStart :: sDivideWait :: sOutput :: Nil = Enum(6)
  val state = RegInit(sIdle)
  val token = Reg(UInt(64.W))
  val position = Reg(UInt(positionBits.W))
  val lastToken = Reg(Bool())
  val ngram = Reg(UInt(ngramBits.W))
  val headsPer = Reg(UInt(headCountBits.W))
  val headCount = Reg(UInt(headCountBits.W))
  val computeGroup = RegInit(0.U(ngramBits.W))
  val term = RegInit(0.U(ngramBits.W))
  val mixAccumulator = RegInit(0.U(64.W))
  val head = RegInit(0.U(headBits.W))
  val within = RegInit(0.U(headCountBits.W))
  val headGroup = RegInit(0.U(ngramBits.W))
  val error = RegInit(false.B)

  val multiply = Module(new HeteroUnsignedMultiply(64))
  val divide = Module(new HeteroUnsignedDivide(64))
  multiply.io.clear := io.clear
  divide.io.clear := io.clear

  val expectedHeadCount = (io.ngramSize - 1.U) * io.headsPerNgram
  val activeSizesNonzero = (0 until maxHeads).map { index =>
    index.U >= io.headCount || io.headSizes(index) =/= 0.U
  }.reduce(_ && _)
  val configValid = io.ngramSize >= 2.U && io.ngramSize <= maxNgram.U &&
    io.headsPerNgram =/= 0.U && io.headCount =/= 0.U &&
    io.headCount <= maxHeads.U && io.headCount === expectedHeadCount &&
    activeSizesNonzero

  val previousIndex = Mux(term === 0.U, 0.U, term - 1.U)
  val selectedTerm = Mux(term === 0.U, token, previous(previousIndex))
  multiply.io.start := state === sMultiplyStart && multiply.io.startReady
  multiply.io.left := selectedTerm
  multiply.io.right := factors(term)
  multiply.io.out.ready := state === sMultiplyWait

  val selectedSize = sizes(head)
  divide.io.start := state === sDivideStart && divide.io.startReady
  divide.io.dividend := mixes(headGroup)
  divide.io.divisor := selectedSize.pad(64)
  divide.io.out.ready := state === sOutput && io.out.ready

  io.in.ready := state === sIdle && configValid
  io.invalidConfig := io.in.valid && state === sIdle && !configValid
  io.protocolError := error
  io.out.valid := state === sOutput && divide.io.out.valid
  io.out.bits.row := (offsets(head).pad(64) + divide.io.out.bits.remainder)(rowBits - 1, 0)
  io.out.bits.head := head
  io.out.bits.position := position
  io.out.bits.lastHead := head + 1.U >= headCount
  io.out.bits.lastToken := lastToken

  when(io.clear) {
    state := sIdle
    historyCount := 0.U
    computeGroup := 0.U
    term := 0.U
    mixAccumulator := 0.U
    head := 0.U
    within := 0.U
    headGroup := 0.U
    error := false.B
  }.otherwise {
    when(divide.io.divideByZero) { error := true.B }
    switch(state) {
      is(sIdle) {
        when(io.in.fire) {
          token := io.in.bits.token.pad(64)
          position := io.in.bits.position
          lastToken := io.in.bits.last
          ngram := io.ngramSize
          headsPer := io.headsPerNgram
          headCount := io.headCount
          for (index <- 0 until maxNgram - 1) {
            previous(index) := Mux(
              historyCount > index.U,
              history(index).pad(64),
              io.sentinel.pad(64)
            )
          }
          for (index <- 0 until maxNgram) { factors(index) := io.multipliers(index) }
          for (index <- 0 until maxHeads) {
            sizes(index) := io.headSizes(index)
            offsets(index) := io.headOffsets(index)
          }
          for (index <- (1 until maxNgram - 1).reverse) {
            history(index) := history(index - 1)
          }
          history(0) := io.in.bits.token
          when(historyCount < (maxNgram - 1).U) { historyCount := historyCount + 1.U }
          computeGroup := 0.U
          term := 0.U
          mixAccumulator := 0.U
          error := false.B
          state := sMultiplyStart
        }
      }
      is(sMultiplyStart) {
        when(multiply.io.start && multiply.io.startReady) { state := sMultiplyWait }
      }
      is(sMultiplyWait) {
        when(multiply.io.out.fire) {
          val nextMix = mixAccumulator ^ multiply.io.out.bits.product(63, 0)
          val termsInGroup = computeGroup + 2.U
          val lastTerm = term + 1.U >= termsInGroup
          when(lastTerm) {
            mixes(computeGroup) := nextMix
            term := 0.U
            mixAccumulator := 0.U
            when(computeGroup + 2.U >= ngram) {
              head := 0.U
              within := 0.U
              headGroup := 0.U
              state := sDivideStart
            }.otherwise {
              computeGroup := computeGroup + 1.U
              state := sMultiplyStart
            }
          }.otherwise {
            term := term + 1.U
            mixAccumulator := nextMix
            state := sMultiplyStart
          }
        }
      }
      is(sDivideStart) {
        when(divide.io.start && divide.io.startReady) { state := sDivideWait }
      }
      is(sDivideWait) {
        when(divide.io.out.valid) { state := sOutput }
      }
      is(sOutput) {
        when(io.out.fire) {
          when(io.out.bits.lastHead) {
            state := sIdle
          }.otherwise {
            head := head + 1.U
            when(within + 1.U >= headsPer) {
              within := 0.U
              headGroup := headGroup + 1.U
            }.otherwise {
              within := within + 1.U
            }
            state := sDivideStart
          }
        }
      }
    }
  }

  when(state === sMultiplyStart || state === sMultiplyWait) {
    assert(computeGroup < ngram - 1.U)
    assert(term < computeGroup + 2.U)
    assert(term < maxNgram.U)
  }
  when(state =/= sIdle && state =/= sMultiplyStart && state =/= sMultiplyWait) {
    assert(head < headCount)
    assert(headGroup < ngram - 1.U)
    assert(selectedSize =/= 0.U)
  }
}

class HeteroSelectedToken(val tokenBits: Int, val rankBits: Int) extends Bundle {
  val token = UInt(tokenBits.W)
  val blockRank = UInt(rankBits.W)
  val fromTail = Bool()
  val last = Bool()
}

/** Stable block Top-K expansion plus an incomplete causal tail. Runtime block
  * address products are produced by a bit-serial multiplier, not a wide
  * combinational multiply on the selected-token output path.
  */
class HeteroQsaBlockSelector(
    val maxBlockTopK: Int = 512,
    val blockCountBits: Int = 20,
    val tokenBits: Int = 32,
    val ratioBits: Int = 5
) extends Module {
  require(maxBlockTopK > 0 && tokenBits >= blockCountBits + ratioBits)
  private val rankBits = log2Ceil(maxBlockTopK + 1)
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val completeBlocks = Input(UInt(blockCountBits.W))
    val blockTopK = Input(UInt(rankBits.W))
    val compressRatio = Input(UInt(ratioBits.W))
    val tailCount = Input(UInt(ratioBits.W))
    val scoreIn = Flipped(Decoupled(new HeteroScoreIndex(32, blockCountBits)))
    val selectedOut = Decoupled(new HeteroSelectedToken(tokenBits, rankBits))
    val busy = Output(Bool())
    val done = Output(Bool())
    val invalidConfig = Output(Bool())
  })

  val topK = Module(new HeteroStreamingTopK(maxBlockTopK, blockCountBits, blockCountBits))
  val multiply = Module(new HeteroUnsignedMultiply(tokenBits))
  topK.io.clear := io.clear
  multiply.io.clear := io.clear

  val sIdle :: sTailBaseStart :: sTailBaseWait :: sTopStart :: sCollect ::
    sBlockBaseStart :: sBlockBaseWait :: sExpand :: sTail :: Nil = Enum(9)
  val state = RegInit(sIdle)
  val blocks = Reg(UInt(blockCountBits.W))
  val ratio = Reg(UInt(ratioBits.W))
  val tail = Reg(UInt(ratioBits.W))
  val selectedCount = Reg(UInt(rankBits.W))
  val block = Reg(UInt(blockCountBits.W))
  val rank = Reg(UInt(rankBits.W))
  val blockLast = Reg(Bool())
  val blockBase = Reg(UInt(tokenBits.W))
  val tailBase = Reg(UInt(tokenBits.W))
  val offset = RegInit(0.U(ratioBits.W))
  val tailOffset = RegInit(0.U(ratioBits.W))

  val selectedWide = Mux(io.completeBlocks < io.blockTopK, io.completeBlocks, io.blockTopK)
  val selected = selectedWide(rankBits - 1, 0)
  val configValid = io.compressRatio =/= 0.U &&
    io.tailCount < io.compressRatio &&
    ((io.completeBlocks === 0.U) ||
      (selected =/= 0.U && selected <= maxBlockTopK.U))

  topK.io.start := state === sTopStart && topK.io.startReady
  topK.io.itemCount := blocks
  topK.io.k := selectedCount
  topK.io.in.valid := io.scoreIn.valid && state === sCollect
  topK.io.in.bits := io.scoreIn.bits
  io.scoreIn.ready := topK.io.in.ready && state === sCollect
  topK.io.out.ready := state === sCollect

  val multiplyTailBase = state === sTailBaseStart
  val multiplyBlockBase = state === sBlockBaseStart
  multiply.io.start := (multiplyTailBase || multiplyBlockBase) && multiply.io.startReady
  multiply.io.left := Mux(multiplyTailBase, blocks.pad(tokenBits), block.pad(tokenBits))
  multiply.io.right := ratio.pad(tokenBits)
  multiply.io.out.ready := state === sTailBaseWait || state === sBlockBaseWait

  io.startReady := state === sIdle && multiply.io.startReady && topK.io.startReady
  io.invalidConfig := io.start && io.startReady && !configValid
  io.busy := state =/= sIdle
  io.done := false.B
  io.selectedOut.valid := state === sExpand || state === sTail
  io.selectedOut.bits.token := Mux(state === sExpand, blockBase + offset, tailBase + tailOffset)
  io.selectedOut.bits.blockRank := Mux(state === sExpand, rank, selectedCount)
  io.selectedOut.bits.fromTail := state === sTail
  io.selectedOut.bits.last := Mux(
    state === sExpand,
    blockLast && offset + 1.U >= ratio && tail === 0.U,
    tailOffset + 1.U >= tail
  )

  when(io.clear) {
    state := sIdle
    offset := 0.U
    tailOffset := 0.U
  }.otherwise {
    switch(state) {
      is(sIdle) {
        when(io.start && io.startReady && configValid) {
          blocks := io.completeBlocks
          ratio := io.compressRatio
          tail := io.tailCount
          selectedCount := selected
          offset := 0.U
          tailOffset := 0.U
          tailBase := 0.U
          when(io.completeBlocks === 0.U) {
            when(io.tailCount === 0.U) {
              io.done := true.B
            }.otherwise {
              state := sTail
            }
          }.otherwise {
            state := sTailBaseStart
          }
        }
      }
      is(sTailBaseStart) {
        when(multiply.io.start && multiply.io.startReady) { state := sTailBaseWait }
      }
      is(sTailBaseWait) {
        when(multiply.io.out.fire) {
          tailBase := multiply.io.out.bits.product(tokenBits - 1, 0)
          state := sTopStart
        }
      }
      is(sTopStart) {
        when(topK.io.start && topK.io.startReady) { state := sCollect }
      }
      is(sCollect) {
        when(topK.io.out.fire) {
          block := topK.io.out.bits.index
          rank := topK.io.out.bits.rank
          blockLast := topK.io.out.bits.last
          state := sBlockBaseStart
        }
      }
      is(sBlockBaseStart) {
        when(multiply.io.start && multiply.io.startReady) { state := sBlockBaseWait }
      }
      is(sBlockBaseWait) {
        when(multiply.io.out.fire) {
          blockBase := multiply.io.out.bits.product(tokenBits - 1, 0)
          offset := 0.U
          state := sExpand
        }
      }
      is(sExpand) {
        when(io.selectedOut.fire) {
          when(offset + 1.U >= ratio) {
            offset := 0.U
            when(blockLast) {
              when(tail === 0.U) {
                state := sIdle
                io.done := true.B
              }.otherwise {
                tailOffset := 0.U
                state := sTail
              }
            }.otherwise {
              state := sCollect
            }
          }.otherwise {
            offset := offset + 1.U
          }
        }
      }
      is(sTail) {
        when(io.selectedOut.fire) {
          when(tailOffset + 1.U >= tail) {
            state := sIdle
            io.done := true.B
          }.otherwise {
            tailOffset := tailOffset + 1.U
          }
        }
      }
    }
  }

  when(state === sExpand) {
    assert(offset < ratio)
    assert(rank < selectedCount)
  }
  when(state === sTail) { assert(tail =/= 0.U && tailOffset < tail) }
}

class HeteroMultiplyResult(val width: Int) extends Bundle {
  val product = UInt((2 * width).W)
}

/** One shift/add bit per cycle.  Used in address-generation paths where a
  * runtime 32x32 multiplier would otherwise become an avoidable timing risk.
  */
class HeteroUnsignedMultiply(val width: Int = 32) extends Module {
  require(width > 1)
  private val countBits = math.max(1, log2Ceil(width + 1))
  val io = IO(new Bundle {
    val clear = Input(Bool())
    val start = Input(Bool())
    val startReady = Output(Bool())
    val left = Input(UInt(width.W))
    val right = Input(UInt(width.W))
    val out = Decoupled(new HeteroMultiplyResult(width))
    val busy = Output(Bool())
  })

  val active = RegInit(false.B)
  val multiplicand = RegInit(0.U((2 * width).W))
  val multiplier = RegInit(0.U(width.W))
  val accumulator = RegInit(0.U((2 * width).W))
  val remaining = RegInit(0.U(countBits.W))
  val outValid = RegInit(false.B)
  val result = Reg(new HeteroMultiplyResult(width))

  io.startReady := !active && !outValid
  io.busy := active || outValid
  io.out.valid := outValid
  io.out.bits := result

  when(io.clear) {
    active := false.B
    multiplicand := 0.U
    multiplier := 0.U
    accumulator := 0.U
    remaining := 0.U
    outValid := false.B
  }.otherwise {
    when(outValid && io.out.ready) { outValid := false.B }
    when(io.start && io.startReady) {
      active := true.B
      multiplicand := io.left.pad(2 * width)
      multiplier := io.right
      accumulator := 0.U
      remaining := width.U
    }
    when(active) {
      val nextAccumulator = Mux(multiplier(0), accumulator + multiplicand, accumulator)
      accumulator := nextAccumulator
      multiplicand := (multiplicand << 1)(2 * width - 1, 0)
      multiplier := multiplier >> 1
      when(remaining === 1.U) {
        active := false.B
        remaining := 0.U
        result.product := nextAccumulator
        outValid := true.B
      }.otherwise {
        remaining := remaining - 1.U
      }
    }
  }
}
