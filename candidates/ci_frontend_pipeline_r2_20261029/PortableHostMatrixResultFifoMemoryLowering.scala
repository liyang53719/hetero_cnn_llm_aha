// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

import firrtl2.ir._
import firrtl2.PrimOps
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/** Simulation-only storage representation transform. NOT a hardware source
  * change or synthesis pass. The one original FIFO's head/tail/count and every
  * other statement remain original AST objects. Only its unreset storage and
  * two bulk storage connects become seventeen packed, depth-two memories.
  *
  * Must run on the same official high Circuit BEFORE official lowering and
  * PrepareAst. The endpoint strict ABI gate still runs on all three Circuits.
  * No parser repair, reference file, arbitrary module-name match, AllowCycles,
  * second hardware elaboration, capacity reduction, or cache-timing shortcut.
  */
object PortableHostMatrixResultFifoMemoryLowering {
  // This exact serialization expectation is derived from the retained high
  // module excerpt. Its actual AST-serializer agreement has NOT yet run; a
  // mismatch is a hard rejection, not permission to learn a new hash in situ.
  // Actual production Host instance has returnTagBits=0, not service fixture32.
  // Metadata packs exactly context[2:0],last[3],error[4]; capacity remains262154bits.
  val HistoricalExpectedOriginalSha256 = "9fcf60e24bde0edcd7d57ffb36fd863cf5560b0287aa813ba1cab1e29f167b2b"
  private def sha(s:String):String = MessageDigest.getInstance("SHA-256")
    .digest(s.getBytes(StandardCharsets.UTF_8)).map(b=>f"${b & 255}%02x").mkString
  private def u(w:Int)=UIntType(IntWidth(w))
  private val one=UIntLiteral(1,IntWidth(1));private val zero=UIntLiteral(0,IntWidth(1))
  private def ref(s:String):Expression=Reference(s)
  private def field(e:Expression,s:String):Expression=SubField(e,s)
  private def path(parts:String*):Expression=parts.tail.foldLeft(ref(parts.head))(field)
  private def port(name:String,p:String,f:String):Expression=path(name,p,f)
  private def conn(a:Expression,b:Expression)=Connect(NoInfo,a,b)
  private def bits(e:Expression,hi:Int,lo:Int):Expression=DoPrim(PrimOps.Bits,Seq(e),Seq(BigInt(hi),BigInt(lo)),u(hi-lo+1))
  // Balanced concat avoids a new deep 256-element left-associated expression.
  private def catLsbFirst(xs:Vector[Expression]):Expression={
    require(xs.nonEmpty)
    if(xs.size==1)xs.head else {val n=xs.size/2
      DoPrim(PrimOps.Cat,Seq(catLsbFirst(xs.drop(n)),catLsbFirst(xs.take(n))),Seq.empty,UnknownType)}
  }
  private def word(which:String,r:Int,c:Int):Expression=
    SubIndex(SubIndex(path("io",which,"bits","value"),r,VectorType(u(32),256)),c,u(32))
  private val names=(0 until 16).map(i=>s"sim_storage_row_$i") :+ "sim_storage_metadata"
  private val widths=Vector.fill(16)(8192):+5
  private def memoryDeclarations:Seq[Statement]=names.zip(widths).map {case(n,w)=>
    DefMemory(NoInfo,n,u(w),BigInt(2),1,0,Seq("r"),Seq("w"),Seq.empty,ReadUnderWrite.Undefined) }
  // Declare storage at its original position, but default ports only after
  // original head/tail declarations and before the original conditional write.
  private def memoryDefaults:Seq[Statement]=names.zip(widths).flatMap {case(n,w)=>Seq(
    conn(port(n,"r","clk"),ref("clock")),conn(port(n,"r","en"),one),conn(port(n,"r","addr"),ref("head")),
    conn(port(n,"w","clk"),ref("clock")),conn(port(n,"w","en"),zero),conn(port(n,"w","addr"),ref("tail")),
    conn(port(n,"w","mask"),one),conn(port(n,"w","data"),UIntLiteral(0,IntWidth(w)))) }
  private def reads:Seq[Statement]={
    val data=(for(r<-0 until 16;c<-0 until 256)yield conn(word("deq",r,c),bits(port(names(r),"r","data"),32*c+31,32*c)))
    val m=port(names(16),"r","data")
    data++Seq(conn(path("io","deq","bits","context"),bits(m,2,0)),
      conn(path("io","deq","bits","last"),bits(m,3,3)),conn(path("io","deq","bits","error"),bits(m,4,4)))
  }
  private def writes:Seq[Statement]={
    val data=(0 until 16).map(r=>catLsbFirst(Vector.tabulate(256)(c=>word("enq",r,c)))) :+
      catLsbFirst(Vector("context","last","error").map(f=>path("io","enq","bits",f)))
    names.zip(data).flatMap{case(n,d)=>Seq(conn(port(n,"w","en"),one),conn(port(n,"w","data"),d))}
  }
  def apply(c:Circuit, expectedCanonical:String):Circuit={
    require(expectedCanonical.matches("[0-9a-f]{64}"),"approved canonical module pin required")
    val selected=c.modules.collect{case m:Module if m.name=="MatrixResultFifo"=>m}
    require(selected.size==1,"one exact original FIFO definition")
    val original=selected.head
    require(chiseltest.simulator.CanonicalHighGate.moduleSemanticSha(original)==expectedCanonical,"original FIFO AST/ABI/hash drift")
    var declaration=0;var read=0;var write=0
    def visit(s:Statement):Statement=s match {
      case d:DefRegister if d.name=="storage"=>
        require(d.reset==zero,"storage must have no reset")
        declaration+=1;Block(memoryDeclarations)
      case x:Connect if x.loc.serialize=="io.deq.bits" && x.expr.serialize=="storage[head]"=>
        read+=1;Block(memoryDefaults++reads)
      case x:Connect if x.loc.serialize=="storage[tail]" && x.expr.serialize=="io.enq.bits"=>
        write+=1;Block(writes)
      case x=>x.mapStmt(visit)
    }
    val replacement=original.copy(body=visit(original.body))
    require(declaration==1 && read==1 && write==1,"exactly three original storage substitutions")
    require(replacement.ports==original.ports,"entire original external ABI retained")
    val out=c.copy(modules=c.modules.map{case m if m eq original=>replacement;case m=>m})
    require(out.modules.zip(c.modules).forall{case(a,b)=>(b eq original)||(a eq b)},"all other modules original objects")
    out
  }
}
