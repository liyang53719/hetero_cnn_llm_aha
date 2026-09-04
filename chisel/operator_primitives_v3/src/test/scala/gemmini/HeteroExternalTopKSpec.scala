package gemmini

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec
import org.scalatest.matchers.should.Matchers

class HeteroExternalTopKSpec extends AnyFlatSpec with ChiselScalatestTester with Matchers {
  behavior of "external-SRAM Top-K primitives"

  private type Entry = (Boolean, BigInt, BigInt)
  private val scores = Seq(
    (BigInt("3f800000", 16), BigInt(0)),
    (BigInt("40400000", 16), BigInt(1)),
    (BigInt("40000000", 16), BigInt(2)),
    (BigInt("40400000", 16), BigInt(3)))

  it should "rank stable FP32 ties through an external 512x65-compatible table" in {
    test(new HeteroStreamingTopK(maxK = 8, indexBits = 32, itemCountBits = 8)) { dut =>
      val memory = Array.fill[Entry](8)((false, 0, 0))
      var pending: Option[Entry] = None
      var input = 0
      var output = Vector.empty[(BigInt, BigInt)]
      dut.io.clear.poke(true.B);dut.io.start.poke(false.B);dut.io.itemCount.poke(4.U);dut.io.k.poke(3.U)
      dut.io.in.valid.poke(false.B);dut.io.out.ready.poke(false.B);dut.io.tableRequest.ready.poke(true.B)
      dut.io.tableResponse.valid.poke(false.B);dut.clock.step();dut.io.clear.poke(false.B)
      dut.io.start.poke(true.B);dut.clock.step();dut.io.start.poke(false.B)
      var cycle = 0
      while (output.size < 3 && cycle < 2000) {
        dut.io.in.valid.poke((input < scores.size).B)
        if (input < scores.size) { dut.io.in.bits.score.poke(scores(input)._1.U);dut.io.in.bits.index.poke(scores(input)._2.U) }
        dut.io.out.ready.poke((cycle % 3 != 1).B)
        dut.io.tableRequest.ready.poke(true.B)
        dut.io.tableResponse.valid.poke(pending.nonEmpty.B)
        pending.foreach { case (valid, score, index) =>
          dut.io.tableResponse.bits.valid.poke(valid.B);dut.io.tableResponse.bits.score.poke(score.U);dut.io.tableResponse.bits.index.poke(index.U)
        }
        val inputFire = input < scores.size && dut.io.in.ready.peek().litToBoolean
        val outputFire = dut.io.out.valid.peek().litToBoolean && cycle % 3 != 1
        val requestFire = dut.io.tableRequest.valid.peek().litToBoolean
        val responseFire = pending.nonEmpty && dut.io.tableResponse.ready.peek().litToBoolean
        val request = if (requestFire) Some((dut.io.tableRequest.bits.write.peek().litToBoolean,
          dut.io.tableRequest.bits.address.peek().litValue,
          dut.io.tableRequest.bits.data.valid.peek().litToBoolean,
          dut.io.tableRequest.bits.data.score.peek().litValue,
          dut.io.tableRequest.bits.data.index.peek().litValue)) else None
        val observed = if (outputFire) Some((dut.io.out.bits.score.peek().litValue,dut.io.out.bits.index.peek().litValue)) else None
        dut.clock.step()
        if (responseFire) pending = None
        request.foreach { case (write, address, valid, score, index) =>
          if (write) memory(address.toInt) = (valid, score, index)
          else pending = Some(memory(address.toInt))
        }
        if (inputFire) input += 1
        observed.foreach(x => output = output :+ x)
        cycle += 1
      }
      output shouldBe Vector(
        (BigInt("40400000",16),BigInt(1)),
        (BigInt("40400000",16),BigInt(3)),
        (BigInt("40000000",16),BigInt(2)))
      dut.io.invalidConfig.expect(false.B)
    }
  }

  it should "expand QSA Top-K blocks and the incomplete causal tail using the same external table" in {
    test(new HeteroQsaBlockSelector(maxBlockTopK = 8, blockCountBits = 8, tokenBits = 16, ratioBits = 4)) { dut =>
      val memory = Array.fill[Entry](8)((false, 0, 0))
      var pending: Option[Entry] = None
      var input = 0
      var output = Vector.empty[(BigInt, BigInt, Boolean)]
      dut.io.clear.poke(true.B);dut.io.start.poke(false.B);dut.io.completeBlocks.poke(4.U);dut.io.blockTopK.poke(2.U)
      dut.io.compressRatio.poke(2.U);dut.io.tailCount.poke(1.U);dut.io.scoreIn.valid.poke(false.B)
      dut.io.selectedOut.ready.poke(false.B);dut.io.topKTableRequest.ready.poke(true.B);dut.io.topKTableResponse.valid.poke(false.B)
      dut.clock.step();dut.io.clear.poke(false.B);dut.io.start.poke(true.B);dut.clock.step();dut.io.start.poke(false.B)
      var cycle = 0
      while (output.size < 5 && cycle < 5000) {
        dut.io.scoreIn.valid.poke((input < scores.size).B)
        if (input < scores.size) { dut.io.scoreIn.bits.score.poke(scores(input)._1.U);dut.io.scoreIn.bits.index.poke(scores(input)._2.U) }
        dut.io.selectedOut.ready.poke((cycle % 4 != 2).B)
        dut.io.topKTableRequest.ready.poke(true.B);dut.io.topKTableResponse.valid.poke(pending.nonEmpty.B)
        pending.foreach { case (valid, score, index) =>
          dut.io.topKTableResponse.bits.valid.poke(valid.B);dut.io.topKTableResponse.bits.score.poke(score.U);dut.io.topKTableResponse.bits.index.poke(index.U)
        }
        val inputFire = input < scores.size && dut.io.scoreIn.ready.peek().litToBoolean
        val outputFire = dut.io.selectedOut.valid.peek().litToBoolean && cycle % 4 != 2
        val requestFire = dut.io.topKTableRequest.valid.peek().litToBoolean
        val responseFire = pending.nonEmpty && dut.io.topKTableResponse.ready.peek().litToBoolean
        val request = if (requestFire) Some((dut.io.topKTableRequest.bits.write.peek().litToBoolean,
          dut.io.topKTableRequest.bits.address.peek().litValue,
          dut.io.topKTableRequest.bits.data.valid.peek().litToBoolean,
          dut.io.topKTableRequest.bits.data.score.peek().litValue,
          dut.io.topKTableRequest.bits.data.index.peek().litValue)) else None
        val observed = if (outputFire) Some((dut.io.selectedOut.bits.token.peek().litValue,
          dut.io.selectedOut.bits.blockRank.peek().litValue,dut.io.selectedOut.bits.fromTail.peek().litToBoolean)) else None
        dut.clock.step()
        if (responseFire) pending = None
        request.foreach { case (write, address, valid, score, index) =>
          if (write) memory(address.toInt) = (valid, score, index)
          else pending = Some(memory(address.toInt))
        }
        if (inputFire) input += 1
        observed.foreach(x => output = output :+ x)
        cycle += 1
      }
      output shouldBe Vector(
        (BigInt(2),BigInt(0),false),(BigInt(3),BigInt(0),false),
        (BigInt(6),BigInt(1),false),(BigInt(7),BigInt(1),false),
        (BigInt(8),BigInt(2),true))
      dut.io.invalidConfig.expect(false.B)
    }
  }
}
