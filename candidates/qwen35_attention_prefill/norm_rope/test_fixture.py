"""Bounded NumPy/stdlib tests with synthetic capture metadata and raw files."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from . import compare, fixture


def synthetic_capture(rows=16, directory=None):
    contract = fixture.load_contract()
    manifest = dict(query_tokens=rows, contract_sha256=fixture.CONTRACT_SHA256,
                    original_producer_sequence=deepcopy(contract['producer_sequence']),
                    model_id=contract['model_id'], revision=contract['revision'], tensors={}, cases=[], parameters={})
    payload = dict(model_id=contract['model_id'], revision=contract['revision'], tensors=[])
    for role, digest in fixture.WEIGHT_SHA256.items():
        meta = dict(shape=[256], dtype='BF16', bytes=512, sha256=digest)
        name = 'self_attn.' + role + '.weight'
        manifest['parameters']['layers.3.' + name] = meta
        payload['tensors'].append(dict(meta, local_name=name, file=role + '.bf16le'))

    def ref(name):
        return {'tensor': name}

    def tensor(name, shape, dtype='BF16'):
        raw = bytes(int(np.prod(shape)) * {'BF16': 2, 'F32': 4, 'I64': 8}[dtype])
        filename = f'{len(manifest["tensors"]):04}.raw'
        manifest['tensors'][name] = dict(shape=list(shape), dtype=dtype, bytes=len(raw), sha256=fixture.sha(raw), file=filename)
        if directory is not None:
            (Path(directory) / filename).write_bytes(raw)
        return name

    for window, base in (('cold', 0), ('carried', 128)):
        name = window + str(rows)
        case = dict(name=name, position_span=[base, base + rows], past_tokens=0 if base == 0 else rows,
                    module_boundaries={}, dispatch_events=[], function_observations=[])
        for key, shape, dtype in (('rope_cos', (1, rows, 64), 'BF16'), ('rope_sin', (1, rows, 64), 'BF16'),
                                 ('position_ids', (1, rows), 'I64'), ('rope_position_ids', (3, 1, rows), 'I64')):
            case[key] = tensor(name + '.' + key, shape, dtype)

        def event(index, op, args, shape, dtype='BF16', module='self_attn', result=None):
            result = ref(tensor(f'{name}.event{index}', shape, dtype)) if result is None else result
            value = dict(index=index, module=module, op=op, args=args, kwargs={}, result=result)
            case['dispatch_events'].append(value)
            return result

        def function(kind, values):
            case['function_observations'].append(dict(function=kind, invocation=0,
                observation='original Python return-frame locals', values=values))

        packed = tensor(name + '.packed', (1, rows, 4096))
        kprojected = tensor(name + '.kprojected', (1, rows, 512))
        case['module_boundaries']['self_attn.q_proj'] = {'output': {'result': ref(packed)}}
        case['module_boundaries']['self_attn.k_proj'] = {'output': {'result': ref(kprojected)}}
        view = event(11, 'aten.view.default', [ref(packed), [1, rows, -1, 512]], (1, rows, 8, 512))
        qinput = ref(tensor(name + '.qinput', (1, rows, 8, 256)))
        gateinput = ref(tensor(name + '.gateinput', (1, rows, 8, 256)))
        event(12, 'aten.chunk.default', [view, 2, -1], (), result=[qinput, gateinput])
        gate = event(13, 'aten.reshape.default', [gateinput, [1, rows, -1]], (1, rows, 2048))
        kinput = event(27, 'aten.view.default', [ref(kprojected), [1, rows, -1, 256]], (1, rows, 2, 256))
        function('attention', {'gate': gate})
        head_major = {}
        for role, heads, start, source in (('q', 8, 15, qinput), ('k', 2, 28, kinput)):
            module, shape = 'self_attn.' + role + '_norm', (1, rows, heads, 256)

            def norm_event(offset, op, args, shape=shape, dtype='F32'):
                return event(start + offset, op, args, shape, dtype, module)

            cast = norm_event(0, 'aten.to.dtype', [source, {'torch_type': 'torch.float32'}])
            squares = norm_event(1, 'aten.pow.Tensor_Scalar', [cast, 2])
            mean = norm_event(2, 'aten.mean.dim', [squares, [-1], True], (1, rows, heads, 1))
            mean_eps = norm_event(3, 'aten.add.Tensor', [mean, 1e-6], (1, rows, heads, 1))
            inverse = norm_event(4, 'aten.rsqrt.default', [mean_eps], (1, rows, heads, 1))
            scaled = norm_event(5, 'aten.mul.Tensor', [cast, inverse])
            weight = norm_event(6, 'aten.to.dtype', [{'parameter': 'layers.3.' + module + '.weight'},
                                                   {'torch_type': 'torch.float32'}], (256,))
            gamma = norm_event(7, 'aten.add.Tensor', [weight, 1.0], (256,))
            weighted = norm_event(8, 'aten.mul.Tensor', [scaled, gamma])
            output = norm_event(9, 'aten.type_as.default', [weighted, source], dtype='BF16')
            case['module_boundaries'][module] = dict(input=dict(args=[source], kwargs={}), output=dict(result=output))
            function('norm', dict(module=module, input=source, result=output, fp32_weighted_output=weighted))
            function('norm_core', dict(module=module, input=cast, result=scaled))
            head_major[role] = event(25 if role == 'q' else 38, 'aten.transpose.int', [output, 1, 2], (1, heads, rows, 256))
        rope = {}
        for label, index in (('cos', 42), ('sin', 43)):
            rope[label] = event(index, 'aten.unsqueeze.default', [ref(case['rope_' + label]), 1], (1, 1, rows, 64))
        for role, heads, start, terminal, sl in (('q', 8, 48, 62, 44), ('k', 2, 55, 63, 46)):
            norm, shape = head_major[role], (1, heads, rows, 64)
            rope[role] = norm
            rot = rope[role + '_rot'] = event(sl, 'aten.slice.Tensor', [norm, 3, 0, 64], shape)
            tail = rope[role + '_pass'] = event(sl + 1, 'aten.slice.Tensor', [norm, 3, 64, 9223372036854775807], (1, heads, rows, 192))
            cos = event(start, 'aten.mul.Tensor', [rot, rope['cos']], shape)
            first = event(start + 1, 'aten.slice.Tensor', [rot, 3, 0, 32], (1, heads, rows, 32))
            second = event(start + 2, 'aten.slice.Tensor', [rot, 3, 32, 9223372036854775807], (1, heads, rows, 32))
            neg = event(start + 3, 'aten.neg.default', [second], (1, heads, rows, 32))
            rotate = event(start + 4, 'aten.cat.default', [[neg, first], -1], shape)
            sin = event(start + 5, 'aten.mul.Tensor', [rotate, rope['sin']], shape)
            result = event(start + 6, 'aten.add.Tensor', [cos, sin], shape)
            rope[role + '_embed'] = event(terminal, 'aten.cat.default', [[result, tail], -1], (1, heads, rows, 256))
        function('rope', rope)
        case['dispatch_events'].sort(key=lambda e: e['index'])
        manifest['cases'].append(case)
    return manifest, payload, contract


def actual_data(rows=16):
    observations, outputs, terminals = {}, {}, {}
    for role, (heads, widths) in compare.ROLES.items():
        recorder = compare.ObservationRecorder(rows, heads, 'norm' if role.endswith('norm') else 'rope')
        for stage, width in widths.items():
            for token in range(rows):
                for head in range(heads):
                    recorder(stage, token, head, (0,) * width)
        observations[role] = recorder.events
        outputs[role] = bytes(rows * heads * 512)
    outputs['raw_gate'] = bytes(rows * 8 * 512)
    outputs['packed_q_gate'] = bytes(rows * 8 * 1024)
    for role, (heads, _) in compare.ROLES.items():
        names = ('q_norm', 'raw_gate') if role == 'q_norm' else (role,)
        count = rows * heads * 512 * len(names)
        terminals[role] = dict(complete=True, status=None, output_published=[True] * len(names),
            counts={'ack_bytes': count}, output_sha256=[fixture.sha(outputs[n]) for n in names],
            owner=dict(status=None, accepted={'owner_results': 1}, acknowledged_write_bytes=count))
    return observations, outputs, terminals


class FixtureTests(unittest.TestCase):
    def test_full_geometry_and_twenty_two_bindings(self):
        for rows in (16, 128):
            manifest, _, contract = synthetic_capture(rows)
            for case in manifest['cases']:
                refs = fixture.select_case_references(manifest, case, contract)
                self.assertEqual(len(refs), 27)
                self.assertEqual(sum(r['producer_key'] is not None for r in refs.values()), 22)
                self.assertEqual(refs['q_norm.gamma']['shape'], [256])
                self.assertEqual(refs['q_rope.output']['shape'], [1, 8, rows, 256])

    def test_reject_bad_metadata_layout_keys_duplicate(self):
        for defect in ('gamma_shape', 'operation', 'dataflow', 'duplicate', 'rope_function', 'dtype', 'contract', 'position'):
            with self.subTest(defect=defect):
                manifest, _, contract = synthetic_capture()
                case = manifest['cases'][0]
                events = {e['index']: e for e in case['dispatch_events']}
                if defect == 'gamma_shape':
                    manifest['tensors'][events[22]['result']['tensor']]['shape'] = [1, 256]
                elif defect == 'operation':
                    events[53]['op'] = 'aten.add.Tensor'
                elif defect == 'dataflow':
                    events[23]['args'][0] = events[22]['result']
                elif defect == 'duplicate':
                    case['dispatch_events'].insert(0, deepcopy(case['dispatch_events'][0]))
                elif defect == 'rope_function':
                    next(f for f in case['function_observations'] if f['function'] == 'rope')['values']['q_embed'] = events[63]['result']
                elif defect == 'dtype':
                    manifest['tensors'][events[25]['result']['tensor']]['dtype'] = 'F32'
                elif defect == 'contract':
                    contract['producer_sequence'][9]['storage_dtype'] = 'bfloat16'
                else:
                    case['position_span'] = [16, 32]
                with self.assertRaises(ValueError):
                    fixture.select_case_references(manifest, case, contract)

    def test_pinned_original_gamma_weights_only(self):
        manifest, payload, _ = synthetic_capture()
        self.assertEqual(set(fixture.select_norm_weights(manifest, payload)), {'q_norm', 'k_norm'})
        for defect in ('duplicate', 'shape', 'precomputed', 'captured'):
            m, p = deepcopy(manifest), deepcopy(payload)
            if defect == 'duplicate':
                p['tensors'].append(deepcopy(p['tensors'][0]))
            elif defect == 'shape':
                p['tensors'][0]['shape'] = [1, 256]
            elif defect == 'precomputed':
                p['tensors'][0]['sha256'] = '0' * 64
            else:
                m['parameters']['layers.3.self_attn.q_norm.weight']['dtype'] = 'F32'
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                fixture.select_norm_weights(m, p)

    def test_absolute_trig_table_and_explicit_unread_gap(self):
        raw = lambda value: np.full((1, 16, 64), value, dtype='<u2').tobytes()
        cases = dict(cold16=dict(cos=raw(0x3f80), sin=raw(0)), carried16=dict(cos=raw(0x3f00), sin=raw(0x3e80)))
        table, provenance = fixture.build_trig_table(cases, 16)
        words = np.frombuffer(table, '<u2').reshape(256, 64)
        self.assertTrue(np.all(words[0:16, :32] == 0x3f80))
        self.assertTrue(np.all(words[128:144, :32] == 0x3f00))
        self.assertTrue(np.all(words[128:144, 32:] == 0x3e80))
        self.assertFalse(words[16:128].any())
        self.assertFalse(words[144:].any())
        self.assertEqual(provenance['zero_filled_unread_spans'], [[16, 128], [144, 256]])
        self.assertFalse(provenance['independent_trig_generation'])
        for value in (raw(0x7f80), raw(0x3f80)[:-2], np.arange(16 * 64, dtype='<u2').tobytes()):
            bad = deepcopy(cases)
            bad['carried16']['cos'] = value
            with self.assertRaises(ValueError):
                fixture.build_trig_table(bad, 16)

    def test_observer_rejects_duplicates_bad_shape_dtype_and_partial(self):
        recorder = compare.ObservationRecorder(16, 8, 'norm')
        recorder('sum', 0, 0, (0,))
        with self.assertRaises(ValueError):
            recorder('sum', 0, 0, (0,))
        for args in (('unknown', 0, 0, (0,)), ('sum', 16, 0, (0,)), ('sum', 0, 1, (0, 0)),
                     ('sum', 0, 1, (False,)), ('output', 0, 1, (1,) * 256), ('sum', 0, 1, (0x7f800000,))):
            with self.assertRaises(ValueError):
                recorder(*args)
        observations, _, _ = actual_data()
        del observations['q_norm']['squares', 0, 0]
        with self.assertRaises(compare.IncompleteObservations):
            compare.validate_observations(observations, 16)

    def test_gamma_must_be_identical_across_heads(self):
        observations, _, _ = actual_data()
        observations['q_norm']['gamma', 0, 1] = (0x3f800000,) * 256
        with self.assertRaises(ValueError):
            compare.validate_observations(observations, 16)

    def test_terminal_and_writeback_failures_before_native_read(self):
        manifest, _, _ = synthetic_capture()
        for defect in ('incomplete', 'failed', 'owner_failed', 'unpublished', 'no_terminal', 'ack', 'owner_ack',
                       'hash', 'observer', 'shape', 'gate', 'tail'):
            observations, outputs, terminals = actual_data()
            evidence = terminals['q_norm']
            if defect == 'incomplete': evidence['complete'] = False
            elif defect == 'failed': evidence['status'] = 'Memory'
            elif defect == 'owner_failed': evidence['owner']['status'] = 'Observer'
            elif defect == 'unpublished': evidence['output_published'][1] = False
            elif defect == 'no_terminal': evidence['owner']['accepted']['owner_results'] = 0
            elif defect == 'ack': evidence['counts']['ack_bytes'] -= 64
            elif defect == 'owner_ack': evidence['owner']['acknowledged_write_bytes'] -= 64
            elif defect == 'hash': evidence['output_sha256'][0] = '0' * 64
            elif defect == 'observer': observations['q_norm']['output', 0, 0] = (0x3f800000,) * 256
            elif defect == 'shape': outputs['q_norm'] = outputs['q_norm'][:-2]
            elif defect == 'gate': outputs['packed_q_gate'] = bytes(512) + b'\x80\x3f' + outputs['packed_q_gate'][514:]
            else:
                altered = list(observations['q_rope']['output', 0, 0]); altered[64] = 0x3f800000
                observations['q_rope']['output', 0, 0] = tuple(altered)
                outputs['q_rope'] = outputs['q_rope'][:128] + b'\x80\x3f' + outputs['q_rope'][130:]
                terminals['q_rope']['output_sha256'][0] = fixture.sha(outputs['q_rope'])
            with self.subTest(defect=defect), patch.object(compare.input_fixture, 'read_tensor') as read:
                with self.assertRaises(ValueError):
                    compare.compare_case('cold16', observations, outputs, manifest, '/unused', terminal_evidence=terminals)
                read.assert_not_called()

    def test_partial_observations_are_not_pass_and_do_not_read_native(self):
        manifest, _, _ = synthetic_capture()
        observations, outputs, terminals = actual_data()
        del observations['q_rope']['cos_product', 0, 0]
        with patch.object(compare.input_fixture, 'read_tensor') as read:
            report = compare.compare_case('cold16', observations, outputs, manifest, '/unused', terminal_evidence=terminals)
            read.assert_not_called()
        self.assertEqual(report['status'], 'INCOMPLETE_ACTUAL_OBSERVATIONS')
        self.assertFalse(report['complete'])
        self.assertFalse(report['all_computed_stages_pass'])
        self.assertEqual(len(report['uncomputed_required_producer_keys']), 57)

    def test_complete_comparison_is_partial_scope_and_preserves_fp32_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, _, _ = synthetic_capture(directory=directory)
            observations, outputs, terminals = actual_data()
            before = {p.name: p.read_bytes() for p in Path(directory).iterdir()}
            report = compare.compare_case('cold16', observations, outputs, manifest, directory, terminal_evidence=terminals)
            self.assertEqual(report['status'], 'PASS_22_OF_57_PARTIAL_SCOPE')
            self.assertEqual(report['computed_required_producers'], 22)
            self.assertEqual(len(report['uncomputed_required_producer_keys']), 35)
            self.assertFalse(report['full_contract_accepted'])
            self.assertFalse(report['native_acceptance'])
            self.assertEqual(len(report['stages']), 27)
            observations['q_norm']['squares', 0, 0] = (0x3f800000,) + (0,) * 255
            failed = compare.compare_case('cold16', observations, outputs, manifest, directory, terminal_evidence=terminals)
            self.assertEqual(failed['status'], 'FAIL_ORIGINAL_NATIVE_THRESHOLDS')
            self.assertEqual(failed['first_fp32_difference']['producer_key'], 'self_attn.q_norm|aten.pow.Tensor_Scalar|0')
            self.assertEqual(failed['first_fp32_difference']['first_bit_difference']['candidate_word'], '0x3f800000')
            self.assertEqual(failed['stages']['q_norm.squares']['max_abs_limit'], 0.03125)
            self.assertEqual(failed['stages']['q_norm.squares']['mean_abs_limit'], 0.005)
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(directory).iterdir()})


if __name__ == '__main__':
    unittest.main()
