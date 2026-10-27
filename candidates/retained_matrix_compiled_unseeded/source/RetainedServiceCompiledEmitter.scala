// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import chisel3.RawModule
import firrtl2.{AnnotationSeq, CircuitState, SystemVerilogEmitter}
import firrtl2.ir._
import firrtl2.annotations.UnrecognizedAnnotation
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.{RetainedBackendCircuitGate, RetainedServicePhaseObserver, MatrixResultFifoMemoryLowering}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths, StandardOpenOption}

/** Simulation-only compiled model emitter. One same original8x512 unseeded
  * Chisel service elaboration, exact qualified FIFO representation lowering,
  * official firrtl2 SV emitter. Endpoints bind to the separately qualified live
  * C++ model, NOT the original retained-provider RTL. Thus this is a Chisel
  * functional-model test backend and never final provider-RTL acceptance.
  * No Treadle-only phases are injected into the compiled simulator route.
  */
object RetainedServiceCompiledEmitter {
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
  private def initializationGate(a:AnnotationSeq):Unit={
    val forbidden=Set("RandomizeAtStartupAnnotation","RandomSeedAnnotation","CallResetAtStartupAnnotation",
      "ValidIfIsRandomAnnotation","LoadMemoryAnnotation","MemoryRandomInitAnnotation","MemoryScalarInitAnnotation",
      "MemoryArrayInitAnnotation","MemoryFileInlineAnnotation","PresetAnnotation","PresetRegAnnotation")
    require(a.forall(x=> !forbidden(x.getClass.getSimpleName.stripSuffix("$"))),"fixed default initialization only")
  }
  private def memoryGate(c:firrtl2.ir.Circuit):Unit={
    val ss=all(fifo(c).body);val memories=ss.collect{case x:firrtl2.ir.DefMemory=>x}
    val expected=(0 until 16).map(i=>s"sim_storage_row_$i"->8192).toMap+("sim_storage_metadata"->37)
    require(memories.size==17 && memories.map(_.name).distinct.size==17,"one original FIFO, exactly17 memories")
    require(memories.map(x=>x.name->x.dataType).toMap==expected.map{case(n,w)=>n->firrtl2.ir.UIntType(firrtl2.ir.IntWidth(w))})
    require(memories.forall(x=>x.depth==2 && x.readLatency==0 && x.writeLatency==1 &&
      x.readers==Seq("r") && x.writers==Seq("w") && x.readwriters.isEmpty && x.readUnderWrite==firrtl2.ir.ReadUnderWrite.Undefined))
    require(!ss.exists{case x:firrtl2.ir.DefRegister=>x.name=="storage"||x.name.startsWith("storage_");case _=>false},"no duplicated old register storage")
  }

  /** Official VerilogPrep replaces every low DefInstance with this terminal
    * connector statement. Inspect its complete port/wire relation and make a
    * read-only hierarchy projection for the unchanged original ABI/path gate.
    * The projected circuit is NEVER returned to the emitter or serialized as
    * the actual final AST. Any separately declared width adaptation is applied
    * before this read-only hierarchy gate; projection itself never mutates it.
    */
  private def finalBindings(c: Circuit): Map[String, String] = {
    require(c.modules.map(_.name).distinct.size==c.modules.size,"unique final modules")
    val definitions=c.modules.map(m=>m.name->m).toMap
    var connectors=0
    val projected=c.modules.map {
      case m:Module =>
        val instanceNames=all(m.body).collect{case i:firrtl2.WDefInstanceConnector=>i.name}
        require(instanceNames.distinct.size==instanceNames.size,"unique final connector names including internal-only modules")
        val declarations=all(m.body).collect{case w:DefWire=>w}
        require(declarations.map(_.name).distinct.size==declarations.size,"unique final wire declarations")
        val wires=declarations.map(w=>w.name->w.tpe).toMap
        def inspect(s:Statement):Statement=s match {
          case i:firrtl2.WDefInstanceConnector =>
            connectors+=1
            val target=definitions.getOrElse(i.module,throw new IllegalArgumentException("unresolved final connector "+i.module))
            require(target.isInstanceOf[Module] || target.isInstanceOf[ExtModule],"explicit final module representation")
            require(target.ports.map(_.name).distinct.size==target.ports.size,"unique final target ports")
            require(i.tpe==firrtl2.Utils.module_type(target),"complete final instance type/direction bundle")
            val expected=target.ports.map(p=>(i.name+"."+p.name)->p).toMap
            require(i.portCons.size==expected.size && i.portCons.map(_._1.serialize).distinct.size==expected.size,
              "complete unique final connector port set")
            require(i.portCons.map(_._1.serialize).toSet==expected.keySet,"exact complete final connector ports")
            i.portCons.foreach{case(port,wire)=>
              val p=expected(port.serialize)
              require(port.tpe==p.tpe && wire.tpe==p.tpe,"exact final connector port/wire type")
              port match {
                case f:SubField =>
                  require(f.name==p.name,"actual connector field name")
                  f.expr match {
                    case r:Reference => require(r.name==i.name && r.tpe==i.tpe,"actual connector instance reference")
                    case _ => throw new IllegalArgumentException("unknown connector port root")
                  }
                case _ => throw new IllegalArgumentException("unknown connector port expression")
              }
              val flow=if(p.direction==Input) firrtl2.SinkFlow else firrtl2.SourceFlow
              require(firrtl2.Utils.flow(port)==flow,"actual connector port direction/flow")
              val name=wire match {
                case r:Reference =>
                  require(r.kind==firrtl2.WireKind && r.flow==firrtl2.UnknownFlow,"exact official VerilogPrep WRef(DefWire) kind/flow")
                  r.name
                case _=>throw new IllegalArgumentException("non-wire final connector")
              }
              require(name==i.name+"_"+p.name && wires.get(name).contains(p.tpe),"original VerilogPrep declared wire binding")
            }
            DefInstance(i.info,i.name,i.module,i.tpe)
          case _:DefInstance => throw new IllegalArgumentException("unconverted final DefInstance")
          case b:Block => b.mapStmt(inspect)
          case _:DefWire | _:DefRegister | _:DefNode | _:DefMemory | _:Connect |
               _:IsInvalid | _:Stop | _:Print | _:Verification | _:Attach | EmptyStmt => s
          case other => throw new IllegalArgumentException("unknown terminal statement "+other.getClass.getName)
        }
        m.copy(body=inspect(m.body))
      case e:ExtModule => e
      case _ => throw new IllegalArgumentException("unsupported described final module")
    }
    require(connectors>0,"actual terminal instance connectors observed")
    RetainedBackendCircuitGate.verify(c.copy(modules=projected),seed=false)
  }

