// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Separate source candidate reuses original job/result/port ABI and fixed
  * max32 producer. Existing compiled GdnRuntimeInputPrepOwner still rejects2.
  * The new gate path requires the one exact qualified shared ScalarV2 service;
  * it is not selectable as a trusted profile until integrated numeric gates.
  */
object GdnRuntimeGatePolicyV2 { val DualInnerCandidate=2 }
/** No arithmetic service is instantiated here: every operation is sent to the
  * one external shared BlockScalarFloat. Softplus is shared opcode 7; the
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
class GdnRuntimeInputPrepScalarV2Owner extends Module {
  val io = IO(new GdnRuntimeInputPrepOwnerPort)
  val idle :: readParam :: waitParam :: readVector :: waitVector :: issue :: waitScalar :: writeVector :: waitWrite :: writeGate :: waitGate :: finish :: locked :: Nil = Enum(13)
  val square :: sum :: epsilon :: root :: inverse :: normalize :: scaleQuery :: biasAdd :: softplus :: aExp :: aInverse :: logDecay :: betaExp :: betaDenominator :: betaInverse :: betaSign :: torchTermAdd :: torchGroupAdd :: torchLaneAdd :: Nil = Enum(19)
  val state = RegInit(idle)
  val operation = RegInit(square)
  val job = Reg(new GdnRuntimeInputPrepJob)
  val parameters = Reg(Vec(4, Vec(16, UInt(32.W))))
  val input = Reg(Vec(128, UInt(16.W)))
  val output = Reg(Vec(128, UInt(32.W)))
  val param = RegInit(0.U(2.W)) // ALog, dtBias, A(and B16), B32
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
  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.accepted := job
  io.done.bits.tag := job.tag
  io.done.bits.status := status
  io.done.bits.writeBytes := bytes
  io.done.bits.cycles := cycles
  io.done.bits.outputCommitted := state === finish && status === Status.Ok.U &&
    bytes === (job.tokens * job.layout.rowBytes).pad(64)
  io.resetRequired := status =/= Status.Ok.U

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
  val parameterAddress = MuxLookup(param, job.aLog.pad(66) + (head(4).asUInt.pad(66) << 6))(Seq(
    1.U -> job.dtBias.pad(66), 2.U -> abRow, 3.U -> (abRow + (job.layout.valueHeads.pad(66) << 1))))
  io.memory.valid := state === readParam || state === readVector || state === writeVector || state === writeGate
  io.memory.bits.write := state === writeVector || state === writeGate
  io.memory.bits.address := MuxLookup(state, rawAddress)(Seq(
    readParam -> parameterAddress, writeVector -> preparedVector, writeGate -> preparedGate))(63,0)
  val outputBeats = output.asUInt.asTypeOf(Vec(8, UInt(512.W)))
  io.memory.bits.data := Mux(state === writeGate, Cat(0.U(448.W), beta, g), Mux(state === writeVector, outputBeats(beat), 0.U))
  io.memory.bits.mask := Mux(io.memory.bits.write, Fill(64, 1.U(1.W)), 0.U)
  io.memory.bits.tag := Cat(job.tag, sequence)
  io.response.ready := state === waitParam || state === waitVector || state === waitWrite || state === waitGate

  val torchReduction = job.reductionPolicy === GdnRuntimePrepPolicy.TorchCpuDefault128.U
  val reductionAddress = Mux(torchReduction && (operation === square || operation === torchTermAdd),
    Cat(lane(1,0),lane(3,2),lane(6,4)),lane)
  val x = Cat(input(reductionAddress), 0.U(16.W))
  val a = parameters(0)(parameterHead)
  val b = parameters(1)(parameterHead)
  val aLog = parameters(2)(parameterHead)
  val bias = parameters(3)(parameterHead)
  // Distinct candidate: explicitly binds the exact finite ScalarV2 recipe.
  // Gate2 admission is NOT inherited by the old frozen prefix owner. This
  // mapping does not upgrade41 finite Scalar samples to an all-domain proof.
  val dualGate = job.gatePolicy === GdnRuntimeGatePolicyV2.DualInnerCandidate.U
  val requestPolicy = Mux(dualGate && operation === softplus, UnifiedScalarPolicyV2.DualInnerSoftplus.U,
    Mux(dualGate && operation === aExp, UnifiedScalarPolicyV2.GradualDecay.U, UnifiedScalarPolicyV2.Legacy.U))
  io.scalar.request.bits.policy := requestPolicy
  io.scalar.request.valid := state === issue
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
  io.scalar.result.ready := state === waitScalar
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }

  when(io.job.fire) {
    job := io.job.bits; token := 0.U; param := 0.U; role := 0.U; head := 0.U; beat := 0.U; lane := 0.U
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
    when(j.tokens===0.U || j.tokens>128.U || !GdnRuntimeChunkLayout.admitted(j.layout) || badAddress || badOverlap) { fail(Status.Bounds.U) }
      .elsewhen(j.reductionPolicy>GdnRuntimePrepPolicy.TorchCpuDefault128.U || j.gatePolicy>GdnRuntimeGatePolicyV2.DualInnerCandidate.U) { fail(Status.Unsupported.U) }
      .elsewhen(io.response.valid || io.scalar.result.valid) { fail(Status.Protocol.U) }
      .otherwise { state := readParam }
  }
  when(io.memory.fire) {
    state := MuxLookup(state, waitVector)(Seq(readParam -> waitParam, writeVector -> waitWrite, writeGate -> waitGate))
  }
  when(io.response.fire) {
    val r = io.response.bits
    when(r.tag =/= Cat(job.tag, sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence + 1.U
        when(state === waitParam) {
          for(i<-0 until 16) {
            val low = r.data((i+1)*16-1,i*16)
            val high = r.data((i+17)*16-1,(i+16)*16)
            val half = Mux(parameterHalf,high,low)
            when(param===0.U) { parameters(2)(i):=r.data((i+1)*32-1,i*32) }
              .elsewhen(param===1.U) { parameters(3)(i):=Cat(half,0.U(16.W)) }
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
          bytes := bytes + 64.U
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
          bytes := bytes + 64.U
          when(head +& 1.U === job.layout.valueHeads) {
            when(token +& 1.U === job.tokens) { state:=finish }
              .otherwise {token:=token+1.U;head:=0.U;role:=0.U;beat:=0.U;param:=0.U;state:=readParam}
          }.otherwise {
            head:=head+1.U;role:=0.U;beat:=0.U
            when(head===15.U) {param:=0.U;state:=readParam}.otherwise{state:=readVector}
          }
        }
      }
  }
  when(io.scalar.request.fire) { state := waitScalar }
  when(io.scalar.result.fire) {
    val r = io.scalar.result.bits.value
    when(io.scalar.result.bits.policy =/= requestPolicy) { fail(Status.Protocol.U) }
      .elsewhen(io.scalar.result.bits.error || !TensorMath.finite(r)) { fail(Status.Numerical.U) }
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
            when((!r(31) && r(30, 0).orR) || (job.gatePolicy===GdnRuntimePrepPolicy.LegacyOpen80.U && r(30, 0) >= F32.lit(80))) { fail(Status.Numerical.U) }
              .otherwise { g := r; operation := betaExp }
          }
          is(betaExp) { exponential := r; operation := betaDenominator }
          is(betaDenominator) { operation := betaInverse }
          is(betaInverse) { operation := betaSign }
          is(betaSign) {
            beta := F32.bf(r)
            when(r(31) || F32.less(F32.lit(1), r)) { fail(Status.Numerical.U) }
              .otherwise { state := writeGate }
          }
        }
      }
  }
  when(io.done.fire) { state := Mux(status === Status.Ok.U, idle, locked) }
}
