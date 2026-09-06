// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import heteronpu.p0.{LocalSramConfig,SharedL2Fabric}
import gemmini.{HeteroBF16FmaLane,HeteroFP32Alu}
import scala.collection.mutable.ArrayBuffer

/** Functional bring-up profile, not the Revision8B 512-lane performance target.
  * The 16 shared MAC lanes reuse the repository BF16/FP32 HardFloat primitive.
  * All DDR words are canonical FP32 containers (weights have BF16 values).
  * Matrix ingress alone rounds activations to BF16; reductions/residuals are FP32.
  */
case class QwenBlockShape(hidden:Int=1536,ffn:Int=8960,heads:Int=12,kvHeads:Int=2,headDim:Int=128,maxTokens:Int=1024,retainedMatrix:Boolean=false) {
  require(hidden==heads*headDim && heads%kvHeads==0)
  require(headDim>=32 && headDim%32==0 && ffn%16==0 && hidden%16==0)
  require(maxTokens>0 && maxTokens<=1024)
  val kv=kvHeads*headDim
  val maxRow=math.max(hidden,ffn)
}
case class BlockRegion(name:String,offset:Long,words:Long,external:Boolean)
class QwenBlockLayout(s:QwenBlockShape) {
  private val list=ArrayBuffer.empty[BlockRegion]; private var cursor=0L
  private def add(n:String,w:Long,ext:Boolean):Unit={cursor=(cursor+63)& ~63L;list+=BlockRegion(n,cursor,w,ext);cursor+=w*4}
  for((n,k,v)<-Seq(("wq",s.hidden,s.hidden),("wk",s.hidden,s.kv),("wv",s.hidden,s.kv),("wo",s.hidden,s.hidden),("wg",s.hidden,s.ffn),("wu",s.hidden,s.ffn),("wd",s.ffn,s.hidden)))add(n,k.toLong*v,true)
  for(n<-Seq("gamma0","gamma1","bq"))add(n,s.hidden,true)
  for(n<-Seq("bk","bv"))add(n,s.kv,true)
  add("cos",s.maxTokens.toLong*s.headDim/2,true);add("sin",s.maxTokens.toLong*s.headDim/2,true)
  add("x",s.maxTokens.toLong*s.hidden,true)
  val writableStart=(cursor+63)& ~63L
  for((n,w)<-Seq(("n0",s.hidden),("qr",s.hidden),("kr",s.kv),("v",s.kv),("q",s.hidden),("k",s.kv),("att",s.hidden),("o",s.hidden),("r",s.hidden),("n1",s.hidden),("gate",s.ffn),("up",s.ffn),("act",s.ffn),("down",s.hidden),("y",s.hidden)))add(n,s.maxTokens.toLong*w,false)
  val total=(cursor+63)& ~63L
  val regions=list.toSeq
  def apply(n:String):Long=regions.find(_.name==n).get.offset
}
class BlockLaunch extends Bundle {val base=UInt(64.W);val limit=UInt(64.W);val tokens=UInt(16.W);val epoch=UInt(16.W)}
class BlockResult extends Bundle {val status=UInt(8.W);val phase=UInt(5.W);val epoch=UInt(16.W);val cycles=UInt(64.W);val macs=UInt(64.W);val executedMacs=UInt(64.W)}

/** Complete text decoder block: no host-supplied intermediate tensor, task-based
  * math, or output lookup. Stage transition happens only after final write ACK.
  * Q/K/V remain in DDR as per-layer KV output. Attention keeps only O(T) scores
  * and probabilities on-chip, never a T-by-T score matrix in DDR.
  */
