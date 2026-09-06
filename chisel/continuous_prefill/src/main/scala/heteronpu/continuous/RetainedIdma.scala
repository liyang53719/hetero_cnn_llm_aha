// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

/** Packed ABI of unchanged idma_backend_rw_axi_flat_wrap and pinned AXI typedefs.
  * Field order is intentionally identical to axi/typedef.svh (first is MSB).
  * 64-bit address, 512-bit data, 4-bit ID, 1-bit user. Do not silently resize.
  */
class IdmaAw extends Bundle {
  val id=UInt(4.W);val addr=UInt(64.W);val len=UInt(8.W);val size=UInt(3.W);val burst=UInt(2.W)
  val lock=Bool();val cache=UInt(4.W);val prot=UInt(3.W);val qos=UInt(4.W);val region=UInt(4.W);val atop=UInt(6.W);val user=Bool()
}
class IdmaAr extends Bundle {
  val id=UInt(4.W);val addr=UInt(64.W);val len=UInt(8.W);val size=UInt(3.W);val burst=UInt(2.W)
  val lock=Bool();val cache=UInt(4.W);val prot=UInt(3.W);val qos=UInt(4.W);val region=UInt(4.W);val user=Bool()
}
class IdmaW extends Bundle {val data=UInt(512.W);val strb=UInt(64.W);val last=Bool();val user=Bool()}
class IdmaB extends Bundle {val id=UInt(4.W);val resp=UInt(2.W);val user=Bool()}
class IdmaR extends Bundle {val id=UInt(4.W);val data=UInt(512.W);val resp=UInt(2.W);val last=Bool();val user=Bool()}
class IdmaAxiRequest extends Bundle {
  val aw=new IdmaAw;val aw_valid=Bool();val w=new IdmaW;val w_valid=Bool();val b_ready=Bool()
  val ar=new IdmaAr;val ar_valid=Bool();val r_ready=Bool()
}
class IdmaAxiResponse extends Bundle {
  val aw_ready=Bool();val ar_ready=Bool();val w_ready=Bool();val b_valid=Bool();val b=new IdmaB
  val r_valid=Bool();val r=new IdmaR
}
class RetainedIdmaBackend extends BlackBox {
  override def desiredName="idma_backend_rw_axi_flat_wrap"
  val io=IO(new Bundle {
    val clk_i=Input(Clock());val rst_ni=Input(Bool())
    val req_valid_i=Input(Bool());val req_ready_o=Output(Bool())
    val src_addr_i=Input(UInt(64.W));val dst_addr_i=Input(UInt(64.W));val length_i=Input(UInt(32.W))
    val rsp_valid_o=Output(Bool());val rsp_ready_i=Input(Bool());val rsp_error_o=Output(Bool())
    val axi_read_req_o=Output(UInt(785.W));val axi_read_rsp_i=Input(UInt(532.W))
    val axi_write_req_o=Output(UInt(785.W));val axi_write_rsp_i=Input(UInt(532.W));val busy_o=Output(UInt(8.W))
  })
}
/** A 64-byte mailbox makes MemoryRequest a real iDMA transfer, not direct AXI.
  * Read: DDR -> iDMA -> local AXI write mailbox. Write: local AXI read mailbox
  * -> iDMA -> DDR. Every byte crosses the unchanged pinned backend. No host
  * arithmetic, no completion echo. Writes return only after actual external B.
  * One transfer in flight; prefix byte masks only. Unsupported masks fail closed.
  */
