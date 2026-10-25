"""Stdlib-only checks of FRESH capture outputs. Never a replacement oracle.

This module imports no numerical package. Validation is invoked only inside the
capability-authorized worker after the two actual ordered official layer calls.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import struct
from gate_common import file_id, need

TOKENS = 128


def wide_bf16(raw):
    need(len(raw) % 2 == 0, 'unaligned BF16')
    out = bytearray(len(raw) * 2)
    out[2::4], out[3::4] = raw[0::2], raw[1::2]
    return bytes(out)


def bf16_rne(value):
    word = struct.unpack('<I', struct.pack('<f', value))[0]
    need((word & 0x7f800000) != 0x7f800000, 'nonfinite semantic intermediate')
    return ((word + 0x7fff + ((word >> 16) & 1)) >> 16) & 0xffff


def words(raw):
    return [v[0] for v in struct.iter_unpack('<H', raw)]


def floats(raw):
    return [v[0] for v in struct.iter_unpack('<f', raw)]


def reorder_bf16(raw, old_shape, new_axes):
    old_strides = [math.prod(old_shape[i + 1:]) for i in range(len(old_shape))]
    new_shape = [old_shape[a] for a in new_axes]
    new_strides = [math.prod(new_shape[i + 1:]) for i in range(len(new_shape))]
    out = bytearray(len(raw))
    for target in range(math.prod(old_shape)):
        old = 0
        rem = target
        for stride, axis in zip(new_strides, new_axes):
            coordinate, rem = divmod(rem, stride)
            old += coordinate * old_strides[axis]
        out[2*target:2*target+2] = raw[2*old:2*old+2]
    return bytes(out)


def repeat_heads(raw, heads=2, repeats=6, tokens=TOKENS, dim=128):
    stride = tokens * dim * 2
    need(len(raw) == heads * stride, 'cold head-repeat geometry')
    return b''.join(raw[h*stride:(h+1)*stride] * repeats for h in range(heads))


def elementwise_relation(a, b, expected, op):
    av, bv, wanted = floats(wide_bf16(a)), floats(wide_bf16(b)), words(expected)
    need(len(av) == len(bv) == len(wanted), 'semantic elementwise geometry')
    mismatches = sum(bf16_rne(x + y if op == 'add' else x * y) != w
                     for x, y, w in zip(av, bv, wanted))
    need(mismatches == 0, 'BF16 ' + op + ' semantic mismatch count: ' + str(mismatches))
    return {'elements': len(wanted), 'mismatches': mismatches, 'rounding': 'FP32 then BF16 round-to-nearest-even'}


def validate_pair(config, output, report, observed_native):
    profile = config['capture_profile']
    need(profile['name'] == 'fresh_m128_same_layer_baseline_then_observed_v1' and
         profile.get('geometry') == 'fresh_cold_chunk128_v1' and
         profile.get('tokens') == TOKENS and profile.get('chunk_count') == 1 and
         profile['layer_instances'] == 1 and profile['forward_calls'] == 2 and
         profile['arm_order'] == ['baseline_no_capture_observer', 'observed_all29'], 'wrong paired execution profile')
    need(report['capture_profile'] == profile, 'capture pair profile drift')
    need(report['layer_instance_count'] == 1 and report['forward_call_count'] == 2, 'one layer/two forwards required')
    need(report['baseline_layer_call_started'] is True and report['baseline_layer_call_returned'] is True, 'baseline missing or incomplete')
    controls = report['baseline_controls']
    for key in ('capture_trace_absent', 'module_hooks_absent', 'global_module_hooks_absent', 'eval', 'no_grad', 'safety_profile_remains_active'):
        need(controls[key] is True, 'baseline control not evidenced: ' + key)
    need(controls['attention_dropout'] == 0.0, 'baseline dropout not zero')
    states = report['state_checkpoints']
    need(set(states) == {'before_baseline', 'after_baseline', 'after_observed'}, 'three full original-state checkpoints required')
    before = states['before_baseline']
    need(before == states['after_baseline'] == states['after_observed'], 'original inputs/parameters/buffers or object identities changed across arms')
    need(set(before['inputs']) == {'x', 'mask', 'positions'} and len(before['parameters']) == 12,
         'complete original input/parameter identity/hash evidence required')
    need(set(before['buffers']) == {'self_attn.rotary_emb.inv_freq', 'self_attn.rotary_emb.cos_cached', 'self_attn.rotary_emb.sin_cached'}, 'complete original rotary buffers required')
    for group in ('inputs', 'parameters', 'buffers'):
        for name, item in before[group].items():
            need(type(item.get('object_id')) is str and item['object_id'].startswith('0x'), 'original object identity missing: ' + group + '/' + name)
            need(type(item.get('native_sha256')) is str and len(item['native_sha256']) == 64 and item['native_bytes'] > 0, 'native state evidence missing')
    need(report['baseline_state_unchanged']['passed'] is True and report['observed_state_unchanged']['passed'] is True, 'state equality not checked')
    comparison = report['pair_output_comparison']
    need(comparison['passed'] is True and comparison['all29_intermediate_noninterference_claimed'] is False, 'pair equality missing or scope overstated')
    need(set(comparison['outputs']) == {'y', 'prob'} and set(report['baseline_exports']) == {'y', 'prob'}, 'baseline y/prob evidence missing')
    baseline_dir = output / 'baseline'
    need({p.name for p in baseline_dir.iterdir()} == {'y.native.bin', 'prob.native.bin'}, 'unexpected/missing baseline exports')
    identities = {}
    for name in ('y', 'prob'):
        record = report['baseline_exports'][name]
        need(record['file'] == 'baseline/' + name + '.native.bin', 'baseline filename substitution')
        need(record['shape'] == config['output_contract'][name]['shape'] and record['native_dtype'] == 'bfloat16', 'baseline geometry/dtype mismatch')
        path = output / record['file']
        actual = path.read_bytes()
        need(actual == observed_native[name], 'baseline/observed actual output bytes differ: ' + name)
        digest = hashlib.sha256(actual).hexdigest()
        item = comparison['outputs'][name]
        need(item['byte_identical'] is True and item['native_bytes'] == record['native_bytes'] == len(actual), 'baseline byte comparison metadata mismatch')
        need(item['baseline_sha256'] == item['observed_sha256'] == record['native_sha256'] == digest, 'baseline/comparison native hash mismatch')
        identities[name] = file_id(path)
    return {'passed': True, 'layer_instances': 1, 'forward_calls': 2,
            'baseline_files': identities, 'same_original_object_identities': True,
            'input_parameter_buffer_native_hashes_unchanged': True,
            'baseline_and_observed_y_prob_native_bytes_identical': True,
            'all29_baseline_intermediates_observed': False,
            'claim_scope': 'Only y/prob actual return equality and boundary original input/parameter/buffer state, not all29 intermediate noninterference.'}


def validate_capture(config, capture_dir, report):
    output = Path(capture_dir)
    need(report['status'] == 'PAIR_CAPTURE_COMPLETE_NOT_NUMERIC_PASS', 'capture not complete')
    need(report['official_layer_call_started'] is True and report['official_layer_call_returned'] is True, 'official call did not return')
    need(report['numeric_acceptance'] == 'NOT_RUN' and report['dut_comparison'] == 'NOT_RUN', 'invalid inherited numeric result')
    need(report['full_model_forward_executed'] is False and report['dynamic_cache_executed'] is False, 'wrong model/cache scope')
    need(report['legacy_results_inherited'] is False and report['source_rewritten'] is False, 'legacy/source contamination')
    fields = config['output_contract']
    need(len(fields) == 29 and set(report['exports']) == set(fields), 'all29 exact export set required')
    expected_files = {n + suffix for n in fields for suffix in ('.native.bin', '.f32.bin')}
    need({p.name for p in output.glob('*.bin')} == expected_files, 'unexpected/missing tensor output')
    raw, f32, identities = {}, {}, {}
    for name, spec in fields.items():
        item = report['exports'][name]
        need(item['shape'] == spec['shape'] and item['native_dtype'] == spec['dtype'], 'geometry/dtype drift: ' + name)
        need(item['device'] == 'cpu', 'non-CPU field: ' + name)
        need(item['native_file'] == name + '.native.bin' and item['fp32_file'] == name + '.f32.bin', 'output filename substitution')
        raw[name] = (output / item['native_file']).read_bytes()
        f32[name] = (output / item['fp32_file']).read_bytes()
        native_size = math.prod(spec['shape']) * (2 if spec['dtype'] == 'bfloat16' else 4)
        need(len(raw[name]) == item['native_bytes'] == native_size, 'native length mismatch: ' + name)
        need(len(f32[name]) == item['fp32_bytes'] == spec['export_f32_bytes'], 'f32 length mismatch: ' + name)
        need(hashlib.sha256(raw[name]).hexdigest() == item['native_sha256'], 'native hash mismatch: ' + name)
        need(hashlib.sha256(f32[name]).hexdigest() == item['fp32_sha256'], 'f32 hash mismatch: ' + name)
        need(f32[name] == (wide_bf16(raw[name]) if spec['dtype'] == 'bfloat16' else raw[name]), 'not exact native-to-FP32 export: ' + name)
        nonfinite = sum((x[0] & 0x7f800000) == 0x7f800000 for x in struct.iter_unpack('<I', f32[name]))
        need(nonfinite == item['nonfinite_count'] == 0, 'nonfinite field: ' + name)
        identities[name] = {'native': file_id(output / item['native_file']), 'f32': file_id(output / item['fp32_file']),
                            'shape': spec['shape'], 'native_dtype': spec['dtype'], 'finite': True}
    pair_validation = validate_pair(config, output, report, raw)
    embedding = next(p for p in config['raw13'] if p['local_name'] == 'embed_tokens.rows_0_255')
    with Path(embedding['path']).open('rb') as stream:
        original_x = stream.read(TOKENS * 1536 * 2)
    need(raw['x'] == original_x, 'x not original raw13 rows0:128')
    mask = b''.join(struct.pack('<H', 0xff7f if k > q else 0) for q in range(TOKENS) for k in range(TOKENS))
    need(raw['mask'] == mask, 'explicit cold BF16 mask bit mismatch')
    need(raw['cache_k'] == raw['k'], 'cold cache_k alias values differ')
    need(raw['cache_v'] == reorder_bf16(raw['v'], [1, TOKENS, 2, 128], [0, 2, 1, 3]), 'cold cache_v transpose differs')
    for which in ('k', 'v'):
        need(raw['repeat_' + which] == repeat_heads(raw['cache_' + which]), 'GQA 6x repeat mismatch: ' + which)
    need(raw['att'] == reorder_bf16(raw['pv'], [1, 12, TOKENS, 128], [0, 2, 1, 3]), 'PV-to-att transpose/reshape mismatch')
    relations = {'r_equals_bf16_x_plus_o': elementwise_relation(raw['x'], raw['o'], raw['r'], 'add'),
                 'y_equals_bf16_r_plus_down': elementwise_relation(raw['r'], raw['down'], raw['y'], 'add'),
                 'act_equals_bf16_silu_times_up': elementwise_relation(raw['silu'], raw['up'], raw['act'], 'multiply')}
    sf = floats(f32['softmax_fp32'])
    pw = words(raw['prob'])
    need(all(bf16_rne(x) == w for x, w in zip(sf, pw)), 'prob not actual softmax return BF16 rounding')
    need(all(0 <= x <= 1 for x in sf), 'FP32 softmax outside probability range')
    probability = floats(f32['prob'])
    sw, lw = words(raw['scores']), words(raw['logits'])
    future = causal = 0
    softmax_words = [x[0] for x in struct.iter_unpack('<I', raw['softmax_fp32'])]
    row_errors, bf16_row_errors = [], []
    for head in range(12):
        for query in range(TOKENS):
            row = (head * TOKENS + query) * TOKENS
            row_errors.append(abs(math.fsum(sf[row:row+TOKENS]) - 1.0))
            bf16_row_errors.append(abs(math.fsum(probability[row:row+TOKENS]) - 1.0))
            for key in range(TOKENS):
                i = row + key
                if key > query:
                    future += 1
                    need(pw[i] == 0 and softmax_words[i] == 0, 'future probability must be positive-zero bits')
                    score = struct.unpack('<f', struct.pack('<I', sw[i] << 16))[0]
                    minimum = struct.unpack('<f', struct.pack('<I', 0xff7f0000))[0]
                    need(lw[i] == bf16_rne(score + minimum), 'future masked logits mismatch')
                else:
                    causal += 1
                    need(lw[i] == sw[i], 'causal logits must preserve scores')
    tolerance = config['comparison_gates']['rowsum_abs_error_lte']
    need(tolerance == 2e-5, 'original FP32 row-sum tolerance changed')
    need(max(row_errors) <= tolerance, 'actual FP32 softmax row-sum gate failed')
    # Fresh hashes are content identities, not expected answers or prior PASS.
    return {'status': 'ALL29_CAPTURE_SELF_CHECKS_PASSED_NOT_DUT_ACCEPTANCE', 'passed': True,
            'fields': identities, 'semantic_relations': relations, 'pair_validation': pair_validation,
            'structural_relations': ['raw13 x prefix', 'exact causal mask', 'cold k alias', 'cold v transpose',
                                    'GQA 6x k/v repeat', 'PV-to-att transpose/reshape', 'prob BF16 cast', 'causal/future mask domains'],
            'future_probability_positive_zero_count': future, 'causal_positions': causal,
            'softmax_fp32_rows': len(row_errors), 'softmax_fp32_rowsum_abs_max': max(row_errors),
            'softmax_fp32_rowsum_abs_lte': tolerance,
            'bf16_prob_rowsum_abs_max_diagnostic_only': max(bf16_row_errors),
            'bf16_prob_rowsum_hard_gate_added': False, 'all29_finite': True,
            'expected_output_hashes': None, 'old_reference_pass_inherited': False,
            'dut_comparison': 'NOT_RUN', 'numeric_acceptance': 'NOT_RUN',
            'comparison_tolerances_unchanged_not_applied': config['comparison_gates'],
            'scope_limit': 'All29 are observed-arm consistency checks; same-instance baseline/observed equality is checked only for actual y/prob returns and original input/parameter/buffer boundary state.'}
