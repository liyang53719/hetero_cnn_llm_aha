#!/usr/bin/env python3
"""Fail-closed, local-only Qwen2 M128 input recipe. Default: stdlib cold check."""
from __future__ import annotations

import argparse
import ast
import copy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PINS_SHA256 = '503b452bb030050f0a570cde89448a4f5bd4c8b95b86e1d1cdb81a362729618d'
OUTPUT_PREFIX = 'work/qwen2_live_qkv_inputs_m128'
MODEL_SOURCE = 'config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
SCALAR_SOURCE = 'scripts/qwen2_rms_rope_policy_diagnostic.py'
PRODUCER_SOURCE = 'scripts/qwen2_layer0_model_gate.py'
RUNTIME_IDENTITY_SCOPE = 'Current key libraries/interpreter only; no complete historical runtime equivalence.'
C_FLAGS = ('-O2', '-std=c11', '-shared', '-fPIC', '-fno-fast-math',
           '-ffp-contract=off', '-fno-tree-vectorize', '-fno-builtin')
STAGES = {'acquire': 'subset_manifest.json', 'materialize': 'INPUTS_READY.json',
          'capture': 'REFERENCE.json', 'bootstrap-capture': 'BOOTSTRAP_REFERENCE.json', 'audit': 'AUDIT.json'}


class Rejected(ValueError):
    """A failed identity, path, scope or immutable-output gate."""


def need(ok, message):
    if not ok:
        raise Rejected(message)


def same(a, b):
    """JSON equality with exact types: bool is never an integer dimension."""
    if type(a) is not type(b):
        return False
    if isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in b)
    if isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def fields(actual, expected, label):
    need(type(actual) is dict and all(k in actual and same(actual[k], v)
         for k, v in expected.items()), label + ' identity/type/geometry drift')


def exact_keys(value, expected, label):
    need(type(value) is dict and set(value) == set(expected), label + ' required/exact field coverage')


def digest(value, label):
    need(type(value) is str and bool(re.fullmatch(r'[0-9a-f]{64}', value)), label + ' SHA256 format')


def python_identity():
    path = Path(sys.executable).resolve()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}


def compiler_identity():
    # Fixed local compiler only, never a path taken from a receipt. This is
    # version interrogation, not compilation or loading the generated binary.
    import subprocess
    path = Path('/usr/bin/gcc').resolve()
    return {'compiler_sha256': sha(path.read_bytes()),
            'compiler': subprocess.check_output(['/usr/bin/gcc', '--version'], text=True,
                                                timeout=10).splitlines()[0]}


