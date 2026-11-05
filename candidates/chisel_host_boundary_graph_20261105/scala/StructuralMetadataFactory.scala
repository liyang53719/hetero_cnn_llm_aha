package heteronpu.continuous.model

import firrtl2.ir._
import treadle2.{ScalaBlackBox, ScalaBlackBoxFactory}
import treadle2.executable.Transition

/** Metadata ONLY. These independently copied ABI/dependency declarations must
  * be reviewed against the pinned candidate whenever that candidate changes.
  * No functional endpoint, native leaf, or execution engine is constructed.
  */
object StructuralLeafContract {
  val endpoint = "qwen2_matrix_command_endpoint"
  val gate = "tc_clk_gating"
  private val ins = Map("clk_i"->1,"rst_ni"->1,"cmd_valid_i"->1,"cmd_i"->128,
    "step_valid_i"->1,"step_context_i"->3,"step_clear_i"->1,"step_last_i"->1,
    "command_last_tile_i"->1,"step_a_i"->256,"step_b_i"->512,"out_ready_i"->1,
    "completion_ready_i"->1,"seed_begin_valid_i"->1,"seed_context_i"->3,
    "seed_group_tag_i"->32,"seed_group_sequence_i"->32,"seed_source_generation_i"->32,
    "seed_beat_valid_i"->1,"seed_cluster_i"->5,"seed_data_i"->512,
    "seed_commit_valid_i"->1,"seed_abort_i"->1,"seed_ack_ready_i"->1)
  private val outs = Map("cmd_ready_o"->1,"step_ready_o"->1,"out_valid_o"->1,
    "out_context_o"->3,"out_last_o"->1,"out_acc_o"->16384,"completion_valid_o"->1,
    "completion_data_o"->56,"protocol_error_o"->1)
  private val seedOuts = Map("seed_begin_ready_o"->1,"seed_beat_ready_o"->1,
    "seed_commit_ready_o"->1,"seed_ack_valid_o"->1,"seed_ack_context_o"->3,
    "seed_ack_group_tag_o"->32,"seed_ack_group_sequence_o"->32,
    "seed_ack_source_generation_o"->32,"seed_ack_error_o"->1,"seed_reset_required_o"->1,
    "arithmetic_busy_o"->5,"arithmetic_out_valid_o"->1)
  def ports(kind:String,seed:Boolean):Map[String,(Direction,Type)] = kind match {
    case `endpoint` =>
      val in=ins.filter{case(n,_)=>seed || !n.startsWith("seed_")}.map{case(n,w)=>
        n->((Input:Direction), (if(n=="clk_i") ClockType else UIntType(IntWidth(w))):Type)}
      in ++ (outs ++ (if(seed)seedOuts else Map.empty[String,Int])).map{case(n,w)=>
        n->((Output:Direction),(UIntType(IntWidth(w)):Type))}
    case `gate` => Map("clk_i"->(Input,ClockType),"en_i"->(Input,UIntType(IntWidth(1))),
      "test_en_i"->(Input,UIntType(IntWidth(1))),"clk_o"->(Output,ClockType))
    case IdmaSplitLayout.modelName => IdmaSplitLayout.ports.map(p=>p.name->(p.direction,p.tpe)).toMap
    case _ => throw new IllegalArgumentException("unknown structural leaf")
  }
  def params(kind:String,seed:Boolean):Seq[Param] =
    if(kind==endpoint && seed)Seq(IntParam("ENABLE_ACCUMULATOR_SEED",BigInt(1))) else Seq.empty
}

