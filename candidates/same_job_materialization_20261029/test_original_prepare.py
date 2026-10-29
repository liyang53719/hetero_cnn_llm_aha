import hashlib,json,os,tempfile,unittest,argparse,sys
from pathlib import Path
from unittest.mock import patch
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,default=Path(os.environ['HETERO_REPO'])if 'HETERO_REPO'in os.environ else None);ap.add_argument('--candidate-dir',type=Path,default=Path(__file__).resolve().parent);ARGS,REST=ap.parse_known_args()
if ARGS.repo is None:ap.error('--repo is required (or explicit HETERO_REPO)')
REPO=ARGS.repo.resolve();sys.path.insert(0,str(ARGS.candidate_dir.resolve()))
import prepare as m
from acquire_profile import selected_plan
class Test(unittest.TestCase):
 def test_inventory(self):
  names=set()
  for i,(n,size) in enumerate([(12,93595648),(14,43111008),(11,36705280),(18,1685402304),(15,1672492032)]):
   p=selected_plan(REPO,i);self.assertEqual(len(p['specs']),n);self.assertEqual(sum(s['bytes'] for s in p['specs']),size)
   keys={(s['model'],s['name']) for s in p['specs']};self.assertFalse(names&keys);names|=keys
  self.assertEqual(len(names),70)
 def test_program_bytes_selected_only(self):
  for i in range(5):
   with tempfile.TemporaryDirectory() as t:
    out=Path(t)/'programs';m.programs(REPO,out,i)
    self.assertEqual(sorted(p.name for p in out.iterdir()),[] if i==0 else [f'profile{i}'])
 def test_reference_routing(self):
  for i in range(5):
   r={'site':'/out/site','wrapper':'/out/python','sidecar':{'path':'/out/side','sha256':'a'},'receipt':{'path':'/out/receipt','sha256':'b'}}
   args=list(map(str,m.reference_command(REPO,Path('/out'),{m.RUNTIME[i]:r},i,Path('/out/payload'))))
   self.assertEqual(args[args.index('--profile')+1],str(i));self.assertIn(str(REPO/'config/upstream/weight_headers'/m.MODEL[i]/'config.json'),args)
 def test_selected_materialize_control_flow(self):
  for i in range(5):
   with tempfile.TemporaryDirectory() as tmp:
    out=Path(tmp);r={'site':str(out/'site'),'wrapper':str(out/'python')}
    for k in ('receipt','sidecar'):
     p=out/k;p.write_text('{}');r[k]=m.pin(p)
    rt=out/'RUNTIMES.json';rt.write_text(json.dumps({'entries':{m.RUNTIME[i]:r},'profile':i,'selected_runtime':m.RUNTIME[i],'provider_python':r['wrapper']}));calls=[]
    def fake(argv,root,label,wall=1800):
     a=list(map(str,argv));calls.append(a)
     if label=='01_acquire':
      d=out/'payload';d.mkdir();p=selected_plan(REPO,i);(d/'SUMMARY.json').write_text(json.dumps(dict(profile=i,tensors=len(p['specs']),tensor_bytes=sum(s['bytes'] for s in p['specs']))))
     elif label.startswith('02_reference'):
      d=out/'reference_runs'/f'profile{i}'/'reference';(d/'input_only').mkdir(parents=True);(d/'input_only/hidden_storage.bin').write_bytes(b'x');(d/'RESULT.json').write_text(json.dumps(dict(complete_block_tokens=128,profile={'profile':i},exact_baseline_observer_output_equal=True)))
     elif label=='03_p0_rope':
      d=out/'rope_run/table';d.mkdir(parents=True);(d/'rope_fp32.bin').write_bytes(b'x')
     else:
      d=Path(a[a.index('--output')+1]);d.mkdir(parents=True)
      if i in (1,2,3,4):d=d/f'profile{i}';d.mkdir()
      for f in ('runtime.tsv','views.tsv','source_spec.json','RESULT.json'):(d/f).write_text('{}')
    original_sha=m.sha
    def mock_sha(p):return '4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815' if Path(p).name=='rope_fp32.bin' else original_sha(p)
    with patch.object(m,'run',fake),patch.object(m,'sha',mock_sha):m.materialize(REPO,out,rt,i)
    bundle=json.loads((out/'runtime_bundle.json').read_text());self.assertEqual([p['id'] for p in bundle['profiles']],[i]);self.assertEqual([p.name for p in (out/'references').iterdir()],[f'profile{i}'])
    for a in calls:
     if '--profile' in a:self.assertEqual(a[a.index('--profile')+1],str(i))
     if '--profiles' in a:self.assertEqual(a[a.index('--profiles')+1],str(i))
    if i==3:self.assertFalse(any('--reference-result' in a for a in calls))
 def test_provider_adaptation_only_selection(self):
  original=(REPO/'candidates/p3_p4_provider_reconstruction_20261028T2344/rebuild.py').read_text()
  new=(m.HERE/'provider_p34.py').read_text().replace("with_name('P34_DEPENDENCIES.json')","with_name('DEPENDENCIES.json')").replace("   if root=='programs' and not any(rel.startswith(f'profile{p}/') for p in a.profiles):continue\n",'')
  self.assertEqual(new,original)
  for i in range(1,5):
   dep=json.loads((m.HERE/('DEPENDENCIES.json' if i<3 else 'P34_DEPENDENCIES.json')).read_text())['programs']
   with tempfile.TemporaryDirectory() as t:
    out=Path(t)/'programs';m.programs(REPO,out,i)
    selected={k:v for k,v in dep.items() if k.startswith(f'profile{i}/')}
    self.assertEqual(len(selected),3)
    for rel,pin in selected.items():self.assertEqual(m.sha(out/rel),pin['sha256']);self.assertEqual((out/rel).stat().st_size,pin['bytes'])
 def test_pin_escape(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'x';p.write_text('x')
   with self.assertRaises(ValueError):m.verify_pin(m.pin(p),Path(t)/'other')
if __name__=='__main__':unittest.main(argv=['test_original_prepare',*REST])
