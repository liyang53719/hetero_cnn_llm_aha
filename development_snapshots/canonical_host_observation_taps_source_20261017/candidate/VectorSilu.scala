// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

class SiluVectorInput(val lanes: Int,enableBinaryAdd:Boolean=false) extends Bundle {
  // Internal loan opcode; absent from every existing default bundle.
  val binaryAdd=if(enableBinaryAdd)Some(Bool())else None
  val gate = Vec(lanes, UInt(32.W))
  val up = Vec(lanes, UInt(32.W))
}
class SiluVectorOutput(val lanes: Int) extends Bundle {
  val value = Vec(lanes, UInt(32.W))
  val error = Bool()
}

/** Parallel, bit-compatible implementation of the frozen scalar SiLU recipe.
  * Each lane retains separate FP32 rounding at exp/add/div/mul/mul/mul.
  * Independent early exp completion is held until all lanes have replied.
  * No floating-point reassociation, lookup approximation, or software callback.
  */
class SiluVectorUnit(val lanes: Int = 16,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableBinaryAdd:Boolean=false) extends Module {
  require(lanes > 0 && lanes <= 16)
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new SiluVectorInput(lanes,enableBinaryAdd)))
    val result = Decoupled(new SiluVectorOutput(lanes))
  })
  val idle :: issue :: waitAll :: reply :: Nil = Enum(4)
  val state = RegInit(idle)
  val input = Reg(new SiluVectorInput(lanes,enableBinaryAdd))
  val value = Reg(Vec(lanes, UInt(32.W)))
  val probability = Reg(Vec(lanes, UInt(32.W)))
  val phase = RegInit(0.U(3.W))
  val error = RegInit(false.B)
  val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))
  val allReady = cores.map(_.io.request.ready).reduce(_ && _)
  val allValid = cores.map(_.io.result.valid).reduce(_ && _)
  // BEGIN_CANONICAL_SILU_PHASE4_TAP_V1
  // Read the already-materialized phase4 register at the real phase5 issue.
  // The resident loan identity, abort and poison are external qualifications.
  if(Qwen2NumericPolicy.official(numericPolicy) && enableBinaryAdd && lanes==16){
    val canonicalSiluTap=Wire(new Bundle {
      val valid=Bool();val value=Vec(16,UInt(32.W))
    })
    canonicalSiluTap:=0.U.asTypeOf(canonicalSiluTap)
    canonicalSiluTap.valid:=state===issue && phase===5.U && allReady && !error && !input.binaryAdd.get
    when(canonicalSiluTap.valid){canonicalSiluTap.value:=value}
    dontTouch(canonicalSiluTap)
  }
  // END_CANONICAL_SILU_PHASE4_TAP_V1
  io.request.ready := state === idle
  io.result.valid := state === reply
  io.result.bits.value := value
  io.result.bits.error := error
  // Fault replies carry no numerical payload in the explicit loan profile.
  if(enableBinaryAdd){when(error){io.result.bits.value:=0.U.asTypeOf(value)}}
  for (i <- 0 until lanes) {
    val core = cores(i)
    core.io.request.valid := state === issue && allReady
    core.io.request.bits.op := MuxLookup(phase, ScalarOp.Mul.U)(Seq(
      0.U -> ScalarOp.ExpNegative.U, 1.U -> ScalarOp.Add.U, 2.U -> ScalarOp.Div.U))
    core.io.request.bits.a := MuxLookup(phase, value(i))(Seq(
      0.U -> input.gate(i), 1.U -> F32.lit(1), 2.U -> F32.lit(1)))
    core.io.request.bits.b := MuxLookup(phase, input.up(i))(Seq(
      0.U -> 0.U, 1.U -> value(i), 2.U -> value(i),
      3.U -> Mux(input.gate(i)(31), probability(i), F32.lit(1)), 4.U -> input.gate(i)))
    // One real Add through the existing lane ALU, with no SiLU sentinel or
    // BF16 materialization. The mode and both operands come from the latch.
    if(enableBinaryAdd){when(input.binaryAdd.get){
      core.io.request.bits.op:=ScalarOp.Add.U
      core.io.request.bits.a:=input.gate(i)
      core.io.request.bits.b:=input.up(i)
    }}
    core.io.result.ready := state === waitAll && allValid
  }
  when(io.request.fire) {
    input := io.request.bits; phase := 0.U; error := false.B; state := issue
  }
  when(state === issue && allReady) { state := waitAll }
  when(state === waitAll && allValid) {
    val bad = cores.map(_.io.error).reduce(_ || _) ||
      (if(Qwen2NumericPolicy.official(numericPolicy)) (phase===4.U || phase===5.U) &&
        cores.map(c=> !TensorMath.finite(F32.bf(c.io.result.bits))).reduce(_||_) else false.B)
    for (i <- 0 until lanes) {
      // Phase 4 materializes SiLU; phase 5 materializes SiLU*Up. The next
      // phase consumes this same existing value register after RNE BF16.
      value(i) := (if(Qwen2NumericPolicy.official(numericPolicy))
        Mux(phase===4.U || phase===5.U,F32.bf(cores(i).io.result.bits),cores(i).io.result.bits)
        else cores(i).io.result.bits)
      when(phase === 0.U) { probability(i) := cores(i).io.result.bits }
    }
    error := error || bad
    when(if(enableBinaryAdd)bad || input.binaryAdd.get || phase === 5.U else bad || phase === 5.U) { state := reply }
      .otherwise { phase := phase + 1.U; state := issue }
  }
  when(io.result.fire) { state := idle }
}

