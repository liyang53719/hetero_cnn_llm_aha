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
object CandidateDenseAccMemoryLoweringV2 {
  final class DenseShapeRejected(val code:String,val counts:Map[String,Long]=Map.empty) extends IllegalArgumentException(code)
  private var counts=Map.empty[String,Long]
  val PredicateCodes:Set[String]=Set("CAT_NONEMPTY","CANONICAL_FORMAT","ONE_CORE","CORE_INTEGRITY","FRESH_NAMES","DENSE_REGISTER","INDEX_REGISTERS","UNIQUE_NODES","READ_INDEX_NODES","BULK_SOURCES","DENSE_REFERENCE_COUNT","READ_EXACT","REWRITE_COUNTS","NO_OLD_STORAGE_PORTS","OTHER_MODULE_IDENTITY","POST_ONE_CORE","POST_ONE_MEMORY","POST_MEMORY_SHAPE","POST_NO_REGISTERS","READ_CONSUMER","ZERO_TILE_NAMES","ZERO_DECLARATIONS","ZERO_TILE_DRIVERS","ZERO_ROW_DRIVERS","ZERO_SAME_BLOCK","ZERO_ORDER","ZERO_EXACT_LITERAL","ZERO_REFERENCE_CLOSURE","ZERO_CLOSURE_COUNTS","CONDITIONAL_STRUCTURE","NONREPLACED_STRUCTURE","CORE_INFO","CORE_PORTS","GATE_MODULE_COUNT","GATE_INFO","GATE_PORTS","INTERNAL_UNCLASSIFIED")
  def checked(code:String,condition:Boolean,message: =>String=""):Unit={
    if(!PredicateCodes(code))throw new DenseShapeRejected("INTERNAL_UNCLASSIFIED")
    if(!condition)throw new DenseShapeRejected(code,counts)
  }

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
    checked("CAT_NONEMPTY",xs.nonEmpty)
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

