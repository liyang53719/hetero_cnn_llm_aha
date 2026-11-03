// Actual production DenseReadCommitCredit leaf only. NOT owner/DMA/4096 RTL PASS.
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.TreadleBackendAnnotation
import firrtl2.options.TargetDirAnnotation
object DenseReadCommitCreditSpec extends App {
  require(args.length==1,"explicit isolated output directory")
  RawTester.test(new DenseReadCommitCredit,
    Seq(TreadleBackendAnnotation,TargetDirAnnotation(args(0)))) { c =>
    c.io.accept.valid.poke(false.B);c.io.returned.valid.poke(false.B)
    c.io.accept.bits.address.poke(0.U);c.io.accept.bits.beats.poke(1.U);c.io.accept.bits.tag.poke(0.U)
    c.io.returned.bits.tag.poke(0.U);c.io.returned.bits.last.poke(false.B);c.io.returned.bits.error.poke(false.B)
    c.clock.step()
    var cases=0
    for(n<-1 to 16;fault<-0 until 5){
      val tag=BigInt(1000+cases)
      c.io.outstanding.expect(false.B)
      c.io.accept.bits.beats.poke(n.U);c.io.accept.bits.tag.poke(tag.U)
      c.io.accept.valid.poke(true.B);c.clock.step();c.io.accept.valid.poke(false.B)
      for(i<-0 until n){
        val finalBeat=i+1==n
        val badAt=if(fault==2)n-1 else 0
        val wrongLast=(fault==1 || fault==2) && i==badAt
        c.io.returned.bits.tag.poke((if(fault==3 && i==0)tag+1 else tag).U)
        c.io.returned.bits.last.poke((if(wrongLast)!finalBeat else finalBeat).B)
        c.io.returned.bits.error.poke((fault==4 && i==0).B)
        c.io.expectedLast.expect(finalBeat.B)
        c.io.bad.expect((wrongLast || ((fault==3 || fault==4) && i==0)).B)
        c.io.outstanding.expect(true.B)
        // Arbitrary consumer backpressure means no accepted return, no credit.
        c.io.returned.valid.poke(false.B);c.clock.step(2)
        c.io.outstanding.expect(true.B);c.io.expectedLast.expect(finalBeat.B)
        c.io.returned.valid.poke(true.B);c.clock.step();c.io.returned.valid.poke(false.B)
        c.io.outstanding.expect((!finalBeat).B)
      }
      cases+=1
    }
    println(s"DENSE_READ_CREDIT_PROTOCOL_ONLY cases=$cases expected_count_drained=true")
  }
}
