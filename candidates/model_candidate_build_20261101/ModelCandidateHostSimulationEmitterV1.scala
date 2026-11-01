// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import chisel3.RawModule
import firrtl2.{AnnotationSeq, CircuitState, SystemVerilogEmitter}
import firrtl2.ir._
import firrtl2.annotations.UnrecognizedAnnotation
import firrtl2.options.TargetDirAnnotation
import firrtl2.stage.FirrtlCircuitAnnotation
import heteronpu.continuous.model.{RetainedBackendCircuitGate, RetainedServicePhaseObserver, PortableHostMatrixResultFifoMemoryLowering, CandidateDenseAccMemoryLoweringV2}
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths, StandardOpenOption}
import java.security.MessageDigest

/** UNREVIEWED model-candidate backend emission from same-run observed high.
  * Same-run descriptor hashes are integrity evidence, NOT approval. Source-reviewed
  * preconditions only permit generation; independent post-build review is required
  * before any numeric execution. Old production emitter/gates remain unchanged.
  * NOT the final post-model-pass frozen RTL acceptance. No second hardware elaboration.
  * Raw official SV only: no inherited service-only width/unsigned adaptation.
  * Matrix must bind original physical4096 provider; DMA must bind original pinned provider RTL.
  * Only FIFO and one private denseAcc storage representation change; all control/arithmetic remain original Chisel.
  * No new top Module, no partial512 service, no input/reference injection.
  */
object ModelCandidateHostSimulationEmitterV1 {
  private def all(s:Statement):Seq[Statement]=s+: {val b=Vector.newBuilder[Statement];s.foreachStmt(x=>b++=all(x));b.result()}
  private def fifo(c:Circuit):Module={val x=c.modules.collect{case m:Module if m.name=="MatrixResultFifo"=>m};require(x.size==1);x.head}
  private def annotationGate(a:AnnotationSeq):Unit={
    // Unlike the service-only circuit, the actual original Host has retained
    // DontTouch targets in the source-reviewed Top/core module set. Preserve every original
    // annotation object; none may point into the representation-replaced FIFO or denseAcc register.
    require(a.nonEmpty && a.size<=100000 && a.count(_.isInstanceOf[firrtl2.transforms.DontTouchAnnotation])==a.size-1,"bounded actual DontTouch plus one TargetDir; no other classes")
    a.foreach {
      case d:firrtl2.transforms.DontTouchAnnotation=>
        require(d.target.circuit=="HostBlockTopV4" && d.target.path.isEmpty && Set("HostBlockTopV4","Qwen2ContinuousBlock","SiluVectorUnit","VectorSiluOwner")(d.target.module),"only actual unaffected original Host/core targets")
        require(d.target.module!="Qwen2ContinuousBlock" || d.target.ref!="denseAcc","no annotation targets replaced private denseAcc")
      case _:TargetDirAnnotation=>()
      case other=>throw new IllegalArgumentException("unreviewed Host annotation "+other.getClass.getName)
    }
    require(a.count(_.isInstanceOf[TargetDirAnnotation])==1,"one output directory annotation")
  }
  private def postHigh(original:Circuit,changed:Circuit,expectedCanonical:String):Unit={
    val a=fifo(original);val b=fifo(changed)
    require(a.ports==b.ports,"all FIFO ports unchanged")
    val users=original.modules.collect{case m:Module=>all(m.body).count{case i:DefInstance=>i.module=="MatrixResultFifo";case _=>false}}.sum
    require(users==1,"exact one full-capacity FIFO instance")
    require(changed==PortableHostMatrixResultFifoMemoryLowering(original,expectedCanonical),"exact generated substitution, including every connection")
    val stmts=all(b.body);val mems=stmts.collect{case d:DefMemory=>d}
    require(mems.size==17 && mems.map(_.name).distinct.size==17,"exact17 memories")
    val expected=(0 until 16).map(i=>s"sim_storage_row_$i"->8192).toMap+("sim_storage_metadata"->5)
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
    CandidateDenseAccMemoryLoweringV2.check(c)
    val ss=all(fifo(c).body);val memories=ss.collect{case x:firrtl2.ir.DefMemory=>x}
    val expected=(0 until 16).map(i=>s"sim_storage_row_$i"->8192).toMap+("sim_storage_metadata"->5)
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
    * the actual final AST. No arithmetic/width adaptation is performed in this raw Host stage;
    * projection itself never mutates the emitted circuit.
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
    hostBindings(c.copy(modules=projected),high=false)
  }

