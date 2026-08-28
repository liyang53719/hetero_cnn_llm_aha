package gemmini

import chisel3._
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

class HeteroAllPrimitives extends Module {
  val io = IO(new Bundle {
    val bfA = Input(UInt(16.W)); val bfB = Input(UInt(16.W)); val bfC = Input(UInt(32.W)); val bfOut = Output(UInt(32.W)); val bfFlags = Output(UInt(5.W))
    val bfStageA = Input(UInt(24.W)); val bfStageB = Input(UInt(24.W)); val bfStageC = Input(UInt(48.W)); val bfStageMeta = Input(UInt(54.W)); val bfStageResult = Input(UInt(49.W)); val bfStageRaw = Input(UInt(41.W)); val bfStageInvalid = Input(Bool())
    val bfPreA = Output(UInt(24.W)); val bfPreB = Output(UInt(24.W)); val bfPreC = Output(UInt(48.W)); val bfPreMeta = Output(UInt(54.W)); val bfMulResult = Output(UInt(49.W)); val bfPostRaw = Output(UInt(41.W)); val bfPostInvalid = Output(Bool()); val bfRoundOut = Output(UInt(32.W)); val bfRoundFlags = Output(UInt(5.W))
    val aluOp = Input(Bool()); val aluX = Input(UInt(32.W)); val aluY = Input(UInt(32.W)); val aluOut = Output(UInt(32.W)); val aluFlags = Output(UInt(5.W))
    val floorX = Input(UInt(32.W)); val floorOut = Output(UInt(16.W)); val floorFlags = Output(UInt(8.W))
    val pipeInValid = Input(Bool()); val pipeX = Input(UInt(32.W)); val pipeY = Input(UInt(32.W)); val pipeTag = Input(UInt(12.W)); val pipeBit = Input(Bool()); val pipeOutReady = Input(Bool())
    val mulTagInReady = Output(Bool()); val mulTagOutValid = Output(Bool()); val mulTagOut = Output(UInt(32.W)); val mulTagFlags = Output(UInt(5.W)); val mulTagUser = Output(UInt(12.W))
    val addTagInReady = Output(Bool()); val addTagOutValid = Output(Bool()); val addTagOut = Output(UInt(32.W)); val addTagFlags = Output(UInt(5.W)); val addTagUser = Output(UInt(12.W))
    val mulBitInReady = Output(Bool()); val mulBitOutValid = Output(Bool()); val mulBitOut = Output(UInt(32.W)); val mulBitFlags = Output(UInt(5.W)); val mulBitUser = Output(Bool())
    val addBitInReady = Output(Bool()); val addBitOutValid = Output(Bool()); val addBitOut = Output(UInt(32.W)); val addBitFlags = Output(UInt(5.W)); val addBitUser = Output(Bool())
  })
  val bf = Module(new HeteroBF16FmaLane); dontTouch(bf.clock); dontTouch(bf.reset); bf.io.a := io.bfA; bf.io.b := io.bfB; bf.io.c := io.bfC; io.bfOut := bf.io.out; io.bfFlags := bf.io.exceptionFlags
  val bfPre = Module(new HeteroBF16FmaPre); bfPre.io.a := io.bfA; bfPre.io.b := io.bfB; bfPre.io.c := io.bfC; io.bfPreA := bfPre.io.mulAddA; io.bfPreB := bfPre.io.mulAddB; io.bfPreC := bfPre.io.mulAddC; io.bfPreMeta := bfPre.io.meta
  val bfMul = Module(new HeteroBF16FmaMul); bfMul.io.mulAddA := io.bfStageA; bfMul.io.mulAddB := io.bfStageB; bfMul.io.mulAddC := io.bfStageC; io.bfMulResult := bfMul.io.mulAddResult
  val bfPost = Module(new HeteroBF16FmaPost); bfPost.io.meta := io.bfStageMeta; bfPost.io.mulAddResult := io.bfStageResult; io.bfPostRaw := bfPost.io.raw; io.bfPostInvalid := bfPost.io.invalid
  val bfRound = Module(new HeteroBF16FmaRound); bfRound.io.raw := io.bfStageRaw; bfRound.io.invalid := io.bfStageInvalid; io.bfRoundOut := bfRound.io.out; io.bfRoundFlags := bfRound.io.exceptionFlags
  val fp = Module(new HeteroFP32Primitives); fp.io.aluOp := io.aluOp; fp.io.aluX := io.aluX; fp.io.aluY := io.aluY; io.aluOut := fp.io.aluOut; io.aluFlags := fp.io.aluFlags; fp.io.floorX := io.floorX; io.floorOut := fp.io.floorOut; io.floorFlags := fp.io.floorFlags
  val mulTag = Module(new HeteroFP32MulPipe(12, "HeteroFP32MulPipeTag12")); val addTag = Module(new HeteroFP32AddPipe(12, "HeteroFP32AddPipeTag12")); val mulBit = Module(new HeteroFP32MulPipe(1, "HeteroFP32MulPipeBit1")); val addBit = Module(new HeteroFP32AddPipe(1, "HeteroFP32AddPipeBit1"))
  mulTag.io.inValid := io.pipeInValid; mulTag.io.x := io.pipeX; mulTag.io.y := io.pipeY; mulTag.io.userIn := io.pipeTag; mulTag.io.outReady := io.pipeOutReady
  io.mulTagInReady := mulTag.io.inReady; io.mulTagOutValid := mulTag.io.outValid; io.mulTagOut := mulTag.io.out; io.mulTagFlags := mulTag.io.exceptionFlags; io.mulTagUser := mulTag.io.userOut
  addTag.io.inValid := io.pipeInValid; addTag.io.x := io.pipeX; addTag.io.y := io.pipeY; addTag.io.userIn := io.pipeTag; addTag.io.outReady := io.pipeOutReady
  io.addTagInReady := addTag.io.inReady; io.addTagOutValid := addTag.io.outValid; io.addTagOut := addTag.io.out; io.addTagFlags := addTag.io.exceptionFlags; io.addTagUser := addTag.io.userOut
  mulBit.io.inValid := io.pipeInValid; mulBit.io.x := io.pipeX; mulBit.io.y := io.pipeY; mulBit.io.userIn := io.pipeBit; mulBit.io.outReady := io.pipeOutReady
  io.mulBitInReady := mulBit.io.inReady; io.mulBitOutValid := mulBit.io.outValid; io.mulBitOut := mulBit.io.out; io.mulBitFlags := mulBit.io.exceptionFlags; io.mulBitUser := mulBit.io.userOut
  addBit.io.inValid := io.pipeInValid; addBit.io.x := io.pipeX; addBit.io.y := io.pipeY; addBit.io.userIn := io.pipeBit; addBit.io.outReady := io.pipeOutReady
  io.addBitInReady := addBit.io.inReady; io.addBitOutValid := addBit.io.outValid; io.addBitOut := addBit.io.out; io.addBitFlags := addBit.io.exceptionFlags; io.addBitUser := addBit.io.userOut
}
object EmitHeteroAllPrimitives extends App { require(args.length == 1); val path = Paths.get(args(0)); val sv = ChiselStage.emitSystemVerilog(new HeteroAllPrimitives); Files.createDirectories(path.getParent); Files.writeString(path, sv, StandardCharsets.UTF_8) }
