// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import chisel3.util._

/** Ordered Torch1536 square reduction. No arithmetic units: borrows the single
  * shared bank. One request in flight, single row, two 512-bit SRAM reads per
  * 32-element group. Returns sum only; original Div/eps/Sqrt/Div and both BF16
  * materializations remain in the owner. Not independently a host authority.
  */
class OrderedRms1536Reduction32 extends Module {
  val io=IO(new Bundle {
    val abort=Input(Bool());val vectorPublished=Input(Bool());val resetRequired=Output(Bool())
    val start=Flipped(Decoupled(Bool()))
    val read=Decoupled(UInt(7.W))
    val readResult=Flipped(Decoupled(Vec(16,UInt(32.W))))
    val vector=Decoupled(new UnifiedVectorElement32PayloadV4)
    val vectorResult=Flipped(Decoupled(new UnifiedVectorElement32ResultPayloadV4))
    val result=Decoupled(new Bundle {val sum=UInt(32.W);val error=Bool()})
    val drained=Output(Bool())
  })
  val idle::readLo::waitLo::readHi::waitHi::square::squareWait::add::addWait::blockFold::blockWait::residueFold::residueWait::laneFold::laneWait::done::Nil=Enum(16)
  val state=RegInit(idle)
  val block=RegInit(0.U(2.W));val term=RegInit(0.U(4.W))
  val residue=RegInit(0.U(2.W));val lane=RegInit(0.U(3.W))
  val input=Reg(Vec(32,UInt(32.W)));val products=Reg(Vec(32,UInt(32.W)))
  val partial=Reg(Vec(32,UInt(32.W)));val blocks=Reg(Vec(32,UInt(32.W)))
  val lanes=Reg(Vec(8,UInt(32.W)));val total=Reg(UInt(32.W))
  val error=RegInit(false.B)
  val aborted=RegInit(false.B);val quarantine=RegInit(false.B)
  val expectedRead=state===waitLo || state===waitHi
  val expectedVector=state===squareWait || state===addWait || state===blockWait || state===residueWait || state===laneWait
  val unknownReturn=(io.readResult.valid && !expectedRead) || (io.vectorResult.valid && !expectedVector)
  when(unknownReturn){quarantine:=true.B}
  when(io.abort && state=/=idle){aborted:=true.B}
  io.resetRequired:=quarantine || unknownReturn
  io.start.ready:=state===idle && !io.abort && !quarantine && !unknownReturn;io.drained:=state===idle && !quarantine && !unknownReturn
  io.read.valid:=state===readLo || state===readHi
  io.read.bits:=((block<<5)+(term<<1)+Mux(state===readHi,1.U,0.U))(6,0)
  io.readResult.ready:=expectedRead && !quarantine
  io.vector.valid:=state===square || state===add || state===blockFold || state===residueFold || state===laneFold
  io.vector.bits.policy:=Mux(state===square,3.U,0.U)
  io.vector.bits.multiply:=state===square
  io.vector.bits.a:=VecInit(Seq.fill(32)(0.U(32.W)))
  io.vector.bits.b:=VecInit(Seq.fill(32)(0.U(32.W)))
  when(state===square){io.vector.bits.a:=input;io.vector.bits.b:=input}
  when(state===add){io.vector.bits.a:=partial;io.vector.bits.b:=products}
  when(state===blockFold){io.vector.bits.a:=blocks;io.vector.bits.b:=partial}
  when(state===residueFold){for(i<-0 until 8){io.vector.bits.a(i):=lanes(i);io.vector.bits.b(i):=blocks((residue<<3)+i.U)}}
  when(state===laneFold){io.vector.bits.a(0):=total;io.vector.bits.b(0):=lanes(lane)}
  io.vectorResult.ready:=expectedVector && !quarantine
  io.result.valid:=state===done;io.result.bits.sum:=total;io.result.bits.error:=error
  when(io.start.fire){
    block:=0.U;term:=0.U;residue:=0.U;lane:=0.U;total:=0.U;error:=false.B;aborted:=false.B
    partial:=VecInit(Seq.fill(32)(0.U(32.W)));blocks:=VecInit(Seq.fill(32)(0.U(32.W)));lanes:=VecInit(Seq.fill(8)(0.U(32.W)));state:=readLo
  }
  when(io.read.fire){state:=Mux(state===readLo,waitLo,waitHi)}
  when(io.readResult.fire){
    when(aborted || io.abort || unknownReturn){error:=true.B;state:=done}.elsewhen(state===waitLo){for(i<-0 until 16){input(i):=io.readResult.bits(i)};state:=readHi}
      .otherwise{for(i<-0 until 16){input(i+16):=io.readResult.bits(i)};state:=square}
  }
  when(io.vector.fire){
    when(state===square){state:=squareWait}.elsewhen(state===add){state:=addWait}
      .elsewhen(state===blockFold){state:=blockWait}.elsewhen(state===residueFold){state:=residueWait}.otherwise{state:=laneWait}
  }
  when(io.vectorResult.fire){
    val r=io.vectorResult.bits
    val mul=state===squareWait
    val bad=r.error || !r.arithFlagsValid || r.formatFlagsValid || r.policy=/=Mux(mul,3.U,0.U) ||
      r.value.map(x=> !TensorMath.finite(x)).reduce(_||_) ||
      r.arithFlags.map(f=>Mux(mul,f(4,2).orR,f(4,1).orR)).reduce(_||_)
    when(bad || aborted || io.abort || unknownReturn){error:=true.B;state:=done}.otherwise{
      when(state===squareWait){products:=r.value;state:=add}
      .elsewhen(state===addWait){partial:=r.value;when(term===15.U){state:=blockFold}.otherwise{term:=term+1.U;state:=readLo}}
      .elsewhen(state===blockWait){blocks:=r.value;partial:=VecInit(Seq.fill(32)(0.U(32.W)));term:=0.U
        when(block===2.U){residue:=0.U;state:=residueFold}.otherwise{block:=block+1.U;state:=readLo}}
      .elsewhen(state===residueWait){for(i<-0 until 8){lanes(i):=r.value(i)}
        when(residue===3.U){lane:=0.U;state:=laneFold}.otherwise{residue:=residue+1.U;state:=residueFold}}
      .otherwise{total:=r.value(0);when(lane===7.U){state:=done}.otherwise{lane:=lane+1.U;state:=laneFold}}
    }
  }
  // Only the audited router can say an offer has not crossed publication.
  // Never withdraw a published/held request, including an abort+fire edge.
  when((aborted || io.abort) && io.vector.valid && !io.vectorPublished && !io.vector.fire){error:=true.B;state:=done}
  when(io.result.fire){state:=idle}
}