  /** Only the 4123 unsigned width-extension sites observed in the frozen
    * official terminal AST are eligible. No generic/legalize-anything pass,
    * signed conversion, truncation, arithmetic reassociation, or RTL text edit.
    * The official renderer will render these explicit typed zero extensions.
    */
  private def explicitObservedWidths(c:Circuit):(Circuit,String)={
    val digest=java.security.MessageDigest.getInstance("SHA-256")
      .digest(c.serialize.getBytes(StandardCharsets.UTF_8)).map(x=>f"${x & 255}%02x").mkString
    require(digest=="b5dd87dbf26e2c04504056cbf21aa2989ec01c77732c7bcb90bcef5ede72426a",
      "exact previously observed official terminal AST before finite width adaptation")
    val top="MatrixPipelineService"
    val targets=scala.collection.mutable.Map.empty[(String,String),Seq[String]]
    for(r<-0 until 16;c<-0 until 256)
      targets((top,s"values_io_enq_bits_value_${r}_${c}"))=Seq("mux:1:32:0")
    targets(("MatrixResultFifo","io_deq_valid"))=Seq("neq:1:2:0")
    for(n<-Seq("enq_ptr_value","deq_ptr_value"))targets(("Queue8_Meta",n))=Seq("mux:1:3:0")
    for(i<-0 until 8)targets((top,s"_completionBad_T_${7+9*i}"))=Seq("neq:1:8:0","neq:2:3:2")
    targets((top,"_T_15"))=Seq("neq:6:8:20")
    targets((top,"_T_16"))=Seq("eq:6:8:20","eq:6:8:21","eq:6:8:23","eq:6:8:24")
    for(n<-Seq("_GEN_7","_GEN_8"))targets((top,n))=Seq("mux:1:5:0")
    targets((top,"_steps_T_23"))=Seq("addw:4:64:bits(_steps_T_20, 3, 0)")
    require(targets.size==4112 && targets.values.map(_.size).sum==4123,"finite observed target set")
    val seen=scala.collection.mutable.Set.empty[(String,String)]
    val replacements=new java.util.IdentityHashMap[Expression,Expression]()
    val rows=scala.collection.mutable.ArrayBuffer.empty[String]
    def width(e:Expression):BigInt=e.tpe match {
      case UIntType(IntWidth(w)) if w>0=>w
      case _=>throw new IllegalArgumentException("observed adaptation requires positive-width unsigned operands")
    }
    val modules=c.modules.map {
      case m:Module=>
        def visit(s:Statement):Statement={
          val name=s match {
            case n:DefNode=>n.name
            case Connect(_,r:Reference,_)=>r.name
            case _=>""
          }
          val key=(m.name,name)
          targets.get(key) match {
            case None=>s.mapStmt(visit)
            case Some(expected)=>
              require(!seen(key),"one observed statement per exact target");seen+=key
              val changes=scala.collection.mutable.ArrayBuffer.empty[String]
              def extend(e:Expression,to:BigInt,kind:String):Expression={
                val from=width(e)
                if(from==to)e else {
                  require(to>from,"only extension: no truncation or signed conversion")
                  val (value,result)=e match {
                    case UIntLiteral(v,IntWidth(w))=>
                      require(w==from && v>=0 && BigInt(v.bitLength)<=from,"preserve unsigned literal value")
                      (v.toString(16),UIntLiteral(v,IntWidth(to)):Expression)
                    case p:DoPrim if key==(top,"_steps_T_23") && kind=="addw" && from==4 && to==64 &&
                      p.op==firrtl2.PrimOps.Bits && p.serialize=="bits(_steps_T_20, 3, 0)"=>
                      (p.serialize,DoPrim(firrtl2.PrimOps.Pad,Seq(p),Seq(to),UIntType(IntWidth(to))):Expression)
                    case _=>throw new IllegalArgumentException("unobserved nonliteral width extension")
                  }
                  val signature=s"$kind:$from:$to:$value"
                  require(expected.contains(signature),"only observed width-extension kind/value")
                  changes+=signature;rows+=s"${m.name}\t$name\t$kind\t$from\t$to\t$value"
                  replacements.put(result,e);result
                }
              }
              def fix(e:Expression):Expression=e.mapExpr(fix) match {
                case x:Mux=>
                  require(width(x.cond)==1,"unchanged scalar mux predicate")
                  x.copy(tval=extend(x.tval,width(x),"mux"),fval=extend(x.fval,width(x),"mux"))
                case x:DoPrim if x.op==firrtl2.PrimOps.Eq || x.op==firrtl2.PrimOps.Neq=>
                  require(x.args.size==2,"binary comparison")
                  val n=x.args.map(width).max;val kind=if(x.op==firrtl2.PrimOps.Eq)"eq" else "neq"
                  x.copy(args=x.args.map(a=>extend(a,n,kind)))
                case x:DoPrim if x.op==firrtl2.Addw=>
                  require(key==(top,"_steps_T_23") && width(x)==64 && x.args.size==2 && x.args.map(width)==Seq(BigInt(64),BigInt(4)),
                    "only observed unsigned64 plus unsigned4, same64-bit modular sum")
                  x.copy(args=x.args.map(a=>extend(a,BigInt(64),"addw")))
                case x=>x
              }
              val changed=s.mapExpr(fix)
              require(changes.sorted==expected.sorted,"exact observed per-statement extension multiset")
              changed
          }
        }
        m.copy(body=visit(m.body))
      case other=>other
    }
    val result=c.copy(modules=modules)
    require(seen.toSet==targets.keySet.toSet && rows.size==4123,"all and only observed extension sites")
    def undoExpr(e:Expression):Expression={
      val old=replacements.get(e)
      if(old!=null)undoExpr(old) else e.mapExpr(undoExpr)
    }
    def undoStmt(s:Statement):Statement=s.mapStmt(undoStmt).mapExpr(undoExpr)
    val restored=result.copy(modules=result.modules.map{case m:Module=>m.copy(body=undoStmt(m.body));case x=>x})
    require(restored==c,"whole AST inverse: no changed declarations/connectors/control/order outside exact extensions")
    (result,rows.mkString("module\ttarget\tkind\tfrom_bits\tto_bits\tvalue_or_original_expression\n","\n","\n"))
  }

