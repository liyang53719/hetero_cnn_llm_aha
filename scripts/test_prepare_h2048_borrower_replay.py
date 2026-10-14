#!/usr/bin/env python3
"""Cold tests with a constructed fake observation tree; no model/RTL execution."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare_h2048_borrower_replay',
                                            Path(__file__).with_name('prepare_h2048_borrower_replay.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cold_h2048_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'work').mkdir()
        (self.root / '.gitignore').write_text('work/\n')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.out = self.root / 'work' / 'fresh_replay'
        self.summary = self.root / 'work' / 'summary.json'
        self.sources = {}
        for name in p.REQUIRED_OWNER_SOURCES + ('candidates/qwen35_35b_prefill/run_prefix.py',):
            path = self.root / name.removeprefix('HEAD:')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('cold fixture source: ' + name + '\n').encode())
            self.sources[name] = p.sha(path.read_bytes())
        self.head_patch = patch.object(p, 'git_blob', side_effect=lambda root, path: (root / path).read_bytes())
        self.mock_head = self.head_patch.start()
        self.addCleanup(self.head_patch.stop)
        self.make_summary(16)

    def record(self, name, data):
        path = self.root / 'work' / name
        path.write_bytes(data)
        return {'path': str(path), 'bytes': len(data), 'sha256': p.sha(data)}

    def make_summary(self, m):
        self.input = b''.join(struct.pack('<H', 0x3f00 + row) * p.WIDTH for row in range(m))
        self.weight = struct.pack('<H', 0x3e80) * p.WIDTH
        residual = self.record('residual.bf16le', self.input)
        output = self.record('output.bf16le', self.input)
        weights = self.record('weight.fp32le', p.expand_bf16(self.weight))
        rows = [dict(token=i, sum=0x3f800000 + i, mean=0x3e800000 + i,
                     variance=0x3e900000 + i, root=0x3f200000 + i, inverse=0x3f900000 + i)
                for i in range(m)]
        nodes = {}
        fields = {'sum': 'sum', 'mean': 'mean', 'mean_eps': 'variance', 'root': 'root', 'inverse': 'inverse'}
        for name in p.SCALAR_NODES + p.VECTOR_NODES:
            raw = (b''.join(struct.pack('<I', row[fields[name]]) for row in rows)
                   if name in fields else p.expand_bf16(self.input))
            nodes[name] = {'actual_observed': True, 'actual': self.record(name + '.fp32le', raw)}
        owner = dict(scope='PACKED_BF16_H2048_RMS_SOFTWARE_OWNER', shared_scalar_service_count=1,
                     retained_bf16_row_capacity=1024, retained_bf16_weight_capacity=1024,
                     retained_bf16_output_capacity=1024, retained_physical_bank_bytes=6144,
                     identity=dict(policy='torch210_cpu_default2048', source_sha256=dict(self.sources),
                                   implementation_sha256=self.sources['candidates/qwen35_35b_rms/owner.py']),
                     row_scalars=rows)
        source_report = dict(complete=True, output_published=True, status=None,
                             output_sha256=residual['sha256'])
        target_report = dict(complete=True, output_published=True, status=None,
                             output_sha256=output['sha256'], owner=owner,
                             input_sha256=[residual['sha256'], p.sha(self.weight)])
        observations = [dict(stage=stage) for stage in sorted(p.OBSERVATIONS)]
        for obs in observations:
            if obs['stage'] == 'attention_residual':
                obs.update(output=residual, owner=source_report)
            elif obs['stage'] == 'post_attention_norm':
                obs.update(output=output, owner=target_report)
        prefix_sources = {name: digest for name, digest in self.sources.items() if not name.startswith('HEAD:')}
        self.s = dict(tokens=m, sources_unchanged=True, native_artifacts_unchanged=True,
                      source_sha256=prefix_sources, source_sha256_after=dict(prefix_sources),
                      native_artifact_records=[self.record('native.fixture', b'opaque native fixture')],
                      arithmetic_source_sha256=dict(prefix_sources), observations=observations,
                      postnorm_reference_records={'weight_fp32': weights}, postnorm_actual_nodes=nodes,
                      reduction_policy='cold_fixture_does_not_claim_arithmetic_execution',
                      status='COLD_UNIT_TEST_NOT_ACTUAL_OBSERVATION',
                      execution=dict(tokens=m, status='COLD_UNIT_TEST_NOT_ACTUAL_OBSERVATION',
                                     terminals=[dict(stage=x, status=None) for x in p.TERMINALS],
                                     same_rms_owner_and_banks_reused=True, postnorm_matrix_vector_unchanged=True,
                                     postnorm_weight_sha256=p.sha(self.weight),
                                     stages=[dict(stage='post_attention_norm', report=target_report)]))
        self.repin_test_summary()

    def repin_test_summary(self):
        # Unit-test construction only. Production CLI never computes its own
        # input trust pin; tests deliberately supply a known fixture SHA.
        raw = (json.dumps(self.s, sort_keys=True) + '\n').encode()
        self.summary.write_bytes(raw)
        self.pin = p.sha(raw)

    def call(self, **kw):
        args = dict(root=self.root, summary=self.summary, summary_sha256=self.pin,
                    out=self.out, tokens=1, row_start=0)
        args.update(kw)
        return p.prepare(**args)

    def fails(self, message, **kw):
        with self.assertRaisesRegex(ValueError, message):
            self.call(**kw)
        self.assertFalse(self.out.exists())

    def obs(self, stage):
        return next(v for v in self.s['observations'] if v['stage'] == stage)

    def test_m1_row_slice_inputs_only_and_actual_expectations(self):
        result = self.call(row_start=7)
        manifest = json.loads((self.out / 'manifest.json').read_text())
        self.assertEqual(result['manifest_sha256'], p.sha((self.out / 'manifest.json').read_bytes()))
        self.assertEqual(manifest['allowed_dut_input_files'], ['stimulus/input.bf16le', 'stimulus/weights.bf16le'])
        self.assertEqual(set(x.name for x in (self.out / 'stimulus').iterdir()), {'input.bf16le', 'weights.bf16le'})
        self.assertEqual((self.out / 'stimulus/input.bf16le').read_bytes(), self.input[7*4096:8*4096])
        self.assertEqual((self.out / 'stimulus/weights.bf16le').read_bytes(), self.weight)
        self.assertEqual((self.out / 'expected/sum.fp32le').read_bytes(), struct.pack('<I', 0x3f800007))
        self.assertEqual((self.out / 'expected/inverse.fp32le').read_bytes(), struct.pack('<I', 0x3f900007))
        self.assertFalse(manifest['rtl_executed'])
        self.assertFalse(manifest['model_rerun'])
        for name, rec in manifest['files'].items():
            raw = (self.out / name).read_bytes()
            self.assertEqual((len(raw), p.sha(raw)), (rec['bytes'], rec['sha256']))
            self.assertEqual(rec['role'], 'DUT_MEMORY_INPUT' if name.startswith('stimulus/') else 'HOST_ASSERTION_ONLY')
        self.assertTrue(self.mock_head.called)

    def test_m16_entire_source(self):
        self.call(tokens=16)
        self.assertEqual((self.out / 'stimulus/input.bf16le').read_bytes(), self.input)
        self.assertEqual((self.out / 'expected/weighted.fp32le').stat().st_size, 16*2048*4)

    def test_m128_entire_source(self):
        self.make_summary(128)
        self.call(tokens=128)
        manifest = json.loads((self.out / 'manifest.json').read_text())
        self.assertEqual(manifest['runner_contract']['expected_scalar_requests'], 128*4268)
        self.assertEqual(manifest['runner_contract']['expected_loan_requests'], 128*128)
        self.assertEqual(manifest['files']['expected/inverse.fp32le']['shape'], [128])

    def test_cli_requires_pin(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            p.main(['--root', str(self.root), '--summary', str(self.summary), '--out', str(self.out), '--tokens', '1'])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.out.exists())

    def test_wrong_pin(self):
        self.fails('summary SHA256', summary_sha256='0'*64)

    def test_malformed_pin(self):
        self.fails('explicit lowercase SHA256', summary_sha256='not-a-pin')

    def test_full_shape_mismatch(self):
        self.fails('entire matching producer', tokens=128)

    def test_full_shape_nonzero_offset(self):
        self.fails('entire matching producer', tokens=16, row_start=1)

    def test_slice_out_of_range(self):
        self.fails('row_start range', row_start=16)

    def test_invalid_output_exists(self):
        self.out.mkdir()
        marker = self.out / 'preserved'
        marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'fresh output'):
            self.call()
        self.assertEqual(marker.read_text(), 'keep')

    def test_dangling_output_symlink(self):
        self.out.symlink_to(self.root / 'no-such-target')
        with self.assertRaisesRegex(ValueError, 'fresh output'):
            self.call()
        self.assertTrue(self.out.is_symlink())

    def test_output_not_ignored(self):
        (self.root / '.gitignore').write_text('')
        self.fails('Git-ignored')

    def test_output_outside_work(self):
        self.fails('direct child', out=self.root / 'outside')

    def test_source_changed(self):
        (self.root / 'candidates/qwen35_35b_rms/owner.py').write_text('drift')
        self.fails('current producer source SHA256')

    def test_committed_scalar_changed(self):
        self.mock_head.side_effect = lambda root, path: b'wrong committed source'
        self.fails('committed producer source SHA256')

    def test_native_artifact_changed(self):
        Path(self.s['native_artifact_records'][0]['path']).write_bytes(b'x')
        self.fails('record byte count')

    def test_actual_observation_changed(self):
        rec = self.s['postnorm_actual_nodes']['inverse']['actual']
        raw = Path(rec['path']).read_bytes()
        Path(rec['path']).write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        self.fails('record SHA256')

    def test_expected_must_be_observed(self):
        self.s['postnorm_actual_nodes']['inverse']['actual_observed'] = False
        self.repin_test_summary()
        self.fails('expected must be actual observed')

    def test_expected_shape(self):
        self.s['postnorm_actual_nodes']['sum']['actual']['bytes'] += 4
        self.repin_test_summary()
        self.fails('record shape')

    def test_original_checkpoint_weight_identity(self):
        self.s['execution']['postnorm_weight_sha256'] = '0'*64
        self.repin_test_summary()
        self.fails('checkpoint BF16 weight identity')

    def test_weight_not_lossless_bf16(self):
        rec = self.s['postnorm_reference_records']['weight_fp32']
        raw = bytearray(Path(rec['path']).read_bytes()); raw[0] = 1
        Path(rec['path']).write_bytes(raw); rec['sha256'] = p.sha(raw)
        self.repin_test_summary()
        self.fails('exact BF16 expansion')

    def test_consumed_input_identity(self):
        self.obs('post_attention_norm')['owner']['input_sha256'][0] = '0'*64
        self.repin_test_summary()
        self.fails('consumed these exact')

    def test_row_scalar_identity(self):
        self.obs('post_attention_norm')['owner']['owner']['row_scalars'][0]['inverse'] ^= 1
        self.repin_test_summary()
        self.fails('row-scalar/node identity')

    def test_duplicate_observation(self):
        self.s['observations'].append(self.s['observations'][0])
        self.repin_test_summary()
        self.fails('complete unique')

    def test_failed_terminal(self):
        self.s['execution']['terminals'][-1]['status'] = 'failure'
        self.repin_test_summary()
        self.fails('successful ordered')

    def test_unsealed_summary(self):
        self.s['sources_unchanged'] = False
        self.repin_test_summary()
        self.fails('sealed producer')

    def test_source_outside_checkout(self):
        with tempfile.TemporaryDirectory(prefix='cold_h2048_escape_') as elsewhere:
            outside = Path(elsewhere) / 'input'; outside.write_bytes(self.input)
            self.obs('attention_residual')['output']['path'] = str(outside)
            self.repin_test_summary()
            self.fails('source outside checkout')

    def test_bf16_output_expansion_mismatch(self):
        rec = self.s['postnorm_actual_nodes']['output']['actual']
        raw = bytearray(Path(rec['path']).read_bytes()); raw[0] ^= 1
        Path(rec['path']).write_bytes(raw); rec['sha256'] = p.sha(raw)
        self.repin_test_summary()
        self.fails('FP32-expanded BF16 output identity')

    def test_weighted_rounding_mismatch(self):
        rec = self.s['postnorm_actual_nodes']['weighted']['actual']
        raw = bytearray(Path(rec['path']).read_bytes()); raw[2] ^= 1
        Path(rec['path']).write_bytes(raw); rec['sha256'] = p.sha(raw)
        self.repin_test_summary()
        self.fails('weighted-to-BF16 RNE')

    def test_duplicate_json_keys(self):
        self.summary.write_bytes(b'{"tokens":16,"tokens":128}')
        self.pin = p.sha(self.summary.read_bytes())
        self.fails('duplicate JSON key')


if __name__ == '__main__':
    unittest.main(verbosity=2)
