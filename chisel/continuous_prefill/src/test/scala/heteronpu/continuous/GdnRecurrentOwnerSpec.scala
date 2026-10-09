// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files, Paths}

/** Test-only connection to the actual existing shared arithmetic circuit. */
class GdnRecurrentArithmeticHarness(heads: Int, dk: Int, dv: Int) extends Module {
  val io = IO(new Bundle {
    val job = Flipped(Decoupled(new GdnRecurrentJob))
    val currentGeneration = Input(UInt(32.W))
    val done = Decoupled(new GdnRecurrentResult)
    val memory = Decoupled(new MemoryRequest)
    val response = Flipped(Decoupled(new MemoryResponse))
    val scalarHold = Input(Bool())
    val scalarFault = Input(Bool())
    val resetRequired = Output(Bool())
  })
  val owner = Module(new GdnRecurrentOwner(heads, dk, dv))
  val scalar = Module(new BlockScalarFloat)
  owner.io.job <> io.job; io.done <> owner.io.done
  owner.io.currentGeneration := io.currentGeneration
  io.memory <> owner.io.memory; owner.io.response <> io.response
  scalar.io.request.valid := owner.io.scalar.request.valid && !io.scalarHold
  scalar.io.request.bits := owner.io.scalar.request.bits
  owner.io.scalar.request.ready := scalar.io.request.ready && !io.scalarHold
  owner.io.scalar.result.valid := scalar.io.result.valid && !io.scalarHold
  owner.io.scalar.result.bits := scalar.io.result.bits
  owner.io.scalar.error := scalar.io.error || io.scalarFault
  scalar.io.result.ready := owner.io.scalar.result.ready && !io.scalarHold
  io.resetRequired := owner.io.resetRequired
}

