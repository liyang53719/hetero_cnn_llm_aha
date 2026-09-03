package gemmini

import chisel3._
import chisel3.util._

object HeteroVisionPatchProgram {
  import HeteroMicroInstruction.flag; import HeteroPrimitiveCode._
  val program:Seq[HeteroMicroInstruction]=Seq(
    HeteroMicroInstruction(MatrixConv,0x00,flag(HeteroPrimitiveFlags.ApplyBias),src0=0,src1=1,dst=2,m=0,n=1,k=2,index0=3),
    HeteroMicroInstruction(BilinearPosition,0x01,src0=3,src1=4,dst=5,m=0,n=1),
    HeteroMicroInstruction(VectorAdd,0x02,flag(HeteroPrimitiveFlags.Last),src0=2,src1=5,dst=6,m=0,n=1))
}
class HeteroVisionPatchEmbedOperatorPrimitive(descriptorBits:Int=24,dimensionBits:Int=16,tagBits:Int=16) extends HeteroCompositeOperatorPrimitive(HeteroVisionPatchProgram.program,"HeteroVisionPatchEmbedOperatorPrimitive",descriptorBits,dimensionBits,tagBits)

object HeteroVisionBlockProgram {
  import HeteroMicroInstruction.flag; import HeteroPrimitiveCode._
  val program:Seq[HeteroMicroInstruction]=Seq(
    HeteroMicroInstruction(LayerNorm,0x00,src0=0,src1=1,dst=2,m=0,n=1),
    HeteroMicroInstruction(MatrixGemm,0x01,flag(HeteroPrimitiveFlags.ApplyBias),src0=2,src1=3,dst=4,m=0,n=2,k=1),
    HeteroMicroInstruction(Rope,0x02,flag(HeteroPrimitiveFlags.NonCausal),src0=4,src1=5,dst=4,m=0,n=2,k=3),
    HeteroMicroInstruction(MatrixQk,0x03,flag(HeteroPrimitiveFlags.NonCausal),src0=4,src1=4,dst=6,m=2,n=2,k=3),
    HeteroMicroInstruction(OnlineSoftmax,0x04,flag(HeteroPrimitiveFlags.NonCausal),src0=6,dst=6,m=2,n=2),
    HeteroMicroInstruction(MatrixPv,0x05,flag(HeteroPrimitiveFlags.NonCausal),src0=6,src1=4,dst=7,m=2,n=1,k=2),
    HeteroMicroInstruction(MatrixGemm,0x06,src0=7,src1=8,dst=7,m=0,n=1,k=1),
    HeteroMicroInstruction(VectorAdd,0x07,src0=0,src1=7,dst=9,m=0,n=1),
    HeteroMicroInstruction(LayerNorm,0x08,src0=9,src1=10,dst=2,m=0,n=1),
    HeteroMicroInstruction(MatrixGemm,0x09,flag(HeteroPrimitiveFlags.ApplyBias),src0=2,src1=11,dst=4,m=0,n=4,k=1),
    HeteroMicroInstruction(GeluTanh,0x0a,src0=4,dst=4,m=0,n=4),
    HeteroMicroInstruction(MatrixGemm,0x0b,flag(HeteroPrimitiveFlags.ApplyBias),src0=4,src1=12,dst=7,m=0,n=1,k=4),
    HeteroMicroInstruction(VectorAdd,0x0c,flag(HeteroPrimitiveFlags.Last),src0=9,src1=7,dst=13,m=0,n=1))
}
class HeteroVisionTransformerBlockOperatorPrimitive(descriptorBits:Int=24,dimensionBits:Int=16,tagBits:Int=16) extends HeteroCompositeOperatorPrimitive(HeteroVisionBlockProgram.program,"HeteroVisionTransformerBlockOperatorPrimitive",descriptorBits,dimensionBits,tagBits)

object HeteroVisionMergeProgram {
  import HeteroMicroInstruction.flag; import HeteroPrimitiveCode._
  val program:Seq[HeteroMicroInstruction]=Seq(
    HeteroMicroInstruction(LayerNorm,0x00,src0=0,src1=1,dst=2,m=0,n=1),
    HeteroMicroInstruction(SpatialMerge,0x01,src0=2,dst=3,m=0,n=1,index0=2),
    HeteroMicroInstruction(MatrixGemm,0x02,flag(HeteroPrimitiveFlags.ApplyBias),src0=3,src1=4,dst=5,m=0,n=2,k=1),
    HeteroMicroInstruction(GeluTanh,0x03,src0=5,dst=5,m=0,n=2),
    HeteroMicroInstruction(MatrixGemm,0x04,flag(HeteroPrimitiveFlags.ApplyBias,HeteroPrimitiveFlags.Last),src0=5,src1=6,dst=7,m=0,n=3,k=2))
}
class HeteroVisionPatchMergeOperatorPrimitive(descriptorBits:Int=24,dimensionBits:Int=16,tagBits:Int=16) extends HeteroCompositeOperatorPrimitive(HeteroVisionMergeProgram.program,"HeteroVisionPatchMergeOperatorPrimitive",descriptorBits,dimensionBits,tagBits)

