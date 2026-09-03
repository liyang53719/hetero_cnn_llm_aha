package gemmini

import chisel3._
import chisel3.util._

object HeteroPrimitiveKind {
  val Width = 8
  val Nop=0x00.U(Width.W); val DmaRead=0x01.U(Width.W); val DmaWrite=0x02.U(Width.W)
  val StateRead=0x03.U(Width.W); val StateWrite=0x04.U(Width.W); val StateCommit=0x05.U(Width.W); val StateRollback=0x06.U(Width.W)
  val MatrixGemm=0x10.U(Width.W); val MatrixGemv=0x11.U(Width.W); val MatrixOuter=0x12.U(Width.W); val MatrixQk=0x13.U(Width.W); val MatrixPv=0x14.U(Width.W); val MatrixConv=0x15.U(Width.W)
  val VectorAdd=0x20.U(Width.W); val VectorSub=0x21.U(Width.W); val VectorMul=0x22.U(Width.W); val VectorFma=0x23.U(Width.W); val VectorCompare=0x24.U(Width.W); val VectorSelect=0x25.U(Width.W); val VectorGather=0x26.U(Width.W); val VectorScatter=0x27.U(Width.W)
  val ReduceSum=0x30.U(Width.W); val ReduceMax=0x31.U(Width.W); val Reciprocal=0x32.U(Width.W); val Rsqrt=0x33.U(Width.W); val Exp2=0x34.U(Width.W); val RmsNorm=0x35.U(Width.W); val LayerNorm=0x36.U(Width.W); val Rope=0x37.U(Width.W); val Silu=0x38.U(Width.W); val GeluTanh=0x39.U(Width.W); val Sigmoid=0x3a.U(Width.W); val Softplus=0x3b.U(Width.W); val OnlineSoftmax=0x3c.U(Width.W); val GroupRmsNorm=0x3d.U(Width.W); val L2Norm=0x3e.U(Width.W)
  val KvAppend=0x40.U(Width.W); val KvGather=0x41.U(Width.W); val SparseGatherRun=0x42.U(Width.W); val DepthwiseConv=0x43.U(Width.W); val StableTopK=0x44.U(Width.W); val NgramHash=0x45.U(Width.W); val EmbeddingLookup=0x46.U(Width.W); val BilinearPosition=0x47.U(Width.W); val SpatialMerge=0x48.U(Width.W); val StableSort=0x49.U(Width.W); val SignedSqrt=0x4a.U(Width.W); val SubgraphLaunch=0x4b.U(Width.W); val Argmax=0x4c.U(Width.W); val Barrier=0x4f.U(Width.W)
}

object HeteroPrimitiveCode {
  val Nop=0x00; val DmaRead=0x01; val DmaWrite=0x02; val StateRead=0x03; val StateWrite=0x04; val StateCommit=0x05; val StateRollback=0x06
  val MatrixGemm=0x10; val MatrixGemv=0x11; val MatrixOuter=0x12; val MatrixQk=0x13; val MatrixPv=0x14; val MatrixConv=0x15
  val VectorAdd=0x20; val VectorSub=0x21; val VectorMul=0x22; val VectorFma=0x23; val VectorCompare=0x24; val VectorSelect=0x25; val VectorGather=0x26; val VectorScatter=0x27
  val ReduceSum=0x30; val ReduceMax=0x31; val Reciprocal=0x32; val Rsqrt=0x33; val Exp2=0x34; val RmsNorm=0x35; val LayerNorm=0x36; val Rope=0x37; val Silu=0x38; val GeluTanh=0x39; val Sigmoid=0x3a; val Softplus=0x3b; val OnlineSoftmax=0x3c; val GroupRmsNorm=0x3d; val L2Norm=0x3e
  val KvAppend=0x40; val KvGather=0x41; val SparseGatherRun=0x42; val DepthwiseConv=0x43; val StableTopK=0x44; val NgramHash=0x45; val EmbeddingLookup=0x46; val BilinearPosition=0x47; val SpatialMerge=0x48; val StableSort=0x49; val SignedSqrt=0x4a; val SubgraphLaunch=0x4b; val Argmax=0x4c; val Barrier=0x4f
}

