package heteronpu.continuous.model
import java.nio.file.{Files,Paths}
import scala.jdk.CollectionConverters._
object NativeLeafTrace {
 def rows(path:String,count:Int):Vector[Vector[BigInt]]={
  val p=Paths.get(path);require(Files.size(p)<=4L*1024*1024,"bounded vector input")
  val lines=Files.readAllLines(p).asScala.toVector;require(lines.nonEmpty&&lines.size<=4096)
  lines.map{s=>require(s.length<=32768);val parts=s.trim.split("\\s+");require(parts.length==count)
   parts.map{v=>require(v.matches("[0-9a-fA-F]{1,8}"));BigInt(v,16)}.toVector}
 }
 def matrixInputs(row:Vector[BigInt]):Map[String,BigInt]={
  require(row.size==64);NativeApiChecks.bit(row.head)
  MatrixNativeLayout.inputs.map{f=>
   val v=(0 until f.words).foldLeft(BigInt(0)){(a,i)=>a|(row(1+f.offset+i)<<(32*i))}
   require(v.bitLength<=f.width);f.name->v}.toMap
 }
 def outputWords(values:Map[String,BigInt]):Vector[BigInt]={
  require(values.keySet==MatrixNativeLayout.outputWidths.keySet)
  MatrixNativeLayout.outputs.flatMap{f=>val v=values(f.name);require(v>=0&&v.bitLength<=f.width)
   (0 until f.words).map(i=>(v>>(32*i))&BigInt("ffffffff",16))}
 }
 def printMatrix(row:Int,clock:BigInt,out:Map[String,BigInt],edges:(Long,Long)):Unit=
  println((Vector(row.toString,clock.toString)++outputWords(out).map(v=>f"${v.toLong}%08x")++Vector(edges._1.toString,edges._2.toString)).mkString(" "))
}
/** JNA execution only. Requires direct-port/C ABI traces independently first. */
object MatrixJnaTrace {
 def main(args:Array[String]):Unit={
  require(args.length==3,"library sha256 vectors")
  val native=new RetainedMatrixNativeLeaf(NativeLibraryPin(args(0),args(1)))
  try{chiseltest.simulator.ActualJvmProcessObservation.capture(java.nio.file.Paths.get("."),"matrix_jna");for((row,i)<-NativeLeafTrace.rows(args(2),64).zipWithIndex){
   native.drive(NativeLeafTrace.matrixInputs(row));native.evaluate();native.clock(row.head)
   val out=native.read();require(native.read()==out,"repeated getter state");NativeLeafTrace.printMatrix(i,row.head,out,native.edgeCounts)
  }}finally native.close()
 }
}
/** Callback order exercise is separate from actual Treadle scheduling proof. */
object MatrixCallbackPermutationDifferential {
 def main(args:Array[String]):Unit={
  require(args.length==3);val pin=NativeLibraryPin(args(0),args(1))
  val native=new RetainedMatrixNativeLeaf(pin);var direct:RetainedMatrixNativeLeaf=null
  val box=new MatrixNativeBlackBox("matrix",native,()=>())
  try{direct=new RetainedMatrixNativeLeaf(pin)
   chiseltest.simulator.ActualJvmProcessObservation.capture(java.nio.file.Paths.get("."),"matrix_callbacks")
   var previous=BigInt(0);var rises=0L
   val digest=java.security.MessageDigest.getInstance("SHA-256")
   val transitions=java.security.MessageDigest.getInstance("SHA-256")
   for((row,i)<-NativeLeafTrace.rows(args(2),64).zipWithIndex){
    val values=NativeLeafTrace.matrixInputs(row);val next=row.head
    def callback():Unit=if(next!=previous)box.clockChange(if(next==1)treadle2.executable.PositiveEdge else treadle2.executable.NegativeEdge,"matrix.clk_i")
    if(i%3==0)callback()
    val setters=values.toVector.sortBy(_._1);for((n,v)<-if(i%2==0)setters else setters.reverse)box.inputChanged(n,v)
    if(i%3==1)callback()
    def get(port:String,clock:BigInt):BigInt={val v=box.outputDependencies(port).map{case "clk_i"=>clock;case n=>values(n)}
     box.getOutput(v,firrtl2.ir.UIntType(firrtl2.ir.IntWidth(MatrixNativeLayout.outputWidths(port))),port)}
    get("out_valid_o",previous)
    direct.drive(values);direct.evaluate();direct.clock(next);val expected=direct.read()
    val ports=MatrixNativeLayout.outputs.map(_.name);for(n<-if(i%2==0)ports else ports.reverse){require(get(n,next)==expected(n),s"callback row $i port $n");require(get(n,next)==expected(n),"repeated getter")}
    if(i%3==2)callback()
    if(previous==0&&next==1){rises+=1;NativeEdgeSnapshot.update(digest,MatrixNativeLayout.inputWidths,values)}
    if(previous!=next)NativeEdgeSnapshot.updateTransition(transitions,MatrixNativeLayout.inputWidths,values,previous,next)
    require(box.positiveEdges==rises&&box.nativeEdgeCounts==direct.edgeCounts)
    require(box.edgeSnapshotSha256==NativeEdgeSnapshot.current(digest),"complete positive-edge inputs")
    require(box.transitionSnapshotSha256==NativeEdgeSnapshot.current(transitions),"complete all-transition inputs")
    previous=next
   }
   println("MATRIX_CALLBACK_DIFFERENTIAL_EXECUTED_NOT_FULL_HOST")
  }finally{try{if(direct!=null)direct.close()}finally box.abortUnqualifiedConstruction()}
 }
}
