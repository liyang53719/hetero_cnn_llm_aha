// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chiseltest._
import chiseltest.simulator.VerilatorBackendAnnotation
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class BlockWritebackFenceSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  private def initialize(d: BlockWritebackFence, expected: Int = 64): Unit = {
    d.io.startRequest.poke(false.B); d.io.startStage.poke(false.B)
    d.io.issue.valid.poke(false.B); d.io.response.valid.poke(false.B)
    d.io.issue.bits.write.poke(false.B); d.io.issue.bits.address.poke(0.U)
    d.io.issue.bits.data.poke(0.U); d.io.issue.bits.mask.poke(0.U); d.io.issue.bits.tag.poke(0.U)
    d.io.response.bits.tag.poke(0.U); d.io.response.bits.error.poke(false.B); d.io.response.bits.data.poke(0.U)
    d.io.expectedBytes.poke(expected.U)
    d.io.startRequest.poke(true.B); d.clock.step(); d.io.startRequest.poke(false.B)
  }
  private def issue(d: BlockWritebackFence, tag: Int, bytes: Int = 64, write: Boolean = true): Unit = {
    d.io.issue.bits.write.poke(write.B); d.io.issue.bits.tag.poke(tag.U)
    d.io.issue.bits.mask.poke(((BigInt(1) << bytes)-1).U)
    d.io.issue.valid.poke(true.B); d.clock.step(); d.io.issue.valid.poke(false.B)
  }
  private def ack(d: BlockWritebackFence, tag: Int, error: Boolean = false): Unit = {
    d.io.response.bits.tag.poke(tag.U); d.io.response.bits.error.poke(error.B)
    d.io.response.valid.poke(true.B); d.clock.step(); d.io.response.valid.poke(false.B)
  }
  "BlockWritebackFence" should "wait for final successful write ACK rather than issued stores" in {
    test(new BlockWritebackFence).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d,128); issue(d,1); d.clock.step(7); d.io.canCommit.expect(false.B); d.io.phaseBytes.expect(0.U)
      ack(d,1); d.io.canCommit.expect(false.B); d.io.phaseBytes.expect(64.U)
      issue(d,2); d.clock.step(3); d.io.canCommit.expect(false.B)
      ack(d,2); d.io.canCommit.expect(true.B); d.io.totalBytes.expect(128.U); d.io.error.expect(false.B)
    }
  }
  it should "exclude reads and count the actual byte mask for a partial final beat" in {
    test(new BlockWritebackFence).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d,68); issue(d,1,64,false); ack(d,1); d.io.phaseBytes.expect(0.U)
      issue(d,2); ack(d,2); issue(d,3,4); ack(d,3); d.io.canCommit.expect(true.B)
      d.io.totalBytes.expect(68.U)
    }
  }
  it should "reset per-stage counts but retain the request total and then allow another request" in {
    test(new BlockWritebackFence).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
      initialize(d); issue(d,1); ack(d,1)
      d.io.startStage.poke(true.B); d.clock.step(); d.io.startStage.poke(false.B)
      d.io.phaseBytes.expect(0.U); d.io.totalBytes.expect(64.U); d.io.canCommit.expect(false.B)
      issue(d,2); ack(d,2); d.io.canCommit.expect(true.B); d.io.totalBytes.expect(128.U)
      d.io.startRequest.poke(true.B); d.clock.step(); d.io.startRequest.poke(false.B)
      d.io.totalBytes.expect(0.U); d.io.canCommit.expect(false.B)
      issue(d,3); ack(d,3); d.io.canCommit.expect(true.B)
    }
  }
  for(kind<-Seq("write_error","tag_error","unsolicited","duplicate_ack","overrun","zero_mask","double_issue","premature_stage")){
    it should s"poison $kind without publishing a tensor" in {
      test(new BlockWritebackFence).withAnnotations(Seq(VerilatorBackendAnnotation)){d=>
        initialize(d)
        kind match {
          case "write_error" => issue(d,1); ack(d,1,true)
          case "tag_error" => issue(d,1); ack(d,2)
          case "unsolicited" => ack(d,1)
          case "duplicate_ack" => issue(d,1); ack(d,1); ack(d,1)
          case "overrun" => issue(d,1); ack(d,1); issue(d,2); ack(d,2)
          case "zero_mask" => issue(d,1,0)
          case "double_issue" => issue(d,1); issue(d,2)
          case "premature_stage" => issue(d,1); d.io.startStage.poke(true.B); d.clock.step(); d.io.startStage.poke(false.B)
        }
        d.io.error.expect(true.B); d.io.canCommit.expect(false.B)
        d.clock.step(3); d.io.error.expect(true.B)
        d.reset.poke(true.B); d.clock.step(); d.reset.poke(false.B)
        initialize(d); issue(d,7); ack(d,7); d.io.error.expect(false.B); d.io.canCommit.expect(true.B)
      }
    }
  }
}
