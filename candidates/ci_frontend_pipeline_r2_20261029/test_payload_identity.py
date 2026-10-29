import ast,pathlib,unittest,re,copy,argparse,json,tempfile
D=pathlib.Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--pipeline-dir',type=pathlib.Path,default=D);ap.add_argument('--materialization-dir',type=pathlib.Path,default=D.parent/'ci_frontend_materialization_r2_20261029');ARGS,REST=ap.parse_known_args()
P=ARGS.pipeline_dir;M=ARGS.materialization_dir
class T(unittest.TestCase):
 def setUp(self):
  self.functions=[];self.asts=[]
  for name in ('pack_frozen_artifact.py','summarize_build_only.py'):
   t=ast.parse(((P if name=='pack_frozen_artifact.py' else M)/name).read_text());f=next(x for x in t.body if isinstance(x,ast.FunctionDef)and x.name=='bounded_payload_identity');self.asts.append(ast.dump(f));ns={'re':re};exec(compile(ast.Module(body=[f],type_ignores=[]),name,'exec'),ns);self.functions.append(ns[f.name])
  self.v={k:{'sha256':'a'*64,'bytes':10}for k in ('binary','sv','driver','source_manifest','tool_manifest','build_receipt')};self.v['driver']['sha256']='20df2692d41693491f0da03fa17f21886b9375ca599c83b5b75c0994841dc45e'
 def test_exact_shared_contract(self):self.assertEqual(*self.asts)
 def test_valid_hashes_only(self):
  for f in self.functions:self.assertEqual(f(self.v,160,100),self.v)
 def test_reject_shape_paths_hash_sizes(self):
  bad=[]
  for patch in ({'path':'/private/file'},{'sha256':'secret'},{'bytes':True},{'bytes':-1},{'bytes':2**40}):
   v=copy.deepcopy(self.v);v['binary'].update(patch);bad.append(v)
  v=copy.deepcopy(self.v);v['extra']={};bad.append(v)
  v=copy.deepcopy(self.v);v.pop('driver');bad.append(v)
  v=copy.deepcopy(self.v);v['driver']['sha256']='b'*64;bad.append(v)
  for f in self.functions:
   for v in bad:
    with self.assertRaises(ValueError):f(v,160,100)
 def test_totals(self):
  for f in self.functions:
   for total,mf in [(161,100),(160,0),(2**40,100),(160,False)]:
    with self.assertRaises(ValueError):f(self.v,total,mf)
 def summary(self,identity):
  tree=ast.parse((M/'summarize_build_only.py').read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in ('bounded_payload_identity','build_summary')]
  ns={'re':re,'pathlib':pathlib,'json':json,'BUILD':[],'summarize':lambda *a:{'stages':[{'stage':'retained','native_exit':0}]}}
  exec(compile(ast.Module(body=functions,type_ignores=[]),'summary_fixture','exec'),ns)
  with tempfile.TemporaryDirectory()as d:
   root=pathlib.Path(d);(root/'frontend').mkdir();a={'manifest':{'sha256':'c'*64,'bytes':100},'files':7,'expanded_bytes':160,'scope':'ONE_SHARED_BINARY_FROZEN_NOT_UPLOADED_NOT_EXECUTED'}
   if identity is not None:a['payload_identity']=identity
   (root/'frontend/BUILD_ONLY_RESULT.json').write_text(json.dumps({'status':'PASS_BINARY_BUILD_AND_FROZEN_ARTIFACT_ONLY_NO_NUMERICS','artifact':a}))
   return ns['build_summary'](root,'d'*40)
 def test_original_missing_metadata(self):
  r=self.summary(None);self.assertTrue(r['completed']);self.assertEqual(r['artifact']['payload_identity_status'],'NOT_EXPORTED_IN_ORIGINAL_RESULT');self.assertEqual(r['stages'][0]['stage'],'retained')
 def test_new_summary_hashes_only(self):
  r=self.summary(self.v);self.assertTrue(r['completed']);self.assertEqual(r['artifact']['payload_identity'],self.v);self.assertEqual(r['artifact']['payload_identity_status'],'EXPORTED_HASHES_ONLY_NOT_DOWNLOADABLE')
 def test_invalid_summary_keeps_stage_evidence(self):
  v=copy.deepcopy(self.v);v['binary']['path']='/forbidden/private.bin';r=self.summary(v);self.assertTrue(r['completed']);self.assertEqual(r['artifact']['payload_identity_status'],'INVALID_IDENTITY_METADATA_NOT_EXPORTED');self.assertNotIn('payload_identity',r['artifact']);self.assertEqual(r['stages'][0]['native_exit'],0)
if __name__=='__main__':unittest.main(argv=['test_payload_identity',*REST])