  /** Prove exactly two distinct typed all-zero constructors. Names have no
    * semantics: every declaration/driver/index/consumer is proved instead.
    * Contexts are identity-indexed to reject equal-looking moved statements. */
  private def proveZeroClosures(original:Module,writes:Seq[Connect]):Unit={
    val ss=all(original.body)
    val context=new java.util.IdentityHashMap[Statement,(Block,Int)]()
    def index(s:Statement):Unit={s match {
      case b:Block=>b.stmts.zipWithIndex.foreach{case(x,i)=>context.put(x,(b,i))}
      case _=>()
    };s.foreachStmt(index)}
    index(original.body)
    counts+= "dense_bulk_writes"->writes.size.toLong
    val tiles=writes.tail.map(_.expr.asInstanceOf[Reference].name)
    counts+= "dense_zero_tiles"->tiles.distinct.size.toLong
    checked("ZERO_TILE_NAMES",tiles.distinct.size==2)
    val declarations=ss.collect{case d:DefWire=>d}
    val allDeclared=original.ports.map(_.name)++ss.collect{
      case d:DefWire=>d.name;case d:DefRegister=>d.name;case d:DefNode=>d.name
      case d:DefMemory=>d.name;case d:DefInstance=>d.name
    }
    def declaration(name:String,t:Type):DefWire={
      val ds=declarations.filter(_.name==name)
      checked("ZERO_DECLARATIONS",ds.size==1 && ds.head.tpe==t && allDeclared.count(_==name)==1);ds.head
    }
    def connects(name:String):Seq[Connect]=ss.collect{case c:Connect if references(c.loc).contains(name)=>c}
    def sameBlock(s:Statement,write:Connect):Int={
      checked("ZERO_SAME_BLOCK",context.containsKey(s)&&context.containsKey(write)&& (context.get(s)._1 eq context.get(write)._1))
      context.get(s)._2
    }
    def before(s:Statement,next:Statement,write:Connect):Unit={
      checked("ZERO_ORDER",sameBlock(s,write)<sameBlock(next,write))
    }
    val owned=scala.collection.mutable.Set.empty[String]
    val allowed=new java.util.IdentityHashMap[Statement,java.lang.Boolean]()
    var rowCount=0;var elementCount=0
    writes.tail.zip(tiles).foreach{case(write,tile)=>
      val td=declaration(tile,TileType);checked("ZERO_TILE_NAMES",!owned(tile));owned+=tile
      val tc=connects(tile)
      checked("ZERO_TILE_DRIVERS",tc.size==16 && tc.zipWithIndex.forall{case(c,i)=>
        c.loc match {case x:SubIndex=>x.expr.isInstanceOf[Reference]&&x.expr.asInstanceOf[Reference].name==tile&&x.value==i&&c.expr.isInstanceOf[Reference];case _=>false}
      })
      val rowNames=tc.map(_.expr.asInstanceOf[Reference].name)
      checked("ZERO_TILE_NAMES",rowNames.distinct.size==16 && !rowNames.exists(owned))
      before(td,tc.head,write);before(tc.last,write,write)
      tc.sliding(2).foreach{pair=>if(pair.size==2)before(pair.head,pair.last,write)}
      tc.zip(rowNames).foreach{case(tileConnect,row)=>
        owned+=row;rowCount+=1;counts+="dense_zero_rows"->rowCount.toLong
        val rd=declaration(row,RowType);val rc=connects(row)
        checked("ZERO_ROW_DRIVERS",rc.size==256 && rc.zipWithIndex.forall{case(c,i)=>
          c.loc match {case x:SubIndex=>x.expr.isInstanceOf[Reference]&&x.expr.asInstanceOf[Reference].name==row&&x.value==i;case _=>false}
        })
        checked("ZERO_EXACT_LITERAL",rc.forall(_.expr==UIntLiteral(0,IntWidth(32))))
        before(rd,rc.head,write);before(rc.last,tileConnect,write)
        rc.sliding(2).foreach{pair=>if(pair.size==2)before(pair.head,pair.last,write)}
        rc.foreach(c=>allowed.put(c,true));allowed.put(tileConnect,true);elementCount+=rc.size;counts+="dense_zero_elements"->elementCount.toLong
      }
      allowed.put(write,true)
    }
    checked("ZERO_CLOSURE_COUNTS",owned.size==34 && rowCount==32 && elementCount==8192)
    ss.foreach{s=>
      var used=Set.empty[String];s.foreachExpr(e=>used++=references(e))
      checked("ZERO_REFERENCE_CLOSURE",!used.exists(owned)||allowed.containsKey(s))
    }
  }
  private def references(e:Expression):Set[String]={
    var out=e match {case r:Reference=>Set(r.name);case _=>Set.empty[String]}
    e.foreachExpr(x=>out++=references(x));out
  }
  private def preserveStructure(before:Statement,after:Statement,replacements:java.util.IdentityHashMap[Statement,Statement]):Unit={
    if(replacements.containsKey(before))checked("NONREPLACED_STRUCTURE",after==replacements.get(before))
    else (before,after) match {
      case(a:Block,b:Block)=>
        checked("NONREPLACED_STRUCTURE",a.stmts.size==b.stmts.size)
        a.stmts.zip(b.stmts).foreach{case(x,y)=>preserveStructure(x,y,replacements)}
      case(a:Conditionally,b:Conditionally)=>
        checked("CONDITIONAL_STRUCTURE",a.info==b.info&&a.pred==b.pred)
        preserveStructure(a.conseq,b.conseq,replacements);preserveStructure(a.alt,b.alt,replacements)
      case(a,b)=>checked("NONREPLACED_STRUCTURE",a==b)
    }
  }

