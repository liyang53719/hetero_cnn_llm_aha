"""Read-only actual L3 observations against the frozen full-shape capture.

No missing arithmetic is supplied by a reference. In particular the fused
causal owner does not materialize the native mask-add tensor: that producer
stays absent and the original 57-producer contract cannot be closed by this
comparator. A successful complete command chain and numerical acceptance are
reported separately. Original absolute/mean limits are unchanged.
"""
from collections import Counter
import numpy as np

from . import full_fixture
from .input_fixture import read_tensor, require
from .norm_rope.fixture import load_contract, select_case_references, NORM_FIELDS
from .norm_rope.compare import observation_arrays, _metrics
from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16


RMS_WIDTHS = dict(squares=1024, sum=1, mean=1, mean_eps=1, inverse=1,
                  scaled=1024, gamma=1024, weighted=1024, output=1024)
GQA_STAGES = ('qk_bf16', 'scaled_scores_bf16', 'probability_fp32',
              'probabilities_bf16', 'context_bf16')


class FullObservations:
    """Host-only immutable-word collection; callback returns are unused."""
    def __init__(self, rows, cache_length):
        require(type(rows) is int and 1 <= rows <= 128 and type(cache_length) is int
                and rows <= cache_length <= 256, 'observation geometry')
        self.rows, self.cache_length = rows, cache_length
        self.rms = {'input_norm': {}, 'post_norm': {}}
        self.activations = {'sigmoid': {}, 'silu': {}}
        self.gqa = {}
        self.gqa_seen = {}
        for stage in GQA_STAGES:
            shape = (1, 8, rows, 256 if stage == 'context_bf16' else cache_length)
            self.gqa[stage] = np.zeros(shape, dtype='<u4')
            self.gqa_seen[stage] = np.zeros(shape, dtype=np.bool_)

    def rms_callback(self, role):
        require(role in self.rms, 'RMS role')
        def observe(stage, token, words):
            require(stage in RMS_WIDTHS and type(token) is int and 0 <= token < self.rows
                    and type(words) is tuple and len(words) == RMS_WIDTHS[stage]
                    and all(type(x) is int and 0 <= x < 1 << 32 for x in words),
                    'actual RMS observation shape/type')
            key = stage, token
            require(key not in self.rms[role], 'duplicate RMS observation')
            self.rms[role][key] = words
        return observe

    def activation_callback(self, role):
        require(role in self.activations, 'activation role')
        width = 2048 if role == 'sigmoid' else 3584
        def observe(index, fp32_word, bf16_word):
            require(type(index) is int and 0 <= index < self.rows * width and
                    all(type(x) is int for x in (fp32_word, bf16_word)) and
                    0 <= fp32_word < 1 << 32 and 0 <= bf16_word < 1 << 16,
                    'actual activation observation type/range')
            require(index not in self.activations[role], 'duplicate activation observation')
            self.activations[role][index] = fp32_word, bf16_word
        return observe

    def gqa_callback(self, stage, token, head, first, words):
        if stage not in self.gqa:
            return
        target, seen = self.gqa[stage], self.gqa_seen[stage]
        require(type(words) is tuple and words and all(type(x) is int and 0 <= x < 1 << 32 for x in words)
                and all(type(x) is int for x in (token, head, first)) and
                0 <= token < self.rows and 0 <= head < 8 and
                0 <= first < first + len(words) <= target.shape[-1], 'actual GQA observation range')
        slot = (0, head, token, slice(first, first + len(words)))
        require(not seen[slot].any(), 'duplicate GQA observation')
        target[slot] = words
        seen[slot] = True

    def arrays(self):
        result = {}
        for role, records in self.rms.items():
            require(set(records) == {(stage, token) for stage in RMS_WIDTHS for token in range(self.rows)},
                    'incomplete actual RMS observations: ' + role)
            for stage, width in RMS_WIDTHS.items():
                values = np.asarray([records[stage, t] for t in range(self.rows)], dtype='<u4')
                if stage == 'gamma':
                    require(np.all(values == values[0]), 'RMS gamma changed between tokens')
                    result[role + '.' + stage] = values[0]
                else:
                    result[role + '.' + stage] = values.reshape(1, self.rows, width)
        for role, records in self.activations.items():
            width = 2048 if role == 'sigmoid' else 3584
            require(set(records) == set(range(self.rows * width)), 'incomplete actual activation: ' + role)
            result[role] = np.asarray([records[i][1] << 16 for i in range(self.rows * width)],
                                     dtype='<u4').reshape(1, self.rows, width)
        for stage, words in self.gqa.items():
            require(self.gqa_seen[stage].all(), 'incomplete actual GQA stage: ' + stage)
            result[stage] = words.copy()
        return result


