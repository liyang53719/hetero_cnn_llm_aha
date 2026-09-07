// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import scala.util.Random

/** Compact test-only port adapter. This does not implement any model arithmetic.
  * The actual production MatrixSliceJoin is tested, with independent slice
  * handshake stimuli and unique row/column reply patterns. Numerical MAC tests
  * use the retained arithmetic and pinned iDMA in HostBlockTop, not this probe. */
class MatrixSliceJoinProbe extends Module {
  val io=IO(new Bundle {
    val valid=Input(Bool());val ready=Output(Bool());val mask=Input(UInt(8.W))
    val clear=Input(Bool());val last=Input(Bool());val opcode=Input(UInt(8.W))
    val requestReady=Input(UInt(8.W));val replyValid=Input(UInt(8.W));val replyError=Input(UInt(8.W))
    val requestValid=Output(UInt(8.W));val replyReady=Output(UInt(8.W))
    val resultReady=Input(Bool());val resultValid=Output(Bool());val error=Output(Bool())
    val mismatch=Output(Bool());val badOperands=Output(Bool());val resetRequired=Output(Bool())
  })
  val dut=Module(new MatrixSliceJoin(256));val mask=RegEnable(io.mask,dut.io.request.fire)
  dut.io.request.valid:=io.valid;io.ready:=dut.io.request.ready
  dut.io.request.bits.sliceMask:=io.mask;dut.io.request.bits.clear:=io.clear
  dut.io.request.bits.last:=io.last;dut.io.request.bits.opcode:=io.opcode
  for(i<-0 until 16)dut.io.request.bits.a(i):=(i+1).U
  for(i<-0 until 256)dut.io.request.bits.b(i):=(100+i).U
  val bad=collection.mutable.ArrayBuffer.empty[Bool]
  for(i<-0 until 8){
    dut.io.sliceRequest(i).ready:=io.requestReady(i)
    dut.io.sliceResult(i).valid:=io.replyValid(i);dut.io.sliceResult(i).bits.error:=io.replyError(i)
    for(r<-0 until 16;c<-0 until 32)dut.io.sliceResult(i).bits.value(r)(c):=(r*256+i*32+c+1000).U
    for(j<-0 until 16)bad+=dut.io.sliceRequest(i).valid&&(dut.io.sliceRequest(i).bits.a(j)=/=(j+1).U)
    for(j<-0 until 32)bad+=dut.io.sliceRequest(i).valid&&(dut.io.sliceRequest(i).bits.b(j)=/=(100+i*32+j).U)
  }
  io.requestValid:=VecInit(dut.io.sliceRequest.map(_.valid)).asUInt
  io.replyReady:=VecInit(dut.io.sliceResult.map(_.ready)).asUInt
  dut.io.result.ready:=io.resultReady;io.resultValid:=dut.io.result.valid
  io.error:=dut.io.result.bits.error;io.resetRequired:=dut.io.resetRequired
  io.badOperands:=bad.reduce(_||_)
  io.mismatch:=(for(r<-0 until 16;c<-0 until 256)yield dut.io.result.bits.value(r)(c)=/=Mux(mask(c/32),(r*256+c+1000).U,0.U)).reduce(_||_)
}
class MatrixSliceJoinSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  def init(d:MatrixSliceJoinProbe):Unit={
    d.io.valid.poke(false.B);d.io.resultReady.poke(false.B);d.io.requestReady.poke(0.U);d.io.replyValid.poke(0.U);d.io.replyError.poke(0.U)
  }
  def put(d:MatrixSliceJoinProbe,mask:Int,clear:Boolean,last:Boolean,op:Int=0x20):Unit={
    d.io.ready.expect(true.B);d.io.mask.poke(mask.U);d.io.clear.poke(clear.B);d.io.last.poke(last.B);d.io.opcode.poke(op.U)
    d.io.valid.poke(true.B);d.clock.step();d.io.valid.poke(false.B)
  }
  def transfer(d:MatrixSliceJoinProbe,mask:Int,seed:Int=1,errorSlice:Int= -1):Unit={
    val rng=new Random(seed);var sent=0;var got=0;var cycles=0
    while(!d.io.resultValid.peek().litToBoolean && cycles<300){
      val ready=rng.nextInt(256)&mask&(~sent);val valid=rng.nextInt(256)&mask&sent&(~got)
      d.io.requestReady.poke(ready.U);d.io.replyValid.poke(valid.U)
      d.io.replyError.poke((if(errorSlice<0)0 else 1<<errorSlice).U)
      d.io.requestValid.expect((mask&(~sent)).U);d.io.badOperands.expect(false.B)
      val sr=d.io.requestValid.peek().litValue.toInt&ready
      val gr=d.io.replyReady.peek().litValue.toInt&valid
      d.clock.step();sent|=sr;got|=gr;cycles+=1
    }
    cycles should be < 300;sent shouldBe mask;got shouldBe mask
    d.io.requestReady.poke(0.U);d.io.replyValid.poke(0.U)
    for(_<-0 until 7){d.io.resultValid.expect(true.B);d.io.error.expect((errorSlice>=0).B);d.io.mismatch.expect(false.B);d.io.ready.expect(false.B);d.clock.step()}
    d.io.resultReady.poke(true.B);d.clock.step();d.io.resultReady.poke(false.B)
  }
  "MatrixSliceJoin" should "cover eight-slice mapping, independent backpressure, tail gating, K ordering, drain-on-error and reset recovery" in {
    test(new MatrixSliceJoinProbe).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d)
      put(d,255,true,true);transfer(d,255,111)
      for(k<-0 until 3){put(d,255,k==0,k==2);transfer(d,255,42+k)}
      for(mask<-Seq(1,3,15,127)){put(d,mask,true,true);transfer(d,mask,mask+3)}
      put(d,255,true,true);transfer(d,255,97,5);d.io.resetRequired.expect(true.B);d.io.ready.expect(false.B)
      for((mask,clear,op)<-Seq((0,true,0x20),(255,true,0xff),(255,false,0x20))){
        d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);init(d)
        put(d,mask,clear,true,op);d.io.resultValid.expect(true.B);d.io.error.expect(true.B);d.io.requestValid.expect(0.U)
        d.io.resultReady.poke(true.B);d.clock.step();d.io.resultReady.poke(false.B);d.io.ready.expect(false.B)
      }
      d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);init(d)
      put(d,255,true,false);transfer(d,255)
      put(d,1,false,true);d.io.resultValid.expect(true.B);d.io.error.expect(true.B);d.io.requestValid.expect(0.U)
      d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);init(d)
      put(d,255,true,true);transfer(d,255);d.io.ready.expect(true.B)
    }
  }
}
