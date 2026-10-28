// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._

/** New private fixed-32-lane ABI. NOT wire-compatible with VectorV2 or
  * the scalar-format V3 port, NOT a host grant, and not installed in a top.
  * All five profiles use these exact types and one physical bank.
  */
object UnifiedVectorElement32PolicyV4 {
  val LegacyRaw = 0
  val Bf16MulRne = 1
  val Bf16AddRne = 2
  val RawFp32FiniteGradual = 3
  val RawFp32ToBf16Rne = 4
  val RawFp32MulBf16Rne = 5
  // 6..7 are unsupported; they still receive one tagged error completion.
}

class UnifiedVectorElement32PayloadV4 extends Bundle {
  val policy = UInt(3.W)
  val multiply = Bool()
  val a = Vec(32, UInt(32.W))
  val b = Vec(32, UInt(32.W))
}

class UnifiedVectorElement32RequestV4 extends Bundle {
  val identity = new UnifiedSharedOperationTagV3
  val payload = new UnifiedVectorElement32PayloadV4
}

class UnifiedVectorElement32ResultPayloadV4 extends Bundle {
  val policy = UInt(3.W)
  // Policies 1,2,4,5 return BF16 expanded into bits31:16, with bits15:0 zero.
  // Policies 0,3 return unmodified FP32 ALU results, not a BF16 recast.
  val value = Vec(32, UInt(32.W))
  val arithFlags = Vec(32, UInt(5.W))
  // Only ALU NV,DZ,OF,UF,NX; NEVER combined arithmetic+format flags.
  // True for0..3 and5. Pure format/unsupported policies return reserved zero.
  val arithFlagsValid = Bool()
  // Always false: the reused formatter exposes no IEEE exception flags.
  val formatFlagsValid = Bool()
  val error = Bool()
}

class UnifiedVectorElement32ResultV4 extends Bundle {
  val identity = new UnifiedSharedOperationTagV3
  val payload = new UnifiedVectorElement32ResultPayloadV4
}
