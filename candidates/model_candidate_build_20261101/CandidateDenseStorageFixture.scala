package chiseltest.simulator
import firrtl2.ir._
import heteronpu.continuous.model.{PortableHostDenseAccMemoryLowering,CandidateDenseAccMemoryLoweringV2=>V2}
import java.nio.file.{Files,Paths}
import java.nio.charset.StandardCharsets.UTF_8
object CandidateDenseStorageFixture {
 val OldCore="9e3ba17f1c0f6353480abe57ef1db050b30cb953241df943cdcd043701286ca2"
 def main(args:Array[String]):Unit={
  require(args.length==1)
  val raw=Files.readAllBytes(Paths.get(args(0)));require(raw.length<8*1024*1024)
  val c=firrtl2.Parser.parse(new String(raw,UTF_8));require(c.modules.size==1 && c.main=="Qwen2ContinuousBlock")
  val core=c.modules.head.asInstanceOf[Module]
  require(CanonicalHighGate.moduleSemanticSha(core)==OldCore,"exact prior actual canonical Core, not inherited run PASS")
  val sentinel=Module(NoInfo,"Sentinel",Seq.empty,EmptyStmt)
  def circuit(m:Module)=c.copy(modules=Seq(m,sentinel))
  def run(m:Module)=V2(circuit(m),CanonicalHighGate.moduleSemanticSha(m))
  def digest(s:String)=java.security.MessageDigest.getInstance("SHA-256").digest(s.getBytes(UTF_8)).map(b=>f"${b&255}%02x").mkString
  val oldResult=PortableHostDenseAccMemoryLowering(circuit(core),OldCore)
  val newResult=run(core);require(oldResult==newResult && (newResult.modules.last eq sentinel))
  require(oldResult.serialize==newResult.serialize)
  require(CanonicalHighGate.circuitSemanticSha(oldResult)==CanonicalHighGate.circuitSemanticSha(newResult))
  println("DENSE_FIXTURE_OUTPUT serialize_sha256="+digest(newResult.serialize)+" canonical_sha256="+CanonicalHighGate.circuitSemanticSha(newResult))
  val names=((10 to 26)++(28 to 44)).map(i=>s"_WIRE_$i").toSet
  def renamed(n:String)=if(names(n))"alphaDenseZero"+n else n
  def expr(e:Expression):Expression=e.mapExpr(expr) match {case r:Reference=>r.copy(name=renamed(r.name));case x=>x}
  // Explicitly preserve nested Block containers. FIRRTL Block.mapStmt is a
  // simplifying traversal; it must not be used for an exact alpha-only oracle.
  def renameStmt(s:Statement):Statement=s match {
    case b:Block=>b.copy(stmts=b.stmts.map(renameStmt))
    case c:Conditionally=>c.copy(pred=expr(c.pred),conseq=renameStmt(c.conseq),alt=renameStmt(c.alt))
    case other=>other.mapExpr(expr) match {case w:DefWire=>w.copy(name=renamed(w.name));case y=>y}
  }
  val nested=Block(Seq(Block(Seq(DefNode(NoInfo,"fixtureNode",UIntLiteral(0,IntWidth(1)))))))
  val genericMapped=nested.mapStmt((s:Statement)=>s)
  require(genericMapped!=nested && genericMapped.serialize==nested.serialize,"official generic Block mapStmt flattens container")
  require(renameStmt(nested)==nested,"alpha oracle retains unrelated nested Block")
  def rename(m:Module)=m.copy(body=renameStmt(m.body))
  val alpha=rename(core);val alphaResult=run(alpha)
  val alphaExpected=rename(oldResult.modules.head.asInstanceOf[Module])
  if(alphaResult.modules.head!=alphaExpected){
    def tag(x:Any):String=x match {case p:Product=>p.productPrefix.filter(c=>c.isLetterOrDigit||c=='_').take(64);case _:String=>"String";case _=>"Other"}
    def first(initialA:Any,initialB:Any,initialPath:String,initialDepth:Int):Unit={
      var a=initialA;var b=initialB;var path=Vector(initialPath);var depth=initialDepth;var found=false
      while(a!=b && !found){
        require(depth<4096,"bounded iterative mismatch diagnostic")
        (a,b)match {
          case(x:Seq[_],y:Seq[_]) if x.size==y.size=>
            val i=x.indices.find(i=>x(i)!=y(i)).get;a=x(i);b=y(i);path=(path:+("s"+i)).takeRight(24)
          case(x:Product,y:Product) if x.productPrefix==y.productPrefix && x.productArity==y.productArity=>
            val i=(0 until x.productArity).find(i=>x.productElement(i)!=y.productElement(i)).get
            a=x.productElement(i);b=y.productElement(i);path=(path:+("p"+i)).takeRight(24)
          case _=>
            println("DENSE_ALPHA_FIRST_DIFF depth="+depth+" path_suffix="+path.mkString("/")+" actual_kind="+tag(a)+" expected_kind="+tag(b)+" actual_sha="+digest(a.toString)+" expected_sha="+digest(b.toString));found=true
        };depth+=1
      }
    }
    println("DENSE_ALPHA_SERIALIZE actual_sha="+digest(alphaResult.modules.head.serialize)+" expected_sha="+digest(alphaExpected.serialize))
    first(alphaResult.modules.head,alphaExpected,"root",0)
  }
  require(alphaResult.modules.head==alphaExpected)
  var oldRejected=false
  try{PortableHostDenseAccMemoryLowering(circuit(alpha),CanonicalHighGate.moduleSemanticSha(alpha))}catch{case _:IllegalArgumentException=>oldRejected=true}
  require(oldRejected,"old generated-name limitation must reproduce")
  def alter(m:Module)(f:Statement=>Statement):Module={def go(s:Statement):Statement=f(s.mapStmt(go));m.copy(body=go(m.body))}
  def rejected(label:String,m:Module,code:String):Unit={
    var actual="NONE";try{run(m)}catch{case e:V2.DenseShapeRejected=>actual=e.code}
    require(actual==code,s"finite fixture expectation $label $actual")
    println(s"DENSE_FIXTURE_REJECT $label $actual")
  }
  rejected("nonzero",alter(core){case x:Connect if x.loc.serialize=="_WIRE_10[0]"=>x.copy(expr=UIntLiteral(1,IntWidth(32)));case x=>x},"ZERO_EXACT_LITERAL")
  rejected("missing_element",alter(core){case x:Connect if x.loc.serialize=="_WIRE_10[0]"=>EmptyStmt;case x=>x},"ZERO_ROW_DRIVERS")
  val firstWrite={def all(s:Statement):Seq[Statement]=Seq(s)++{val a=Vector.newBuilder[Statement];s.foreachStmt(x=>a++=all(x));a.result()};all(core.body).collectFirst{case x:Connect if x.loc.serialize=="denseAcc"=>x}.get}
  rejected("extra_write",core.copy(body=Block(Seq(core.body,firstWrite))),"BULK_SOURCES")
  rejected("index_change",alter(core){case n:DefNode if n.name=="_selectedDense_0_T"=>n.copy(value=DoPrim(firrtl2.PrimOps.Bits,Seq(Reference("denseRow")),Seq(BigInt(4),BigInt(0)),UnknownType));case x=>x},"READ_INDEX_NODES")
  rejected("moved_condition",alter(core){case x:Connect if x.loc.serialize=="_WIRE_10[0]"=>Conditionally(NoInfo,UIntLiteral(1,IntWidth(1)),x,EmptyStmt);case x=>x},"ZERO_SAME_BLOCK")
  rejected("extra_consumer",core.copy(body=Block(Seq(core.body,DefNode(NoInfo,"unreviewedConsumer",Reference("_WIRE_10"))))),"ZERO_REFERENCE_CLOSURE")
  rejected("duplicate_driver",alter(core){case x:Connect if x.loc.serialize=="_WIRE_10[0]"=>Block(Seq(x,x));case x=>x},"ZERO_ROW_DRIVERS")
  rejected("wrong_row_type",alter(core){case x:DefWire if x.name=="_WIRE_10"=>x.copy(tpe=VectorType(UIntType(IntWidth(16)),256));case x=>x},"ZERO_DECLARATIONS")
  rejected("duplicate_namespace",core.copy(body=Block(Seq(core.body,DefNode(NoInfo,"_WIRE_10",UIntLiteral(0,IntWidth(1)))))),"ZERO_DECLARATIONS")
  val reordered=alter(core){case b:Block=>
    val i=b.stmts.indexWhere{case c:Connect=>c.loc.serialize=="_WIRE_26[0]";case _=>false}
    val j=b.stmts.indexWhere{case c:Connect=>c.loc.serialize=="_WIRE_26[1]";case _=>false}
    if(i>=0&&j>=0)b.copy(stmts=b.stmts.updated(i,b.stmts(j)).updated(j,b.stmts(i)))else b
    case x=>x}
  rejected("row_order",reordered,"ZERO_TILE_DRIVERS")
  println("DENSE_FIXTURE_COMPLETE_PRIOR_CORE_AND_ALPHA_ONLY_NOT_ACTUAL_NEW_HIGH_OR_NUMERICS")
 }
}
