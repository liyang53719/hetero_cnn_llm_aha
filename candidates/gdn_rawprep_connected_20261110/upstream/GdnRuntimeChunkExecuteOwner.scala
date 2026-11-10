// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Private retained scheduler input, never a host claim of producer authority.
  * predecessor is the actual previous phase receipt retained by the scheduler.
  * Sources/destinations are decoded internally, never host-selected M/N/K.
  */
class GdnRuntimeChunkExecuteJob extends Bundle {
  val context = new GdnChunkJob
  val layout = new GdnRuntimeChunkLayout
  val head = UInt(5.W)
  val chunk = UInt(1.W)
  val phase = UInt(5.W)
  val predecessorContext = new GdnChunkJob
  val predecessorLayout = new GdnRuntimeChunkLayout
  val predecessor = new GdnChunkStageReceipt
  val decay = new GdnRuntimeChunkPrivateDecay
}
class GdnRuntimeChunkExecuteResult extends Bundle {
  val context = new GdnChunkJob
  val layout = new GdnRuntimeChunkLayout
  val receipt = new GdnChunkStageReceipt
  val readBytes = UInt(64.W)
  val vectorRequests = UInt(32.W)
  val vectorResults = UInt(32.W)
  val cycles = UInt(64.W)
  val stageComplete = Bool()
}
class GdnRuntimeChunkExecutePort extends Bundle {
  val job = Flipped(Decoupled(new GdnRuntimeChunkExecuteJob))
  val committed = Input(new GdnChunkCommittedState)
  val memory = Decoupled(new MemoryRequest)
  val response = Flipped(Decoupled(new MemoryResponse))
  val vectorRequest = Decoupled(new UnifiedVectorRequestV2)
  val vectorResult = Flipped(Decoupled(new UnifiedVectorResultV2))
  val done = Decoupled(new GdnRuntimeChunkExecuteResult)
  val resetRequired = Output(Bool())
}

/** Common phases5..17. Exactly three512-bit payload registers; no arithmetic
  * Module, Matrix, SRAM or Scalar instance. The existing one Vector16 bank is
  * exclusively leased externally, with at most one request outstanding.
  * Every dot uses ascending K, separate FP32 Mul then Add from +0 (no FMA).
  * Unit-lower solve reads only already-ACKed earlier destination rows and never
  * divides by the stored diagonal. State remains FP32; only phase17 roundsBF16.
  * There are no synchronous host callbacks or token-by-token recurrent steps.
  *
  * Native VectorV2 has no identity beyond policy: the external scheduler/router
  * must ensure exclusive/no-stale ownership. DDR tag32/sequence32 checks this
  * transaction, not global replay. Any failure locks after held done until a
  * coordinated global reset/drain; this leaf cannot publish persistent roots.
  */
