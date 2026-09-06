// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
class LayerStackGateSpec extends AnyFlatSpec with ChiselScalatestTester {
  val s=QwenBlockShape(hidden=64,ffn=128,heads=2,kvHeads=1,headDim=32,maxTokens=33)
  val g=new StackGeometry(s)
  def configure(d:LayerStackController,n:Int):Unit={
    d.io.launch.valid.poke(false.B);d.io.result.ready.poke(false.B)
    d.io.childLaunch.ready.poke(false.B);d.io.childResult.valid.poke(false.B)
    val c=d.io.launch.bits
    c.weights.poke(0x1000000.U);c.weightStride.poke(g.weightBytes.U);c.rope.poke(0x10000000.U)
    c.hiddenA.poke(0x20000000.U);c.hiddenB.poke(0x21000000.U);c.scratch.poke(0x30000000.U)
    c.limit.poke(0x40000000.U);c.layers.poke(n.U);c.tokens.poke(17.U);c.epoch.poke(100.U)
  }
  def launch(d:LayerStackController):Unit={d.io.launch.ready.expect(true.B);d.io.launch.valid.poke(true.B);d.clock.step();d.io.launch.valid.poke(false.B)}
  def result(d:LayerStackController,l:Int,status:Int=0,phase:Int=14,epoch:Int = -1):Unit={
    d.io.childResult.bits.status.poke(status.U);d.io.childResult.bits.phase.poke(phase.U)
    d.io.childResult.bits.epoch.poke((if(epoch<0)100+l else epoch).U)
    d.io.childResult.bits.macs.poke(17.U);d.io.childResult.bits.executedMacs.poke(512.U)
    d.io.childResult.valid.poke(true.B);d.clock.step();d.io.childResult.valid.poke(false.B)
  }
  for(n<-Seq(1,2,4,28)) it should s"publish exactly $n layers after actual child completion" in {
    test(new LayerStackController(s)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      configure(d,n);launch(d)
      for(i<-0 until n){
        d.io.childLaunch.valid.expect(true.B);d.io.childLaunch.bits.epoch.expect((100+i).U)
        d.io.sourceHidden.expect((if(i%2==0)0x20000000 else 0x21000000).U)
        d.clock.step(3);d.io.childLaunch.valid.expect(true.B)
        d.io.childLaunch.ready.poke(true.B);d.clock.step();d.io.childLaunch.ready.poke(false.B)
        d.clock.step(2);d.io.layerCommit.expect(false.B);result(d,i)
      }
      d.io.result.valid.expect(true.B);d.io.result.bits.status.expect(0.U)
      d.io.result.bits.completedLayers.expect(n.U);d.io.result.bits.usefulMacs.expect((n*17).U)
      d.io.result.bits.output.expect((if(n%2==1)0x21000000 else 0x20000000).U)
      val held=d.io.result.bits.peek();d.clock.step(5);d.io.result.bits.expect(held)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.launch.ready.expect(true.B)
    }
  }
  for(kind<-Seq("overlap","stride","zero_layers","many_layers","tokens","epoch_wrap","address_wrap")) it should s"reject $kind before starting a block" in {
    test(new LayerStackController(s)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      configure(d,2);val c=d.io.launch.bits
      kind match {
        case "overlap"=>c.hiddenB.poke(0x20000000.U)
        case "stride"=>c.weightStride.poke(64.U)
        case "zero_layers"=>c.layers.poke(0.U)
        case "many_layers"=>c.layers.poke(29.U)
        case "tokens"=>c.tokens.poke(34.U)
        case "epoch_wrap"=>c.epoch.poke(65535.U)
        case "address_wrap"=>c.weights.poke(((BigInt(1)<<64)-64).U)
      }
      launch(d);d.io.childLaunch.valid.expect(false.B);d.io.result.valid.expect(true.B)
      d.io.result.bits.status.expect(Status.Bounds.U);d.io.result.bits.completedLayers.expect(0.U)
    }
  }
  for(kind<-Seq("status","phase","epoch")) it should s"stop without publication on invalid child $kind" in {
    test(new LayerStackController(s)).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      configure(d,2);launch(d);d.io.childLaunch.ready.poke(true.B);d.clock.step()
      result(d,0,if(kind=="status")3 else 0,if(kind=="phase")13 else 14,if(kind=="epoch")99 else 100)
      d.io.result.valid.expect(true.B);d.io.result.bits.completedLayers.expect(0.U);d.io.resetRequired.expect(true.B)
      d.io.result.ready.poke(true.B);d.clock.step();d.io.launch.ready.expect(false.B)
      d.reset.poke(true.B);d.clock.step();d.reset.poke(false.B);d.io.launch.ready.expect(true.B)
    }
  }
}
