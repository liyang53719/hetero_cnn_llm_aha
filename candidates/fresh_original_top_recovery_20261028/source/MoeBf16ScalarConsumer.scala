package heteronpu.continuous
import chisel3._
import chisel3.util._

class MoeBf16TileIdentity extends Bundle {
  val transactionId=UInt(64.W);val token=UInt(32.W);val tileOrdinal=UInt(16.W)
}
class MoeBf16TileJob extends Bundle {
  val identity=new MoeBf16TileIdentity
  val contributionCount=UInt(5.W)
}
class MoeBf16TileContribution extends Bundle {
  val identity=new MoeBf16TileIdentity
  val routeTag=UInt(4.W);val weight=UInt(32.W);val data=UInt(512.W)
  val first=Bool();val last=Bool()
}
class MoeBf16SourceFailure extends Bundle {
  val identity=new MoeBf16TileIdentity;val status=UInt(8.W);val drained=Bool()
}
class MoeBf16TileResult extends Bundle {
  val identity=new MoeBf16TileIdentity;val data=UInt(512.W);val status=UInt(8.W)
}
/** One fixed 32-BF16 tile consumer, sharing (not instantiating) the existing
  * scalar service. Every expert product and every separate expert addition
  * materializes BF16 RNE. Caller must supply expert-ID order with shared last.
  * This module does not compute experts, select routes, or grow a MAC array.
  * Scalar arbitration must retain the one-outstanding response ownership;
  * the legacy ScalarRequest/UInt32 response has no embedded transaction tag.
  * There is no internal timeout: a missing legitimate contribution waits for
  * parent watchdog/isolation and an authentic drained failure receipt. It can
  * never turn timeout or bare producer error into success/early publication.
  * Generic contributionCount is 1..16; a MoE gateway must admit only8/9
  * before launching this consumer and its fixed-top8 order controller.
  * No destructive clear port: reset is only legal after the parent drains.
  * Numerical support is exactly the existing scalar finite-domain policy;
  * errors (including Add underflow flags) are never silently ignored.
  */
