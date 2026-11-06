package heteronpu.continuous.model
import firrtl2.ir._
import treadle2.{ScalaBlackBox,ScalaBlackBoxFactory}

object AllNativeRetainedModelFactory {
 val route="hybrid Chisel Host + native original RTL leaves"
 val matrixName="qwen2_matrix_command_endpoint"
 val icgName="tc_clk_gating"
 private val icgPorts:Map[String,(Direction,Type)]=Map(
  "clk_i"->((Input:Direction),(ClockType:Type)),"en_i"->((Input:Direction),(UIntType(IntWidth(1)):Type)),
  "test_en_i"->((Input:Direction),(UIntType(IntWidth(1)):Type)),"clk_o"->((Output:Direction),(ClockType:Type)))
 /** Validation only: no native loads, allocations, simulator construction or tokens. */
 def validateInventory(circuit:Circuit):Map[String,String]={
  val modules=circuit.modules.map(m=>m.name->m).toMap
  require(modules.size==circuit.modules.size,"unique actual modules")
  require(modules.get(circuit.main).exists(_.isInstanceOf[Module]),"regular actual top")
  val expected=scala.collection.mutable.Map.empty[String,String]
  def visit(moduleName:String,path:String,ancestors:Set[String]):Unit={
   require(!ancestors(moduleName),"nonrecursive original hierarchy")
   modules.getOrElse(moduleName,throw new IllegalArgumentException("unresolved actual module "+moduleName)) match {
    case e:ExtModule=>
     val ports=e.defname match {
      case `matrixName`=>MatrixNativeLayout.expectedPorts
      case `icgName`=>icgPorts
      case IdmaSplitLayout.modelName=>IdmaSplitLayout.ports.map(p=>p.name->(p.direction,p.tpe)).toMap
      case other=>throw new IllegalArgumentException("unknown actual external leaf "+other)
     }
     require(e.ports.map(_.name).distinct.size==e.ports.size,"unique actual port names")
     require(e.ports.size==ports.size&&e.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==ports,"complete exact native port ABI "+e.name)
     val params=if(e.defname==matrixName)Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1)))else Seq.empty
     require(e.params==params,"exact original leaf parameters")
     require(path.nonEmpty && !expected.contains(path),"unique actual instance path")
     expected(path)=e.defname
    case m:Module=>
     def walk(s:Statement):Unit={
      s match{case i:DefInstance=>visit(i.module,if(path.isEmpty)i.name else path+"."+i.name,ancestors+moduleName);case _=>()}
      s.foreachStmt(walk)
     };walk(m.body)
   }
  }
  visit(circuit.main,"",Set.empty)
  require(expected.values.count(_==matrixName)==8,"eight independent512-lane Matrix endpoints")
  require(expected.values.count(_==icgName)==8,"eight original low-transparent ICGs")
  require(expected.values.count(_==IdmaSplitLayout.modelName)==1&&expected.size==17,"exact8+8+1 native leaves")
  expected.toMap
 }
}

/** Independent runnable factory implementation, not a qualification claim.
  * Constructor validates only; createInstance creates one NEW native object
  * per actual instance. No old functional or metadata model is reachable. */
