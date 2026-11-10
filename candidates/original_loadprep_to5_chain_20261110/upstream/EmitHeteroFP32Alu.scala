package gemmini
import chisel3._
import circt.stage.ChiselStage
import hardfloat._
import hardfloat.consts._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths}
class HeteroFP32Alu extends Module{
  val io=IO(new Bundle{val op=Input(Bool());val x=Input(UInt(32.W));val y=Input(UInt(32.W));
    val out=Output(UInt(32.W));val exceptionFlags=Output(UInt(5.W))})
  val xr=recFNFromFN(8,24,io.x);val yr=recFNFromFN(8,24,io.y)
  val add=Module(new AddRecFN(8,24));add.io.subOp:=false.B;add.io.a:=xr;add.io.b:=yr
  add.io.roundingMode:=round_near_even;add.io.detectTininess:=tininess_afterRounding
  val mul=Module(new MulRecFN(8,24));mul.io.a:=xr;mul.io.b:=yr
  mul.io.roundingMode:=round_near_even;mul.io.detectTininess:=tininess_afterRounding
  io.out:=fNFromRecFN(8,24,Mux(io.op,mul.io.out,add.io.out))
  io.exceptionFlags:=Mux(io.op,mul.io.exceptionFlags,add.io.exceptionFlags)
}
object EmitHeteroFP32Alu extends App{require(args.length==1);val p=Paths.get(args(0));val s=ChiselStage.emitSystemVerilog(new HeteroFP32Alu)
  Files.createDirectories(p.getParent);Files.writeString(p,s,StandardCharsets.UTF_8)}
