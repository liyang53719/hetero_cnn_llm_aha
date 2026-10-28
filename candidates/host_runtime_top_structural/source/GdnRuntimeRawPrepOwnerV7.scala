// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private runtime V7 successor of the historical max32 input-preparation
  * numerical recipe. The new job/result/prepare ABI is explicit: historical
  * compiled owners are neither silently replaced nor granted new authority.
  * Shared ScalarV2 and raw BF16 formatter remain externally owned resources.
  */
/** No arithmetic service is instantiated here: every operation is sent to the
  * one external shared ScalarPolicyV2 service. Softplus is shared opcode 7; the
  * owner intentionally fails closed if the service does not implement it.
  *
  * Q/K: BF16 expand, separate FP32 squares and ascending sum, +1e-6, sqrt,
  * reciprocal, multiply. Q then multiplies FP32(128^-0.5); this owner
  * uses the existing FP32 chunk scale; no recurrent decode path is implemented. This fixed hardware recipe
  * is separately checked against official torch rsqrt/reduction semantics.
  * V only widens. Beta uses sigmoid followed by BF16 RNE THEN FP32 expansion.
  * g = -exp(original FP32 A_log) * softplus(FP32(a) + FP32(BF16 dt_bias)).
  * exp(A_log) uses the shared exp(-abs(x)) and reciprocal for positive x.
  * The accepted exp domain is |A_log|<80, b>-80, and finite g<=0; LegacyOpen80 additionally requires -80<g. No domain
  * saturation or quantization of the raw recurrent state is hidden here.
  *
  * Tags, memory and scalar requests and completion are stable under stalls.
  * Output publication waits for the last gate ACK. Any failure locks until
  * reset; reset must also reset/drain the shared service and transport.
  */
/** Control-only successor: same numerical node order and finite domains.
  * Pre-read immutable A_log once under actual Guard-owned DDR, then expose
  * exact data-dependent request counts before any shared arithmetic request.
  * The parent must authenticate prepare.fire against its retained Guard job
  * and acquire the existing ordinary slots; this event itself is no grant.
  */
