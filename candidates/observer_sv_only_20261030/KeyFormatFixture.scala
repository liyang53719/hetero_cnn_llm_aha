package chiseltest.simulator
import firrtl2._
import firrtl2.ir._
import java.io.StringWriter
import java.nio.file.{Files,Paths,StandardOpenOption}
object KeyFormatFixture {
 val fields=Seq("identity"->32,"slot"->2,"ng"->16,"index"->11)
 def main(args:Array[String]):Unit={
  for(name<-Seq("Public21QkvReductionRouter","TransposedDenseDownOwner");fresh<-Seq(false,true)){
   val ports=collection.mutable.ArrayBuffer[Port](Port(NoInfo,"clock",Input,ClockType),Port(NoInfo,"source",Input,UIntType(IntWidth(32))),Port(NoInfo,"result",Output,UIntType(IntWidth(32))))
   val stmts=collection.mutable.ArrayBuffer[Statement](Connect(NoInfo,WRef("result",UIntType(IntWidth(32)),PortKind,SinkFlow),WRef("source",UIntType(IntWidth(32)),PortKind,SourceFlow)))
   for((f,w)<-fields){
    val src=if(name=="Public21QkvReductionRouter")"io_tiles_response_bits_key_"+f else "banks_io_tiles_response_bits_key_"+f
    val dst=if(name=="Public21QkvReductionRouter")"io_residentTiles_response_bits_key_"+f else "io_tiles_response_bits_key_"+f
    val t=UIntType(IntWidth(w));val info=FileInfo(StringLit("/synthetic/Format.scala 1:1"))
    if(fresh||name=="TransposedDenseDownOwner")ports+=Port(info,src,Input,t)
    if(name=="TransposedDenseDownOwner"){
     ports+=Port(NoInfo,"legacy_"+f,Output,t)
     stmts+=Connect(NoInfo,WRef("legacy_"+f,t,PortKind,SinkFlow),WRef(src,t,PortKind,SourceFlow))
    }
    if(fresh){ports+=Port(info,dst,Output,t);stmts+=Connect(info,WRef(dst,t,PortKind,SinkFlow),WRef(src,t,PortKind,SourceFlow))}
   }
   val c=Circuit(NoInfo,Seq(Module(NoInfo,name,ports.toSeq,Block(stmts.toSeq))),name)
   val out=new StringWriter;new SystemVerilogEmitter().emit(CircuitState(c,Seq.empty),out)
   Files.write(Paths.get((if(fresh)"new-"else"old-")+name+".sv"),out.toString.getBytes("UTF-8"),StandardOpenOption.CREATE_NEW)
  }
 }
}
