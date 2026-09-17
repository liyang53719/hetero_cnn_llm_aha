"""C08.1 fail-closed full tensor/state export contract and exact comparator.

An independently frozen manifest enumerates ALL expected exports and commands;
the receipt cannot choose its own coverage or tolerances. This validator checks
files and records, not whether a producer really ran RTL. Approximate numerical
metrics remain unavailable until C02 freezes the formula and tolerance policy.
All exports in v1 are dense little-endian, with no padding or strided views.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Any

WIDTHS = {'f32le': 4, 'bf16le': 2, 'u32le': 4, 'i32le': 4}
IDENTITY = {'design_sha', 'reference_sha', 'input_sha256', 'model_revision', 'run_id'}


class ReceiptError(ValueError):
    pass


class ComparisonUnavailable(ReceiptError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise ReceiptError(why)


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ReceiptError('nonfinite JSON: ' + x)))


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()


def safe_file(root: Path, name: str) -> Path:
    need(isinstance(name, str) and name and '\\' not in name, 'invalid relative path')
    rel = Path(name)
    need(not rel.is_absolute() and '..' not in rel.parts and ':' not in name, 'path traversal')
    p = root.resolve()
    for part in rel.parts:
        p = p / part
        need(not p.is_symlink(), 'symlink exports are forbidden')
    need(p.is_file() and p.resolve().is_relative_to(root.resolve()), 'missing/outside file: ' + name)
    return p


def keys(obj: Any, fields: set[str], name: str) -> None:
    need(isinstance(obj, dict) and set(obj) == fields, 'unknown/missing fields: ' + name)


def integer(n: Any, lo: int, hi: int, name: str) -> int:
    need(type(n) is int and lo <= n <= hi, 'invalid integer: ' + name)
    return n


def hash_text(value: Any, n: int, name: str) -> None:
    need(isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(n) + '}', value) is not None, 'invalid hash: ' + name)


def identity(obj: Any) -> None:
    keys(obj, IDENTITY, 'identity')
    for field in ('design_sha', 'reference_sha', 'model_revision'):
        hash_text(obj[field], 40, field)
    hash_text(obj['input_sha256'], 64, 'input')
    need(isinstance(obj['run_id'], str) and bool(obj['run_id'].strip()), 'empty run ID')


def tensor_bytes(t: dict) -> int:
    need(isinstance(t['dtype'], str) and t['dtype'] in WIDTHS and isinstance(t['shape'], list) and 1 <= len(t['shape']) <= 8, 'dtype/shape')
    for n in t['shape']:
        integer(n, 1, (1 << 32) - 1, 'dimension')
    size = math.prod(t['shape']) * WIDTHS[t['dtype']]
    need(size <= (1 << 56), 'tensor byte extent overflow')
    return size


def validate_manifest(spec: dict) -> dict[str, dict]:
    keys(spec, {'version', 'identity', 'tensors', 'commands'}, 'manifest')
    integer(spec['version'], 1, 1, 'version'); identity(spec['identity'])
    need(isinstance(spec['tensors'], list) and bool(spec['tensors']), 'empty tensor inventory')
    tensors = {}
    fields = {'id', 'role', 'dtype', 'shape', 'reference', 'reference_sha256', 'comparison', 'generation', 'producer_pc'}
    for t in spec['tensors']:
        keys(t, fields, 'tensor')
        need(isinstance(t['id'], str) and bool(t['id']) and t['id'] not in tensors, 'duplicate/invalid tensor ID')
        need(t['role'] in ('tensor', 'state'), 'tensor role')
        tensor_bytes(t)
        hash_text(t['reference_sha256'], 64, 'reference tensor')
        need(isinstance(t['reference'], str) and bool(t['reference']), 'reference path')
        if t['comparison'] != 'bit_exact':
            raise ComparisonUnavailable('C02 comparison formula is not registered: ' + str(t['comparison']))
        integer(t['producer_pc'], 0, 65534, 'producer pc')
        if t['role'] == 'state':
            integer(t['generation'], 1, (1 << 64) - 1, 'state generation')
        else:
            need(t['generation'] is None, 'ordinary tensor must not name state generation')
        tensors[t['id']] = t
    need(isinstance(spec['commands'], list) and bool(spec['commands']), 'empty commands')
    pcs = []
    for c in spec['commands']:
        keys(c, {'pc', 'write_ack_bytes'}, 'command')
        pcs.append(integer(c['pc'], 0, 65534, 'command pc'))
        integer(c['write_ack_bytes'], 0, (1 << 56), 'expected write bytes')
    need(pcs == list(range(len(pcs))), 'noncontiguous/duplicate expected PCs')
    need(all(t['producer_pc'] in pcs for t in tensors.values()), 'unknown tensor producer')
    # Never infer write traffic from exported bytes: fused virtual tensors can
    # have no physical write, and padded DDR writes differ from canonical dumps.
    return tensors


def _finite(data: bytes, dtype: str) -> None:
    if dtype == 'f32le':
        need(all((x & 0x7f800000) != 0x7f800000 for (x,) in struct.iter_unpack('<I', data)), 'nonfinite FP32 export')
    elif dtype == 'bf16le':
        need(all((x & 0x7f80) != 0x7f80 for (x,) in struct.iter_unpack('<H', data)), 'nonfinite BF16 export')


def compare_files(actual: Path, reference: Path, dtype: str, size: int) -> dict:
    need(not actual.samefile(reference), 'actual/reference file alias')
    need(actual.stat().st_size == reference.stat().st_size == size, 'truncated or oversized tensor')
    width = WIDTHS[dtype]
    checked = differences = 0
    first = None
    ha, hr = hashlib.sha256(), hashlib.sha256()
    with actual.open('rb') as a, reference.open('rb') as r:
        while checked * width < size:
            amount = min(1 << 20, size - checked * width)
            x, y = a.read(amount), r.read(amount)
            need(len(x) == len(y) == amount, 'file changed during comparison')
            _finite(x, dtype); _finite(y, dtype)
            ha.update(x); hr.update(y)
            if x != y:
                for i in range(0, amount, width):
                    if x[i:i+width] != y[i:i+width]:
                        differences += 1
                        if first is None:
                            first = checked + i // width
            checked += amount // width
        need(a.read(1) == r.read(1) == b'', 'export grew during comparison')
    return {'elements': checked, 'different_elements': differences, 'first_difference': first,
            'actual_sha256': ha.hexdigest(), 'reference_sha256': hr.hexdigest()}


def verify(spec_path: Path, receipt_path: Path, root: Path) -> dict:
    # Contract must be frozen independently; receipt path is not an authority.
    before = sha_file(spec_path)
    spec = read_json(spec_path)
    tensors = validate_manifest(spec)
    receipt = read_json(receipt_path)
    keys(receipt, {'version', 'manifest_sha256', 'identity', 'exports', 'completions', 'attestation'}, 'receipt')
    integer(receipt['version'], 1, 1, 'receipt version')
    identity(receipt['identity'])
    need(receipt['manifest_sha256'] == before and receipt['identity'] == spec['identity'], 'manifest/run provenance mismatch')
    flags = receipt['attestation']
    keys(flags, {'cpu_fallback', 'host_intermediate_writes', 'unresolved_owners'}, 'attestation')
    need(all(type(x) is int and x == 0 for x in flags.values()), 'forbidden fallback/injection/unresolved owner')
    need(isinstance(receipt['completions'], list), 'completions must be a list')
    expected = spec['commands']
    need(len(receipt['completions']) == len(expected), 'incomplete/duplicate completions')
    for c, e in zip(receipt['completions'], expected):
        keys(c, {'pc', 'status', 'write_ack_bytes'}, 'completion')
        integer(c['pc'], 0, 65534, 'completion pc')
        integer(c['status'], 0, 255, 'completion status')
        integer(c['write_ack_bytes'], 0, 1 << 56, 'actual write bytes')
        need(c['pc'] == e['pc'] and c['status'] == 0 and c['write_ack_bytes'] == e['write_ack_bytes'], 'completion order/status/ACK mismatch')
    need(isinstance(receipt['exports'], list), 'exports must be a list')
    exports = {}
    for x in receipt['exports']:
        keys(x, {'id', 'file', 'sha256', 'dtype', 'shape', 'generation', 'producer_pc'}, 'export')
        need(isinstance(x['id'], str) and x['id'] in tensors and x['id'] not in exports, 'missing/extra/duplicate export ID')
        t = tensors[x['id']]
        hash_text(x['sha256'], 64, 'actual tensor')
        for field in ('dtype', 'shape', 'generation', 'producer_pc'):
            need(type(x[field]) is type(t[field]) and x[field] == t[field], 'export metadata drift: ' + field)
        tensor_bytes(x)
        if x['generation'] is not None:
            integer(x['generation'], 1, (1 << 64) - 1, 'actual state generation')
        integer(x['producer_pc'], 0, 65534, 'actual producer')
        exports[x['id']] = x
    need(set(exports) == set(tensors), 'missing exports including state')
    # No alias via path spelling, symlink or hardlink, even across different IDs.
    actual_paths = {n: safe_file(root, x['file']) for n, x in exports.items()}
    ref_paths = {n: safe_file(root, t['reference']) for n, t in tensors.items()}
    def inode(p: Path) -> tuple[int, int]:
        st = p.stat(); return st.st_dev, st.st_ino
    ai = [inode(p) for p in actual_paths.values()]
    ri = {inode(p) for p in ref_paths.values()}
    need(len(ai) == len(set(ai)) and not set(ai) & ri, 'export file alias')
    results = {}
    for name, t in tensors.items():
        result = compare_files(actual_paths[name], ref_paths[name], t['dtype'], tensor_bytes(t))
        need(result['reference_sha256'] == t['reference_sha256'], 'reference bytes changed')
        need(result['actual_sha256'] == exports[name]['sha256'], 'actual bytes/hash mismatch')
        need(result['different_elements'] == 0, f'numerical mismatch: {name} first={result["first_difference"]}')
        results[name] = result
    need(sha_file(spec_path) == before, 'manifest changed during verification')
    return {'status': 'PASS_FULL_EXPORT_CONTRACT', 'manifest_sha256': before,
            'tensor_count': sum(t['role'] == 'tensor' for t in tensors.values()),
            'state_count': sum(t['role'] == 'state' for t in tensors.values()),
            'compared_elements': sum(x['elements'] for x in results.values()), 'results': results,
            'hardware_execution_verified': False, 'official_model_accepted': False,
            'scope': 'Full dense exact exports and receipt consistency only; producer attestation is not proof of RTL execution. C02 approximate metrics are not implemented.'}
