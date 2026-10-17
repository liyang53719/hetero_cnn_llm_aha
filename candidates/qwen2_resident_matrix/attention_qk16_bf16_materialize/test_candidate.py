"""Source contracts and independent arithmetic/reference tests, NOT RTL tests."""
import math, struct, subprocess, tempfile, unittest
from fractions import Fraction
from pathlib import Path
import prepare as p

def value(u): return struct.unpack('>f',struct.pack('>I',u))[0]
def bits(x):
 try:return struct.unpack('>I',struct.pack('>f',x))[0]
 except OverflowError:return 0xff800000 if x<0 else 0x7f800000

def rtl_helper_projection(u):
 # Direct projection of existing TensorMath.bf16Rne, not candidate hardware.
 if u&0x7f800000==0x7f800000:return (u&0xff800000)|(0x00400000 if u&0x7fffff else 0)
 return ((u+0x7fff+((u>>16)&1))&0xffff0000)

def independent_nearest(u):
 # Exact real midpoint comparison against adjacent BF16 numbers. Overflow's
 # upper endpoint is the mathematical 2^128, with ties choosing even infinity.
 sign=u&0x80000000;mag=u&0x7fffffff
 if mag>=0x7f800000:return sign|0x7f800000|(0x400000 if mag>0x7f800000 else 0)
 low=mag&0xffff0000; high=low+0x10000
 x=Fraction(value(mag));a=Fraction(value(low))
 b=Fraction(2**128) if high==0x7f800000 else Fraction(value(high))
 midpoint=(a+b)/2
 chosen=low if x<midpoint or (x==midpoint and (low>>16)%2==0) else high
 return sign|chosen

def score(parts,enabled=True):
 total=0
 for part in parts:total=bits(value(total)+value(part))
 dot=rtl_helper_projection(total) if enabled else total
 if not math.isfinite(value(dot)):return None
 scaled=bits(value(dot)*value(0x3db504f3))
 result=rtl_helper_projection(scaled) if enabled else scaled
 return result if math.isfinite(value(result)) else None