class MoeBf16ScalarConsumer extends Module {
  val io=IO(new Bundle {
    val job=Flipped(Decoupled(new MoeBf16TileJob))
    val contribution=Flipped(Decoupled(new MoeBf16TileContribution))
    val result=Decoupled(new MoeBf16TileResult)
    val sourceFailure=Flipped(Decoupled(new MoeBf16SourceFailure))
    val rejectedFailure=Output(Bool())
    val scalarRequest=Decoupled(new ScalarRequest)
    val scalarResult=Flipped(Decoupled(UInt(32.W)))
    val scalarError=Input(Bool())
    val busy=Output(Bool());val staleContributionRejected=Output(Bool())
  })
  val sIdle::sLoad::sMulIssue::sMulWait::sAddIssue::sAddWait::sDrain::sDone::Nil=Enum(8)
  val state=RegInit(sIdle);val identity=Reg(new MoeBf16TileIdentity)
  val count=Reg(UInt(5.W));val received=RegInit(0.U(5.W));val seen=RegInit(0.U(16.W))
  val lane=RegInit(0.U(5.W));val data=Reg(UInt(512.W));val weight=Reg(UInt(16.W));val product=Reg(UInt(16.W))
  val accum=Reg(Vec(32,UInt(16.W)));val status=RegInit(Status.Ok.U(8.W))
  val selected=(data >> (lane << 4))(15,0)
  val productBf16=TensorMath.bf16Rne(io.scalarResult.bits)
  val finiteResult=TensorMath.finite(io.scalarResult.bits) && productBf16(14,7)=/=255.U
  io.job.ready:=state===sIdle;io.busy:=state=/=sIdle
  io.contribution.ready:=state===sLoad || state===sDrain
  val sameIdentity=io.contribution.bits.identity.asUInt===identity.asUInt
  val validUniqueTag=io.contribution.bits.routeTag<count && !seen(io.contribution.bits.routeTag)
  val acceptedContribution=io.contribution.fire && sameIdentity && validUniqueTag
  io.staleContributionRejected:=io.contribution.fire && !sameIdentity
  val safeFailureBoundary=state===sLoad || state===sDrain
  val validFailure=io.sourceFailure.bits.identity.asUInt===identity.asUInt &&
    io.sourceFailure.bits.drained && io.sourceFailure.bits.status>=Status.Malformed.U &&
    io.sourceFailure.bits.status<=Status.Permission.U
  // A malformed/stale failure can be dropped alongside a real contribution.
  // A valid drained failure cannot consume/replace a competing contribution.
  io.sourceFailure.ready:=safeFailureBoundary && (!validFailure || !io.contribution.valid)
  io.rejectedFailure:=io.sourceFailure.fire && !validFailure
  io.result.valid:=state===sDone;io.result.bits.identity:=identity
  io.result.bits.data:=Mux(status===Status.Ok.U,accum.asUInt,0.U);io.result.bits.status:=status
  io.scalarRequest.valid:=state===sMulIssue || state===sAddIssue
  io.scalarRequest.bits.op:=Mux(state===sMulIssue,ScalarOp.MulIeeeRne.U,ScalarOp.Add.U)
  io.scalarRequest.bits.a:=Mux(state===sMulIssue,Cat(selected,0.U(16.W)),Cat(accum(lane),0.U(16.W)))
  io.scalarRequest.bits.b:=Mux(state===sMulIssue,Cat(weight,0.U(16.W)),Cat(product,0.U(16.W)))
  io.scalarResult.ready:=state===sMulWait || state===sAddWait
  def failAfterResponse():Unit={status:=Status.Numerical.U;state:=Mux(received>=count,sDone,sDrain)}
  // Neither stale epochs nor duplicate/out-of-range route tags spend current
  // job drain credit. Only unique current-job contributions retire a slot.
  when(io.contribution.fire && sameIdentity && !validUniqueTag){
    when(status===Status.Ok.U){status:=Status.Protocol.U};state:=sDrain
  }
  switch(state){
    is(sIdle){when(io.job.fire){
      identity:=io.job.bits.identity;count:=io.job.bits.contributionCount;received:=0.U;seen:=0.U;lane:=0.U;status:=Status.Ok.U
      for(i<-0 until 32){accum(i):=0.U}
      when(io.job.bits.contributionCount===0.U || io.job.bits.contributionCount>16.U){status:=Status.Malformed.U;state:=sDone}
        .otherwise{state:=sLoad}
    }}
    is(sLoad){when(acceptedContribution){
      val c=io.contribution.bits
      val markersOk=c.first===(received===0.U) && c.last===((received +& 1.U)>=count)
      val finiteData=(0 until 32).map(i=>c.data(16*i+14,16*i+7)=/=255.U).reduce(_&&_)
      val canonical=c.weight(31,16)===0.U && c.weight(14,7)=/=255.U && finiteData
      received:=received+1.U;seen:=seen | (1.U(16.W)<<c.routeTag)
      when(!markersOk || !canonical){
        status:=Mux(!canonical,Status.Numerical.U,Status.Protocol.U)
        state:=Mux((received +& 1.U)>=count,sDone,sDrain)
      }.otherwise{data:=c.data;weight:=c.weight(15,0);lane:=0.U;state:=sMulIssue}
    }}
    is(sMulIssue){when(io.scalarRequest.fire){state:=sMulWait}}
    is(sMulWait){when(io.scalarResult.fire){
      when(io.scalarError || !finiteResult){failAfterResponse()}
        .otherwise{product:=productBf16;state:=sAddIssue}
    }}
    is(sAddIssue){when(io.scalarRequest.fire){state:=sAddWait}}
    is(sAddWait){when(io.scalarResult.fire){
      when(io.scalarError || !finiteResult){failAfterResponse()}
        .otherwise{accum(lane):=productBf16
          when(lane===31.U){state:=Mux(received>=count,sDone,sLoad)}
            .otherwise{lane:=lane+1.U;state:=sMulIssue}
        }
    }}
    is(sDrain){when(acceptedContribution){
      received:=received+1.U;seen:=seen | (1.U(16.W)<<io.contribution.bits.routeTag)
      when((received +& 1.U)>=count){state:=sDone}
    }}
    is(sDone){when(io.result.fire){state:=sIdle}}
  }
  // Only a real producer's identity-bound, drained failure receipt may end a
  // missing-contribution wait. No scalar request/response is outstanding in
  // Load/Drain. Error data are invalid (zero), never a published numeric tile.
  when(io.sourceFailure.fire && validFailure){
    when(status===Status.Ok.U){status:=io.sourceFailure.bits.status}
    state:=sDone
  }

}
