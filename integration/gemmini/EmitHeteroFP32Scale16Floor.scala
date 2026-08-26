package gemmini
import chisel3._
import chisel3.util.Cat
import circt.stage.ChiselStage
import hardfloat._
import hardfloat.consts._
import java.nio.charset.StandardCharsets
import java.nio.file.{Files,Paths}
class HeteroFP32Scale16Floor extends Module{
 val io=IO(new Bundle{val x=Input(UInt(32.W));val out=Output(UInt(16.W));val exceptionFlags=Output(UInt(8.W))})
 val mul=Module(new MulRecFN(8,24));mul.io.a:=recFNFromFN(8,24,io.x);mul.io.b:=recFNFromFN(8,24,"h41800000".U)
 mul.io.roundingMode:=round_near_even;mul.io.detectTininess:=tininess_afterRounding
 val cvt=Module(new RecFNToIN(8,24,16));cvt.io.in:=mul.io.out;cvt.io.roundingMode:=round_min;cvt.io.signedOut:=true.B
 io.out:=cvt.io.out;io.exceptionFlags:=Cat(mul.io.exceptionFlags,cvt.io.intExceptionFlags)
}
object EmitHeteroFP32Scale16Floor extends App{require(args.length==1);val p=Paths.get(args(0));val s=ChiselStage.emitSystemVerilog(new HeteroFP32Scale16Floor);Files.createDirectories(p.getParent);Files.writeString(p,s,StandardCharsets.UTF_8)}
