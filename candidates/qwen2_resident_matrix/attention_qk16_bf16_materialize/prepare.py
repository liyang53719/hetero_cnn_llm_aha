"""Source-only QK materialization rebase. Never touches its input closure."""
import hashlib, json, difflib
from pathlib import Path
HERE=Path(__file__).resolve().parent
TARGET='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'
BASE_SHA='4375ccf715cf408975c3e45ae595955767b824404ef8337bb260ed807527dc1e'
OUTPUT_SHA='1de7319ec20c56a86ea1fefc18af96918dde8ae97b338eb67e14b5d4322ccaa4'
def sha(b):return hashlib.sha256(b).hexdigest()
def replacements():
 return [
 ('enablePackedQk16Keys:Boolean=false) extends Module {','enablePackedQk16Keys:Boolean=false,enablePackedQk16OfficialBf16:Boolean=false) extends Module {\n  // QK-only rebase of official_bf16 materialize hooks; not the full-block policy.\n  require(!enablePackedQk16OfficialBf16 || enablePackedQk16Keys,"QK BF16 materialization requires the packed sixteen-key route")\n  private def materializePackedQk(x:UInt):UInt=if(enablePackedQk16OfficialBf16)F32.bf(x)else x'),
 ('when(lane===15.U){calc(ScalarOp.Mul,scalarValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}','when(lane===15.U){\n    val dot=materializePackedQk(scalarValue)\n    if(enablePackedQk16OfficialBf16){\n      when(!TensorMath.finite(dot)){packedSelectedFault:=true.B}\n        .otherwise{calc(ScalarOp.Mul,dot,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}\n    }else{calc(ScalarOp.Mul,scalarValue,F32.lit(1/math.sqrt(s.headDim.toDouble)),"attScore")}\n  }'),
 ('{if(enablePackedQk16Keys){packedCommitted.get:=packedSelected.get+&1.U===packedKeys};scores.write(key+packedSelected.getOrElse(0.U),scalarValue);when(F32.less(maxScore,scalarValue)){maxScore:=scalarValue};state:=st("attNextKey")}','{\n    val score=materializePackedQk(scalarValue)\n    def commitScore():Unit={if(enablePackedQk16Keys){packedCommitted.get:=packedSelected.get+&1.U===packedKeys};scores.write(key+packedSelected.getOrElse(0.U),score);when(F32.less(maxScore,score)){maxScore:=score};state:=st("attNextKey")}\n    if(enablePackedQk16OfficialBf16){\n      when(!TensorMath.finite(score)){packedSelectedFault:=true.B}.otherwise{commitScore()}\n    }else{commitScore()}\n  }')]
def transform(text):
 for old,new in replacements():
  if text.count(old)!=1:raise ValueError('expected one exact source anchor')
  text=text.replace(old,new)
 return text
def validate_inputs(source_root,helper_root,official_policy):
 source_root=Path(source_root);helper_root=Path(helper_root)
 pins=json.loads((HERE/'pins.json').read_text())
 checks=[(source_root/TARGET,pins['source'][TARGET]),(Path(official_policy),pins['official_policy_sha256'])]
 checks.extend((helper_root/name,digest) for name,digest in pins['helpers'].items())
 for path,expected in checks:
  if sha(path.read_bytes())!=expected:raise ValueError('pinned policy/helper/source drift: '+str(path))
 return source_root

def prepare(out,*,source_root,helper_root,official_policy):
 out=Path(out)
 if out.exists() or out.is_symlink():raise ValueError('fresh output required')
 source_root=validate_inputs(source_root,helper_root,official_policy)
 raw=(source_root/TARGET).read_bytes()
 if b'numericPolicy' in raw or b'materialize(' in raw:raise ValueError('already materialized core')
 result=transform(raw.decode())
 if sha(result.encode())!=OUTPUT_SHA:raise ValueError('output identity drift')
 # mkdir(exist_ok=False) enforces exclusive creation even for concurrent calls.
 out.mkdir(parents=True,exist_ok=False)
 dest=out/TARGET;dest.parent.mkdir(parents=True);dest.write_text(result)
 return {TARGET:sha(dest.read_bytes())}

def arguments():
 import argparse
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source-root',required=True,type=Path,help='Exact composed packed QK16 source root')
 parser.add_argument('--helper-root',required=True,type=Path,help='Published base tree containing unchanged BlockFloat.scala and Protocol.scala')
 parser.add_argument('--official-policy',required=True,type=Path,help='Pinned original official_bf16/chisel_policy.patch')
 parser.add_argument('--output',required=True,type=Path,help='New overlay directory; existing paths refused')
 return parser.parse_args()
if __name__=='__main__':
 args=arguments()
 print(json.dumps(prepare(args.output,source_root=args.source_root,helper_root=args.helper_root,official_policy=args.official_policy),indent=2))
