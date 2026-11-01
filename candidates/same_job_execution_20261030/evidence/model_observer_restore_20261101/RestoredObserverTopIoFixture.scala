package heteronpu.continuous {
import chisel3._
import chisel3.util._
/** Mechanically extracted actual Top IO only, not full Top behavior. */
class RestoredObserverTopIoFixture extends Module {
  val io=IO(new Bundle {
    val launch=Flipped(Decoupled(new HostCommandLaunchV4));val result=Decoupled(new HostCommandResult)
    val residentObservation=Output(Valid(new FfnResidentObservation))
    val rawScoreObservation=Output(Valid(new UnifiedMoeRouterScoreObservationV1))
    val completion=Decoupled(UInt(56.W));val axi=new BlockAxiMaster
    val resetRequired=Output(Bool());val idmaTransfers=Output(UInt(64.W))
    val idmaStreamedWriteBeats=Output(UInt(64.W))
    val idmaStreamedBeats=Output(UInt(64.W));val pipelineIssues=Output(UInt(64.W));val pipelineStalls=Output(UInt(64.W))
    val idmaReadBursts=Output(UInt(64.W));val idmaReadBeats=Output(UInt(64.W));val idmaCacheHits=Output(UInt(64.W))
    val pc=Output(UInt(16.W));val issuedJobs=Output(UInt(16.W))
    val usefulMacs=Output(UInt(64.W));val executedMacs=Output(UInt(64.W));val writeBytes=Output(UInt(64.W))
    val memoryAccepted=Output(Vec(2,UInt(64.W)));val memoryReturned=Output(Vec(2,UInt(64.W)))
  })
  io := DontCare
  dontTouch(io)
}
}
package chiseltest.simulator {
object RestoredObserverTopIoCheck {
 def main(args:Array[String]):Unit={
  require(args.length==2,"fixed typed contract and driver header contract")
  val (high,_)=chiseltest.simulator.Compiler.elaborate(()=>new heteronpu.continuous.RestoredObserverTopIoFixture,Seq(firrtl2.options.TargetDirAnnotation("observer-io-only")),Seq.empty)
  val low=chiseltest.simulator.Compiler.toLowFirrtl(high)
  val top=low.circuit.modules.collect{case m:firrtl2.ir.Module if m.name==low.circuit.main=>m}.head
  def width(p:firrtl2.ir.Port):BigInt=p.tpe match {
   case firrtl2.ir.UIntType(firrtl2.ir.IntWidth(w))=>w
   case firrtl2.ir.ClockType=>BigInt(1)
   case firrtl2.ir.ResetType=>BigInt(1)
   case firrtl2.ir.AsyncResetType=>BigInt(1)
   case _=>throw new IllegalArgumentException("unsupported top type")
  }
  def direction(p:firrtl2.ir.Port):String=p.direction match {case firrtl2.ir.Input=>"input";case firrtl2.ir.Output=>"output"}
  val actual=ujson.Arr.from(top.ports.map(p=>ujson.Obj("name"->p.name,"direction"->direction(p),"type"->p.tpe.serialize,"width"->width(p).toDouble)))
  val expected=ujson.read(java.nio.file.Files.readString(java.nio.file.Paths.get(args(0))))("typed_ports")
  if(actual!=expected){actual.arr.zip(expected.arr).zipWithIndex.filter{case((a,b),_)=>a!=b}.take(2).foreach{case((a,b),i)=>println("IO_TYPED_DIFFERENCE index="+i+" actual="+ujson.write(a)+" expected="+ujson.write(b))}}
  require(actual==expected,"exact full ordered typed122 actual IO")
  val header=ujson.read(java.nio.file.Files.readString(java.nio.file.Paths.get(args(1)))).obj
  require(top.ports.size==122 && header.size==122 && top.ports.map(_.name).toSet==header.keySet.toSet,"exact122 driver contract")
  top.ports.foreach{p=>val h=header(p.name).arr;require(h(0).str==direction(p) && h(1).num==width(p).toDouble,"driver direction/width")}
  println("OBSERVER_ACTUAL_IO_122_AND_DRIVER_CONTRACT_PASS full_top_pass=false numerical_pass=false")
 }
}
}
