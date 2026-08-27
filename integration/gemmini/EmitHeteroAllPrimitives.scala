package gemmini

import chisel3._
import circt.stage.ChiselStage
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

class HeteroAllPrimitives extends Module {
  val io = IO(new Bundle {
    val bfA = Input(UInt(16.W)); val bfB = Input(UInt(16.W)); val bfC = Input(UInt(32.W)); val bfOut = Output(UInt(32.W)); val bfFlags = Output(UInt(5.W))
    val aluOp = Input(Bool()); val aluX = Input(UInt(32.W)); val aluY = Input(UInt(32.W)); val aluOut = Output(UInt(32.W)); val aluFlags = Output(UInt(5.W))
    val floorX = Input(UInt(32.W)); val floorOut = Output(UInt(16.W)); val floorFlags = Output(UInt(8.W))
  })
  val bf = Module(new HeteroBF16FmaLane); dontTouch(bf.clock); dontTouch(bf.reset); bf.io.a := io.bfA; bf.io.b := io.bfB; bf.io.c := io.bfC; io.bfOut := bf.io.out; io.bfFlags := bf.io.exceptionFlags
  val fp = Module(new HeteroFP32Primitives); fp.io.aluOp := io.aluOp; fp.io.aluX := io.aluX; fp.io.aluY := io.aluY; io.aluOut := fp.io.aluOut; io.aluFlags := fp.io.aluFlags; fp.io.floorX := io.floorX; io.floorOut := fp.io.floorOut; io.floorFlags := fp.io.floorFlags
  val mulTag = Module(new HeteroFP32MulPipe(12, "HeteroFP32MulPipeTag12")); val addTag = Module(new HeteroFP32AddPipe(12, "HeteroFP32AddPipeTag12")); val mulBit = Module(new HeteroFP32MulPipe(1, "HeteroFP32MulPipeBit1")); val addBit = Module(new HeteroFP32AddPipe(1, "HeteroFP32AddPipeBit1"))
  mulTag.io.inValid := false.B; mulTag.io.x := 0.U; mulTag.io.y := 0.U; mulTag.io.userIn := 0.U; mulTag.io.outReady := true.B
  addTag.io.inValid := false.B; addTag.io.x := 0.U; addTag.io.y := 0.U; addTag.io.userIn := 0.U; addTag.io.outReady := true.B
  mulBit.io.inValid := false.B; mulBit.io.x := 0.U; mulBit.io.y := 0.U; mulBit.io.userIn := 0.U; mulBit.io.outReady := true.B
  addBit.io.inValid := false.B; addBit.io.x := 0.U; addBit.io.y := 0.U; addBit.io.userIn := 0.U; addBit.io.outReady := true.B
  dontTouch(mulTag.io.out); dontTouch(mulTag.io.exceptionFlags); dontTouch(mulTag.io.userOut); dontTouch(addTag.io.out); dontTouch(addTag.io.exceptionFlags); dontTouch(addTag.io.userOut); dontTouch(mulBit.io.out); dontTouch(mulBit.io.exceptionFlags); dontTouch(mulBit.io.userOut); dontTouch(addBit.io.out); dontTouch(addBit.io.exceptionFlags); dontTouch(addBit.io.userOut)
}
object EmitHeteroAllPrimitives extends App { require(args.length == 1); val path = Paths.get(args(0)); val sv = ChiselStage.emitSystemVerilog(new HeteroAllPrimitives); Files.createDirectories(path.getParent); Files.writeString(path, sv, StandardCharsets.UTF_8) }
