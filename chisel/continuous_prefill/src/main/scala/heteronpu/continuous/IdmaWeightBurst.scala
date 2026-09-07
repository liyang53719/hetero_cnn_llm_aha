// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** An immutable, already permission-checked Dense weight tensor for one job.
  * Only this range can be prefetched. Metadata, activations and stores bypass.
  * A change of job/request must pulse flush before another memory request.
  */
class IdmaWeightWindow extends Bundle {
  val enable = Bool()
  val base = UInt(64.W)
  val limit = UInt(64.W)
}

/** Same single pinned iDMA backend, with a bounded read-only weight mailbox.
  * At most 16 x 64B are fetched per real iDMA transfer. The transfer ends at
  * the tensor limit, a tensor-relative line or a physical 1KiB boundary.
  * The last bound honors pinned iDMA src/dst_max_llen=4 and implies AXI 4KiB.
  * Only the final successful backend response validates a line. A failed beat
  * poisons the whole line; all requested beats are drained and no consumer is
  * given successful data. Writes remain one beat and return only after B.
  * This is not a persistent object cache and never fetches a new tensor speculatively.
  */
class RetainedIdmaWeightBurstAdapter(maxBeats: Int = 16) extends Module {
  require(maxBeats >= 1 && maxBeats <= 16 && isPow2(maxBeats))
  val idxBits = math.max(1, log2Ceil(maxBeats))
  val countBits = log2Ceil(maxBeats + 1)
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new MemoryRequest))
    val response = Decoupled(new MemoryResponse)
    val window = Input(new IdmaWeightWindow)
    val flush = Input(Bool())
    val axi = new BlockAxiMaster
    val resetRequired = Output(Bool())
    val transfers = Output(UInt(64.W))
    val readBeats = Output(UInt(64.W))
    val writeBeats = Output(UInt(64.W))
    val readBursts = Output(UInt(64.W))
    val cacheHits = Output(UInt(64.W))
  })
  val idle :: issue :: waitDma :: reply :: locked :: Nil = Enum(5)
  val state = RegInit(idle)
  val req = Reg(new MemoryRequest)
  val rsp = Reg(new MemoryResponse)
  val fault = RegInit(false.B)
  val poison = RegInit(false.B)
  val count = RegInit(1.U(countBits.W))
  val cacheable = RegInit(false.B)
  val data = Reg(Vec(maxBeats, UInt(512.W)))
  val lineValid = RegInit(false.B)
  val lineBase = Reg(UInt(64.W))
  val lineCount = Reg(UInt(countBits.W))
  val lineWindow = Reg(new IdmaWeightWindow)
  val localAw = RegInit(false.B)
  val localR = RegInit(false.B)
  val localId = Reg(UInt(4.W))
  val localCount = RegInit(0.U(countBits.W))
  val externalCount = RegInit(0.U(countBits.W))
  val localDone = RegInit(false.B)
  val externalDone = RegInit(false.B)
  val extId = Reg(UInt(8.W))
  val arSeen = RegInit(false.B)
  val transfers = RegInit(0.U(64.W))
  val reads = RegInit(0.U(64.W))
  val writes = RegInit(0.U(64.W))
  val bursts = RegInit(0.U(64.W))
  val hits = RegInit(0.U(64.W))
  io.transfers := transfers; io.readBeats := reads; io.writeBeats := writes
  io.readBursts := bursts; io.cacheHits := hits; io.resetRequired := poison

  val backend = Module(new RetainedIdmaBackend)
  val d = backend.io
  val rr = d.axi_read_req_o.asTypeOf(new IdmaAxiRequest)
  val wr = d.axi_write_req_o.asTypeOf(new IdmaAxiRequest)
  val rs = WireDefault(0.U.asTypeOf(new IdmaAxiResponse))
  val ws = WireDefault(0.U.asTypeOf(new IdmaAxiResponse))
  d.clk_i := clock; d.rst_ni := !reset.asBool
  d.req_valid_i := state === issue
  d.src_addr_i := Mux(req.write, 0.U, req.address)
  d.dst_addr_i := Mux(req.write, req.address, 0.U)
  d.length_i := Mux(req.write, PopCount(req.mask), count.pad(32) << 6)
  d.rsp_ready_i := state === waitDma && localDone && externalDone
  d.axi_read_rsp_i := rs.asUInt; d.axi_write_rsp_i := ws.asUInt
  io.request.ready := state === idle && !poison && !io.flush
  io.response.valid := state === reply; io.response.bits := rsp
  io.axi.aw.valid := false.B; io.axi.aw.bits := 0.U.asTypeOf(new BlockAxiAddress)
  io.axi.ar.valid := false.B; io.axi.ar.bits := 0.U.asTypeOf(new BlockAxiAddress)
  io.axi.w.valid := false.B; io.axi.w.bits := 0.U.asTypeOf(new BlockAxiWrite)
  io.axi.b.ready := false.B; io.axi.r.ready := false.B

  when(io.flush) { lineValid := false.B }
  val active = state === issue || state === waitDma
  when(active) {
    when(req.write) {
      // Unchanged one-beat source mailbox and actual external B completion.
      rs.ar_ready := !localR && !localDone
      rs.r_valid := localR; rs.r.id := localId; rs.r.data := req.data
      rs.r.last := true.B; rs.r.resp := Mux(fault, 3.U, 0.U)
      when(rr.ar_valid && rs.ar_ready) {
        localR := true.B; localId := rr.ar.id
        when(rr.ar.addr =/= 0.U || rr.ar.len =/= 0.U || rr.ar.size > 6.U) { fault := true.B }
      }
      when(rs.r_valid && rr.r_ready) { localR := false.B; localDone := true.B }
      io.axi.aw.valid := wr.aw_valid
      io.axi.aw.bits.addr := wr.aw.addr; io.axi.aw.bits.id := wr.aw.id
      io.axi.aw.bits.len := wr.aw.len; io.axi.aw.bits.size := wr.aw.size; io.axi.aw.bits.burst := wr.aw.burst
      io.axi.w.valid := wr.w_valid; io.axi.w.bits.data := wr.w.data
      io.axi.w.bits.strb := wr.w.strb; io.axi.w.bits.last := wr.w.last
      io.axi.b.ready := wr.b_ready
      ws.aw_ready := io.axi.aw.ready; ws.w_ready := io.axi.w.ready; ws.b_valid := io.axi.b.valid
      val bid = Mux(io.axi.aw.fire, io.axi.aw.bits.id, extId)
      ws.b.id := bid(3, 0); ws.b.resp := Mux(io.axi.b.bits.id =/= bid, 3.U, io.axi.b.bits.resp)
      when(io.axi.aw.fire) { extId := io.axi.aw.bits.id }
      when(io.axi.w.fire) { writes := writes + 1.U }
      when(io.axi.b.fire) {
        externalDone := true.B
        when(io.axi.b.bits.resp =/= 0.U || io.axi.b.bits.id =/= bid) { fault := true.B }
      }
    }.otherwise {
      // One bounded source burst. LAST is checked against the accepted length.
      io.axi.ar.valid := rr.ar_valid
      io.axi.ar.bits.addr := rr.ar.addr; io.axi.ar.bits.id := rr.ar.id
      io.axi.ar.bits.len := rr.ar.len; io.axi.ar.bits.size := rr.ar.size; io.axi.ar.bits.burst := rr.ar.burst
      rs.ar_ready := io.axi.ar.ready
      io.axi.r.ready := rr.r_ready && !externalDone
      rs.r_valid := io.axi.r.valid && !externalDone
      val rid = Mux(io.axi.ar.fire, io.axi.ar.bits.id, extId)
      val last = externalCount + 1.U === count
      val bad = io.axi.r.bits.id =/= rid || io.axi.r.bits.last =/= last || (!arSeen && !io.axi.ar.fire)
      rs.r.id := rid(3, 0); rs.r.data := io.axi.r.bits.data; rs.r.last := last
      rs.r.resp := Mux(bad, 3.U, io.axi.r.bits.resp)
      when(io.axi.ar.fire) {
        extId := io.axi.ar.bits.id; arSeen := true.B; bursts := bursts + 1.U
        when(arSeen || rr.ar.addr =/= req.address || rr.ar.len +& 1.U =/= count || rr.ar.size =/= 6.U || rr.ar.burst =/= 1.U) { fault := true.B }
      }
      when(io.axi.r.fire) {
        reads := reads + 1.U; externalCount := externalCount + 1.U
        when(last) { externalDone := true.B }
        when(bad || io.axi.r.bits.resp =/= 0.U) { fault := true.B }
      }
      // Destination mailbox accepts W only after AW; no circular dependency.
      ws.aw_ready := !localAw && !localDone
      ws.w_ready := localAw && localCount < count && !localDone
      ws.b_valid := localAw && localCount === count && !localDone
      ws.b.id := localId; ws.b.resp := Mux(fault, 3.U, 0.U)
      when(wr.aw_valid && ws.aw_ready) {
        localAw := true.B; localId := wr.aw.id
        when(wr.aw.addr =/= 0.U || wr.aw.len +& 1.U =/= count || wr.aw.size =/= 6.U || wr.aw.burst =/= 1.U) { fault := true.B }
      }
      when(wr.w_valid && ws.w_ready) {
        data(localCount(idxBits - 1, 0)) := wr.w.data
        localCount := localCount + 1.U
        when(wr.w.last =/= (localCount + 1.U === count) || !wr.w.strb.andR) { fault := true.B }
      }
      when(ws.b_valid && wr.b_ready) { localAw := false.B; localDone := true.B }
    }
  }

  when(io.request.fire) {
    val x = io.request.bits
    req := x; rsp.tag := x.tag; rsp.data := 0.U; rsp.error := false.B
    fault := false.B; localAw := false.B; localR := false.B; arSeen := false.B
    localCount := 0.U; externalCount := 0.U; localDone := false.B; externalDone := false.B
    val prefix = x.mask =/= 0.U && (x.mask & (x.mask + 1.U)) === 0.U
    val end = x.address.pad(66) + 64.U
    val validWindow = io.window.enable && io.window.base(5, 0) === 0.U && io.window.limit(5, 0) === 0.U &&
      io.window.base < io.window.limit && io.window.limit.pad(66) <= (BigInt(1) << 56).U
    val inWindow = !x.write && validWindow && x.address >= io.window.base && end <= io.window.limit.pad(66)
    val offset = x.address - io.window.base
    val lineRemaining = maxBeats.U(7.W) - ((offset >> 6) & (maxBeats - 1).U)
    val pageRemaining = maxBeats.U(7.W) - ((x.address >> 6) & (maxBeats - 1).U)
    val tensorRemaining = (io.window.limit - x.address) >> 6
    val bounded = Mux(lineRemaining < pageRemaining, lineRemaining, pageRemaining)
    val length = Mux(tensorRemaining < bounded, tensorRemaining, bounded)
    val hit = inWindow && lineValid && lineWindow.asUInt === io.window.asUInt &&
      x.address >= lineBase && end <= lineBase.pad(66) + (lineCount.pad(66) << 6)
    count := Mux(inWindow, length, 1.U)
    cacheable := inWindow; lineWindow := io.window
    when(x.address(5, 0) =/= 0.U || end > (BigInt(1) << 56).U || (x.write && !prefix)) {
      lineValid := false.B; rsp.error := true.B; poison := true.B; state := reply
    }.elsewhen(hit) {
      rsp.data := data(((x.address - lineBase) >> 6)(idxBits - 1, 0))
      hits := hits + 1.U; state := reply
    }.otherwise {
      lineValid := false.B; state := issue
    }
  }
  when(state === issue && d.req_ready_o) { transfers := transfers + 1.U; state := waitDma }
  when(state === waitDma && d.rsp_valid_o && d.rsp_ready_i) {
    val bad = fault || d.rsp_error_o
    rsp.error := bad; rsp.data := Mux(req.write || bad, 0.U, data(0))
    poison := bad; state := reply
    lineValid := !req.write && cacheable && !bad && !io.flush
    lineBase := req.address; lineCount := count
  }
  when(state === reply && io.response.fire) { state := Mux(poison, locked, idle) }
}