def producer_references(manifest, case, contract):
    """Assign captured native dispatch events to exactly the original 57 keys."""
    pairs = {tuple(x['key'].split('|')[:2]) for x in contract['producer_sequence']}
    counts, selected = Counter(), {}
    for event in case['dispatch_events']:
        module, op, result = event['module'], event['op'], event['result']
        if type(result) is not dict or set(result) != {'tensor'}:
            continue
        dtype = manifest['tensors'][result['tensor']]['dtype']
        if op == 'aten.type_as.default' or (module == 'self_attn' and op == 'aten.to.dtype' and dtype == 'BF16'):
            op = 'cast_bf16'
        pair = module, op
        if pair not in pairs:
            continue
        key = module + '|' + op + '|' + str(counts[pair])
        counts[pair] += 1
        selected[key] = result['tensor']
    require(list(selected) == [x['key'] for x in contract['producer_sequence']],
            'full native 57-producer assignment differs from frozen contract')
    for entry in contract['producer_sequence']:
        require(manifest['tensors'][selected[entry['key']]]['dtype'] ==
                {'float32': 'F32', 'bfloat16': 'BF16'}[entry['storage_dtype']],
                'native producer storage dtype')
    return selected


def _bf16_words(raw, shape):
    require(type(raw) is bytes and len(raw) == int(np.prod(shape)) * 2, 'actual full output byte extent')
    return np.frombuffer(raw, '<u2').astype('<u4').reshape(shape) << 16


