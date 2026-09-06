// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Public v2 tensor prefix: tensor_base -> shape4 -> stride3 -> optional policy.
  * Field encodings match config/descriptor_public_encoding.json and
  * heteronpu.descriptor_chain. Strides are ELEMENT strides, not byte strides.
  */
class TensorReadRequest extends Bundle {
  val tableBase = UInt(64.W); val tableLimit = UInt(64.W)
  val entryCount = UInt(25.W); val root = UInt(24.W)
  val writeAccess = Bool(); val regions = Vec(4, new Region)
}
class DecodedTensor extends Bundle {
  val address = UInt(64.W); val elementCount = UInt(32.W)
  val payloadBytes = UInt(64.W); val paddedEnd = UInt(64.W)
  val dtype = UInt(4.W); val rank = UInt(3.W)
  val dims = Vec(4, UInt(18.W)); val tail = UInt(24.W)
}
class TensorReadResult extends Bundle {
  val status = UInt(8.W); val tensor = new DecodedTensor
}
class TypedTensorReader extends Module {
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new TensorReadRequest))
    val result = Decoupled(new TensorReadResult)
    val record = Decoupled(new Record128Request)
    val recordResult = Flipped(Decoupled(new Record128Result))
  })
  val idle :: issue :: receive :: validate :: reply :: Nil = Enum(5)
  val state = RegInit(idle)
  val cfg = Reg(new TensorReadRequest)
  val result = Reg(new TensorReadResult)
  val step = RegInit(0.U(2.W)); val index = Reg(UInt(24.W))
  val indices = Reg(Vec(3, UInt(24.W)))
  val strides = Reg(Vec(3, UInt(24.W)))
  io.request.ready := state === idle
  io.result.valid := state === reply; io.result.bits := result
  io.record.valid := state === issue
  io.record.bits.tableBase := cfg.tableBase
  io.record.bits.tableLimit := cfg.tableLimit
  io.record.bits.entryCount := cfg.entryCount
  io.record.bits.index := index
  io.record.bits.requestTag := step
  io.recordResult.ready := state === receive
  def fail(status: UInt): Unit = { result.status := status; state := reply }
  when(io.request.fire) {
    cfg := io.request.bits
    index := io.request.bits.root
    step := 0.U
    indices := VecInit(Seq.fill(3)(0xffffff.U(24.W)))
    result := 0.U.asTypeOf(new TensorReadResult)
    state := issue
  }
  when(io.record.fire) { state := receive }
  when(io.recordResult.fire) {
    val r = io.recordResult.bits
    val w = r.data
    val next = w(55, 32)
    val kind = w(7, 0)
    val revisits = (0 until 3).map(i => i.U < step && index === indices(i)).reduce(_ || _)
    when(r.status =/= 0.U) { fail(r.status) }
    .elsewhen(r.requestTag =/= step) { fail(Status.Protocol.U) }
    .elsewhen(w(31, 8) =/= 0.U || revisits) { fail(Status.Malformed.U) }
    .elsewhen(kind =/= step + 1.U) { fail(Status.Unsupported.U) }
    .otherwise {
      indices(step) := index
      when(step === 0.U) {
        val dtype = w(111,108); val rank = w(119,116)
        when(w(107,104) =/= 0.U || w(115,112) =/= 0.U ||
          (dtype =/= 5.U && dtype =/= 7.U) || rank < 1.U || rank > 4.U) {
          fail(Status.Unsupported.U)
        }.otherwise {
          result.tensor.address := Cat(0.U(8.W), w(127,120), w(103,56))
          result.tensor.dtype := dtype; result.tensor.rank := rank
          index := next; step := 1.U; state := issue
        }
      }.elsewhen(step === 1.U) {
        for (i <- 0 until 4) result.tensor.dims(i) := w(56+18*i+17,56+18*i)
        index := next; step := 2.U; state := issue
      }.otherwise {
        for (i <- 0 until 3) strides(i) := w(56+24*i+23,56+24*i)
        result.tensor.tail := next
        state := validate
      }
    }
  }
  when(state === validate) {
    val t = result.tensor
    val dimsOK = (0 until 4).map(i => t.dims(i) > 0.U && (i.U < t.rank || t.dims(i) === 1.U)).reduce(_ && _)
    val elements = t.dims.reduce(_ * _)
    val elementBytes = Mux(t.dtype === 5.U, 2.U, 4.U)
    val bytes = elements * elementBytes
    val end = t.address.pad(96) + (((bytes + 63.U) >> 6) << 6)
    val expected = Seq(t.dims(1)*t.dims(2)*t.dims(3), t.dims(2)*t.dims(3), t.dims(3))
    val stridesOK = (0 until 3).map(i => !strides(i)(23) && strides(i).pad(80) === expected(i)).reduce(_ && _)
    val allowed = cfg.regions.map { r =>
      r.base < r.limit && t.address >= r.base && end <= r.limit &&
        Mux(cfg.writeAccess, r.write, r.read)
    }.reduce(_ || _)
    when(!dimsOK || elements > "hffffffff".U || t.address(5,0) =/= 0.U || end > (BigInt(1)<<56).U || end <= t.address) {
      fail(Status.Bounds.U)
    }.elsewhen(!stridesOK) { fail(Status.Unsupported.U) }
    .elsewhen(!allowed) { fail(Status.Permission.U) }
    .otherwise {
      result.tensor.elementCount := elements
      result.tensor.payloadBytes := bytes
      result.tensor.paddedEnd := end
      result.status := Status.Ok.U
      state := reply
    }
  }
  when(io.result.fire) { state := idle }
}