  def apply(c:Circuit, expectedCanonical:String):Circuit={
    counts=Map.empty
    checked("CANONICAL_FORMAT",expectedCanonical.matches("[0-9a-f]{64}"),"approved canonical module pin required")
    val ms=c.modules.collect{case m:Module if m.name==ModuleName=>m}
    checked("ONE_CORE",ms.size==1,"one exact original Core module")
    val original=ms.head;val text=original.serialize
    checked("CORE_INTEGRITY",chiseltest.simulator.CanonicalHighGate.moduleSemanticSha(ms.head)==expectedCanonical,"entire actual Core high AST drift")
    checked("FRESH_NAMES",!text.contains("sim_denseacc_"),"fresh finite simulation names")
    val ss=all(original.body)
    val ds=ss.collect{case r:DefRegister if r.name=="denseAcc"=>r}
    checked("DENSE_REGISTER",ds.size==1 && ds.head.tpe==TileType && ds.head.reset==zero &&
      ds.head.init.serialize=="denseAcc" && ds.head.clock.serialize=="clock","exact unreset original131072bit register")
    def regType(n:String,t:Type):Unit={val a=ss.collect{case r:DefRegister if r.name==n=>r};checked("INDEX_REGISTERS",a.size==1 && a.head.tpe==t)}
    regType("denseRow",u(5));regType("denseBeat",u(4))
    val nodeSeq=ss.collect{case n:DefNode=>n}
    val nodes=nodeSeq.map(n=>n.name->n).toMap
    checked("UNIQUE_NODES",nodes.size==nodeSeq.size,"unique original node names")
    for(i<-0 until 16){
      val n=s"_selectedDense_${i}_T"
      val k=UIntLiteral(BigInt(i),IntWidth(math.max(1,BigInt(i).bitLength))).serialize
      val expected=Seq(n->"bits(denseRow, 3, 0)",(n+"_1")->"shl(denseBeat, 4)",
        (n+"_2")->s"add(${n}_1, $k)",(n+"_3")->s"tail(${n}_2, 1)")
      expected.foreach{case(name,value)=>checked("READ_INDEX_NODES",nodes.get(name).exists(_.value.serialize==value),"exact original bounded index "+name)}
    }
    // Full4bit beat and each i0..15 imply column=16*beat+i in0..255;
    // row is ORIGINAL bits(denseRow,3,0), including original alias for16..31.
    val oldWrites=ss.collect{case x:Connect if x.loc.serialize=="denseAcc"=>x}
    checked("BULK_SOURCES",oldWrites.size==3 && oldWrites.head.expr.serialize=="matrixResult.bits.value" && oldWrites.tail.forall(_.expr.isInstanceOf[Reference]),"three ordered original bulk writes")
    proveZeroClosures(original,oldWrites)

    checked("DENSE_REFERENCE_COUNT",refCount(original.body)==20,"exact self-init+three writes+sixteen reads; reject unknown access")
    var declarations=0;var writeSites=0;val reads=scala.collection.mutable.Set.empty[Int]
    val replacements=new java.util.IdentityHashMap[Statement,Statement]()
    def replace(old:Statement,next:Statement):Statement={replacements.put(old,next);next}
    def visit(s:Statement):Statement=s match {
      case r:DefRegister if r.name=="denseAcc"=>declarations+=1;replace(r,Block(declaration+:defaults))
      case x:Connect if x.loc.serialize=="denseAcc"=>
        writeSites+=1;replace(x,Block(writes(x.expr))) // same original conditional / source position
      case x:Connect if x.expr.serialize.startsWith("denseAcc[")=>
        val i=(0 until 16).find(j=>x.loc.serialize==s"selectedDense[$j]").getOrElse(
          throw new DenseShapeRejected("READ_CONSUMER"))
        checked("READ_EXACT",!reads(i) && x.expr.serialize==s"denseAcc[_selectedDense_${i}_T][_selectedDense_${i}_T_3]","exact original read")
        reads+=i
        val value=x.copy(expr=bits(ref(BeatName),32*i+31,32*i))
        replace(x,if(i==0)Block(readPrelude:+value)else value)
      case x=>x.mapStmt(visit)
    }
    val changed=original.copy(body=visit(original.body))
    preserveStructure(original.body,changed.body,replacements)
    checked("CORE_INFO",changed.info==original.info)
    checked("CORE_PORTS",changed.ports==original.ports)
    checked("REWRITE_COUNTS",declarations==1 && writeSites==3 && reads.toSet==(0 until 16).toSet,"finite exact substitution counts")
    checked("NO_OLD_STORAGE_PORTS",refCount(changed.body)==0 && changed.ports==original.ports,"no duplicate old storage; complete public ABI unchanged")
    val result=c.copy(modules=c.modules.map{case m if m eq original=>changed;case m=>m})
    checked("OTHER_MODULE_IDENTITY",result.modules.zip(c.modules).forall{case(a,b)=>(b eq original)||(a eq b)},"all other original module objects preserved")
    check(result);result
  }
  def check(c:Circuit):Unit={
    val ms=c.modules.collect{case m:Module if m.name==ModuleName=>m};checked("POST_ONE_CORE",ms.size==1)
    val ss=all(ms.head.body);val mems=ss.collect{case m:DefMemory if m.name==MemName=>m}
    checked("POST_ONE_MEMORY",mems.size==1,"one denseAcc replacement memory")
    val m=mems.head
    checked("POST_MEMORY_SHAPE",m.dataType==u(8192) && m.depth==16 && m.writeLatency==1 && m.readLatency==0 &&
      m.readers==Seq("r") && m.writers==Writers && m.readwriters.isEmpty && m.readUnderWrite==ReadUnderWrite.Undefined,"same capacity/parallel write ports/zero-latency read")
    checked("POST_NO_REGISTERS",!ss.exists{case r:DefRegister=>r.name=="denseAcc"||r.name.startsWith("denseAcc_");case _=>false},"no duplicate original register storage")
  }
}