/** Existing owner job and MemoryRequest ABI, widened SFU arithmetic only.
  * All read/write traffic still goes through the common real iDMA backend.
  * Completion is emitted only after the final successful write response.
  */
class VectorSiluOwner(enableTileLoan:Boolean=false,numericPolicy:Qwen2NumericPolicy=Qwen2NumericPolicy.LegacyV0,enableBinaryAdd:Boolean=false) extends Module {
  require(!enableBinaryAdd || enableTileLoan,"binary Add is an explicit internal tile arithmetic loan")
  val io = IO(new Bundle {
    val loan=if(enableTileLoan)Some(new FfnSiluLoanPort(enableBinaryAdd))else None
    val job = Flipped(Decoupled(new QwenOwnerJob))
    val done = Decoupled(new QwenOwnerResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val resetRequired = Output(Bool())
  })
  val idle :: readGate :: waitGate :: readUp :: waitUp :: compute :: waitCompute :: write :: waitWrite :: finish :: locked :: Nil = Enum(11)
  val state = RegInit(idle)
  val job = Reg(new QwenOwnerJob)
  val index = RegInit(0.U(32.W))
  val elements = Reg(UInt(32.W))
  val cycles = RegInit(0.U(64.W))
  val bytes = RegInit(0.U(64.W))
  val status = RegInit(0.U(8.W))
  val sequence = RegInit(0.U(32.W))
  val a = Reg(Vec(16,UInt(32.W)))
  val b = Reg(Vec(16,UInt(32.W)))
  val output = Reg(UInt(512.W))
  val vector = Module(new SiluVectorUnit(16,numericPolicy=numericPolicy,enableBinaryAdd=enableBinaryAdd))
  vector.io.request.valid := state === compute
  vector.io.request.bits.gate := a; vector.io.request.bits.up := b
  if(enableBinaryAdd){vector.io.request.bits.binaryAdd.get:=false.B}
  vector.io.result.ready := state === waitCompute
  io.job.ready := state === idle
  io.done.valid := state === finish
  io.done.bits.tag := job.tag; io.done.bits.status := status
  io.done.bits.cycles := cycles; io.done.bits.writeBytes := bytes
  io.done.bits.usefulMacs := 0.U; io.done.bits.executedMacs := 0.U
  io.resetRequired := status =/= 0.U
  io.memory.valid := state === readGate || state === readUp || state === write
  io.memory.bits.write := state === write
  io.memory.bits.address := Mux(state === readGate,job.a,Mux(state === readUp,job.b,job.dst)) + (index.pad(64)<<2)
  io.memory.bits.data := Mux(state === write,output,0.U)
  io.memory.bits.mask := Mux(state === write,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag := Cat(job.tag,sequence)
  io.response.ready := state === waitGate || state === waitUp || state === waitWrite
  when(state =/= idle && state =/= finish && state =/= locked) { cycles := cycles + 1.U }
  def fail(code: UInt): Unit = { status := code; state := finish }
  when(io.job.fire) {
    job := io.job.bits; index := 0.U; sequence := 0.U; cycles := 0.U; bytes := 0.U; status := 0.U
    val j = io.job.bits
    val count = j.m * j.n
    val size = count.pad(66)<<2
    val badAddress = Seq(j.a,j.b,j.dst).map(x => x(5,0) =/= 0.U || x.pad(66)+size > (BigInt(1)<<56).U).reduce(_||_)
    elements := count
    when(j.kind =/= QwenOwnerKind.Activation.U || count===0.U || count(3,0)=/=0.U || j.writeBytes=/=size || badAddress) {
      fail(Status.Bounds.U)
    }.otherwise { state := readGate }
  }
  when(io.memory.fire) { state := Mux(state===readGate,waitGate,Mux(state===readUp,waitUp,waitWrite)) }
  when(io.response.fire) {
    val r=io.response.bits
    when(r.tag=/=Cat(job.tag,sequence)) { fail(Status.Protocol.U) }
      .elsewhen(r.error) { fail(Status.Memory.U) }
      .otherwise {
        sequence := sequence+1.U
        when(state===waitGate) { a:=r.data.asTypeOf(a);state:=readUp }
        when(state===waitUp) { b:=r.data.asTypeOf(b);state:=compute }
        when(state===waitWrite) {
          bytes:=bytes+64.U
          when(index+16.U===elements) { state:=finish }
            .otherwise { index:=index+16.U;state:=readGate }
        }
      }
  }
  when(if(enableTileLoan)vector.io.request.fire && state===compute else vector.io.request.fire) { state:=waitCompute }
  when(if(enableTileLoan)vector.io.result.fire && state===waitCompute else vector.io.result.fire) {
    when(vector.io.result.bits.error) { fail(Status.Numerical.U) }
      .otherwise { output:=vector.io.result.bits.value.asUInt;state:=write }
  }
  if(enableTileLoan){
    val p=io.loan.get
    val loanActive=RegInit(false.B);val loanPoison=RegInit(false.B)
    // BEGIN_CANONICAL_SILU_LOAN_CONTEXT_TAP_V1
    // This is qualification only, not a claim of resident coordinates or B retirement.
    if(Qwen2NumericPolicy.official(numericPolicy) && enableBinaryAdd){
      val canonicalLoanContextTap=Wire(new Bundle {
        val active=Bool();val poison=Bool();val abort=Bool()
      })
      canonicalLoanContextTap.active:=loanActive
      canonicalLoanContextTap.poison:=loanPoison
      canonicalLoanContextTap.abort:=p.abort
      dontTouch(canonicalLoanContextTap)
    }
    // END_CANONICAL_SILU_LOAN_CONTEXT_TAP_V1
    val borrow=state===idle && !loanActive && !loanPoison && !p.abort
    p.request.ready:=borrow && vector.io.request.ready
    p.result.valid:=(if(enableBinaryAdd)loanActive && vector.io.result.valid && !loanPoison && !p.abort else loanActive && vector.io.result.valid)
    p.result.bits:=vector.io.result.bits
    p.busy:=(if(enableBinaryAdd)loanActive || loanPoison || p.abort else loanActive || loanPoison)
    p.drained:= !loanActive
    p.resetRequired:=loanPoison
    when(state===idle){
      vector.io.request.valid:=p.request.valid && borrow
      vector.io.request.bits:=p.request.bits
    }
    when(loanActive){vector.io.result.ready:=(if(enableBinaryAdd)p.result.ready || loanPoison || p.abort else p.result.ready)}
    io.job.ready:=state===idle && !loanActive && !loanPoison && !p.request.valid && !p.abort
    io.resetRequired:=status=/=0.U || loanPoison
    when(p.request.fire){loanActive:=true.B}
    if(enableBinaryAdd){
      // resetRequired stays registered: a borrower may feed it into abort.
      // Never feed this cycle's result.error back into abort; consume the
      // error response and register borrower poison at that same edge.
      // Abort wins over a coincident final result. Drain privately even when
      // the borrower holds ready low; never publish an aborted payload.
      when(loanActive && vector.io.result.fire){
        loanActive:=false.B
        when(vector.io.result.bits.error){loanPoison:=true.B}
      }
    }else{
      when(p.result.fire){loanActive:=false.B;when(p.result.bits.error){loanPoison:=true.B}}
    }
    // The disabled profile retains the original stable result drain.
    // Both profiles block new traffic until coordinated reset after abort.
    when(p.abort){loanPoison:=true.B}
  }
  when(io.done.fire) { state:=Mux(status===0.U,idle,locked) }
}

/** Explicit internal loan of the existing sixteen-lane arithmetic owner. */
class FfnSiluLoanPort(enableBinaryAdd:Boolean=false) extends Bundle {
  val request=Flipped(Decoupled(new SiluVectorInput(16,enableBinaryAdd)))
  val result=Decoupled(new SiluVectorOutput(16))
  val abort=Input(Bool());val busy=Output(Bool());val drained=Output(Bool());val resetRequired=Output(Bool())
}
