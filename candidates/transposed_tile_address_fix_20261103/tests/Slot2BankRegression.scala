// Actual full-size bank storage/protocol regression. This is NOT a complete
// DenseTileSumBridge/vector arithmetic, lease-owner, MAC-array or full-top test.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.{VerilatorBackendAnnotation,VerilatorCFlags}
import firrtl2.options.TargetDirAnnotation

object Slot2BankRegression {
  def raw(x:Float):BigInt=BigInt(java.lang.Float.floatToRawIntBits(x).toLong&0xffffffffL)
  def pack(v:Seq[BigInt],bits:Int):BigInt=v.zipWithIndex.foldLeft(BigInt(0)){case(a,(b,i))=>a|(b<<(bits*i))}
  def aValue(m:Int,k:Int):BigInt=BigInt(0x3f00|((m*17+k*131+k/16)&255))
  def tileValue(slot:Int,index:Int,bank:Int,ng:Int):BigInt=
    raw((1+slot*17+(index%113)+bank*3+ng/32).toFloat/16.0f)
  def sumValue(index:Int,bank:Int,ng:Int):BigInt={
    val a=java.lang.Float.intBitsToFloat(tileValue(0,index,bank,ng).toInt)
    val b=java.lang.Float.intBitsToFloat(tileValue(1,index,bank,ng).toInt)
    raw(a+b)
  }
  def main(args:Array[String]):Unit={
    require(args.length==1 && Set("all","address","retention","negative").contains(args(0)))
    val mode=args(0)
    RawTester.test(new Slot2BankFixture,Seq(VerilatorBackendAnnotation,
      VerilatorCFlags(Seq("-O0")),TargetDirAnnotation("sim"))){d=>
      d.clock.setTimeout(0) // External wall/CPU/RSS supervisor remains mandatory.
      val p=d.io.tiles.get
      def zeros(x:Data):Unit=x match {
        case b:Bool=>b.poke(false.B);case u:UInt=>u.poke(0.U)
        case v:Vec[_]=>v.foreach(zeros);case r:Record=>r.elements.values.foreach(zeros)
        case _=>throw new IllegalArgumentException("unsupported test input")
      }
      def initialize():Unit={
        d.io.zero.valid.poke(false.B);d.io.zero.bits.poke(0.U)
        d.io.activation.valid.poke(false.B);zeros(d.io.activation.bits)
        d.io.weight.valid.poke(false.B);zeros(d.io.weight.bits)
        d.io.read.valid.poke(false.B);zeros(d.io.read.bits)
        d.io.tileEnable.get.poke(true.B);p.abort.poke(false.B)
        p.control.valid.poke(false.B);zeros(p.control.bits)
        p.write.valid.poke(false.B);zeros(p.write.bits)
        p.read.valid.poke(false.B);zeros(p.read.bits);p.response.ready.poke(false.B)
        d.reset.poke(true.B);d.clock.step(2);d.reset.poke(false.B);d.clock.step()
      }
      var checks=0L;var beatsWritten=0L;var beatsRead=0L
      var activationWrites=0L;var expectedIdentity=1
      def healthy():Unit={p.resetRequired.expect(false.B)}
      def control(op:Int,slot:Int,rows:Int,cols:Int,ng:Int=0,order:Boolean=false):Unit={
        p.control.bits.op.poke(op.U);p.control.bits.slot.poke(slot.U)
        p.control.bits.identity.poke(expectedIdentity.U);p.control.bits.ng.poke(ng.U)
        p.control.bits.rows.poke(rows.U);p.control.bits.cols.poke(cols.U)
        p.control.bits.matrixProducerOrder.get.poke(order.B)
        p.control.valid.poke(true.B);p.control.ready.expect(true.B)
        d.clock.step();p.control.valid.poke(false.B)
      }
      def key(k:FfnTileIndex,slot:Int,index:Int,ng:Int):Unit={
        k.slot.poke(slot.U);k.identity.poke(expectedIdentity.U);k.ng.poke(ng.U);k.index.poke(index.U)
      }
      // Mathematical expectation is only the scoreboard. Actual observed
      // issue/commit signals and actual synchronous memory are the DUT.
      def expectedWord(slot:Int,index:Int,cols:Int):Int=768+slot*160+(index/cols)*20+(index%cols)/8
      def checkAddress(slot:Int,index:Int,cols:Int,commit:Boolean):Unit={
        val word=expectedWord(slot,index,cols);val lane=index%cols%8
        if(commit){d.diagnostic.commit.expect(true.B);d.diagnostic.commitWord.expect(word.U);d.diagnostic.commitLane.expect(lane.U)}
        else {d.diagnostic.issueWord.expect(word.U);d.diagnostic.issueLane.expect(lane.U)}
        assert(word>=768 && word<1248 && word<1376);checks+=1
      }
      def write(slot:Int,index:Int,cols:Int,values:Seq[BigInt],ng:Int=0,addressGate:Boolean=true):Unit={
        key(p.write.bits.key,slot,index,ng)
        values.zipWithIndex.foreach{case(v,b)=>p.write.bits.value(b).poke(v.U)}
        p.write.valid.poke(true.B);p.write.ready.expect(true.B)
        d.diagnostic.issueWrite.expect(true.B)
        if(addressGate)checkAddress(slot,index,cols,false)
        d.clock.step();p.write.valid.poke(false.B)
        // Change live key while its reserved edge is pending: commit must
        // use captured key, not a later idle/live input.
        key(p.write.bits.key,(slot+1)%3,0,ng+160)
        if(addressGate)checkAddress(slot,index,cols,true)
        p.write.ready.expect(false.B);p.read.ready.expect(false.B)
        d.clock.step();healthy();beatsWritten+=1
      }
      def read(slot:Int,index:Int,cols:Int,expected:Seq[BigInt],ng:Int=0,addressGate:Boolean=true,stall:Boolean=false):Unit={
        key(p.read.bits,slot,index,ng);p.read.valid.poke(true.B);p.read.ready.expect(true.B)
        d.diagnostic.issueRead.expect(true.B)
        if(addressGate)checkAddress(slot,index,cols,false)
        d.clock.step();p.read.valid.poke(false.B);key(p.read.bits,(slot+1)%3,0,ng+160)
        p.response.valid.expect(false.B);d.clock.step()
        p.response.valid.expect(true.B);p.response.bits.error.expect(false.B)
        p.response.bits.key.slot.expect(slot.U);p.response.bits.key.identity.expect(expectedIdentity.U)
        p.response.bits.key.ng.expect(ng.U);p.response.bits.key.index.expect(index.U)
        d.diagnostic.tilePacked.expect(pack(expected,32).U)
        if(stall){d.clock.step(3);p.response.valid.expect(true.B);d.diagnostic.tilePacked.expect(pack(expected,32).U);p.read.ready.expect(false.B)}
        p.response.ready.poke(true.B);d.clock.step();p.response.ready.poke(false.B)
        healthy();beatsRead+=1
      }
      def initA():Unit={
        // Initialize every physical A word/lane reachable by K<1536.
        // No hierarchical memory poke or storage replacement is used.
        for(kw<-0 until 96;m<-0 until 128){
          d.io.activation.bits.kWord.poke(kw.U);d.io.activation.bits.m.poke(m.U)
          d.io.activation.bits.value.poke(pack((0 until 16).map(k=>aValue(m,kw*16+k)),16).U)
          d.io.activation.valid.poke(true.B);d.io.activation.ready.expect(true.B)
          d.clock.step();d.io.activation.valid.poke(false.B);d.io.activationWritten.expect(true.B)
          d.clock.step();activationWrites+=1
        }
      }
      def checkA(label:String):Unit={
        for(k<-0 until 1536){
          d.io.read.bits.k.poke(k.U);d.io.read.bits.context.poke(0.U);d.io.read.bits.half.poke(false.B)
          d.io.read.valid.poke(true.B);d.io.read.ready.expect(true.B);d.clock.step();d.io.read.valid.poke(false.B)
          d.io.response.valid.expect(true.B)
          val expected=pack((0 until 128).map(m=>aValue(m,k)),16)
          val actual=d.diagnostic.activationPacked.peek().litValue
          assert(actual==expected,s"A_RETENTION_CORRUPTED phase=$label k=$k actual=$actual expected=$expected")
          d.clock.step()
        }
        println(s"SLOT2_A_DOMAIN_PASS phase=$label halfwords=196608 activation_loads=$activationWrites")
      }
      initialize()
      if(mode=="all" || mode=="address"){
        // Every legal geometry, every beat, every bank, all eight FP32 lanes.
        for(rows<-Seq(16,128);cols<-Seq(32,64,96,128,160);slot<-0 until 3){
          val count=rows/16*cols
          control(0,slot,rows,cols)
          for(i<-0 until count)write(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,0)))
          p.state(slot).produced.expect(count.U);control(1,slot,rows,cols)
          for(i<-0 until count)read(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,0)),stall=i==0||i==count-1)
          p.state(slot).consumed.expect(count.U);control(2,slot,rows,cols);p.state(slot).live.expect(false.B)
          expectedIdentity+=1
        }
        // Producer-order writes are physical context-major; reads stay linear.
        for(rows<-Seq(16,128);cols<-Seq(32,64,96,128,160);slot<-0 until 2){
          val groups=rows/16;val count=groups*cols
          control(0,slot,rows,cols,order=true)
          for(q<-0 until count){val i=(q/(32*groups))*32+((q/32)%groups)*cols+q%32
            write(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,0)))}
          control(1,slot,rows,cols)
          for(i<-0 until count)read(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,0)))
          control(2,slot,rows,cols);expectedIdentity+=1
        }
        println(s"SLOT2_BANK_ADDRESS_PASS address_checks=$checks writes=$beatsWritten reads=$beatsRead legal_shapes=10 linear_slots=3 producer_slots=2")
      }
      if(mode=="all" || mode=="retention"){
        initialize();initA();checkA("before_tiles")
        // Two ng windows with NO A clear/reload. Bank-level reproduction of
        // partial0/partial1 -> FP32 result writes to slot2 -> drain -> reuseA.
        // Sum values below are host stimuli, not a hardware arithmetic PASS.
        for(ng<-Seq(0,160)){
          val rows=128;val cols=160;val count=1280
          for(slot<-0 until 2){
            control(0,slot,rows,cols,ng)
            for(i<-0 until count)write(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,ng)),ng,addressGate=false)
            control(1,slot,rows,cols,ng)
          }
          control(0,2,rows,cols,ng)
          for(i<-0 until count){
            for(slot<-0 until 2)read(slot,i,cols,(0 until 16).map(b=>tileValue(slot,i,b,ng)),ng,addressGate=false)
            write(2,i,cols,(0 until 16).map(b=>sumValue(i,b,ng)),ng,addressGate=false)
          }
          control(1,2,rows,cols,ng)
          for(slot<-0 until 2)control(2,slot,rows,cols,ng)
          for(i<-0 until count)read(2,i,cols,(0 until 16).map(b=>sumValue(i,b,ng)),ng,addressGate=false,stall=i==0||i==count-1)
          control(2,2,rows,cols,ng);p.leased.expect(false.B)
          assert(activationWrites==12288,"A was reloaded and could hide pollution")
          checkA(s"after_drain_reuseA_ng_${ng+160}")
        }
        println(s"SLOT2_BANK_RETENTION_PASS windows=2 activation_loads=$activationWrites writes=$beatsWritten reads=$beatsRead hardware_arithmetic_verified=false owner_lease_verified=false")
      }
      if(mode=="all" || mode=="negative"){
        // Each malformed begin poisons. Reset only between independent cases.
        for((rows,cols,slot,order)<-Seq((16,0,0,false),(16,16,0,false),(16,48,0,false),
          (16,192,0,false),(32,32,0,false),(128,160,3,false),(128,160,2,true))){
          initialize();control(0,slot,rows,cols,order=order);p.resetRequired.expect(true.B)
          d.diagnostic.issueRead.expect(false.B);d.diagnostic.issueWrite.expect(false.B)
        }
        println("SLOT2_BANK_INVALID_GEOMETRY_PASS malformed_begins=7")
      }
      if(mode=="all")println("SLOT2_ACTUAL_BANK_ALL_PASS full_top=false hardware_arithmetic_verified=false owner_lease_verified=false")
    }
  }
}
