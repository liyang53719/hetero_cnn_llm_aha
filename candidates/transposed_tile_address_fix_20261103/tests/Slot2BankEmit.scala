// Actual Chisel elaboration -> official low FIRRTL -> actual SystemVerilog.
// Checks inspect emitted hardware IR; this is not a Python address model.
package chiseltest.simulator.jna
import heteronpu.continuous.Slot2BankFixture
import chiseltest.simulator.{Compiler,VerilatorBackendAnnotation,VerilatorCoverage}
import firrtl2.options.TargetDirAnnotation
import firrtl2.ir._
import firrtl2.PrimOps
import java.nio.file.{Files,Paths}

object Slot2BankEmit {
  def main(args:Array[String]):Unit={
    require(args.length==1,"output directory, relative to fresh stage directory")
    val target=Paths.get(args(0));require(!target.isAbsolute)
    Files.createDirectory(target)
    val (high,_) = Compiler.elaborate(()=>new Slot2BankFixture,
      Seq(VerilatorBackendAnnotation,TargetDirAnnotation(args(0))),
      firrtl.seqToAnnoSeq(Seq.empty[firrtl.annotations.Annotation]))
    Files.write(target.resolve("actual-high.fir"),high.circuit.serialize.getBytes("UTF-8"))
    val low=Compiler.toLowFirrtl(high)
    val memories=scala.collection.mutable.ArrayBuffer.empty[DefMemory]
    val bases=scala.collection.mutable.ArrayBuffer.empty[(String,BigInt,String)]
    def expr(e:Expression,where:String):Unit={
      e match {
        case DoPrim(PrimOps.Add,operands,_,_) =>
          operands.collect{case UIntLiteral(v,IntWidth(w)) if v==768 => w}.foreach { w =>
            bases += ((where,w,e.serialize))
          }
        case _ =>
      }
      e.foreachExpr(q=>expr(q,where))
    }
    def stmt(s:Statement):Unit={
      s match {case m:DefMemory=>memories+=m;case _=>}
      s.foreachExpr(e=>expr(e,s.serialize.takeWhile(_!='\n').take(120)))
      s.foreachStmt(stmt)
    }
    low.circuit.modules.foreach {case m:Module=>stmt(m.body);case _=>}
    val a=memories.filter(m=>m.depth==1376 && m.dataType==UIntType(IntWidth(256)))
    val b=memories.filter(m=>m.depth==160 && m.dataType==UIntType(IntWidth(256)))
    require(a.size==16 && b.size==16,s"physical geometry drift A=${a.size} B=${b.size}")
    require(memories.size==32,s"unexpected physical memory count ${memories.size}")
    require((a++b).forall(m=>m.readLatency==1 && m.writeLatency==1 &&
      m.readers.size==1 && m.writers.size==1 && m.readwriters.isEmpty),"physical ports changed")
    Files.write(target.resolve("slot-base-widths.txt"),bases.map {case(n,w,e)=>s"literal_width=$w node=$n expression=$e"}.mkString("\n").getBytes("UTF-8"))
    // Emit before gate so negative baseline retains actual RTL and width proof.
    Compiler.lowFirrtlToSystemVerilog(low,VerilatorCoverage.CoveragePasses)
    require(bases.size==2,s"expected issue+commit base additions, found ${bases.size}")
    require(bases.forall(_._2>=11),s"SLOT2_BASE_CARRY_TRUNCATED: ${bases.map(_._2).mkString(",")}")
    println("SLOT2_EMITTED_IR_PASS actual_chisel=true base_additions=2 minimum_literal_width=11 A=16x1376x256 B=16x160x256 full_top=false")
  }
}
