"""Cold-only admission/isolation tests; no numeric runtime, inputs or compilation."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from candidates.qwen2_live_attention_model_m16 import gates as g, runner


class ColdGateTests(unittest.TestCase):
    def setUp(self):
        self.data=g.ROOT/'work/qwen2_live_qkv_inputs/fixture'
        self.out=g.OUTPUT_ROOT/'fixture'
        self.reference=g.ROOT/'work/qwen2_live_attention_reference_m16_20261014/frozen01/reference'
        self.gate=g.OracleGate(self.data,self.out,self.reference)
    def read(self,path):return self.gate.audit('open',(str(path),'rb',0))
    def test_default_not_executed_without_numeric_imports(self):
        stream=io.StringIO()
        with patch.object(runner,'dependencies',side_effect=AssertionError('runtime forbidden')),contextlib.redirect_stdout(stream):
            self.assertEqual(runner.main([]),0)
        r=json.loads(stream.getvalue());self.assertEqual(r['status'],'NOT_EXECUTED')
        self.assertFalse(r['input_loading'] or r['build'] or r['rtl'] or r['fullblock'])
    def test_partial_actual_arguments_rejected(self):
        for args in (['--actual'],['--data','x'],['--reference','x'],['--out','x'],['--actual','--data','x','--out','x']):
            with self.assertRaises(ValueError):runner.main(args)
    def test_unfrozen_attention_rejected_before_paths(self):
        with (patch.object(g,'pins',return_value=dict(g.pins(),attention_reference_finalized=False)),
            patch.object(g,'data_path',side_effect=AssertionError('no input read')),
            patch.object(g,'reference_path',side_effect=AssertionError('no reference admission'))):
            with self.assertRaisesRegex(ValueError,'not finalized'):runner.run('out','data','ref')
    def test_reference_freeze_requires_valid_sha(self):
        for value in (None,'0','bad','x'*64):
            with patch.object(g,'pins',return_value=dict(g.pins(),attention_reference_finalized=True,attention_reference_pins_sha256=value)):
                with self.assertRaisesRegex(ValueError,'not finalized'):g.require_final_reference()
    def test_exact_scope_rows(self):
        for row in (128,15,17,16.0,True,'16'):
            with patch.object(g,'pins',return_value=dict(scope='M16_SOFTWARE_PC0_12_HELD',rows=row)):
                with self.assertRaises(ValueError):g.verify_dependencies()
    def test_dependency_drift_rejected(self):
        with patch.object(g,'pins',return_value=dict(scope='M16_SOFTWARE_PC0_12_HELD',rows=16,dependency_sha256={'spec/numerical_contract.md':'0'*64})):
            with self.assertRaisesRegex(ValueError,'dependency drift'):g.verify_dependencies()
    def test_only_nine_executable_inputs(self):
        for role in g.ROLES:self.read(self.data/'inputs'/(role+'.bin'))
        for role in ('q','k','v','kv','att','scores','prob'):
            with self.assertRaises(ValueError):self.read(self.data/'inputs'/(role+'.bin'))
    def test_eighteen_oracles_blocked_before_seal(self):
        for role in g.REFERENCES:
            with self.assertRaises(ValueError):self.read(self.reference/(role+'.f32le'))
        with self.assertRaises(ValueError):self.read(self.reference/'mask.bf16le')
        self.assertEqual(self.gate.blocked,19)
    def test_only_new_frozen_namespace_after_seal(self):
        self.gate.opened=True
        for role in g.REFERENCES:self.read(self.reference/(role+'.f32le'))
        for path in (self.data/'reference/q.f32le',g.OUTPUT_ROOT/'old/att.f32le',self.reference/'qraw.f32le'):
            with self.assertRaises(ValueError):self.read(path)
    def test_prior_actual_and_arbitrary_binary_rejected(self):
        for path in (g.ROOT/'work/qwen2_live_qkv_numeric_m128_20261014/package_m128_v1/q.f32le',Path('/tmp/input.bin'),g.ROOT/'old.npz'):
            with self.assertRaises(ValueError):self.read(path)
    def test_fresh_output_metadata_only_within_run(self):
        self.read(self.out/'tmp/commands.bin');self.read(self.gate.header)
        with self.assertRaises(ValueError):self.read(self.gate.header.with_name('not_header.bin'))
    def test_paths_are_narrow(self):
        for value in ('/tmp/reference','work/qwen2_live_attention_reference_m16_20261014/frozen01/../reference','work/qwen2_live_qkv_inputs_m128/frozen01/reference'):
            with self.assertRaises(ValueError):g.reference_path(value)
        for path in (g.OUTPUT_ROOT,self.out/'nested',self.data/'output'):
            with self.assertRaises(ValueError):g.fresh_output(path,self.data)
    def test_old_m128_package_unchanged(self):
        for name,digest in g.pins()['parent_m128_source_sha256'].items():
            self.assertEqual(g.sha(g.ROOT/'candidates/qwen2_live_qkv_model_m128'/name),digest)
    def test_source_bounds_distinguish_actual_slice(self):
        source=(g.ROOT/'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp').read_text()
        self.assertIn('for(unsigned r=0;r<16;r++)for(unsigned col=0;col<32;col++)',source)
        self.assertEqual(12*16*17//2*12*512,10027008)
        self.assertEqual(16/512,0.03125)

if __name__=='__main__':unittest.main()
