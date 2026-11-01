"""Synthetic bytes and mocked loader only. No ELF/loader/subprocess execution."""
import importlib.util,json,pathlib,struct,tempfile,types,unittest
from unittest.mock import patch
D=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('workspace_abi_test',D/'runtime_abi_owned.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('workspace_abi_contract',D/'workspace_loader.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class Tests(unittest.TestCase):
 def setUp(self):m._WORKSPACE_LOADER_BINDING=None;m._OWNED_ENV_BINDING=None
 def test_synthetic_dso_zero_interp_zero_needed_not_binary(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'synthetic';raw=bytearray(512);raw[:16]=b'\x7fELF\x02\x01\x01'+bytes(9);raw[16:64]=struct.pack('<HHIQQQIHHHHHH',3,62,1,0,64,0,0,64,56,2,0,0,0)
   raw[64:120]=struct.pack('<IIQQQQQQ',1,4,0,0,0,512,512,4096);raw[120:176]=struct.pack('<IIQQQQQQ',2,4,256,256,256,48,48,8)
   raw[256:304]=struct.pack('<qQqQqQ',5,400,10,1,0,0);p.write_bytes(raw)
   self.assertEqual(m.elf_info(p,require_interpreter=False)['needed'],[])
   with self.assertRaises(ValueError):m.elf_info(p)
   raw[256:304]=struct.pack('<qQqQqQ',29,400,10,1,0,0);p.write_bytes(raw)
   with self.assertRaises(ValueError):m.elf_info(p,require_interpreter=False)
 def fixture(self,root):
  b=root/'dut';b.write_text('synthetic non executable');tool=root/'tools';tool.write_text('{}');libs={}
  for n in sorted(w.SONAMES):
   p=root/n;p.write_text('synthetic '+n);v=m.pin(p);libs[n]=dict(v,original_resolved='/usr/lib/x86_64-linux-gnu/'+n)
  v=dict(manifest={'path':str(root/'contract'),'bytes':2,'sha256':'a'*64},root=str(root),loader=libs['ld-linux-x86-64.so.2'],libraries=libs,elf={'interpreter':'/lib64/ld-linux-x86-64.so.2','needed':sorted(w.SONAMES),'machine':'ELF64_LE_X86_64'},builder_source_commit='b'*40,artifact_manifest_sha256='c'*64)
  text='linux-vdso.so.1 (0x1)\n'+''.join(n+' => '+libs[n]['path']+' (0x2)\n'for n in sorted(libs));return b,tool,v,text
 def test_workspace_receipt_and_prepost_no_fallback(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);b,tool,v,text=self.fixture(root);out=root/'ABI.json';env={'TMPDIR':t};owned={'sha256':'d'*64};m._WORKSPACE_LOADER_BINDING=('synthetic','a'*64,'b'*40,'c'*64)
   with patch.object(m,'workspace_verified',return_value=(w,v))as verified,patch.object(m,'_list',return_value=text)as listing,patch.object(m,'config_pins',return_value={}),patch.object(m,'clean_env',return_value=env),patch.object(m,'owned_environment_pin',return_value=owned):
    r=m.prepare(b,m.sha(b),tool,m.sha(tool),out);self.assertEqual(verified.call_count,2);self.assertEqual(listing.call_args.args,(v['loader']['resolved'],b,w.prefix(v)));self.assertEqual(r['workspace_loader'],v['manifest'])
    result=m.verify(out,m.sha(out),b,m.sha(b),tool,m.sha(tool));self.assertEqual(result['libraries'],6);self.assertEqual(result['status'],'PASS_STARTUP_ABI_IDENTITY_ONLY')
    r['libraries']['libc.so.6']['path']='/usr/lib/x86_64-linux-gnu/libc.so.6';out.write_text(json.dumps(r))
    with self.assertRaises((ValueError,OSError)):m.verify(out,m.sha(out),b,m.sha(b),tool,m.sha(tool))
 def test_missing_actual_resolved_object_rejected(self):
  with tempfile.TemporaryDirectory()as t:
   b,tool,v,text=self.fixture(pathlib.Path(t));parsed=m.parse_list(text);del parsed['libm.so.6']
   with self.assertRaises(ValueError):w.resolved_libraries(parsed,v,m.pin)
 def test_prepost_closure_drift_refused(self):
  with tempfile.TemporaryDirectory()as t:
   root=pathlib.Path(t);b,tool,v,text=self.fixture(root);changed=dict(v,artifact_manifest_sha256='e'*64)
   with patch.object(m,'workspace_verified',side_effect=[(w,v),(w,changed)]),patch.object(m,'_list',return_value=text),patch.object(m,'config_pins',return_value={}),patch.object(m,'clean_env',return_value={}),patch.object(m,'owned_environment_pin',return_value={}):
    with self.assertRaises(ValueError):m.prepare_workspace(b,m.sha(b),tool,m.sha(tool),root/'out')
 def test_execution_argv_legacy_and_workspace_revalidate(self):
  self.assertEqual(m.execution_argv('/dut','/runtime','/out',123),['/dut','/runtime','/out','123'])
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'contract';p.write_text('{}');m._WORKSPACE_LOADER_BINDING=(str(p),'a'*64,'b'*40,'c'*64);fake=types.SimpleNamespace(read=lambda c:{'binary':{'sha256':'d'*64},'tool_manifest':{'path':'/tools','sha256':'e'*64}},prefix=lambda v:['/private/ld','--inhibit-cache','--library-path','/private'])
   with patch.object(m,'workspace_module',return_value=fake),patch.object(m,'workspace_verified',return_value=(fake,{}))as verifier:
    self.assertEqual(m.execution_argv('/dut','/runtime','/out',123),['/private/ld','--inhibit-cache','--library-path','/private','/dut','/runtime','/out','123']);verifier.assert_called_once_with('/dut','d'*64,'/tools','e'*64)
 def test_immutable_workspace_config(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'contract';p.write_text('{}');fake=types.SimpleNamespace(read=lambda c:{'builder_source_commit':'b'*40,'artifact_manifest_sha256':'c'*64})
   with patch.object(m,'workspace_module',return_value=fake):
    m.configure_workspace_loader(p,'a'*64,'b'*40,'c'*64)
    with self.assertRaises(ValueError):m.configure_workspace_loader(p,'d'*64,'b'*40,'c'*64)
 def test_cli_partial_pin_refused_before_environment(self):
  a=types.SimpleNamespace(expected_run_id=1,expected_source_commit='a'*40,expected_launch_commit='b'*40,workspace_loader=pathlib.Path('/contract'),workspace_loader_sha256=None,executor_adaptation=None,executor_adaptation_sha256=None,artifact_manifest_sha256=None)
  with patch.object(m,'configure_owned_environment')as environment:
   with self.assertRaises(ValueError):m.configure_cli(a)
   environment.assert_not_called()
 def test_list_mock_exact_prefix_and_no_inherited_env(self):
  with tempfile.TemporaryDirectory()as t:
   def fake(argv,**kw):
    self.assertEqual(argv,['/private/ld','--inhibit-cache','--library-path','/private','--list','/dut']);self.assertEqual(kw['env'],{'TMPDIR':t});self.assertTrue(callable(kw['preexec_fn']));kw['stdout'].write(b'synthetic listing')
    return types.SimpleNamespace(wait=lambda timeout:None,poll=lambda:0,returncode=0)
   with patch.object(m,'clean_env',return_value={'TMPDIR':t}),patch.object(m.subprocess,'Popen',side_effect=fake):self.assertEqual(m._list('/private/ld','/dut',['/private/ld','--inhibit-cache','--library-path','/private']),'synthetic listing')
 def test_legacy_identity_mismatch_requires_adapter(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'identity';p.write_text(json.dumps({'source_commit':'d'*40}))
   a=types.SimpleNamespace(expected_run_id=1,expected_source_commit='a'*40,expected_launch_commit='b'*40,executor_identity=p,executor_identity_sha256=m.sha(p),workspace_loader=None,workspace_loader_sha256=None,executor_adaptation=None,executor_adaptation_sha256=None,artifact_manifest_sha256=None)
   with patch.object(m,'configure_owned_environment')as environment:
    with self.assertRaisesRegex(ValueError,'without adaptation'):m.configure_cli(a)
    environment.assert_not_called()
 def test_actual_workspace_helper_source_lock(self):
  self.assertEqual(m.WORKSPACE_HELPER_SHA256,m.sha(D/'workspace_loader.py'));self.assertTrue(callable(m.workspace_module().verify))
 def test_untrusted_handoff_checker_refused_before_compile(self):
  self.assertEqual(m.HANDOFF_HELPER_SHA256,m.sha(D/'artifact_handoff.py'))
  with patch.object(m.P,'read_bytes',return_value=b'raise RuntimeError("UNTRUSTED SOURCE EXECUTED")'),patch('builtins.compile',side_effect=AssertionError('must reject before compile')):
   with self.assertRaisesRegex(ValueError,'before import'):m.adaptation_checker({'path':'/irrelevant','bytes':1,'sha256':'a'*64})
 def test_invalid_external_adapter_pin_refused(self):
  with tempfile.TemporaryDirectory()as t:
   p=pathlib.Path(t)/'adaptation';p.write_text('{}')
   with self.assertRaises(ValueError):m.adaptation_checker({'path':str(p),'bytes':p.stat().st_size,'sha256':'0'*64})
if __name__=='__main__':unittest.main()
