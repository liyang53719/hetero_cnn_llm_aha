// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import heteronpu.p0.{LocalSramConfig,SharedL2Fabric}
import gemmini.HeteroFP32Alu

/** Actual tiled DDR -> shared SRAM -> FP32 add/mul/copy -> DDR owner.
  * One outstanding memory request. A write response means globally visible data,
  * not merely AXI AW/W acceptance. Failed tensors remain unpublished.
  * All tiles use three bounded canonical FP32 buffers in the retained P0 fabric.
  * BF16 is expanded exactly at ingress and rounded RNE only at output.
  */
class ElementwiseMemoryEngine(c:ChainConfig=ChainConfig(),sram:LocalSramConfig=LocalSramConfig()) extends Module {
  require(BigInt(c.localBytes)<=sram.bytes)
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new BoundJob));val done=Decoupled(new JobResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val cycles=Output(UInt(64.W));val readBytes=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
    val resetRequired=Output(Bool());val localAddressError=Output(UInt(3.W))
  })
  val idle::loadReq::loadRsp::loadStore::calcRead::calcWait::calculate::calcStore::outReq0::outRsp0::outReq1::outRsp1::writeReq::writeRsp::finish::locked::Nil=Enum(16)
  val state=RegInit(idle);val job=Reg(new BoundJob);val status=RegInit(0.U(8.W));val poison=RegInit(false.B)
  val base=RegInit(0.U(32.W));val tile=RegInit(0.U(32.W));val loadIndex=RegInit(0.U(32.W));val loadB=RegInit(false.B)
  val calcIndex=RegInit(0.U(32.W));val outIndex=RegInit(0.U(32.W));val raw=Reg(UInt(512.W))
  val a=Reg(UInt(512.W));val b=RegInit(0.U(512.W));val value=Reg(UInt(512.W));val packet=RegInit(0.U(512.W))
  val sent=RegInit(0.U(2.W));val got=RegInit(0.U(2.W))
  val seq=RegInit(0.U(32.W));val expectedTag=Reg(UInt(64.W))
  val cycles=RegInit(0.U(64.W));val reads=RegInit(0.U(64.W));val writes=RegInit(0.U(64.W));val elementCount=RegInit(0.U(32.W))
  val fabric=Module(new SharedL2Fabric(sram));val f=fabric.io
  f.rd_valid_i:=0.U;f.rd_addr_i:=0.U;f.rd_resp_ready_i:=0.U
  f.wr_valid_i:=false.B;f.wr_addr_i:=0.U;f.wr_data_i:=0.U;f.wr_be_i:=0.U
  io.localAddressError:=f.address_error_o
  io.job.ready:=state===idle && !poison
  io.done.valid:=state===finish;io.done.bits.tag:=job.tag;io.done.bits.status:=status
  io.done.bits.elementCount:=elementCount;io.done.bits.writeBytes:=writes
  io.resetRequired:=poison;io.cycles:=cycles;io.readBytes:=reads;io.writeBytes:=writes
  io.memory.valid:=false.B;io.memory.bits:=0.U.asTypeOf(new MemoryRequest)
  io.memory.bits.tag:=Cat(job.tag,seq)
  io.response.ready:=state===loadRsp || state===writeRsp
  val binary=job.op=/=ElemOp.Copy.U
  val short= Mux(loadB,job.bBf16,job.aBf16)
  val source= Mux(loadB,job.b,job.a)
  val loadOffset=base+loadIndex
  val secondHalf=short && loadOffset(4)
  val localLoad=((Mux(loadB,c.bBeat.U,c.aBeat.U))+(loadIndex>>4))(sram.addressBits-1,0)
  val localOut=(c.cBeat.U+(outIndex>>4))(sram.addressBits-1,0)
  val loadData=Wire(Vec(16,UInt(32.W)))
  for(i<-0 until 16) {
    val lo=raw(16*i+15,16*i); val hi=raw(256+16*i+15,256+16*i)
    loadData(i):=Mux(loadIndex+i.U<tile,Mux(short,Cat(Mux(secondHalf,hi,lo),0.U(16.W)),raw(32*i+31,32*i)),0.U)
  }
  val aluResults=Wire(Vec(16,UInt(32.W)));val aluBad=Wire(Vec(16,Bool()))
  for(i<-0 until 16) {
    val alu=Module(new HeteroFP32Alu)
    alu.io.op:=job.op===ElemOp.Mul.U;alu.io.x:=a(32*i+31,32*i);alu.io.y:=b(32*i+31,32*i)
    aluResults(i):=Mux(calcIndex+i.U<tile,Mux(binary,alu.io.out,a(32*i+31,32*i)),0.U)
    aluBad(i):=calcIndex+i.U<tile && (!TensorMath.finite(aluResults(i)) || (binary && alu.io.exceptionFlags(4,1).orR))
  }
  def bfPack(w:UInt):UInt=Cat((0 until 16).reverse.map(i=>TensorMath.bf16Rne(w(32*i+31,32*i))))
  val outputStride=Mux(job.dstBf16,32.U,16.U)
  val outputElements=Mux(tile-outIndex>outputStride,outputStride,tile-outIndex)
  val outputBytes=outputElements << Mux(job.dstBf16,1.U,2.U)
  val writeMask=VecInit((0 until 64).map(i=>i.U<outputBytes)).asUInt
  def fail(code:UInt):Unit={status:=code;poison:=true.B;state:=finish}
  def nextTile():Unit={
    val next=base+tile
    base:=next;tile:=Mux(job.elementCount-next>c.tileElements.U,c.tileElements.U,job.elementCount-next)
    loadIndex:=0.U;loadB:=false.B;state:=loadReq
  }
  when(state=/=idle && state=/=finish && state=/=locked) {cycles:=cycles+1.U}
  when(io.memory.fire) {expectedTag:=io.memory.bits.tag;seq:=seq+1.U}
  val rspBad=io.response.bits.error || io.response.bits.tag=/=expectedTag || f.address_error_o.orR
  val rspCode=Mux(io.response.bits.tag=/=expectedTag,Status.Protocol.U,Status.Memory.U)
  switch(state) {
    is(idle) {when(io.job.fire) {
      job:=io.job.bits;status:=0.U;cycles:=0.U;reads:=0.U;writes:=0.U;elementCount:=0.U;seq:=0.U
      base:=0.U;tile:=Mux(io.job.bits.elementCount>c.tileElements.U,c.tileElements.U,io.job.bits.elementCount)
      loadIndex:=0.U;loadB:=false.B;state:=loadReq
      val j=io.job.bits
      def end(addr:UInt,s:Bool):UInt=addr.pad(66)+(((j.elementCount.pad(66)<<Mux(s,1.U,2.U))+63.U)>>6<<6)
      when(j.elementCount===0.U||j.op>ElemOp.Mul.U) {fail(Status.Unsupported.U)}
      .elsewhen(j.a(5,0)=/=0.U||j.dst(5,0)=/=0.U || (j.op=/=ElemOp.Copy.U&&j.b(5,0)=/=0.U) ||
        end(j.a,j.aBf16)>(BigInt(1)<<56).U || end(j.dst,j.dstBf16)>(BigInt(1)<<56).U ||
        (j.op=/=ElemOp.Copy.U&&end(j.b,j.bBf16)>(BigInt(1)<<56).U)) {fail(Status.Bounds.U)}
    }}
    is(loadReq) {
      // Adjacent canonical chunks share one packed BF16 DDR beat.
      when(secondHalf && loadIndex=/=0.U) {state:=loadStore}.otherwise {
        io.memory.valid:=true.B;io.memory.bits.address:=((source+(loadOffset.pad(64)<<Mux(short,1.U,2.U)))>>6)<<6
        when(io.memory.fire) {state:=loadRsp}
      }
    }
    is(loadRsp) {when(io.response.fire) {
      when(rspBad) {fail(rspCode)}.otherwise {raw:=io.response.bits.data;reads:=reads+64.U;state:=loadStore}
    }}
    is(loadStore) {
      f.wr_valid_i:=true.B;f.wr_addr_i:=localLoad;f.wr_data_i:=loadData.asUInt;f.wr_be_i:=Fill(64,1.U(1.W))
      when(f.wr_ready_o) {
        when(loadIndex+16.U>=tile) {
          when(!loadB&&binary) {loadB:=true.B;loadIndex:=0.U;state:=loadReq}
            .otherwise {calcIndex:=0.U;sent:=0.U;got:=Mux(binary,0.U,2.U);b:=0.U;state:=calcRead}
        }.otherwise {loadIndex:=loadIndex+16.U;state:=loadReq}
      }
    }
    is(calcRead) {
      f.rd_valid_i:=Cat(binary && !sent(1),!sent(0))
      f.rd_addr_i:=Cat((c.bBeat.U+(calcIndex>>4))(sram.addressBits-1,0),(c.aBeat.U+(calcIndex>>4))(sram.addressBits-1,0))
      sent:=sent | (f.rd_valid_i & f.rd_ready_o)
      when(((sent | (f.rd_valid_i & f.rd_ready_o)) | Mux(binary,0.U,2.U))===3.U) {state:=calcWait}
    }
    is(calcWait) {when(got===3.U) {state:=calculate}}
    is(calculate) {
      when(aluBad.asUInt.orR) {fail(Status.Numerical.U)}.otherwise {value:=aluResults.asUInt;state:=calcStore}
    }
    is(calcStore) {
      f.wr_valid_i:=true.B;f.wr_addr_i:=(c.cBeat.U+(calcIndex>>4));f.wr_data_i:=value;f.wr_be_i:=Fill(64,1.U(1.W))
      when(f.wr_ready_o) {
        when(calcIndex+16.U>=tile) {outIndex:=0.U;state:=outReq0}
          .otherwise {calcIndex:=calcIndex+16.U;sent:=0.U;got:=Mux(binary,0.U,2.U);state:=calcRead}
      }
    }
    is(outReq0) {f.rd_valid_i:=1.U;f.rd_addr_i:=localOut;when(f.rd_ready_o(0)) {state:=outRsp0}}
    is(outRsp0) {
      f.rd_resp_ready_i:=1.U
      when(f.rd_resp_valid_o(0)) {
        packet:=Mux(job.dstBf16,bfPack(f.rd_data_o(511,0)).pad(512),f.rd_data_o(511,0))
        when(job.dstBf16&&outIndex+16.U<tile) {state:=outReq1}.otherwise {state:=writeReq}
      }
    }
    is(outReq1) {f.rd_valid_i:=1.U;f.rd_addr_i:=localOut+1.U;when(f.rd_ready_o(0)) {state:=outRsp1}}
    is(outRsp1) {f.rd_resp_ready_i:=1.U;when(f.rd_resp_valid_o(0)) {packet:=Cat(bfPack(f.rd_data_o(511,0)),packet(255,0));state:=writeReq}}
    is(writeReq) {
      val nonfiniteBf=(0 until 32).map(i=>i.U<outputElements&&packet(i*16+14,i*16+7)===255.U).reduce(_||_)
      when(job.dstBf16&&nonfiniteBf) {fail(Status.Numerical.U)}.otherwise {
        io.memory.valid:=true.B;io.memory.bits.write:=true.B
        io.memory.bits.address:=job.dst+((base+outIndex).pad(64)<<Mux(job.dstBf16,1.U,2.U))
        io.memory.bits.data:=packet;io.memory.bits.mask:=writeMask
        when(io.memory.fire) {state:=writeRsp}
      }
    }
    is(writeRsp) {when(io.response.fire) {
      when(rspBad) {fail(rspCode)}.otherwise {
        writes:=writes+outputBytes
        when(outIndex+outputStride>=tile) {
          when(base+tile===job.elementCount) {elementCount:=job.elementCount;state:=finish}.otherwise {nextTile()}
        }.otherwise {outIndex:=outIndex+outputStride;state:=outReq0}
      }
    }}
    is(finish) {when(io.done.fire) {state:=Mux(poison,locked,idle)}}
    is(locked) {}
  }
  when(state===calcRead||state===calcWait) {
    f.rd_resp_ready_i:= ~got
    val fires=f.rd_resp_valid_o & f.rd_resp_ready_i
    got:=got | fires
    when(fires(0)) {a:=f.rd_data_o(511,0)}
    when(fires(1)) {b:=f.rd_data_o(1023,512)}
  }
  // A local fault cannot be ignored. Do not withdraw an offered DDR request or
  // forget an accepted request: response states still drain that one request.
  when(f.address_error_o.orR&&state=/=idle&&state=/=finish&&state=/=locked&&
    state=/=loadReq&&state=/=loadRsp&&state=/=writeReq&&state=/=writeRsp) {fail(Status.Bounds.U)}
}

