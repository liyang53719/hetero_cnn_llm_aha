// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class LayerChainSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  val shape=QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32)
  val layout=new QwenBlockLayout(shape)
  val base=BigInt(1)<<32
  def init(d:LayerChainController):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B);d.io.blockLaunch.ready.poke(false.B)
    d.io.blockResult.valid.poke(false.B);d.io.blockResult.bits.status.poke(0.U);d.io.blockResult.bits.phase.poke(14.U)
    d.io.blockResult.bits.epoch.poke(7.U);d.io.blockResult.bits.cycles.poke(123.U)
    d.io.blockResult.bits.macs.poke(4096.U);d.io.blockResult.bits.executedMacs.poke(131072.U)
    d.io.stageCommit.poke(false.B);d.io.committedPhase.poke(0.U)
    d.io.memoryDrained.poke(true.B);d.io.externalFault.poke(false.B)
    d.io.launch.bits.base.poke(base.U);d.io.launch.bits.limit.poke((base+layout.total*4).U)
    d.io.launch.bits.stride.poke(layout.total.U);d.io.launch.bits.tokens.poke(17.U)
    d.io.launch.bits.epoch.poke(7.U);d.io.launch.bits.layers.poke(3.U)
  }
  "LayerChainController" should "reuse one block with different arena bases and wait for all fifteen commits" in {
    test(new LayerChainController(shape)){d=>
      init(d);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
      for(l<-0 until 3){
        d.io.blockLaunch.valid.expect(true.B);d.io.blockLaunch.bits.base.expect((base+l*layout.total).U)
        d.clock.step(3);d.io.blockLaunch.bits.base.expect((base+l*layout.total).U)
        d.io.blockLaunch.ready.poke(true.B);d.clock.step();d.io.blockLaunch.ready.poke(false.B)
        for(p<-0 until 15){d.io.committedPhase.poke(p.U);d.io.stageCommit.poke(true.B);d.clock.step();d.io.stageCommit.poke(false.B);d.clock.step()}
        d.io.blockResult.valid.poke(true.B);d.io.layerCommit.expect(true.B);d.clock.step();d.io.blockResult.valid.poke(false.B)
      }
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(0.U);d.io.result.bits.completedLayers.expect(3.U)
      d.io.result.bits.macs.expect(12288.U);d.io.result.bits.finalOutput.expect((base+layout.total*2+layout("y")).U)
      d.clock.step(5);d.io.result.valid.expect(true.B);d.io.result.ready.poke(true.B);d.clock.step();d.io.launch.ready.expect(true.B)
    }
  }
  for(fault<-Seq("missing_phase","reordered_phase","pending_write","epoch","status")){
    it should s"never launch a consumer after failed producer $fault" in {
      test(new LayerChainController(shape)){d=>
        init(d);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
        d.io.blockLaunch.ready.poke(true.B);d.clock.step();d.io.blockLaunch.ready.poke(false.B)
        for(p<-0 until (if(fault=="missing_phase")14 else 15)){
          d.io.committedPhase.poke((if(fault=="reordered_phase"&&p==3)4 else p).U);d.io.stageCommit.poke(true.B);d.clock.step();d.io.stageCommit.poke(false.B)
        }
        if(fault=="pending_write")d.io.memoryDrained.poke(false.B)
        if(fault=="epoch")d.io.blockResult.bits.epoch.poke(8.U)
        if(fault=="status")d.io.blockResult.bits.status.poke(3.U)
        d.io.blockResult.valid.poke(true.B);d.io.layerCommit.expect(false.B);d.clock.step();d.io.blockResult.valid.poke(false.B)
        d.io.result.valid.expect(true.B);d.io.result.bits.status.peek().litValue should not be BigInt(0)
        d.io.result.bits.completedLayers.expect(0.U);d.io.resetRequired.expect(true.B)
        d.io.result.ready.poke(true.B);d.clock.step();d.io.launch.ready.expect(false.B);d.io.blockLaunch.valid.expect(false.B)
      }
    }
  }
  for(fault<-Seq("zero","too_many","stride","overflow","tokens")){
    it should s"reject invalid whole-chain extent $fault before any child starts" in {
      test(new LayerChainController(shape)){d=>
        init(d)
        fault match {
          case "zero" => d.io.launch.bits.layers.poke(0.U)
          case "too_many" => d.io.launch.bits.layers.poke(29.U)
          case "stride" => d.io.launch.bits.stride.poke((layout.total-64).U)
          case "overflow" => d.io.launch.bits.base.poke(((BigInt(1)<<64)-64).U)
          case "tokens" => d.io.launch.bits.tokens.poke(1025.U)
        }
        d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)
        d.io.blockLaunch.valid.expect(false.B);d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(5.U)
      }
    }
  }
}
