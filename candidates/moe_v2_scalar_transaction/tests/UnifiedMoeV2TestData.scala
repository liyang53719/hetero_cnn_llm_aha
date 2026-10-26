package heteronpu.continuous
import chisel3._
import chiseltest._

/** Deterministic protocol stimuli only. No software model computes a claimed
  * hardware numerical answer. Mock primitive results in control tests are
  * explicitly not numeric/HardFloat/complete4096 qualification. */
object UnifiedMoeV2TestData {
  def clearFlat(x:Bundle):Unit=x.elements.values.foreach {
    case b:Bool => b.poke(false.B)
    case u:UInt => u.poke(0.U)
    case _ => throw new IllegalArgumentException("flat scalar fields only")
  }
  def id(x:MoeBf16TileIdentity,txn:Long,token:Int=0,tile:Int=0):Unit={
    x.transactionId.poke(txn.U);x.token.poke(token.U);x.tileOrdinal.poke(tile.U)
  }
  def lease(x:UnifiedScalarTileLeaseV2,txn:Long,profile:Int=3,token:Int=0,tile:Int=0):Unit={
    id(x.identity,txn,token,tile);x.context.transactionId.poke(txn.U)
    clearFlat(x.context.launch);clearFlat(x.context.profile)
    val l=x.context.launch;val p=x.context.profile
    l.version.poke(1.U);l.opcode.poke(0.U);l.profileId.poke(profile.U);l.tag.poke(17.U)
    l.tokens.poke(128.U);l.cold.poke(true.B)
    p.profileId.poke(profile.U);p.mlp.poke(1.U);p.hidden.poke(2048.U)
    p.expertCount.poke(256.U);p.expertsPerToken.poke(8.U);p.expertFfn.poke(512.U);p.sharedFfn.poke(512.U)
    p.maxPosition.poke(262144.U)
    if(profile==3){p.mixer.poke(1.U);p.gdnKeyHeads.poke(16.U);p.gdnValueHeads.poke(32.U)
      p.gdnKeyDim.poke(128.U);p.gdnValueDim.poke(128.U);p.convKernel.poke(4.U)}
    else if(profile==4){p.attentionHeads.poke(16.U);p.kvHeads.poke(2.U);p.headDim.poke(256.U);p.rotaryDim.poke(64.U);l.cacheCapacity.poke(128.U)}
  }
  def op(x:UnifiedOwnedScalarRequestV2,txn:Long,serial:Int,token:Int=0,tile:Int=0):Unit={
    id(x.tag.tile,txn,token,tile);x.tag.operationSerial.poke(serial.U)
    x.payload.op.poke(ScalarOp.Add.U);x.payload.a.poke("h3f800000".U);x.payload.b.poke(0.U)
  }
  def scalar(x:UnifiedScalarResult,value:BigInt=0,error:Boolean=false):Unit={
    x.value.poke(value.U);x.flags.poke(0.U);x.primitiveFlagsValid.poke(true.B);x.error.poke(error.B)
  }
  def intent(x:UnifiedScalarTileReleaseIntentV2,txn:Long,count:Int,token:Int=0,tile:Int=0,status:Int=0):Unit={
    id(x.identity,txn,token,tile);x.issuedOperations.poke(count.U);x.completedOperations.poke(count.U)
    x.status.poke(status.U);x.drained.poke(true.B)
  }
  val expertLoad=Vector(256,5,1,7,0,3,6,4,2)
  val mergeTags=Vector(4,2,8,5,7,1,6,3,0)
  def route(x:UnifiedTaggedMoeRouteV2,txn:Long,expert:Int,weight:BigInt=0,token:Int=0,tile:Int=0):Unit={
    id(x.identity,txn,token,tile);x.payload.expert.poke(expert.U);x.payload.shared.poke((expert==256).B);x.payload.weight.poke(weight.U)
  }
  def returned(x:UnifiedTaggedMoeReturnV2,txn:Long,tag:Int,data:BigInt=0,token:Int=0,tile:Int=0):Unit={
    id(x.identity,txn,token,tile);x.payload.routeTag.poke(tag.U);x.payload.data.poke(data.U)
  }
}
