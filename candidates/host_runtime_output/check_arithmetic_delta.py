"""Read-only exact arithmetic delta; source-writing option removed."""
from pathlib import Path
import hashlib,sys
D=Path(__file__).parent/'source'
p=D/'UnifiedMoeSharedArithmeticProtocolV5.scala'
b=D.parent.parent/'host_runtime_gqa/source'/p.name
if hashlib.sha256(b.read_bytes()).hexdigest()!='d19428d909442d7f09479118ba46fe18400a6a1068f6e6a103be29ffe64a69ca':raise SystemExit('protocol base SHA mismatch')
s=b.read_text()
s=s.replace('  val Count=11','''  val OrdinaryElementwiseScalar=8;val OrdinaryElementwiseFormat=9
  val OrdinaryElementwiseStage=77
  // Only SigmoidMul (five FP32 nodes + two BF16 boundaries) and residual
  // Add (one FP32 node + one BF16 boundary); no SiLU/FFN authorization.
  // Same fixed M128/width4096 owner for every runtime profile.
  val OrdinaryElementwiseMaximumOperations=Seq(2621440,1048576)
  val Count=11''')
s=s.replace('val OrdinaryGqa=8\n','val OrdinaryGqa=8;val OrdinaryElementwise=9\n')
s=s.replace('  * authorityKind is globally four bits', '  * Elementwise kind9/stage77 uses Scalar8/Format9 with separate bounds;\n  * sigmoid and Add retain their exact runtime counts, never an inferred grant.\n  * authorityKind is globally four bits')
if s!=p.read_text():raise SystemExit('derived source differs from final source '+p.name)
print('DERIVATION_MATCH',p.name,hashlib.sha256(s.encode()).hexdigest())
p=D/'UnifiedMoeSharedArithmeticAdapterV5.scala'
b=D.parent.parent/'host_runtime_gqa/source'/p.name
if hashlib.sha256(b.read_bytes()).hexdigest()!='3c66fc90f8d20c1fb2232d8a839a64bdfef09b3160736bee5c77e6369b435fb6':raise SystemExit('adapter base SHA mismatch')
s=b.read_text()
s=s.replace('k===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U\n','k===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U ||\n      k===UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U\n')
s=s.replace('    val ordinaryGqa=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U','    val ordinaryGqa=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryGqa.U\n    val ordinaryElementwise=a.authorityKind===UnifiedArithmeticAuthorityKindV5.OrdinaryElementwise.U')
s=s.replace('else Mux(ordinaryGqa,UnifiedMoeArithmeticClientV5.OrdinaryGqaStage.U,','else Mux(ordinaryElementwise,UnifiedMoeArithmeticClientV5.OrdinaryElementwiseStage.U,\n        Mux(ordinaryGqa,UnifiedMoeArithmeticClientV5.OrdinaryGqaStage.U,')
s=s.replace('UnifiedMoeArithmeticClientV5.Stages(i).U)))))))','UnifiedMoeArithmeticClientV5.Stages(i).U))))))))')
s=s.replace('else Mux(ordinaryGqa,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U else 0.U),','else Mux(ordinaryElementwise,UnifiedMoeArithmeticClientV5.OrdinaryElementwiseMaximumOperations(i-8).U,\n        Mux(ordinaryGqa,(if(i==8) UnifiedMoeArithmeticClientV5.OrdinaryGqaMaximumOperations.U else 0.U),')
s=s.replace('UnifiedMoeArithmeticClientV5.MaximumOperations(i).U)))))))','UnifiedMoeArithmeticClientV5.MaximumOperations(i).U))))))))')
if s!=p.read_text():raise SystemExit('derived source differs from final source '+p.name)
print('DERIVATION_MATCH',p.name,hashlib.sha256(s.encode()).hexdigest())