  private def bitWidth(t:Type):BigInt=t match {
    case UIntType(IntWidth(w))=>w
    case SIntType(IntWidth(w))=>w
    case ClockType|ResetType|AsyncResetType=>BigInt(1)
    case BundleType(fields)=>fields.map(f=>bitWidth(f.tpe)).sum
    case VectorType(t,n)=>bitWidth(t)*n
    case _=>throw new IllegalArgumentException("unresolved actual width "+t.serialize)
  }
  private def field(t:Type,name:String):Type=t match {
    case BundleType(fs)=>fs.find(_.name==name).getOrElse(throw new IllegalArgumentException("actual field "+name)).tpe
    case _=>throw new IllegalArgumentException("actual bundle required")
  }
  private def hostBindings(c:Circuit,high:Boolean):Map[String,String]={
    require(c.main=="HostBlockTopV4" && c.modules.map(_.name).distinct.size==c.modules.size,"same original unique Host top")
    val modules=c.modules.map(m=>m.name->m).toMap
    val rows=scala.collection.mutable.ArrayBuffer.empty[(String,String,String)]
    val bindings=scala.collection.mutable.Map.empty[String,String]
    val dmaInputs=Map("clk_i"->1,"rst_ni"->1,"req_valid_i"->1,"src_addr_i"->64,"dst_addr_i"->64,"length_i"->32,"rsp_ready_i"->1,"axi_read_rsp_i"->532,"axi_write_rsp_i"->532)
    val dmaOutputs=Map("req_ready_o"->1,"rsp_valid_o"->1,"rsp_error_o"->1,"axi_read_req_o"->785,"axi_write_req_o"->785,"busy_o"->8)
    val dmaPorts=dmaInputs.map{case(n,w)=>n->((Input:Direction),if(n=="clk_i")ClockType else UIntType(IntWidth(w)))} ++ dmaOutputs.map{case(n,w)=>n->((Output:Direction),UIntType(IntWidth(w)):Type)}
    def visit(name:String,path:String,ancestors:Set[String]):Unit={
      require(!ancestors(name)&&ancestors.size<128&&rows.size<100000,"bounded real hierarchy")
      val m=modules.getOrElse(name,throw new IllegalArgumentException("missing actual module "+name))
      rows+=((path,name,m match {case e:ExtModule=>e.defname;case _=>""}))
      m match {
        case e:ExtModule=>
          val expected= e.defname match {
            case "qwen2_matrix_command_endpoint"=>RetainedBackendCircuitGate.expected(seed=true,endpoint=true)
            case "tc_clk_gating"=>RetainedBackendCircuitGate.expected(seed=true,endpoint=false)
            case "idma_backend_rw_axi_flat_wrap"=>dmaPorts
            case _=>throw new IllegalArgumentException("unknown real Host external provider "+e.defname)
          }
          require(e.ports.map(_.name).distinct.size==e.ports.size && e.ports.map(p=>p.name->((p.direction:Direction),p.tpe)).toMap==expected,"complete Host provider ABI "+e.name)
          require(e.params==(if(e.defname=="qwen2_matrix_command_endpoint")Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1)))else Seq.empty),"exact provider params")
          require(path.nonEmpty && !bindings.contains(path),"unique real external path");bindings(path)=e.defname
        case r:Module=>
          val instances=all(r.body).collect{case i:DefInstance=>i}
          require(instances.map(_.name).distinct.size==instances.size,"unique real instance names")
          instances.foreach(i=>visit(i.module,if(path.isEmpty)i.name else path+"."+i.name,ancestors+name))
        case _=>throw new IllegalArgumentException("unsupported actual module")
      }
    }
    visit(c.main,"",Set.empty)
    require(bindings.size==17 && bindings.values.count(_=="qwen2_matrix_command_endpoint")==8 && bindings.values.count(_=="tc_clk_gating")==8 && bindings.values.count(_=="idma_backend_rw_axi_flat_wrap")==1,"full4096 and eightICG plus ONE real iDMA")
    require(rows.count(_._2.startsWith("MatrixPipelineService"))==1 && rows.count(_._2.startsWith("QwenOwnerKernel"))==1,"one real service and Kernel")
    val banks=rows.filter(_._2.startsWith("UnifiedVectorElement32BankV4"))
    require(banks.size==1 && rows.count(r=>r._1.startsWith(banks.head._1+".")&&r._2.startsWith("HeteroFP32Alu"))==32,"one original fixed32 ALU bank")
    require(rows.count(_._2.startsWith("HeteroStreamingTopK"))==1,"one original TopK512")
    if(high){val top=modules(c.main).asInstanceOf[Module];val io=top.ports.find(_.name=="io").getOrElse(throw new IllegalArgumentException("Host io"));require(bitWidth(field(field(io.tpe,"launch"),"bits"))==844,"same full launch844")}
    if(high){
      ModelCandidateDiagnosticV1.phase("BANK_SUBTREE_HASH")
      val oldRows=preconditions("bank_subtree_reference_modules").arr
      require(oldRows.map(_("name").str).distinct.size==oldRows.size,"unique original canonical reference modules")
      val oldMap=oldRows.map(r=>r("name").str->r("sha256").str).toMap
      val actualBankNames=rows.filter(r=>r._1==banks.head._1 || r._1.startsWith(banks.head._1+".")).map(_._2).distinct
      require(actualBankNames.nonEmpty)
      actualBankNames.zipWithIndex.foreach{case(n,index)=>
        val actual=CanonicalHighGate.moduleSemanticSha(modules(n))
        if(!oldMap.get(n).contains(actual)){ModelCandidateDiagnosticV1.number("bank_subtree_module_index",index);ModelCandidateDiagnosticV1.hash("failing_module_sha256",actual)}
        require(oldMap.get(n).contains(actual),"original entire bank subtree canonical definition drift; no suffix rename bypass")
      }
    }
    if(high && observedHierarchy==ujson.Null){
      ModelCandidateDiagnosticV1.number("reachable_instance_count",rows.size)
      observedHierarchy=ujson.Obj("reachable_instance_count"->rows.size,
        "providers"->ujson.Arr.from(rows.filter(_._3.nonEmpty).map{case(path,module,defname)=>ujson.Obj("path"->path,"module"->module,"defname"->defname)}),
        "shared_vector_bank_path"->banks.head._1,"shared_vector_bank_instances"->banks.size,
        "bank_alu_instances"->rows.count(r=>r._1.startsWith(banks.head._1+".")&&r._2.startsWith("HeteroFP32Alu")),
        "all_reachable_alu_instances"->rows.count(_._2.startsWith("HeteroFP32Alu")),
        "bank_subtree_modules"->ujson.Arr.from(rows.filter(r=>r._1==banks.head._1 || r._1.startsWith(banks.head._1+".")).map(_._2).distinct.map(n=>ujson.Obj("name"->n,"sha256"->CanonicalHighGate.moduleSemanticSha(modules(n))))),
        "instances"->ujson.Arr.from(rows.map{case(path,module,defname)=>ujson.Obj("path"->path,"module"->module,"defname"->defname)}))
    }
    bindings.toMap
  }
  private def checkAnnotations(state:CircuitState):Unit={
    require(!state.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported official Chisel annotation")
    require(!state.annotations.exists(_.isInstanceOf[FirrtlCircuitAnnotation]),"no second circuit annotation")
  }
  private var originalHighPath=""
  private var observedRows=Map.empty[String,String]
  // Observed SAME-RUN identity only: none of these values is an acceptance pin.
  private var preconditions:ujson.Value=ujson.Null
  private var observedHierarchy:ujson.Value=ujson.Null
  private val PreconditionsSha="80c1426efa4a8f2740dadc1757a35d01913233e86c5fc5c2a35f9d3a8d044f0e"
  private var observedModules=Map.empty[String,String]
  private var observedModuleOrder=Seq.empty[String]
  private def sha(bytes:Array[Byte]):String=MessageDigest.getInstance("SHA-256").digest(bytes).map(b=>f"${b&255}%02x").mkString
  private def checkOriginalHigh(c:Circuit):Unit={
    require(CanonicalHighGate.circuitSemanticSha(c)==observedRows("circuit"),"whole high non-metadata drift")
    require(c.modules.nonEmpty && c.modules.size<=4096 && c.modules.size==observedModules.size && c.modules.map(_.name).distinct.size==c.modules.size,"complete observed modules")
    require(c.modules.map(_.name)==observedModuleOrder,"complete observed module order, never sort")
    require(c.modules.forall(m=>CanonicalHighGate.moduleSemanticSha(m)==observedModules(m.name)),"all module canonical pins")
    val raw=c.serialize.getBytes(StandardCharsets.UTF_8)
    retain("original-high-reference.json",s"""{"qualification":"MODEL_CANDIDATE_OBSERVED_IDENTITY_NOT_ACCEPTANCE","actual_bytes":${raw.length},"actual_sha256":"${sha(raw)}","canonical_sha256":"${observedRows("circuit")}"}\n""")
  }
  private def verifyCanonicalLow(c:Circuit):Unit={
    val bytes=c.serialize.getBytes(StandardCharsets.UTF_8);val expected=sha(bytes)
    val path=Paths.get("compiled-host","HostBlockTopV4.lo.fir")
    require(Files.isRegularFile(path) && !Files.isSymbolicLink(path),"canonical official low retained")
    val size=Files.size(path);val md=MessageDigest.getInstance("SHA-256");val in=Files.newInputStream(path)
    val buffer=new Array[Byte](65536)
    try {var n=in.read(buffer);while(n!= -1){md.update(buffer,0,n);n=in.read(buffer)}} finally in.close()
    val actual=md.digest().map(b=>f"${b&255}%02x").mkString
    val matches=size==bytes.length && actual==expected
    if(!matches)retain("unexpected-low-serialization.fir",new String(bytes,StandardCharsets.UTF_8))
    require(matches,"canonical official low equals actual Circuit.serialize bytes; no trim or dropped distinct evidence")
    retain("canonical-low-identity.json",s"""{"path":"HostBlockTopV4.lo.fir","bytes":$size,"sha256":"$actual","actual_serialization_sha256":"$expected","equal":true}\n""")
  }
  private def retain(name:String,text:String):Unit={
    val directory=Paths.get("compiled-host");Files.createDirectories(directory)
    Files.write(directory.resolve(name),text.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
  }
  def main(args:Array[String]):Unit=ModelCandidateDiagnosticV1.run("emit_host"){
    ModelCandidateDiagnosticV1.phase("INPUT_BOUNDS_OR_PIN")
    require(args.length==6,"fresh high, annotations, observed same-run canonical, observedSHA, fixed preconditions, fixedSHA; no profile switch")
    val contractBytes=ModelCandidateHighDescriptorV1.read(args(4),1L<<20)
    require(args(5)==PreconditionsSha && sha(contractBytes)==PreconditionsSha,"source-reviewed precondition bytes, not dynamically learned")
    preconditions=ujson.read(new String(contractBytes,StandardCharsets.UTF_8))
    require(preconditions("schema").str=="MODEL_CANDIDATE_GENERATION_PRECONDITIONS_V1")
    require(preconditions("scope").str=="SOURCE_REVIEWED_PRECONDITIONS_NOT_POST_BUILD_STRUCTURAL_ACCEPTANCE")
    ModelCandidateDiagnosticV1.phase("CANONICAL_IDENTITY")
    originalHighPath=args(0)
    val observedBytes=ModelCandidateHighDescriptorV1.read(args(2),512L<<10)
    require(args(3).matches("[0-9a-f]{64}") && sha(observedBytes)==args(3),"same-run observed descriptor integrity; not approval")
    val rows=new String(observedBytes,StandardCharsets.UTF_8).split("\n").toSeq
    require(rows.head==ModelCandidateHighDescriptorV1.Header)
    val fields=rows.tail.map(_.split("\t").toSeq)
    require(fields.forall(r=>r.size==2 || (r.size==3 && r.head=="module")))
    require(fields.filter(_.size==2).map(_.head).distinct.size==3 && fields.filter(_.size==2).size==3,"unique descriptor header rows")
    require(fields.filter(_.size==3).map(_(1)).distinct.size==fields.count(_.size==3),"unique ordered module rows")
    require(fields.filter(_.size==3).forall(r=>r(2).matches("[0-9a-f]{64}")),"module digests")
    observedRows=fields.filter(_.size==2).map(r=>r.head->r(1)).toMap
    observedModules=fields.filter(_.size==3).map(r=>r(1)->r(2)).toMap
    observedModuleOrder=fields.filter(_.size==3).map(_(1))
    require(observedRows.keySet==Set("main","circuit","annotations_order_preserved") && observedRows("main")=="HostBlockTopV4" && observedModules.nonEmpty && observedModules.size<=4096)
    require(!Files.exists(Paths.get("compiled-host")),"fresh output")
    val raw=ModelCandidateHighDescriptorV1.read(originalHighPath,384L<<20)
    require(raw.nonEmpty,"fresh observed high required; not accepted baseline")
    ModelCandidateDiagnosticV1.number("high_bytes",raw.length);ModelCandidateDiagnosticV1.hash("high_sha256",sha(raw))
    ModelCandidateDiagnosticV1.phase("HIGH_ROUNDTRIP")
    val circuit=firrtl2.Parser.parse(new String(raw,StandardCharsets.UTF_8))
    require(java.util.Arrays.equals(circuit.serialize.getBytes(StandardCharsets.UTF_8),raw),"official parser exact full high roundtrip including info")
    val annotationPath=Paths.get(args(1))
    val annotationBytes=ModelCandidateHighDescriptorV1.read(args(1),16L<<20)
    require(CanonicalHighGate.annotationSemanticSha(new String(annotationBytes,StandardCharsets.UTF_8))==observedRows("annotations_order_preserved"),"all annotation structure/order except TargetDir must match")
    ModelCandidateDiagnosticV1.number("module_count",circuit.modules.size);ModelCandidateDiagnosticV1.number("annotation_bytes",annotationBytes.length);ModelCandidateDiagnosticV1.hash("annotations_sha256",sha(annotationBytes))
    ModelCandidateDiagnosticV1.phase("ANNOTATION_ROUNDTRIP")
    val originalAnnotations=firrtl2.annotations.JsonProtocol.deserialize(new String(annotationBytes,StandardCharsets.UTF_8))
    require(java.util.Arrays.equals(firrtl2.annotations.JsonProtocol.serialize(originalAnnotations).getBytes(StandardCharsets.UTF_8),annotationBytes),"all annotations exact deserialization roundtrip")
    ModelCandidateDiagnosticV1.number("annotation_count",originalAnnotations.size);ModelCandidateDiagnosticV1.phase("ANNOTATION_CLASS_TARGET")
    annotationGate(originalAnnotations);initializationGate(originalAnnotations)
    require(originalAnnotations.collect{case t:TargetDirAnnotation=>t.directory}==Seq("host-diagnostic"),"one original TargetDir")
    val relocated=originalAnnotations.map {case _:TargetDirAnnotation=>TargetDirAnnotation("compiled-host");case other=>other}
    require(relocated.size==originalAnnotations.size && relocated.zip(originalAnnotations).forall{case(a,b)=>b.isInstanceOf[TargetDirAnnotation] || (a eq b)},"only explicit single TargetDir relocation; every other annotation object retained")
    retain("observed-original-annotations.json",new String(annotationBytes,StandardCharsets.UTF_8))
    val high=CircuitState(circuit,relocated)
    checkAnnotations(high)
    ModelCandidateDiagnosticV1.phase("CANONICAL_IDENTITY")
    checkOriginalHigh(high.circuit)
    val actualModules=high.circuit.modules.map(m=>m.name->CanonicalHighGate.moduleSemanticSha(m)).toMap
    ModelCandidateDiagnosticV1.phase("FIXED_MODULE_HASH")
    preconditions("unchanged_modules").arr.zipWithIndex.foreach{case(row,index)=>
      val observed=actualModules.get(row("name").str)
      if(!observed.contains(row("sha256").str)){ModelCandidateDiagnosticV1.number("fixed_module_index",index);observed.foreach(x=>ModelCandidateDiagnosticV1.hash("failing_module_sha256",x))}
      require(observed.contains(row("sha256").str),"fixed unchanged module contract drift")}
    retain("high-annotations.json",firrtl2.annotations.JsonProtocol.serialize(high.annotations))
    ModelCandidateDiagnosticV1.phase("FIXED_PROVIDER_BINDINGS")
    val highBindings=hostBindings(high.circuit,high=true)
    val selected=RetainedServicePhaseObserver.measured("host.fifo.transform"){
      annotationGate(high.annotations);initializationGate(high.annotations)
      ModelCandidateDiagnosticV1.phase("FIFO_LOCAL_SHAPE")
      val fifoChanged=PortableHostMatrixResultFifoMemoryLowering(high.circuit,observedModules("MatrixResultFifo"))
      postHigh(high.circuit,fifoChanged,observedModules("MatrixResultFifo"))
      ModelCandidateDiagnosticV1.phase("DENSE_ACC_LOCAL_SHAPE")
      val changed=CandidateDenseAccMemoryLoweringV2(fifoChanged,observedModules("Qwen2ContinuousBlock"))
      memoryGate(changed)
      require(hostBindings(changed,high=true)==highBindings,"same complete17 external bindings")
      retain("official-bridge-memory-high.fir",changed.serialize)
      high.copy(circuit=changed)
    }
    ModelCandidateDiagnosticV1.phase("LOW_LOWERING")
    val low=RetainedServicePhaseObserver.measured("host.low.compiler"){Compiler.toLowFirrtl(selected)}
    memoryGate(low.circuit);checkAnnotations(low)
    ModelCandidateDiagnosticV1.phase("LOW_SERIALIZATION")
    verifyCanonicalLow(low.circuit)
    retain("low-annotations.json",firrtl2.annotations.JsonProtocol.serialize(low.annotations))
    val lowBindings=hostBindings(low.circuit,high=false)
    require(lowBindings==highBindings,"same actual Host provider paths after official low")
    var finalCircuit:Option[Circuit]=None
    val emitter=new SystemVerilogEmitter {
      override protected def runTransforms(in:CircuitState):CircuitState={
        val out=super.runTransforms(in)
        require(finalCircuit.isEmpty,"one official terminal AST")
        retain("official-emission-ast.fir",out.circuit.serialize)
        val inventory=out.circuit.modules.flatMap {
          case m:Module=>all(m.body).collect{case i:firrtl2.WDefInstanceConnector=>s"${m.name}\tconnector\t${i.name}\t${i.module}\t${i.portCons.size}";case i:DefInstance=>s"${m.name}\tunconverted-instance\t${i.name}\t${i.module}\t-1"}
          case e:ExtModule=>Seq(s"${e.name}\textmodule\t-\t${e.defname}\t${e.ports.size}")
          case other=>Seq(s"${other.name}\tunsupported-module\t-\t-\t-1")
        }
        retain("official-emission-instances.tsv",inventory.mkString("parent\tkind\tinstance\tmodule\tports\n","\n","\n"))
        ModelCandidateDiagnosticV1.phase("FINAL_CONNECTORS")
        require(finalBindings(out.circuit)==lowBindings,"actual final8x512/8ICG/1iDMA exact connectors")
        memoryGate(out.circuit);checkAnnotations(out);initializationGate(out.annotations)
        finalCircuit=Some(out.circuit);out
      }
    }
    val writer=new java.io.StringWriter
    ModelCandidateDiagnosticV1.phase("SV_EMISSION")
    RetainedServicePhaseObserver.measured("host.sv.emitter"){emitter.emit(low,writer)}
    require(finalCircuit.nonEmpty,"real terminal circuit captured")
    val c=finalCircuit.get;val top=c.modules.collect{case m:Module if m.name==c.main=>m}
    require(top.size==1 && c.main=="HostBlockTopV4","same actual original root")
    ModelCandidateDiagnosticV1.phase("TOP_PORT_ABI")
    val ports=top.head.ports;require(ports.map(_.name).distinct.size==ports.size,"unique actual top ABI")
    val wide=Map("io_axi_r_bits_data"->Input,"io_axi_w_bits_data"->Output)
    def width(p:Port):Int=p.tpe match {
      case ClockType=>1
      case UIntType(IntWidth(w)) if w>0 && w<=64=>w.toInt
      case UIntType(IntWidth(w)) if w==512 && wide.get(p.name).contains(p.direction)=>512
      case _=>throw new IllegalArgumentException("unexpected actual Host top port "+p.serialize)
    }
    require(ports.count(p=>width(p)==512)==2 && ports.filter(_.name.startsWith("io_launch_bits_")).map(p=>width(p)).sum==844,"whole launch844 and both true512 AXI buses")
    val lowTop=low.circuit.modules.collect{case m:Module if m.name==low.circuit.main=>m}
    require(lowTop.size==1 && lowTop.head.ports.map(p=>(p.name,p.direction,p.tpe))==ports.map(p=>(p.name,p.direction,p.tpe)),"all ordered typed LOW ports equal actual terminal AST ports")
    ModelCandidateDiagnosticV1.number("low_port_count",ports.size)
    val expectedPorts=preconditions("ports").obj
    require(ports.size==122 && expectedPorts.size==122 && ports.map(_.name).toSet==expectedPorts.keySet.toSet,"exact original122 top port names")
    ports.foreach{p=>val expected=expectedPorts(p.name).arr;require(expected.size==2 && expected(0).str==p.direction.toString && expected(1).num==width(p).toDouble,"exact original top direction/width")}
    val typedPorts=ujson.Arr.from(ports.map(p=>ujson.Obj("name"->p.name,"direction"->p.direction.toString,"type"->p.tpe.serialize,"width"->width(p))))
    require(typedPorts==preconditions("typed_ports"),"full original typed122 ordered LOW ABI, including clock/reset types")
    retain("actual_top_ports.tsv",ports.map(p=>s"${p.name}\t${p.direction}\t${width(p)}").mkString("","\n","\n"))
    retain("HostBlockTopV4.sv",writer.toString)
    val lowBytes=low.circuit.serialize.getBytes(StandardCharsets.UTF_8)
    val svBytes=writer.toString.getBytes(StandardCharsets.UTF_8)
    ModelCandidateDiagnosticV1.phase("METADATA_BOUNDS")
    val structureObservation=ujson.Obj("schema"->"MODEL_CANDIDATE_STRUCTURE_OBSERVATION_V1",
      "scope"->"CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED",
      "sv"->ujson.Obj("bytes"->svBytes.length,"sha256"->sha(svBytes)),
      "preconditions_sha256"->PreconditionsSha,"fixed_module_checks"->preconditions("unchanged_modules"),
      "structure"->observedHierarchy,"numerical_pass"->false,"post_build_structure_accepted"->false)
    val portsObservation=ujson.Obj("schema"->"MODEL_CANDIDATE_LOW_PORTS_OBSERVATION_V1",
      "scope"->"CANDIDATE_GENERATION_PRECONDITIONS_ONLY_UNREVIEWED",
      "port_observation_stage"->"OFFICIAL_LOW_AND_TERMINAL_AST_EXACT_ORDERED_TYPES","ports"->typedPorts,
      "low"->ujson.Obj("bytes"->lowBytes.length,"sha256"->sha(lowBytes)),"abi_accepted_for_execution"->false)
    ModelCandidateHighDescriptorV1.write("model-structure.json",(ujson.write(structureObservation,indent=2)+"\n").getBytes(StandardCharsets.UTF_8),2<<20)
    ModelCandidateHighDescriptorV1.write("model-low-ports.json",(ujson.write(portsObservation,indent=2)+"\n").getBytes(StandardCharsets.UTF_8),128<<10)
    retain("EMITTER_SCOPE.txt","UNREVIEWED_MODEL_CANDIDATE_DENSEACC_STORAGE_ADAPTED_ORIGINAL_HOST_FUNCTIONAL_MODEL_BACKEND; SAME_HOST844_FULL4096_FIXED32; MATRIX_REAL_PHYSICAL_PROVIDER_REQUIRED_NO_DPI; ORIGINAL_IDMA_REQUIRED; NO_WIDTH_OR_COMPARISON_ADAPTATION; NOT_RUN_OR_FIVE_BLOCK_PASS\n")
  }
}
