"""Source-contract tests only; no Chisel constructor execution or RTL simulation."""
import argparse,json,re,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
import prepare as p
P='chisel/continuous_prefill/src/main/scala/heteronpu/continuous/'
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.out=Path(self.tmp.name)/'overlay'
  p.prepare(SOURCE,FRAGMENT,self.out)
 def text(self,n):return (self.out/P/n).read_text()
 def test_exact_output_and_inverse(self):
  pins,edits=p.load()
  for n,rs in edits.items():
   t=(self.out/n).read_text();self.assertEqual(p.sha(t.encode()),pins['outputs'][n])
   for a,b in reversed(rs):self.assertEqual(t.count(b),1);t=t.replace(b,a)
   self.assertEqual(t,(SOURCE/n).read_text())
 def test_packed_transport_unchanged(self):
  t=self.text('QwenOwnerProtocol.scala');old=(SOURCE/P/'QwenOwnerProtocol.scala').read_text()
  self.assertEqual(t.split('    val matrix=')[1],old.split('    val matrix=')[1])
  self.assertIn('new MatrixPipelineService(enablePackedDrainStatus=enablePackedQk16Keys)',t)
  self.assertIn('core.io.packedQkStepsDrained.get:=matrix.io.packedStepsDrained.get',t)
 def test_fragment_unchanged(self):
  self.assertEqual((self.out/P/'Qwen2Block.scala').read_bytes(),(FRAGMENT/P/'Qwen2Block.scala').read_bytes())
 def test_defaults_and_forwarding(self):
  for name,classes in [('HostBlockTop.scala',['HostBlockTop','HostBlockCollection']),('QwenOwnerProtocol.scala',['QwenOwnerKernel'])]:
   t=self.text(name)
   for c in classes:
    line=next(l for l in t.splitlines() if l.startswith('class '+c+'('))
    self.assertTrue(line.endswith(',enablePackedQk16Keys:Boolean=false,enablePackedQk16OfficialBf16:Boolean=false) extends Module {'))
  for name,callee in [('HostBlockTop.scala','QwenOwnerKernel'),('HostBlockTop.scala','HostBlockTop'),('QwenOwnerProtocol.scala','Qwen2ContinuousBlock')]:
   lines=[l for l in self.text(name).splitlines() if 'new '+callee+'(' in l and 'enablePackedQk16Keys=' in l]
   self.assertEqual(len(lines),1)
   self.assertIn('enablePackedQk16Keys=enablePackedQk16Keys,enablePackedQk16OfficialBf16=enablePackedQk16OfficialBf16',lines[0])
 def test_nonpipelined_owner_unchanged(self):
  t=self.text('QwenOwnerProtocol.scala');original=(SOURCE/P/'QwenOwnerProtocol.scala').read_text()
  self.assertEqual(t.split('  if(!pipelined){')[1].split('  }else{')[0],original.split('  if(!pipelined){')[1].split('  }else{')[0])
 def test_original_emitters_unchanged(self):
  self.assertEqual(self.text('HostBlockTop.scala').split('object EmitHostBlock extends App {')[1],(SOURCE/P/'HostBlockTop.scala').read_text().split('object EmitHostBlock extends App {')[1])
 def test_guard_actual_expression_projection(self):
  # Evaluate exact Scala Boolean guard text with syntax-only translation.
  # This is not execution of require during Chisel elaboration.
  baseline=dict(pipelined=True,enablePackedQk16Keys=True,enablePackedQk16OfficialBf16=True,bf16AttentionCore=False,bf16Gdn=False,bf16QkNormRope=False,enableH2048RmsBorrower=False)
  shape=dict(retainedMatrix=True,matrixColumns=256,hidden=1536,ffn=8960,heads=12,kvHeads=2,headDim=128,nativeProfile=False,maxTokens=128)
  for name in ['HostBlockTop.scala','QwenOwnerProtocol.scala']:
   t=self.text(name)
   guards=re.findall(r'require\((!enablePackedQk16[^\n]+?),\s*(?:\n\s*)?"',t)
   self.assertEqual(len(guards),3 if name=='QwenOwnerProtocol.scala' else 2)
   def admitted(flags=None,changes=None):
    env={**baseline,**(flags or {}),'s':SimpleNamespace(**{**shape,**(changes or {})})}
    return all(eval(g.replace('&&',' and ').replace('||',' or ').replace('!',' not '),{'__builtins__':{}},env) for g in guards)
   self.assertTrue(admitted())
   for m in [1,15,16,127,128]:self.assertTrue(admitted(changes={'maxTokens':m}))
   for m in [0,129,1024]:self.assertFalse(admitted(changes={'maxTokens':m}))
   self.assertFalse(admitted({'pipelined':False}))
   if name=='QwenOwnerProtocol.scala':
    for flag in ['bf16AttentionCore','bf16Gdn','bf16QkNormRope','enableH2048RmsBorrower']:self.assertFalse(admitted({flag:True}))
   self.assertFalse(admitted({'enablePackedQk16Keys':False}))
   self.assertTrue(admitted({'enablePackedQk16OfficialBf16':False}))
   self.assertTrue(admitted({'enablePackedQk16OfficialBf16':False},{'ffn':3584}))
   for key,value in dict(retainedMatrix=False,matrixColumns=32,hidden=1024,ffn=3584,heads=8,kvHeads=1,headDim=256,nativeProfile=True).items():
    self.assertFalse(admitted(changes={key:value}),key)
   self.assertTrue(admitted({'pipelined':False,'enablePackedQk16Keys':False,'enablePackedQk16OfficialBf16':False},{'maxTokens':1024}))
 def test_overwrite_rejected(self):
  with self.assertRaises(ValueError):p.prepare(SOURCE,FRAGMENT,self.out)
 def test_symlink_rejected(self):
  dest=Path(self.tmp.name)/'dangling';dest.symlink_to(Path(self.tmp.name)/'missing')
  with self.assertRaises(ValueError):p.prepare(SOURCE,FRAGMENT,dest)
 def test_drift_no_output(self):
  dest=Path(self.tmp.name)/'new'
  with self.assertRaises(ValueError):p.prepare(self.out,FRAGMENT,dest)
  self.assertFalse(dest.exists())
 def test_patch_exact_replay(self):
  import shutil
  target=Path(self.tmp.name)/'patch';target.mkdir()
  pins,_=p.load()
  for n in pins['inputs']:
   f=target/n;f.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/n,f)
  run=subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(p.HERE/'selection.patch')],cwd=target,capture_output=True)
  self.assertEqual(run.returncode,0,run.stderr)
  for n,h in pins['outputs'].items():self.assertEqual(p.sha((target/n).read_bytes()),h)
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--fragment-root',type=Path,required=True)
 a,rest=parser.parse_known_args();SOURCE=a.source_root.resolve();FRAGMENT=a.fragment_root.resolve()
 unittest.main(argv=['test_candidate.py']+rest)
