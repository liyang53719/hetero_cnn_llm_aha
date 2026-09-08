// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

class SiluVectorInput(val lanes: Int) extends Bundle {
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
class SiluVectorUnit(val lanes: Int = 16) extends Module {
  require(lanes > 0 && lanes <= 16)
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new SiluVectorInput(lanes)))
    val result = Decoupled(new SiluVectorOutput(lanes))
  })
  val idle :: issue :: waitAll :: reply :: Nil = Enum(4)
  val state = RegInit(idle)
  val input = Reg(new SiluVectorInput(lanes))
  val value = Reg(Vec(lanes, UInt(32.W)))
  val probability = Reg(Vec(lanes, UInt(32.W)))
  val phase = RegInit(0.U(3.W))
  val error = RegInit(false.B)
  val cores = Seq.fill(lanes)(Module(new BlockScalarFloat))
  val allReady = cores.map(_.io.request.ready).reduce(_ && _)
  val allValid = cores.map(_.io.result.valid).reduce(_ && _)
  io.request.ready := state === idle
  io.result.valid := state === reply
  io.result.bits.value := value
  io.result.bits.error := error
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
    core.io.result.ready := state === waitAll && allValid
  }
  when(io.request.fire) {
    input := io.request.bits; phase := 0.U; error := false.B; state := issue
  }
  when(state === issue && allReady) { state := waitAll }
  when(state === waitAll && allValid) {
    val bad = cores.map(_.io.error).reduce(_ || _)
    for (i <- 0 until lanes) {
      value(i) := cores(i).io.result.bits
      when(phase === 0.U) { probability(i) := cores(i).io.result.bits }
    }
    error := error || bad
    when(bad || phase === 5.U) { state := reply }
      .otherwise { phase := phase + 1.U; state := issue }
  }
  when(io.result.fire) { state := idle }
}

/** Existing owner job and MemoryRequest ABI, widened SFU arithmetic only.
  * All read/write traffic still goes through the common real iDMA backend.
  * Completion is emitted only after the final successful write response.
  */
class VectorSiluOwner extends Module {
  val io = IO(new Bundle {
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
  val vector = Module(new SiluVectorUnit(16))
  vector.io.request.valid := state === compute
  vector.io.request.bits.gate := a; vector.io.request.bits.up := b
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
  when(vector.io.request.fire) { state:=waitCompute }
  when(vector.io.result.fire) {
    when(vector.io.result.bits.error) { fail(Status.Numerical.U) }
      .otherwise { output:=vector.io.result.bits.value.asUInt;state:=write }
  }
  when(io.done.fire) { state:=Mux(status===0.U,idle,locked) }
}
