"""Cold admission and metadata tests. They never launch RTL or numerical work."""
import hashlib,json,sys,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(Path(__file__).resolve().parent)]
import generate_contract as g
import run_control as r

class Public21DispatchContractTests(unittest.TestCase):
    def setUp(self):self.f=g.make_qwen2_21_fixture(16)
    def make_gate(self,root):
        entries=[g.generate(m,e,a,root/name) for m,e,a,name in ((16,7,0,'m16'),(128,8,0,'m128'),(16,9,0x10000000000000,'m16_relocated'))]
        (root/'gate.json').write_text(json.dumps(dict(scope='METADATA_CONTROL_ONLY',arithmetic_executed=False,
            fixtures=entries,source_sha256=g.PINS['source_sha256'])))
        return hashlib.sha256((root/'gate.json').read_bytes()).hexdigest()
    def test_current_19_and_resident_17_have_complete_distinct_coverage(self):
        for enabled,count in ((False,19),(True,17)):
            jobs,events,result=g.contracts(g.make_qwen2_21_fixture(16),enabled)
            self.assertEqual(len(jobs),count);self.assertEqual(result['jobs'],count)
            self.assertEqual([e['pc'] for e in events],list(range(21)))
            self.assertEqual([p for j in jobs for p in j['public_pcs']],list(range(21)))
            self.assertEqual([e['signal'] for e in events],list(range(1,22)))
    def test_m128_complete_geometry_and_storage_contract(self):
        jobs,events,_=g.contracts(g.make_qwen2_21_fixture(128))
        for j in jobs:
            self.assertEqual(j['m'],128);self.assertFalse(j['activationBf16']);self.assertFalse(j['outputBf16'])
            self.assertEqual(j['weightBf16'],j['kind']=='Dense')
        self.assertEqual([j['pc'] for j in jobs if j['role'] in ('q_raw','k_raw','v_raw')],[1,4,7])
        self.assertEqual(len(events),21)
    def test_high_address_relocation_remains_exact_integer(self):
        base,_,_=g.contracts(self.f);relocated,_,_=g.contracts(g.make_qwen2_21_fixture(16,9,0x10000000000000))
        for a,b in zip(base,relocated):
            for key in ('a','b','dst'):self.assertEqual(b[key]-a[key],0x10000000000000)
            self.assertIs(type(b['a']),int);self.assertEqual(b['tag'],(9<<16)|b['pc'])
    def test_tables_contain_only_public_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'fixture';g.generate(16,7,0,out);manifest=json.loads((out/'manifest.json').read_bytes())
            self.assertEqual({p.name for p in out.iterdir()},{'command.bin','descriptor.bin','manifest.json'})
            for key,values in (('command',self.f.commands),('descriptor',self.f.records)):
                raw=(out/(key+'.bin')).read_bytes();self.assertEqual(raw[:16*len(values)],b''.join(v.pack().to_bytes(16,'little') for v in values))
            self.assertFalse(manifest['arithmetic_executed']);self.assertFalse(manifest['weights_materialized'])
    def test_role_validator_rejects_shape_root_type_and_terminal_drift(self):
        host=g.m.group.HostControl(enabled=False,legacy_prefix=True,legacy_attention=True)
        g.m.PublicFrontend(self.f.memory,self.f.config).launch(host)
        while host.ports()['ordinary_request'] is None:host.tick(request_ready=False)
        job=host.ports()['ordinary_request'];self.assertEqual(g.VALIDATE(self.f,job),0)
        for changes in ({'a':job.a+64},{'m':1},{'tag':job.tag+1},{'write_bytes':job.write_bytes-64},
                        {'activation_bf16':True},{'output_bf16':True},{'weight_bf16':True},{'c':64}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):g.VALIDATE(self.f,replace(job,**changes))
    def test_fixture_shape_and_epoch_reject_invalid_domains(self):
        for kwargs in ({'rows':True},{'rows':1},{'rows':17},{'epoch':65536},{'relocate':1},{'max_tokens':128}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):g.make_qwen2_21_fixture(**kwargs)
    def test_generated_gate_validates_all_manifest_and_metadata_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pin=self.make_gate(root);self.assertEqual(len(r.validate_fixture(root,pin)),10)
            with self.assertRaises(ValueError):r.validate_fixture(root,'0'*64)
            raw=root/'m16/command.bin';raw.write_bytes(raw.read_bytes()[:-1]+b'\xff')
            with self.assertRaises(ValueError):r.validate_fixture(root,pin)
    def test_gate_rejects_inherited_arithmetic_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_gate(root);p=root/'gate.json';data=json.loads(p.read_bytes());data['arithmetic_executed']=True;p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):r.validate_fixture(root,hashlib.sha256(p.read_bytes()).hexdigest())
    def test_gate_rejects_external_metadata_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_gate(root);p=root/'m16/manifest.json';data=json.loads(p.read_bytes());data['tables']['command']['file']='../../elsewhere.bin';p.write_text(json.dumps(data))
            gp=root/'gate.json';gate=json.loads(gp.read_bytes());gate['fixtures'][0]['manifest_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();gp.write_text(json.dumps(gate))
            with self.assertRaises(ValueError):r.validate_fixture(root,hashlib.sha256(gp.read_bytes()).hexdigest())
    def test_source_identity_rejects_missing_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):g.verify_sources(Path(tmp))
    def test_fresh_generation_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):g.generate(16,7,0,Path(tmp))
    def test_rtl_test_preserves_wide_integer_and_mock_boundary(self):
        text=(Path(__file__).with_name('Qwen2Public21DispatchControlSpec.scala')).read_text()
        self.assertIn('def exactJson',text);self.assertNotIn('.num',text)
        self.assertIn('owner_completion_mock=true',text);self.assertIn('bf16Weights=true',text)
        self.assertIn('short,tag,owner,metadata,unknown_opcode,stale_producer',text)
if __name__=='__main__':unittest.main()
