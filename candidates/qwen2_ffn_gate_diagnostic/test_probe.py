import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from . import probe as p


class ColdTests(unittest.TestCase):
    def test_default_is_cold(self):
        with patch('pathlib.Path.open', side_effect=AssertionError('unexpected read')):
            self.assertEqual(p.run(), {'status':'NOT_EXECUTED'})
        self.assertNotIn('torch', sys.modules)
        self.assertNotIn('numpy', sys.modules)

    def test_original_gate_source(self):
        self.assertEqual(p.source_check(), p.SOURCE_PINS)

    def test_fixed_bounds(self):
        self.assertEqual((p.ROWS,p.K,p.WIDTH,p.NCOLS),(128,1536,8960,32))
        self.assertEqual(p.WINDOWS,(0,4480,8928))
        self.assertTrue(all(ng%32==0 and ng+32<=8960 for ng in p.WINDOWS))
        self.assertEqual((p.CPU_SECONDS,p.AS_BYTES,p.OUTPUT_BYTES),(120,4<<30,64<<20))

    def test_original_constructor_only(self):
        pins=json.loads((p.ROOT/'candidates/qwen2_fullblock_reference_m128/pins.json').read_text())
        node=p.gate_constructor(pins['model_ast_nodes'])
        self.assertEqual(ast.unparse(node),'self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)')
        specs=p.raw_specs(pins)
        self.assertEqual(len(specs),11)
        self.assertNotIn('mlp.up_proj.weight',specs)
        self.assertNotIn('mlp.down_proj.weight',specs)

    def test_audit_refuses_historical_payload(self):
        a=p.payload_audit([p.PREFIX/'input_layernorm.weight.bin'],p.OUT)
        for path in ('work/qwen2_fresh_reference_recovery_m128/recovered01/frozen/n1.f32le',
                     'work/qwen2_fullblock_recovery_numeric_m128_20261015/attempt01/n1.f32le',
                     'work/private_ci_dut/gate.f32le'):
            with self.assertRaises(ValueError): a('open',(str(p.ROOT/path),'r',0))
        a('open',(str(p.PREFIX/'input_layernorm.weight.bin'),'r',0))
        a('open',(str(p.OUT/'selected.f32le'),'w',0))
        with self.assertRaises(ValueError): a('open',(str(p.HERE/'oops.py'),'w',0))
        with self.assertRaises(ValueError): a('subprocess.Popen',())

    def test_ast_stops_before_mlp(self):
        tree=ast.parse((p.HERE/'probe.py').read_text())
        method=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='official_to_n1')
        calls=[n for n in ast.walk(method) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(any(n.func.attr in ('up_proj','down_proj','mlp') for n in calls))
        self.assertEqual(sum(n.func.attr=='gate_proj' for n in calls),1)


class NativeReceiptColdTests(unittest.TestCase):
    def setUp(self):
        from candidates.qwen2_resident_matrix.official_bf16 import dense_silu
        self.dense = dense_silu
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.library = self.root/'synthetic.so'
        self.library.write_bytes(b'\x7fELFsynthetic test bytes; never loaded')
        self.compiler = self.root/'synthetic-compiler'
        self.compiler.write_bytes(b'synthetic compiler identity; never executed')
        self.receipt = self.root/'compile.json'
        self.compiler_record = dict(path=str(self.compiler), sha256=p.sha(self.compiler), version='synthetic')
        self.data = dict(schema=1, policy=self.dense.POLICY_VERSION, status='PASS', returncode=0,
            selected_silu_entrypoint='sf_vector_bf16_v1', original_silu_entrypoint='sf_vector',
            compiler=self.compiler_record, library=str(self.library), library_sha256=p.sha(self.library),
            argv=[str(self.compiler), *self.dense.STRICT_FLAGS,
                  *(str(self.dense.ROOT/name) for name in self.dense.TRANSLATION_UNITS), '-o', str(self.library)],
            source_sha256={name:p.sha(self.dense.ROOT/name) for name in self.dense.SOURCE_CLOSURE})
        self.expected_library_patch = patch.object(p,'KNOWN_LIBRARY_SHA256',p.sha(self.library))
        self.expected_library_patch.start(); self.addCleanup(self.expected_library_patch.stop)
        self.compiler_patch = patch.object(self.dense,'compiler_identity',return_value=self.compiler_record)
        self.compiler_patch.start(); self.addCleanup(self.compiler_patch.stop)
        self.load_patch = patch('ctypes.CDLL',side_effect=AssertionError('no native load in cold tests'))
        self.load_patch.start(); self.addCleanup(self.load_patch.stop)

    def write_receipt(self, data=None):
        self.receipt.write_text(json.dumps(self.data if data is None else data))
        return p.sha(self.receipt)

    def prepare(self, data=None):
        digest=self.write_receipt(data)
        return p.prepare_native_artifact(self.receipt,digest,self.dense)

    def test_complete_tracked_verifier_and_pure_recheck(self):
        with patch.object(self.dense,'verify_library',wraps=self.dense.verify_library) as verify:
            artifact=self.prepare()
            verify.assert_called_once()
        with patch.object(self.dense,'compiler_identity',side_effect=AssertionError('late process probe')):
            p.recheck_native_artifact(artifact,self.dense)
        self.assertNotIn('torch',sys.modules)
        self.assertNotIn('numpy',sys.modules)

    def test_explicit_independent_hash_required(self):
        self.write_receipt()
        for digest in (None,'','0'*64,'g'*64):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                p.prepare_native_artifact(self.receipt,digest,self.dense)
        with self.assertRaises(ValueError): p.run(execute=True)

    def test_original_schema_policy_abi_compiler_and_flags_rejections(self):
        changes=[('schema',2),('policy','changed'),('status','FAIL'),('returncode',1),
                 ('selected_silu_entrypoint','sf_vector'),('original_silu_entrypoint','other'),
                 ('compiler',{**self.compiler_record,'version':'changed'}),
                 ('argv',self.data['argv']+['-ffast-math']),('source_sha256',{}),
                 ('library_sha256','0'*64)]
        for key,value in changes:
            data=copy.deepcopy(self.data); data[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.prepare(data)

    def test_aliases_and_noncanonical_receipt_rejected(self):
        digest=self.write_receipt()
        alias=self.root/'alias.json'; alias.symlink_to(self.receipt)
        with self.assertRaises(ValueError): p.prepare_native_artifact(alias,digest,self.dense)
        (self.root/'unused').mkdir()
        with self.assertRaises(ValueError):
            p.prepare_native_artifact(self.root/'unused/../compile.json',digest,self.dense)
        link=self.root/'alias.so';link.symlink_to(self.library)
        data=copy.deepcopy(self.data);data['library']=str(link)
        with self.assertRaises(ValueError): self.prepare(data)

    def test_known_elf_and_receipt_drift_rejected(self):
        artifact=self.prepare()
        self.library.write_bytes(b'\x7fELFchanged')
        with self.assertRaises(ValueError): p.recheck_native_artifact(artifact,self.dense)
        self.library.write_bytes(b'\x7fELFsynthetic test bytes; never loaded')
        self.receipt.write_text(self.receipt.read_text()+' ')
        with self.assertRaises(ValueError): p.recheck_native_artifact(artifact,self.dense)

    def test_elf_magic_rejected_even_with_matching_synthetic_pin(self):
        self.library.write_bytes(b'not an ELF')
        data=copy.deepcopy(self.data);data['library_sha256']=p.sha(self.library)
        with patch.object(p,'KNOWN_LIBRARY_SHA256',p.sha(self.library)),self.assertRaises(ValueError):
            self.prepare(data)

    def test_change_during_verifier_rejected(self):
        original=self.dense.verify_library
        def mutate(data):
            result=original(data)
            self.receipt.write_text(self.receipt.read_text()+' ')
            return result
        with patch.object(self.dense,'verify_library',side_effect=mutate),self.assertRaises(ValueError):
            self.prepare()

    def test_runtime_no_untracked_recovery_import_and_pre_audit_verification(self):
        source=(p.HERE/'probe.py').read_text()
        self.assertNotIn('qwen2_fullblock_recovery',source)
        self.assertFalse(any('qwen2_fullblock_recovery' in name for name in p.SOURCE_PINS))
        tree=ast.parse(source)
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        calls=list(ast.walk(run))
        verify=min(n.lineno for n in calls if isinstance(n,ast.Call) and
                   isinstance(n.func,ast.Name) and n.func.id=='prepare_native_artifact')
        audit=min(n.lineno for n in calls if isinstance(n,ast.Call) and
                  isinstance(n.func,ast.Attribute) and n.func.attr=='addaudithook')
        self.assertLess(verify,audit)


if __name__=='__main__': unittest.main()
