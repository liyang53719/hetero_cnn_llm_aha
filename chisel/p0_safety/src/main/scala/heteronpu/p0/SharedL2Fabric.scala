// SPDX-License-Identifier: Apache-2.0
package heteronpu.p0

import chisel3._
import chisel3.util._

class SharedL2FabricIO(val addressBits: Int) extends Bundle {
  val rd_valid_i = Input(UInt(2.W)); val rd_ready_o = Output(UInt(2.W))
  val rd_addr_i = Input(UInt((2*addressBits).W))
  val rd_resp_valid_o = Output(UInt(2.W)); val rd_resp_ready_i = Input(UInt(2.W))
  val rd_data_o = Output(UInt(1024.W))
  val wr_valid_i = Input(Bool()); val wr_ready_o = Output(Bool())
  val wr_addr_i = Input(UInt(addressBits.W)); val wr_data_i = Input(UInt(512.W)); val wr_be_i = Input(UInt(64.W))
  val cycle_count_o = Output(UInt(64.W)); val read_count_o = Output(UInt(64.W)); val write_count_o = Output(UInt(64.W))
  val bank_conflict_count_o = Output(UInt(64.W)); val read_stall_count_o = Output(UInt(64.W)); val write_stall_count_o = Output(UInt(64.W))
  // Sticky [2]=write,[1]=read1,[0]=read0. Illegal requests never access SRAM.
  // Legacy ABI has no error response; supervisor must abort/reset on this output.
  val address_error_o = Output(UInt(3.W))
}

/** Sixteen real 128-bit synchronous Chisel memories, grouped four per beat.
  * Data holds while response is stalled. No memory initialization assumption.
  * SRAM macro binding remains a separate physical integration gate.
  */
class SharedL2Fabric(val cfg: LocalSramConfig = LocalSramConfig()) extends Module {
  val io = IO(new SharedL2FabricIO(cfg.addressBits))
  val addrs = VecInit((0 until 2).map(p => io.rd_addr_i((p+1)*cfg.addressBits-1,p*cfg.addressBits)))
  val groups = VecInit(addrs.map(_(1,0))); val rows = VecInit(addrs.map(_ >> 2))
  val wg = io.wr_addr_i(1,0); val wr = io.wr_addr_i >> 2
  val legal = VecInit(rows.map(_ < cfg.rowsPerBank.U)); val wlegal = wr < cfg.rowsPerBank.U
  val responseValid = RegInit(VecInit(Seq.fill(2)(false.B)))
  val rr = RegInit(VecInit(Seq.fill(4)(0.U(2.W))))
  val eligible = VecInit((0 until 2).map(p => io.rd_valid_i(p) && legal(p) && (!responseValid(p) || io.rd_resp_ready_i(p))))
  val grants = Wire(Vec(4, UInt(3.W)))
  for(g <- 0 until 4) {
    val r0 = eligible(0) && groups(0) === g.U
    val r1 = eligible(1) && groups(1) === g.U
    val w = io.wr_valid_i && wlegal && wg === g.U
    grants(g) := 0.U
    switch(rr(g)) {
      is(0.U) { grants(g) := Mux(r0,1.U,Mux(r1,2.U,Mux(w,4.U,0.U))) }
      is(1.U) { grants(g) := Mux(r1,2.U,Mux(w,4.U,Mux(r0,1.U,0.U))) }
      is(2.U) { grants(g) := Mux(w,4.U,Mux(r0,1.U,Mux(r1,2.U,0.U))) }
    }
    when(grants(g)(0)) { rr(g) := 1.U }
    when(grants(g)(1)) { rr(g) := 2.U }
    when(grants(g)(2)) { rr(g) := 0.U }
  }
  val combined = grants.reduce(_ | _)
  val readGrant = combined(1,0); val writeGrant = combined(2)
  io.rd_ready_o := readGrant; io.wr_ready_o := writeGrant
  val groupRead = Wire(Vec(4,UInt(512.W)))
  for(g <- 0 until 4) {
    val re = grants(g)(0) || grants(g)(1)
    val readRow = Mux(grants(g)(0),rows(0),rows(1))
    val banks = (0 until 4).map { lane =>
      val memory = SyncReadMem(cfg.rowsPerBank, Vec(16,UInt(8.W)))
      memory.suggestName(s"bank_${g*4+lane}")
      val read = memory.read(readRow,re)
      when(grants(g)(2)) {
        val data = io.wr_data_i(128*lane+127,128*lane).asTypeOf(Vec(16,UInt(8.W)))
        val mask = (0 until 16).map(b => io.wr_be_i(16*lane+b))
        memory.write(wr,data,mask)
      }
      read.asUInt
    }
    groupRead(g) := Cat(banks.reverse)
  }
  val outputs = Wire(Vec(2,UInt(512.W)))
  for(p <- 0 until 2) {
    val justRead = RegNext(readGrant(p),false.B)
    val returnedGroup = RegEnable(groups(p),0.U(2.W),readGrant(p))
    val held = RegInit(0.U(512.W))
    val fresh = groupRead(returnedGroup)
    when(justRead) { held := fresh }
    outputs(p) := Mux(justRead,fresh,held)
    when(readGrant(p)) { responseValid(p) := true.B }
      .elsewhen(responseValid(p) && io.rd_resp_ready_i(p)) { responseValid(p) := false.B }
  }
  io.rd_resp_valid_o := responseValid.asUInt; io.rd_data_o := outputs.asUInt
  val errors = RegInit(0.U(3.W))
  errors := errors | Cat(io.wr_valid_i && !wlegal, io.rd_valid_i(1) && !legal(1), io.rd_valid_i(0) && !legal(0))
  io.address_error_o := errors
  val cycles = RegInit(0.U(64.W)); val reads = RegInit(0.U(64.W)); val writes = RegInit(0.U(64.W))
  val conflicts = RegInit(0.U(64.W)); val rs = RegInit(0.U(64.W)); val ws = RegInit(0.U(64.W))
  cycles := cycles + 1.U; reads := reads + PopCount(readGrant); writes := writes + writeGrant
  rs := rs + PopCount(io.rd_valid_i & ~readGrant); ws := ws + (io.wr_valid_i && !writeGrant)
  conflicts := conflicts + PopCount(Cat(io.wr_valid_i && wlegal && !writeGrant,eligible(1) && !readGrant(1),eligible(0) && !readGrant(0)))
  io.cycle_count_o := cycles; io.read_count_o := reads; io.write_count_o := writes
  io.bank_conflict_count_o := conflicts; io.read_stall_count_o := rs; io.write_stall_count_o := ws
}
