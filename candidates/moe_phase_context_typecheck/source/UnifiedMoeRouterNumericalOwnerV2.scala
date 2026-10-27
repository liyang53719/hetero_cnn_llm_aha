// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import gemmini.HeteroFp32Order

class UnifiedMoeRouterNumericResultV2 extends Bundle {
  val transactionId=UInt(64.W);val ownerSequence=UInt(32.W)
  val rows=UInt(8.W);val emittedRoutes=UInt(11.W);val status=UInt(8.W);val drained=Bool()
  val scalarIssued=UInt(33.W);val scalarReturned=UInt(33.W);val expectedScalarOperations=UInt(32.W)
  val ambiguousCutoffRows=UInt(8.W)
}
/** Original full-M router arithmetic control candidate. A single accepted
  * M<=128 job consumes all8 DDR beats/all256 BF16 logits per row. It is not
  * repeated completeblock M1. All256 FP32 probabilities are materialized BEFORE
  * sharedTopK start. Exp uses sharedScalar policy1/op4, then CPU_DEFAULT width8
  * stride8 sums, ascending lane collapse, reciprocal and256 separate FP32 Mul.
  * Top8 values are summed ascending rank, independently divided, then BF16 RNE.
  *
  * IMPORTANT: P7 exp is not std::exp bit-equivalence; stable index tie order is
  * not Torch cutoff tie equivalence. No tolerance is introduced by this source.
  * Full numeric/route comparison remains REQUIRED before enabling production.
  * ONE 256x32-bit row buffer, eight32-bit sums, eight scores/IDs and state are
  * new control/storage cost. No Scalar/Vector/TopK/formatter/Matrix instance.
  * Scalar serialization is initial functional control, NOT performance proof;
  * vectorized lowering may preserve this node order on the same shared bank.
  * Raw service IO requires parent exclusive fulltxn/ownerSequence lease and
  * original pending attribution. Unknown responses quarantine, never relabel.
  */
