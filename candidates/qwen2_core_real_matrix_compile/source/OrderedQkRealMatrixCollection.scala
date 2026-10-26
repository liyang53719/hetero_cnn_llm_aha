// Source candidate only: no emitter/main and no automatic elaboration.
package heteronpu.continuous
import chisel3._
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}

/** Common emission namespace, NOT the future simulation/resource top.
  * The selected future top is OrderedQkRealMatrixCore. The four siblings below
  * provide original FMA ABI definitions for retained external endpoint RTL.
  * They are not four additional datapaths inside the selected core hierarchy.
  * Emit once together: separately emitted HardFloat helpers may share names
  * while having incompatible interfaces. Never rename/edit their generated SV.
  */
class OrderedQkRealMatrixCollection extends Module {
  val top=Module(new OrderedQkRealMatrixCore)
  val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val observation=IO(Output(chiselTypeOf(top.observation)))
  observation:=top.observation;dontTouch(observation)
  val scoreWrite=IO(Output(chiselTypeOf(top.scoreWrite)))
  scoreWrite:=top.scoreWrite;dontTouch(scoreWrite)
  val pre=Module(new HeteroBF16FmaPre);val prePort=IO(chiselTypeOf(pre.io));prePort<>pre.io;dontTouch(prePort)
  val mul=Module(new HeteroBF16FmaMul);val mulPort=IO(chiselTypeOf(mul.io));mulPort<>mul.io;dontTouch(mulPort)
  val post=Module(new HeteroBF16FmaPost);val postPort=IO(chiselTypeOf(post.io));postPort<>post.io;dontTouch(postPort)
  val round=Module(new HeteroBF16FmaRound);val roundPort=IO(chiselTypeOf(round.io));roundPort<>round.io;dontTouch(roundPort)
}