class GdnRuntimeRawPrepOwnerV7 extends Module {
  val io = IO(new GdnRuntimeRawPrepPortV7)
  val idle :: readALog :: waitALog :: prepared :: readParam :: waitParam :: readVector :: waitVector :: issue :: waitScalar :: writeVector :: waitWrite :: writeGate :: waitGate :: formatIssue :: formatWait :: finish :: report :: locked :: Nil = Enum(19)
  val square :: sum :: epsilon :: root :: inverse :: normalize :: scaleQuery :: biasAdd :: softplus :: aExp :: aInverse :: logDecay :: betaExp :: betaDenominator :: betaInverse :: betaSign :: torchTermAdd :: torchGroupAdd :: torchLaneAdd :: Nil = Enum(19)
  val state = RegInit(idle)
  val operation = RegInit(square)
  val job = Reg(new GdnRuntimeRawPrepJobV7)
  val parameters = Reg(Vec(3, Vec(16, UInt(32.W)))) // A, B, dtBias
  val aLogCache=Reg(Vec(32,UInt(32.W))) // fixed common capacity, replaces old16word A_log slot
  val aLogBeat=RegInit(0.U(1.W));val aLogReads=RegInit(0.U(2.W))
  val nonnegativeALog=RegInit(0.U(6.W))
  val scalarAccepted=RegInit(0.U(32.W));val scalarReturned=RegInit(0.U(32.W))
  val formatAccepted=RegInit(0.U(32.W));val formatReturned=RegInit(0.U(32.W))
  val betaRaw=Reg(UInt(32.W))
  val input = Reg(Vec(128, UInt(16.W)))
  val output = Reg(Vec(128, UInt(32.W)))
  val param = RegInit(0.U(2.W)) // active values1 dtBias,2 A(and B16),3 B32
  val role = RegInit(0.U(2.W)) // Q, K, V
  val head = RegInit(0.U(5.W))
  val token = RegInit(0.U(7.W))
  val beat = RegInit(0.U(3.W))
  val lane = RegInit(0.U(7.W))
  val sequence = RegInit(0.U(32.W))
  val accumulator = RegInit(0.U(32.W))
  val temporary = Reg(UInt(32.W))
  val inverseNorm = Reg(UInt(32.W))
  val positive = Reg(UInt(32.W))
  val exponential = Reg(UInt(32.W))
  val g = Reg(UInt(32.W))
  val beta = Reg(UInt(32.W))
  val status = RegInit(Status.Ok.U(8.W))
  val bytes = RegInit(0.U(64.W))
  val cycles = RegInit(0.U(64.W))
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val terminal=Reg(new GdnRuntimeRawPrepResultV7)
  val expectedScalar=(job.tokens.pad(64)*(job.layout.valueHeads.pad(64)*
    Mux(job.reductionPolicy===GdnRuntimeRawPrepPolicyV7.TorchCpuDefault128.U,908.U,910.U)+nonnegativeALog.pad(64)))(31,0)
  val expectedFormat=(job.tokens.pad(32)*job.layout.valueHeads.pad(32))(31,0)
  val expectedBytes=(job.tokens.pad(80)*job.layout.rowBytes.pad(80))
  val memoryOffer=state===readALog || state===readParam || state===readVector || state===writeVector || state===writeGate
  val memoryDebt=state===waitALog || state===waitParam || state===waitVector || state===waitWrite || state===waitGate
  val expectedTag=Cat(job.tag,sequence)
  val unknownMemory=io.response.valid && (!memoryDebt || io.response.bits.tag=/=expectedTag)
  // requestPolicy below depends only on retained job/operation, stable in waitScalar.
  val expectedPolicy=Wire(UInt(2.W))
  val unknownScalar=io.scalar.result.valid && (state=/=waitScalar || io.scalar.result.bits.policy=/=expectedPolicy)
  val unknownFormat=io.formatResult.valid && state=/=formatWait
  val unknown=unknownMemory || unknownScalar || unknownFormat
  val currentFault=io.parentFault || unknown
  when(unknown){quarantine:=true.B}
  when(currentFault){poison:=true.B;when(state=/=report && status===Status.Ok.U){status:=Status.Protocol.U}}
  val quiet= !io.response.valid && !io.scalar.result.valid && !io.formatResult.valid
  val noService= !memoryOffer && !memoryDebt && state=/=issue && state=/=waitScalar &&
    state=/=formatIssue && state=/=formatWait && state=/=prepared
  io.resourcesDrained:=noService && quiet && !quarantine && !unknown
  io.resetRequired:=poison || quarantine || currentFault
  io.job.ready:=state===idle && !poison && !currentFault && quiet
  io.done.valid:=state===report;io.done.bits:=terminal
  // This held metadata event is never cancelled by a late fault. The parent
  // may consume it while rejecting fresh arithmetic authority using CURRENT
  // independent fault; existing Guard/memory ownership still must be retained.
  io.prepare.valid:=state===prepared
  io.prepare.bits.accepted:=job;io.prepare.bits.scalarOperations:=expectedScalar
  io.prepare.bits.formatOperations:=expectedFormat
  io.prepare.bits.nonnegativeALog:=nonnegativeALog;io.prepare.bits.acknowledgedALogReads:=aLogReads