class RetainedIdmaMemoryAdapter extends Module {
  val io=IO(new Bundle {
    val request=Flipped(Decoupled(new MemoryRequest));val response=Decoupled(new MemoryResponse)
    val axi=new BlockAxiMaster;val resetRequired=Output(Bool())
    val transfers=Output(UInt(64.W));val readBeats=Output(UInt(64.W));val writeBeats=Output(UInt(64.W))
  })
  val idle::issue::waitDma::reply::locked::Nil=Enum(5)
  val state=RegInit(idle);val req=Reg(new MemoryRequest);val rsp=Reg(new MemoryResponse)
  val poison=RegInit(false.B);val fault=RegInit(false.B)
  val localAw=RegInit(false.B);val localW=RegInit(false.B);val localR=RegInit(false.B)
  val localId=Reg(UInt(4.W));val payload=Reg(UInt(512.W));val localDone=RegInit(false.B)
  val externalDone=RegInit(false.B);val extId=Reg(UInt(8.W))
  val transfers=RegInit(0.U(64.W));val reads=RegInit(0.U(64.W));val writes=RegInit(0.U(64.W))
  io.transfers:=transfers;io.readBeats:=reads;io.writeBeats:=writes
  val bb=Module(new RetainedIdmaBackend);val d=bb.io
  val rr=d.axi_read_req_o.asTypeOf(new IdmaAxiRequest)
  val wr=d.axi_write_req_o.asTypeOf(new IdmaAxiRequest)
  val rs=WireDefault(0.U.asTypeOf(new IdmaAxiResponse))
  val ws=WireDefault(0.U.asTypeOf(new IdmaAxiResponse))
  require(rr.getWidth==785 && rs.getWidth==532)
  d.clk_i:=clock;d.rst_ni:= !reset.asBool
  d.req_valid_i:=state===issue;d.src_addr_i:=Mux(req.write,0.U,req.address)
  d.dst_addr_i:=Mux(req.write,req.address,0.U)
  d.length_i:=Mux(req.write,PopCount(req.mask),64.U)
  d.rsp_ready_i:=state===waitDma&&localDone&&externalDone
  d.axi_read_rsp_i:=rs.asUInt;d.axi_write_rsp_i:=ws.asUInt
  io.request.ready:=state===idle && !poison;io.response.valid:=state===reply;io.response.bits:=rsp
  io.resetRequired:=poison
  io.axi.aw.valid:=false.B;io.axi.aw.bits:=0.U.asTypeOf(new BlockAxiAddress)
  io.axi.ar.valid:=false.B;io.axi.ar.bits:=0.U.asTypeOf(new BlockAxiAddress)
  io.axi.w.valid:=false.B;io.axi.w.bits:=0.U.asTypeOf(new BlockAxiWrite)
  io.axi.r.ready:=false.B;io.axi.b.ready:=false.B
  val active=state===issue||state===waitDma
  when(active){
    when(req.write){
      // iDMA source is the local AXI mailbox; address=0, exactly one beat.
      rs.ar_ready:= !localR && !localDone
      rs.r_valid:=localR;rs.r.id:=localId;rs.r.data:=req.data;rs.r.last:=true.B
      rs.r.resp:=Mux(fault,3.U,0.U)
      when(rr.ar_valid&&rs.ar_ready){localR:=true.B;localId:=rr.ar.id
        when(rr.ar.addr=/=0.U||rr.ar.len=/=0.U||rr.ar.size>6.U){fault:=true.B}}
      when(rs.r_valid&&rr.r_ready){localR:=false.B;localDone:=true.B}
      io.axi.aw.valid:=wr.aw_valid
      io.axi.aw.bits.addr:=wr.aw.addr;io.axi.aw.bits.id:=wr.aw.id;io.axi.aw.bits.len:=wr.aw.len
      io.axi.aw.bits.size:=wr.aw.size;io.axi.aw.bits.burst:=wr.aw.burst
      io.axi.w.valid:=wr.w_valid;io.axi.w.bits.data:=wr.w.data;io.axi.w.bits.strb:=wr.w.strb;io.axi.w.bits.last:=wr.w.last
      io.axi.b.ready:=wr.b_ready
      ws.aw_ready:=io.axi.aw.ready;ws.w_ready:=io.axi.w.ready
      ws.b_valid:=io.axi.b.valid;ws.b.id:=extId(3,0)
      val bid=Mux(io.axi.aw.fire,io.axi.aw.bits.id,extId)
      ws.b.id:=bid(3,0)
      ws.b.resp:=Mux(io.axi.b.bits.id=/=bid,3.U,io.axi.b.bits.resp)
      when(io.axi.aw.fire){extId:=io.axi.aw.bits.id}
      when(io.axi.w.fire){writes:=writes+1.U}
      when(io.axi.b.fire){externalDone:=true.B
        when(io.axi.b.bits.resp=/=0.U||io.axi.b.bits.id=/=bid){fault:=true.B}}
    }.otherwise{
      io.axi.ar.valid:=rr.ar_valid
      io.axi.ar.bits.addr:=rr.ar.addr;io.axi.ar.bits.id:=rr.ar.id;io.axi.ar.bits.len:=rr.ar.len
      io.axi.ar.bits.size:=rr.ar.size;io.axi.ar.bits.burst:=rr.ar.burst
      io.axi.r.ready:=rr.r_ready
      rs.ar_ready:=io.axi.ar.ready;rs.r_valid:=io.axi.r.valid
      rs.r.data:=io.axi.r.bits.data;rs.r.last:=true.B // strict single-beat request: terminate bad LAST as an error
      val rid=Mux(io.axi.ar.fire,io.axi.ar.bits.id,extId)
      rs.r.id:=rid(3,0)
      rs.r.resp:=Mux(io.axi.r.bits.id=/=rid || !io.axi.r.bits.last,3.U,io.axi.r.bits.resp)
      when(io.axi.ar.fire){extId:=io.axi.ar.bits.id}
      when(io.axi.r.fire){reads:=reads+1.U;externalDone:=true.B
        when(io.axi.r.bits.resp=/=0.U||io.axi.r.bits.id=/=rid|| !io.axi.r.bits.last){fault:=true.B}}
      ws.aw_ready:= !localAw && !localDone;ws.w_ready:= !localW && !localDone
      ws.b_valid:=localAw&&localW;ws.b.id:=localId;ws.b.resp:=Mux(fault,3.U,0.U)
      when(wr.aw_valid&&ws.aw_ready){localAw:=true.B;localId:=wr.aw.id
        when(wr.aw.addr=/=0.U||wr.aw.len=/=0.U||wr.aw.size=/=6.U){fault:=true.B}}
      when(wr.w_valid&&ws.w_ready){localW:=true.B;payload:=wr.w.data
        when(!wr.w.last || !wr.w.strb.andR){fault:=true.B}}
      when(ws.b_valid&&wr.b_ready){localAw:=false.B;localW:=false.B;localDone:=true.B}
    }
  }
  when(io.request.fire){
    req:=io.request.bits;rsp.tag:=io.request.bits.tag;rsp.data:=0.U;rsp.error:=false.B
    localAw:=false.B;localW:=false.B;localR:=false.B;localDone:=false.B;externalDone:=false.B;fault:=false.B
    val x=io.request.bits
    val prefix=x.mask=/=0.U && (x.mask & (x.mask+1.U))===0.U
    when(x.address(5,0)=/=0.U||x.address.pad(66)+64.U>(BigInt(1)<<56).U || (x.write && !prefix)){
      rsp.error:=true.B;poison:=true.B;state:=reply
    }.otherwise{state:=issue}
  }
  when(state===issue&&d.req_ready_o){transfers:=transfers+1.U;state:=waitDma}
  when(state===waitDma&&d.rsp_valid_o&&d.rsp_ready_i){
    rsp.data:=Mux(req.write,0.U,payload);rsp.error:=fault||d.rsp_error_o
    poison:=fault||d.rsp_error_o;state:=reply
  }
  when(state===reply&&io.response.fire){state:=Mux(poison,locked,idle)}
}
class Qwen2IdmaBlockTop(s:QwenBlockShape=QwenBlockShape(retainedMatrix=true)) extends Module {
  require(s.retainedMatrix,"production transport gate requires the retained array")
  val block=Module(new Qwen2ContinuousBlock(s));val dma=Module(new RetainedIdmaMemoryAdapter)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new BlockLaunch));val result=Decoupled(new BlockResult);val axi=new BlockAxiMaster
    val phase=Output(UInt(5.W));val stageCommit=Output(Bool());val committedPhase=Output(UInt(5.W));val resetRequired=Output(Bool())
    val readBytes=Output(UInt(64.W));val writeBytes=Output(UInt(64.W));val idmaTransfers=Output(UInt(64.W))
  })
  dontTouch(io)
  block.io.launch<>io.launch;io.result<>block.io.result
  dma.io.request<>block.io.memory;block.io.response<>dma.io.response;io.axi<>dma.io.axi
  io.phase:=block.io.phase;io.stageCommit:=block.io.stageCommit;io.committedPhase:=block.io.committedPhase
  io.resetRequired:=block.io.resetRequired||dma.io.resetRequired
  io.readBytes:=block.io.readBytes;io.writeBytes:=block.io.writeBytes;io.idmaTransfers:=dma.io.transfers
}
