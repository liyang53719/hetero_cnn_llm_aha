"""Expected-only layer3 full-block reference. Never imports a DUT.

The public factory reads raw hidden inputs from an authenticated live capture. Existing
QKV/Norm authorities preserve their original independent component gates and
provide their already-built tools; their native-normalized inputs and cached
terminals are NOT substituted into this raw-hidden graph.

No factory runs at import time. The long-K tool factory is explicit so its
future caller can serialize compilation. This preparation does not run it.
"""
from dataclasses import dataclass
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import weakref

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'chisel/continuous_prefill/scripts'
for path in (ROOT / 'src', SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import host_bf16_attention_core_reference as core
import host_bf16_qkv_reference as projection
import host_bf16_qk_rope_reference as norm_rope
import gdn_dense_reference as dense
import gdn_rmsnorm_reference as rms
import gdn_elementwise_reference as elementwise
from pack_host_bf16_v_fixture import CaptureSession, capture, load_payload
from heteronpu.qwen35_bf16_reference import producer_compare

import attention_sigmoid_reference as sigmoid
require, digest, file_digest = projection.require, projection.digest, projection.file_digest
CONTRACT_PATH = ROOT / 'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json'
PIN_PATH = ROOT / 'config/upstream/qwen3_5_0p8b/layer3_payload_pin.json'
SOURCE_PATH = ROOT / 'config/upstream/qwen3_5_0p8b/modeling_qwen3_5.py'

COMMANDS = ('input_norm', 'q', 'k', 'v', 'norm_q', 'norm_k', 'rope_q', 'rope_k',
            'append', 'qk', 'softmax', 'pv', 'sigmoid_mul', 'o', 'residual1',
            'post_norm', 'ffn_gate', 'ffn_up', 'silu_mul', 'down', 'residual2', 'fence')
DENSE_SHAPES = {'q': (1024, 4096), 'k': (1024, 512), 'v': (1024, 512),
                'o': (2048, 1024), 'ffn_gate': (1024, 3584),
                'ffn_up': (1024, 3584), 'down': (3584, 1024)}
PARAMETERS = {'input_norm': 'input_layernorm.weight', 'post_norm': 'post_attention_layernorm.weight',
              'q_gamma': 'self_attn.q_norm.weight', 'k_gamma': 'self_attn.k_norm.weight',
              **{r: 'self_attn.' + r + '_proj.weight' for r in ('q', 'k', 'v', 'o')},
              'ffn_gate': 'mlp.gate_proj.weight', 'ffn_up': 'mlp.up_proj.weight',
              'down': 'mlp.down_proj.weight'}
TERMINAL_NODES = {'input_norm': 7, 'q': 8, 'k': 17, 'v': 26, 'norm_q': 16,
                  'norm_k': 25, 'rope_q_prefix': 29, 'rope_k_prefix': 32,
                  'qk': 33, 'score': 34, 'masked_score': 35, 'probability_fp32': 36,
                  'probability': 37, 'context': 38, 'sigmoid': 39, 'sigmoid_mul': 40,
                  'o': 41, 'residual1': 42, 'post_norm': 50, 'ffn_gate': 51,
                  'silu': 52, 'ffn_up': 53, 'silu_mul': 54, 'down': 55, 'residual2': 56}
MATRIX_MACS_PER_TOKEN = sum(k * n for k, n in DENSE_SHAPES.values())
GQA_NODES = frozenset(range(33, 39))
_TOOLS = weakref.WeakKeyDictionary()
_REFERENCES = weakref.WeakKeyDictionary()


def predecessor_schema():
    """Actual fixed-recipe operands. Native-conditioned graph values never enter."""
    predecessors = {}
    for base, source, weight in ((0, 'raw_hidden', 'weight_input_norm'),
                                 (9, 'producer_08.content256_per_head', 'weight_q_gamma'),
                                 (18, 'producer_17', 'weight_k_gamma'),
                                 (43, 'producer_42', 'weight_post_norm')):
        predecessors.update({base: [source], base + 1: [f'producer_{base:02d}'],
            base + 2: [f'producer_{base + 1:02d}', 'frozen_epsilon'],
            base + 3: [f'producer_{base + 2:02d}'],
            base + 4: [source, f'producer_{base + 3:02d}'],
            base + 5: [weight, 'fp32_one'], base + 6: [f'producer_{base + 4:02d}', f'producer_{base + 5:02d}'],
            base + 7: [f'producer_{base + 6:02d}']})
    predecessors.update({8: ['producer_07', 'weight_q'], 17: ['producer_07', 'weight_k'],
        26: ['producer_07', 'weight_v'],
        27: ['producer_16.prefix64', 'authenticated_trig.cos'],
        28: ['producer_16.rotate_half_prefix64', 'authenticated_trig.sin'],
        29: ['producer_27', 'producer_28'],
        30: ['producer_25.prefix64', 'authenticated_trig.cos'],
        31: ['producer_25.rotate_half_prefix64', 'authenticated_trig.sin'],
        32: ['producer_30', 'producer_31'],
        33: ['producer_29.concat_producer_16.tail192', 'canonical_cache_prefix_K_plus_current_rope_K'],
        34: ['producer_33', 'fp32_scale_1_over_16'],
        35: ['producer_34', 'exact_causal_mask'],
        36: ['producer_34.allowed_entries', 'exact_causal_mask'],
        37: ['producer_36'], 38: ['producer_37', 'canonical_cache_prefix_V_plus_producer_26'],
        39: ['producer_08.gate256_per_head'], 40: ['producer_38', 'producer_39'],
        41: ['producer_40', 'weight_o'], 42: ['raw_hidden', 'producer_41'],
        51: ['producer_50', 'weight_ffn_gate'], 52: ['producer_51'],
        53: ['producer_50', 'weight_ffn_up'], 54: ['producer_52', 'producer_53'],
        55: ['producer_54', 'weight_down'], 56: ['producer_42', 'producer_55']})
    require(set(predecessors) == set(range(57)), 'predecessor provenance inventory')
    return {f'producer_{i:02d}': dict(actual_predecessors=predecessors[i],
        origin='same_raw_hidden_canonical_graph', native_intermediate_consumed=False) for i in range(57)}


def source_identity():
    sources = projection._source_identity() | norm_rope._source_identity()
    modules = (core, dense, rms, elementwise, core.gqa, sigmoid)
    paths = [Path(m.__file__).resolve() for m in modules]
    paths += [Path(__file__).resolve(), CONTRACT_PATH, PIN_PATH, SOURCE_PATH,
              SCRIPTS / 'gdn_dense_reference.c', ROOT / 'spec/numerical_contract.md',
              ROOT / 'src/heteronpu/qwen35_bf16_reference.py']
    for path in paths:
        require(path.is_file() and not path.is_symlink() and path.is_relative_to(ROOT),
                'source identity/path drift')
        sources[str(path.relative_to(ROOT))] = file_digest(path)
    require(file_digest(SOURCE_PATH) == sigmoid.SOURCE_SHA256, 'official modeling pin drift')
    require(file_digest(CONTRACT_PATH) == capture.CONTRACT_SHA256, 'producer contract pin drift')
    return sources


def contract_schema():
    """22 command roles; a source contract, not a public ABI/descriptor builder."""
    contract = json.loads(CONTRACT_PATH.read_text())
    pin = json.loads(PIN_PATH.read_text())
    require(len(COMMANDS) == 22 and len(contract['producer_sequence']) == 57, 'command/node inventory')
    require(set(PARAMETERS.values()) == {p['local_name'] for p in pin['tensors']}, 'all 11 parameters required')
    require(all(p['dtype'] == 'BF16' for p in pin['tensors']), 'parameter dtype drift')
    return dict(schema_version=1, scope='ISOLATED_22_COMMAND_FULL_BLOCK_REFERENCE_CANDIDATE',
        command_order=list(COMMANDS), raw_input='phase_m128_input[0, token, :]',
        input_dtype='BF16 stored losslessly in FP32 capture arrays', parameters=copy.deepcopy(pin['tensors']),
        dense_k_major_shapes={k: list(v) for k, v in DENSE_SHAPES.items()},
        producers=copy.deepcopy(contract['producer_sequence']), terminal_nodes=TERMINAL_NODES.copy(),
        dense_macs_per_token=MATRIX_MACS_PER_TOKEN,
        producer_predecessors=predecessor_schema(),
        native_thresholds=copy.deepcopy(contract['thresholds']),
        gqa_acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE',
        expected_only=True, dut_input_injection=False, production_abi_implemented=False)


class FullBlockDenseTools:
    """Only the explicit compiler factory issues this process-local authority."""
    __slots__ = ('__weakref__',)

    def __init__(self, *args, **kwargs):
        raise TypeError('use compile_full_block_dense_tools in the centrally serialized compiler job')

    def verify(self):
        require(self in _TOOLS, 'unissued dense tool authority')
        sources, receipt = _TOOLS[self]
        require(source_identity() == sources, 'source changed since long-K tool build')
        projection._verify_tools(receipt)
        return copy.deepcopy(receipt)


def compile_full_block_dense_tools(directory):
    """Dormant preparation API. Not called by schema/unit tests or import."""
    directory = Path(directory).resolve()
    require(directory.is_relative_to(ROOT / 'work') and directory != ROOT / 'work'
            and not directory.exists(), 'fresh ignored compiler directory required')
    before = source_identity()
    directory.mkdir(parents=True)
    _, receipt = dense.compile_reference(directory)
    require(source_identity() == before, 'source changed during compiler execution')
    result = object.__new__(FullBlockDenseTools)
    _TOOLS[result] = (before, receipt)
    result.verify()
    return result


def _bf16(value, shape, name):
    require(isinstance(value, np.ndarray) and value.dtype == np.dtype('<u2')
            and value.shape == shape, name + ' BF16 storage/shape')
    require(np.isfinite(rms.fp(value)).all(), name + ' nonfinite')
    return value


def sigmoid_product(gate, context):
    """The independent scalar owner's five operations and TWO BF16 boundaries."""
    _bf16(gate, gate.shape, 'gate'); _bf16(context, gate.shape, 'context')
    require(gate.size > 0, 'empty sigmoid')
    sig, product = np.empty_like(gate), np.empty_like(gate)
    for index in np.ndindex(gate.shape):
        row = sigmoid.lane(int(gate[index]), int(context[index]))
        sig[index], product[index] = row['sigmoid'], row['output']
    return sig, product


def _rms_nodes(x, weight, base, nodes):
    result, trace = rms.recipe(x, weight)
    names = ('squares', 'mean', 'variance', 'inverse_rms', 'normalized_fp32',
             'one_plus_weight', 'weighted_fp32')
    for offset, name in enumerate(names):
        nodes[base + offset] = trace[name].copy()
    nodes[base + 7] = rms.fp(result)
    return result


def _dense_rows(x, weight, executable, scratch):
    """Stream 256 columns, preserving all K FMA steps within each output."""
    k, columns = weight.shape
    _bf16(x, (x.shape[0], k), 'Dense input')
    _bf16(weight, (k, columns), 'Dense weight')
    require(k in dense.ALLOWED_K and columns % 256 == 0, 'Dense unsupported shape')
    result, proofs = np.empty((x.shape[0], columns), dtype='<u2'), []
    for token in range(x.shape[0]):
        for start in range(0, columns, 256):
            value, proof = dense.project_and_crosscheck(x[token], np.ascontiguousarray(weight[:, start:start + 256]),
                                                        executable, scratch)
            require(proof['pass'] and proof['uninterrupted_fp32_accumulation'], 'Dense C witness failed')
            result[token, start:start + 256] = np.frombuffer(value['bf16'], dtype='<u2')
            proofs.append(dict(token=token, column_start=start, **proof))
    return result, proofs


def _norm_rope(q, k, weights, trig, executables, scratch, nodes):
    count = q.shape[0]
    packed = q.reshape(count, 8, 512)
    gate = packed[:, :, 256:].copy().reshape(count, 2048)
    results, ni, nt, ri, rt = {}, [], [], [], []
    for role, values, heads, base, rope_base in (
            ('q', packed[:, :, :256], 8, 9, 27), ('k', k.reshape(count, 2, 256), 2, 18, 30)):
        gamma = weights[role + '_gamma'].astype('<u4') << 16
        fields = {name: [] for name in ('squares', 'mean', 'mean_eps', 'inverse', 'scaled', 'output_fp32', 'output_bf16')}
        normalized, rotated, cos_products, sin_products = [], [], [], []
        for token in range(count):
            for head in range(heads):
                value = values[token, head].astype('<u4') << 16
                _, _, trace = norm_rope.arithmetic.norm_execution_trace(value, gamma)
                ni.append(np.concatenate((value, gamma))); nt.append(norm_rope.arithmetic.norm.trace_words(trace))
                for name in fields:
                    fields[name].append(trace[name])
                normalized.append(trace['output_bf16'])
                out, _, _, full, pairs = norm_rope.arithmetic.rope_execution_trace(
                    trace['output_bf16'], trig[token].astype('<u4') << 16)
                rotated.append(out); ri.extend(pairs); rt.extend(full)
                cos_products.append(np.concatenate((full[:, 8], full[:, 11])))
                sin_products.append(np.concatenate((full[:, 9] ^ np.uint32(0x80000000), full[:, 10])))
        for offset, name in enumerate(('squares', 'mean', 'mean_eps', 'inverse', 'scaled')):
            width = 1 if name in ('mean', 'mean_eps', 'inverse') else 256
            nodes[base + offset] = np.asarray(fields[name], dtype='<u4').view('<f4').reshape(1, count, heads, width)
        nodes[base + 5] = np.asarray(trace['gamma'], dtype='<u4').view('<f4')
        for offset, name in ((6, 'output_fp32'), (7, 'output_bf16')):
            nodes[base + offset] = np.asarray(fields[name], dtype='<u4').view('<f4').reshape(1, count, heads, 256)
        n = np.asarray(normalized, dtype='<u4').reshape(count, heads, 256)
        r = np.asarray(rotated, dtype='<u4').reshape(count, heads, 256)
        require(np.array_equal(n[:, :, 64:], r[:, :, 64:]), 'partial64 tail drift')
        for offset, value in enumerate((cos_products, sin_products, r[:, :, :64])):
            nodes[rope_base + offset] = np.asarray(value, dtype='<u4').view('<f4').reshape(count, heads, 64).transpose(1, 0, 2)[None]
        results['norm_' + role] = (n >> 16).astype('<u2').reshape(count, -1)
        results['rope_' + role] = (r >> 16).astype('<u2').reshape(count, -1)
    proof = norm_rope.arithmetic.crosscheck_c(executables, scratch, ni, np.asarray(nt, dtype='<u4'),
                                              ri, np.asarray(rt, dtype='<u4'))
    return results | {'gate': gate}, proof


def _crosscheck_gqa(executable, scratch, query, cache, trace, output):
    """Bounded every-FMA witness, including M128, without giant Python lists."""
    inputs, expected, count, hashes = [], [], 0, []
    source, target = scratch / 'gqa_fma_input.bin', scratch / 'gqa_fma_output.bin'

    def flush():
        nonlocal count
        if not inputs:
            return
        a, e = np.asarray(inputs, dtype='<u4'), np.asarray(expected, dtype='<u4')
        a.tofile(source)
        subprocess.run([str(executable), '--fma', str(source), str(target)], check=True, capture_output=True, timeout=30)
        actual = np.fromfile(target, dtype='<u4')
        require(actual.size == e.size and np.array_equal(actual.reshape(e.shape), e), 'GQA integer/C FMA/flags mismatch')
        hashes.append(dict(input_sha256=digest(a.tobytes()), output_sha256=digest(actual.tobytes()), fmas=len(inputs)))
        count += len(inputs)
        inputs.clear(); expected.clear()

    def dot(left, right):
        acc = 0
        for a, b in zip(left.view('<u4'), right.view('<u4'), strict=True):
            inputs.append((int(a), int(b), acc))
            acc, flags = core.fma_rne(int(a), int(b), acc)
            expected.append((acc, flags))
            if len(inputs) == 8192:
                flush()
        return acc

    live = cache[:, :trace['qk_fp32'].shape[-1]]
    for row in range(query.shape[0]):
        for head in range(8):
            start = head // 4 * 256
            for key in range(live.shape[1]):
                word = dot(query[row, head], live[0, key, start:start + 256])
                require(word == int(trace['qk_fp32'].view('<u4')[row, head, key]), 'QK witness terminal')
            for col in range(256):
                word = dot(trace['probabilities_bf16'][row, head], live[1, :, start + col])
                require(word == int(trace['pv_fp32'].view('<u4')[row, head, col]), 'PV witness terminal')
                require(core.gqa._bf16(word) == int(output.reshape(-1, 8, 256).view('<u4')[row, head, col]), 'PV BF16 witness')
    flush()
    source.unlink(); target.unlink()
    return dict(status='PASS_INTEGER_C_EVERY_QK_PV_FMA', fmas=count, chunks=hashes,
                max_buffered_fmas=8192, bit_mismatches=0, flag_mismatches=0)


def _evaluate_launch(hidden, weights, trig, cache, start, dense_executable, matrix_executable, norm_executables, scratch):
    """Pure expected graph; native values are absent from this function."""
    count = hidden.shape[0]
    _bf16(hidden, (count, 1024), 'raw hidden'); _bf16(trig, (count, 64), 'trig')
    require(1 <= count <= 128 and 0 <= start and start + count <= 256, 'launch window')
    nodes, terminals, proofs = {}, {}, {}
    normalized = _rms_nodes(hidden[None], weights['input_norm'], 0, nodes)[0]
    terminals['input_norm'] = normalized
    for role, node in (('q', 8), ('k', 17), ('v', 26)):
        terminals[role], proofs[role] = _dense_rows(normalized, weights[role], dense_executable, scratch)
        nodes[node] = rms.fp(terminals[role])[None]
    nr, proofs['norm_rope'] = _norm_rope(terminals['q'], terminals['k'], weights, trig, norm_executables, scratch, nodes)
    terminals.update(nr)
    # Caller owns this canonical cache. The prior prefix is never native input.
    cache = cache.copy()
    cache[0, start:start + count] = rms.fp(terminals['rope_k'])
    cache[1, start:start + count] = rms.fp(terminals['v'])
    query = rms.fp(terminals['rope_q']).reshape(count, 8, 256)
    context, trace = core.gqa.causal_gqa(query, cache, query_start=start, cache_length=start + count, return_trace=True)
    proofs['gqa'] = _crosscheck_gqa(matrix_executable, scratch, query, cache, trace, context)
    # Reconstruct every official materialization boundary, including mask and
    # FP32 softmax, while retaining the frozen GQA approximation policy.
    probabilities = np.empty_like(trace['probabilities_bf16'])
    masked = trace['logits_bf16'].copy()
    for row in range(count):
        allowed = trace['allowed'][row]
        mask = np.where(allowed, np.float32(0), np.asarray(0xff7f0000, dtype='<u4').view('<f4'))
        for head in range(8):
            _, soft = core.gqa.softmax_row(trace['logits_bf16'][row, head], allowed, return_trace=True)
            probabilities[row, head] = soft['probabilities_fp32']
            masked[row, head] = rms.fp(rms.bf16(np.add(trace['logits_bf16'][row, head], mask, dtype=np.float32)))
    for index, value in ((33, trace['qk_bf16']), (34, trace['logits_bf16']), (35, masked),
                         (36, probabilities), (37, trace['probabilities_bf16'])):
        nodes[index] = value.transpose(1, 0, 2)[None]
    nodes[38] = context.reshape(count, 8, 256).transpose(1, 0, 2)[None]
    terminals['context'] = rms.bf16(context)
    sig, gated = sigmoid_product(terminals['gate'], terminals['context'])
    terminals['sigmoid'], terminals['sigmoid_mul'] = sig, gated
    nodes[39], nodes[40] = rms.fp(sig)[None], rms.fp(gated)[None]
    o, proofs['o'] = _dense_rows(gated, weights['o'], dense_executable, scratch)
    residual1, _ = elementwise.recipe('add', hidden, o)
    post = _rms_nodes(residual1[None], weights['post_norm'], 43, nodes)[0]
    gate, proofs['ffn_gate'] = _dense_rows(post, weights['ffn_gate'], dense_executable, scratch)
    up, proofs['ffn_up'] = _dense_rows(post, weights['ffn_up'], dense_executable, scratch)
    product, silu = elementwise.recipe('silu_mul', gate, up)
    down, proofs['down'] = _dense_rows(product, weights['down'], dense_executable, scratch)
    residual2, _ = elementwise.recipe('add', residual1, down)
    for role, value, node in (('o', o, 41), ('residual1', residual1, 42), ('post_norm', post, 50),
            ('ffn_gate', gate, 51), ('silu', silu['silu_bf16'], 52), ('ffn_up', up, 53),
            ('silu_mul', product, 54), ('down', down, 55), ('residual2', residual2, 56)):
        terminals[role] = value
        nodes[node] = rms.fp(value)[None]
    terminals['cache_k'], terminals['cache_v'] = rms.bf16(cache[0, :start + count]), rms.bf16(cache[1, :start + count])
    require(set(nodes) == set(range(57)), 'missing full-block producer boundary')
    return terminals, nodes, cache, proofs


def _select_native(array, index, token, count, keys):
    if index in (5, 14, 23, 48):
        return array.copy()  # one_plus_weight, independent of tokens
    if 27 <= index <= 38:
        selected = array[:, :, token:token + count]
        return selected[..., :keys].copy() if 33 <= index <= 37 else selected.copy()
    return array[:, token:token + count].copy()


def _diagnostics(nodes, native, report, phase):
    contract = json.loads(CONTRACT_PATH.read_text())
    require(report['thresholds'] == contract['thresholds'] and report['producer_sequence'] == contract['producer_sequence'],
            'original native thresholds/node inventory drift')
    rows = []
    for index, definition in enumerate(contract['producer_sequence']):
        require(nodes[index].dtype == native[index].dtype == np.dtype('<f4'), 'producer FP32 container dtype drift')
        if definition['storage_dtype'] == 'bfloat16':
            core.gqa.require_bf16(nodes[index], 'expected producer ' + str(index))
            core.gqa.require_bf16(native[index], 'native producer ' + str(index))
        metric = producer_compare(nodes[index], native[index])
        original = [row for row in report['comparisons'] if row['case'] == phase + '_m128' and row['producer'] == definition['key']]
        require(len(original) == 1, 'original native producer comparison missing')
        require(original[0]['max_abs_limit'] == contract['thresholds']['operator']['max_abs']
                and original[0]['mean_abs_limit'] == contract['thresholds']['operator']['mean_abs']
                and original[0]['storage_dtype'] == definition['storage_dtype'], 'original hidden/operator boundary drift')
        rows.append(dict(index=index, producer=definition['key'], storage_dtype=definition['storage_dtype'],
            comparison=metric, original_native_comparison=copy.deepcopy(original[0]), diagnostic_only=True,
            acceptance='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE' if index in GQA_NODES else 'ORIGINAL_OPERATOR_LIMITS_DIAGNOSTIC',
            predecessor_bit_identity_claimed=False))
    return rows


@dataclass(frozen=True)
class _ReferenceAuthority:
    capture_session: object
    projection_session: object
    attention_session: object
    dense_tools: object
    sources: dict
    receipt: dict
    inputs: dict
    expected: dict


def _byte_records(files):
    return {name: dict(bytes=len(raw), sha256=digest(raw)) for name, raw in files.items()}


class FullBlockReferenceSession:
    """No receipt/path/expected-array constructor; same-process authority only."""
    __slots__ = ('__weakref__',)

    def __init__(self, *args, **kwargs):
        raise TypeError('use prepare_full_block_reference with live authorities')

    def select(self, *, session):
        require(self in _REFERENCES, 'unissued full-block reference')
        a = _REFERENCES[self]
        require(session is a.capture_session and type(session) is CaptureSession and session.fresh is True,
                'same live fresh capture required')
        official = session.verify()
        require(session.manifest_sha256 == a.receipt['official_manifest_sha256'], 'capture changed')
        a.projection_session.verify(session=session)
        a.attention_session.verify(session=session, projection_reference_session=a.projection_session)
        a.dense_tools.verify()
        require(source_identity() == a.sources, 'full-block source closure changed')
        require(session.evidence(official) == a.receipt['original_capture_evidence'], 'original native failure changed')
        require(_byte_records(a.inputs) == a.receipt['inputs'], 'raw inputs changed')
        require({k: _byte_records(v) for k, v in a.expected.items()} == a.receipt['expected'], 'expected-only bytes changed')
        return copy.deepcopy(a.inputs), copy.deepcopy(a.expected), copy.deepcopy(a.receipt)


def prepare_full_block_reference(session, projection_session, attention_session, dense_tools, *, variant='baseline', launch_counts=(1, 1)):
    """Future heavy factory: adjacent cold rows OR complete cold/carried M128.

    This function was not executed for source preparation. It never loads a
    saved reference as authority and never returns a hardware/native PASS.
    All runtime scratch files are bounded and discarded after each launch.
    """
    require(type(session) is CaptureSession and session.fresh is True, 'live fresh CaptureSession required')
    require(type(projection_session) is projection.FreshProjectionReferenceSession and
            type(attention_session) is norm_rope.FreshAttentionReferenceSession and
            type(dense_tools) is FullBlockDenseTools, 'live independent reference authorities required')
    require(type(variant) is str and variant in projection.VARIANTS and type(launch_counts) is tuple
            and all(type(v) is int for v in launch_counts) and launch_counts in ((1, 1), (128, 128)),
            'supported source launch scope')
    p = projection_session.verify(session=session)
    n = attention_session.verify(session=session, projection_reference_session=projection_session)
    require(variant in p['variants'] and variant in n['variants'], 'uncomputed original component gates')
    tool_receipt = dense_tools.verify()
    before, official = source_identity(), session.verify()
    contract = capture._contract(ROOT)
    path = session.directory / variant / 'native/all_bf16_producers.npz'
    report_path = path.with_name('result.json')
    capture._verify_file(path, official['corpora'][variant]['fresh_audit_arrays'])
    capture._verify_file(report_path, official['corpora'][variant]['fresh_audit_report'])
    report = json.loads(report_path.read_text())
    prefix_path = session.directory / variant / 'prefix/result.json'
    capture._verify_file(prefix_path, official['corpora'][variant]['fresh_prefix_report'])
    prefix_report = json.loads(prefix_path.read_text())
    manifest, raw = load_payload(ROOT, session.payload_layer3)
    pins = {row['local_name']: row for row in json.loads(PIN_PATH.read_text())['tensors']}
    weights, inputs = {}, {}
    for role, name in PARAMETERS.items():
        require(pins[name]['dtype'] == 'BF16' and digest(raw[name]) == pins[name]['sha256'], 'original parameter pin drift')
        value = np.frombuffer(raw[name], dtype='<u2').reshape(pins[name]['shape'])
        weights[role] = np.ascontiguousarray(value.T) if role in DENSE_SHAPES else value.copy()
        inputs['weight_' + role + '.bf16le'] = weights[role].tobytes()
    cache = np.zeros((2, 256, 512), dtype='<f4')  # cold expected state only
    expected, cases = {}, {}
    matrix_exe = Path(p['tools']['executable']['path'])
    dense_exe = Path(tool_receipt['executable']['path'])
    norm_exes = {key: Path(row['path']) for key, row in n['tools']['executables'].items()}
    with np.load(path, allow_pickle=False) as arrays:
        require(len(arrays.files) == len(set(arrays.files)), 'duplicate native array names')
        trig_parts = []
        for trig_phase in ('cold', 'carried'):
            values = [capture._bf16_words(arrays[trig_phase + '_m128_native_' + name],
                (1, 128, 64), name)[0] for name in ('cos', 'sin')]
            require(all(np.array_equal(v[:, :32], v[:, 32:]) for v in values), 'trig pair layout')
            trig_parts.append((np.concatenate((values[0][:, :32], values[1][:, :32]), axis=1) >> 16).astype('<u2'))
        all_trig = np.concatenate(trig_parts)
        inputs['trig.bf16le'] = all_trig.tobytes()
        require(len(inputs['trig.bf16le']) == 256 * 64 * 2, 'complete authenticated trig allocation')
        for launch, count in enumerate(launch_counts):
            phase, token, start = ('cold', launch, launch) if count == 1 else (('cold' if launch == 0 else 'carried'), 0, launch * 128)
            label = phase + str(token)
            prefix = phase + '_m128_'
            hidden_all = capture._bf16_words(arrays[prefix + 'input'], (1, 128, 1024), 'raw layer3 hidden')
            hidden = (hidden_all[0, token:token + count] >> 16).astype('<u2')
            trig = all_trig[start:start + count].copy()
            inputs[label + '_hidden.bf16le'] = hidden.tobytes()
            prior_cache_sha256 = digest(cache[:, :start].tobytes())
            with tempfile.TemporaryDirectory(prefix='.full_block_', dir=projection_session.directory.parent) as temporary:
                terminals, nodes, cache, proofs = _evaluate_launch(hidden, weights, trig, cache, start,
                    dense_exe, matrix_exe, norm_exes, Path(temporary))
            native = {i: _select_native(arrays[prefix + f'native_producer_{i:02d}'], i, token, count, start + count) for i in range(57)}
            diagnostics = _diagnostics(nodes, native, report, phase)
            terminal_files = {name + '.bf16le': value.tobytes() for name, value in terminals.items()}
            terminal_files.update({f'producer_{i:02d}.f32le': value.astype('<f4').tobytes() for i, value in nodes.items()})
            expected[label] = terminal_files
            cases[label] = dict(command_count=22, source_phase=phase, source_token=token, token_count=count,
                absolute_position=start, expected_length=start, expected_generation=launch,
                producer_predecessors=predecessor_schema(), raw_hidden_sha256=digest(hidden.tobytes()),
                cache_prefix_origin='cold_empty' if launch == 0 else 'previous_launch_canonical_append_outputs',
                canonical_cache_prefix_sha256=prior_cache_sha256,
                selected_trig=dict(backing_file='trig.bf16le', byte_offset=start * 128,
                    bytes=count * 128, sha256=digest(trig.tobytes()), backing_sha256=digest(inputs['trig.bf16le'])),
                cold=launch == 0, all_57_producer_diagnostics=diagnostics, independent_proofs=proofs,
                output_comparison=producer_compare(nodes[56], arrays[prefix + 'native_output'][:, token:token + count], block=True),
                cache_comparisons={role: producer_compare(rms.fp(terminals['cache_' + role]).reshape(-1, 2, 256).transpose(1, 0, 2)[None],
                    arrays[prefix + 'native_' + name][:, :, :start + count]) for role, name in (('k', 'key'), ('v', 'value'))},
                predecessor_bit_identity_claimed=False, native_accuracy_accepted=False)
    require(source_identity() == before and session.verify() == official, 'source/capture changed during full-block reference')
    require(projection_session.verify(session=session) == p and
            attention_session.verify(session=session, projection_reference_session=projection_session) == n and
            dense_tools.verify() == tool_receipt, 'independent authority changed')
    receipt = dict(schema_version=1, status='PREPARED_FULL_BLOCK_EXPECTED_ONLY_NOT_NATIVE_PASS',
        source_sha256_before=before, source_sha256_after=source_identity(),
        official_manifest_sha256=session.manifest_sha256, variant=variant, launch_counts=list(launch_counts),
        model_revision=manifest['revision'], schema=contract_schema(), cases=cases,
        inputs=_byte_records(inputs), expected={k: _byte_records(v) for k, v in expected.items()},
        original_capture_evidence=session.evidence(official), original_native_report=copy.deepcopy(report),
        original_prefix_report=copy.deepcopy(prefix_report), original_native_thresholds=copy.deepcopy(contract['thresholds']),
        original_projection_gate_pass=p['native_operator_gate_pass'], original_norm_rope_gate_pass=n['original_operator_gate_pass'],
        original_component_gate_scope=dict(projection_windows=p['requested_windows'], norm_rope_windows=n['requested_windows'],
            projection_receipt_sha256=projection_session.receipt_sha256,
            norm_rope_receipt_sha256=attention_session.receipt_sha256,
            projection_thresholds=p['native_thresholds'], norm_rope_criteria=n['original_native_criteria']),
        original_native_full_block_failures=copy.deepcopy(n['native_full_block_failures']),
        gqa_native_gate='UNASSIGNED_DIAGNOSTIC_ONLY_NOT_NATIVE_ACCEPTANCE',
        expected_only=True, intermediate_preload_allowed=False, dut_input_injection=False,
        acceptance_layers=dict(frozen_hardware_arithmetic='expected bit patterns only; compare actual DUT separately',
            official_native_accuracy='original audit and limits retained; GQA stage unassigned; no native PASS'),
        actual_cache_execution=False, numerical_rtl_executed=False, native_full_block_pass=False,
        full128_reference_generated=launch_counts == (128, 128), upstream_gdn_decode_executed=False)
    reference = object.__new__(FullBlockReferenceSession)
    _REFERENCES[reference] = _ReferenceAuthority(session, projection_session, attention_session, dense_tools,
                                                before, receipt, inputs, expected)
    reference.select(session=session)
    return reference
