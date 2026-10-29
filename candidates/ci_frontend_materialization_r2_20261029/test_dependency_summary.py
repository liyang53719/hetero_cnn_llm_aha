import unittest,tempfile,pathlib,json,sys,types,importlib.util
P=pathlib.Path
class T(unittest.TestCase):
 def load(self):
  # Source-only summary unit fixture; frontend/stage code is not executed.
  mods={'summarize_frontend':dict(summarize=lambda *a:{'stages':[]},encode_summary=json.dumps),'frontend_telemetry':dict(typed_metrics=lambda r:{}),'safe_diagnostics':dict(stage_diagnostics=lambda *a:{}),'build_error_samples':dict(full_build_errors=lambda *a:{},sample=lambda *a:{})}
  old={k:sys.modules.get(k)for k in mods}
  try:
   for k,v in mods.items():m=types.ModuleType(k);m.__dict__.update(v);sys.modules[k]=m
   s=importlib.util.spec_from_file_location('summary_under_test',P(__file__).with_name('summarize_build_only.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
  finally:
   for k,v in old.items():
    if v is None:sys.modules.pop(k,None)
    else:sys.modules[k]=v
 def test_export_and_reject(self):
  m=self.load()
  with tempfile.TemporaryDirectory()as d:
   root=P(d);out=root/'frontend/binary_admission';out.mkdir(parents=True);p=out/'generated_tree_failure.json'
   good=dict(schema='GENERATED_TREE_REJECTION_V1',code='UNEXPECTED_DEPENDENCY_NAME',relative_path='VChild/foreign.d',suffix='.d',bytes=123,sha256='a'*64)
   p.write_text(json.dumps(good));self.assertEqual(m.build_summary(root,'b'*40)['generated_tree_rejection']['relative_path'],'VChild/foreign.d')
   for patch in [dict(relative_path='/private/x.d'),dict(relative_path='../x.d'),dict(code='secret'),dict(bytes=2**60),dict(sha256='not-a-hash')]:
    p.write_text(json.dumps(dict(good,**patch)));self.assertNotIn('generated_tree_rejection',m.build_summary(root,'b'*40))
if __name__=='__main__':unittest.main()
