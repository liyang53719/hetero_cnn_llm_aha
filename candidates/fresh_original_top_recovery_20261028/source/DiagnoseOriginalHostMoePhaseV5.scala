// SPDX-License-Identifier: Apache-2.0
package chiseltest.simulator

import heteronpu.continuous._
import firrtl2.{CircuitState, AnnotationSeq}
import firrtl2.ir._
import firrtl2.annotations.JsonProtocol
import firrtl2.options.TargetDirAnnotation
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths,StandardOpenOption}
import java.security.MessageDigest
import java.lang.management.ManagementFactory

/** One same original Host Top, not a wrapper Module/test harness. Diagnostic
  * high->official low FIRRTL only. No simulation, custom lowering, SV/firtool,
  * FIFO replacement, reference values, model/profile constructor override,
  * policy change, or qualification inherited from previous types/fixtures.
  */
object DiagnoseOriginalHostMoePhaseV5 {
  private val out=Paths.get("host-diagnostic")
  private val started=System.nanoTime()
  private val os=ManagementFactory.getOperatingSystemMXBean.asInstanceOf[com.sun.management.OperatingSystemMXBean]
  private def mark(name:String):Unit={
    println(s"HOST_PHASE $name wall_ns=${System.nanoTime()-started} process_cpu_ns=${os.getProcessCpuTime}")
    Console.out.flush()
  }
  private def phase[A](name:String)(f: => A):A={mark(name+".begin");val a=f;mark(name+".end");a}
  private def save(name:String,text:String):Unit={
    val bytes=text.getBytes(StandardCharsets.UTF_8)
    require(bytes.length<=384L*1024*1024,"single artifact cap")
    Files.write(out.resolve(name),bytes,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)
    val sha=MessageDigest.getInstance("SHA-256").digest(bytes).map(b=>f"${b&255}%02x").mkString
    println(s"HOST_ARTIFACT $name bytes=${bytes.length} sha256=$sha");Console.out.flush()
  }
  private def width(t:Type):BigInt=t match {
    case UIntType(IntWidth(w))=>w
    case SIntType(IntWidth(w))=>w
    case ClockType|ResetType|AsyncResetType=>BigInt(1)
    case BundleType(fields)=>fields.map(f=>width(f.tpe)).sum
    case VectorType(elem,n)=>width(elem)*n
    case x=>throw new IllegalArgumentException("unresolved diagnostic width "+x.serialize)
  }
  private def field(t:Type,name:String):Type=t match {
    case BundleType(fields)=>fields.find(_.name==name).getOrElse(throw new IllegalArgumentException("missing field "+name)).tpe
    case _=>throw new IllegalArgumentException("expected bundle for "+name)
  }
  private def inventory(state:CircuitState,label:String,high:Boolean):Unit={
    val c=state.circuit
    require(c.main=="HostBlockTopV4","only original real Top")
    require(c.modules.map(_.name).distinct.size==c.modules.size,"unique module definitions")
    val modules=c.modules.map(m=>m.name->m).toMap
    val rows=scala.collection.mutable.ArrayBuffer.empty[(String,String,String)]
    def visit(name:String,path:String,ancestors:Set[String]):Unit={
      require(!ancestors(name) && ancestors.size<128,"acyclic bounded hierarchy")
      val m=modules(name);require(rows.size<100000,"hierarchy inventory bound")
      rows+=((path,name,m match {case e:ExtModule=>e.defname;case _=>""}))
      m match {
        case r:Module=>
          def walk(s:Statement):Unit={s match {
            case i:DefInstance=>visit(i.module,if(path.isEmpty)i.name else path+"."+i.name,ancestors+name)
            case _=>()
          };s.foreachStmt(walk)}
          walk(r.body)
        case _:ExtModule=>()
      }
    }
    visit(c.main,"",Set.empty)
    val endpoints=rows.filter(_._3=="qwen2_matrix_command_endpoint")
    require(endpoints.size==8,"complete original eight512 endpoints")
    require(rows.count(_._3=="tc_clk_gating")==8,"eight original clock gates")
    for((_,name,_)<-endpoints){
      val e=modules(name).asInstanceOf[ExtModule]
      require(e.params==Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1))),"real seed enabled")
      def bits(n:String)=width(e.ports.find(_.name==n).getOrElse(throw new IllegalArgumentException("missing endpoint port "+n)).tpe)
      require(bits("seed_data_i")==512 && bits("out_acc_o")==16384,"no seed/result truncation")
    }
    val banks=rows.filter(_._2.startsWith("UnifiedVectorElement32BankV4"))
    require(banks.size==1,"one fixed32 Element bank")
    val bankPrefix=banks.head._1+"."
    require(rows.count(r=>r._1.startsWith(bankPrefix)&&r._2.startsWith("HeteroFP32Alu"))==32,"32 actual bank ALUs")
    require(rows.count(_._2.startsWith("HeteroStreamingTopK"))==1,"one real512 TopK")
    require(rows.count(_._2.startsWith("MatrixPipelineService"))==1,"one original Matrix service")
    require(rows.count(_._2.startsWith("QwenOwnerKernel"))==1,"one original Kernel")
    val top=modules(c.main).asInstanceOf[Module]
    if(high){
      val io=top.ports.find(_.name=="io").getOrElse(throw new IllegalArgumentException("actual Top io"))
      require(width(field(field(io.tpe,"launch"),"bits"))==844,"fixed public launch844")
    }
    save(label+"-hierarchy.tsv",rows.map{case(p,n,d)=>s"$p\t$n\t$d"}.mkString("","\n","\n"))
    save(label+"-top-ports.fir",top.ports.map(_.serialize).mkString("","\n","\n"))
    save(label+"-extmodules.fir",c.modules.collect{case e:ExtModule=>e.serialize}.mkString("","\n","\n"))
    save(label+"-summary.txt",s"top=${c.main}\nmodule_definitions=${c.modules.size}\nreachable_instances=${rows.size}\nendpoints=${endpoints.size}\nmatrix_logical_macs=4096\nfixed_element_lanes=32\nlaunch_bits=844\n"+
      "Scope: AST diagnostic only; no claim of physical SRAM ports, PPA, interface timing, full-model numerical or final provider RTL.\n")
  }
  private def annotations(state:CircuitState,label:String):Unit={
    save(label+"-annotations.json",JsonProtocol.serialize(state.annotations))
    require(!state.annotations.exists(_.isInstanceOf[UnsupportedAnnotation]),"unsupported official bridge annotation")
  }
  def main(args:Array[String]):Unit={
    require(args.isEmpty,"one fixed common constructor; no model/profile/shape override")
    require(!Files.exists(out),"fresh diagnostic directory")
    Files.createDirectory(out)
    // Original public21 producer/consumer constructor is retained. Capacity1024
    // is not an M128 run; runtime profile1..4 admission remains Unsupported.
    val shape=QwenBlockShape().copy(retainedMatrix=true,matrixColumns=256)
    val (high,_)=phase("elaborate"){
      Compiler.elaborate(()=>new HostBlockTopV4(shape,weightReadBeats=16,pipelined=true,
        burstWrites=true,commitTailRead=false,overlapSilu=false,
        enableTransposedDown=true,enableResidentFfn=true,enablePublic21QkvReduction=true,
        numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
        enableProductionPackedQk16=true,enableOrderedVectorQkFold=true),
        Seq(TargetDirAnnotation(out.toString)),Seq.empty)
    }
    phase("high.save"){save("original-high.fir",high.circuit.serialize);annotations(high,"high")}
    phase("high.identity"){inventory(high,"high",high=true)}
    // Exact official Compiler.toLowFirrtl default pipeline includes width/flow
    // checks, ExpandWhensAndCheck initialization and CheckCombLoops. No custom
    // transforms or annotation suppression is introduced here.
    val low=phase("official.low"){Compiler.toLowFirrtl(high)}
    phase("low.save"){save("official-low.fir",low.circuit.serialize);annotations(low,"low")}
    phase("low.identity"){inventory(low,"low",high=false)}
    save("SCOPE.txt","HIGH_AND_OFFICIAL_LOW_FIRRTL_ONLY; ORIGINAL_HOST_TOP; NOT_SIMULATION_OR_SV_OR_FULLMODEL_PASS\n")
    mark("PASS_HIGH_AND_LOW_DIAGNOSTIC_ONLY")
  }
}