class ContinuousElementwiseTop(c:ChainConfig=ChainConfig(),sram:LocalSramConfig=LocalSramConfig()) extends Module {
  val controller=Module(new TensorProgram(c));val engine=Module(new ElementwiseMemoryEngine(c,sram))
  val io=IO(new Bundle {
    val regionWrite=Flipped(Decoupled(new RegionWrite))
    val tensorWrite=Flipped(Decoupled(new TensorWrite(c)))
    val programWrite=Flipped(Decoupled(new ProgramWrite(c)))
    val launch=Flipped(Decoupled(new Launch));val result=Decoupled(new ChainResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val busy=Output(Bool());val resetRequired=Output(Bool());val committed=Output(Bool())
    val committedTensor=Output(UInt(c.tensorBits.W));val committedVersion=Output(UInt(16.W))
  })
  controller.io.regionWrite <> io.regionWrite
  controller.io.tensorWrite <> io.tensorWrite
  controller.io.programWrite <> io.programWrite
  controller.io.launch <> io.launch;io.result <> controller.io.result
  engine.io.job <> controller.io.job;controller.io.done <> engine.io.done
  io.memory <> engine.io.memory;engine.io.response <> io.response
  io.busy:=controller.io.busy;io.resetRequired:=controller.io.resetRequired||engine.io.resetRequired
  io.committed:=controller.io.committed;io.committedTensor:=controller.io.committedTensor;io.committedVersion:=controller.io.committedVersion
}
