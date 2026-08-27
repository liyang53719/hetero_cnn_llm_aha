package gemmini

import chisel3._
import circt.stage.ChiselStage
import hardfloat._
import hardfloat.consts._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

/** Elastic IEEE-FP32 multiply split at HardFloat's raw/round boundary. */
class HeteroFP32MulPipe(val userBits: Int, val moduleName: String) extends Module {
  require(userBits > 0)
  override def desiredName: String = moduleName
  val io = IO(new Bundle {
    val inValid = Input(Bool()); val inReady = Output(Bool())
    val x = Input(UInt(32.W)); val y = Input(UInt(32.W)); val userIn = Input(UInt(userBits.W))
    val outValid = Output(Bool()); val outReady = Input(Bool())
    val out = Output(UInt(32.W)); val exceptionFlags = Output(UInt(5.W)); val userOut = Output(UInt(userBits.W))
  })
  val raw = Module(new MulRawFN(8, 24))
  raw.io.a := rawFloatFromRecFN(8, 24, recFNFromFN(8, 24, io.x)); raw.io.b := rawFloatFromRecFN(8, 24, recFNFromFN(8, 24, io.y))
  val rawValid = RegInit(false.B); val rawValue = Reg(new RawFloat(8, 26)); val rawInvalid = Reg(Bool()); val rawUser = Reg(UInt(userBits.W))
  val round = Module(new RoundRawFNToRecFN(8, 24, 0)); round.io.invalidExc := rawInvalid; round.io.infiniteExc := false.B; round.io.in := rawValue; round.io.roundingMode := round_near_even; round.io.detectTininess := tininess_afterRounding
  val outValid = RegInit(false.B); val outValue = Reg(UInt(32.W)); val outFlags = Reg(UInt(5.W)); val outUser = Reg(UInt(userBits.W)); val outStageReady = !outValid || io.outReady; val rawStageReady = !rawValid || outStageReady
  io.inReady := rawStageReady; io.outValid := outValid; io.out := outValue; io.exceptionFlags := outFlags; io.userOut := outUser
  when(outStageReady) { outValid := rawValid; when(rawValid) { outValue := fNFromRecFN(8, 24, round.io.out); outFlags := round.io.exceptionFlags; outUser := rawUser } }
  when(rawStageReady) { rawValid := io.inValid; when(io.inValid) { rawValue := raw.io.rawOut; rawInvalid := raw.io.invalidExc; rawUser := io.userIn } }
}

/** Elastic IEEE-FP32 addition split at HardFloat's raw/round boundary. */
class HeteroFP32AddPipe(val userBits: Int, val moduleName: String) extends Module {
  require(userBits > 0)
  override def desiredName: String = moduleName
  val io = IO(new Bundle {
    val inValid = Input(Bool()); val inReady = Output(Bool())
    val x = Input(UInt(32.W)); val y = Input(UInt(32.W)); val userIn = Input(UInt(userBits.W))
    val outValid = Output(Bool()); val outReady = Input(Bool())
    val out = Output(UInt(32.W)); val exceptionFlags = Output(UInt(5.W)); val userOut = Output(UInt(userBits.W))
  })
  val raw = Module(new AddRawFN(8, 24)); raw.io.subOp := false.B; raw.io.a := rawFloatFromRecFN(8, 24, recFNFromFN(8, 24, io.x)); raw.io.b := rawFloatFromRecFN(8, 24, recFNFromFN(8, 24, io.y)); raw.io.roundingMode := round_near_even
  val rawValid = RegInit(false.B); val rawValue = Reg(new RawFloat(8, 26)); val rawInvalid = Reg(Bool()); val rawUser = Reg(UInt(userBits.W))
  val round = Module(new RoundRawFNToRecFN(8, 24, 0)); round.io.invalidExc := rawInvalid; round.io.infiniteExc := false.B; round.io.in := rawValue; round.io.roundingMode := round_near_even; round.io.detectTininess := tininess_afterRounding
  val outValid = RegInit(false.B); val outValue = Reg(UInt(32.W)); val outFlags = Reg(UInt(5.W)); val outUser = Reg(UInt(userBits.W)); val outStageReady = !outValid || io.outReady; val rawStageReady = !rawValid || outStageReady
  io.inReady := rawStageReady; io.outValid := outValid; io.out := outValue; io.exceptionFlags := outFlags; io.userOut := outUser
  when(outStageReady) { outValid := rawValid; when(rawValid) { outValue := fNFromRecFN(8, 24, round.io.out); outFlags := round.io.exceptionFlags; outUser := rawUser } }
  when(rawStageReady) { rawValid := io.inValid; when(io.inValid) { rawValue := raw.io.rawOut; rawInvalid := raw.io.invalidExc; rawUser := io.userIn } }
}

class HeteroFP32PipelineEmitTop extends Module {
  val io = IO(new Bundle { val keep = Output(Bool()) }); io.keep := false.B
  val mulTag = Module(new HeteroFP32MulPipe(12, "HeteroFP32MulPipeTag12")); val addTag = Module(new HeteroFP32AddPipe(12, "HeteroFP32AddPipeTag12")); val mulBit = Module(new HeteroFP32MulPipe(1, "HeteroFP32MulPipeBit1")); val addBit = Module(new HeteroFP32AddPipe(1, "HeteroFP32AddPipeBit1"))
  mulTag.io.inValid := false.B; mulTag.io.x := 0.U; mulTag.io.y := 0.U; mulTag.io.userIn := 0.U; mulTag.io.outReady := true.B
  addTag.io.inValid := false.B; addTag.io.x := 0.U; addTag.io.y := 0.U; addTag.io.userIn := 0.U; addTag.io.outReady := true.B
  mulBit.io.inValid := false.B; mulBit.io.x := 0.U; mulBit.io.y := 0.U; mulBit.io.userIn := 0.U; mulBit.io.outReady := true.B
  addBit.io.inValid := false.B; addBit.io.x := 0.U; addBit.io.y := 0.U; addBit.io.userIn := 0.U; addBit.io.outReady := true.B
  dontTouch(mulTag.io.out); dontTouch(mulTag.io.exceptionFlags); dontTouch(mulTag.io.userOut); dontTouch(addTag.io.out); dontTouch(addTag.io.exceptionFlags); dontTouch(addTag.io.userOut); dontTouch(mulBit.io.out); dontTouch(mulBit.io.exceptionFlags); dontTouch(mulBit.io.userOut); dontTouch(addBit.io.out); dontTouch(addBit.io.exceptionFlags); dontTouch(addBit.io.userOut)
}
object EmitHeteroFP32Pipelines extends App { require(args.length == 1); val output = Paths.get(args(0)); val sv = ChiselStage.emitSystemVerilog(new HeteroFP32PipelineEmitTop); Files.createDirectories(output.getParent); Files.writeString(output, sv, StandardCharsets.UTF_8) }