class GdnRuntimeChunkExecuteOwner extends Module {
  val io = IO(new GdnRuntimeChunkExecutePort)
  private val shapes = GdnChunkAddressPlan.Shapes
  private def offset(name: String): BigInt = {
    val i=shapes.indexWhere(_.name==name); require(i>=0)
    shapes.take(i).map(_.bytes).sum
  }
  private val chunkBytes=GdnChunkAddressPlan.PerHeadChunkBytes
  private val stateBytes=GdnChunkAddressPlan.PerHeadStateBytes
  require(chunkBytes==806912 && stateBytes==65536)
  private val phaseDefinitions=Seq(
    (5,"kb","kt","ut",64,64,128), (6,"q","kt","intra",64,64,128),
    (7,"ut","vb","solvev",64,128,64), (8,"ut","kbg","solvek",64,128,64),
    (9,"solvek","next_state","pred",64,128,128),
    (10,"solvev","pred","vnew",64,128,0),
    (11,"qg","next_state","inter",64,128,128),
    (12,"intra","vnew","local",64,128,64),
    (13,"inter","local","out",64,128,0),
    (14,"ket","vnew","state_update",128,128,64),
    (15,"next_state","gates","decay_state",128,128,0),
    (16,"decay_state","state_update","next_state",128,128,0),
    (17,"out","out","out",64,128,0))
  val idle :: issueRead :: waitRead :: issueVector :: waitVector :: issueWrite :: waitWrite :: finish :: locked :: Nil=Enum(9)
  val readA :: readB :: multiply :: accumulate :: readFactor :: factorMultiply :: readRhs :: solveSubtract :: binaryReadB :: binaryCompute :: materializeHigh :: Nil=Enum(11)
  val state=RegInit(idle);val step=RegInit(readA)
  val context=Reg(new GdnChunkJob);val layout=Reg(new GdnRuntimeChunkLayout)
  val head=Reg(UInt(5.W));val chunk=Reg(UInt(1.W));val phase=Reg(UInt(5.W))
  val chunkBase=Reg(UInt(64.W));val previousBase=Reg(UInt(64.W))
  val chunkDecay=Reg(UInt(32.W))
  val row=RegInit(0.U(7.W));val colBeat=RegInit(0.U(3.W));val k=RegInit(0.U(7.W))
  val a=Reg(UInt(512.W));val b=Reg(UInt(512.W));val total=Reg(UInt(512.W))
  val memorySequence=RegInit(0.U(32.W))
  val memoryOutstanding=RegInit(false.B);val vectorOutstanding=RegInit(false.B)
  val reads=RegInit(0.U(64.W));val writes=RegInit(0.U(64.W))
  val issued=RegInit(0.U(32.W));val returned=RegInit(0.U(32.W));val cycles=RegInit(0.U(64.W))
  val status=RegInit(Status.Ok.U(8.W))
  def decode(select: ((Int,String,String,String,Int,Int,Int))=>BigInt,width:Int): UInt =
    MuxLookup(phase,0.U(width.W))(phaseDefinitions.map(d=>d._1.U->select(d).U(width.W)))
  val rows=decode(d=>BigInt(d._5),8)
  val cols=decode(d=>BigInt(d._6),8)
  val reduction=decode(d=>BigInt(d._7),8)
  val solve=phase===7.U || phase===8.U
  val dot=phase===5.U || phase===6.U || phase===9.U || phase===11.U || phase===12.U || phase===14.U
  val factor=phase===5.U || phase===6.U
  val decayPhase=phase===15.U
  val outputPhase=phase===17.U
  val activeRows=Mux(outputPhase && context.tokens===16.U,16.U(8.W),rows)
  val beatsPerRow=Mux(outputPhase,4.U(4.W),cols>>4)
  val aCols=Mux(dot,reduction,Mux(solve,64.U(8.W),128.U(8.W)))
  val aBase=Mux(decayPhase,previousBase,chunkBase+decode(d=>offset(d._2),64))
  val bBase=Mux(phase===9.U || phase===11.U,previousBase,chunkBase+decode(d=>offset(d._3),64))
  val destination=chunkBase+decode(d=>offset(d._4),64)
  val aColumn=Mux(dot || solve,Cat(k(6,4),0.U(4.W)),Mux(outputPhase,colBeat<<5,colBeat<<4))
  val aAddress=aBase.pad(66)+((row*aCols+aColumn).pad(66)<<2)
  val bAddress=Mux(solve,destination,bBase).pad(66)+((k*cols+(colBeat<<4)).pad(66)<<2)
  val rhsAddress=bBase.pad(66)+((row*cols+(colBeat<<4)).pad(66)<<2)
  val pairAddress=chunkBase.pad(66)+offset("pair").U+((row.pad(66)<<8)+(colBeat.pad(66)<<6))
  val highAddress=aBase.pad(66)+((row.pad(66)<<9)+(colBeat.pad(66)<<7)+64.U)
  val readAddress=MuxLookup(step,aAddress)(Seq(readB->bAddress,readFactor->pairAddress,
    readRhs->rhsAddress,binaryReadB->rhsAddress,materializeHigh->highAddress))
  val scratchWriteAddress=destination.pad(66)+((row*cols+(colBeat<<4)).pad(66)<<2)
  val outputToken=(chunk.pad(66)<<6)+row.pad(66)
  val outputAddress=context.output.pad(66)+(((outputToken*layout.valueHeads+head).pad(66)<<8)+(colBeat.pad(66)<<6))
  val writeAddress=Mux(outputPhase,outputAddress,scratchWriteAddress)
  val requestedPolicy=Mux(context.vectorPolicy===GdnChunkVectorPolicy.FiniteGradualUnderflow.U,
    UnifiedVectorPolicyV2.RawFp32FiniteGradual.U,UnifiedVectorPolicyV2.LegacyRaw.U)
  val isMultiply=step===multiply || step===factorMultiply || (step===binaryCompute && decayPhase)
  val coefficient=a.asTypeOf(Vec(16,UInt(32.W)))(k(3,0))
  val negateTotal=total ^ Fill(16,"h80000000".U(32.W))
  val negateB=b ^ Fill(16,"h80000000".U(32.W))
  val vectorA=MuxLookup(step,a)(Seq(multiply->Fill(16,coefficient),accumulate->total,
    factorMultiply->total,solveSubtract->a))
  val vectorB=MuxLookup(step,b)(Seq(solveSubtract->negateTotal,
    binaryCompute->Mux(decayPhase,Fill(16,chunkDecay),Mux(phase===10.U,negateB,b))))
  io.vectorRequest.valid:=state===issueVector
  io.vectorRequest.bits.policy:=requestedPolicy;io.vectorRequest.bits.multiply:=isMultiply
  io.vectorRequest.bits.a:=vectorA.asTypeOf(Vec(16,UInt(32.W)))
  io.vectorRequest.bits.b:=vectorB.asTypeOf(Vec(16,UInt(32.W)))
  io.vectorResult.ready:=state===waitVector
  io.memory.valid:=state===issueRead || state===issueWrite
  io.memory.bits.write:=state===issueWrite
  io.memory.bits.address:=Mux(state===issueWrite,writeAddress,readAddress)(63,0)
  io.memory.bits.data:=Mux(state===issueWrite,total,0.U)
  io.memory.bits.mask:=Mux(state===issueWrite,Fill(64,1.U(1.W)),0.U)
  io.memory.bits.tag:=Cat(context.tag,memorySequence)
  io.response.ready:=state===waitRead || state===waitWrite
  val expectedWriteBytes=Mux(outputPhase,activeRows.pad(64)<<8,(rows*cols).pad(64)<<2)
  val dotReadBeats=(rows*(cols>>4)*(reduction+(reduction>>4)+factor.asUInt)).pad(64)
  val dotVectors=(rows*(cols>>4)*((reduction<<1)+factor.asUInt)).pad(32)
  val expectedReadBeats=Mux(dot,dotReadBeats,Mux(solve,17888.U(64.W),
    Mux(outputPhase,activeRows.pad(64)<<3,Mux(decayPhase,1024.U(64.W),(rows*(cols>>4)*2.U).pad(64)))))
  val expectedVectors=Mux(dot,dotVectors,Mux(solve,32768.U(32.W),
    Mux(outputPhase,0.U(32.W),(rows*(cols>>4)).pad(32))))
  val drained= !memoryOutstanding && !vectorOutstanding
  val complete=state===finish && status===Status.Ok.U && drained && writes===expectedWriteBytes &&
    reads===(expectedReadBeats<<6) && issued===expectedVectors && returned===expectedVectors
  io.job.ready:=state===idle
  io.done.valid:=state===finish
  io.done.bits.context:=context;io.done.bits.layout:=layout
  io.done.bits.receipt.tag:=context.tag;io.done.bits.receipt.expectedGeneration:=context.expectedGeneration
  io.done.bits.receipt.head:=head;io.done.bits.receipt.chunk:=chunk;io.done.bits.receipt.phase:=phase
  io.done.bits.receipt.status:=status
  io.done.bits.receipt.scratchAckBytes:=Mux(outputPhase,0.U,writes)
  io.done.bits.receipt.outputAckBytes:=Mux(outputPhase,writes,0.U)
  io.done.bits.receipt.stateAckBytes:=0.U
  io.done.bits.receipt.drained:=drained
  io.done.bits.readBytes:=reads;io.done.bits.vectorRequests:=issued;io.done.bits.vectorResults:=returned
  io.done.bits.cycles:=cycles;io.done.bits.stageComplete:=complete
  io.resetRequired:=status=/=Status.Ok.U
  def finiteBeat(x:UInt):Bool=(0 until 16).map(i=>TensorMath.finite(x(32*i+31,32*i))).reduce(_&&_)
  def fail(code:UInt):Unit={status:=code;state:=finish}
  def startOutput():Unit={
    k:=0.U;total:=0.U
    when(solve && row===0.U){step:=readRhs}.otherwise{step:=readA}
    state:=issueRead
  }
  when(state=/=idle && state=/=finish && state=/=locked){cycles:=cycles+1.U}
  when(io.job.fire){
    val j=io.job.bits;val c=j.context;val p=j.predecessor
    context:=c;layout:=j.layout;head:=j.head;chunk:=j.chunk;phase:=j.phase
    row:=0.U;colBeat:=0.U;k:=0.U;a:=0.U;b:=0.U;total:=0.U
    reads:=0.U;writes:=0.U;issued:=0.U;returned:=0.U;cycles:=0.U;status:=Status.Ok.U
    memorySequence:=0.U;memoryOutstanding:=false.B;vectorOutstanding:=false.B;chunkDecay:=j.decay.value
    val chunks=Mux(c.tokens===128.U,2.U,1.U)
    val stride=stateBytes.U(66.W)+(chunks*chunkBytes.U).pad(66)
    val hb=c.scratch.pad(66)+(j.head*stride).pad(66)
    val cb=hb+stateBytes.U+(j.chunk*chunkBytes.U).pad(66)
    chunkBase:=cb(63,0)
    previousBase:=Mux(j.chunk===0.U,hb,cb-chunkBytes.U+offset("next_state").U)(63,0)
    val spans=Seq((c.input,(c.tokens*j.layout.rowBytes).pad(66)),
      (c.stateIn,(j.layout.valueHeads*stateBytes.U).pad(66)),(c.stateOut,(j.layout.valueHeads*stateBytes.U).pad(66)),
      (c.output,(c.tokens*j.layout.valueHeads*256.U).pad(66)),(c.scratch,(j.layout.valueHeads*stride).pad(66)))
    val badSpan=spans.map{case(b,n)=>b(5,0)=/=0.U || n===0.U || b.pad(66)+n>(BigInt(1)<<56).U}.reduce(_||_)
    val aliases=(for(i<-spans.indices;z<-0 until i)yield spans(i)._1.pad(66)<spans(z)._1.pad(66)+spans(z)._2 && spans(z)._1.pad(66)<spans(i)._1.pad(66)+spans(i)._2).reduce(_||_)
    val rootBad=c.expectedGeneration=/=io.committed.generation || Mux(c.cold,
      c.expectedGeneration=/=0.U || io.committed.valid,c.expectedGeneration===0.U || !io.committed.valid || io.committed.state=/=c.stateIn)
    val beforeBytes=MuxLookup(j.phase,0.U(64.W))(Seq(5.U->32768.U,6.U->16384.U,7.U->16384.U,
      8.U->32768.U,9.U->32768.U,10.U->32768.U,11.U->32768.U,12.U->32768.U,
      13.U->32768.U,14.U->32768.U,15.U->65536.U,16.U->65536.U,17.U->65536.U))
    val predecessorGood=j.predecessorContext.asUInt===c.asUInt && j.predecessorLayout.asUInt===j.layout.asUInt &&
      p.tag===c.tag && p.expectedGeneration===c.expectedGeneration && p.head===j.head && p.chunk===j.chunk &&
      p.phase+&1.U===j.phase && p.status===Status.Ok.U && p.drained && p.scratchAckBytes===beforeBytes &&
      p.outputAckBytes===0.U && p.stateAckBytes===0.U
    val decayGood=j.decay.valid && j.decay.context.asUInt===c.asUInt && j.decay.layout.asUInt===j.layout.asUInt &&
      j.decay.head===j.head && j.decay.chunk===j.chunk && TensorMath.finite(j.decay.value) &&
      !j.decay.value(31) && j.decay.value<="h3f800000".U
    when(rootBad){fail(Status.Dependency.U)}
      .elsewhen((c.tokens=/=16.U && c.tokens=/=128.U) || !GdnRuntimeChunkLayout.admitted(j.layout) ||
        j.head>=j.layout.valueHeads || j.chunk>=chunks || j.phase<5.U || j.phase>17.U ||
        c.expectedGeneration==="hffffffff".U || badSpan || aliases){fail(Status.Bounds.U)}
      .elsewhen(!predecessorGood || (j.phase===15.U && !decayGood)){fail(Status.Dependency.U)}
      .elsewhen(io.response.valid || io.vectorResult.valid){fail(Status.Protocol.U)}
      .otherwise{step:=Mux(j.phase===7.U || j.phase===8.U,readRhs,readA);state:=issueRead}
  }
  when(io.memory.fire){memoryOutstanding:=true.B;state:=Mux(state===issueRead,waitRead,waitWrite)}
  when(io.response.fire){
    val r=io.response.bits
    when(r.tag=/=Cat(context.tag,memorySequence)){fail(Status.Protocol.U)}
      .elsewhen(r.error){memoryOutstanding:=false.B;fail(Status.Memory.U)}
      .otherwise{
        memoryOutstanding:=false.B;memorySequence:=memorySequence+1.U
        when(state===waitWrite){
          writes:=writes+64.U
          when(colBeat+&1.U===beatsPerRow){
            colBeat:=0.U
            when(row+&1.U===activeRows){
              when(writes+64.U===expectedWriteBytes && reads===(expectedReadBeats<<6) &&
                issued===expectedVectors && returned===expectedVectors && !vectorOutstanding){state:=finish}
                .otherwise{fail(Status.Protocol.U)}
            }
              .otherwise{row:=row+1.U;k:=0.U;total:=0.U;step:=readA;state:=issueRead}
          }.otherwise{colBeat:=colBeat+1.U;startOutput()}
        }.otherwise{
          reads:=reads+64.U
          when(!finiteBeat(r.data)){fail(Status.Numerical.U)}.otherwise{
            switch(step){
              is(readA){a:=r.data
                when(dot || solve){step:=readB;state:=issueRead}
                  .elsewhen(outputPhase){step:=materializeHigh;state:=issueRead}
                  .elsewhen(decayPhase){step:=binaryCompute;state:=issueVector}
                  .otherwise{step:=binaryReadB;state:=issueRead}
              }
              is(readB){b:=r.data;step:=multiply;state:=issueVector}
              is(readFactor){b:=r.data;step:=factorMultiply;state:=issueVector}
              is(readRhs){a:=r.data;step:=solveSubtract;state:=issueVector}
              is(binaryReadB){b:=r.data;step:=binaryCompute;state:=issueVector}
              is(materializeHigh){
                val words=Cat(r.data,a).asTypeOf(Vec(32,UInt(32.W)))
                val packed=VecInit(words.map(TensorMath.bf16Rne))
                when(packed.map(x=>x(14,7)==="hff".U).reduce(_||_)){fail(Status.Numerical.U)}
                  .otherwise{total:=packed.asUInt;state:=issueWrite}
              }
            }
          }
        }
      }
  }
  when(io.vectorRequest.fire){vectorOutstanding:=true.B;issued:=issued+1.U;state:=waitVector}
  when(io.vectorResult.fire){
    val r=io.vectorResult.bits
    when(r.policy=/=requestedPolicy){fail(Status.Protocol.U)}
      .elsewhen(r.error || !finiteBeat(r.value.asUInt)){vectorOutstanding:=false.B;returned:=returned+1.U;fail(Status.Numerical.U)}
      .otherwise{
        vectorOutstanding:=false.B;returned:=returned+1.U
        switch(step){
          is(multiply){b:=r.value.asUInt;step:=accumulate;state:=issueVector}
          is(accumulate){
            total:=r.value.asUInt
            val limit=Mux(solve,row.pad(8),reduction)
            when(k+&1.U===limit){
              when(solve){step:=readRhs;state:=issueRead}
                .elsewhen(factor){step:=readFactor;state:=issueRead}
                .otherwise{state:=issueWrite}
            }.otherwise{k:=k+1.U;step:=Mux(k(3,0)===15.U,readA,readB);state:=issueRead}
          }
          is(factorMultiply){total:=r.value.asUInt;state:=issueWrite}
          is(solveSubtract){total:=r.value.asUInt;state:=issueWrite}
          is(binaryCompute){total:=r.value.asUInt;state:=issueWrite}
        }
      }
  }
  when(io.done.fire){state:=Mux(status===Status.Ok.U && complete,idle,locked)}
}