def compile_command(directory):
    build = directory / 'rope_build'
    return ['/usr/bin/gcc', *C_FLAGS, str(build / 'independent.c'), '-lm', '-o',
            str(build / 'independent.so')]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def timestamp(value):
    need(type(value) is str, 'timestamp type')
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError as e:
        raise Rejected('timestamp format') from e
    need(parsed.utcoffset() == dt.timedelta(0), 'UTC timestamp required')


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def parse_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out

    def nonfinite(value):
        raise Rejected('nonfinite JSON: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def safe_path(root, relative):
    """No absolute/dot/backslash/symlink aliases, including parent symlinks."""
    need(type(relative) is str and relative and '\\' not in relative,
         'unsafe path spelling')
    path = Path(relative)
    need(not path.is_absolute() and all(p not in ('', '.', '..') for p in relative.split('/')),
         'path must be canonical repository-relative')
    root = root.resolve()
    current = root
    for part in path.parts:
        current /= part
        need(not current.is_symlink(), 'symlink path refused: ' + relative)
    need(current.resolve().is_relative_to(root), 'path escaped root')
    return current


def checked(root, relative, pin):
    path = safe_path(root, relative)
    need(path.is_file(), 'missing pinned file: ' + relative)
    raw = path.read_bytes()
    fields({'bytes': len(raw), 'sha256': sha(raw)}, pin, relative)
    return raw


def load_pins(root=ROOT):
    raw = safe_path(root, 'candidates/qwen2_live_qkv_inputs_m128/pins.json').read_bytes()
    need(sha(raw) == PINS_SHA256, 'recipe pin file drift')
    return parse_json(raw)


def source_check(root, pins):
    need((root / '.git').exists(), 'checkout root required')
    check_contract(pins)
    for path, pin in pins['sources'].items():
        checked(root, path, pin)
    payload = parse_json((root / 'config/payload_pins/qwen2_layer0.json').read_bytes())
    by_name = {t['local_name']: t for t in payload['tensors']}
    for tensor in pins['tensors']:
        expected = {k: v for k, v in tensor.items() if k != 'file'}
        fields(by_name[tensor['local_name']], expected, 'upstream payload pin')
        segments = by_name[tensor['local_name']]['segments']
        need(len(segments) == 1, 'subset must have one bounded range per tensor')
    need(len(pins['tensors']) == 8 and sum(t['bytes'] for t in pins['tensors']) == 7085056,
         'eight-tensor byte coverage drift')
    need(len(pins['roles']) == 9 and len(pins['references']) == 9, 'node coverage drift')
    official_nodes(root, pins)
    rope_source(root, pins)
    return {'pinned_source_files': len(pins['sources']), 'official_ast_nodes': 15,
            'raw_tensors': 8, 'payload_bytes': 7085056, 'input_roles': 9,
            'reference_nodes': 9}


def recipe_identity(root):
    names = ('recipe.py', 'capture.py', 'pins.json')
    return {n: sha(safe_path(root, 'candidates/qwen2_live_qkv_inputs_m128/' + n).read_bytes())
            for n in names}


def stage_path(root, value):
    # Only one dedicated ignored namespace, then exactly run-id/stage-id.
    need(type(value) is str and re.fullmatch(re.escape(OUTPUT_PREFIX) +
         r'/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value),
         'expected work/qwen2_live_qkv_inputs_m128/<run-id>/<stage-id>')
    return safe_path(root, value)


def fresh_output(root, value, inputs=()):
    out = stage_path(root, value)
    need(not out.exists(), 'output already exists; select a fresh identity')
    for source in inputs:
        need(not out.is_relative_to(source) and not source.is_relative_to(out),
             'output overlaps an input')
    return out


def start_output(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(exist_ok=False)


def write_new(path, raw):
    need(not path.is_symlink(), 'output symlink refused')
    with path.open('xb') as stream:
        stream.write(raw)


def report(root, pins, stage):
    return {'contract': pins['contract'], 'stage': stage, 'recorded_utc': stamp(),
            'recipe': recipe_identity(root), 'source_pins_sha256': PINS_SHA256}


def verify_report(value, root, pins, stage):
    fields(value, {'contract': pins['contract'], 'stage': stage,
                  'recipe': recipe_identity(root), 'source_pins_sha256': PINS_SHA256}, stage)
    timestamp(value.get('recorded_utc'))
    extras = {
        'acquire': {'status', 'payload_bytes', 'acquisition', 'tensors'},
        'materialize': {'status', 'roles', 'subset', 'subset_manifest_sha256', 'rope', 'rope_build',
                        'python', 'python_executable', 'torch_imported', 'numpy_imported'},
        'capture': {'status', 'subset', 'inputs', 'subset_manifest_sha256', 'input_ready_sha256',
                    'official_ast_nodes', 'outputs', 'runtime', 'official_ast_subset_executed',
                    'old_runtime_identity_claimed', 'posthoc_oracle_only', 'numerical_acceptance_claimed',
                    'transformers_imported', 'rotary_cache_max_position_embeddings',
                    'original_config_max_position_embeddings', 'configuration_equivalence_claimed',
                    'layout_rule', 'reference_hash_comparison', 'old_raw_archive_read', 'reference_freeze'},
    }
    allowed = {'contract', 'stage', 'recorded_utc', 'recipe', 'source_pins_sha256'} | extras.get(stage, set())
    need(stage in extras, 'unsupported report reader stage')
    exact_keys(value, allowed, stage)


def verify_http(receipt, spec, pins):
    shard = pins['shard']
    fields(receipt, {'requested_url': shard['url'],
           'request_range': 'bytes=%d-%d' % (spec['start'], spec['end']),
           'status': 206, 'content_range': 'bytes %d-%d/%d' %
           (spec['start'], spec['end'], shard['file_bytes']),
           'bytes': spec['bytes'], 'sha256': spec['sha256']}, 'HTTP206 receipt')
    timestamp(receipt.get('acquired_at'))
    need(set(receipt) == {'acquired_at', 'requested_url', 'request_range', 'status',
                         'content_range', 'bytes', 'sha256'}, 'unknown HTTP receipt fields')


def read_subset(root, pins, relative, frozen=False):
    if frozen:
        need(relative == pins['frozen_directory'], 'frozen input alias refused')
        directory = safe_path(root, relative)
        raw_manifest = checked(directory, 'subset_manifest.json', pins['frozen_metadata']['subset_manifest.json'])
    else:
        directory = stage_path(root, relative)
        raw_manifest = safe_path(directory, 'subset_manifest.json').read_bytes()
    manifest = parse_json(raw_manifest)
    if frozen:
        fields(manifest, {'model_id': pins['contract']['model_id'],
               'revision': pins['contract']['revision'], 'payload_bytes': 7085056,
               'old_pass_inherited': False, 'old_manifest_reproduced': False,
               'full_checkpoint_sha256_verified': False, 'official_forward_executed': False,
               'rtl_executed': False, 'status': 'RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY'}, 'frozen subset')
    else:
        verify_report(manifest, root, pins, 'acquire')
        fields(manifest, {'payload_bytes': 7085056, 'status': 'RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY'}, 'subset')
        need(manifest.get('acquisition') in ('verified_frozen_copy', 'fresh_HTTP206'), 'acquisition provenance missing')
    tensors = manifest.get('tensors')
    need(type(tensors) is list and len(tensors) == 8, 'exact eight-tensor inventory required')
    values = {}
    for entry, spec in zip(tensors, pins['tensors']):
        fields(entry, spec, 'tensor record')
        need(set(entry) == set(spec) | {'http_ranges'}, 'unknown tensor record fields')
        need(type(entry.get('http_ranges')) is list and len(entry['http_ranges']) == 1,
             'exact one HTTP206 receipt required')
        receipt = entry['http_ranges'][0]
        verify_http(receipt, spec, pins)
        receipt_name = spec['local_name'] + '.receipt.json'
        receipt_raw = (checked(directory, receipt_name, pins['frozen_metadata'][receipt_name])
                       if frozen else safe_path(directory, receipt_name).read_bytes())
        need(same(parse_json(receipt_raw), receipt), 'standalone receipt differs from manifest')
        values[spec['local_name']] = checked(directory, spec['file'],
                                            {'bytes': spec['bytes'], 'sha256': spec['sha256']})
    return manifest, values, sha(raw_manifest), directory


def acquire(root, pins, out, *, reuse_frozen=False, download=False):
    need(reuse_frozen != download, 'choose exactly one: --reuse-frozen or --download')
    old = None
    guard_paths = [safe_path(root, pins['frozen_directory'])] if reuse_frozen else []
    guard = boundary_snapshot(root, pins, guard_paths)
    if reuse_frozen:
        old, raw, _, _ = read_subset(root, pins, pins['frozen_directory'], frozen=True)
    # Even an empty pre-existing directory is rejected before any HTTP request.
    start_output(out)
    records = []
    for index, spec in enumerate(pins['tensors']):
        if old is not None:
            data, receipt = raw[spec['local_name']], old['tensors'][index]['http_ranges'][0]
        else:
            data, receipt = download_range(pins, spec)
        verify_http(receipt, spec, pins)
        need(len(data) == spec['bytes'] and sha(data) == spec['sha256'], 'acquired byte/hash drift')
        write_new(out / spec['file'], data)
        write_new(out / (spec['local_name'] + '.receipt.json'), json_bytes(receipt))
        records.append({**spec, 'http_ranges': [receipt]})
    result = report(root, pins, 'acquire')
    result.update(status='RECOVERED_PINNED_QWEN2_PREFIX_SUBSET_ONLY', payload_bytes=7085056,
                  acquisition='verified_frozen_copy' if reuse_frozen else 'fresh_HTTP206', tensors=records)
    finish_boundary(root, pins, guard_paths, guard)
    write_new(out / STAGES['acquire'], json_bytes(result))
    return result


def download_range(pins, spec):
    # The URL and range come only from the hash-bound pin file; no arbitrary URL.
    import urllib.request
    size = spec['bytes']
    need(0 < size <= 4718592, 'unbounded range refused')
    request = urllib.request.Request(pins['shard']['url'], headers={
        'Range': 'bytes=%d-%d' % (spec['start'], spec['end']),
        'Accept-Encoding': 'identity', 'User-Agent': 'hetero-qwen2-m128-recipe/1'})
    expected = 'bytes %d-%d/%d' % (spec['start'], spec['end'], pins['shard']['file_bytes'])
    with urllib.request.urlopen(request, timeout=90) as response:
        need(response.status == 206 and response.headers.get('Content-Range') == expected,
             'server ignored/mismatched range; body refused')
        need(response.headers.get('Content-Length') == str(size), 'range length drift')
        need(response.headers.get('Content-Encoding', 'identity') == 'identity', 'encoded range refused')
        raw = response.read(size + 1)
    receipt = {'acquired_at': stamp(), 'requested_url': pins['shard']['url'],
               'request_range': 'bytes=%d-%d' % (spec['start'], spec['end']),
               'status': 206, 'content_range': expected, 'bytes': len(raw), 'sha256': sha(raw)}
    verify_http(receipt, spec, pins)
    return raw, receipt


def widen_bf16(raw):
    need(len(raw) % 2 == 0, 'BF16 byte length')
    # Exact storage widening, no floating-point conversion or gamma addition.
    return b''.join(b'\x00\x00' + raw[i:i + 2] for i in range(0, len(raw), 2))


def transpose_words(raw, rows, columns):
    need(type(rows) is int and type(columns) is int and rows > 0 and columns > 0 and
         len(raw) == rows * columns * 2, 'BF16 transpose shape')
    result = bytearray(len(raw))
    for row in range(rows):
        for column in range(columns):
            src, dst = (row * columns + column) * 2, (column * rows + row) * 2
            result[dst:dst + 2] = raw[src:src + 2]
    return bytes(result)


def bf16_rne_word(word):
    need(type(word) is int and 0 <= word <= 0xffffffff and (word & 0x7f800000) != 0x7f800000,
         'finite FP32 word required')
    rounded = (word + 0x7fff + ((word >> 16) & 1)) & 0xffff0000
    need((rounded & 0x7f800000) != 0x7f800000, 'BF16 overflow')
    return rounded


def rope_source(root, pins):
    source = (root / SCALAR_SOURCE).read_text()
    assignments = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == 'C_SOURCE' for t in n.targets)]
    need(len(assignments) == 1, 'unique scalar C source required')
    code = ast.literal_eval(assignments[0].value)
    need(type(code) is str and sha(code.encode()) == pins['rope_c_source_sha256'], 'scalar C pin drift')
    return code


def generate_rope(root, pins, out):
    import ctypes
    import subprocess
    need(sys.byteorder == 'little', 'little-endian C FP32 host required')
    build = out / 'rope_build'
    build.mkdir()
    source, binary = build / 'independent.c', build / 'independent.so'
    write_new(source, rope_source(root, pins).encode())
    command = compile_command(out)
    done = subprocess.run(command, text=True, capture_output=True, timeout=30)
    write_new(build / 'build.log', (done.stdout + done.stderr).encode())
    need(done.returncode == 0, 'scalar C compile failed')
    lib = ctypes.CDLL(str(binary))
    lib.environment.restype = ctypes.c_int
    lib.rope.argtypes = [ctypes.POINTER(ctypes.c_float)]
    lib.rope.restype = ctypes.c_int
    need(ctypes.sizeof(ctypes.c_float) == 4 and lib.environment() == 1, 'C FP32 RNE environment')
    array = (ctypes.c_float * (192 + 5 * 16384))()
    need(lib.rope(array) == 1, 'C RoPE generation failed')
    raw = bytes(array)
    fields({'bytes': len(raw), 'sha256': sha(raw)}, pins['rope'], 'raw C RoPE table')
    write_new(out / 'rope_full.f32le', raw)
    # Pin the rounded 256-row duplicated table too; only first128 raw rows feed inputs.
    for index, name in ((3, 'cos'), (4, 'sin')):
        table = raw[(192 + index * 16384) * 4:(192 + (index + 1) * 16384) * 4]
        doubled = b''.join(table[i:i + 256] * 2 for i in range(0, len(table), 256))
        need(sha(doubled) == pins['rope_table_digests'][name], 'rounded RoPE table pin drift')
    identity = {'command': command, 'source_sha256': sha(source.read_bytes()),
                'binary_sha256': sha(binary.read_bytes()), **compiler_identity(),
                'historical_binary_identity_claimed': False}
    return raw, identity


def input_x(raw):
    need(len(raw) == 256 * 1536 * 2, 'exact original embedding range required')
    return widen_bf16(raw[:128 * 1536 * 2])


def input_rope(raw):
    need(len(raw) == 328448, 'complete scalar RoPE table required')
    table = bytearray(2 * 1024 * 64 * 4)
    for index in range(2):
        src = (192 + (index + 1) * 16384) * 4
        dst = index * 1024 * 64 * 4
        table[dst:dst + 128 * 64 * 4] = raw[src:src + 128 * 64 * 4]
    return bytes(table)


def materialize(root, pins, subset, out):
    guard_paths = [stage_path(root, subset)]
    guard = boundary_snapshot(root, pins, guard_paths)
    _, raw, manifest_sha, _ = read_subset(root, pins, subset)
    start_output(out)
    values = {}
    for letter in 'qkv':
        width = 1536 if letter == 'q' else 256
        values['w' + letter] = transpose_words(raw['self_attn.' + letter + '_proj.weight'], width, 1536)
        values['b' + letter] = widen_bf16(raw['self_attn.' + letter + '_proj.bias'])
    values['gamma0'] = widen_bf16(raw['input_layernorm.weight'])
    values['x'] = input_x(raw['embed_tokens.rows_0_255'])
    rope, build = generate_rope(root, pins, out)
    values['rope'] = input_rope(rope)
    records = {}
    for name, spec in pins['roles'].items():
        data = values[name]
        fields({'bytes': len(data), 'sha256': sha(data)},
               {'bytes': spec['bytes'], 'sha256': spec['sha256']}, 'materialized ' + name)
        write_new(out / (name + '.bin'), data)
        records[name] = {**spec, 'file': name + '.bin'}
    result = report(root, pins, 'materialize')
    result.update(status='PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION', roles=records,
                  subset=subset, subset_manifest_sha256=manifest_sha, rope={**pins['rope'], 'file': 'rope_full.f32le'},
                  rope_build=build, python=sys.version, python_executable=python_identity(),
                  torch_imported=False, numpy_imported=False)
    finish_boundary(root, pins, guard_paths, guard)
    write_new(out / STAGES['materialize'], json_bytes(result))
    return result


def check_rope_build(root, pins, directory, build):
    exact_keys(build, {'command', 'source_sha256', 'binary_sha256', 'compiler_sha256',
                      'compiler', 'historical_binary_identity_claimed'}, 'RoPE build')
    fields(build, {'command': compile_command(directory),
                   'source_sha256': pins['rope_c_source_sha256'],
                   'historical_binary_identity_claimed': False}, 'RoPE build source/flags')
    for key in ('source_sha256', 'binary_sha256', 'compiler_sha256'):
        digest(build[key], key)
    need(type(build['compiler']) is str and bool(build['compiler']) and '\n' not in build['compiler'],
         'compiler version line required')
    source = safe_path(directory, 'rope_build/independent.c').read_bytes()
    need(sha(source) == pins['rope_c_source_sha256'] and source == rope_source(root, pins).encode(),
         'generated C source provenance drift')
    binary = safe_path(directory, 'rope_build/independent.so').read_bytes()
    need(bool(binary) and sha(binary) == build['binary_sha256'], 'generated binary identity drift')
    fields(build, compiler_identity(), 'current compiler identity')


def read_inputs(root, pins, relative, subset, subset_sha):
    directory = stage_path(root, relative)
    raw = safe_path(directory, 'INPUTS_READY.json').read_bytes()
    value = parse_json(raw)
    verify_report(value, root, pins, 'materialize')
    fields(value, {'status': 'PINNED_PREFIX_INPUTS_READY_NO_MODEL_EXECUTION',
                  'subset': subset, 'subset_manifest_sha256': subset_sha,
                  'torch_imported': False, 'numpy_imported': False}, 'inputs')
    fields(value, {'python': sys.version, 'python_executable': python_identity()}, 'materializer Python provenance')
    check_rope_build(root, pins, directory, value['rope_build'])
    check_records(directory, value.get('roles'), pins['roles'], '.bin')
    need(same(value['rope'], {**pins['rope'], 'file': 'rope_full.f32le'}), 'exact RoPE metadata')
    checked(directory, 'rope_full.f32le', pins['rope'])
    return value, sha(raw), directory


def check_records(directory, records, expected, suffix):
    need(type(records) is dict and records.keys() == expected.keys(), 'exact named-node coverage required')
    result = {}
    for name, spec in expected.items():
        fields(records[name], {**spec, 'file': name + suffix}, 'node ' + name)
        need(set(records[name]) == set(spec) | {'file'}, 'unknown node metadata fields')
        result[name] = checked(directory, name + suffix, {'bytes': spec['bytes'], 'sha256': spec['sha256']})
    return result


def official_nodes(root, pins):
    source = (root / MODEL_SOURCE).read_text()
    tree = ast.parse(source)
    by_span = {(n.lineno, n.end_lineno, type(n).__name__): n for n in ast.walk(tree)
               if hasattr(n, 'lineno')}
    result = []
    for spec in pins['official_ast_nodes']:
        node = by_span.get((spec['line_start'], spec['line_end'], spec['node_type']))
        need(node is not None, 'missing pinned official AST node')
        need(sha(ast.get_source_segment(source, node).encode()) == spec['source_sha256'] and
             sha(ast.dump(node, include_attributes=False).encode()) == spec['ast_sha256'],
             'official AST node pin drift')
        result.append(node)
    need(len(result) == 15, 'official AST subset coverage drift')
    return result


def head_to_token(raw, shape):
    need(type(shape) is list and len(shape) == 4 and all(type(n) is int and n > 0 for n in shape),
         'Q/K shape types')
    batch, heads, rows, width = shape
    need(batch == 1 and rows == 128 and heads in (2, 12) and width == 128 and
         len(raw) == math.prod(shape) * 4, 'Q/K M128 logical shape/length')
    # The pinned producer exports transpose(0,2,1,3).reshape(B,M,H*D).
    span = width * 4
    return b''.join(raw[(h * rows + t) * span:(h * rows + t + 1) * span]
                    for t in range(rows) for h in range(heads))


def compare_reference(values, pins):
    result = {}
    for name, spec in pins['references'].items():
        raw = values[name]
        archive = head_to_token(raw, spec['shape']) if name in ('q', 'k') else raw
        need(sha(archive) == spec['token_major_sha256'], 'frozen M128 reference hash mismatch: ' + name)
        result[name] = {'logical_sha256': sha(raw), 'token_major_sha256': sha(archive),
                        'frozen_reference_hash_matches': True,
                        'layout': 'head-major -> token-major' if name in ('q', 'k') else 'unchanged'}
    return result


def expected_comparison(pins):
    return {name: {'logical_sha256': spec['sha256'],
                   'token_major_sha256': spec['token_major_sha256'],
                   'frozen_reference_hash_matches': True,
                   'layout': 'head-major -> token-major' if name in ('q', 'k') else 'unchanged'}
            for name, spec in pins['references'].items()}


def check_runtime(runtime, pins):
    required = set(pins['runtime_requirements']) | {'python', 'torch_build', 'affinity', 'environment',
                'new_process', 'historical_runtime_equivalence_claimed', 'native_files', 'identity_scope'}
    exact_keys(runtime, required, 'runtime')
    fields(runtime, pins['runtime_requirements'], 'reference runtime')
    fields(runtime, {'python': sys.version, 'new_process': True,
                    'historical_runtime_equivalence_claimed': False,
                    'identity_scope': RUNTIME_IDENTITY_SCOPE}, 'runtime claims/Python/identity scope')
    environment = pins['capture_environment']
    exact_keys(environment, {'ATEN_CPU_CAPABILITY','OMP_NUM_THREADS','MKL_NUM_THREADS',
                            'OPENBLAS_NUM_THREADS','PYTHONPATH','PYTHONNOUSERSITE'}, 'capture environment pin')
    fields(environment, {'ATEN_CPU_CAPABILITY':None, 'OMP_NUM_THREADS':'4', 'MKL_NUM_THREADS':'4',
                         'OPENBLAS_NUM_THREADS':'1', 'PYTHONNOUSERSITE':'1'}, 'capture environment policy')
    need(type(environment['PYTHONPATH']) is str and Path(environment['PYTHONPATH']).is_absolute(),
         'absolute pinned capture import environment required')
    need(same(runtime['environment'], environment), 'runtime environment coverage/dispatch/thread/import drift')
    affinity = sorted(os.sched_getaffinity(0))
    need(bool(affinity) and same(runtime['affinity'], affinity), 'runtime affinity identity/type/order drift')
    build = runtime['torch_build']
    need(type(build) is str and bool(build) and len(build) < 1024 * 1024, 'Torch build text required')
    need(sha(build.encode()) == pins['runtime_requirements']['torch_build_sha256'], 'Torch build text pin drift')
    for token in ('TORCH_VERSION=2.10.0', 'COMMIT_SHA=' + pins['runtime_requirements']['torch_commit'],
                  'USE_CUDA=0', 'CPU capability usage: AVX512'):
        need(token in build, 'Torch build configuration flag missing')
    libraries = runtime['native_files']
    exact_keys(libraries, {'python', 'torch_C', 'numpy_multiarray', 'libtorch_cpu.so',
                          'libc10.so', 'libtorch_python.so'}, 'key runtime libraries')
    for name, item in libraries.items():
        exact_keys(item, {'path', 'bytes', 'sha256'}, 'runtime library ' + name)
        need(type(item['bytes']) is int and item['bytes'] > 0 and type(item['path']) is str and
             Path(item['path']).is_absolute() and '..' not in Path(item['path']).parts and
             '\x00' not in item['path'] and '\n' not in item['path'], 'invalid current-runtime file receipt')
        digest(item['sha256'], 'runtime library ' + name)
        if name in ('libtorch_cpu.so', 'libc10.so', 'libtorch_python.so'):
            need(Path(item['path']).name == name, 'runtime library basename drift')
    need(same(libraries['python'], python_identity()), 'runtime interpreter file identity drift')
    need(same(libraries, runtime_files(ROOT, pins)), 'runtime native byte/hash identity drift')


def verify_reference_metadata(root, pins, subset, inputs, reference, subset_sha, inputs_sha):
    """Validate metadata/runtime only; never opens any reference tensor payload."""
    require_frozen_references(pins)
    directory = stage_path(root, reference)
    raw = safe_path(directory, 'REFERENCE.json').read_bytes()
    value = parse_json(raw)
    verify_report(value, root, pins, 'capture')
    fields(value, {'status': 'FRESH_OFFICIAL_AST_PREFIX_CAPTURE_ONLY', 'subset': subset,
                  'inputs': inputs, 'subset_manifest_sha256': subset_sha, 'input_ready_sha256': inputs_sha,
                  'official_ast_nodes': pins['official_ast_nodes'], 'official_ast_subset_executed': True,
                  'old_runtime_identity_claimed': False, 'posthoc_oracle_only': True,
                  'rotary_cache_max_position_embeddings': 256, 'original_config_max_position_embeddings': 32768,
                  'configuration_equivalence_claimed': False, 'old_raw_archive_read': False,
                  'numerical_acceptance_claimed': False, 'transformers_imported': False,
                  'layout_rule': pins['layout_rule'], 'reference_freeze': pins['reference_freeze'],
                  'reference_hash_comparison': expected_comparison(pins)}, 'reference')
    check_runtime(value.get('runtime'), pins)
    records = value.get('outputs')
    exact_keys(records, pins['references'], 'reference inventory')
    for name, spec in pins['references'].items():
        exact_keys(records[name], set(spec) | {'file'}, 'reference record')
        fields(records[name], {**spec, 'file':name + '.f32le'}, 'reference metadata ' + name)
    return value


def audit(root, pins, subset, inputs, reference, out):
    guard_paths = [stage_path(root, path) for path in (subset, inputs, reference)]
    guard = boundary_snapshot(root, pins, guard_paths, native=True)
    require_frozen_references(pins)
    _, _, subset_sha, _ = read_subset(root, pins, subset)
    _, inputs_sha, _ = read_inputs(root, pins, inputs, subset, subset_sha)
    directory = stage_path(root, reference)
    raw = safe_path(directory, 'REFERENCE.json').read_bytes()
    value = verify_reference_metadata(root, pins, subset, inputs, reference, subset_sha, inputs_sha)
    values = check_records(directory, value.get('outputs'), pins['references'], '.f32le')
    comparison = compare_reference(values, pins)
    need(same(value['reference_hash_comparison'], comparison), 'reference comparison receipt differs from recomputed hashes')
    start_output(out)
    result = report(root, pins, 'audit')
    result.update(status='VERIFIED_PREFIX_ARTIFACTS_ONLY', raw_tensors_verified=8,
                  materialized_roles_verified=9, fresh_reference_nodes_verified=9,
                  subset=subset, inputs=inputs, reference=reference,
                  subset_manifest_sha256=subset_sha, input_ready_sha256=inputs_sha,
                  reference_sha256=sha(raw), layout_rule=pins['layout_rule'],
                  reference_hash_comparison=comparison, model_execution_in_this_audit=False,
                  numerical_acceptance_claimed=False, old_raw_archive_read=False)
    finish_boundary(root, pins, guard_paths, guard, native=True)
    write_new(out / STAGES['audit'], json_bytes(result))
    return result


def check_contract(pins):
    fields(pins['contract'], {'recipe_id': 'qwen2-live-qkv-inputs-m128-v1',
           'rows': 128, 'token_ids': list(range(128)), 'position_ids': list(range(128)),
           'past_tokens': 0, 'direct_gamma': True, 'old_pass_inherited': False,
           'intermediate_preloads': 0}, 'M128 contract')
    need(set(pins['roles']) == {'x', 'gamma0', 'wq', 'wk', 'wv', 'bq', 'bk', 'bv', 'rope'}, 'nine roles')
    fields(pins['roles']['x'], {'shape': [128,1536], 'bytes': 786432,
           'sha256': 'ddcdcca67cb3e26007880a78074ea3eb70bf83e8d8060fa2258bb2c7644695df'}, 'M128 x')
    fields(pins['roles']['rope'], {'shape': [2,1024,64], 'bytes': 524288,
           'sha256': 'f6c6e15e3f480afe2e9ebfb05719ff8d20a77a5a5551aa8a44bf2a49870d77af'}, 'M128 RoPE')
    shapes = {'x':[1,128,1536], 'n0':[1,128,1536], 'qr':[1,128,1536],
              'kr':[1,128,256], 'v':[1,128,256], 'q':[1,12,128,128],
              'k':[1,2,128,128], 'cos':[128,128], 'sin':[128,128]}
    exact_keys(pins['references'], shapes, 'nine reference nodes')
    for name, shape in shapes.items():
        spec = pins['references'][name]
        exact_keys(spec, {'shape','bytes','native_dtype','export_dtype','sha256','token_major_sha256'}, 'reference pin')
        fields(spec, {'shape':shape, 'bytes':math.prod(shape)*4, 'native_dtype':'torch.bfloat16',
                     'export_dtype':'FP32 exact BF16 widening'}, 'M128 reference geometry')
    need(sum(s['bytes'] for s in pins['roles'].values()) == 7616512, 'M128 input byte budget')
    need(sum(s['bytes'] for s in pins['references'].values()) == 3670016, 'M128 reference byte budget')
    fields(pins['reference_freeze'], {'numeric_nodes':['n0','qr','q','kr','k','v'],
           'reference_bytes':3670016, 'numeric_node_bytes':2752512}, 'six numeric producer nodes')
    need('historical_comparison' not in pins, 'M16 historical comparison forbidden')


def require_frozen_references(pins):
    check_contract(pins)
    need(pins['reference_freeze']['status'] == 'FROZEN_FROM_REVIEWED_M128_BOOTSTRAP',
         'M128 references not frozen; bootstrap is never accepted')
    digest(pins['reference_freeze']['bootstrap_manifest_sha256'], 'bootstrap manifest')
    for name, spec in pins['references'].items():
        for key in ('sha256', 'token_major_sha256'):
            digest(spec[key], name + ' ' + key)
            need(spec[key] != '0' * 64, 'placeholder reference hash refused')
        if name not in ('q', 'k'):
            need(spec['sha256'] == spec['token_major_sha256'], 'unchanged-layout hash drift')
    for name, expected in pins['reference_crosschecks'].items():
        need(pins['references'][name]['sha256'] == expected, 'independent input/scalar reference cross-check')


def runtime_files(root, pins):
    result = {}
    for name, spec in pins['runtime_native_files'].items():
        path = Path(spec['path'])
        path = path if path.is_absolute() else safe_path(root, spec['path'])
        need(path.is_file(), 'missing runtime file ' + name)
        raw = path.read_bytes()
        fields({'bytes':len(raw), 'sha256':sha(raw)}, {k:spec[k] for k in ('bytes','sha256')}, 'runtime file ' + name)
        result[name] = {'path':str(path.resolve()), 'bytes':len(raw), 'sha256':sha(raw)}
    exact_keys(result, {'python','torch_C','numpy_multiarray','libtorch_cpu.so','libc10.so','libtorch_python.so'}, 'six native files')
    return result


def boundary_snapshot(root, pins, directories, native=False):
    # Explicit stages only: no data/tool reads in the default source-only path.
    source_check(root, pins)
    need(same(load_pins(root), pins), 'in-memory pins differ from reviewed pin file')
    files = {str(root / p): checked(root, p, spec) for p, spec in pins['sources'].items()}
    for name in ('recipe.py','capture.py','pins.json'):
        path = root / 'candidates/qwen2_live_qkv_inputs_m128' / name
        files[str(path)] = path.read_bytes()
    for directory in directories:
        need(directory.is_dir() and not directory.is_symlink(), 'missing/aliased input directory')
        for path in sorted(directory.rglob('*')):
            need(not path.is_symlink(), 'input symlink refused')
            if path.is_file():
                files[str(path)] = path.read_bytes()
    for path in (Path(sys.executable).resolve(), Path('/usr/bin/gcc').resolve()):
        files[str(path)] = path.read_bytes()
    result = {name:{'bytes':len(raw),'sha256':sha(raw)} for name,raw in files.items()}
    if native:
        result['native_files'] = runtime_files(root, pins)
    return result


def finish_boundary(root, pins, directories, before, native=False):
    need(same(before, boundary_snapshot(root, pins, directories, native=native)),
         'source/input/tool identity changed during execution; no completed manifest written')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(ROOT), help='must be this recipe\'s checkout root')
    parser.add_argument('--action', choices=('check', *STAGES), default='check')
    parser.add_argument('--execute', action='store_true', help='explicit local opt-in for the chosen stage')
    parser.add_argument('--download', action='store_true', help='additional opt-in for exact eight HTTP206 ranges')
    parser.add_argument('--reuse-frozen', action='store_true', help='read-only verification then copy exact original eight tensors')
    parser.add_argument('--out')
    parser.add_argument('--subset')
    parser.add_argument('--inputs')
    parser.add_argument('--reference')
    args = parser.parse_args(argv)
    try:
        root = Path(args.root).absolute()
        need(root == ROOT and root.resolve() == ROOT, '--root must identify this recipe\'s checkout')
        pins = load_pins(root)
        coverage = source_check(root, pins)
        if args.action in ('check', 'capture', 'audit'):
            require_frozen_references(pins)
        if args.action == 'check':
            need(not any((args.execute, args.download, args.reuse_frozen, args.out,
                          args.subset, args.inputs, args.reference)), 'cold check accepts no execution/path options')
            result = {'status': 'NOT_EXECUTED', 'cold_check': 'PASS', **coverage,
                      'torch_imported': 'torch' in sys.modules, 'numpy_imported': 'numpy' in sys.modules,
                      'network_used': False, 'raw_payload_read': False,
                      'model_executed': False, 'rtl_executed': False, 'outputs_written': False}
        else:
            need(args.execute, '--execute required; nothing executed')
            need(args.out is not None, '--out fresh identity required')
            needed = {'acquire': (), 'materialize': ('subset',),
                      'capture': ('subset', 'inputs'), 'bootstrap-capture': ('subset', 'inputs'), 'audit': ('subset', 'inputs', 'reference')}[args.action]
            for name in ('subset', 'inputs', 'reference'):
                need(bool(getattr(args, name)) == (name in needed), 'unexpected/missing --' + name)
            paths = [stage_path(root, getattr(args, n)) for n in needed]
            need(len(set(paths)) == len(paths), 'input stage aliases refused')
            if args.action != 'acquire':
                need(not args.download and not args.reuse_frozen, 'acquisition flags only allowed for acquire')
            if args.reuse_frozen:
                paths.append(safe_path(root, pins['frozen_directory']))
            out = fresh_output(root, args.out, paths)
            if args.action == 'acquire':
                result = acquire(root, pins, out, reuse_frozen=args.reuse_frozen, download=args.download)
            elif args.action == 'materialize':
                result = materialize(root, pins, args.subset, out)
            elif args.action in ('capture', 'bootstrap-capture'):
                # No Torch, NumPy or official code is imported by check/acquire/materialize/audit.
                import capture
                result = capture.capture(root, pins, args.subset, args.inputs, out, bootstrap=args.action == 'bootstrap-capture')
            else:
                result = audit(root, pins, args.subset, args.inputs, args.reference, out)
            result = {'status': result['status'], 'out': args.out, 'stage': args.action,
                      'manifest_sha256': sha((out / STAGES[args.action]).read_bytes())}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(json.dumps({'status': 'REJECTED', 'reason': str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