class UnifiedMoeRouterNumericalOwnerV2 extends Module {
  val io=IO(new Bundle {
    val begin=Flipped(Decoupled(new UnifiedMoeRouterLogitCommitV2))
    val logits=Flipped(Decoupled(new UnifiedMoeRouterLogitBeatV2))
    val scalar=new UnifiedScalarClientV2
    val selection=new UnifiedMoeRouterSelectionClientV2
    val format=new UnifiedMoeRouterFormatClientV2
    val sourceResetRequired=Input(Bool())
    val route=Decoupled(new UnifiedMoeSelectedRouteV2)
    val done=Decoupled(new UnifiedMoeRouterNumericResultV2)
    val resetRequired=Output(Bool());val contextReserved=Output(Bool())
    // V3 private parent attribution: no16bit serial wrapping across fullM128.
    val scalarOperationOrdinal=Output(UInt(32.W));val arithmeticToken=Output(UInt(32.W))
    val arithmeticPhase=Output(UInt(5.W))
  })
  val ss=Enum(14)
  val idle=ss(0);val load=ss(1);val maximum=ss(2);val compute=ss(3);val waitScalar=ss(4)
  val selectStart=ss(5);val selectFeed=ss(6);val selectRead=ss(7);val formatIssue=ss(8)
  val formatWait=ss(9);val emit=ss(10);val report=ss(11);val locked=ss(12);val validateSelection=ss(13)
  val state=RegInit(idle);val phase=Reg(UInt(3.W))
  val command=Reg(new UnifiedMoeRouterDenseCommandV2)
  val row=Reg(Vec(256,UInt(32.W)));val sums=Reg(Vec(8,UInt(32.W)))
  val scores=Reg(Vec(8,UInt(32.W)));val experts=Reg(Vec(8,UInt(8.W)))
  val token=Reg(UInt(7.W));val beat=Reg(UInt(3.W));val index=Reg(UInt(8.W));val rank=Reg(UInt(3.W))
  val maxValue=Reg(UInt(32.W));val temporary=Reg(UInt(32.W));val denominator=Reg(UInt(32.W))
  val reciprocal=Reg(UInt(32.W));val routeWeight=Reg(UInt(16.W))
  val aboveCount=Reg(UInt(9.W));val equalCount=Reg(UInt(9.W))
  val result=Reg(new UnifiedMoeRouterNumericResultV2)
  val poison=RegInit(false.B);val quarantine=RegInit(false.B)
  val selectOwned=RegInit(false.B)
  val unknownScalar=io.scalar.result.valid && state=/=waitScalar
  val unknownFormat=io.format.result.valid && state=/=formatWait
  val unknownSelection=io.selection.out.valid && state=/=selectRead
  val unknown=unknownScalar||unknownFormat||unknownSelection
  when(unknown){poison:=true.B;quarantine:=true.B}
  when(io.sourceResetRequired || io.selection.invalidConfig){poison:=true.B}
  val fault=poison||quarantine||unknown||io.sourceResetRequired||io.selection.invalidConfig
  io.resetRequired:=fault;io.contextReserved:=state=/=idle || io.begin.valid
  io.scalarOperationOrdinal:=result.scalarIssued(31,0);io.arithmeticToken:=token;io.arithmeticPhase:=phase
  io.begin.ready:=state===idle && !fault && !io.selection.busy
  io.logits.ready:=state===load && !fault
  io.scalar.request.valid:=state===compute && !result.scalarIssued(32) // held until actualfire;33bit counter never silently wraps
  io.scalar.request.bits:=0.U.asTypeOf(new UnifiedScalarRequestV2)
  io.scalar.request.bits.payload.op:=ScalarOp.Add.U
  switch(phase){
    is(0.U){io.scalar.request.bits.payload.a:=row(index);io.scalar.request.bits.payload.b:=maxValue ^ "h80000000".U}
    is(1.U){io.scalar.request.bits.policy:=UnifiedScalarPolicyV2.GradualDecay.U;io.scalar.request.bits.payload.op:=ScalarOp.ExpNegative.U;io.scalar.request.bits.payload.a:=temporary}
    is(2.U){io.scalar.request.bits.payload.a:=sums(index(2,0));io.scalar.request.bits.payload.b:=temporary}
    is(3.U){io.scalar.request.bits.payload.a:=denominator;io.scalar.request.bits.payload.b:=sums(rank)}
    is(4.U){io.scalar.request.bits.payload.op:=ScalarOp.Div.U;io.scalar.request.bits.payload.a:="h3f800000".U;io.scalar.request.bits.payload.b:=denominator}
    is(5.U){io.scalar.request.bits.payload.op:=ScalarOp.MulIeeeRne.U;io.scalar.request.bits.payload.a:=row(index);io.scalar.request.bits.payload.b:=reciprocal}
    is(6.U){io.scalar.request.bits.payload.a:=denominator;io.scalar.request.bits.payload.b:=scores(rank)}
    is(7.U){io.scalar.request.bits.payload.op:=ScalarOp.Div.U;io.scalar.request.bits.payload.a:=scores(rank);io.scalar.request.bits.payload.b:=denominator}
  }
  io.scalar.result.ready:=state===waitScalar && !quarantine
  io.selection.start:=state===selectStart && !fault
  io.selection.itemCount:=256.U;io.selection.k:=8.U
  io.selection.in.valid:=state===selectFeed // started selector must actually drain
  io.selection.in.bits.score:=row(index);io.selection.in.bits.index:=index
  io.selection.out.ready:=state===selectRead && !quarantine
  io.format.request.valid:=state===formatIssue;io.format.request.bits.value:=temporary
  io.format.result.ready:=state===formatWait && !quarantine
  io.route.valid:=state===emit;io.route.bits.transactionId:=command.context.transactionId
  io.route.bits.token:=token;io.route.bits.rank:=rank;io.route.bits.expert:=experts(rank)
  io.route.bits.weight:=routeWeight
  io.done.valid:=state===report;io.done.bits:=result
  def fail(status:UInt):Unit={result.status:=status;result.drained:= !selectOwned && !quarantine && !unknown;poison:=true.B;state:=report}
  def nextExp():Unit={
    when(index===255.U){denominator:=sums(0);rank:=1.U;phase:=3.U;state:=compute}
    .otherwise{index:=index+1.U;phase:=0.U;state:=compute}
  }
  val (decoded,shapeLegal)=UnifiedMoeRouterDenseCommandV2.decode(io.begin.bits.command)
  when(io.begin.fire){
    command:=io.begin.bits.command;token:=0.U;beat:=0.U;selectOwned:=false.B
    result:=0.U.asTypeOf(new UnifiedMoeRouterNumericResultV2)
    result.transactionId:=io.begin.bits.command.context.transactionId
    result.ownerSequence:=io.begin.bits.command.ownerSequence
    result.expectedScalarOperations:=io.begin.bits.command.context.tokens*1040.U
    val good=shapeLegal && io.begin.bits.successfulWriteback &&
      io.begin.bits.result.status===Status.Ok.U && io.begin.bits.result.tag===decoded.tag &&
      io.begin.bits.result.writeBytes===decoded.writeBytes
    when(good){state:=load}.otherwise{fail(Status.Dependency.U)}
  }
  when(io.logits.fire){
    val b=io.logits.bits
    val finite=(0 until 32).map(i=>b.data(i*16+14,i*16+7)=/="hff".U).reduce(_&&_)
    val good=b.transactionId===command.context.transactionId && b.ownerSequence===command.ownerSequence &&
      b.token===token && b.beat===beat && finite
    when(good){
      for(i<-0 until 32){row(Cat(beat,i.U(5.W))):=Cat(b.data(i*16+15,i*16),0.U(16.W))}
      when(beat===7.U){index:=0.U;maxValue:="hff800000".U;state:=maximum}.otherwise{beat:=beat+1.U}
    }.otherwise{fail(Status.Protocol.U)}
  }
  when(state===maximum){
    when(fault){fail(Status.Dependency.U)}.otherwise{
      when(HeteroFp32Order.key(row(index))>HeteroFp32Order.key(maxValue)){maxValue:=row(index)}
      when(index===255.U){index:=0.U;phase:=0.U;state:=compute}.otherwise{index:=index+1.U}
    }
  }
  when(io.scalar.request.fire){result.scalarIssued:=result.scalarIssued+1.U;state:=waitScalar}
  when(state===compute && result.scalarIssued(32)){fail(Status.Bounds.U)}
  when(io.scalar.result.fire){
    result.scalarReturned:=result.scalarReturned+1.U
    val r=io.scalar.result.bits;val expectedPolicy=Mux(phase===1.U,1.U,0.U)
    val bad=r.policy=/=expectedPolicy || r.error || !TensorMath.finite(r.value)
    when(bad || fault){fail(Mux(bad,Status.Numerical.U,Status.Dependency.U))}.otherwise{
      state:=compute
      switch(phase){
        is(0.U){temporary:=r.value;phase:=1.U}
        is(1.U){
          row(index):=r.value;temporary:=r.value
          when(index<8.U){sums(index(2,0)):=r.value;nextExp()}.otherwise{phase:=2.U}
        }
        is(2.U){sums(index(2,0)):=r.value;nextExp()}
        is(3.U){denominator:=r.value;when(rank===7.U){phase:=4.U}.otherwise{rank:=rank+1.U}}
        is(4.U){reciprocal:=r.value;index:=0.U;phase:=5.U}
        is(5.U){
          row(index):=r.value
          when(r.value(31) || r.value>"h3f800000".U){fail(Status.Numerical.U)}
          .elsewhen(index===255.U){index:=0.U;state:=selectStart}.otherwise{index:=index+1.U}
        }
        is(6.U){denominator:=r.value;when(rank===7.U){rank:=0.U;phase:=7.U}.otherwise{rank:=rank+1.U}}
        is(7.U){
          when(r.value(31) || r.value>"h3f800000".U){fail(Status.Numerical.U)}
          .otherwise{temporary:=r.value;state:=formatIssue}
        }
      }
    }
  }
  when(state===selectStart && fault){fail(Status.Dependency.U)}
  when(io.selection.start && io.selection.startReady){selectOwned:=true.B;index:=0.U;state:=selectFeed}
  when(io.selection.in.fire){when(index===255.U){rank:=0.U;state:=selectRead}.otherwise{index:=index+1.U}}
  when(io.selection.out.fire){
    val r=io.selection.out.bits
    val duplicate=(0 until 8).map(i=>i.U<rank && experts(i)===r.index(7,0)).reduce(_||_)
    val good=r.index<256.U && r.rank===rank && r.last===(rank===7.U) &&
      r.score===row(r.index(7,0)) && !duplicate && !r.score(31) && r.score<="h3f800000".U &&
      (rank===0.U || !HeteroFp32Order.better(r.score,r.index,scores(rank-1.U),experts(rank-1.U)))
    scores(rank):=r.score;experts(rank):=r.index(7,0)
    when(!good){poison:=true.B}
    when(rank===7.U){
      // Primitive done is asserted only with its true last output handshake.
      when(!io.selection.done){poison:=true.B;quarantine:=true.B;state:=locked}
      .otherwise{
        selectOwned:=false.B
        when(fault || !good){result.status:=Status.Protocol.U;result.drained:= !quarantine && !unknown;state:=report}
        .otherwise{index:=0.U;aboveCount:=0.U;equalCount:=0.U;state:=validateSelection}
      }
    }.otherwise{rank:=rank+1.U}
  }
  when(state===validateSelection){
    // Independently validate membership against ALL256 materialized probabilities.
    // Legal cutoff ties remain observable and are not called Torch ID equality.
    val above=aboveCount+(row(index)>scores(7)).asUInt
    val equal=equalCount+(row(index)===scores(7)).asUInt
    aboveCount:=above;equalCount:=equal
    when(fault){fail(Status.Dependency.U)}.elsewhen(index===255.U){
      val selectedAbove=PopCount((0 until 8).map(i=>scores(i)>scores(7)))
      when(above=/=selectedAbove || above>=8.U || above+&equal<8.U){fail(Status.Protocol.U)}
      .otherwise{
        when(above+&equal>8.U){result.ambiguousCutoffRows:=result.ambiguousCutoffRows+1.U}
        denominator:=0.U;rank:=0.U;phase:=6.U;state:=compute
      }
    }.otherwise{index:=index+1.U}
  }
  when(io.format.request.fire){state:=formatWait}
  when(io.format.result.fire){
    when(fault || io.format.result.bits.error || io.format.result.bits.value(15) || io.format.result.bits.value>"h3f80".U){fail(Status.Numerical.U)}
    .otherwise{routeWeight:=io.format.result.bits.value;state:=emit}
  }
  when(io.route.fire){
    result.emittedRoutes:=result.emittedRoutes+1.U
    when(fault){fail(Status.Dependency.U)}.elsewhen(rank===7.U){
      result.rows:=result.rows+1.U
      when(token.pad(16)+1.U===command.context.tokens){
        val countsGood=result.scalarIssued===result.expectedScalarOperations && result.scalarReturned===result.scalarIssued
        result.status:=Mux(countsGood,Status.Ok.U,Status.Protocol.U)
        when(!countsGood){poison:=true.B}
        result.drained:=true.B;state:=report
      }
      .otherwise{token:=token+1.U;beat:=0.U;state:=load}
    }.otherwise{rank:=rank+1.U;phase:=7.U;state:=compute}
  }
  when(io.done.fire){state:=Mux(fault,locked,idle)}
  // This owner cannot prove upstream read-stream drained or DDR route-map ACK.
  // Parent final router fence must join reader.done, numeric.done, route.done and
  // shared resource lease drain, with current sticky poison. No local reset.
}
