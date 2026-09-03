package gemmini

import chisel3._
import chisel3.util._

class HeteroNgramHeadConfig(val headBits: Int = 5) extends Bundle {
  val order = UInt(2.W)
  val tableSize = UInt(32.W)
  val tableOffset = UInt(64.W)
  val head = UInt(headBits.W)
  val last = Bool()
  override def cloneType: this.type = new HeteroNgramHeadConfig(headBits).asInstanceOf[this.type]
}
class HeteroNgramRowIndex(val headBits: Int = 5) extends Bundle {
  val row = UInt(64.W); val head = UInt(headBits.W); val last = Bool()
  override def cloneType: this.type = new HeteroNgramRowIndex(headBits).asInstanceOf[this.type]
}
class HeteroNgramHash(val maxOrder:Int=3,val tokenBits:Int=20,val maxHeads:Int=16) extends Module {
  require(maxOrder>=2); require(maxHeads>=1); private val headBits=math.max(1,log2Ceil(maxHeads))
  val io=IO(new Bundle{val start=Input(Bool());val tokens=Input(Vec(maxOrder,UInt(tokenBits.W)));val multipliers=Input(Vec(maxOrder,UInt(64.W)));val headConfig=Flipped(Decoupled(new HeteroNgramHeadConfig(headBits)));val rowIndex=Decoupled(new HeteroNgramRowIndex(headBits));val busy=Output(Bool());val done=Output(Bool());val invalidConfig=Output(Bool())})
  val active=RegInit(false.B);val tokens=Reg(Vec(maxOrder,UInt(tokenBits.W)));val multipliers=Reg(Vec(maxOrder,UInt(64.W)));val outValid=RegInit(false.B);val outRow=Reg(UInt(64.W));val outHead=Reg(UInt(headBits.W));val outLast=RegInit(false.B);val invalidConfig=RegInit(false.B);val donePulse=RegInit(false.B)
  io.headConfig.ready:=active&&!outValid;io.rowIndex.valid:=outValid;io.rowIndex.bits.row:=outRow;io.rowIndex.bits.head:=outHead;io.rowIndex.bits.last:=outLast;io.busy:=active||outValid;io.done:=donePulse;io.invalidConfig:=invalidConfig;donePulse:=false.B
  when(!active&&!outValid&&io.start){tokens:=io.tokens;multipliers:=io.multipliers;invalidConfig:=false.B;active:=true.B}
  when(io.headConfig.fire){val mixed=Wire(Vec(maxOrder,UInt(64.W)));for(index<-0 until maxOrder){val product=(tokens(index)*multipliers(index))(63,0);mixed(index):=Mux(index.U<io.headConfig.bits.order,product,0.U)};val hash=mixed.reduce(_^_);val validOrder=io.headConfig.bits.order>=2.U&&io.headConfig.bits.order<=maxOrder.U;val validSize=io.headConfig.bits.tableSize=/=0.U;val modulo=Mux(validSize,hash%io.headConfig.bits.tableSize,0.U);outRow:=io.headConfig.bits.tableOffset+modulo;outHead:=io.headConfig.bits.head;outLast:=io.headConfig.bits.last;outValid:=true.B;when(!validOrder||!validSize){invalidConfig:=true.B};when(io.headConfig.bits.last){active:=false.B}}
  when(io.rowIndex.fire){outValid:=false.B;when(outLast){donePulse:=true.B}}
}

object HeteroGatedResidualProgram {
  import HeteroMicroInstruction.flag; import HeteroPrimitiveCode._
  val program:Seq[HeteroMicroInstruction]=Seq(
    HeteroMicroInstruction(GroupRmsNorm,0x00,src0=0,dst=4,m=0,n=1,k=2),
    HeteroMicroInstruction(MatrixGemm,0x01,src0=4,src1=1,dst=5,m=0,n=3,k=4),
    HeteroMicroInstruction(Reciprocal,0x02,src0=0,dst=11,n=1,index0=1),
    HeteroMicroInstruction(VectorMul,0x03,src0=5,src1=11,dst=5,m=0,n=3),
    HeteroMicroInstruction(Silu,0x04,src0=5,dst=5,m=0,n=3),
    HeteroMicroInstruction(MatrixGemm,0x05,src0=5,src1=2,dst=6,m=0,n=4,k=3),
    HeteroMicroInstruction(Sigmoid,0x06,src0=6,dst=6,m=0,n=4),
    HeteroMicroInstruction(VectorMul,0x07,src0=4,src1=6,dst=7,m=0,n=1,k=2),
    HeteroMicroInstruction(ReduceSum,0x08,src0=7,dst=7,m=0,n=1,k=2),
    HeteroMicroInstruction(VectorMul,0x09,src0=7,src1=11,dst=7,m=0,n=2),
    HeteroMicroInstruction(MatrixGemm,0x0a,src0=4,src1=3,dst=9,m=0,n=1,k=4),
    HeteroMicroInstruction(VectorMul,0x0b,src0=9,src1=11,dst=9,m=0,n=1,index0=2),
    HeteroMicroInstruction(Sigmoid,0x0c,src0=9,dst=9,m=0,n=1),
    HeteroMicroInstruction(VectorMul,0x0d,src0=8,src1=9,dst=10,m=0,n=1,k=2),
    HeteroMicroInstruction(VectorAdd,0x0e,flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Last),src0=0,src1=10,dst=10,m=0,n=1,k=2),
    HeteroMicroInstruction(StateCommit,0x0f,flag(HeteroPrimitiveFlags.Stateful,HeteroPrimitiveFlags.Commit,HeteroPrimitiveFlags.Last),src0=15,dst=15))
}
class HeteroGatedResidualOperatorPrimitive(descriptorBits:Int=24,dimensionBits:Int=16,tagBits:Int=16) extends HeteroCompositeOperatorPrimitive(HeteroGatedResidualProgram.program,"HeteroGatedResidualOperatorPrimitive",descriptorBits,dimensionBits,tagBits)