class SourceContracts(unittest.TestCase):
 def test_exact_inverse_and_default(self):
  raw=(SOURCE/p.TARGET).read_text();result=p.transform(raw)
  self.assertEqual(p.sha(raw.encode()),p.BASE_SHA)
  for old,new in reversed(p.replacements()):result=result.replace(new,old)
  self.assertEqual(result,raw) # all other controls, handshakes, storage unchanged
  self.assertIn('enablePackedQk16OfficialBf16:Boolean=false',p.transform(raw))
 def test_round_only_terminal_fold_and_score(self):
  result=p.transform((SOURCE/p.TARGET).read_text())
  self.assertEqual(result.count('materializePackedQk('),3) # definition plus 2 boundaries
  self.assertIn('when(state===st("attReduce")){calc(ScalarOp.Add,sum,acc(lane)',result)
  self.assertIn('when(F32.less(maxScore,score)){maxScore:=score}',result)
  self.assertIn('when(!TensorMath.finite(score)){packedSelectedFault:=true.B}.otherwise{commitScore()}',result)
  self.assertIn('when(packedSelectedFault){fail(Status.Numerical.U)}',result)
  self.assertIn('c.io.result.ready:=packedCommitted.get && !poisoned',result)
 def test_install_patch_matches_overlay(self):
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/p.TARGET;dest.parent.mkdir(parents=True);dest.write_bytes((SOURCE/p.TARGET).read_bytes())
   subprocess.run(["patch","--batch","--fuzz=0","-p1"],input=(p.HERE/"qk_materialize.patch").read_bytes(),cwd=tmp,check=True,capture_output=True)
   self.assertEqual(dest.read_bytes(),p.transform((SOURCE/p.TARGET).read_text()).encode())
 def test_existing_helpers(self):
  root=HELPERS/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous'
  self.assertIn('def bf(x:UInt):UInt=Cat(TensorMath.bf16Rne(x),0.U(16.W))',(root/'BlockFloat.scala').read_text())
  self.assertIn('(x +& "h7fff".U +& x(16))(31,16)',(root/'Protocol.scala').read_text())
 def test_scalar_exception_policy_unchanged(self):
  text=(HELPERS/"chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala").read_text()
  self.assertIn("(alu.io.exceptionFlags(1) && op=/=ScalarOp.MulIeeeRne.U)",text)
  self.assertNotIn("MulIeeeRne",p.transform((SOURCE/p.TARGET).read_text()))
 def test_fresh_only_and_no_double_install(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'new';p.prepare(out,source_root=SOURCE,helper_root=HELPERS,official_policy=POLICY)
   with self.assertRaises(ValueError):p.prepare(out,source_root=SOURCE,helper_root=HELPERS,official_policy=POLICY)
  with self.assertRaises(ValueError):p.transform(p.transform((SOURCE/p.TARGET).read_text()))

class DirectedReference(unittest.TestCase):
 def test_halves_sign_carry_and_overflow(self):
  cases={0x3f808000:0x3f800000,0x3f818000:0x3f820000,0xbf808000:0xbf800000,0xbf818000:0xbf820000,
   0x3fff8000:0x40000000,0xbfff8000:0xc0000000,0x7f7f7fff:0x7f7f0000,0x7f7f8000:0x7f800000,
   0xff7f8000:0xff800000,0x00008000:0,0x00018000:0x00020000,0x80008000:0x80000000}
  for raw,expected in cases.items():
   self.assertEqual(independent_nearest(raw),expected);self.assertEqual(rtl_helper_projection(raw),expected)
 def test_nonfinite_rejection(self):
  for raw in (0x7f800000,0xff800000,0x7fc00001,0xffc00001,0x7f800001,0xff800001):
   self.assertFalse(math.isfinite(value(rtl_helper_projection(raw))))
   self.assertEqual(rtl_helper_projection(raw),independent_nearest(raw))
   self.assertIsNone(score([raw]+[0]*15))
 def test_bf16_boundary_neighborhoods(self):
  # Every finite positive BF16 midpoint plus negative reflection, below/at/above.
  for top in range(0x7f80):
   for delta in (0x7fff,0x8000,0x8001):
    for sign in (0,0x80000000):
     raw=sign|(top<<16)|delta
     self.assertEqual(rtl_helper_projection(raw),independent_nearest(raw))
 def test_fold_order_and_two_boundaries(self):
  parts=[0x3f818000]+[0]*15
  actual=score(parts)
  dot=independent_nearest(parts[0]);expected=independent_nearest(bits(value(dot)*value(0x3db504f3)))
  self.assertEqual(actual,expected);self.assertNotEqual(actual,score(parts,False))
  self.assertIsNone(score([0x7f7f8000]+[0]*15)) # no publish after rounding overflow
 def test_tail_key16_and_max_order(self):
  # Causal query index16 is a full 16-key group followed by singleton key16.
  keys=[base+i for base in range(0,17,16) for i in range(min(16,17-base))]
  self.assertEqual(keys,list(range(17)))
  raw=[0x3f800001]*16+[0x3f807fff]
  rounded=[rtl_helper_projection(x) for x in raw]
  maximum=0xff800000;selected=None
  for key,x in zip(keys,rounded):
   if value(maximum)<value(x):maximum=x;selected=key
  self.assertEqual(maximum,0x3f800000);self.assertEqual(selected,0)
  self.assertEqual(max(range(17),key=lambda k:value(raw[k])),16)
  # Raw comparison before BF16 publication would incorrectly choose key16.

if __name__=='__main__':
 import argparse,sys
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--source-root',required=True,type=Path)
 parser.add_argument('--helper-root',required=True,type=Path)
 parser.add_argument('--official-policy',required=True,type=Path)
 args,rest=parser.parse_known_args()
 SOURCE=args.source_root;HELPERS=args.helper_root;POLICY=args.official_policy
 p.validate_inputs(SOURCE,HELPERS,POLICY)
 unittest.main(argv=[sys.argv[0]]+rest,verbosity=2)