final class StructuralMetadataFactory(circuit:Circuit,seed:Boolean) extends ScalaBlackBoxFactory {
  private val modules=circuit.modules.map(m=>m.name->m).toMap
  require(modules.size==circuit.modules.size,"unique module declarations")
  require(modules.get(circuit.main).exists(_.isInstanceOf[Module]),"regular top required")
  private val expected=scala.collection.mutable.Map.empty[String,String]
  private def visit(n:String,path:String,ancestors:Set[String]):Unit={
    require(!ancestors(n),"nonrecursive hierarchy")
    modules(n) match {
      case e:ExtModule =>
        val ports=StructuralLeafContract.ports(e.defname,seed)
        require(e.ports.map(_.name).distinct.size==e.ports.size,"unique leaf ports")
        require(e.ports.map(p=>p.name->(p.direction,p.tpe)).toMap==ports,"exact leaf ABI")
        require(e.params==StructuralLeafContract.params(e.defname,seed),"exact leaf params")
        require(path.nonEmpty && !expected.contains(path),"unique leaf path")
        expected(path)=e.defname
      case m:Module =>
        def walk(s:Statement):Unit={
          s match {case i:DefInstance=>visit(i.module,if(path.isEmpty)i.name else path+"."+i.name,ancestors+n);case _=>()}
          s.foreachStmt(walk)
        }
        walk(m.body)
    }
  }
  visit(circuit.main,"",Set.empty)
  require(expected.values.count(_==StructuralLeafContract.endpoint)==8,"eight matrix leaves")
  require(expected.values.count(_==StructuralLeafContract.gate)==8,"eight clock gates")
  require(expected.values.count(_==IdmaSplitLayout.modelName)==1 && expected.size==17,"one iDMA leaf")
  val bindings:Map[String,String]=expected.toMap
  private val instantiated=scala.collection.mutable.Set.empty[String]
  def requireComplete():Unit=require(instantiated.toSet==bindings.keySet && boxes.size==17,"all exact metadata bindings")
  override def createInstance(instanceName:String,blackBoxName:String):Option[ScalaBlackBox]={
    require(bindings.get(instanceName).contains(blackBoxName) && !instantiated(instanceName),"exact unique metadata instance")
    val box=new StructuralMetadataBox(instanceName,blackBoxName,seed)
    instantiated+=instanceName
    Some(add(box))
  }
}

private final class StructuralMetadataBox(val name:String,kind:String,seed:Boolean) extends ScalaBlackBox {
  private val ports=StructuralLeafContract.ports(kind,seed)
  private def forbidden():Nothing=throw new IllegalStateException("structural metadata cannot execute")
  override def setParams(p:Seq[Param]):Unit=forbidden()
  override def setPlusArgs(p:Seq[treadle2.blackboxes.PlusArg]):Unit=forbidden()
  override def inputChanged(p:String,v:BigInt):Unit=forbidden()
  override def clockChange(t:Transition,n:String):Unit=forbidden()
  override def getOutput(v:Seq[BigInt],t:Type,n:String):BigInt=forbidden()
  override def finish():Unit=forbidden()
  override def getDependencies:Seq[(String,Set[String])]={
    if(kind==StructuralLeafContract.gate)Seq("en_i"->Set("clk_o"),"test_en_i"->Set("clk_o"))
    else {
      val anchor=if(kind==StructuralLeafContract.endpoint)"out_valid_o" else "req_ready_o"
      ports.toSeq.filter{case(n,(d,_))=>d==Input && n!="clk_i" && n!="rst_ni"}
        .map(_._1).sorted.map(_->Set(anchor))
    }
  }
  override def outputDependencies(port:String):Seq[String]={
    require(ports.get(port).exists(_._1==Output),"known output")
    val q=Seq("clk_i","rst_ni")
    if(kind==StructuralLeafContract.gate)Seq("clk_i")
    else if(kind==StructuralLeafContract.endpoint){
      val sb=if(seed)Seq("seed_begin_valid_i","seed_beat_valid_i","seed_commit_valid_i","seed_abort_i") else Seq.empty
      port match {
        case "cmd_ready_o"=>q++sb
        case "step_ready_o"=>q++Seq("step_context_i","out_ready_i")++sb
        case "seed_begin_ready_o"|"seed_beat_ready_o"|"seed_commit_ready_o"=>q++Seq("step_context_i","step_valid_i","out_ready_i")++sb
        case _=>q
      }
    }else{
      val rd="axi_read_rsp_i__";val wr="axi_write_rsp_i__"
      port match {
        case "rsp_valid_o"=>q++Seq(wr+"b_valid","req_valid_i","length_i")
        case "rsp_error_o"=>q++Seq(rd+"r_valid",rd+"r_resp",wr+"b_valid",wr+"b_resp","req_valid_i","length_i")
        case "axi_read_req_o__r_ready"=>q++Seq(rd+"r_last",wr+"w_ready")
        case "busy_o"=>q++Seq(wr+"w_ready")
        case _=>q
      }
    }
  }
}
