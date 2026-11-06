package heteronpu.continuous.model

import firrtl2.ir._

/** Classify only exact ports whose module and instance topology were checked.
  * Unknown/intermediate nodes remain OTHER. No dotted-name heuristic labels.
  */
object CycleWitnessRoles {
  def apply(c:Circuit,bindings:Map[String,String]):Map[String,String]={
    val ms=c.modules.map(m=>m.name->m).toMap
    require(ms.size==c.modules.size,"CYCLE_WITNESS_ROLES_MODULES")
    val leaves=bindings.toVector.filter(_._2==IdmaSplitLayout.modelName)
    require(leaves.size==1,"CYCLE_WITNESS_ROLES_LEAF_COUNT")
    val leafPath=leaves.head._1
    val parts=leafPath.split("\\.").toVector
    require(parts.size>=2 && parts.size<=64 && parts.forall(_.nonEmpty),"CYCLE_WITNESS_ROLES_PATH")
    var selected=ms(c.main);var wrapper:Module=null
    parts.zipWithIndex.foreach{case(segment,index)=>
      val m=selected.asInstanceOf[Module]
      if(index==parts.size-1)wrapper=m
      val instances=Vector.newBuilder[DefInstance]
      def visit(s:Statement):Unit={s match{case i:DefInstance if i.name==segment=>instances+=i;case _=>()};s.foreachStmt(visit)}
      visit(m.body);val matches=instances.result();require(matches.size==1,"CYCLE_WITNESS_ROLES_INSTANCE")
      selected=ms(matches.head.module)
    }
    val leaf=selected.asInstanceOf[ExtModule]
    require(leaf.defname==IdmaSplitLayout.modelName && leaf.ports==IdmaSplitLayout.ports,"CYCLE_WITNESS_ROLES_LEAF_ABI")
    val wrapperPath=parts.dropRight(1).mkString(".")
    def exact(m:DefModule,p:String,d:Direction,w:Int,guard:String):Unit=
      require(m.ports.count(x=>x.name==p && x.direction==d && x.tpe==UIntType(IntWidth(w)))==1,guard)
    exact(wrapper,"axi_read_req_o",Output,IdmaSplitLayout.busWidths("axi_read_req_o"),"CYCLE_WITNESS_ROLES_PACKED_REQ")
    exact(wrapper,"axi_read_rsp_i",Input,IdmaSplitLayout.busWidths("axi_read_rsp_i"),"CYCLE_WITNESS_ROLES_PACKED_RSP")
    exact(leaf,"axi_read_req_o__r_ready",Output,1,"CYCLE_WITNESS_ROLES_SPLIT_READY")
    exact(leaf,"axi_read_rsp_i__r_last",Input,1,"CYCLE_WITNESS_ROLES_SPLIT_LAST")
    Map(wrapperPath+".axi_read_req_o"->"IDMA_READ_REQUEST_PACKED",
      wrapperPath+".axi_read_rsp_i"->"IDMA_READ_RESPONSE_PACKED",
      leafPath+".axi_read_req_o__r_ready"->"IDMA_SPLIT_R_READY",
      leafPath+".axi_read_rsp_i__r_last"->"IDMA_SPLIT_R_LAST")
  }
}