object HeteroPrimitiveFlags {
  val InitAccumulator=0; val FinalAccumulator=1; val Causal=2; val NonCausal=3; val ApplyBias=4; val ApplyActivation=5; val Sparse=6; val Stateful=7; val First=8; val Last=9; val SharedExpert=10; val RoutedExpert=11; val Commit=12; val Rollback=13; val PartialRotary=14; val MropeInterleaved=15
}

class HeteroTensorMicroOp(val descriptorBits:Int=24,val dimensionBits:Int=16,val tagBits:Int=16) extends Bundle {
  val kind=UInt(HeteroPrimitiveKind.Width.W); val phase=UInt(8.W); val flags=UInt(16.W)
  val src0=UInt(descriptorBits.W); val src1=UInt(descriptorBits.W); val src2=UInt(descriptorBits.W); val dst=UInt(descriptorBits.W)
  val m=UInt(dimensionBits.W); val n=UInt(dimensionBits.W); val k=UInt(dimensionBits.W); val index0=UInt(dimensionBits.W); val index1=UInt(dimensionBits.W); val tag=UInt(tagBits.W)
  override def cloneType:this.type=new HeteroTensorMicroOp(descriptorBits,dimensionBits,tagBits).asInstanceOf[this.type]
}
class HeteroPrimitiveCompletion(val tagBits:Int=16) extends Bundle { val tag=UInt(tagBits.W); val status=UInt(8.W); override def cloneType:this.type=new HeteroPrimitiveCompletion(tagBits).asInstanceOf[this.type] }
class HeteroOperatorResult(val tagBits:Int=16) extends Bundle { val tag=UInt(tagBits.W); val status=UInt(8.W); val completedSteps=UInt(16.W); override def cloneType:this.type=new HeteroOperatorResult(tagBits).asInstanceOf[this.type] }
class HeteroOperatorLaunch(val descriptorBits:Int=24,val dimensionBits:Int=16,val tagBits:Int=16,val descriptorSlots:Int=16,val dimensionSlots:Int=8,val controlSlots:Int=8) extends Bundle {
  val descriptors=Vec(descriptorSlots,UInt(descriptorBits.W)); val dimensions=Vec(dimensionSlots,UInt(dimensionBits.W)); val controls=Vec(controlSlots,UInt(32.W)); val tag=UInt(tagBits.W)
  override def cloneType:this.type=new HeteroOperatorLaunch(descriptorBits,dimensionBits,tagBits,descriptorSlots,dimensionSlots,controlSlots).asInstanceOf[this.type]
}
case class HeteroMicroInstruction(kind:Int,phase:Int,flags:Int=0,src0:Int=0,src1:Int=0,src2:Int=0,dst:Int=0,m:Int=0,n:Int=0,k:Int=0,index0:Int=0,index1:Int=0)
object HeteroMicroInstruction { def flag(bits:Int*):Int=bits.foldLeft(0)((v,b)=>v|(1<<b)) }

