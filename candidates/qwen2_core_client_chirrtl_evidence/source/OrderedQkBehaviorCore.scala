// Test-only read-only shell; no replacement arithmetic, no production mutation.
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Official shape unchanged; only accepted owner.m is M1/M2/M3.
  * Uses production PackedAttentionStreamClient created inside the real core.
  * External Matrix results are scripted protocol stimuli, NOT FMA evidence.
  */
class OrderedQkBehaviorCore(ordered:Boolean=true) extends Qwen2ContinuousBlock(
  QwenBlockShape(hidden=1536,ffn=8960,heads=12,kvHeads=2,headDim=128,
    maxTokens=1024,retainedMatrix=true,matrixColumns=256),
  ownerDriven=true,externalMatrix=true,externalScalar=false,
  numericPolicy=Qwen2NumericPolicy.Qwen2OfficialBf16V2,
  enableProductionPackedQk16=true,enableOrderedVectorQkFold=ordered) {
  val observation=IO(Output(new Bundle {
    val state=UInt(7.W);val vectorPhase=UInt(3.W)
    val token=UInt(16.W);val head=UInt(8.W);val key=UInt(16.W)
    val lane=UInt(4.W);val selected=UInt(4.W);val faults=UInt(16.W)
    val maxScore=UInt(32.W);val committed=Bool();val owned=Bool()
    val memoryDebt=Bool();val localDebt=Bool();val scalarDebt=Bool()
    val selectedFault=Bool();val resultReady=Bool();val completionValid=Bool()
    val completionReady=Bool();val scalarIssue=Bool()
  }))
  observation.state:=state;observation.vectorPhase:=0.U
  if(ordered){
    when(state===st("attVectorScan")){observation.vectorPhase:=1.U}
    when(state===st("attVectorFold")){observation.vectorPhase:=2.U}
    when(state===st("attVectorScale")){observation.vectorPhase:=3.U}
    when(state===st("attVectorRetire")){observation.vectorPhase:=4.U}
  }
  observation.token:=token;observation.head:=head;observation.key:=key
  observation.lane:=lane;observation.selected:=packedSelected.get
  observation.faults:=orderedQkFault.map(_.asUInt).getOrElse(0.U(16.W))
  observation.maxScore:=maxScore;observation.committed:=packedCommitted.get
  observation.owned:=packedOwned.get
  observation.memoryDebt:=packedMemDebt.get;observation.localDebt:=packedLocalDebt.get
  observation.scalarDebt:=packedScalarDebt.get;observation.selectedFault:=packedSelectedFault
  observation.resultReady:=packedQk.get.io.result.ready
  observation.completionValid:=packedQk.get.io.completion.valid
  observation.completionReady:=packedQk.get.io.completion.ready
  observation.scalarIssue:=scalar.io.request.valid
  dontTouch(observation);dontTouch(testScoreWrite)
}