  private def checkAnnotations(state: CircuitState): Unit = {
    require(!state.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),
      "unsupported official Chisel-to-firrtl2 annotation")
    require(!state.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),
      "CircuitState annotations must not carry a second circuit")
  }
  private def retain(name: String, text: String): Unit = {
    val directory = Paths.get("compiled-service")
    Files.createDirectories(directory)
    Files.write(directory.resolve(name), text.getBytes(StandardCharsets.UTF_8),
      StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
  }
  def emit[M <: RawModule](gen: () => M): Unit = {
    val (high, _) = RetainedServicePhaseObserver.measured("elaborate"){ Compiler.elaborate(gen, Seq(TargetDirAnnotation("compiled-service")), Seq.empty) }
    checkAnnotations(high)
    RetainedServicePhaseObserver.measured("high.serialize"){ retain("official-bridge-high.fir", high.circuit.serialize) }
    val highBindings = RetainedServicePhaseObserver.measured("high.gate"){ RetainedBackendCircuitGate.verify(high.circuit, seed = false) }
    val selected = RetainedServicePhaseObserver.measured("fifo.transform"){
      annotationGate(high.annotations);initializationGate(high.annotations)
      val changed=MatrixResultFifoMemoryLowering(high.circuit)
      postHigh(high.circuit,changed);memoryGate(changed)
      require(RetainedBackendCircuitGate.verify(changed,seed=false)==highBindings,
        "all eight512 endpoints and clock gates unchanged by FIFO representation")
      retain("official-bridge-memory-high.fir",changed.serialize)
      high.copy(circuit=changed)
    }
    val low = RetainedServicePhaseObserver.measured("low.compiler"){ Compiler.toLowFirrtl(selected) }
    memoryGate(low.circuit)
    checkAnnotations(low)
    RetainedServicePhaseObserver.measured("low.serialize"){ retain("official-bridge-low.fir", low.circuit.serialize) }
    val lowBindings = RetainedServicePhaseObserver.measured("low.gate"){ RetainedBackendCircuitGate.verify(low.circuit, seed = false) }
    require(lowBindings == highBindings, "same-elaboration exact external instance paths and definitions")
    var finalCircuit: Option[Circuit] = None
    val emitter = new SystemVerilogEmitter {
      // Official emit() calls this immediately before rendering that result.
      // Capture/gate the actual emission AST, not an earlier low approximation.
      override protected def runTransforms(in: CircuitState): CircuitState = {
        val out = super.runTransforms(in)
        require(finalCircuit.isEmpty, "one emission transform invocation")
        // Preserve the real terminal AST even when a structural gate rejects it.
        retain("official-pre-width-adaptation-ast.fir",out.circuit.serialize)
        val (adapted,widthRows)=explicitObservedWidths(out.circuit)
        retain("official-emission-ast.fir",adapted.serialize)
        retain("official-emission-width-adaptations.tsv",widthRows)
        val inventory=out.circuit.modules.flatMap {
          case m:Module => all(m.body).collect {
            case i:firrtl2.WDefInstanceConnector => s"${m.name}\tconnector\t${i.name}\t${i.module}\t${i.portCons.size}"
            case i:DefInstance => s"${m.name}\tunconverted-instance\t${i.name}\t${i.module}\t-1"
          }
          case e:ExtModule => Seq(s"${e.name}\textmodule\t-\t${e.defname}\t${e.ports.size}")
          case other => Seq(s"${other.name}\tunsupported-module\t-\t-\t-1")
        }
        retain("official-emission-instances.tsv",inventory.mkString("parent\tkind\tinstance\tmodule\tports\n","\n","\n"))
        require(finalBindings(adapted)==lowBindings,
          "exact eight full512 endpoints/eight original ICG in emission AST")
        memoryGate(adapted)
        checkAnnotations(out);initializationGate(out.annotations)
        finalCircuit=Some(adapted)
        out.copy(circuit=adapted)
      }
    }
    val writer = new java.io.StringWriter
    RetainedServicePhaseObserver.measured("sv.emitter"){ emitter.emit(low,writer) }
    require(finalCircuit.nonEmpty,"official emission AST observed and checked")
    val emitted=finalCircuit.get
    val top=emitted.modules.collect{case m:Module if m.name==emitted.main=>m}
    require(top.size==1 && emitted.main=="MatrixPipelineService","fixed original top")
    val ports=top.head.ports
    require(ports.map(_.name).distinct.size==ports.size,"unique actual top ports")
    def width(p:Port):Int=p.tpe match {
      case ClockType=>1
      case UIntType(IntWidth(w)) if w>0 && w<=64=>w.toInt
      case _=>throw new IllegalArgumentException("unsupported actual C++ test port "+p.serialize)
    }
    require(ports.forall(_.name.matches("[a-zA-Z_][a-zA-Z0-9_]*")),"safe actual identifier")
    val bindings=ports.map{p=>s"  addPort(ports, \"${p.name}\", d.${p.name}, ${width(p)}, ${p.direction==Input});"}
    retain("actual_port_bindings.hpp","// Generated from the exact final emission AST; not a guessed port map.\n"+
      "#pragma once\ninline void bindPorts(VMatrixPipelineService& d, PortMap& ports) {\n"+bindings.mkString("\n")+"\n}\n")
    retain("actual_top_ports.tsv",ports.map(p=>s"${p.name}\t${p.direction}\t${width(p)}").mkString("","\n","\n"))
    retain("MatrixPipelineService.sv",writer.toString)
    retain("EMITTER_SCOPE.txt","FUNCTIONAL_MODEL_BACKEND_ONLY; original unseeded8x512 service; not final retained-provider RTL\n")
  }
  def main(args:Array[String]):Unit={
    require(args.isEmpty,"fixed original unseeded service only; no profile or geometry override")
    emit(() => new heteronpu.continuous.MatrixPipelineService(returnTagBits=32,
      enableTransposedDense=true,enableAccumulatorSeed=false,enablePackedDrainStatus=true))
  }
}
