"""Opt-in Q/K Norm256 oracle and immutable historical producer corpus.

Every arithmetic operation is exact integer binary32 RNE; no host float math
is used by the oracle. PWL coefficients are literal copies of the frozen RTL
ROM, followed by exactly one Newton step in fp32_rsqrt_nr.sv order. This is a
new candidate policy, not the native framework reduction or production policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from collections.abc import Iterable
import numpy as np
from .model_geometry import require
from .rope_bf16_candidate import add_rne, mul_rne, bf16_convert

POLICY = 0xC1
HEAD_DIM = 256
EPSILON = 0x358637BD
ROLE_Q, ROLE_K = 0, 1
STATUS_OK, STATUS_DESCRIPTOR, STATUS_NONFINITE, STATUS_RANGE = 0, 1, 2, 3
FIXTURES = Path(__file__).resolve().parents[2] / 'tests/fixtures/qk_norm256'
PROVENANCE_SHA256 = '3cd114d66dc53d9f20e2b5185669e3ce3a86616fd25a679be6ee209bcf407361'
BUNDLE_SHA256 = {
    'local': 'a31084a31fa5df8814e961cf854389af8759fe64ba579193a23196e265c40ead',
    'remote': '3e30156abce2c9dd45a1117004f208810d4b4839f0ddf64bcac851e44870d3f9',
}
ORIGINAL_REPORT_SHA256 = {
    'local': 'fece52d072ea997675a59865ed1e5ffb48ac28e41b7ae3e8e32552f8e9d0fda1',
    'remote': 'd04f72678b8347bcf872f5a33c5948a0fc66e14a4f98d1a60d0976a611523d25',
}
ORIGINAL_ARRAYS_SHA256 = {
    'local': '836ce634c677f5b171c69c525a8d5cf6d018b30414f06427c236c8c08803bff7',
    'remote': '81f51be898714b17602eaa63e51d945c7a7552cf0e0e25648fbe863948f4fe48',
}
WEIGHT_SHA256 = (
    '6fbc460e96b527aa6b54ab345195d141716dd4e34094baec92c65344f8bac298',
    '424ead8a89f71d4e83858da7f28335665c4d61a8797b121cfaa26a56d1f5ea6a',
)
RSQRT_COEFFICIENTS = (
    0xBEF497B73FBD25EE, 0xBEDFEA6B3FB7A7E6, 0xBECDFF353FB29DBE, 0xBEBE58E33FADF85E,
    0xBEB0956F3FA9AB4A, 0xBEA4671B3FA5AC16, 0xBE998F8E3FA1F1FE, 0xBE8FDC3F3F9E758D,
    0xBE8723D63F9B3066, 0xBE7E88713F981D0C, 0xBE7042093F9536BF, 0xBE6344EC3F92795B,
    0xBE5769013F8FE140, 0xBE4C8C3F3F8D6B3C, 0xBE42919B3F8B147D, 0xBE3960253F88DA83,
    0xBE2CF3FF3F85BF79, 0xBE1E55123F81DD42, 0xBE11A96C3F7C99F7, 0xBE0698873F7607EF,
    0xBDF9BA233F6FF2C6, 0xBDE880283F6A4BC0, 0xBDD92AEE3F650674, 0xBDCB73013F60185B,
    0xBDBF1DE73F5B7871, 0xBDB3FB643F571EF6, 0xBDA9E3563F530530, 0xBDA0B4203F4F2545,
    0xBD9851683F4B7A15, 0xBD90A31D3F47FF1B, 0xBD8994B63F44B05A, 0xBD8314903F418A48,
)
# Full trace ABI, independently emitted by scripts/qk_norm256_reference.c.
# Tree order is chunk-major, then levels 8,4,2,1. Partial is its root.
TRACE_FIELDS = (
    ('squares', 256), ('square_flags', 256), ('tree', 240), ('tree_flags', 240),
    ('partials', 16), ('partial_flags', 16), ('running', 16), ('running_flags', 16),
    ('mean', 1), ('mean_flags', 1), ('mean_eps', 1), ('mean_eps_flags', 1),
    ('rsqrt_norm', 1), ('rsqrt_scale', 1), ('rsqrt_index', 1),
    ('rsqrt_values', 8), ('rsqrt_flags', 8), ('inverse', 1), ('domain_error', 1),
    ('gamma', 256), ('gamma_flags', 256), ('scaled', 256), ('scaled_flags', 256),
    ('output_fp32', 256), ('output_fp32_flags', 256),
    ('output_bf16', 256), ('output_bf16_flags', 256),
    ('arithmetic_flags', 1), ('conversion_flags', 1), ('aggregate_flags', 1),
)
TRACE_WORDS = sum(size for _, size in TRACE_FIELDS)
TRACE_OFFSETS = {}
_offset = 0
for _field, _size in TRACE_FIELDS:
    TRACE_OFFSETS[_field] = (_offset, _offset + _size)
    _offset += _size


def _words(values: Iterable[int], name: str) -> tuple[int, ...]:
    if isinstance(values, np.ndarray):
        require(values.dtype == np.uint32 and values.shape == (256,), f'{name}: expected uint32[256]')
    result = tuple(values)
    require(len(result) == 256, f'{name}: expected 256 words')
    require(all(isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_))
                and 0 <= v <= 0xFFFFFFFF for v in result), f'{name}: expected uint32 bit words')
    return tuple(int(v) for v in result)


def admit(inputs: Iterable[int], weights: Iterable[int], *, policy: int = POLICY,
          role: int = ROLE_Q, head_dim: int = HEAD_DIM, epsilon: int = EPSILON) -> int:
    """Match wrapper rejection priority: descriptor, nonfinite, finite range.

    BF16 words are widened into binary32 containers. Only signed zeros and
    normal exponents 95..158 are accepted. The raw Q gate is not arithmetic
    input and every 16-bit gate encoding is transported without inspection.
    """
    if any(type(v) is not int for v in (policy, role, head_dim, epsilon)) or (
        policy != POLICY or role not in (ROLE_Q, ROLE_K) or head_dim != HEAD_DIM or epsilon != EPSILON
    ):
        return STATUS_DESCRIPTOR
    x, w = _words(inputs, 'input'), _words(weights, 'weight')
    if any((v & 0x7F800000) == 0x7F800000 for v in x + w):
        return STATUS_NONFINITE
    if any((v & 0xFFFF) or ((v & 0x7FFFFFFF) and not 95 <= ((v >> 23) & 255) <= 158) for v in x + w):
        return STATUS_RANGE
    return STATUS_OK


def rsqrt_trace(word: int) -> dict:
    """Literal RTL normalization + PWL + one Newton step, including flags."""
    require(type(word) is int and 0 <= word <= 0xFFFFFFFF, 'rsqrt expects uint32')
    exponent = (word >> 23) & 255
    e = exponent - 127
    odd = e & 1
    norm = ((128 if odd else 127) << 23) | (word & 0x7FFFFF)
    scale = ((127 - ((e - odd) // 2)) & 255) << 23
    index = (odd << 4) | ((word >> 19) & 15)
    coeff = RSQRT_COEFFICIENTS[index]
    values, flags = [], []
    def step(operation, a, b):
        value, flag = operation(a, b)
        values.append(value); flags.append(flag)
        return value
    mx = step(mul_rne, coeff >> 32, norm)
    y0 = step(add_rne, mx, coeff & 0xFFFFFFFF)
    y2 = step(mul_rne, y0, y0)
    xy2 = step(mul_rne, norm, y2)
    half = step(mul_rne, 0x3F000000, xy2)
    term = step(add_rne, 0x3FC00000, half ^ 0x80000000)
    y1 = step(mul_rne, y0, term)
    scaled = step(mul_rne, y1, scale)
    zero = word == 0
    pinf = word == 0x7F800000
    normal = not (word & 0x80000000) and 2 <= exponent <= 253
    inverse = 0x7F800000 if zero else 0 if pinf else scaled if normal else 0x7FC00000
    return {'rsqrt_norm': norm, 'rsqrt_scale': scale, 'rsqrt_index': index,
            'rsqrt_values': tuple(values), 'rsqrt_flags': tuple(flags),
            'inverse': inverse, 'domain_error': int(not (zero or pinf or normal))}


def head_trace(inputs: Iterable[int], weights: Iterable[int]) -> dict:
    """Compute all observable candidate operations for one admitted head."""
    x, w = _words(inputs, 'input'), _words(weights, 'weight')
    require(admit(x, w) == STATUS_OK, 'head is outside candidate admission domain')
    trace = {}
    arithmetic_flags = 0
    def operations(name, op, pairs):
        nonlocal arithmetic_flags
        values, flags = [], []
        for a, b in pairs:
            value, flag = op(a, b)
            values.append(value); flags.append(flag); arithmetic_flags |= flag
        trace[name] = tuple(values)
        trace[{'squares': 'square_flags'}.get(name, name + '_flags')] = tuple(flags)
        return values
    squares = operations('squares', mul_rne, ((v, v) for v in x))
    tree, tree_flags, partials, partial_flags = [], [], [], []
    for chunk in range(16):
        level = squares[chunk * 16:(chunk + 1) * 16]
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                value, flag = add_rne(level[i], level[i + 1])
                tree.append(value); tree_flags.append(flag); next_level.append(value)
                arithmetic_flags |= flag
            level = next_level
        partials.append(level[0]); partial_flags.append(tree_flags[-1])
    trace.update(tree=tuple(tree), tree_flags=tuple(tree_flags), partials=tuple(partials), partial_flags=tuple(partial_flags))
    total = 0
    running, running_flags = [], []
    for part in partials:
        total, flag = add_rne(total, part)
        running.append(total); running_flags.append(flag); arithmetic_flags |= flag
    trace['running'], trace['running_flags'] = tuple(running), tuple(running_flags)
    trace['mean'], trace['mean_flags'] = mul_rne(total, 0x3B800000)
    trace['mean_eps'], trace['mean_eps_flags'] = add_rne(trace['mean'], EPSILON)
    arithmetic_flags |= trace['mean_flags'] | trace['mean_eps_flags']
    trace.update(rsqrt_trace(trace['mean_eps']))
    for flag in trace['rsqrt_flags']:
        arithmetic_flags |= flag
    gamma = operations('gamma', add_rne, ((0x3F800000, v) for v in w))
    scaled = operations('scaled', mul_rne, ((v, trace['inverse']) for v in x))
    output = operations('output_fp32', mul_rne, zip(scaled, gamma))
    converted = [bf16_convert(v) for v in output]
    trace['output_bf16'] = tuple(v for v, _ in converted)
    trace['output_bf16_flags'] = tuple(f for _, f in converted)
    conversion_flags = 0
    for _, flag in converted:
        conversion_flags |= flag
    trace.update(arithmetic_flags=arithmetic_flags, conversion_flags=conversion_flags,
                 aggregate_flags=arithmetic_flags | conversion_flags)
    return trace


def trace_words(trace: dict) -> tuple[int, ...]:
    result = []
    for field, size in TRACE_FIELDS:
        value = trace[field]
        words = (value,) if size == 1 else tuple(value)
        require(len(words) == size, f'trace field width mismatch: {field}')
        result.extend(words)
    require(len(result) == TRACE_WORDS, 'trace size mismatch')
    return tuple(result)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_arrays(data: dict, origin: dict) -> None:
    schema = {
        'input_bf16_u32': (np.dtype('<u4'), (2560, 256)),
        'native_bf16_u32': (np.dtype('<u4'), (2560, 256)),
        'gate_bf16_u32': (np.dtype('<u4'), (2048, 256)),
        'weight_bf16_u32': (np.dtype('<u4'), (2, 256)),
        'phase': (np.dtype('u1'), (2560,)), 'token': (np.dtype('u1'), (2560,)),
        'head': (np.dtype('u1'), (2560,)), 'role': (np.dtype('u1'), (2560,)),
        'gate_index': (np.dtype('<i4'), (2560,)),
    }
    require(set(data) == set(schema), 'corpus array schema drift')
    for key, (dtype, shape) in schema.items():
        arr = data[key]
        require(arr.dtype == dtype and arr.shape == shape, f'corpus dtype/shape drift: {key}')
        require(hashlib.sha256(arr.tobytes()).hexdigest() == origin['array_sha256'][key], f'corpus array hash drift: {key}')
        if key.endswith('_u32'):
            require(not np.any(arr & 0xFFFF), f'non-BF16 container: {key}')
    row, gate = 0, 0
    for phase in range(2):
        for role, heads in enumerate((8, 2)):
            size = 128 * heads; sl = slice(row, row + size)
            require(np.all(data['phase'][sl] == phase) and np.all(data['role'][sl] == role), 'corpus source mapping drift')
            require(np.array_equal(data['token'][sl], np.repeat(np.arange(128), heads)), 'token mapping drift')
            require(np.array_equal(data['head'][sl], np.tile(np.arange(heads), 128)), 'head mapping drift')
            expected_gate = np.arange(gate, gate + size) if role == 0 else np.full(size, -1)
            require(np.array_equal(data['gate_index'][sl], expected_gate), 'gate mapping drift')
            row += size
            if role == 0: gate += size
    for role in range(2):
        raw = (data['weight_bf16_u32'][role] >> 16).astype('<u2').tobytes()
        require(hashlib.sha256(raw).hexdigest() == WEIGHT_SHA256[role], 'pinned weight hash drift')


def load_corpus(name: str, fixture_dir: Path | None = None) -> tuple[dict, dict]:
    """Verify independent source pins before returning owned read-only arrays.

    Neither metadata's self-declared status nor an NPZ claimed hash establishes
    trust. Code-fixed hashes pin the complete metadata, source reports and NPZ.
    """
    require(name in BUNDLE_SHA256, 'unknown corpus')
    directory = FIXTURES if fixture_dir is None else Path(fixture_dir)
    require(_sha256(directory / 'provenance.json') == PROVENANCE_SHA256, 'frozen provenance hash mismatch')
    manifest = json.loads((directory / 'provenance.json').read_text())
    require(manifest['schema_version'] == 1 and manifest['policy'] == POLICY
            and manifest['head_dim'] == HEAD_DIM and manifest['epsilon_word'] == EPSILON, 'corpus contract drift')
    require(manifest['arithmetic_recomputed_when_freezing'] is False, 'corpus source origin drift')
    origin = manifest['corpora'][name]
    require(origin['original_audit_report']['sha256'] == ORIGINAL_REPORT_SHA256[name]
            and origin['original_audit_arrays']['sha256'] == ORIGINAL_ARRAYS_SHA256[name], 'historical authority drift')
    require(_sha256(directory / (name + '_original_report.json')) == ORIGINAL_REPORT_SHA256[name], 'historical report hash mismatch')
    require(_sha256(directory / 'payload_manifest.json') == '31d12acb34c7c0c4ad031a93a1ef46203ec21e193865728ada407dbbe014cd66', 'payload manifest hash mismatch')
    path = directory / (name + '.npz')
    require(_sha256(path) == BUNDLE_SHA256[name] == origin['bundle']['sha256'], 'frozen corpus hash mismatch')
    with np.load(path, allow_pickle=False) as bundle:
        data = {key: bundle[key] for key in bundle.files}
    _validate_arrays(data, origin)
    for array in data.values():
        array.flags.writeable = False
    return data, {**origin, 'model_id': manifest['model_id'], 'revision': manifest['revision'],
                  'framework_revision': manifest['framework_revision'], 'layer_id': 3,
                  'policy': POLICY, 'provenance_sha256': PROVENANCE_SHA256}


def verify_fixtures(fixture_dir: Path | None = None) -> None:
    for name in ('local', 'remote'):
        load_corpus(name, fixture_dir)