class HeteroBilinearPositionResult(val addressBits:Int=24) extends Bundle {val addresses=Vec(4,UInt(addressBits.W));val weightsQ16=Vec(4,UInt(17.W));override def cloneType:this.type=new HeteroBilinearPositionResult(addressBits).asInstanceOf[this.type]}
class HeteroBilinearPositionPlanner(val addressBits:Int=24) extends Module {
  val io=IO(new Bundle{val in=Flipped(Decoupled(new Bundle{val row=UInt(addressBits.W);val column=UInt(addressBits.W);val height=UInt(addressBits.W);val width=UInt(addressBits.W);val rowFractionQ16=UInt(16.W);val columnFractionQ16=UInt(16.W)}));val out=Decoupled(new HeteroBilinearPositionResult(addressBits))})
  val valid=RegInit(false.B);val result=Reg(new HeteroBilinearPositionResult(addressBits));io.in.ready:=!valid||io.out.ready;io.out.valid:=valid;io.out.bits:=result
  when(io.in.ready){valid:=io.in.valid;when(io.in.valid){val safeHeight=Mux(io.in.bits.height===0.U,1.U,io.in.bits.height);val safeWidth=Mux(io.in.bits.width===0.U,1.U,io.in.bits.width);val row0=Mux(io.in.bits.row>=safeHeight,safeHeight-1.U,io.in.bits.row);val col0=Mux(io.in.bits.column>=safeWidth,safeWidth-1.U,io.in.bits.column);val row1=Mux(row0+1.U>=safeHeight,row0,row0+1.U);val col1=Mux(col0+1.U>=safeWidth,col0,col0+1.U);val one=65536.U(17.W);val fr=io.in.bits.rowFractionQ16;val fc=io.in.bits.columnFractionQ16;val invR=one-fr;val invC=one-fc;result.addresses(0):=row0*safeWidth+col0;result.addresses(1):=row0*safeWidth+col1;result.addresses(2):=row1*safeWidth+col0;result.addresses(3):=row1*safeWidth+col1;result.weightsQ16(0):=(invR*invC)(32,16);result.weightsQ16(1):=(invR*fc)(32,16);result.weightsQ16(2):=(fr*invC)(32,16);result.weightsQ16(3):=(fr*fc)(32,16)}}
}
class HeteroSpatialMergeIndex(val addressBits:Int=24) extends Bundle {val sourceToken=UInt(addressBits.W);val lane=UInt(2.W);val last=Bool();override def cloneType:this.type=new HeteroSpatialMergeIndex(addressBits).asInstanceOf[this.type]}
class HeteroSpatialMergeAddressGenerator(val addressBits:Int=24) extends Module {
  val io=IO(new Bundle{val start=Input(Bool());val groupRow=Input(UInt(addressBits.W));val groupColumn=Input(UInt(addressBits.W));val sourceWidth=Input(UInt(addressBits.W));val out=Decoupled(new HeteroSpatialMergeIndex(addressBits));val busy=Output(Bool());val done=Output(Bool())});val active=RegInit(false.B);val lane=RegInit(0.U(2.W));val baseRow=Reg(UInt(addressBits.W));val baseColumn=Reg(UInt(addressBits.W));val width=Reg(UInt(addressBits.W));val donePulse=RegInit(false.B);val rowOffset=lane(1);val columnOffset=lane(0);io.out.valid:=active;io.out.bits.sourceToken:=(baseRow+rowOffset)*width+baseColumn+columnOffset;io.out.bits.lane:=lane;io.out.bits.last:=lane===3.U;io.busy:=active;io.done:=donePulse;donePulse:=false.B
  when(!active&&io.start){baseRow:=io.groupRow<<1;baseColumn:=io.groupColumn<<1;width:=Mux(io.sourceWidth===0.U,1.U,io.sourceWidth);lane:=0.U;active:=true.B}.elsewhen(io.out.fire){when(lane===3.U){active:=false.B;donePulse:=true.B}.otherwise{lane:=lane+1.U}}
}
