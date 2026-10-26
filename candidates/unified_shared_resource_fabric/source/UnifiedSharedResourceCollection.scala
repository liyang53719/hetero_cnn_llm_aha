// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
import gemmini.{HeteroBF16FmaPre,HeteroBF16FmaMul,HeteroBF16FmaPost,HeteroBF16FmaRound}

/** Namespace emission container ONLY, never a product/synthesis/simulation top.
  * All five runtime profiles use the single UnifiedSharedResourceTop child and
  * exactly the same generated artifact. There is no model argument or branch.
  * Four siblings provide the original FMA module ABI for external retained
  * endpoints; hierarchy rooted at UnifiedSharedResourceTop excludes siblings.
  * Never combine a separately emitted old Qwen2 core with this namespace.
  */
class UnifiedSharedResourceCollection extends Module {
  val top=Module(new UnifiedSharedResourceTop)
  val port=IO(chiselTypeOf(top.io));port<>top.io;dontTouch(port)
  val pre=Module(new HeteroBF16FmaPre);val prePort=IO(chiselTypeOf(pre.io));prePort<>pre.io;dontTouch(prePort)
  val mul=Module(new HeteroBF16FmaMul);val mulPort=IO(chiselTypeOf(mul.io));mulPort<>mul.io;dontTouch(mulPort)
  val post=Module(new HeteroBF16FmaPost);val postPort=IO(chiselTypeOf(post.io));postPort<>post.io;dontTouch(postPort)
  val round=Module(new HeteroBF16FmaRound);val roundPort=IO(chiselTypeOf(round.io));roundPort<>round.io;dontTouch(roundPort)
}