class HeteroMicroProgramSequencer(val program:Seq[HeteroMicroInstruction],val descriptorBits:Int=24,val dimensionBits:Int=16,val tagBits:Int=16) extends Module {
  require(program.nonEmpty); private val stepBits=math.max(1,log2Ceil(program.length+1))
  val io=IO(new Bundle { val launch=Flipped(Decoupled(new HeteroOperatorLaunch(descriptorBits,dimensionBits,tagBits))); val microOp=Decoupled(new HeteroTensorMicroOp(descriptorBits,dimensionBits,tagBits)); val completion=Flipped(Decoupled(new HeteroPrimitiveCompletion(tagBits))); val result=Decoupled(new HeteroOperatorResult(tagBits)); val busy=Output(Bool()); val protocolError=Output(Bool()) })
  val sIdle::sIssue::sWait::sResult::Nil=Enum(4); val state=RegInit(sIdle); val launchReg=Reg(new HeteroOperatorLaunch(descriptorBits,dimensionBits,tagBits)); val step=RegInit(0.U(stepBits.W)); val completed=RegInit(0.U(16.W)); val status=RegInit(0.U(8.W)); val protocolError=RegInit(false.B)
  val kinds=VecInit(program.map(_.kind.U(HeteroPrimitiveKind.Width.W))); val phases=VecInit(program.map(_.phase.U(8.W))); val flags=VecInit(program.map(_.flags.U(16.W))); val s0=VecInit(program.map(_.src0.U(4.W))); val s1=VecInit(program.map(_.src1.U(4.W))); val s2=VecInit(program.map(_.src2.U(4.W))); val ds=VecInit(program.map(_.dst.U(4.W))); val ms=VecInit(program.map(_.m.U(3.W))); val ns=VecInit(program.map(_.n.U(3.W))); val ks=VecInit(program.map(_.k.U(3.W))); val i0=VecInit(program.map(_.index0.U(dimensionBits.W))); val i1=VecInit(program.map(_.index1.U(dimensionBits.W)))
  io.launch.ready:=state===sIdle; io.microOp.valid:=state===sIssue; io.microOp.bits.kind:=kinds(step); io.microOp.bits.phase:=phases(step); io.microOp.bits.flags:=flags(step); io.microOp.bits.src0:=launchReg.descriptors(s0(step)); io.microOp.bits.src1:=launchReg.descriptors(s1(step)); io.microOp.bits.src2:=launchReg.descriptors(s2(step)); io.microOp.bits.dst:=launchReg.descriptors(ds(step)); io.microOp.bits.m:=launchReg.dimensions(ms(step)); io.microOp.bits.n:=launchReg.dimensions(ns(step)); io.microOp.bits.k:=launchReg.dimensions(ks(step)); io.microOp.bits.index0:=i0(step); io.microOp.bits.index1:=i1(step); io.microOp.bits.tag:=launchReg.tag
  io.completion.ready:=state===sWait; io.result.valid:=state===sResult; io.result.bits.tag:=launchReg.tag; io.result.bits.status:=status; io.result.bits.completedSteps:=completed; io.busy:=state=/=sIdle; io.protocolError:=protocolError
  when(state===sIdle){when(io.launch.fire){launchReg:=io.launch.bits;step:=0.U;completed:=0.U;status:=0.U;protocolError:=false.B;state:=sIssue}}
    .elsewhen(state===sIssue){when(io.microOp.fire){state:=sWait}}
    .elsewhen(state===sWait){when(io.completion.fire){val tagOk=io.completion.bits.tag===launchReg.tag;val nextStatus=Mux(tagOk,io.completion.bits.status,"hfe".U);completed:=completed+1.U;when(!tagOk){protocolError:=true.B};when(nextStatus=/=0.U||step+1.U>=program.length.U){status:=nextStatus;state:=sResult}.otherwise{step:=step+1.U;state:=sIssue}}}
    .elsewhen(state===sResult){when(io.result.fire){state:=sIdle}}
}

class HeteroScoreIndex(val indexBits:Int=16) extends Bundle { val score=UInt(32.W); val index=UInt(indexBits.W); val last=Bool(); override def cloneType:this.type=new HeteroScoreIndex(indexBits).asInstanceOf[this.type] }
class HeteroRankedScore(val indexBits:Int=16,val rankBits:Int=10) extends Bundle { val score=UInt(32.W); val index=UInt(indexBits.W); val rank=UInt(rankBits.W); val last=Bool(); override def cloneType:this.type=new HeteroRankedScore(indexBits,rankBits).asInstanceOf[this.type] }
object HeteroFp32Order {
  def isZero(v:UInt):Bool=v(30,0)===0.U; def isNaN(v:UInt):Bool=v(30,23)==="hff".U&&v(22,0)=/=0.U
  def orderedKey(v:UInt):UInt={val c=Mux(isZero(v),0.U(32.W),v);Mux(c(31),~c,c^"h80000000".U)}
  def better(cs:UInt,ci:UInt,rs:UInt,ri:UInt):Bool={val cn=isNaN(cs);val rn=isNaN(rs);val ck=orderedKey(cs);val rk=orderedKey(rs);Mux(cn,rn&&ci<ri,Mux(rn,true.B,ck>rk||(ck===rk&&ci<ri)))}
}