def compare_case(case, manifest, directory, outputs, norm_observations, observations):
    """Compare only actual stored producer bytes; no reconstructed arithmetic."""
    contract, rows = load_contract(), manifest['query_tokens']
    references = producer_references(manifest, case, contract)
    arrays = observations.arrays()
    actual = {}
    for role, module in (('input_norm', 'input_layernorm'), ('post_norm', 'post_attention_layernorm')):
        operations = ('aten.pow.Tensor_Scalar', 'aten.mean.dim', 'aten.add.Tensor', 'aten.rsqrt.default',
                      'aten.mul.Tensor', 'aten.add.Tensor', 'aten.mul.Tensor', 'cast_bf16')
        counts = Counter()
        for field, op in zip(NORM_FIELDS, operations):
            key = module + '|' + op + '|' + str(counts[op]); counts[op] += 1
            actual[key] = arrays[role + '.' + field]
        require(np.array_equal(arrays[role + '.output'], _bf16_words(outputs[role], (1, rows, 1024))),
                'RMS observer differs from actual writeback')
    nr_arrays = observation_arrays(norm_observations, outputs, rows)
    nr_references = select_case_references(manifest, case, contract)
    for label, record in nr_references.items():
        if record['producer_key'] is not None:
            actual[record['producer_key']] = nr_arrays[label]
    direct = {
        'packed_q_gate': 'self_attn.q_proj|aten.linear.default|0',
        'k': 'self_attn.k_proj|aten.linear.default|0', 'v': 'self_attn.v_proj|aten.linear.default|0',
        'gated_context': 'self_attn|aten.mul.Tensor|5', 'o': 'self_attn.o_proj|aten.linear.default|0',
        'attention_residual': '|aten.add.Tensor|0', 'gate': 'mlp.gate_proj|aten.linear.default|0',
        'up': 'mlp.up_proj|aten.linear.default|0', 'silu_mul': 'mlp|aten.mul.Tensor|0',
        'down': 'mlp.down_proj|aten.linear.default|0', 'output': '|aten.add.Tensor|1',
    }
    for role, key in direct.items():
        actual[key] = _bf16_words(outputs[role], (1, rows, full_fixture.WIDTHS[role]))
    for stage, key in {
        'qk_bf16': 'self_attn|aten.matmul.default|0',
        'scaled_scores_bf16': 'self_attn|aten.mul.Tensor|4',
        'probability_fp32': 'self_attn|aten.softmax.int|0',
        'probabilities_bf16': 'self_attn|cast_bf16|0',
        'context_bf16': 'self_attn|aten.matmul.default|1',
        'sigmoid': 'self_attn|aten.sigmoid.default|0', 'silu': 'mlp.act_fn|aten.silu.default|0',
    }.items():
        actual[key] = arrays[stage]
    require(np.array_equal(arrays['context_bf16'].transpose(0, 2, 1, 3).reshape(1, rows, 2048),
                           _bf16_words(outputs['context'], (1, rows, 2048))), 'GQA observer/writeback mismatch')
    gates = {}
    for key, words in actual.items():
        reference = references[key]; record = manifest['tensors'][reference]
        raw = read_tensor(directory, manifest, reference)
        expected = np.frombuffer(raw, '<u2' if record['dtype'] == 'BF16' else '<u4').astype('<u4').reshape(record['shape'])
        if record['dtype'] == 'BF16': expected <<= 16
        gates[key] = _metrics(words, expected, record['dtype'], contract['thresholds']['operator'])
        gates[key]['native_tensor'] = reference
    missing = [x['key'] for x in contract['producer_sequence'] if x['key'] not in actual]
    require(missing == ['self_attn|aten.add.Tensor|2'], 'unexpected missing actual producer')
    block = compare_finite_bf16(outputs['output'], read_tensor(directory, manifest, case['output']))
    block.update(thresholds=contract['thresholds']['block'],
                 passed=block['max_abs'] <= contract['thresholds']['block']['max_abs'] and
                        block['mean_abs'] <= contract['thresholds']['block']['mean_abs'])
    probability = arrays['probability_fp32'].view('<f4')
    sums = probability.astype(np.float64).sum(axis=-1)
    row_error = float(np.max(np.abs(sums - 1)))
    limit = contract['softmax_row_sum_abs_limit']
    cache = {}
    final = case['final_cache']['3']
    require(final['tokens'] == observations.cache_length, 'native/actual final cache length')
    for role, key in (('cache_k', final['key']), ('cache_v', final['value'])):
        record = manifest['tensors'][key]
        shape = (1, 2, observations.cache_length, 256)
        require(record['dtype'] == 'BF16' and record['shape'] == list(shape), 'native final KV dtype/layout')
        actual_cache = _bf16_words(outputs[role], (1, observations.cache_length, 2, 256)).transpose(0, 2, 1, 3)
        expected = _bf16_words(read_tensor(directory, manifest, key), shape)
        cache[role] = _metrics(actual_cache, expected, 'BF16', contract['thresholds']['operator'])
        cache[role]['native_tensor'] = key
    return dict(case=case['name'], original_contract_sha256=manifest['contract_sha256'],
        total_required_producers=57, computed_required_producers=len(actual),
        missing_producers=missing, missing_reason='fused causal control does not materialize native mask-add tensor; no values fabricated',
        producer_gates=gates, block_output=block, final_kv=cache,
        softmax_row_sum=dict(max_abs=row_error, limit=limit, passed=row_error <= limit),
        all_computed_stages_pass=all(x['pass'] for x in (*gates.values(), *cache.values())) and block['passed'] and row_error <= limit,
        full_contract_accepted=False, numerical_thresholds_changed=False)
