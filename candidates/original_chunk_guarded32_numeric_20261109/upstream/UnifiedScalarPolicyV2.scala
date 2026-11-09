// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous
import chisel3._
/** Request policy is scheduler-selected and latched on fire, never a model
  * elaboration parameter. Other opcode/policy combinations are errors. */
object UnifiedScalarPolicyV2 {val Legacy=0;val GradualDecay=1;val DualInnerSoftplus=2;val Reserved=3}
class UnifiedScalarRequestV2 extends Bundle {val policy=UInt(2.W);val payload=new ScalarRequest}
class UnifiedScalarResultV2 extends Bundle {
  val policy=UInt(2.W);val value=UInt(32.W);val flags=UInt(5.W)
  val primitiveFlagsValid=Bool();val error=Bool()
}
/** Direction is from an arithmetic owner toward the one shared primitive. */
class UnifiedScalarClientV2 extends Bundle {
  val request=chisel3.util.Decoupled(new UnifiedScalarRequestV2)
  val result=Flipped(chisel3.util.Decoupled(new UnifiedScalarResultV2))
}
