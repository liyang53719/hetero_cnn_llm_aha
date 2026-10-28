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

/** Selected Down bank port widths; original default bank source remains exact. */
class TransposedDownActivationLoad extends Bundle {
  val kWord=UInt(8.W);val m=UInt(7.W);val value=UInt(256.W)
}
class TransposedDownWeightLoad extends Bundle {
  val half=Bool();val depth=UInt(7.W);val group16=UInt(4.W)
  val pair=Bool();val value=UInt(512.W)
}
class TransposedDownOperandRead extends Bundle {
  val k=UInt(12.W);val context=UInt(3.W);val half=Bool()
}
class TransposedDownOperandResponse extends Bundle {
  val activation=Vec(128,UInt(16.W));val weight=Vec(32,UInt(16.W))
}

/** Alternative ownership of the EXISTING 688-KiB A / 80-KiB B allocation.
  * Each memory has exactly one synchronous read and one write call per bank.
  * A response is consumed on its reserved next-cycle write edge, without a
  * response register or a downstream-ready condition. The 256-bit RMW payload
  * is the sole FP32-ingress hold. Native BF16 adds one 256-bit upper hold in
  * the owner, for 512 bits total. There is no 4096-bit response-hold register.
  */
class TransposedDownDenseBanks(enableFfnTiles:Boolean=false,enableMatrixProducerOrder:Boolean=false) extends Module {
  val io=IO(new Bundle {
    val zero=Flipped(Valid(UInt(11.W)))
    val tiles=if(enableFfnTiles)Some(new FfnTilePort(enableMatrixProducerOrder))else None
    val tileEnable=if(enableFfnTiles)Some(Input(Bool()))else None
    val activation=Flipped(Decoupled(new TransposedDownActivationLoad))
    val activationBusy=Output(Bool());val activationWritten=Output(Bool())
    val weight=Flipped(Valid(new TransposedDownWeightLoad))
    val read=Flipped(Decoupled(new TransposedDownOperandRead))
    val response=Valid(new TransposedDownOperandResponse)
  })
  val aBanks=Seq.fill(16)(SyncReadMem(1376,UInt(256.W)))
  val bBanks=Seq.fill(16)(SyncReadMem(160,UInt(256.W)))
  val rmwPending=RegInit(false.B)
  val rmw=Reg(new TransposedDownActivationLoad)
  val readPending=RegInit(false.B)
  val selected=Reg(new TransposedDownOperandRead)
  val tileSignals=if(enableFfnTiles)Some(Wire(new FfnTileBankSignals))else None
  if(enableFfnTiles){
    val p=io.tiles.get;val x=tileSignals.get
    val tags=RegInit(0.U.asTypeOf(Vec(3,new FfnTileState(enableMatrixProducerOrder))))
    val poison=RegInit(false.B)
    val pendingWrite=RegInit(false.B);val pendingRead=RegInit(false.B)
    val responseValid=RegInit(false.B);val responseError=RegInit(false.B)
    val selectedTile=Reg(new FfnTileIndex)
    val writeValue=Reg(Vec(16,UInt(32.W)))
    val responseValue=Reg(Vec(16,UInt(32.W)))
    val occupied=tags.map(_.live).reduce(_||_)
    val outstanding=pendingWrite || pendingRead || responseValid
    val quiet= !rmwPending && !readPending && !outstanding && !io.zero.valid &&
      !io.activation.valid && !io.read.valid
    val admit=io.tileEnable.get && quiet && !poison && !p.abort
    p.control.ready:=admit
    p.write.ready:=admit && !p.control.valid
    p.read.ready:=admit && !p.control.valid && !p.write.valid
    p.response.valid:=responseValid
    p.response.bits.key:=selectedTile;p.response.bits.value:=responseValue;p.response.bits.error:=responseError
    p.busy:=outstanding || poison || p.abort;p.leased:=occupied
    p.drained:= !outstanding
    p.resetRequired:=poison
    p.state:=tags
    x.busy:=p.busy;x.leased:=occupied;x.issueRead:=false.B;x.issueWrite:=false.B
    x.commit:=pendingWrite;x.word:=0.U;x.lane:=0.U
    x.commitWord:=768.U+selectedTile.slot*160.U+(selectedTile.index/tags(selectedTile.slot).cols)*20.U+
      (selectedTile.index%tags(selectedTile.slot).cols)/8.U
    x.commitLane:=(selectedTile.index%tags(selectedTile.slot).cols)(2,0)
    x.writeValue:=writeValue
    pendingWrite:=false.B;pendingRead:=false.B
    when(pendingWrite){tags(selectedTile.slot).produced:=tags(selectedTile.slot).produced+1.U}
    when(pendingRead){
      val returned=Wire(Vec(16,UInt(32.W)))
      for(b<-0 until 16){returned(b):=(x.readWords(b)>>(x.commitLane<<5))(31,0)}
      val nonfinite=returned.map(v=>v(30,23)===255.U).reduce(_||_)
      responseValue:=returned
      when(nonfinite){poison:=true.B}
      responseValid:=true.B;responseError:=poison || p.abort || nonfinite
    }
    when(p.response.fire){
      tags(selectedTile.slot).consumed:=tags(selectedTile.slot).consumed+1.U
      responseValid:=false.B
    }
    def matching(key:FfnTileIndex):Bool=key.slot<3.U && tags(key.slot).live &&
      key.identity===tags(key.slot).identity && key.ng===tags(key.slot).ng
    when(p.control.fire){
      val c=p.control.bits;val t=tags(c.slot)
      val extent=(c.rows>>4)*c.cols
      val identity=c.slot<3.U && t.live && t.identity===c.identity && t.ng===c.ng && t.rows===c.rows && t.cols===c.cols
      val beginOK=c.slot<3.U && c.identity=/=0.U && c.ng(4,0)===0.U && !t.live && (c.rows===16.U || c.rows===128.U) &&
        c.cols>0.U && c.cols<=160.U && c.cols(4,0)===0.U
      val orderOK=if(enableMatrixProducerOrder)!c.matrixProducerOrder.get || c.slot<2.U else true.B
      when(if(enableMatrixProducerOrder)c.op===0.U && beginOK && orderOK else c.op===0.U && beginOK){
        t.live:=true.B;t.sealedTile:=false.B;t.identity:=c.identity;t.ng:=c.ng
        if(enableMatrixProducerOrder){t.matrixProducerOrder.get:=c.matrixProducerOrder.get}
        t.rows:=c.rows;t.cols:=c.cols;t.expected:=extent;t.produced:=0.U;t.consumed:=0.U
      }.elsewhen(c.op===1.U && identity && !t.sealedTile && t.produced===t.expected){
        t.sealedTile:=true.B
      }.elsewhen(c.op===2.U && identity && t.sealedTile && t.consumed===t.expected){
        t.live:=false.B;t.sealedTile:=false.B
      }.otherwise{poison:=true.B}
    }
    val key=Mux(p.write.valid,p.write.bits.key,p.read.bits)
    val tag=tags(key.slot)
    val writeFinite=p.write.bits.value.map(v=>v(30,23)=/=255.U).reduce(_&&_)
    // Physical Matrix results arrive context-major; sealed readers stay linear.
    // rows is exactly 16 or 128, so q/(32*R) and q%(32*R) use only bit slices.
    val writeOK=if(enableMatrixProducerOrder){
    val producerContext=Mux(tag.rows===16.U,tag.produced>>5,tag.produced>>8)
    val producerGroup=Mux(tag.rows===16.U,0.U(3.W),tag.produced(7,5))
    val producerIndex=producerGroup*tag.cols+(producerContext<<5)+tag.produced(4,0)
    val expectedWriteIndex=Mux(tag.matrixProducerOrder.get,producerIndex,tag.produced)
    matching(key) && !tag.sealedTile && key.index===expectedWriteIndex && key.index<tag.expected && writeFinite
    }else matching(key) && !tag.sealedTile && key.index===tag.produced && key.index<tag.expected && writeFinite
    val readOK=matching(key) && tag.sealedTile && key.index===tag.consumed && key.index<tag.expected
    when(p.write.fire || p.read.fire){
      when(Mux(p.write.fire,writeOK,readOK)){
        selectedTile:=key
        val n=key.index%tag.cols;val rowGroup=key.index/tag.cols
        x.word:=768.U+key.slot*160.U+rowGroup*20.U+n/8.U;x.lane:=n(2,0)
        x.issueRead:=p.read.fire;x.issueWrite:=p.write.fire
        pendingWrite:=p.write.fire;pendingRead:=p.read.fire
        when(p.write.fire){writeValue:=p.write.bits.value}
      }.otherwise{poison:=true.B}
    }
    // Poison does not retract a held response or cancel a reserved RMW edge.
    when(p.abort){poison:=true.B}
    when(io.zero.valid){
      assert(!outstanding,"clear cannot steal an accepted tile transaction")
      when(occupied && io.zero.bits>=768.U){poison:=true.B}
    }
    when(occupied && ((io.activation.valid && io.activation.bits.kWord>=96.U) ||
      (io.read.valid && io.read.bits.k>=1536.U))){poison:=true.B}
  }
  io.activation.ready:= !rmwPending && !io.zero.valid && !io.read.valid
  io.read.ready:= !rmwPending && !io.zero.valid && !io.activation.valid
  if(enableFfnTiles){
    io.activation.ready:= !rmwPending && !io.zero.valid && !io.read.valid && !tileSignals.get.busy && (!tileSignals.get.leased || io.activation.bits.kWord<96.U)
    io.read.ready:= !rmwPending && !io.zero.valid && !io.activation.valid && !tileSignals.get.busy && (!tileSignals.get.leased || io.read.bits.k<1536.U)
  }
  val readFire=io.read.fire
  val loadFire=io.activation.fire
  rmwPending:=loadFire;readPending:=readFire
  when(loadFire){rmw:=io.activation.bits}
  when(readFire){selected:=io.read.bits}
  io.activationBusy:=rmwPending
  io.activationWritten:=rmwPending
  io.response.valid:=readPending
  when(io.zero.valid){assert(!rmwPending && !loadFire && !readFire);assert(io.zero.bits<1376.U)}
  when(loadFire){assert(io.activation.bits.kWord<160.U)}
  when(readFire){assert(io.read.bits.k<2560.U && io.read.bits.context<5.U)}

