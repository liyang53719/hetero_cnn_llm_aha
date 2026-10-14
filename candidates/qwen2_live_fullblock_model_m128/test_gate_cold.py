"""Source/metadata and synthetic audit events only: no actual/raw/reference bytes.

The real original Scalar/FENV initialization probe is separate; these tests do
not import numeric model services, compile native code, or run model arithmetic.
"""
import copy
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import struct
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import gates as g


class FullBlockGateColdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = g.OracleGate(g.DATA, g.OUTPUT_ROOT/'cold_gate_only', g.REFERENCE)
        cls.pin = g.pins()
        cls.recipe_pin = g.R.load_pins()

    def setUp(self):
        self.gate = copy.copy(self.template)
        for name in ('reference_reads','provenance_reads','artifact_reads','environment_events','input_reads',
                     'source_cache_bypasses','cleanup_directory_reads'):
            setattr(self.gate, name, [])
        self.gate.opened = False
        self.gate.blocked = 0

    def read(self, path):
        self.gate.audit('open', (str(path), 'rb', 0))

    def seal(self, **changes):
        value = dict(actual_outputs_sealed=True, public_completions=21,
            actual_owner_jobs=17, accepted_launch_results=1, finalfence=True,
            same_live_identity=True, outstanding_debts={})
        value.update(changes)
        return value

    def test_exact_fourteen_readonly_operand_paths(self):
        self.assertEqual(len(self.gate.input_paths), 14)
        for path in self.gate.input_paths:
            self.read(path)
            for mode, flags in (('wb',0), ('r+b',0), (None,os.O_WRONLY), ('rb',os.O_CREAT)):
                with self.assertRaisesRegex(ValueError, 'read-only'):
                    self.gate.audit('open', (str(path),mode,flags))
        self.assertEqual(len(self.gate.input_reads),14)
        for name in ('q','k','v','kv','att','n1','gate','up','act','down','y'):
            for directory in (g.DATA/'inputs',g.TAIL_INPUTS):
                with self.assertRaises(ValueError):
                    self.read(directory/(name+'.bin'))

    def test_all_thirty_reference_payloads_blocked_preseal(self):
        self.assertEqual(len(self.gate.reference_paths),30)
        for path in self.gate.reference_paths:
            with self.assertRaises(ValueError):
                self.read(path)
        self.assertEqual(self.gate.blocked,30)
        self.assertEqual(self.gate.reference_reads,[])

    def test_thirteen_raw_paths_postseal_provenance_only(self):
        for path in self.gate.raw_paths:
            with self.assertRaises(ValueError):
                self.read(path)
        self.gate.open_after_seal(self.seal())
        for path in self.gate.raw_paths:
            self.read(path)
            with self.assertRaises(ValueError):
                self.gate.audit('open',(str(path),'wb',0))
        self.assertEqual(len(self.gate.provenance_reads),13)

    def test_full_launch_seal_required(self):
        for key, value in (('actual_outputs_sealed',False), ('public_completions',13),
                           ('public_completions',21.0), ('actual_owner_jobs',11),
                           ('accepted_launch_results',0), ('accepted_launch_results',True),
                           ('finalfence',False), ('same_live_identity',False),
                           ('outstanding_debts',{'pending':True}),
                           ('outstanding_debts',{'seed':1}), ('outstanding_debts',None)):
            with self.subTest(key=key,value=value):
                with self.assertRaises(ValueError):
                    self.gate.open_after_seal(self.seal(**{key:value}))
                self.assertFalse(self.gate.opened)
        self.gate.open_after_seal(self.seal(outstanding_debts={'matrix':False,'seed':0,'dma':None}))
        with self.assertRaises(ValueError):
            self.gate.open_after_seal(self.seal())

    def test_only_fresh_frozen_reference_paths_open_after_seal(self):
        self.gate.open_after_seal(self.seal())
        for path in self.gate.reference_paths:
            self.read(path)
            with self.assertRaises(ValueError):
                self.gate.audit('open',(str(path),'ab',0))
        for path in (g.REFERENCE/'qraw.f32le',g.REFERENCE/'unknown',
                     g.REFERENCE.parent/'bootstrap/y.f32le',
                     g.ROOT/'work/qwen2_live_attention_reference_m128/frozen01/reference/att.f32le'):
            with self.assertRaises(ValueError):
                self.read(path)
        self.assertEqual(len(self.gate.reference_reads),30)

    def test_old_actual_files_denied_regardless_extension_and_seal(self):
        for opened in (False,True):
            if opened:
                self.gate.open_after_seal(self.seal())
            for extension in ('.bin','.f32le','.bf16le','.u32le','.presence','.npy','.npz','.json','.txt',''):
                for directory in (g.OUTPUT_ROOT/'previous',
                    g.ROOT/'work/qwen2_live_attention_numeric_m128_bounded_20261014/old',
                    self.gate.artifacts['library'].parent.parent):
                    with self.subTest(opened=opened,extension=extension,directory=directory):
                        with self.assertRaises(ValueError):
                            self.read(directory/('saved_actual'+extension))

    def test_only_exact_native_code_artifacts(self):
        for path in self.gate.artifacts.values():
            self.read(path)
            with self.assertRaises(ValueError):
                self.gate.audit('open',(str(path),'wb',0))
        self.gate.audit('ctypes.dlopen',(str(self.gate.artifacts['library']),))
        for path in (g.ROOT/'work/other/library.so',g.ROOT/'work/other/library.so.1',Path('/tmp/unknown.so')):
            with self.assertRaises(ValueError):
                self.gate.audit('ctypes.dlopen',(str(path),))
            with self.assertRaises(ValueError):
                self.read(path)
        with self.assertRaises(ValueError):
            self.gate.audit('ctypes.dlopen',(None,))

    def test_current_process_symbol_not_widened(self):
        class CurrentProcess:
            _name = None
        for symbol in ('fegetround','system','fopen','fesetround'):
            with self.assertRaises(ValueError):
                self.gate.audit('ctypes.dlsym',(CurrentProcess(),symbol))

    def test_exact_v2_fenv_source_helpers_are_inherited(self):
        for name in ('_ctypes_frame','_original_environment_frames'):
            self.assertIs(getattr(g.OracleGate,name),getattr(g.v2.OracleGate,name))
        self.assertEqual(self.gate.expected_environment.co_name,'_check_environment')
        self.assertEqual(self.gate.expected_init.co_name,'__init__')

    def test_current_output_and_pinned_metadata_available(self):
        for name in ('RESULT.json','observed.u32le','observed.presence','tmp/commands.bin'):
            self.read(self.gate.out/name)
            self.gate.audit('open',(str(self.gate.out/name),'wb',os.O_WRONLY|os.O_CREAT))
        self.read(self.gate.header)
        for name in g.REFERENCE_METADATA:
            self.read(g.REFERENCE/name)
        for name in ('gates.py','pins.json','BUDGET.json'):
            self.read(g.HERE/name)
        for path in self.gate.runtime_paths:
            self.read(path)
        with self.assertRaises(ValueError):
            self.read(g.ROOT/'work/runtime_recovery/site-packages/not_pinned.npy')

    def test_torch_and_transformers_imports_forbidden(self):
        for name in ('torch','torch.nn.functional','transformers','transformers.cache_utils'):
            with self.assertRaises(ValueError):
                self.gate.audit('import',(name,None,None,None,None))

    def test_fixed_input_and_reference_namespaces(self):
        self.assertEqual(g.data_path(str(g.DATA.relative_to(g.ROOT))),g.DATA)
        self.assertEqual(g.reference_path(str(g.REFERENCE.relative_to(g.ROOT))),g.REFERENCE)
        for value in ('/tmp/data','work/qwen2_live_qkv_inputs_m128/another',
                      str(g.DATA.relative_to(g.ROOT))+'/../frozen01'):
            with self.assertRaises(ValueError):
                g.data_path(value)
        for value in ('/tmp/reference',str(g.REFERENCE.relative_to(g.ROOT)).replace('frozen','bootstrap'),
                      'work/qwen2_live_attention_reference_m128/frozen01/reference'):
            with self.assertRaises(ValueError):
                g.reference_path(value)
        g.fresh_output(self.gate.out,g.DATA)
        for path in (g.OUTPUT_ROOT,self.gate.out/'nested',g.DATA/'output',g.REFERENCE/'output'):
            with self.assertRaises(ValueError):
                g.fresh_output(path,g.DATA)

    def test_rows_and_stored_approval_rejected(self):
        for row in (16,127,129,128.0,True,'128'):
            with patch.object(g,'pins',return_value=dict(self.pin,rows=row)):
                with self.assertRaises(ValueError):
                    g.verify_dependencies()
        with patch.object(g,'pins',return_value=dict(self.pin,actual_execution_authorized=True)):
            with self.assertRaises(ValueError):
                g.verify_dependencies()

    def test_review_required_and_freeze_excluded(self):
        for value in (None,'','0'*64,'x'*64):
            with self.assertRaises(ValueError):
                g.require_review(value)
        sources = g.sources()
        relative = str(g.HERE.relative_to(g.ROOT))
        for filename in ('gates.py','test_gate_cold.py','pins.json','BUDGET.json'):
            self.assertIn(relative+'/'+filename,sources)
        self.assertNotIn(relative+'/FREEZE.json',sources)

    def test_unreviewed_wholeblock_budget_refuses_actual(self):
        with self.assertRaisesRegex(ValueError,'budget unreviewed'):
            g.require_budget()

    def test_budget_positive_types_and_no_call_time_override(self):
        valid = dict(status='REVIEWED_FIXED_WHOLE_BLOCK_BUDGET',inner_wall_seconds=1,
            outer_wall_seconds=8,rss_bytes=1,output_bytes=2,file_bytes=1,log_bytes=1,
            progress_loop_interval=131072,poll_seconds=.1,automatic_retry=False)
        with patch.object(g.R,'parse',return_value=valid):
            self.assertEqual(g.require_budget(),valid)
        for key in ('inner_wall_seconds','outer_wall_seconds','rss_bytes','output_bytes',
                    'file_bytes','log_bytes','progress_loop_interval'):
            for value in (None,0,True,1.0):
                with patch.object(g.R,'parse',return_value=dict(valid,**{key:value})):
                    with self.assertRaises(ValueError):
                        g.require_budget()
        for value in (None,0,True,2,float('nan'),float('inf')):
            with patch.object(g.R,'parse',return_value=dict(valid,poll_seconds=value)):
                with self.assertRaises(ValueError):
                    g.require_budget()
        for changes in ({'outer_wall_seconds':7},{'automatic_retry':True},
                        {'automatic_retry':None},{'progress_loop_interval':131071}):
            with patch.object(g.R,'parse',return_value=dict(valid,**changes)):
                with self.assertRaises(ValueError):
                    g.require_budget()
        with self.assertRaises(TypeError):
            g.require_budget(inner_wall_seconds=1200)

    def test_metadata_validation_never_opens_input_raw_or_reference_payloads(self):
        forbidden = self.gate.input_paths | self.gate.raw_paths | self.gate.reference_paths
        original_open = Path.open
        reads = []
        def guarded_open(path,*args,**kwargs):
            actual = path.resolve()
            if actual in forbidden:
                raise AssertionError('cold metadata opened payload: '+str(actual))
            self.gate.audit('open',(str(path),'rb',0))
            reads.append(str(actual))
            return original_open(path,*args,**kwargs)
        before = set(sys.modules)
        with patch.object(Path,'open',guarded_open):
            ref = g.validate_reference_metadata(g.DATA,g.REFERENCE)
        self.assertEqual(set(ref['outputs']),g.REFERENCES)
        self.assertFalse(any(name.split('.')[0] in ('torch','numpy','transformers') for name in set(sys.modules)-before))
        self.assertTrue(reads)

    def test_pinned_producer_and_raw_counts_and_geometry(self):
        rp = self.recipe_pin
        self.assertEqual(set(rp['producer_roles']),g.ROLES)
        self.assertEqual(len(rp['raw_tensors']),13)
        self.assertEqual(sum(s['bytes'] for s in rp['producer_roles'].values()),94916608)
        self.assertEqual(sum(s['bytes'] for s in rp['raw_tensors']),94382080)
        for role in ('wo','wg','wu','wd'):
            self.assertTrue(rp['producer_roles'][role]['record']['transposed'])
            self.assertEqual(rp['producer_roles'][role]['record']['storage_encoding'],'BF16_LE')
        self.assertTrue(rp['producer_roles']['gamma1']['record']['widened'])

    def test_named_cold_cache_layout_is_fixed(self):
        raw = struct.pack('<6I',0,1,2,3,4,5)
        token_major = struct.pack('<6I',0,3,1,4,2,5)
        for name in ('q','k','cache_k','cache_v','repeat_k','repeat_v','pv'):
            self.assertEqual(g._token_bytes(name,raw,[1,2,3,1]),token_major)
        for name in ('v','att','scores','logits','prob','softmax_fp32'):
            self.assertEqual(g._token_bytes(name,raw,[1,2,3,1]),raw)

    def test_pinned_source_cache_is_a_miss_without_reading_bytecode(self):
        source = g.ROOT/'chisel/continuous_prefill/scripts/pack_owner_block_fixture.py'
        cache = Path(importlib.util.cache_from_source(str(source)))
        with self.assertRaises(FileNotFoundError):
            self.read(cache)
        self.assertEqual(self.gate.source_cache_bypasses,[str(cache)])
        self.assertEqual(self.gate.blocked,0)
        self.read(source)
        with self.assertRaises(ValueError):
            self.read(g.ROOT/'work/old/__pycache__/actual.cpython-312.pyc')

    def test_relative_directory_names_have_no_general_allowance(self):
        for name in ('tmp','nested','../tmp'):
            with self.assertRaises(ValueError):
                self.gate.audit('open',(name,None,os.O_RDONLY|os.O_NONBLOCK))

    def test_original_shutil_fd_relative_cleanup_is_output_only(self):
        # Empty temporary directories only. No model, raw or reference payload.
        g.OUTPUT_ROOT.mkdir(exist_ok=True)
        out = Path(tempfile.mkdtemp(prefix='cold_gate_cleanup_',dir=g.OUTPUT_ROOT))
        other = Path(tempfile.mkdtemp(prefix='cold_gate_outside_',dir=g.OUTPUT_ROOT))
        self.gate.out = out
        (out/'tmp'/'nested').mkdir(parents=True)
        (other/'tmp').mkdir()
        original_open = os.open
        def checked_open(path, flags, mode=0o777, *, dir_fd=None):
            if not Path(path).is_absolute():
                admitted = self.gate._cleanup_directory(os.fsdecode(path),None,flags,sys._getframe(1))
                self.assertIsNotNone(admitted)
            return original_open(path,flags,mode,dir_fd=dir_fd)
        try:
            with patch.object(os,'open',checked_open):
                shutil.rmtree(out)
                with self.assertRaisesRegex(ValueError,'inside the current output'):
                    shutil.rmtree(other)
            self.assertEqual(self.gate.cleanup_directory_reads,['tmp','tmp/nested'])
            self.assertFalse(out.exists())
            self.assertTrue((other/'tmp').is_dir())
        finally:
            for path in (out,other):
                if path.exists():
                    shutil.rmtree(path)


if __name__ == '__main__':
    unittest.main()
