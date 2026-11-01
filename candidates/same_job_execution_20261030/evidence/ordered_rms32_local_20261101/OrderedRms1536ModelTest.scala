package heteronpu.continuous
import chisel3._
import chisel3.util._
import chiseltest._
import chiseltest.simulator.{VerilatorBackendAnnotation,VerilatorCFlags}

class OrderedRms1536BankFixture extends Module {
  val io=IO(new Bundle {
    val start=Flipped(Decoupled(Bool()))
    val read=Decoupled(UInt(7.W))
    val readResult=Flipped(Decoupled(Vec(16,UInt(32.W))))
    val acceptedVectorOperations=Output(UInt(16.W))
    val result=Decoupled(new Bundle {val sum=UInt(32.W);val error=Bool()})
  })
  val r=Module(new OrderedRms1536Reduction32)
  val bank=Module(new UnifiedVectorElement32BankV4)
  val accepted=RegInit(0.U(16.W));when(io.start.fire){accepted:=0.U}.elsewhen(bank.io.request.fire){accepted:=accepted+1.U};io.acceptedVectorOperations:=accepted
  val bridge=Module(new OrderedRmsSramReadBridge32)
  bridge.io.active:= !r.io.drained;bridge.io.externalUnexpected:=false.B
  bridge.io.request<>r.io.read;r.io.readResult<>bridge.io.response
  io.read<>bridge.io.physicalRequest
  bridge.io.physicalResponse.valid:=io.readResult.valid;bridge.io.physicalResponse.bits:=io.readResult.bits.asUInt
  io.readResult.ready:=bridge.io.physicalResponse.ready
  r.io.abort:=bridge.io.resetRequired;r.io.vectorPublished:=r.io.vector.valid;r.io.start<>io.start
  io.result.valid:=r.io.result.valid;io.result.bits.sum:=r.io.result.bits.sum;io.result.bits.error:=r.io.result.bits.error;r.io.result.ready:=io.result.ready
  bank.io.request.valid:=r.io.vector.valid;bank.io.request.bits.identity:=0.U.asTypeOf(new UnifiedSharedOperationTagV3)
  bank.io.request.bits.payload:=r.io.vector.bits;r.io.vector.ready:=bank.io.request.ready
  r.io.vectorResult.valid:=bank.io.result.valid;r.io.vectorResult.bits:=bank.io.result.bits.payload;bank.io.result.ready:=r.io.vectorResult.ready
}
object OrderedRms1536ModelTest extends App {
  def bits(x:Float):BigInt=BigInt(java.lang.Integer.toUnsignedLong(java.lang.Float.floatToRawIntBits(x)))
  def scalarGold(x:Seq[Float]):Float={
    var total=0.0f
    for(l<-0 until 8){var ls=0.0f
      for(r<-0 until 4){var rs=0.0f
        for(b<-0 until 3){var p=0.0f
          for(t<-0 until 16){val v=x(b*512+t*32+r*8+l);val q:Float=v*v;p=(p+q).toFloat}
          rs=(rs+p).toFloat
        };ls=(ls+rs).toFloat
      };total=(total+ls).toFloat
    };total
  }
  val random=new scala.util.Random(1536)
  val cases=Seq(
    Seq.fill(1536)(1.0f),
    (0 until 1536).map(i=>if(i%2==0) -0.0f else 0.0f),
    (0 until 1536).map(i=>if(i%3==0) java.lang.Float.intBitsToFloat(0x1c800000) else 0.0f),
    (0 until 1536).map(i=>if(i%2==0) 1.00000011920928955078125f else -1.0f),
    (0 until 1536).map(_=>(random.nextFloat()*32.0f-16.0f)),
    (0 until 1536).map(_=>(random.nextFloat()*0.0002f-0.0001f)))
  println("MODEL_CHECKPOINT_BEFORE_ELABORATION")
  RawTester.test(new OrderedRms1536BankFixture,Seq(VerilatorBackendAnnotation,VerilatorCFlags(Seq("-O0","-fno-fast-math","-ffp-contract=off")))){ c =>
    println("MODEL_CHECKPOINT_SIMULATOR_READY")
    c.io.start.valid.poke(false.B);c.io.start.bits.poke(true.B);c.io.read.ready.poke(false.B)
    c.io.readResult.valid.poke(false.B);c.io.readResult.bits.foreach(_.poke(0.U));c.io.result.ready.poke(false.B);c.clock.step(2)
    for((row,caseId)<-cases.zipWithIndex){
      c.io.result.ready.poke(false.B);c.io.start.valid.poke(true.B);c.io.start.ready.expect(true.B);c.clock.step();c.io.start.valid.poke(false.B)
      var pending=false;var pendingIndex=0;var reads=0;var cycles=0
      while(!c.io.result.valid.peek().litToBoolean && cycles<2000){
        c.io.read.ready.poke((!pending && cycles%3!=0).B)
        c.io.readResult.valid.poke((pending && cycles%5!=0).B)
        for(i<-0 until 16)c.io.readResult.bits(i).poke(bits(row(pendingIndex*16+i)).U)
        val takeRead=c.io.read.valid.peek().litToBoolean && c.io.read.ready.peek().litToBoolean
        val takeData=c.io.readResult.valid.peek().litToBoolean && c.io.readResult.ready.peek().litToBoolean
        val nextIndex=if(takeRead)c.io.read.bits.peek().litValue.toInt else pendingIndex
        if(takeRead){assert(nextIndex==reads);reads+=1}
        c.clock.step();if(takeRead){pending=true;pendingIndex=nextIndex};if(takeData)pending=false;cycles+=1
      }
      assert(cycles<2000 && reads==96 && !pending)
      c.io.result.valid.expect(true.B);c.io.result.bits.error.expect(false.B);c.io.result.bits.sum.expect(bits(scalarGold(row)).U)
      c.io.acceptedVectorOperations.expect(111.U)
      c.clock.step(3);c.io.result.valid.expect(true.B);c.io.result.bits.sum.expect(bits(scalarGold(row)).U)
      println("MODEL_CASE_PASS="+caseId+" SUM_BITS="+bits(scalarGold(row)).toString(16)+" REQUESTS=111 CYCLES="+cycles)
      c.io.result.ready.poke(true.B);c.clock.step();c.io.result.valid.expect(false.B)
    }
    println("MODEL_SIX_FINITE_ROWS_STRICT_SCALAR_ORDER_BITWISE_PASS_NOT_FULL_BLOCK")
  }
}
