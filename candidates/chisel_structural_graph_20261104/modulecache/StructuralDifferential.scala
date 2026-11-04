package treadle2.executable

import firrtl2.ir._
import java.io.{OutputStream,PrintStream}
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Paths
import java.security.MessageDigest
import scala.util.control.NonFatal

/** FUTURE executable fixture, NOT RUN. Same driver must be used in separate
  * official and cached processes; no simulator, native or data-store creation. */
object StructuralDifferential {
  private def sha(b:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(b).map(x=>f"${x&255}%02x").mkString
  private def hash(s:String):String=sha(s.getBytes(UTF_8))
  private val u=UIntType(IntWidth(1))
  private val clock=Reference("clock",ClockType)
  private val enabled=Reference("en",u)
  private val one=UIntLiteral(1,IntWidth(1))
  private val ports=Vector(Port(NoInfo,"clock",Input,ClockType),Port(NoInfo,"en",Input,u))
  private def statements(prefix:String):Vector[Statement]=Vector.tabulate(3){i=>Vector[Statement](
    Stop(NoInfo,0,clock,enabled,s"${prefix}stop$i"),
    Print(NoInfo,StringLit("fixture"),Seq.empty,clock,enabled,s"${prefix}print$i"),
    Verification(Formal.Cover,NoInfo,clock,one,enabled,StringLit("fixture"),s"${prefix}cover$i")
  )}.flatten
  private def module(name:String):Module=Module(NoInfo,name,ports,Block(statements("")))
  private def circuit(m:Module):Circuit=Circuit(NoInfo,Seq(m),m.name)
  private def instance(n:String,m:String):Vector[Statement]=Vector(
    DefInstance(NoInfo,n,m,UnknownType),
    Connect(NoInfo,SubField(Reference(n),"clock",ClockType),clock),
    Connect(NoInfo,SubField(Reference(n),"en",u),enabled))
  private def fixtures:Vector[(String,Circuit,Boolean)]={
    val leaf=module("Leaf")
    val top=Module(NoInfo,"Top",ports,Block(instance("i0","Leaf")++instance("i1","Leaf")))
    val aa=module("Aa");val bb=module("BB")
    require(aa!=bb && aa.hashCode()==bb.hashCode(),"real Module hash collision fixture")
    val collidingTop=Module(NoInfo,"Top",ports,Block(instance("a","Aa")++instance("b","BB")))
    val cyc=Module(NoInfo,"Cycle",ports,Block(statements("")++Vector(DefWire(NoInfo,"x",u),DefWire(NoInfo,"y",u),
      Connect(NoInfo,Reference("x",u),Reference("y",u)),Connect(NoInfo,Reference("y",u),Reference("x",u)))))
    val bad=Module(NoInfo,"Bad",ports,Block(Vector(Stop(NoInfo,0,clock,enabled,"duplicate"),Stop(NoInfo,0,clock,enabled,"duplicate"))))
    val reg=DefRegister(NoInfo,"q",u,clock,UIntLiteral(0,IntWidth(1)),UIntLiteral(0,IntWidth(1)))
    val withReg=Module(NoInfo,"Registered",ports,Block(Vector(reg,Connect(NoInfo,Reference("q",u),one))++statements("")))
    Vector(("flat",circuit(module("Flat")),false),("repeated",Circuit(NoInfo,Seq(top,leaf),"Top"),false),
      ("hash_collision",Circuit(NoInfo,Seq(collidingTop,aa,bb),"Top"),false),
      ("registered",circuit(withReg),false),("cycle",circuit(cyc),true),("invalid_duplicate",circuit(bad),true))
  }
  // This exact block is injected from prepare_candidate.KEY_CODE; tests check
  // byte identity with the production candidate helper, not a hand-made variant.
  private def keyLaws():Unit={
    // Candidate optimization: memoize only structural hash computation.
    // Semantic map equality remains Module.equals, including equal distinct ASTs.
    // Valid only while the prepared immutable Module graph is unchanged.
    final class CachedModuleKey(val module: Module) {
      private val structuralHash: Int = module.hashCode()
      override def hashCode(): Int = structuralHash
      override def equals(other: Any): Boolean = other match {
        case that: CachedModuleKey => module.equals(that.module)
        case _ => false
      }
    }
    // Identity is ONLY the memoization lookup, never the semantic key relation.
    val cachedModuleKeys = new java.util.IdentityHashMap[Module, CachedModuleKey]()
    def moduleKey(module: Module): CachedModuleKey = {
      val previous = cachedModuleKeys.get(module)
      if (previous != null) previous
      else {
        val created = new CachedModuleKey(module)
        cachedModuleKeys.put(module, created)
        created
      }
    }
    def validateStableModuleHashes(): Unit = {
      val keys = cachedModuleKeys.values().iterator()
      while (keys.hasNext) {
        val key = keys.next()
        require(key.module.hashCode() == key.hashCode(), "prepared module hash changed during structural construction")
      }
    }
    val a=module("Aa");val equal=a.copy();val collision=module("BB")
    require((a ne equal) && a==equal && a.hashCode()==equal.hashCode())
    require(a!=collision && a.hashCode()==collision.hashCode())
    val unequalBody=a.copy(body=EmptyStmt)
    val unequalPorts=a.copy(ports=ports.take(1))
    val unequalInfo=a.copy(info=FileInfo(StringLit("fixture:1")))
    val ms=Vector(a,a,equal,collision,unequalBody,unequalPorts,unequalInfo)
    require(moduleKey(a) eq moduleKey(a))
    require((moduleKey(a) ne moduleKey(equal)) && moduleKey(a)==moduleKey(equal))
    val old=Vector.fill(3)(scala.collection.mutable.HashMap.empty[Module,AnyRef])
    val cached=Vector.fill(3)(scala.collection.mutable.HashMap.empty[CachedModuleKey,AnyRef])
    for(i<-0 until 512){
      val channel=i%3;val m=ms((i*13)%ms.size);val value=new Object
      val before=old(channel).get(m);val after=cached(channel).get(moduleKey(m))
      require(before.size==after.size && before.zip(after).forall{case(x,y)=>x eq y},"lookup value identity")
      old(channel)(m)=value;cached(channel)(moduleKey(m))=value
    }
    for(ch<-0 until 3;m<-ms)require(old(ch)(m) eq cached(ch)(moduleKey(m)))
    validateStableModuleHashes()
  }
  private def encode(x:Any):String=x match {
    case null=>"null"
    case s:Symbol=>"symbol:"+s.name
    case n:FirrtlNode=>"ir:"+n.serialize
    case s:String=>s.length+":"+s
    case n:java.lang.Number=>n.toString
    case b:Boolean=>b.toString
    case p:Product=>p.productPrefix+p.productIterator.map(encode).mkString("(",",",")")
    case _=>throw new IllegalArgumentException("unsupported fixture metadata type")
  }
  private def digestTable(t:SymbolTable):String={
    require(t.size<=4096,"small fixture symbol cap")
    val rows=Vector.newBuilder[String]
    t.symbols.toVector.sortBy(_.name).foreach{s=>
      rows+=Seq(s.name,s.dataSize.toString,s.dataType.toString,s.dataKind.toString,s.bitWidth.toString,
        s.slots.toString,s.firrtlType.serialize,s.info.serialize,s.index.toString,s.cardinalNumber.toString).map(encode).mkString("symbol:","|","")
      rows+=t.childrenOf.getEdges(s).toVector.map(_.name).sorted.map(encode).mkString("children:"+s.name+":","|","")
      rows+=t.parentsOf.getEdges(s).toVector.map(_.name).sorted.map(encode).mkString("parents:"+s.name+":","|","")
    }
    def names(label:String,x:Iterable[String]):Unit={rows+=x.toVector.sorted.map(encode).mkString(label+":","|","")}
    def pairs(label:String,x:Iterable[(Any,Any)]):Unit={rows+=x.toVector.map{case(a,b)=>encode(a)+"="+encode(b)}.sorted.mkString(label+":","|","")}
    names("orphans",t.orphans.map(_.name));names("instances",t.instanceNames);names("registers",t.registerNames)
    names("inputs",t.inputPortsNames);names("outputs",t.outputPortsNames)
    pairs("instanceModules",t.instanceNameToModuleName);pairs("registerClocks",t.registerToClock)
    pairs("stopInfo",t.stopToStopInfo);pairs("printInfo",t.printToPrintInfo);pairs("verifyInfo",t.verifyInfo)
    hash(rows.result().mkString("\n"))
  }
  private def loadedClassSha(c:Class[_],expectedLocation:String):String={
    require(Paths.get(c.getProtectionDomain.getCodeSource.getLocation.toURI).toRealPath()==Paths.get(expectedLocation).toRealPath(),"actual code source")
    val in=c.getResourceAsStream("/"+c.getName.replace('.','/')+".class")
    require(in!=null)
    try{val b=in.readAllBytes();require(b.length<=1024*1024);sha(b)}finally{in.close()}
  }
  def main(args:Array[String]):Unit={
    // label, pinned source SHA, compiled class SHA, companion SHA, code location
    val out=System.out;val err=System.err;val muted=new PrintStream(OutputStream.nullOutputStream())
    var result=Vector.empty[String];var ok=false
    try {
      System.setOut(muted);System.setErr(muted)
      Console.withOut(muted){Console.withErr(muted){
        require(args.length==5 && Set("official","cached")(args(0)))
        require(args.slice(1,4).forall(_.matches("[0-9a-f]{64}")))
        val classSha=loadedClassSha(classOf[SymbolTable],args(4))
        val companionSha=loadedClassSha(SymbolTable.getClass,args(4))
        require(classSha==args(2) && companionSha==args(3),"runtime class hashes")
        keyLaws()
        result=fixtures.map{case(id,c,mustFail)=>
          val before=c.serialize;val beforeHash=c.hashCode()
          var failure:Option[Throwable]=None;var digest=""
          try{digest=digestTable(SymbolTable(c,Seq.empty,allowCycles=false))}catch{case NonFatal(e)=>failure=Some(e)}
          require(c.serialize==before && c.hashCode()==beforeHash,"fixture AST unchanged")
          require(failure.nonEmpty==mustFail,"expected fixture outcome")
          val expectedError=Map("cycle"->"firrtl2.graph.CyclicException","invalid_duplicate"->"treadle2.executable.TreadleException")
          failure.foreach(e=>require(expectedError.get(id).contains(e.getClass.getName),"exact expected exception"))
          val outcome=failure.map(e=>"ERROR classSha="+hash(e.getClass.getName)).getOrElse("GRAPH digest="+digest)
          "STRUCTURAL_DIFF_CASE_V1 id="+id+" "+outcome
        }
        result :+= "STRUCTURAL_DIFF_RUN_V1 label="+args(0)+" sourceSha="+args(1)+" classSha="+classSha+" companionSha="+companionSha+" cases=6 keyLaws=PASS numericalPass=false"
        ok=true
      }}
    }catch{case NonFatal(_)=>result=Vector("STRUCTURAL_DIFF_RUN_V1 status=FAIL_FIXTURE_OR_LINKAGE numericalPass=false")}
    finally{System.setOut(out);System.setErr(err)}
    result.foreach(out.println);out.flush()
    if(!ok)System.exit(2)
  }
}
