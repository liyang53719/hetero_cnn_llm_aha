// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

class TransposedActivationLoad extends Bundle {
  val kWord=UInt(7.W);val m=UInt(7.W);val value=UInt(256.W)
}
class TransposedWeightLoad extends Bundle {
  val half=Bool();val depth=UInt(7.W);val group16=UInt(4.W)
  val pair=Bool();val value=UInt(512.W)
}
class TransposedOperandRead extends Bundle {
  val k=UInt(11.W);val context=UInt(3.W);val half=Bool()
}
class TransposedOperandResponse extends Bundle {
  val activation=Vec(128,UInt(16.W));val weight=Vec(32,UInt(16.W))
}

/** Alternative ownership of the EXISTING 688-KiB A / 80-KiB B allocation.
  * Each memory has exactly one synchronous read and one write call per bank.
  * A response is consumed on its reserved next-cycle write edge, without a
  * response register or a downstream-ready condition. The 256-bit RMW payload
  * is the sole FP32-ingress hold. Native BF16 adds one 256-bit upper hold in
  * the owner, for 512 bits total. There is no 4096-bit response-hold register.
  */
class TransposedDenseBanks extends Module {
  val io=IO(new Bundle {
    val zero=Flipped(Valid(UInt(11.W)))
    val activation=Flipped(Decoupled(new TransposedActivationLoad))
    val activationBusy=Output(Bool());val activationWritten=Output(Bool())
    val weight=Flipped(Valid(new TransposedWeightLoad))
    val read=Flipped(Decoupled(new TransposedOperandRead))
    val response=Valid(new TransposedOperandResponse)
  })
  val aBanks=Seq.fill(16)(SyncReadMem(1376,UInt(256.W)))
  val bBanks=Seq.fill(16)(SyncReadMem(160,UInt(256.W)))
  val rmwPending=RegInit(false.B)
  val rmw=Reg(new TransposedActivationLoad)
  val readPending=RegInit(false.B)
  val selected=Reg(new TransposedOperandRead)
  io.activation.ready:= !rmwPending && !io.zero.valid && !io.read.valid
  io.read.ready:= !rmwPending && !io.zero.valid && !io.activation.valid
  val readFire=io.read.fire
  val loadFire=io.activation.fire
  rmwPending:=loadFire;readPending:=readFire
  when(loadFire){rmw:=io.activation.bits}
  when(readFire){selected:=io.read.bits}
  io.activationBusy:=rmwPending
  io.activationWritten:=rmwPending
  io.response.valid:=readPending
  when(io.zero.valid){assert(!rmwPending && !loadFire && !readFire);assert(io.zero.bits<1376.U)}
  when(loadFire){assert(io.activation.bits.kWord<96.U)}
  when(readFire){assert(io.read.bits.k<1536.U && io.read.bits.context<5.U)}

  val gatherK=io.read.bits.k
  val aOut=(0 until 16).map { bank =>
    val mt=gatherK(3,0)^bank.U(4.W)
    val gatherAddress=Cat(gatherK(10,4),0.U(3.W))+mt
    val loadAddress=Cat(io.activation.bits.kWord,0.U(3.W))+io.activation.bits.m(6,4)
    val readEnable=loadFire || (readFire && mt<8.U)
    val address=Mux(loadFire,loadAddress,gatherAddress)
    val response=aBanks(bank).read(address,readEnable)
    val merged=Wire(Vec(16,UInt(16.W)))
    merged:=response.asTypeOf(Vec(16,UInt(16.W)))
    val laneValue=rmw.value.asTypeOf(Vec(16,UInt(16.W)))
    merged(rmw.m(3,0)):=laneValue(bank.U(4.W)^rmw.m(6,4))
    val writeAddress=Mux(io.zero.valid,io.zero.bits,Cat(rmw.kWord,0.U(3.W))+rmw.m(6,4))
    when(io.zero.valid || rmwPending){
      aBanks(bank).write(writeAddress,Mux(io.zero.valid,0.U(256.W),merged.asUInt))
    }
    response
  }
  val aReadVector=VecInit(aOut)
  for(mt<-0 until 8;lane<-0 until 16){
    val bank=selected.k(3,0)^mt.U(4.W)
    io.response.bits.activation(mt*16+lane):=aReadVector(bank)(lane*16+15,lane*16)
  }

  def linear(half:Bool,depth:UInt,group:UInt):UInt=
    Mux(half,1280.U(12.W),0.U(12.W))+depth.pad(12)*10.U+group.pad(12)
  val rd0=linear(io.read.bits.half,io.read.bits.k(6,0),io.read.bits.context.pad(4)<<1)
  val rd1=rd0+1.U
  val wr0=linear(io.weight.bits.half,io.weight.bits.depth,io.weight.bits.group16)
  val wr1=wr0+1.U
  when(io.weight.valid){
    assert(io.weight.bits.group16<10.U)
    when(io.weight.bits.pair){assert(!io.weight.bits.group16(0) && io.weight.bits.group16<9.U)}
  }
  val bOut=(0 until 16).map { bank =>
    val first=rd0(3,0)===bank.U
    val readEnable=readFire && (first || rd1(3,0)===bank.U)
    val address=Mux(first,rd0>>4,rd1>>4)
    val response=bBanks(bank).read(address,readEnable)
    val writeFirst=wr0(3,0)===bank.U
    val writeEnable=io.weight.valid && (writeFirst || (io.weight.bits.pair && wr1(3,0)===bank.U))
    val writeAddress=Mux(writeFirst,wr0>>4,wr1>>4)
    val writeValue=Mux(writeFirst,io.weight.bits.value(255,0),io.weight.bits.value(511,256))
    when(writeEnable){
      assert(writeAddress<160.U)
      assert(!(readEnable && address===writeAddress),"B half reused while a synchronous read owns it")
      bBanks(bank).write(writeAddress,writeValue)
    }
    response
  }
  val bReadVector=VecInit(bOut)
  val selectedLinear=linear(selected.half,selected.k(6,0),selected.context.pad(4)<<1)
  for(n<-0 until 32){
    val bank=(selectedLinear+(n/16).U)(3,0)
    io.response.bits.weight(n):=bReadVector(bank)(16*(n%16)+15,16*(n%16))
  }
}
