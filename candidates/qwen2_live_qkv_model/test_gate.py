"""Stdlib-only cold/negative tests. No payloads, compilation, NumPy or RTL."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from candidates.qwen2_live_qkv_model import gates as g, runner


class ColdGateTests(unittest.TestCase):
    def setUp(self):
        self.data=g.ROOT/'work/qwen2_live_qkv_inputs/fixture'
        self.out=g.OUTPUT_ROOT/'fresh_fixture'
        self.gate=g.OracleGate(self.data,self.out)

    def check(self,path):return self.gate.audit('open',(str(path),'rb',0))

    def test_default_is_not_executed(self):
        stream=io.StringIO()
        with patch.object(runner,'dependencies',side_effect=AssertionError('no runtime')),contextlib.redirect_stdout(stream):
            self.assertEqual(runner.main([]),0)
        r=json.loads(stream.getvalue());self.assertEqual(r['status'],'NOT_EXECUTED')
        self.assertFalse(r['input_loading'] or r['build'] or r['rtl'] or r['fullblock'])

    def test_no_data_or_out_without_explicit_actual(self):
        for a in (['--data','anything'],['--out','anything']):
            with self.assertRaises(ValueError):runner.main(a)

    def test_actual_requires_both_explicit_paths(self):
        for a in (['--actual'],['--actual','--data','anything'],['--actual','--out','anything']):
            with self.assertRaises(ValueError):runner.main(a)

    def test_eight_raw_nine_inputs_nine_references_pins(self):
        p=g.verify_dependencies()
        from candidates.qwen2_live_qkv_inputs import recipe
        r=recipe.load_pins();self.assertEqual(len(r['tensors']),8);self.assertEqual(set(r['roles']),g.ROLES)
        self.assertEqual(set(r['references']),{'x','n0','qr','q','kr','k','v','cos','sin'})
        self.assertEqual(p['rows'],16)

    def test_source_drift_is_fatal(self):
        with patch.object(g,'pins',return_value=dict(scope='M16_SOFTWARE_PC0_8_HELD',rows=16,
                dependency_sha256={'spec/numerical_contract.md':'0'*64})):
            with self.assertRaisesRegex(ValueError,'dependency drift'):g.verify_dependencies()

    def test_no_m128_or_changed_scope(self):
        for row in (128,True,'16'):
            with patch.object(g,'pins',return_value=dict(scope='M16_SOFTWARE_PC0_8_HELD',rows=row)):
                with self.assertRaises(ValueError):g.verify_dependencies()

    def test_data_path_alias_and_other_namespaces_rejected(self):
        for p in ('/tmp/input','work/qwen2_live_qkv_inputs/../evil','work/other/x','work/qwen2_live_qkv_inputs/x/reference'):
            with self.assertRaises(ValueError):g.data_path(p)

    def test_output_is_fresh_narrow_direct_child(self):
        for p in (g.OUTPUT_ROOT,g.OUTPUT_ROOT/'a/b',g.ROOT/'candidates/output',self.data/'child'):
            with self.assertRaises(ValueError):g.fresh_output(p,self.data)
        with patch.object(Path,'exists',return_value=True):
            with self.assertRaises(ValueError):g.fresh_output(g.OUTPUT_ROOT/'already_exists',self.data)

    def test_nine_input_reads_allowed(self):
        for role in g.ROLES:self.check(self.data/'inputs'/(role+'.bin'))
        self.assertEqual(self.gate.reference_reads,[])

    def test_all_official_payloads_rejected_before_seal(self):
        for role in ('x','n0','qr','q','kr','k','v','cos','sin'):
            with self.assertRaises(ValueError):self.check(self.data/'reference'/(role+'.f32le'))
        self.assertEqual(self.gate.blocked,9)

    def test_preloaded_intermediate_input_rejected(self):
        for role in ('n0','qraw','kraw','vraw','q','k','v'):
            with self.assertRaises(ValueError):self.check(self.data/'inputs'/(role+'.bin'))

    def test_prior_actual_and_recipe_outputs_rejected(self):
        for rel in ('m16_v2/qraw.f32le','m16_v2_raw_reference_v1/qraw.typed_recipe.f32le','m16_v2/q.error_f64.npy'):
            with self.assertRaises(ValueError):self.check(g.OUTPUT_ROOT/rel)

    def test_other_payload_namespaces_and_formats_rejected(self):
        for p in (g.ROOT/'work/other/cache.npz',g.ROOT/'old.f32le',Path('/tmp/oracle.bin')):
            with self.assertRaises(ValueError):self.check(p)

    def test_only_exact_pinned_header_binary_is_source_metadata(self):
        self.check(self.gate.header)
        with self.assertRaises(ValueError):self.check(self.gate.header.with_name('other.header.bin'))

    def test_fresh_run_command_metadata_allowed_without_tmp_wildcard(self):
        self.check(self.out/'tmp/metadata/fp32/host_commands.bin')
        with self.assertRaises(ValueError):self.check(Path('/tmp/metadata/host_commands.bin'))

    def test_only_reference_inventory_opened_after_seal(self):
        self.gate.opened=True
        self.check(self.data/'reference/q.f32le')
        self.assertEqual(self.gate.reference_reads,['reference/q.f32le'])
        with self.assertRaises(ValueError):self.check(self.data/'reference/qraw.f32le')

    def test_exact_official_comparison_coverage(self):
        c={n:{'official_numeric_pass':True} for n in g.OFFICIAL}
        c.update({n:{'official_numeric_pass':None} for n in g.RAW})
        self.assertTrue(g.official_pass(c))
        for name in tuple(c):
            d=dict(c);d.pop(name)
            with self.assertRaises(ValueError):g.official_pass(d)
        c['q']={'official_numeric_pass':False};self.assertFalse(g.official_pass(c))

    def test_missing_official_cannot_be_raw_or_vacuous_pass(self):
        for c in ({},{n:{'official_numeric_pass':None} for n in g.OFFICIAL|g.RAW}):
            with self.assertRaises(ValueError):g.official_pass(c)

    def test_no_invented_official_raw_pass(self):
        c={n:{'official_numeric_pass':True} for n in g.OFFICIAL|g.RAW}
        with self.assertRaises(ValueError):g.official_pass(c)

    def test_raw_rejected_destination_never_writes_old_failure_record(self):
        from candidates.qwen2_live_qkv_model import raw_reference
        for out in (g.OUTPUT_ROOT/'m16_v2',g.OUTPUT_ROOT/'alias'):
            with (patch.object(raw_reference,'run',side_effect=ValueError('output exists/alias')),
                  patch.object(raw_reference,'save') as writer):
                with self.assertRaises(ValueError):
                    raw_reference.main(['--actual-result',str(out),'--data','work/qwen2_live_qkv_inputs/fixture','--out',str(out)])
                writer.assert_not_called()


if __name__=='__main__':unittest.main()
