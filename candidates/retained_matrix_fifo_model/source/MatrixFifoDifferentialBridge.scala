// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator
import chisel3.RawModule
import firrtl2.{AnnotationSeq,CircuitState}
import firrtl2.ir._
import firrtl2.annotations.UnrecognizedAnnotation
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.MatrixResultFifoMemoryLowering
import treadle2.{ClockInfoAnnotation,TreadleCircuitStateAnnotation}
import treadle2.executable.ClockInfo
import treadle2.stage.phases.{GetFirrtlAst,PrepareAst,SetImplicitOutputInfo}

/** Same actual original high AST, two interpretable representations. No second
  * Chisel elaboration or regenerated hardware; no parser/text substitutions.
  * Official low/PrepareAst remains mandatory on both sides. */
object MatrixFifoDifferentialBridge {
  private def all(s:Statement):Seq[Statement]=s+: {val b=Vector.newBuilder[Statement];s.foreachStmt(x=>b++=all(x));b.result()}
  private def fifo(c:Circuit):Module={val x=c.modules.collect{case m:Module if m.name=="MatrixResultFifo"=>m};require(x.size==1);x.head}
  private def annotationGate(a:AnnotationSeq):Unit={
    require(!a.exists(x=>x.isInstanceOf[UnsupportedAnnotation] || x.isInstanceOf[UnrecognizedAnnotation]),"uninterpreted annotation")
    // Deliberately conservative: any targeted high annotation requires an
    // explicit separately reviewed mapping; no stale storage targets allowed.
    require(a.forall(_.getTargets.isEmpty),"targeted annotations require explicit migration; none silently dropped")
    require(!a.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),"no second circuit annotation")
  }
  private def postHigh(original:Circuit,changed:Circuit):Unit={
    val a=fifo(original);val b=fifo(changed)
    require(a.ports==b.ports,"all FIFO ports unchanged")
    val users=original.modules.collect{case m:Module=>all(m.body).count{case i:DefInstance=>i.module=="MatrixResultFifo";case _=>false}}.sum
    require(users==1,"exact one full-capacity FIFO instance")
    require(changed==MatrixResultFifoMemoryLowering(original),"exact generated substitution, including every connection")
    val stmts=all(b.body);val mems=stmts.collect{case d:DefMemory=>d}
    require(mems.size==17 && mems.map(_.name).distinct.size==17,"exact17 memories")
    val expected=(0 until 16).map(i=>s"sim_storage_row_$i"->8192).toMap+("sim_storage_metadata"->37)
    require(mems.map(m=>m.name->m.dataType).toMap==expected.map{case(n,w)=>n->UIntType(IntWidth(w))})
    require(mems.forall(m=>m.depth==2 && m.readLatency==0 && m.writeLatency==1 && m.readers==Seq("r") && m.writers==Seq("w") && m.readwriters.isEmpty))
    val oldControl=all(a.body).collect{case d:DefRegister if d.name!="storage"=>d}
    val newControl=stmts.collect{case d:DefRegister=>d}
    require(newControl==oldControl && newControl.map(_.name).toSet==Set("head","tail","count"),"all original control registers exact")
    require(changed.modules.size==original.modules.size && changed.modules.zip(original.modules).forall{case(x,y)=>y.name=="MatrixResultFifo" || (x eq y)},"other original modules exact objects")
  }
  private def preparedGate(c:Circuit,memory:Boolean):Unit={
    require(!c.modules.exists(_.isInstanceOf[ExtModule]),"FIFO differential has no black boxes")
    val m=fifo(c);val ss=all(m.body);val mems=ss.collect{case x:DefMemory=>x}
    if(memory){
      require(mems.size==17,"official preparation preserves17 memories")
      val expected=(0 until 16).map(i=>s"sim_storage_row_$i"->8192).toMap+("sim_storage_metadata"->37)
      require(mems.map(x=>x.name->x.dataType).toMap==expected.map{case(n,w)=>n->UIntType(IntWidth(w))})
      require(mems.forall(x=>x.depth==2 && x.readLatency==0 && x.writeLatency==1))
      require(!ss.exists{case x:DefRegister=>x.name=="storage"||x.name.startsWith("storage_");case _=>false},"no duplicated old storage")
    }else {require(mems.isEmpty,"original remains register-backed")
      require(ss.collect{case x:DefRegister if x.name.startsWith("storage_")=>x}.size==8200,"all8192 data words and8 metadata registers")}
  }
  // Each representation owns separate official output and exact serialized
  // snapshots. Never use one overwritten filename as evidence for both ASTs.
  private def retain(c:Circuit,dir:java.nio.file.Path,label:String):Unit={
    import java.nio.file.{Files,StandardOpenOption}
    val bytes=c.serialize.getBytes(java.nio.charset.StandardCharsets.UTF_8)
    val hash=java.security.MessageDigest.getInstance("SHA-256").digest(bytes).map(b=>f"${b&255}%02x").mkString
    // Only the final prepared snapshot is duplicated explicitly; official low
    // outputs have separate directories. High/low identities are producer hashes.
    val retained=label=="prepared"
    if(retained)Files.write(dir.resolve(s"snapshot-$label.fir"),bytes,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
    val identity=s"sha256=$hash bytes=${bytes.length} explicitSnapshot=$retained label=$label\n"
    Files.write(dir.resolve(s"snapshot-$label.identity"),identity.getBytes(java.nio.charset.StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
  }
  private def prepare(h:CircuitState,memory:Boolean):(CircuitState,AnnotationSeq)={
    val name=if(memory)"memory"else"original"
    val dir=java.nio.file.Paths.get("fifo-differential",name)
    java.nio.file.Files.createDirectories(dir)
    val scoped=h.copy(annotations=h.annotations.filterNot(_.isInstanceOf[TargetDirAnnotation]) :+ TargetDirAnnotation(dir.toString))
    retain(scoped.circuit,dir,"high")
    heteronpu.continuous.model.MatrixFifoTrace.mark(s"FIFO_PHASE $name.low.begin")
    val low=Compiler.toLowFirrtl(scoped);retain(low.circuit,dir,"low");heteronpu.continuous.model.MatrixFifoTrace.mark(s"FIFO_PHASE $name.low.end")
    val clocks=TopmoduleInfo(low.circuit).clocks;require(clocks==Seq("clock"))
    val a=ClockInfoAnnotation(Seq(ClockInfo("clock")))+:(FirrtlCircuitAnnotation(low.circuit)+:low.annotations)
    val p=(new PrepareAst).transform(SetImplicitOutputInfo.transform(GetFirrtlAst.transform(a)))
    val states=p.collect{case TreadleCircuitStateAnnotation(x)=>x};require(states.size==1)
    require(p.collect{case TargetDirAnnotation(d)=>d}==Seq(dir.toString),"one representation-owned output directory")
    retain(states.head.circuit,dir,"prepared")
    preparedGate(states.head.circuit,memory)
    heteronpu.continuous.model.MatrixFifoTrace.mark(s"FIFO_PHASE $name.prepared_gate.end")
    (states.head,p)
  }
  def both[M<:RawModule](gen:()=>M):((CircuitState,AnnotationSeq),(CircuitState,AnnotationSeq))={
    heteronpu.continuous.model.MatrixFifoTrace.mark("FIFO_PHASE elaborate.begin")
    val (h,_)=Compiler.elaborate(gen,Seq(TargetDirAnnotation("fifo-differential")),Seq.empty)
    annotationGate(h.annotations);heteronpu.continuous.model.MatrixFifoTrace.mark("FIFO_PHASE elaborate.end")
    val changed=MatrixResultFifoMemoryLowering(h.circuit)
    postHigh(h.circuit,changed);heteronpu.continuous.model.MatrixFifoTrace.mark("FIFO_PHASE exact_high_transform_gate.end")
    val original=prepare(h,false);val memory=prepare(h.copy(circuit=changed),true)
    require(fifo(original._1.circuit).ports==fifo(memory._1.circuit).ports,"strict final FIFO ABI equal")
    (original,memory)
  }
}