class Qwen2ContinuousBlock(s:QwenBlockShape=QwenBlockShape()) extends Module {
  val layout=new QwenBlockLayout(s)
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new BlockLaunch));val result=Decoupled(new BlockResult)
    val memory=Decoupled(new MemoryRequest);val response=Flipped(Decoupled(new MemoryResponse))
    val phase=Output(UInt(5.W));val stageCommit=Output(Bool());val committedPhase=Output(UInt(5.W))
    val resetRequired=Output(Bool());val readBytes=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
  })
  val stateNames=Seq("idle","begin","memReq","memRsp","localReq","localRsp","localWrite","scalarReq","scalarRsp","advance", "normLoad","normGot","normSquare","normReduce","normReduceDone","normMean","normEps","normSqrt","normInv","normEmit","normLocal","normGamma","normScale","normProduct","normWritten", "denseLoad","denseGot","denseLoaded","denseLocal","denseWeight","denseCompute","denseBias","denseBiasGot","denseWrite","denseWritten", "ropeStart","ropeEven","ropeOdd","ropeCos","ropeSin","ropeMul0","ropeMul1","ropeAdd0","ropeAdd1","ropeWrite0","ropeWrite1","ropeWritten", "attQLoad","attQGot","attQStored","attKey","attLocal","attWeight","attDot","attReduce","attReduceDone","attScore","attNextKey","attExpRead","attExpWait","attExpDiff","attExpResult","attExpSum","attNextExp","attInv","attPVStart","attProbRead","attProbWait","attProbScale","attVRead","attPVCompute","attPVWrite","attPVWritten", "siluRead","siluGate","siluUp","siluExp","siluDenom","siluInv","siluSign","siluGateMul","siluUpMul","siluNext","siluWritten","resIssue","resWait","finish","locked")
  private val codes=stateNames.zipWithIndex.toMap
  def st(n:String):UInt=codes(n).U(7.W)
  val state=RegInit(st("idle"));val resume=Reg(UInt(7.W));val scalarResume=Reg(UInt(7.W));val localResume=Reg(UInt(7.W))
  val phase=RegInit(0.U(5.W));val base=Reg(UInt(64.W));val tokens=Reg(UInt(16.W));val epoch=Reg(UInt(16.W))
  val status=RegInit(0.U(8.W));val poisoned=RegInit(false.B);val cycles=RegInit(0.U(64.W));val macs=RegInit(0.U(64.W))
  val reads=RegInit(0.U(64.W));val writes=RegInit(0.U(64.W));val seq=RegInit(0.U(32.W))
  val request=Reg(new MemoryRequest);val packet=Reg(UInt(512.W))
  val token=RegInit(0.U(16.W));val col=RegInit(0.U(16.W));val depth=RegInit(0.U(16.W));val head=RegInit(0.U(8.W));val key=RegInit(0.U(16.W));val lane=RegInit(0.U(4.W))
  val sum=RegInit(0.U(32.W));val scale=Reg(UInt(32.W));val maxScore=Reg(UInt(32.W));val probability=Reg(UInt(32.W))
  val av=Reg(Vec(16,UInt(32.W)));val bv=Reg(Vec(16,UInt(32.W)));val cv=Reg(Vec(16,UInt(32.W)));val dv=Reg(Vec(16,UInt(32.W)))
  val acc=Reg(Vec(16,UInt(32.W)));val tmp=Reg(Vec(16,UInt(32.W)));val tmp2=Reg(Vec(16,UInt(32.W)))
  val scalarValue=Reg(UInt(32.W));val scalarRequest=Reg(new ScalarRequest)
  val scalar=Module(new BlockScalarFloat);scalar.io.request.valid:=state===st("scalarReq");scalar.io.request.bits:=scalarRequest;scalar.io.result.ready:=state===st("scalarRsp")
  val localRows=(s.maxRow*4+255)/256
  val fabric=Module(new SharedL2Fabric(LocalSramConfig(rowsPerBank=localRows)))
  val f=fabric.io;f.rd_valid_i:=0.U;f.rd_addr_i:=0.U;f.rd_resp_ready_i:=0.U;f.wr_valid_i:=false.B;f.wr_addr_i:=0.U;f.wr_data_i:=0.U;f.wr_be_i:=Mux(state===st("localWrite"),Fill(64,1.U(1.W)),0.U)
  val localIndex=Reg(UInt(15.W));val localData=Reg(UInt(512.W))
  val scores=SyncReadMem(s.maxTokens,UInt(32.W));val probs=SyncReadMem(s.maxTokens,UInt(32.W))
  val scoreOut=scores.read(key,state===st("attExpRead"));val probOut=probs.read(key,state===st("attProbRead"))
  val vectorA=Wire(Vec(16,UInt(32.W)));val vectorB=Wire(Vec(16,UInt(32.W)));val vectorMul=WireDefault(false.B)
  vectorA:=av;vectorB:=bv
  val vout=VecInit((0 until 16).map {i=>val a=Module(new HeteroFP32Alu);a.io.op:=vectorMul;a.io.x:=vectorA(i);a.io.y:=vectorB(i);a.io.out})
  val fmA=Wire(Vec(16,UInt(32.W)));val fmB=Wire(Vec(16,UInt(32.W)));fmA:=av;fmB:=bv
  val fmOut=Wire(Vec(16,UInt(32.W)));val fmDone=WireDefault(true.B)
  val matrixFault=WireDefault(false.B)
  if(s.retainedMatrix){
    val m=Module(new RetainedMatrix16Adapter);val pending=RegInit(false.B)
    val computing=state===st("denseCompute")||state===st("attDot")||state===st("attPVCompute")
    m.io.request.valid:=computing && !pending;m.io.request.bits.a:=fmA;m.io.request.bits.b:=fmB
    m.io.request.bits.clear:=Mux(state===st("attPVCompute"),key===0.U,depth===0.U)
    m.io.request.bits.last:=Mux(state===st("attPVCompute"),key===token,Mux(state===st("attDot"),depth+16.U===s.headDim.U,depth+1.U===Mux(phase===13.U,s.ffn.U,s.hidden.U)))
    m.io.request.bits.diagonal:=state===st("attDot")
    m.io.result.ready:=computing && pending
    when(m.io.request.fire){pending:=true.B};when(m.io.result.fire){pending:=false.B}
    fmOut:=m.io.result.bits.value;fmDone:=m.io.result.fire;matrixFault:=m.io.result.fire&&m.io.result.bits.error
  }else{
    fmOut:=VecInit((0 until 16).map {i=>val a=Module(new HeteroBF16FmaLane);a.io.a:=TensorMath.bf16Rne(fmA(i));a.io.b:=TensorMath.bf16Rne(fmB(i));a.io.c:=acc(i);a.io.out})
  }
  val elemCfg=ChainConfig();val elem=Module(new ElementwiseMemoryEngine(elemCfg,LocalSramConfig(rowsPerBank=elemCfg.localBytes/256)))
  val resActive=state===st("resIssue")||state===st("resWait")
  elem.io.job.valid:=state===st("resIssue");elem.io.job.bits:=0.U.asTypeOf(new BoundJob)
  elem.io.job.bits.op:=ElemOp.Add.U;elem.io.job.bits.a:=base+Mux(phase===8.U,layout("x").U,layout("r").U)
  elem.io.job.bits.b:=base+Mux(phase===8.U,layout("o").U,layout("down").U)
  elem.io.job.bits.dst:=base+Mux(phase===8.U,layout("r").U,layout("y").U)
  elem.io.job.bits.elementCount:=tokens*s.hidden.U;elem.io.job.bits.tag:=Cat(epoch,phase.pad(16))
  elem.io.done.ready:=state===st("resWait")
  elem.io.memory.ready:=io.memory.ready&&resActive;elem.io.response.valid:=io.response.valid&&resActive;elem.io.response.bits:=io.response.bits
  io.memory.valid:=Mux(resActive,elem.io.memory.valid,state===st("memReq"));io.memory.bits:=Mux(resActive,elem.io.memory.bits,request)
  io.response.ready:=Mux(resActive,elem.io.response.ready,state===st("memRsp"))
  io.launch.ready:=state===st("idle") && !poisoned
  io.result.valid:=state===st("finish");io.result.bits.status:=status;io.result.bits.phase:=phase;io.result.bits.epoch:=epoch;io.result.bits.cycles:=cycles;io.result.bits.macs:=macs;io.result.bits.executedMacs:=macs*(if(s.retainedMatrix)32 else 1).U
  io.phase:=phase;io.stageCommit:=false.B;io.committedPhase:=phase;io.resetRequired:=poisoned||elem.io.resetRequired
  io.readBytes:=reads;io.writeBytes:=writes
  when(state=/=st("idle")&&state=/=st("finish")&&state=/=st("locked")){cycles:=cycles+1.U}
  when(io.memory.fire){when(io.memory.bits.write){writes:=writes+PopCount(io.memory.bits.mask)}.otherwise{reads:=reads+64.U}}
  def fail(code:UInt):Unit={status:=code;poisoned:=true.B;state:=st("finish")}
  def read(address:UInt,next:String):Unit={request.write:=false.B;request.address:=address;request.data:=0.U;request.mask:=0.U;request.tag:=Cat(epoch.pad(32),seq);seq:=seq+1.U;resume:=st(next);state:=st("memReq")}
  def write(address:UInt,data:UInt,next:String):Unit={
    // Never publish a non-finite intermediate, even if a later consumer could
    // otherwise detect it. All block writes contain sixteen valid FP32 words.
    val bad=(0 until 16).map(i=> !TensorMath.finite(data(32*i+31,32*i))).reduce(_||_)
    when(bad){fail(Status.Numerical.U)}.otherwise{
      request.write:=true.B;request.address:=address;request.data:=data;request.mask:=Fill(64,1.U(1.W))
      request.tag:=Cat(epoch.pad(32),seq);seq:=seq+1.U;resume:=st(next);state:=st("memReq")
    }
  }
  def localRead(index:UInt,next:String):Unit={localIndex:=index;localResume:=st(next);state:=st("localReq")}
  def localWrite(index:UInt,data:UInt,next:String):Unit={localIndex:=index;localData:=data;localResume:=st(next);state:=st("localWrite")}
  def calc(op:Int,a:UInt,b:UInt,next:String):Unit={scalarRequest.op:=op.U;scalarRequest.a:=a;scalarRequest.b:=b;scalarResume:=st(next);state:=st("scalarReq")}
  def ptr(n:String,index:UInt=0.U):UInt=base+layout(n).U(64.W)+(index.pad(64)<<2)
  def clearAcc():Unit={acc:=VecInit(Seq.fill(16)(0.U(32.W)))}
  def rowOffset(width:UInt):UInt=token.pad(32)*width
  val nIn= Mux(phase===0.U,layout("x").U,layout("r").U)
  val nOut=Mux(phase===0.U,layout("n0").U,layout("n1").U)
  val gamma=Mux(phase===0.U,layout("gamma0").U,layout("gamma1").U)
  val dIn=MuxLookup(phase,layout("n0").U)(Seq(7.U->layout("att").U,10.U->layout("n1").U,11.U->layout("n1").U,13.U->layout("act").U))
  val dOut=MuxLookup(phase,layout("qr").U)(Seq(2.U->layout("kr").U,3.U->layout("v").U,7.U->layout("o").U,10.U->layout("gate").U,11.U->layout("up").U,13.U->layout("down").U))
  val dWeight=MuxLookup(phase,layout("wq").U)(Seq(2.U->layout("wk").U,3.U->layout("wv").U,7.U->layout("wo").U,10.U->layout("wg").U,11.U->layout("wu").U,13.U->layout("wd").U))
  val dK=Mux(phase===13.U,s.ffn.U,s.hidden.U);val dN=Mux(phase===2.U||phase===3.U,s.kv.U,Mux(phase===10.U||phase===11.U,s.ffn.U,s.hidden.U))
  val bias=MuxLookup(phase,layout("bq").U)(Seq(2.U->layout("bk").U,3.U->layout("bv").U))
  val ropeWidth=Mux(phase===4.U,s.hidden.U,s.kv.U);val ropeHeads=Mux(phase===4.U,s.heads.U,s.kvHeads.U)
  val ropeInput=Mux(phase===4.U,layout("qr").U,layout("kr").U);val ropeOutput=Mux(phase===4.U,layout("q").U,layout("k").U)
  val ropeIndex=token.pad(32)*ropeWidth+head*s.headDim.U+col
  val kvHead=head/(s.heads/s.kvHeads).U
  when(state===st("memReq")){when(io.memory.fire){state:=st("memRsp")}}
  when(state===st("memRsp")&&io.response.fire){
    when(io.response.bits.tag=/=request.tag){fail(Status.Protocol.U)}
    .elsewhen(io.response.bits.error){fail(Status.Memory.U)}
    .otherwise{packet:=io.response.bits.data;state:=resume}
  }
  when(state===st("localReq")){f.rd_valid_i:=1.U;f.rd_addr_i:=localIndex;when(f.rd_ready_o(0)){state:=st("localRsp")}}
  when(state===st("localRsp")){f.rd_resp_ready_i:=1.U;when(f.rd_resp_valid_o(0)){av:=f.rd_data_o(511,0).asTypeOf(av);state:=localResume}}
  when(state===st("localWrite")){f.wr_valid_i:=true.B;f.wr_addr_i:=localIndex;f.wr_data_i:=localData;when(f.wr_ready_o){state:=localResume}}
  when(state===st("scalarReq")&&scalar.io.request.fire){state:=st("scalarRsp")}
  when(state===st("scalarRsp")&&scalar.io.result.fire){when(scalar.io.error){fail(Status.Numerical.U)}.otherwise{scalarValue:=scalar.io.result.bits;state:=scalarResume}}
  when(f.address_error_o.orR && state=/=st("finish")&&state=/=st("locked")){fail(Status.Bounds.U)}
  when(state===st("idle")&&io.launch.fire){
    base:=io.launch.bits.base;tokens:=io.launch.bits.tokens;epoch:=io.launch.bits.epoch;phase:=0.U;seq:=0.U;status:=0.U;cycles:=0.U;macs:=0.U;reads:=0.U;writes:=0.U
    when(io.launch.bits.tokens===0.U||io.launch.bits.tokens>s.maxTokens.U||io.launch.bits.base(5,0)=/=0.U||
      io.launch.bits.base.pad(66)+layout.total.U>io.launch.bits.limit.pad(66)||io.launch.bits.limit>(BigInt(1)<<56).U){fail(Status.Bounds.U)}.otherwise{state:=st("begin")}
  }
  when(state===st("begin")){
    token:=0.U;head:=0.U;key:=0.U;depth:=0.U;col:=0.U;sum:=0.U;lane:=0.U;clearAcc()
    when(phase===0.U||phase===9.U){state:=st("normLoad")}
    .elsewhen(phase===4.U||phase===5.U){state:=st("ropeStart")}
    .elsewhen(phase===6.U){state:=st("attQLoad")}
    .elsewhen(phase===8.U||phase===14.U){state:=st("resIssue")}
    .elsewhen(phase===12.U){state:=st("siluRead")}
    .otherwise{state:=st("denseLoad")}
  }
  when(state===st("advance")){io.stageCommit:=true.B;when(phase===14.U){state:=st("finish")}.otherwise{phase:=phase+1.U;state:=st("begin")}}
  when(state===st("finish")&&io.result.fire){state:=Mux(poisoned,st("locked"),st("idle"))}
  // RMSNorm: row SRAM, FP32 squared products and fixed sequential reduction.
  when(state===st("normLoad")){read(base+nIn+((rowOffset(s.hidden.U)+col).pad(64)<<2),"normGot")}
  when(state===st("normGot")){av:=packet.asTypeOf(av);localWrite(col>>4,packet,"normSquare")}
  when(state===st("normSquare")){vectorMul:=true.B;vectorB:=av;tmp:=vout;lane:=0.U;state:=st("normReduce")}
  when(state===st("normReduce")){calc(ScalarOp.Add,sum,tmp(lane),"normReduceDone")}
  when(state===st("normReduceDone")){sum:=scalarValue;when(lane===15.U){when(col+16.U<s.hidden.U){col:=col+16.U;state:=st("normLoad")}.otherwise{state:=st("normMean")}}.otherwise{lane:=lane+1.U;state:=st("normReduce")}}
  when(state===st("normMean")){calc(ScalarOp.Mul,sum,F32.lit(1.0/s.hidden),"normEps")}
  when(state===st("normEps")){calc(ScalarOp.Add,scalarValue,F32.lit(1e-6),"normSqrt")}
  when(state===st("normSqrt")){calc(ScalarOp.Sqrt,scalarValue,0.U,"normInv")}
  when(state===st("normInv")){calc(ScalarOp.Div,F32.lit(1),scalarValue,"normEmit");col:=0.U}
  when(state===st("normEmit")){scale:=scalarValue;localRead(col>>4,"normLocal")}
  when(state===st("normLocal")){read(base+gamma+(col.pad(64)<<2),"normGamma")}
  when(state===st("normGamma")){bv:=packet.asTypeOf(bv);state:=st("normScale")}
  when(state===st("normScale")){vectorMul:=true.B;vectorB:=VecInit(Seq.fill(16)(scale));tmp:=vout;state:=st("normProduct")}
  when(state===st("normProduct")){vectorMul:=true.B;vectorA:=tmp;write(base+nOut+((rowOffset(s.hidden.U)+col).pad(64)<<2),VecInit(vout.map(F32.bf)).asUInt,"normWritten")}
  when(state===st("normWritten")){
    when(col+16.U<s.hidden.U){col:=col+16.U;localRead((col+16.U)>>4,"normLocal")}
    .elsewhen(token+1.U<tokens){token:=token+1.U;col:=0.U;sum:=0.U;state:=st("normLoad")}.otherwise{state:=st("advance")}
  }
  // Dense projection, contiguous K order, 16 shared repository FMA lanes.
  when(state===st("denseLoad")){read(base+dIn+((rowOffset(dK)+col).pad(64)<<2),"denseGot")}
  when(state===st("denseGot")){localWrite(col>>4,packet,"denseLoaded")}
  when(state===st("denseLoaded")){when(col+16.U<dK){col:=col+16.U;state:=st("denseLoad")}.otherwise{col:=0.U;depth:=0.U;clearAcc();localRead(0.U,"denseLocal")}}
  when(state===st("denseLocal")){state:=st("denseWeight")}
  when(state===st("denseWeight")){read(base+dWeight+((depth.pad(32)*dN+col).pad(64)<<2),"denseCompute")}
  when(state===st("denseCompute")){fmA:=VecInit(Seq.fill(16)(av(depth(3,0))));fmB:=packet.asTypeOf(fmB)}
  when(state===st("denseCompute")&&fmDone){
    acc:=fmOut;macs:=macs+16.U
    when(depth+1.U===dK){when(phase<=3.U){state:=st("denseBias")}.otherwise{state:=st("denseWrite")}}
    .otherwise{depth:=depth+1.U;when(depth(3,0)===15.U){localRead((depth+1.U)>>4,"denseLocal")}.otherwise{state:=st("denseWeight")}}
  }
  when(state===st("denseBias")){read(base+bias+(col.pad(64)<<2),"denseBiasGot")}
  when(state===st("denseBiasGot")){vectorA:=acc;vectorB:=packet.asTypeOf(vectorB);acc:=vout;state:=st("denseWrite")}
  when(state===st("denseWrite")){write(base+dOut+((rowOffset(dN)+col).pad(64)<<2),acc.asUInt,"denseWritten")}
  when(state===st("denseWritten")){
    when(col+16.U<dN){col:=col+16.U;depth:=0.U;clearAcc();localRead(0.U,"denseLocal")}
    .elsewhen(token+1.U<tokens){token:=token+1.U;col:=0.U;state:=st("denseLoad")}.otherwise{state:=st("advance")}
  }
  // Half-split RoPE, four independently rounded multiplies and two adds.
  when(state===st("ropeStart")){read(base+ropeInput+(ropeIndex.pad(64)<<2),"ropeEven")}
  when(state===st("ropeEven")){av:=packet.asTypeOf(av);read(base+ropeInput+((ropeIndex+s.headDim.U/2.U).pad(64)<<2),"ropeOdd")}
  when(state===st("ropeOdd")){bv:=packet.asTypeOf(bv);read(ptr("cos",token.pad(32)*(s.headDim/2).U+col),"ropeCos")}
  when(state===st("ropeCos")){cv:=packet.asTypeOf(cv);read(ptr("sin",token.pad(32)*(s.headDim/2).U+col),"ropeSin")}
  when(state===st("ropeSin")){dv:=packet.asTypeOf(dv);state:=st("ropeMul0")}
  when(state===st("ropeMul0")){vectorMul:=true.B;vectorB:=cv;tmp:=vout;state:=st("ropeMul1")}
  when(state===st("ropeMul1")){vectorMul:=true.B;vectorA:=bv;vectorB:=dv;tmp2:=vout;state:=st("ropeAdd0")}
  when(state===st("ropeAdd0")){vectorA:=tmp;vectorB:=VecInit(tmp2.map(F32.neg));acc:=vout;state:=st("ropeAdd1")}
  when(state===st("ropeAdd1")){vectorMul:=true.B;vectorB:=dv;tmp:=vout;state:=st("ropeWrite0")}
  when(state===st("ropeWrite0")){vectorMul:=true.B;vectorA:=bv;vectorB:=cv;tmp2:=vout;write(base+ropeOutput+(ropeIndex.pad(64)<<2),acc.asUInt,"ropeWrite1")}
  when(state===st("ropeWrite1")){vectorA:=tmp;vectorB:=tmp2;write(base+ropeOutput+((ropeIndex+(s.headDim/2).U).pad(64)<<2),vout.asUInt,"ropeWritten")}
  when(state===st("ropeWritten")){
    when(col+16.U<(s.headDim/2).U){col:=col+16.U;state:=st("ropeStart")}
    .elsewhen(head+1.U<ropeHeads){head:=head+1.U;col:=0.U;state:=st("ropeStart")}
    .elsewhen(token+1.U<tokens){token:=token+1.U;head:=0.U;col:=0.U;state:=st("ropeStart")}.otherwise{state:=st("advance")}
  }
  // Causal GQA: one query/head resident; score/prob memories are only maxTokens.
  when(state===st("attQLoad")){read(ptr("q",rowOffset(s.hidden.U)+head*s.headDim.U+depth),"attQGot")}
  when(state===st("attQGot")){localWrite(depth>>4,packet,"attQStored")}
  when(state===st("attQStored")){when(depth+16.U<s.headDim.U){depth:=depth+16.U;state:=st("attQLoad")}.otherwise{key:=0.U;maxScore:="hff800000".U;state:=st("attKey")}}
  when(state===st("attKey")){depth:=0.U;clearAcc();localRead(0.U,"attLocal")}
  when(state===st("attLocal")){read(ptr("k",key.pad(32)*s.kv.U+kvHead*s.headDim.U+depth),"attDot")}
  when(state===st("attDot")){fmB:=packet.asTypeOf(fmB)}
  when(state===st("attDot")&&fmDone){acc:=fmOut;macs:=macs+16.U
    when(depth+16.U<s.headDim.U){depth:=depth+16.U;localRead((depth+16.U)>>4,"attLocal")}.otherwise{lane:=0.U;sum:=0.U;state:=st("attReduce")}}
  when(state===st("attReduce")){calc(ScalarOp.Add,sum,acc(lane),"attReduceDone")}
  when(state===st("attReduceDone")){sum:=scalarValue;when(lane===15.U){calc(ScalarOp.Mul,scalarValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}.otherwise{lane:=lane+1.U;state:=st("attReduce")}}
  when(state===st("attScore")){scores.write(key,scalarValue);when(F32.less(maxScore,scalarValue)){maxScore:=scalarValue};state:=st("attNextKey")}
  when(state===st("attNextKey")){when(key<token){key:=key+1.U;state:=st("attKey")}.otherwise{key:=0.U;sum:=0.U;state:=st("attExpRead")}}
  when(state===st("attExpRead")){state:=st("attExpWait")}
  when(state===st("attExpWait")){calc(ScalarOp.Add,scoreOut,F32.neg(maxScore),"attExpDiff")}
  when(state===st("attExpDiff")){calc(ScalarOp.ExpNegative,scalarValue,0.U,"attExpResult")}
  when(state===st("attExpResult")){probs.write(key,scalarValue);calc(ScalarOp.Add,sum,scalarValue,"attExpSum")}
  when(state===st("attExpSum")){sum:=scalarValue;when(key<token){key:=key+1.U;state:=st("attExpRead")}.otherwise{calc(ScalarOp.Div,F32.lit(1),scalarValue,"attInv")}}
  when(state===st("attInv")){scale:=scalarValue;col:=0.U;state:=st("attPVStart")}
  when(state===st("attPVStart")){clearAcc();key:=0.U;state:=st("attProbRead")}
  when(state===st("attProbRead")){state:=st("attProbWait")}
  when(state===st("attProbWait")){calc(ScalarOp.Mul,probOut,scale,"attProbScale")}
  when(state===st("attProbScale")){probability:=scalarValue;read(ptr("v",key.pad(32)*s.kv.U+kvHead*s.headDim.U+col),"attPVCompute")}
  when(state===st("attPVCompute")){fmA:=VecInit(Seq.fill(16)(probability));fmB:=packet.asTypeOf(fmB)}
  when(state===st("attPVCompute")&&fmDone){acc:=fmOut;macs:=macs+16.U
    when(key<token){key:=key+1.U;state:=st("attProbRead")}.otherwise{state:=st("attPVWrite")}}
  when(state===st("attPVWrite")){write(ptr("att",rowOffset(s.hidden.U)+head*s.headDim.U+col),acc.asUInt,"attPVWritten")}
  when(state===st("attPVWritten")){
    when(col+16.U<s.headDim.U){col:=col+16.U;state:=st("attPVStart")}
    .elsewhen(head+1.U<s.heads.U){head:=head+1.U;depth:=0.U;state:=st("attQLoad")}
    .elsewhen(token+1.U<tokens){token:=token+1.U;head:=0.U;depth:=0.U;state:=st("attQLoad")}.otherwise{state:=st("advance")}
  }
  // Stable SiLU: exp(-abs(g)), no overflow on the negative sigmoid branch.
  when(state===st("siluRead")){read(ptr("gate",rowOffset(s.ffn.U)+col),"siluGate")}
  when(state===st("siluGate")){av:=packet.asTypeOf(av);read(ptr("up",rowOffset(s.ffn.U)+col),"siluUp")}
  when(state===st("siluUp")){bv:=packet.asTypeOf(bv);lane:=0.U;state:=st("siluExp")}
  when(state===st("siluExp")){calc(ScalarOp.ExpNegative,av(lane),0.U,"siluDenom")}
  when(state===st("siluDenom")){probability:=scalarValue;calc(ScalarOp.Add,F32.lit(1),scalarValue,"siluInv")}
  when(state===st("siluInv")){calc(ScalarOp.Div,F32.lit(1),scalarValue,"siluSign")}
  when(state===st("siluSign")){calc(ScalarOp.Mul,scalarValue,Mux(av(lane)(31),probability,F32.lit(1)),"siluGateMul")}
  when(state===st("siluGateMul")){calc(ScalarOp.Mul,scalarValue,av(lane),"siluUpMul")}
  when(state===st("siluUpMul")){calc(ScalarOp.Mul,scalarValue,bv(lane),"siluNext")}
  when(state===st("siluNext")){tmp(lane):=scalarValue;when(lane===15.U){write(ptr("act",rowOffset(s.ffn.U)+col),Cat((0 until 16).reverse.map(i=>Mux(lane===i.U,scalarValue,tmp(i)))),"siluWritten")}.otherwise{lane:=lane+1.U;state:=st("siluExp")}}
  when(state===st("siluWritten")){when(col+16.U<s.ffn.U){col:=col+16.U;state:=st("siluRead")}.elsewhen(token+1.U<tokens){token:=token+1.U;col:=0.U;state:=st("siluRead")}.otherwise{state:=st("advance")}}
  when(state===st("resIssue")&&elem.io.job.fire){state:=st("resWait")}
  when(matrixFault){fail(Status.Protocol.U)}
  when(state===st("resWait")&&elem.io.done.fire){when(elem.io.done.bits.status=/=0.U){fail(elem.io.done.bits.status)}
    .elsewhen(elem.io.done.bits.tag=/=Cat(epoch,phase.pad(16))||elem.io.done.bits.elementCount=/=tokens*s.hidden.U||elem.io.done.bits.writeBytes=/=tokens.pad(64)*s.hidden.U*4.U){fail(Status.Protocol.U)}
    .otherwise{state:=st("advance")}}
}