  val grouped = job.layout.valueHeads === 32.U
  val sourceHead = Mux(role === 2.U, head, Mux(grouped, head >> 1, head))
  val rawRowBytes = (job.layout.valueHeads +& 32.U(6.W)) << 8
  val rawRoleOffset = MuxLookup(role, 0.U(15.W))(Seq(1.U -> 4096.U, 2.U -> 8192.U))
  val rawAddress = job.conv.pad(66) + (token * rawRowBytes).pad(66) +
    rawRoleOffset.pad(66) + (sourceHead.pad(66) << 8) + (beat.pad(66) << 6)
  val preparedRow = job.output.pad(66) + (token * job.layout.rowBytes).pad(66)
  val preparedVector = preparedRow + ((role * job.layout.valueHeads).pad(66) << 9) +
    (head.pad(66) << 9) + (beat.pad(66) << 6)
  val preparedGate = preparedRow + ((job.layout.valueHeads * 1536.U).pad(66)) + (head.pad(66) << 6)
  val parameterHalf = grouped && head(4)
  val parameterHead = head(3,0)
  val abRow = job.ab.pad(66) + ((token * job.layout.valueHeads).pad(66) << 2)
  val parameterAddress = MuxLookup(param, job.aLog.pad(66) + (head(4,4).pad(66) << 6))(Seq(
    1.U -> job.dtBias.pad(66), 2.U -> abRow, 3.U -> (abRow + (job.layout.valueHeads.pad(66) << 1))))
  val memoryHeld=HeldDecoupledOffer(memoryOffer,io.memory.ready,poison || currentFault || quarantine)
  io.memory.valid:=memoryHeld.valid
  io.memory.bits.write := state === writeVector || state === writeGate
  io.memory.bits.address := MuxLookup(state, rawAddress)(Seq(
    readALog -> (job.aLog.pad(66)+(aLogBeat.pad(66)<<6)), readParam -> parameterAddress, writeVector -> preparedVector, writeGate -> preparedGate))(63,0)
  val outputBeats = output.asUInt.asTypeOf(Vec(8, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeGate, Cat(0.U(448.W), beta, g), Mux(state === writeVector, outputBeats(beat), 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := expectedTag
  io.response.ready:=memoryDebt && !quarantine && !unknownMemory

  val torchReduction = job.reductionPolicy === GdnRuntimeRawPrepPolicyV7.TorchCpuDefault128.U
  val reductionAddress = Mux(torchReduction && (operation === square || operation === torchTermAdd),
    Cat(lane(1,0),lane(3,2),lane(6,4)),lane)
  val x = Cat(input(reductionAddress), 0.U(16.W))
  val a = parameters(0)(parameterHead)
  val b = parameters(1)(parameterHead)
  val aLog = aLogCache(head)
  val bias = parameters(2)(parameterHead)
  // Distinct candidate: explicitly binds the exact finite ScalarV2 recipe.
  // Gate2 admission is NOT inherited by the old frozen prefix owner. This
  // mapping does not upgrade41 finite Scalar samples to an all-domain proof.
  val dualGate = job.gatePolicy === GdnRuntimeRawPrepPolicyV7.DualInnerCandidate.U
  val requestPolicy = Mux(dualGate && operation === softplus, UnifiedScalarPolicyV2.DualInnerSoftplus.U,
    Mux(dualGate && operation === aExp, UnifiedScalarPolicyV2.GradualDecay.U, UnifiedScalarPolicyV2.Legacy.U))
  expectedPolicy:=requestPolicy
  io.scalar.request.bits.policy := requestPolicy
  val scalarHeld=HeldDecoupledOffer(state===issue,io.scalar.request.ready,poison || currentFault || quarantine)
  io.scalar.request.valid:=scalarHeld.valid
  io.scalar.request.bits.payload.op := MuxLookup(operation, ScalarOp.MulIeeeRne.U)(Seq(
    sum -> ScalarOp.Add.U, torchTermAdd -> ScalarOp.Add.U, torchGroupAdd -> ScalarOp.Add.U, torchLaneAdd -> ScalarOp.Add.U, epsilon -> ScalarOp.Add.U, root -> ScalarOp.Sqrt.U,
    inverse -> ScalarOp.Div.U, scaleQuery -> ScalarOp.MulIeeeRne.U,
    biasAdd -> ScalarOp.Add.U, softplus -> ScalarOp.Softplus.U, aExp -> ScalarOp.ExpNegative.U,
    aInverse -> ScalarOp.Div.U, betaExp -> ScalarOp.ExpNegative.U,
    betaDenominator -> ScalarOp.Add.U, betaInverse -> ScalarOp.Div.U))
  io.scalar.request.bits.payload.a := MuxLookup(operation, temporary)(Seq(
    square -> x, sum -> accumulator, torchTermAdd -> positive, torchGroupAdd -> inverseNorm, torchLaneAdd -> accumulator, inverse -> F32.lit(1), normalize -> x,
    biasAdd -> a, aExp -> Mux(dualGate, Cat(1.U(1.W), aLog(30,0)), aLog), aInverse -> F32.lit(1),
    logDecay -> F32.neg(temporary), betaExp -> b, betaDenominator -> F32.lit(1), betaInverse -> F32.lit(1)))
  io.scalar.request.bits.payload.b := MuxLookup(operation, temporary)(Seq(
    square -> x, epsilon -> F32.lit(1e-6), root -> 0.U, normalize -> inverseNorm,
    scaleQuery -> F32.lit(1 / math.sqrt(128)),
    biasAdd -> bias, softplus -> 0.U, aExp -> 0.U, logDecay -> positive,
    betaExp -> 0.U, betaDenominator -> exponential, betaSign -> Mux(b(31), exponential, F32.lit(1))))
  io.scalar.result.ready:=state===waitScalar && !quarantine && !unknownScalar
  val formatHeld=HeldDecoupledOffer(state===formatIssue,io.formatRequest.ready,poison || currentFault || quarantine)
  io.formatRequest.valid:=formatHeld.valid;io.formatRequest.bits.value:=betaRaw
  io.formatResult.ready:=state===formatWait && !quarantine && !unknownFormat
  when((poison || currentFault) && !quarantine){
    when(memoryOffer && !memoryHeld.held && !io.memory.fire){state:=finish}
    when(state===issue && !scalarHeld.held && !io.scalar.request.fire){state:=finish}
    when(state===formatIssue && !formatHeld.held && !io.formatRequest.fire){state:=finish}
  }
  when(state =/= idle && state =/= report && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { when(status===Status.Ok.U){status:=code};poison:=true.B;state:=finish }

  when(io.job.fire) {
    job := io.job.bits; token := 0.U; param := 1.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U
    aLogBeat:=0.U;aLogReads:=0.U;nonnegativeALog:=0.U
    scalarAccepted:=0.U;scalarReturned:=0.U;formatAccepted:=0.U;formatReturned:=0.U
    sequence := 0.U; accumulator := 0.U; status := Status.Ok.U; bytes := 0.U; cycles := 0.U
    val j = io.job.bits
    val rawBytes = (j.tokens * ((j.layout.valueHeads +& 32.U(6.W)) << 8)).pad(66)
    val abBytes = ((j.tokens * j.layout.valueHeads).pad(66) << 2)
    val outputBytes = (j.tokens * j.layout.rowBytes).pad(66)
    val spans = Seq((j.conv,rawBytes),(j.ab,abBytes),
      (j.aLog,(j.layout.valueHeads.pad(66) << 2)),(j.dtBias,64.U(66.W)),(j.output,outputBytes))
    def overlap(a:(UInt,UInt),b:(UInt,UInt)):Bool =
      a._1.pad(66) < b._1.pad(66)+b._2 && b._1.pad(66) < a._1.pad(66)+a._2
    val badAddress = spans.map { case (base,size) =>
      base(5,0) =/= 0.U || size===0.U || base.pad(66)+size > (BigInt(1)<<56).U }.reduce(_||_)
    val badOverlap = (for(i<-spans.indices;k<-0 until i)yield overlap(spans(i),spans(k))).reduce(_||_)
    when(j.tokens===0.U || j.tokens>128.U || !GdnRuntimeRawPrepLayoutV7.admitted(j.layout) || badAddress || badOverlap) { fail(Status.Bounds.U) }
      .elsewhen(j.reductionPolicy>GdnRuntimeRawPrepPolicyV7.TorchCpuDefault128.U || j.gatePolicy>GdnRuntimeRawPrepPolicyV7.DualInnerCandidate.U) { fail(Status.Unsupported.U) }
      .elsewhen(io.response.valid || io.scalar.result.valid) { fail(Status.Protocol.U) }
      .otherwise { state := readALog }
  }
  when(io.prepare.fire){
    when(poison || currentFault){state:=finish}.otherwise{param:=1.U;state:=readParam}
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitVector)(Seq(readALog -> waitALog, readParam -> waitParam, writeVector -> waitWrite, writeGate -> waitGate))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(sequence=/="hffffffff".U){sequence:=sequence+1.U}
    when((state===waitWrite || state===waitGate) && !r.error){bytes:=bytes+64.U}
    when(sequence==="hffffffff".U){fail(Status.Protocol.U)}
      .elsewhen(r.error){fail(Status.Memory.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise {
        when(state===waitALog){
          val words=r.data.asTypeOf(Vec(16,UInt(32.W)))
          val validWords=words.map(x=>TensorMath.finite(x) && x(30,0)<F32.lit(80)).reduce(_&&_)
          when(!validWords){fail(Status.Numerical.U)}.otherwise{
            for(i<-0 until 16){aLogCache(Cat(aLogBeat,i.U(4.W))):=words(i)}
            // EXACT original aExp branch: +0 counts, -0 does not; no abs/sign
            // reinterpretation and NaN/Inf already excluded above.
            nonnegativeALog:=nonnegativeALog+PopCount(words.map(x=> !x(31)))
            aLogReads:=aLogReads+1.U
            when(job.layout.valueHeads===16.U || aLogBeat===1.U){state:=prepared}
              .otherwise{aLogBeat:=1.U;state:=readALog}
          }
        }
        when(state === waitParam) {
          for(i<-0 until 16) {
            val low = r.data((i+1)*16-1,i*16)
            val high = r.data((i+17)*16-1,(i+16)*16)
            val half = Mux(parameterHalf,high,low)
            when(param===1.U) { parameters(2)(i):=Cat(half,0.U(16.W)) }
              .elsewhen(param===2.U) {
                parameters(0)(i):=Cat(half,0.U(16.W))
                when(!grouped) { parameters(1)(i):=Cat(high,0.U(16.W)) }
              }.otherwise { parameters(1)(i):=Cat(half,0.U(16.W)) }
          }
          when(param===3.U || (param===2.U && !grouped)) { beat:=0.U;state:=readVector }
            .otherwise { param:=param+1.U;state:=readParam }
        }
        when(state === waitVector) {
          val invalid = Wire(Vec(32, Bool()))
          for (i <- 0 until 32) {
            val v = r.data((i + 1) * 16 - 1, i * 16)
            input(Cat(beat(1, 0), i.U(5.W))) := v
            when(role === 2.U) { output(Cat(beat(1, 0), i.U(5.W))) := Cat(v, 0.U(16.W)) }
            invalid(i) := v(14, 7) === 255.U
          }
          when(invalid.asUInt.orR) { fail(Status.Numerical.U) }
            .elsewhen(beat === 3.U) {
              beat := 0.U; lane := 0.U; accumulator := 0.U; operation := square
              state := Mux(role === 2.U, writeVector, issue)
            }.otherwise { beat := beat + 1.U; state := readVector }
        }
        when(state === waitWrite) {
          when(beat === 7.U) {
            beat := 0.U
            when(role === 2.U) {
              when(!TensorMath.finite(aLog) || aLog(30, 0) >= F32.lit(80) ||
                !TensorMath.finite(b) || (b(31) && b(30, 0) >= F32.lit(80))) { fail(Status.Numerical.U) }
                .otherwise { operation := biasAdd; state := issue }
            }.otherwise { role := role + 1.U; state := readVector }
          }.otherwise { beat := beat + 1.U; state := writeVector }
        }
        when(state === waitGate) {
          when(head +& 1.U === job.layout.valueHeads) {
            when(token +& 1.U === job.tokens) { state:=finish }
              .otherwise {token:=token+1.U;head:=0.U;role:=0.U;beat:=0.U;param:=1.U;state:=readParam}
          }.otherwise {
            head:=head+1.U;role:=0.U;beat:=0.U
            when(head===15.U) {param:=1.U;state:=readParam}.otherwise{state:=readVector}
          }
        }
      }
  }
  when(io.scalar.request.fire) { scalarAccepted:=scalarAccepted+1.U;state := waitScalar }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits.value
    scalarReturned:=scalarReturned+1.U
    when(io.scalar.result.bits.error || !TensorMath.finite(r)){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise {
        temporary := r; state := issue
        switch(operation) {
          is(square) {
            when(torchReduction) {
              when(lane(1,0)===0.U) {positive:=r;lane:=lane+1.U;operation:=square}
                .otherwise {operation:=torchTermAdd}
            }.otherwise {operation:=sum}
          }
          is(torchTermAdd) {
            positive:=r
            when(lane(1,0)===3.U) {
              when(lane(3,2)===0.U) {inverseNorm:=r;lane:=lane+1.U;operation:=square}
                .otherwise {operation:=torchGroupAdd}
            }.otherwise {lane:=lane+1.U;operation:=square}
          }
          is(torchGroupAdd) {
            inverseNorm:=r
            when(lane(3,2)===3.U) {
              when(lane(6,4)===0.U) {accumulator:=r;lane:=lane+1.U;operation:=square}
                .otherwise {operation:=torchLaneAdd}
            }.otherwise {lane:=lane+1.U;operation:=square}
          }
          is(torchLaneAdd) {
            accumulator:=r
            when(lane===127.U) {lane:=0.U;operation:=epsilon}
              .otherwise {lane:=lane+1.U;operation:=square}
          }
          is(sum) {
            accumulator := r
            when(lane === 127.U) { lane := 0.U; operation := epsilon }
              .otherwise { lane := lane + 1.U; operation := square }
          }
          is(epsilon) { operation := root }
          is(root) { operation := inverse }
          is(inverse) { inverseNorm := r; operation := normalize }
          is(normalize) {
            when(role === 0.U) { operation := scaleQuery }
              .otherwise {
                output(lane) := r
                when(lane === 127.U) { beat := 0.U; state := writeVector }
                  .otherwise { lane := lane + 1.U; operation := normalize }
              }
          }
          is(scaleQuery) {
            output(lane) := r
            when(lane === 127.U) { beat := 0.U; state := writeVector }
              .otherwise { lane := lane + 1.U; operation := normalize }
          }
          is(biasAdd) {
            // Never clip unsupported biased values or silently use legacySP.
            // Nonfinite r was already rejected above for every operation.
            when(dualGate && r(31) && r(30,0)>=F32.lit(80)) { fail(Status.Numerical.U) }
              .otherwise { operation := softplus }
          }
          is(softplus) {
            when(r(31)) { fail(Status.Numerical.U) }
              .otherwise { positive := r; operation := aExp }
          }
          is(aExp) { operation := Mux(aLog(31), logDecay, aInverse) }
          is(aInverse) { operation := logDecay }
          is(logDecay) {
            when((!r(31) && r(30, 0).orR) || (job.gatePolicy===GdnRuntimeRawPrepPolicyV7.LegacyOpen80.U && r(30, 0) >= F32.lit(80))) { fail(Status.Numerical.U) }
              .otherwise { g := r; operation := betaExp }
          }
          is(betaExp) { exponential := r; operation := betaDenominator }
          is(betaDenominator) { operation := betaInverse }
          is(betaInverse) { operation := betaSign }
          is(betaSign) {
            betaRaw:=r
            when(r(31) || F32.less(F32.lit(1), r)) { fail(Status.Numerical.U) }
              .otherwise { state := formatIssue }
          }
        }
      }
  }
  when(io.formatRequest.fire){formatAccepted:=formatAccepted+1.U;state:=formatWait}
  when(io.formatResult.fire){
    formatReturned:=formatReturned+1.U
    val r=io.formatResult.bits
    when(r.error || r.value(14,7)===255.U){fail(Status.Numerical.U)}
      .elsewhen(poison || currentFault){state:=finish}
      .otherwise{beta:=Cat(r.value,0.U(16.W));state:=writeGate}
  }
  when(state===finish && io.resourcesDrained){
    val exact=bytes.pad(80)===expectedBytes && scalarAccepted===expectedScalar && scalarReturned===expectedScalar &&
      formatAccepted===expectedFormat && formatReturned===expectedFormat
    val complete=status===Status.Ok.U && !poison && !currentFault && exact
    terminal.accepted:=job;terminal.tag:=job.tag;terminal.writeBytes:=bytes;terminal.cycles:=cycles
    terminal.status:=Mux(status===Status.Ok.U && (!exact || poison || currentFault),Status.Protocol.U,status)
    terminal.outputCommitted:=complete
    when(status===Status.Ok.U && !exact){poison:=true.B}
    state:=report
  }
  when(io.done.fire){state:=Mux(io.resetRequired || terminal.status=/=Status.Ok.U,locked,idle)}
  assert(PopCount(Seq(io.memory.valid,io.scalar.request.valid,io.formatRequest.valid))<=1.U)
}
