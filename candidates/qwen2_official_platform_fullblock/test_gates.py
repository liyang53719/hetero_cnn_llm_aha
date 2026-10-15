"""Real gate construction with synthetic external identities, no model/native runs."""
import copy
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
from candidates.qwen2_official_platform_fullblock import gates as g
from candidates.qwen2_official_platform_fullblock import native_artifact

class GatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rp=g.R.C.O.load_pins()
        for spec in rp['raw_tensors']:
            directory=g.R.C.PREFIX if spec['manifest_role']=='prefix_raw' else g.R.C.TAIL
            spec['path']=directory+'/raw/'+spec['local_name']+'.bin'
        for role,spec in rp['producer_roles'].items():
            directory=g.R.C.TAIL if role in ('wo','gamma1','wg','wu','wd') else g.R.C.PREFIX
            spec['path']=directory+'/inputs/'+role+'.bin'
        cls.rp=rp
        cls.artifacts={k:dict(path=str(g.ROOT/'work/qwen2_fullblock_ci_native/ci01'/f),bytes=1,sha256='a'*64)
            for k,f in [('library','official_bf16_matrix_silu.so'),('receipt','official_bf16_compile.json')]}
        dependency={str((g.REFERENCE/n).relative_to(g.ROOT)):'b'*64 for n in g.REFERENCE_METADATA}
        dependency.update({g.R.FROZEN_BINDING:'b'*64,g.R.C.BINDING:'b'*64})
        dependency['chisel/continuous_prefill/scripts/pack_owner_block_fixture.py']='b'*64
        cls.pin=dict(dependency_sha256=dependency,runtime_read_sha256={
            '/opt/hostedtoolcache/Python/3.12.14/x64/lib/libpython3.12.so.1.0':'b'*64})
        # Only runtime evidence lookups are substituted; construct actual base,
        # Scalar code-frame, ctypes code-frame, cleanup and exact-path gate state.
        with patch.object(g,'verify_dependencies',return_value=cls.pin),patch.object(g.R,'load_pins',return_value=rp), \
             patch.object(native_artifact,'identity',return_value=cls.artifacts), \
             patch.object(g,'_ctypes_runtime_source',return_value=(Path(g.ctypes.__file__).resolve(),
                 Path(g.ctypes.__file__).read_bytes())):
            # This class tests gate/readset behavior on the local runtime. The
            # strict official platform/source admission has separate real-file tests.
            cls.template=g.OracleGate(g.DATA,g.OUTPUT_ROOT/'synthetic_cold_only',g.REFERENCE)

    def setUp(self):
        self.gate=copy.copy(self.template)
        for n in ('reference_reads','provenance_reads','artifact_reads','environment_events','input_reads',
                  'source_cache_bypasses','cleanup_directory_reads'):setattr(self.gate,n,[])
        self.gate.opened=False;self.gate.blocked=0

    def read(self,p):self.gate.audit('open',(str(p),'rb',0))
    def seal(self,**kw):
        result=dict(actual_outputs_sealed=True,finalfence=True,same_live_identity=True,
            public_completions=21,actual_owner_jobs=17,accepted_launch_results=1,outstanding_debts={})
        result.update(kw);return result

    def test_actual_constructor_preserves_code_frame_proofs(self):
        for n in ('_ctypes_frame','_original_environment_frames'):
            self.assertIs(getattr(g.OracleGate,n),getattr(g.v2.OracleGate,n))
        self.assertEqual(self.gate.expected_environment.co_name,'_check_environment')
        self.assertEqual(self.gate.expected_init.co_name,'__init__')
        self.assertEqual(set(self.gate.expected_ctypes),{'__init__','__getitem__','__getattr__'})
        self.assertEqual(self.gate.expected_cleanup.co_name,'_rmtree_safe_fd')

    def test_exact_14_inputs_readonly_no_intermediate_preloads(self):
        self.assertEqual(len(self.gate.input_paths),14)
        for p in self.gate.input_paths:
            self.read(p)
            for mode,flags in [('wb',0),('r+b',0),(None,os.O_CREAT),('rb',os.O_WRONLY)]:
                with self.assertRaises(ValueError):self.gate.audit('open',(str(p),mode,flags))
        for name in ('q','k','v','att','n1','gate','up','act','down','y'):
            for directory in (g.DATA/'inputs',g.TAIL_INPUTS):
                with self.assertRaises(ValueError):self.read(directory/(name+'.bin'))
        self.assertEqual(len(self.gate.input_reads),14)

    def test_all_30_references_and_raw13_denied_before_whole_launch_seal(self):
        self.assertEqual((len(self.gate.reference_paths),len(self.gate.raw_paths)),(30,13))
        for p in self.gate.reference_paths|self.gate.raw_paths:
            with self.assertRaises(ValueError):self.read(p)
        self.assertEqual(self.gate.reference_reads,[])

    def test_exact_references_and_raw_allowed_only_after_full_seal(self):
        self.gate.open_after_seal(self.seal())
        for p in self.gate.reference_paths|self.gate.raw_paths:self.read(p)
        self.assertEqual(len(self.gate.reference_reads),30);self.assertEqual(len(self.gate.provenance_reads),13)
        for p in self.gate.reference_paths:
            with self.assertRaises(ValueError):self.gate.audit('open',(str(p),'wb',os.O_WRONLY))

    def test_partial_21_17_1_or_outstanding_debt_seal_rejected(self):
        for key,value in [('public_completions',12),('public_completions',21.0),('actual_owner_jobs',16),
            ('accepted_launch_results',True),('actual_outputs_sealed',False),('finalfence',False),
            ('same_live_identity',False),('outstanding_debts',{'pending':True}),('outstanding_debts',{'count':1})]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.gate.open_after_seal(self.seal(**{key:value}))
            self.assertFalse(self.gate.opened)
        self.gate.open_after_seal(self.seal())
        with self.assertRaises(ValueError):self.gate.open_after_seal(self.seal())

    def test_saved_actual_and_unlisted_work_denied_regardless_suffix_or_stage(self):
        for after in (False,True):
            if after:self.gate.open_after_seal(self.seal())
            for suffix in ('.json','.bin','.u32le','.presence','.f32le','.so','.txt',''):
                for base in (g.OUTPUT_ROOT/'prior',g.ROOT/'work/unknown',g.REFERENCE.parent/'old'):
                    with self.subTest(after=after,suffix=suffix),self.assertRaises(ValueError):self.read(base/('saved_actual'+suffix))

    def test_only_exact_current_native_elf_can_load(self):
        for p in self.gate.artifacts.values():self.read(p)
        self.gate.audit('ctypes.dlopen',(str(self.gate.artifacts['library']),))
        for p in (g.ROOT/'work/other/native.so',Path('/tmp/unknown.so')):
            with self.assertRaises(ValueError):self.gate.audit('ctypes.dlopen',(str(p),))
        with self.assertRaises(ValueError):self.gate.audit('ctypes.dlopen',(None,))

    def test_current_process_symbol_not_widened(self):
        class Process:_name=None
        for n in ('fegetround','system','fopen','fesetround'):
            with self.assertRaises(ValueError):self.gate.audit('ctypes.dlsym',(Process(),n))

    def test_only_minimal_platform_maps_read_is_added(self):
        self.read('/proc/self/maps')
        for p in ('/proc/self/mem','/proc/1/maps','/proc/self/environ'):
            with self.assertRaises(ValueError):self.read(p)
        for p in self.gate.runtime_paths:self.read(p)
        with self.assertRaises(ValueError):self.read(g.ROOT/'work/runtime_recovery/site-packages/numpy/unlisted.py')

    def test_source_cache_is_miss_without_bytecode_read(self):
        p=g.ROOT/'chisel/continuous_prefill/scripts/pack_owner_block_fixture.py'
        cache=Path(importlib.util.cache_from_source(str(p)))
        with self.assertRaises(FileNotFoundError):self.read(cache)
        self.read(p)
        with self.assertRaises(ValueError):self.read(g.ROOT/'work/unknown/__pycache__/thing.cpython-312.pyc')

    def test_old_namespace_and_output_overlap_denied(self):
        with self.assertRaises(ValueError):g.data_path('work/qwen2_live_qkv_inputs_m128/frozen01')
        with self.assertRaises(ValueError):g.reference_path('work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen')
        with self.assertRaises(ValueError):g.fresh_output(g.DATA/'actual',g.DATA)
        g.fresh_output(g.OUTPUT_ROOT/'synthetic_fresh_output_not_created',g.DATA)

    def test_torch_transformers_blocked(self):
        for module in ('torch','torch.nn','transformers','transformers.cache_utils'):
            with self.assertRaises(ValueError):self.gate.audit('import',(module,))

    def test_review_uses_external_source_closure_not_dynamic_evidence_digest(self):
        with patch('candidates.qwen2_official_platform_fullblock.job.authorize'), \
             patch.dict(os.environ,{g.R.CLOSURE_ENV:'a'*64}),patch.object(g.closure,'digest',return_value='a'*64), \
             patch.object(g,'sources',return_value={'synthetic_dynamic_evidence':'b'*64}):
            self.assertEqual(g.require_review('a'*64),{'synthetic_dynamic_evidence':'b'*64})
            with self.assertRaises(ValueError):g.require_review('c'*64)

    def test_original_232_dependency_hashes_and_21_exclusions_are_fixed(self):
        raw=g.ORIGINAL_PINS.read_bytes()
        self.assertEqual(g.R.sha(raw),g.ORIGINAL_PINS_SHA256)
        old=g.R.parse(raw)['dependency_sha256'];lost=set(g.LOST_HISTORICAL_EVIDENCE)
        self.assertEqual((len(old),len(lost),len(set(old)-lost)),(253,21,232))
        self.assertEqual({n for n in old if n.startswith('work/') and not n.startswith('work/runtime_recovery/')},lost)

    def test_runtime_remap_is_exact_not_directory_allow(self):
        old=g.R.parse(g.ORIGINAL_PINS.read_bytes())
        binding={'context':{'platform_files':{'python':{'path':'/fixed/python','sha256':'a'*64},
                                             'libpython':{'path':'/fixed/libpython','sha256':'b'*64}}}}
        record={'compiler':{'path':'/usr/bin/fixed-g++','sha256':'c'*64}}
        with patch.object(Path,'read_bytes',return_value=g.R.encoded(record)):
            runtime=g._runtime_pins(old,binding,self.artifacts)
            self.assertEqual(len(runtime),7)
            self.assertIn(str(g.ROOT/'work/runtime_recovery/site-packages/yaml/__init__.py'),runtime)
            self.assertEqual(runtime[self.artifacts['library']['path']],'a'*64)
            old['runtime_read_sha256']['/unknown/anything']='d'*64
            with self.assertRaises(ValueError):g._runtime_pins(old,binding,self.artifacts)

    def test_original_cleanup_helper_limited_to_current_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';other=root/'other'
            (out/'tmp'/'nested').mkdir(parents=True);(other/'tmp').mkdir(parents=True)
            self.gate.out=out
            original_open=os.open
            def guarded(path,flags,mode=0o777,*,dir_fd=None):
                if not Path(path).is_absolute():
                    admitted=self.gate._cleanup_directory(os.fsdecode(path),None,flags,sys._getframe(1))
                    self.assertIsNotNone(admitted)
                return original_open(path,flags,mode,dir_fd=dir_fd)
            with patch.object(os,'open',guarded):
                shutil.rmtree(out)
                with self.assertRaisesRegex(ValueError,'inside the current output'):shutil.rmtree(other)
            self.assertFalse(out.exists());self.assertTrue(other.exists())

if __name__=='__main__':unittest.main()
