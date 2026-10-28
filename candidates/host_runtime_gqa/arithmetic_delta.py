#!/usr/bin/env python3
"""Read-only expected Scalar8 authority delta for tests; no file-writing entrypoint."""
from pathlib import Path
import hashlib
C=Path(__file__).resolve().parent
B=C.parent/'host_runtime_rope/source'
PINS={
 'UnifiedMoeSharedArithmeticProtocolV5.scala':'24867c503bbb4667cbca04c86fe3cab72457057a7e969687be02e40e779c8107',
 'UnifiedMoeSharedArithmeticAdapterV5.scala':'af46201ea735ee0622bf20e863ceb1ee9e1c46e6a63d10e09e8c5e9f37f53a97',
}
def change(s,a,b):
 if s.count(a)!=1: raise ValueError('nonunique exact anchor '+a)
 return s.replace(a,b)
def expected(name,s):
 if name.endswith('ProtocolV5.scala'):
  s=change(s,'  val OrdinaryRopeMaximumOperations=393216\n','  val OrdinaryRopeMaximumOperations=393216\n  val OrdinaryGqaScalar=8\n  val OrdinaryGqaStage=76\n  // Exact success count is six actual Scalar operations for EVERY score.\n  // Fixed owner capacities M128/C256/Q16 bound this separate authority domain.\n  // The first Commands route is colder/narrower (M128/C128), not a new cap.\n  val OrdinaryGqaMaximumOperations=3145728\n')
  s=change(s,'val OrdinaryRope=7\n','val OrdinaryRope=7;val OrdinaryGqa=8\n')
  s=change(s,'  * Scalar8 ONLY, never Format9 or Vector10; neither widens another bound.','  * Scalar8 ONLY, never Format9 or Vector10; neither widens another bound.\n  * GQA kind8/stage76 also uses ONLY Scalar8 and its separate six-per-score cap.\n  * authorityKind is globally four bits in this shared Bundle for ALL profiles;\n  * old kinds0..7 retain their values. This adds metadata/register bits, not a\n  * numerical client, arithmetic bank, FPU or authority alias to kind7/RoPE.')
  s=change(s,'  val authorityKind=UInt(3.W)','  val authorityKind=UInt(4.W)')
 else:
  s=change(s,'      k===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U\n','      k===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U ||\n      k===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U\n')
  s=change(s,'    val ordinaryRope=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U\n','    val ordinaryRope=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryRope.U\n    val ordinaryGqa=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U\n')
  s=change(s,'else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm && !ordinaryRope\n','else if(i==9) ordinaryKind(a.authorityKind) && !ordinaryChunk && !ordinaryQkNorm && !ordinaryRope && !ordinaryGqa\n')
  s=change(s,'      else Mux(ordinaryRope,UnifiedMoeArithmeticClientV5.OrdinaryRopeStage.U,','      else Mux(ordinaryGqa,UnifiedMoeArithmeticClientV5.OrdinaryGqaStage.U,\n        Mux(ordinaryRope,UnifiedMoeArithmeticClientV5.OrdinaryRopeStage.U,')
  s=change(s,'UnifiedMoeArithmeticClientV5.Stages(i).U))))))','UnifiedMoeArithmeticClientV5.Stages(i).U)))))))')
  s=change(s,'    // Do not enlarge Norm, Conv, RawPrep, QKNorm or any other count domain.','    // Do not enlarge Norm, Conv, RawPrep, QKNorm, RoPE or any other count domain.')
  s=change(s,'      else Mux(ordinaryRope,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryRopeMaximumOperations.U else 0.U),','      else Mux(ordinaryGqa,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U else 0.U),\n        Mux(ordinaryRope,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryRopeMaximumOperations.U else 0.U),')
  s=change(s,'UnifiedMoeArithmeticClientV5.MaximumOperations(i).U))))))','UnifiedMoeArithmeticClientV5.MaximumOperations(i).U)))))))')
 return s
