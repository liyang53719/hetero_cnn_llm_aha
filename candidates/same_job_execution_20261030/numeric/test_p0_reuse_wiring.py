"""Small synthetic two-root metadata tests; no real weights or DUT."""
import ast,hashlib,importlib.util,json,pathlib,tempfile,types,unittest
from unittest import mock
D=pathlib.Path(__file__).resolve().parent
EMITTER_BASE_SHA='fe08d00c8a06a15c2fb734e1b637e09f96fe651a6cfb5d05fc8b5b0b3c323ec6'
def need(v,m):
 if not v:raise ValueError(m)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class ReuseWiring(unittest.TestCase):
 def test_original_emitter_all_bytes_reverse_exact(self):
  text=(D/'emit_reused_p0_tsv.py').read_text()
  text=text.replace('import argparse,json,hashlib,importlib.util','import argparse,json,hashlib')
  added="def verified_input_root(a):\n # The core revalidates the separately pinned reuse contract and fresh metadata.\n path=Path(__file__).resolve().with_name('p0_provider_data_reuse.py')\n spec=importlib.util.spec_from_file_location('pinned_p0_input_reuse',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n return Path(module.verify_materialized(a.reuse_binding,a.reuse_binding_sha256,a.provider))\n\n"
  self.assertEqual(text.count(added),1);text=text.replace(added,'')
  self.assertEqual(text.count(' input_root=verified_input_root(a)\n'),1);text=text.replace(' input_root=verified_input_root(a)\n','')
  self.assertEqual(text.count("input_root/(name+'.bin')"),1);text=text.replace("input_root/(name+'.bin')","root/'input_only'/(name+'.bin')")
  extra="p.add_argument('--reuse-binding',type=Path,required=True);p.add_argument('--reuse-binding-sha256',required=True);"
  self.assertEqual(text.count(extra),1);text=text.replace(extra,'')
  self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),EMITTER_BASE_SHA)
 def test_real_emit_algorithm_two_roots_small_input(self):
  tree=ast.parse((D/'emit_reused_p0_tsv.py').read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in('sha','run')]
  with tempfile.TemporaryDirectory()as td:
   root=pathlib.Path(td);old=root/'closed_input';old.mkdir();fresh=root/'new_provider';fresh.mkdir();(fresh/'program').mkdir();out=root/'transport'
   (old/'x.bin').write_bytes(bytes(range(128)));(fresh/'program/host_commands.bin').write_bytes(bytes(range(64)));(fresh/'program/host_descriptors.bin').write_bytes(bytes(range(64)))
   m=dict(commandBase=0,commandLimit=64,commands=1,descriptorBase=64,descriptorLimit=128,descriptors=1,base=0,metadataLimit=128,scratchBase=1024,limit=4096,allocations=['x'],tensors={'x':dict(storage_bytes=128,words=32,address=128,readonly=True,virtual=False)},schedule=[])
   (fresh/'program/manifest.json').write_text(json.dumps(m));(fresh/'source_manifest.json').write_text(json.dumps({'sources':[]}))
   a=types.SimpleNamespace(provider=fresh,output=out,payload=root)
   ns=dict(Path=pathlib.Path,json=json,hashlib=hashlib,verified_input_root=lambda args:old)
   exec(compile(ast.Module(body=functions,type_ignores=[]),'real_emitter_functions','exec'),ns);ns['run'](a)
   rows=[line.split('\t')for line in(out/'views.tsv').read_text().splitlines()[1:]]
   self.assertEqual([pathlib.Path(r[8])for r in rows],[fresh/'program/host_commands.bin',fresh/'program/host_descriptors.bin',old/'x.bin'])
   self.assertFalse((fresh/'input_only').exists());self.assertTrue((out/'PRIVATE_PROBES.tsv').stat().st_size>0)
   report=json.loads((out/'MANIFEST.json').read_text());self.assertTrue(report['no_reference_outputs']);self.assertFalse(report['rw_preloaded'])
 def test_provider_branch_uses_only_pinned_helpers_and_binding(self):
  with tempfile.TemporaryDirectory()as td:
   root=pathlib.Path(td).resolve();numeric=root/'numeric';numeric.mkdir();(numeric/'provider_from_frozen.py').write_bytes((D/'provider_from_frozen.py').read_bytes())
   for name in('p0_provider_data_reuse.py','emit_reused_p0_tsv.py'):(numeric/name).write_text('# Synthetic source-pin target, stage callback does not execute it.\n')
   p=load('reuse_provider_actual',numeric/'provider_from_frozen.py')
   repo=root/'repo';materializer=repo/'materializer';materializer.mkdir(parents=True);(materializer/'prepare.py').write_text('')
   out=root/'new';out.mkdir();(out/'reference').mkdir();ref=out/'reference/RESULT.json';ref.write_text('{}');reference=p.pin(ref);(out/'INITIALIZED.json').write_text(json.dumps(dict(profile=0,reference=reference)))
   binding=root/'reuse.json';binding.write_text('{}');reuse=p.pin(binding);calls=[]
   sourcepins={str(materializer/'prepare.py'):p.sha(materializer/'prepare.py')}
   for name in('p0_provider_data_reuse.py','emit_reused_p0_tsv.py'):
    helper=numeric/name
    sourcepins[str(helper)]=p.sha(helper)
   def stage(name,argv):
    calls.append((name,argv))
    if name=='p0_provider':
     (out/'p0_provider').mkdir();(out/'p0_provider/RESULT.json').write_text('{}')
    if name=='p0_transport':
     (out/'p0_transport').mkdir()
     for fn in('runtime.tsv','views.tsv'):(out/'p0_transport'/fn).write_text('fixture')
   p.prepare(repo,materializer,out,0,'python',root,reference,stage,sourcepins,p0_provider_reuse=reuse)
   self.assertEqual([x[0]for x in calls],['p0_provider','p0_transport']);self.assertIn(str(binding),calls[0][1]);self.assertIn(reuse['sha256'],calls[1][1]);self.assertFalse((out/'rope').exists())
if __name__=='__main__':unittest.main()
