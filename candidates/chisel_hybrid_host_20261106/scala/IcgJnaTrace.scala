package heteronpu.continuous.model
object IcgJnaTrace {
 def main(args:Array[String]):Unit={
  require(args.length==3);val native=new RetainedIcgNativeLeaf(NativeLibraryPin(args(0),args(1)))
  try{chiseltest.simulator.ActualJvmProcessObservation.capture(java.nio.file.Paths.get("."),"icg_jna");for((row,i)<-NativeLeafTrace.rows(args(2),3).zipWithIndex){
   row.foreach(NativeApiChecks.bit);native.drive(row(1),row(2));native.evaluate();native.clock(row.head)
   val out=native.read();require(native.read()==out)
   println((Vector(i.toString,row.head.toString,out.toString)++native.edgeCounts.map(_.toString)).mkString(" "))
  }}finally native.close()
 }
}