final class AllNativeRetainedModelFactory(circuit:Circuit,matrixLibrary:NativeLibraryPin,
 icgLibrary:NativeLibraryPin,idmaLibrary:NativeLibraryPin)
 extends ScalaBlackBoxFactory with AutoCloseable {
 import AllNativeRetainedModelFactory._
 val bindingInventory:Map[String,String]=validateInventory(circuit)
 private val instantiated=scala.collection.mutable.Set.empty[String]
 private val matrices=scala.collection.mutable.Map.empty[String,MatrixNativeBlackBox]
 private val gates=scala.collection.mutable.Map.empty[String,IcgNativeBlackBox]
 private val dmas=scala.collection.mutable.Map.empty[String,CheckedIdmaFieldSplitBlackBox]
 private var closed=false
 private def q(x:String):String=NativeApiChecks.quoted(x)
 def bindingInventoryJson:String=bindingInventory.toVector.sortBy(_._1).map{case(n,d)=>q(n)+":"+q(d)}.mkString("{",",","}")
 def factoryContractJson:String={
  val pins=Vector("matrix"->matrixLibrary,"icg"->icgLibrary,"idma"->idmaLibrary).map{case(n,p)=>q(n)+":"+q(p.sha256)}.mkString("{",",","}")
  "{\"schema\":\"ALL_NATIVE_RETAINED_FACTORY_V1\",\"route\":"+q(route)+
   ",\"qualified\":false,\"pureOriginalChisel\":false,\"finalSameRtlReplay\":false,\"matrixSeed\":1,\"matrixLanes\":4096,\"icgDefaultIsFunctional\":1,\"matrixAbiSha256\":"+
   q(MatrixNativeLayout.contractSha256)+",\"nativeLibrarySha256\":"+pins+",\"bindings\":"+bindingInventoryJson+"}"
 }
 def edgeAuditJson:String={
  val m=matrices.toVector.sortBy(_._1).map{case(n,b)=>q(n)+":{\"rises\":"+b.positiveEdges+",\"falls\":"+b.negativeEdges+",\"nativeEdges\":["+b.nativeEdgeCounts.productIterator.mkString(",")+"],\"snapshotSha256\":"+q(b.edgeSnapshotSha256)+",\"allTransitionSnapshotSha256\":"+q(b.transitionSnapshotSha256)+"}"}
  val g=gates.toVector.sortBy(_._1).map{case(n,b)=>q(n)+":{\"rises\":"+b.positiveEdges+",\"falls\":"+b.negativeEdges+",\"nativeInputAndGatedEdges\":["+b.nativeEdgeCounts.mkString(",")+"],\"snapshotSha256\":"+q(b.edgeSnapshotSha256)+",\"allTransitionSnapshotSha256\":"+q(b.transitionSnapshotSha256)+"}"}
  val d=dmas.toVector.sortBy(_._1).map{case(n,b)=>q(n)+":{\"rises\":"+b.positiveEdges+",\"snapshotSha256\":"+q(b.edgeSnapshotSha256)+"}"}
  (m++g++d).mkString("{",",","}")
 }
 def requireCompleteBinding():Unit={
  require(!closed,"live all-native factory")
  require(instantiated.toSet==bindingInventory.keySet&&boxes.size==17,"exact original instance binding set")
  require(matrices.size==8&&gates.size==8&&dmas.size==1,"independent native state inventory8+8+1")
 }
 override def createInstance(instanceName:String,blackBoxName:String):Option[ScalaBlackBox]={
  require(!closed&&bindingInventory.get(instanceName).contains(blackBoxName)&& !instantiated(instanceName),"unique exact native binding")
  try {
   val leaf:ScalaBlackBox=blackBoxName match {
    case `matrixName`=>
     val native=new RetainedMatrixNativeLeaf(matrixLibrary)
     val b=try{new MatrixNativeBlackBox(instanceName,native,()=>requireCompleteBinding())}catch{case t:Throwable=>native.close();throw t}
     matrices(instanceName)=b;b
    case `icgName`=>
     val native=new RetainedIcgNativeLeaf(icgLibrary)
     val b=try{new IcgNativeBlackBox(instanceName,native,()=>requireCompleteBinding())}catch{case t:Throwable=>native.close();throw t}
     gates(instanceName)=b;b
    case IdmaSplitLayout.modelName=>
     val native=new CheckedRetainedIdmaNativeLeaf(idmaLibrary.path,idmaLibrary.sha256)
     val b=try{new CheckedIdmaFieldSplitBlackBox(instanceName,native,()=>requireCompleteBinding())}catch{case t:Throwable=>native.close();throw t}
     dmas(instanceName)=b;b
   }
   instantiated+=instanceName;Some(add(leaf))
  } catch {case t:Throwable=>try abortUnqualifiedConstruction() catch{case cleanup:Throwable=>t.addSuppressed(cleanup)};throw t}
 }
 def abortUnqualifiedConstruction():Unit=close()
 override def close():Unit={
  if(!closed){
   closed=true
   var error:Throwable=null
   val closers=matrices.values.toVector.map(b=>(()=>b.abortUnqualifiedConstruction()))++
    gates.values.toVector.map(b=>(()=>b.abortUnqualifiedConstruction()))++
    dmas.values.toVector.map(b=>(()=>b.abortUnqualifiedConstruction()))
   closers.foreach{f=>try f() catch{case t:Throwable=>if(error==null)error=t else error.addSuppressed(t)}}
   if(error!=null)throw error
  }
 }
}
