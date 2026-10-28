// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous.model

import firrtl2.ir._
import firrtl2.PrimOps
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/** One exact simulation storage representation, NOT provider RTL or a general
  * register/memory inference pass. Preserve all 131072 stored bits, all 4096
  * simultaneous capture/clear writes, asynchronous read timing and original
  * last-connect priority. Every other original module is the same AST object.
  */
object HostDenseAccMemoryLowering {
  val ExpectedModuleSha256 = "341ecb4c4ec3ebf04f56ad78e60a5eabb42b5f708c8285cbea56b15222af9cef"
  private val ModuleName="Qwen2ContinuousBlock"
  private val MemName="sim_denseacc_rows"
  private val BeatName="sim_denseacc_selected_beat"
  private def u(w:Int)=UIntType(IntWidth(w))
  private val RowType=VectorType(u(32),256)
  private val TileType=VectorType(RowType,16)
  private val zero=UIntLiteral(0,IntWidth(1))
  private val one=UIntLiteral(1,IntWidth(1))
  private def ref(n:String):Expression=Reference(n)
  private def port(p:String,f:String):Expression=SubField(SubField(ref(MemName),p),f)
  private def connect(a:Expression,b:Expression)=Connect(NoInfo,a,b)
  private def bits(e:Expression,hi:Int,lo:Int):Expression=
    DoPrim(PrimOps.Bits,Seq(e),Seq(BigInt(hi),BigInt(lo)),u(hi-lo+1))
  private def sha(s:String)=MessageDigest.getInstance("SHA-256")
    .digest(s.getBytes(StandardCharsets.UTF_8)).map(b=>f"${b&255}%02x").mkString
  private def all(s:Statement):Seq[Statement]={
    val b=Vector.newBuilder[Statement];b+=s;s.foreachStmt(x=>b++=all(x));b.result()
  }
  private def refs(e:Expression):Int={
    var n=e match {case r:Reference if r.name=="denseAcc"=>1;case _=>0}
    e.foreachExpr(x=>n+=refs(x));n
  }
  private def refCount(s:Statement):Int=all(s).map{x=>var n=0;x.foreachExpr(e=>n+=refs(e));n}.sum
  private def catLsbFirst(xs:Vector[Expression]):Expression={
    require(xs.nonEmpty)
    if(xs.size==1)xs.head else {val n=xs.size/2
      DoPrim(PrimOps.Cat,Seq(catLsbFirst(xs.drop(n)),catLsbFirst(xs.take(n))),Seq.empty,UnknownType)}
  }
  private val Writers=(0 until 16).map(i=>s"w$i")
  private def declaration:DefMemory=DefMemory(NoInfo,MemName,u(8192),BigInt(16),1,0,
    Seq("r"),Writers,Seq.empty,ReadUnderWrite.Undefined)
  private def defaults:Seq[Statement]=Seq(connect(port("r","clk"),ref("clock")),
    connect(port("r","en"),one))++Writers.zipWithIndex.flatMap{case(w,r)=>Seq(
      connect(port(w,"clk"),ref("clock")),connect(port(w,"en"),zero),
      connect(port(w,"addr"),UIntLiteral(r,IntWidth(4))),connect(port(w,"mask"),one),
      connect(port(w,"data"),UIntLiteral(0,IntWidth(8192))))}
  private def writes(data:Expression):Seq[Statement]=Writers.zipWithIndex.flatMap{case(w,r)=>
    val row=SubIndex(data,r,RowType)
    val packed=catLsbFirst(Vector.tabulate(256)(c=>SubIndex(row,c,u(32))))
    Seq(connect(port(w,"en"),one),connect(port(w,"data"),packed))
  }
  private def readPrelude:Seq[Statement]={
    // Preserve ORIGINAL explicit row bits and original eight-bit column0.
    // No new truncation of the original five-bit denseRow is introduced.
    val shift=DoPrim(PrimOps.Cat,Seq(ref("_selectedDense_0_T_3"),UIntLiteral(0,IntWidth(5))),Seq.empty,u(13))
    val shifted=DoPrim(PrimOps.Dshr,Seq(port("r","data"),shift),Seq.empty,u(8192))
    Seq(connect(port("r","addr"),ref("_selectedDense_0_T")),
      DefNode(NoInfo,BeatName,bits(shifted,511,0)))
  }
  def apply(c:Circuit):Circuit={
    val ms=c.modules.collect{case m:Module if m.name==ModuleName=>m}
    require(ms.size==1,"one exact original Core module")
    val original=ms.head;val text=original.serialize
    require(sha(text)==ExpectedModuleSha256,"entire actual Core high AST drift")
    require(!text.contains("sim_denseacc_"),"fresh finite simulation names")
    val ss=all(original.body)
    val ds=ss.collect{case r:DefRegister if r.name=="denseAcc"=>r}
    require(ds.size==1 && ds.head.tpe==TileType && ds.head.reset==zero &&
      ds.head.init.serialize=="denseAcc" && ds.head.clock.serialize=="clock","exact unreset original131072bit register")
    def regType(n:String,t:Type):Unit={val a=ss.collect{case r:DefRegister if r.name==n=>r};require(a.size==1 && a.head.tpe==t)}
    regType("denseRow",u(5));regType("denseBeat",u(4))
    val nodeSeq=ss.collect{case n:DefNode=>n}
    val nodes=nodeSeq.map(n=>n.name->n).toMap
    require(nodes.size==nodeSeq.size,"unique original node names")
    for(i<-0 until 16){
      val n=s"_selectedDense_${i}_T"
      val k=UIntLiteral(BigInt(i),IntWidth(math.max(1,BigInt(i).bitLength))).serialize
      val expected=Seq(n->"bits(denseRow, 3, 0)",(n+"_1")->"shl(denseBeat, 4)",
        (n+"_2")->s"add(${n}_1, $k)",(n+"_3")->s"tail(${n}_2, 1)")
      expected.foreach{case(name,value)=>require(nodes.get(name).exists(_.value.serialize==value),"exact original bounded index "+name)}
    }
    // Full4bit beat and each i0..15 imply column=16*beat+i in0..255;
    // row is ORIGINAL bits(denseRow,3,0), including original alias for16..31.
    val oldWrites=ss.collect{case x:Connect if x.loc.serialize=="denseAcc"=>x}
    require(oldWrites.map(_.expr.serialize)==Seq("matrixResult.bits.value","_WIRE_26","_WIRE_44"),"all three bulk writes in original priority order")
    require(refCount(original.body)==20,"exact self-init+three writes+sixteen reads; reject unknown access")
    var declarations=0;var writeSites=0;val reads=scala.collection.mutable.Set.empty[Int]
    def visit(s:Statement):Statement=s match {
      case r:DefRegister if r.name=="denseAcc"=>declarations+=1;Block(declaration+:defaults)
      case x:Connect if x.loc.serialize=="denseAcc"=>
        writeSites+=1;Block(writes(x.expr)) // same original conditional / source position
      case x:Connect if x.expr.serialize.startsWith("denseAcc[")=>
        val i=(0 until 16).find(j=>x.loc.serialize==s"selectedDense[$j]").getOrElse(
          throw new IllegalArgumentException("unknown denseAcc read consumer"))
        require(!reads(i) && x.expr.serialize==s"denseAcc[_selectedDense_${i}_T][_selectedDense_${i}_T_3]","exact original read")
        reads+=i
        val value=x.copy(expr=bits(ref(BeatName),32*i+31,32*i))
        if(i==0)Block(readPrelude:+value)else value
      case x=>x.mapStmt(visit)
    }
    val changed=original.copy(body=visit(original.body))
    require(declarations==1 && writeSites==3 && reads.toSet==(0 until 16).toSet,"finite exact substitution counts")
    require(refCount(changed.body)==0 && changed.ports==original.ports,"no duplicate old storage; complete public ABI unchanged")
    val result=c.copy(modules=c.modules.map{case m if m eq original=>changed;case m=>m})
    require(result.modules.zip(c.modules).forall{case(a,b)=>(b eq original)||(a eq b)},"all other original module objects preserved")
    check(result);result
  }
  def check(c:Circuit):Unit={
    val ms=c.modules.collect{case m:Module if m.name==ModuleName=>m};require(ms.size==1)
    val ss=all(ms.head.body);val mems=ss.collect{case m:DefMemory if m.name==MemName=>m}
    require(mems.size==1,"one denseAcc replacement memory")
    val m=mems.head
    require(m.dataType==u(8192) && m.depth==16 && m.writeLatency==1 && m.readLatency==0 &&
      m.readers==Seq("r") && m.writers==Writers && m.readwriters.isEmpty && m.readUnderWrite==ReadUnderWrite.Undefined,"same capacity/parallel write ports/zero-latency read")
    require(!ss.exists{case r:DefRegister=>r.name=="denseAcc"||r.name.startsWith("denseAcc_");case _=>false},"no duplicate original register storage")
  }
}