trait GdnRecurrentTestSupport { self: ChiselScalatestTester with Matchers =>
  val qBase = BigInt("210000000",16); val kBase = BigInt("220000000",16)
  val vBase = BigInt("230000000",16); val gBase = BigInt("240000000",16)
  val oldBase = BigInt("250000000",16); val newBase = BigInt("260000000",16)
  val outBase = BigInt("270000000",16)
  val tag = BigInt("a1234567",16)
  def bits(f: Float): BigInt = BigInt(java.lang.Float.floatToRawIntBits(f).toLong & 0xffffffffL)
  def bf(f: Float): Int = { val b=bits(f).toLong; (((b+0x7fffL+((b>>>16)&1))>>>16)&65535).toInt }
  def pack(xs: Seq[BigInt], width: Int): BigInt = xs.zipWithIndex.foldLeft(BigInt(0)) { case(a,(x,i)) => a | (x << (width*i)) }
  def bytes(xs: Seq[BigInt], width: Int): Array[Byte] = xs.flatMap(x => (0 until width/8).map(i => ((x>>(i*8))&255).toByte)).toArray
  def words(b: Array[Byte], width: Int): Seq[BigInt] = b.grouped(width/8).map(x => x.zipWithIndex.foldLeft(BigInt(0)){case(a,(v,i))=>a|(BigInt(v&255)<<(8*i))}).toSeq
  def floats(b: Array[Byte]): Seq[Float] = words(b,32).map(x=>java.lang.Float.intBitsToFloat(x.toInt))
  def read(path: String): Array[Byte] = Files.readAllBytes(Paths.get(path))
  def expRecipe(x: Float): Float = {
    val t=(math.abs(x)*(1/math.log(2)).toFloat).toFloat; val k=t.toInt; val f=(t-k.toFloat).toFloat
    val coeff=(0 to 7).map(i=>(math.pow(-math.log(2),i)/(if(i==0)1.0 else (1 to i).map(_.toDouble).product)).toFloat)
    var h=coeff(7);for(i<-6 to 0 by -1)h=((h*f).toFloat+coeff(i)).toFloat
    (h*java.lang.Float.intBitsToFloat((127-k)<<23)).toFloat
  }
  case class Inputs(q: Array[Byte], k: Array[Byte], v: Array[Byte], gates: Array[Byte], past: Array[Byte])
  case class Expected(out: Array[Byte], state: Array[Byte])
  def expected(in: Inputs, heads: Int, dk: Int, dv: Int, cold: Boolean): Expected = {
    val q=floats(in.q);val k=floats(in.k);val v=floats(in.v);val g=floats(in.gates)
    val st=(if(cold) Seq.fill(heads*dk*dv)(0f) else floats(in.past)).toArray
    val out=Array.fill(heads*dv)(0)
    for(h<-0 until heads){
      val decay=expRecipe(g(h*16));val beta=g(h*16+1)
      for(j<-0 until dv){
        var pred=0f
        for(i<-0 until dk){val s=(h*dk+i)*dv+j;st(s)=(st(s)*decay).toFloat;pred=(pred+(st(s)*k(h*dk+i)).toFloat).toFloat}
        val delta=((v(h*dv+j)-pred).toFloat*beta).toFloat
        var sum=0f
        for(i<-0 until dk){val s=(h*dk+i)*dv+j;st(s)=(st(s)+(k(h*dk+i)*delta).toFloat).toFloat;sum=(sum+(st(s)*q(h*dk+i)).toFloat).toFloat}
        out(h*dv+j)=bf(sum)
      }
    }
    Expected(bytes(out.toSeq.map(BigInt(_)),16),bytes(st.toSeq.map(bits),32))
  }
  def init(d:GdnRecurrentArithmeticHarness): Unit = {
    d.io.job.valid.poke(false.B);d.io.done.ready.poke(false.B);d.io.memory.ready.poke(false.B)
    d.io.response.valid.poke(false.B);d.io.response.bits.tag.poke(0.U);d.io.response.bits.data.poke(0.U);d.io.response.bits.error.poke(false.B)
    d.io.currentGeneration.poke(0.U);d.io.scalarHold.poke(false.B);d.io.scalarFault.poke(false.B)
    d.reset.poke(true.B);d.clock.step(3);d.reset.poke(false.B);d.clock.step();d.clock.setTimeout(0)
  }
  def setJob(d:GdnRecurrentArithmeticHarness,heads:Int,dk:Int,dv:Int,cold:Boolean,generation:Int):Unit={
    val j=d.io.job.bits;j.tokens.poke(1.U);j.heads.poke(heads.U);j.keyDim.poke(dk.U);j.valueDim.poke(dv.U)
    j.query.poke(qBase.U);j.key.poke(kBase.U);j.value.poke(vBase.U);j.gates.poke(gBase.U)
    j.stateIn.poke(oldBase.U);j.stateOut.poke(newBase.U);j.output.poke(outBase.U)
    j.cold.poke(cold.B);j.expectedGeneration.poke(generation.U);j.tag.poke(tag.U);d.io.currentGeneration.poke(generation.U)
  }
  def beats(base:BigInt,b:Array[Byte]):Map[BigInt,BigInt]=b.grouped(64).zipWithIndex.map{case(x,i)=>(base+i*64)->pack(x.toSeq.map(y=>BigInt(y&255)),8)}.toMap
  case class Request(write:Boolean,address:BigInt,data:BigInt,mask:BigInt,tag:BigInt)
  def req(d:GdnRecurrentArithmeticHarness):Request={val r=d.io.memory.bits;Request(r.write.peek().litToBoolean,r.address.peek().litValue,r.data.peek().litValue,r.mask.peek().litValue,r.tag.peek().litValue)}
  def run(d:GdnRecurrentArithmeticHarness,in:Inputs,gold:Expected,heads:Int,dk:Int,dv:Int,cold:Boolean,generation:Int,label:String,fault:String="none"):Expected={
    d.io.scalarHold.poke(false.B);d.io.scalarFault.poke(false.B)
    val reads=beats(qBase,in.q)++beats(kBase,in.k)++beats(vBase,in.v)++beats(gBase,in.gates)++beats(oldBase,in.past)
    val want=beats(outBase,gold.out)++beats(newBase,gold.state)
    val actual=scala.collection.mutable.Map.empty[BigInt,BigInt]
    val seenMasks=scala.collection.mutable.Map.empty[BigInt,BigInt]
    var elapsed=0;var issued=0;var acknowledged=0;var injected=false
    def step(n:Int):Unit={d.clock.step(n);elapsed+=n}
    setJob(d,heads,dk,dv,cold,generation);d.io.job.ready.expect(true.B);d.io.job.valid.poke(true.B);step(1);d.io.job.valid.poke(false.B)
    if(fault=="scalar")d.io.scalarFault.poke(true.B)
    while(!d.io.done.valid.peek().litToBoolean && elapsed<100000+heads*dk*dv*40){
      if(!d.io.memory.valid.peek().litToBoolean){d.io.scalarHold.poke(((elapsed/64)%7==0).B);step(64)}else{
        val r=req(d);assert(r.tag==((tag<<32)|issued));assert((r.address&63)==0)
        d.io.scalarHold.poke((issued%3==0).B);step(1+issued%5);assert(req(d)==r,"request changed under backpressure")
        d.io.scalarHold.poke(false.B);d.io.memory.ready.poke(true.B);step(1);d.io.memory.ready.poke(false.B)
        val last=r.write&&r.address==outBase+gold.out.length-64&&r.mask==BigInt("ffffffff00000000",16)
        val inject= !injected && (if(fault=="read"||fault=="tag") !r.write else fault=="final-ack"&&last)
        if(inject)injected=true
        if(r.write){
          assert(want.contains(r.address),"write outside staging spans")
          assert((seenMasks.getOrElse(r.address,BigInt(0))&r.mask)==0,"duplicate staging-byte write")
          seenMasks(r.address)=seenMasks.getOrElse(r.address,BigInt(0))|r.mask
          val mask=(0 until 64).foldLeft(BigInt(0)){(m,i)=>if(r.mask.testBit(i))m|(BigInt(255)<<(i*8))else m}
          assert((r.data&mask)==(want(r.address)&mask),s"actual FP32/BF16 arithmetic mismatch $label address=${r.address.toString(16)}")
          assert(if(r.address>=outBase) Set(BigInt("ffffffff",16),BigInt("ffffffff00000000",16)).contains(r.mask) else r.mask==(BigInt(1)<<64)-1)
          if(!inject){actual(r.address)=(actual.getOrElse(r.address,BigInt(0))& ~mask)|(r.data&mask);acknowledged+=r.mask.bitCount}
        }else{assert(reads.contains(r.address));assert(r.mask==0);if(cold)assert(r.address<oldBase||r.address>=oldBase+in.past.length,"cold read stale state")}
        step(if(last)31 else 2);d.io.done.valid.expect(false.B);d.io.done.bits.stateCommitted.expect(false.B)
        d.io.response.bits.data.poke((if(r.write)BigInt(0)else reads(r.address)).U)
        d.io.response.bits.tag.poke((r.tag^(if(inject&&fault=="tag")BigInt(1)else BigInt(0))).U)
        d.io.response.bits.error.poke((inject&&fault!="tag").B);d.io.response.valid.poke(true.B);d.io.response.ready.expect(true.B)
        step(1);d.io.response.valid.poke(false.B);issued+=1
      }
    }
    assert(d.io.done.valid.peek().litToBoolean,s"deadlock $label cycles=$elapsed")
    val status=if(fault=="none")Status.Ok else if(fault=="tag")Status.Protocol else if(fault=="scalar"||fault=="domain")Status.Numerical else Status.Memory
    d.io.done.bits.status.expect(status.U);d.io.done.bits.writeBytes.expect(acknowledged.U)
    d.io.done.bits.stateCommitted.expect((fault=="none").B);d.io.done.bits.generation.expect((generation+(if(fault=="none")1 else 0)).U)
    def completion=Seq(d.io.done.bits.tag.peek().litValue,d.io.done.bits.status.peek().litValue,d.io.done.bits.writeBytes.peek().litValue,d.io.done.bits.cycles.peek().litValue,d.io.done.bits.stateCommitted.peek().litValue,d.io.done.bits.generation.peek().litValue)
    val held=completion;step(17);assert(completion==held,"unstable terminal result")
    if(fault=="none"){assert(actual.toMap==want,"not every output/state byte was actually written");assert(acknowledged==gold.out.length+gold.state.length,"incorrect acknowledged byte total")}
    println(s"GDN_RECURRENT_RTL_CASE label=$label heads=$heads dk=$dk dv=$dv cold=$cold status=$status acknowledged_bytes=$acknowledged cycles=${d.io.done.bits.cycles.peek().litValue}")
    d.io.done.ready.poke(true.B);step(1);d.io.done.ready.poke(false.B);d.io.job.ready.expect((fault=="none").B)
    def collected(base:BigInt,n:Int)= (0 until n/64).flatMap(i=>(0 until 64).map(j=>((actual.getOrElse(base+i*64,BigInt(0))>>(8*j))&255).toByte)).toArray
    Expected(collected(outBase,gold.out.length),collected(newBase,gold.state.length))
  }
}

class GdnRecurrentOwnerSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnRecurrentTestSupport {
  "GdnRecurrentOwner" should "compute FP32 state, preserve signed zero and underflow, fence ACKs and reset failures" in {
    test(new GdnRecurrentArithmeticHarness(1,16,32)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d)
      val random=new scala.util.Random(350891)
      def vector(n:Int)=bytes(Seq.fill(n)(bits((random.nextDouble()*.4-.2).toFloat)),32)
      val q=vector(16);val k=vector(16);val v=vector(32);val gates=bytes(Seq(bits(-.7f),bits(.65f))++Seq.fill(14)(BigInt(0)),32)
      val in=Inputs(q,k,v,gates,vector(16*32));val cold=expected(in,1,16,32,true)
      val first=run(d,in,cold,1,16,32,true,0,"cold_m1")
      val carried=in.copy(v=vector(32),past=first.state);val carry=expected(carried,1,16,32,false)
      run(d,carried,carry,1,16,32,false,1,"carried_decode_m1")
      assert(!java.util.Arrays.equals(carry.state,expected(carried,1,16,32,true).state))
      for(fault<-Seq("read","tag","scalar","final-ack")){init(d);run(d,in,cold,1,16,32,true,0,fault,fault);d.io.resetRequired.expect(true.B);d.clock.step(5);d.io.job.ready.expect(false.B)}
      for((g,b)<-Seq((-80f,.5f),(.1f,.5f),(-.7f,1.1f),(Float.NaN,.5f))){
        init(d);val bad=in.copy(gates=bytes(Seq(bits(g),bits(b))++Seq.fill(14)(BigInt(0)),32))
        run(d,bad,cold,1,16,32,true,0,"invalid_gate_domain","domain")
      }
      // Reset an accepted read before its response. The harness models the
      // required common transport reset by discarding that outstanding read.
      init(d);setJob(d,1,16,32,true,0);d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B)
      d.io.memory.valid.expect(true.B);d.io.memory.ready.poke(true.B);d.clock.step();d.io.memory.ready.poke(false.B)
      d.io.done.valid.expect(false.B);d.io.done.bits.stateCommitted.expect(false.B)
      init(d);run(d,in,cold,1,16,32,true,0,"reset_inflight_read_then_cold")
      // Gradual FP32 state underflow, negative zero and exact subnormal multiply.
      init(d)
      val tiny=java.lang.Float.intBitsToFloat(1);val tinyIn=Inputs(bytes(Seq.fill(16)(bits(-0f)),32),bytes(Seq.fill(16)(bits(.5f)),32),bytes(Seq.fill(32)(bits(tiny)),32),gates,bytes(Seq.fill(16*32)(bits(-tiny)),32))
      run(d,tinyIn,expected(tinyIn,1,16,32,false),1,16,32,false,4,"signed_zero_gradual_underflow")
      for(bad<-0 until 9){
        init(d);setJob(d,1,16,32,false,7);val j=d.io.job.bits
        bad match{case 0=>j.stateOut.poke(oldBase.U);case 1=>j.output.poke(qBase.U);case 2=>j.key.poke((kBase+4).U);case 3=>j.tokens.poke(2.U);case 4=>j.heads.poke(0.U);case 5=>j.keyDim.poke(128.U);case 6=>j.expectedGeneration.poke(6.U);case 7=>j.cold.poke(true.B);case 8=>j.stateOut.poke(((BigInt(1)<<56)-64).U)}
        d.io.job.valid.poke(true.B);d.clock.step();d.io.job.valid.poke(false.B);d.io.done.valid.expect(true.B)
        d.io.done.bits.status.expect((if(bad==6||bad==7)Status.Dependency else Status.Bounds).U)
        d.io.memory.valid.expect(false.B);d.io.done.bits.stateCommitted.expect(false.B)
      }
      // A new cold job after the common reset cannot expose stale tile contents.
      init(d);run(d,in,cold,1,16,32,true,0,"reset_then_cold")
    }
  }
}

class GdnRecurrentCheckpointSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers with GdnRecurrentTestSupport {
  "GdnRecurrentOwner" should "compute pinned checkpoint heads at the real 128 by 128 geometry" in {
    val root=sys.env.getOrElse("GDN_RECURRENT_FIXTURE",throw new IllegalArgumentException("GDN_RECURRENT_FIXTURE required"))
    val heads=sys.env.getOrElse("GDN_RECURRENT_HEADS","2").toInt
    test(new GdnRecurrentArithmeticHarness(heads,128,128)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      init(d);var actualState=Array.fill[Byte](heads*128*128*4)(0)
      for(t<-0 until 2){
        val in=Inputs(read(s"$root/query$t.f32le"),read(s"$root/key$t.f32le"),read(s"$root/value$t.f32le"),read(s"$root/gates$t.f32le"),actualState)
        val gold=Expected(read(s"$root/expected_output$t.bf16le"),read(s"$root/expected_state$t.f32le"))
        val scalaGold=expected(in,heads,128,128,t==0)
        assert(java.util.Arrays.equals(scalaGold.out,gold.out)&&java.util.Arrays.equals(scalaGold.state,gold.state),"independent Scala/Python fixed oracles disagree")
        val observed=run(d,in,gold,heads,128,128,t==0,t,if(t==0)"checkpoint_cold_m1"else"checkpoint_carried_decode_m1")
        actualState=observed.state // only actual acknowledged RTL stores feed carry
      }
    }
  }
}
