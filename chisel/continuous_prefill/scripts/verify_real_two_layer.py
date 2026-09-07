#!/usr/bin/env python3
"""Independently seal the fixed real16, two-layer original Host command graph.

Read-only to all DUT evidence. No oracle tensor is supplied to the simulator.
This is synthetic-weight numerical/transport evidence, not official quality,
full-model q1024 throughput, or 800 MHz physical timing signoff.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from audit_owner_block_abi import audit
from verify_host_block_gate import verify, tagged


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fixed_contract(m: dict) -> None:
    expected = {'H': 1536, 'F': 8960, 'HEADS': 12, 'KVHEADS': 2, 'HD': 128}
    require(all(type(m['shape'][k]) is int and m['shape'][k] == v for k, v in expected.items()), 'not real Qwen2 dimensions')
    require(all(type(m[k]) is int and m[k] == v for k, v in {'tokens': 16, 'layers': 2, 'commands': 42, 'descriptors': 430}.items()), 'not fixed real16 two-layer graph')
    require(m.get('layer_weight_salts') == [0, 17], 'distinct deterministic layer weights required')
    require([x['pc'] for x in m['schedule']] == list(range(42)), 'incomplete command graph')
    require([x['layer'] for x in m['schedule']] == [0] * 21 + [1] * 21, 'wrong layer ownership')
    tensors = m['tensors']
    x1, y0 = tensors['l1_x'], tensors['l0_y']
    require(x1['address'] == y0['address'] and x1['words'] == y0['words'] == 16 * 1536, 'layer one must directly alias actual layer zero Y')
    require(x1['readonly'] is False and 'l1_x' not in m['allocations'], 'layer input must not be Host-initialized')
    require(tensors['l1_y']['address'] != y0['address'], 'retain first layer output for independent verification')
    for name in ('wq', 'wk', 'wv', 'wo', 'wg', 'wu', 'wd'):
        a, b = tensors['l0_' + name], tensors['l1_' + name]
        require(a['readonly'] is True and b['readonly'] is True, 'weight write permission')
        require(a['address'] + a['words'] * 4 <= b['address'] or b['address'] + b['words'] * 4 <= a['address'], 'layer weights overlap')


def compare_all(out: Path, m: dict) -> int:
    total = 0
    with gzip.open(out / 'all_owner_elements.csv.gz', 'rt', newline='') as stream:
        rows = csv.reader(stream)
        require(next(rows, None) == ['pc', 'tensor', 'index', 'actual_hex', 'reference_hex'], 'CSV header')
        for op in m['schedule']:
            for name in op['outputs']:
                a = (out / 'tensors' / (name + '_actual.f32le')).read_bytes()
                b = (out / 'tensors' / (name + '_reference.f32le')).read_bytes()
                require(len(a) == len(b) == m['tensors'][name]['words'] * 4, 'tensor length: ' + name)
                for i, ((x,), (y,)) in enumerate(zip(struct.iter_unpack('<I', a), struct.iter_unpack('<I', b))):
                    require(x == y and x & 0x7f800000 != 0x7f800000, 'nonfinite or unequal output: ' + name)
                    require(next(rows, None) == [str(op['pc']), name, str(i), f'{x:08x}', f'{y:08x}'], 'CSV does not describe actual outputs')
                    total += 1
        require(next(rows, None) is None, 'extra CSV rows')
    require(total == 1409024, 'incomplete two-layer output coverage')
    return total


def check(repo: Path, out: Path) -> dict:
    require((out / 'gate.exit').read_text().strip() == '0', 'numerical gate not complete')
    m = json.loads((out / 'fixture/manifest.json').read_text())
    fixed_contract(m)
    result = verify(out, False)
    abi = audit(out)
    total = compare_all(out, m)
    require(result['checked_fp32'] == abi['checked_fp32'] == total, 'inconsistent numeric/ABI coverage')
    require(len(abi['commands']) == 42 and abi['descriptor_records'] == 430, 'ABI coverage')
    log = (out / 'run.log').read_text()
    weights = tagged(log, 'LAYER_WEIGHT_ID')
    require([int(x['layer']) for x in weights] == [0, 1], 'missing weight identity')
    require([int(x['salt']) for x in weights] == [0, 17], 'wrong weight stimulus')
    require(all(weights[0][n] != weights[1][n] for n in ('wq', 'wg', 'wd')), 'identical layer matrices')
    y0 = out / 'tensors/l0_y_actual.f32le'
    y1 = out / 'tensors/l1_y_actual.f32le'
    require(y0.read_bytes() != y1.read_bytes(), 'second layer did not transform hidden state')
    identities = json.loads((out / 'sources.sha256.json').read_text())
    require(len(identities) > 100, 'incomplete source manifest')
    for name, sha in identities.items():
        p = Path(name)
        require(not p.is_absolute() and '..' not in p.parts, 'unsafe source path')
        require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{64}', sha) is not None, 'invalid source hash')
        require(digest(repo / p) == sha, 'tested source changed: ' + name)
    commit = (out / 'source_base_commit.txt').read_text().strip()
    require(re.fullmatch('[0-9a-f]{40}', commit) is not None, 'source identity')
    return {'schema': 1, 'status': 'PASS_REAL16_TWO_LAYER_HOST_NUMERICAL',
            'source_commit': commit, 'tokens': 16, 'layers': 2, 'hidden': 1536, 'ffn': 8960,
            'commands': 42, 'owner_jobs': 38, 'descriptor_records': 430,
            'checked_fp32': total, 'bit_differences': 0, 'counters': result['counters'],
            'layer_weight_identities': weights,
            'layer0_y_sha256': digest(y0), 'layer1_y_sha256': digest(y1),
            'log_sha256': digest(out / 'run.log'), 'csv_sha256': digest(out / 'all_owner_elements.csv.gz'),
            'generated_rtl_sha256': digest(out / 'generated/HostBlockTop.sv'),
            'source_files_rechecked': len(identities),
            'scope': {'original_host_command_graph': True, 'retained_matrix': True,
                      'pinned_idma': True, 'one_launch': True, 'block_launch': False,
                      'host_layer_copy': False, 'synthetic_weights': True,
                      'official_weights': False, 'full_network_q1024': False, 'dc': False}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.output:
            require(not args.output.exists(), 'never overwrite evidence')
        report = check(args.repo.resolve(), args.evidence.resolve())
        text = json.dumps(report, indent=2) + '\n'
        if args.output:
            with args.output.open('x') as stream:
                stream.write(text)
        print(text, end='')
    except (ValueError, OSError, KeyError, TypeError) as error:
        raise SystemExit('REAL_TWO_LAYER_REJECTED: ' + str(error))