  val gatherK=io.read.bits.k
  val aOut=(0 until 16).map { bank =>
    val mt=gatherK(3,0)^bank.U(4.W)
    val gatherAddress=Cat(gatherK(11,4),0.U(3.W))+mt
    val loadAddress=Cat(io.activation.bits.kWord,0.U(3.W))+io.activation.bits.m(6,4)
    val readEnable=if(enableFfnTiles)loadFire || (readFire && mt<8.U) || tileSignals.get.issueRead || tileSignals.get.issueWrite else loadFire || (readFire && mt<8.U)
    val address=if(enableFfnTiles)Mux(tileSignals.get.issueRead || tileSignals.get.issueWrite,tileSignals.get.word,Mux(loadFire,loadAddress,gatherAddress))else Mux(loadFire,loadAddress,gatherAddress)
    val response=aBanks(bank).read(address,readEnable)
    if(enableFfnTiles){tileSignals.get.readWords(bank):=response}
    val merged=Wire(Vec(16,UInt(16.W)))
    merged:=response.asTypeOf(Vec(16,UInt(16.W)))
    val laneValue=rmw.value.asTypeOf(Vec(16,UInt(16.W)))
    merged(rmw.m(3,0)):=laneValue(bank.U(4.W)^rmw.m(6,4))
    if(enableFfnTiles){
      val x=tileSignals.get
      val tileMerged=Wire(Vec(8,UInt(32.W)));tileMerged:=response.asTypeOf(Vec(8,UInt(32.W)))
      tileMerged(x.commitLane):=x.writeValue(bank)
      val writeAddress=Mux(x.commit,x.commitWord,Mux(io.zero.valid,io.zero.bits,Cat(rmw.kWord,0.U(3.W))+rmw.m(6,4)))
      val clearLegal=io.zero.valid && !x.busy && (!x.leased || io.zero.bits<768.U)
      when(clearLegal || rmwPending || x.commit){
        assert(!(x.commit && (io.zero.valid || rmwPending)),"accepted tile RMW owns its next-cycle write edge")
        aBanks(bank).write(writeAddress,Mux(x.commit,tileMerged.asUInt,Mux(io.zero.valid,0.U(256.W),merged.asUInt)))
      }
    }else{
      val writeAddress=Mux(io.zero.valid,io.zero.bits,Cat(rmw.kWord,0.U(3.W))+rmw.m(6,4))
      when(io.zero.valid || rmwPending){
        aBanks(bank).write(writeAddress,Mux(io.zero.valid,0.U(256.W),merged.asUInt))
      }
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


/** Internal typed tile ABI. A beat is one column across sixteen consecutive
  * rows, so every physical A bank performs at most one access per cycle.
  * The SRAM values are FP32; no numerical conversion occurs in this service.
  */
/** matrixProducerOrder is a begin-only write-order policy. Seal, release and
  * linear sealed reads retain the existing complete tag/geometry contract. */
class FfnTileControl(enableMatrixProducerOrder:Boolean=false) extends Bundle {
  val op=UInt(2.W) // 0 begin, 1 seal, 2 release; 3 is invalid and poisons.
  val slot=UInt(2.W);val identity=UInt(32.W);val ng=UInt(16.W)
  val rows=UInt(8.W);val cols=UInt(8.W);val matrixProducerOrder=if(enableMatrixProducerOrder)Some(Bool())else None
}
class FfnTileIndex extends Bundle {
  val slot=UInt(2.W);val identity=UInt(32.W);val ng=UInt(16.W);val index=UInt(11.W)
}
class FfnTileBeat extends Bundle {val key=new FfnTileIndex;val value=Vec(16,UInt(32.W))}
class FfnTileResponse extends Bundle {val key=new FfnTileIndex;val value=Vec(16,UInt(32.W));val error=Bool()}
class FfnTileState(enableMatrixProducerOrder:Boolean=false) extends Bundle {
  val live=Bool();val sealedTile=Bool();val identity=UInt(32.W);val ng=UInt(16.W)
  val rows=UInt(8.W);val cols=UInt(8.W);val matrixProducerOrder=if(enableMatrixProducerOrder)Some(Bool())else None;val expected=UInt(11.W)
  val produced=UInt(11.W);val consumed=UInt(11.W)
}
class FfnTilePort(enableMatrixProducerOrder:Boolean=false) extends Bundle {
  val control=Flipped(Decoupled(new FfnTileControl(enableMatrixProducerOrder)))
  val write=Flipped(Decoupled(new FfnTileBeat));val read=Flipped(Decoupled(new FfnTileIndex))
  val response=Decoupled(new FfnTileResponse);val abort=Input(Bool())
  val busy=Output(Bool());val leased=Output(Bool());val drained=Output(Bool());val resetRequired=Output(Bool())
  val state=Output(Vec(3,new FfnTileState(enableMatrixProducerOrder)))
}
class FfnTileBankSignals extends Bundle {
  val busy=Bool();val leased=Bool();val issueRead=Bool();val issueWrite=Bool();val commit=Bool()
  val word=UInt(11.W);val lane=UInt(3.W);val commitWord=UInt(11.W);val commitLane=UInt(3.W)
  val writeValue=Vec(16,UInt(32.W));val readWords=Vec(16,UInt(256.W))
}
