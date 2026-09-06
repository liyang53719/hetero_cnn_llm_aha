#!/usr/bin/env python3
"""Seal independently rechecked Host Command128/iDMA evidence.

This is an evidence auditor, not a simulator. It neither writes DUT memory nor
computes replacement block outputs. Existing generated RTL is never modified.
The original log/dump verifier must already have run successfully. This audit
also decodes all 30 descriptor records, checks exact predecessor addresses and
compares every stored CSV word with the binary dumps.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import re
import struct
from pathlib import Path
from verify_shared_command_gate import host_checks, parse_commands
from verify_production_chain import NAMES, counts, parse_log

BASE = 0x100000000
NULL = 0xffffff

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def header_value(text: str, name: str) -> int:
    matches = re.findall(r'\b' + re.escape(name) + r'\s*=\s*(\d+)(?:ULL)?\b', text)
    require(len(matches) == 1, 'missing/duplicate generated constant ' + name)
    return int(matches[0])

def decode_tables(commands: bytes, descriptors: bytes, *, tokens: int,
                  hidden: int, source_y: int, source_x: int, output: int) -> list[dict]:
    """Decode the frozen v2 prefix and existing SFU_VECTOR policy from bytes."""
    require(len(commands) == 64 and len(descriptors) == 512, 'table length')
    span = ((tokens * hidden * 4 + 63) // 64) * 64
    rows = [int.from_bytes(descriptors[i:i + 16], 'little') for i in range(0, 480, 16)]

    def record(index: int, kind: int, next_index: int) -> int:
        require(0 <= index < 30, 'record index')
        word = rows[index]
        require((word & 0xffffffff) == kind, f'record {index}: type/flags/version')
        require(((word >> 32) & NULL) == next_index, f'record {index}: next index')
        return word >> 56

    def tensor(root: int, address: int, tail: int) -> None:
        p = record(root, 1, root + 1)
        # DDR space=0, FP32 dtype=7, layout=0, rank=2, full 56-bit address.
        expected = (address & ((1 << 48) - 1)) | (7 << 52) | (2 << 60) | ((address >> 48) << 64)
        require(p == expected, f'tensor {root}: address/dtype/space/layout/rank')
        shape = tokens | (hidden << 18) | (1 << 36) | (1 << 54)
        require(record(root + 1, 2, root + 2) == shape, f'tensor {root}: shape')
        require(record(root + 2, 3, tail) == hidden | (1 << 24) | (1 << 48), f'tensor {root}: element strides')

    decoded = []
    for pc in range(3):
        root = 10 * pc
        word = int.from_bytes(commands[16 * pc:16 * pc + 16], 'little')
        expected = 0x330 | (pc << 24) | ((pc + 1) << 40) | (root << 56) | ((root + 4) << 80) | ((root + 7) << 104)
        require(word == expected, f'command {pc}: full 128-bit envelope')
        a = source_y if pc == 0 else output + (pc - 1) * span
        d = output + pc * span
        tensor(root, a, root + 3)
        tensor(root + 4, source_x, NULL)
        tensor(root + 7, d, NULL)
        program = 0x30 | (2 << 16) | (1 << 24) | (7 << 32) | (7 << 36) | (16 << 40)
        require(record(root + 3, 0x20, NULL) == program, f'command {pc}: SFU program')
        decoded.append(dict(pc=pc, opcode=48, engine=3, wait_event=pc,
                            signal_event=pc + 1, a=hex(a), b=hex(source_x),
                            dst=hex(d), shape=[tokens, hidden], dtype='FP32',
                            input_root=root, second_root=root + 4, output_root=root + 7))
    return decoded

def compare_csv(directory: Path, stage_counts: list[int], hidden_values: int) -> int:
    td = directory / 'tensors'
    specs = [(i, name, n, f'phase_{i}_{name}') for i, (name, n) in enumerate(zip(NAMES, stage_counts))]
    specs += [(15 + i, f'host_{i}', hidden_values, f'host_{i}') for i in range(3)]
    checked = 0
    with gzip.open(directory / 'all_shared_elements.csv.gz', 'rt', newline='') as stream:
        reader = csv.reader(stream)
        require(next(reader, None) == ['phase', 'tensor', 'index', 'actual_hex', 'reference_hex'], 'CSV header')
        for phase, name, n, prefix in specs:
            a = (td / f'{prefix}_actual.f32le').read_bytes()
            b = (td / f'{prefix}_reference.f32le').read_bytes()
            require(len(a) == len(b) == n * 4 and a == b, f'{name}: binary parity/length')
            for j, ((av,), (bv,)) in enumerate(zip(struct.iter_unpack('<I', a), struct.iter_unpack('<I', b))):
                require((av & 0x7f800000) != 0x7f800000, f'{name}: nonfinite word')
                row = next(reader, None)
                require(row == [str(phase), name, str(j), f'{av:08x}', f'{bv:08x}'], f'{name}[{j}]: CSV/binary mismatch')
                checked += 1
        require(next(reader, None) is None, 'CSV extra rows')
    return checked

def check_exit(directory: Path, name: str = 'gate.exit') -> None:
    require((directory / name).read_text().strip() == '0', f'{directory.name}: {name}')

def verify_sources(repo: Path, directory: Path) -> None:
    manifest = json.loads((directory / 'sources.sha256.json').read_text())
    require(bool(manifest), 'empty source manifest')
    for path, digest in manifest.items():
        resolved = (repo / path).resolve()
        require(resolved.is_relative_to(repo.resolve()), 'unsafe source path')
        require(sha(resolved) == digest, 'tested source changed: ' + path)

def audit(unit: Path, commands: Path, real: Path, repo: Path, source_base: str) -> dict:
    require(re.fullmatch('[0-9a-f]{40}', source_base) is not None, 'source base SHA')
    for folder in (unit, commands, real):
        check_exit(folder)
        verify_sources(repo, folder)
    for folder in (commands, real):
        check_exit(folder, 'simulation.exit')
    unit_text = re.sub(r'\x1b\[[0-9;]*m', '', (unit / 'chisel_tests.log').read_text())
    require('Total number of tests run: 14' in unit_text and
            'Tests: succeeded 14, failed 0, canceled 0, ignored 0, pending 0' in unit_text,
            'incomplete Chisel frontend unit suite')
    numeric = parse_commands((commands / 'run.log').read_text())
    block = parse_log((real / 'run.log').read_text(), 'real', 16)
    host = host_checks((real / 'run.log').read_text(), 24576, 7)
    admitted = json.loads((real / 'RESULT.json').read_text())
    require(admitted['status'] == 'PASS_BLOCK_TO_HOST_COMMAND_SHARED_IDMA', 'missing combined gate')
    require(admitted['details']['total_values'] == 737280, 'combined output count')
    for path, digest in admitted['files'].items():
        require(sha(real / path) == digest, 'combined artifact changed: ' + path)
    for path, digest in admitted['tensor_sha256'].items():
        require(sha(real / 'tensors' / path) == digest, 'tensor changed: ' + path)
    layout = (real / 'generated/block_layout.h').read_text()
    for key, value in [('H', 1536), ('F', 8960), ('HEADS', 12), ('KVHEADS', 2), ('HD', 128)]:
        require(header_value(layout, key) == value, 'real shape mismatch: ' + key)
    td = real / 'tensors'
    binding = decode_tables((td / 'host_commands.bin').read_bytes(), (td / 'host_descriptors.bin').read_bytes(),
                            tokens=16, hidden=1536, source_y=BASE + header_value(layout, 'OFF_Y'),
                            source_x=BASE + header_value(layout, 'OFF_X'),
                            output=BASE + header_value(layout, 'ARENA_BYTES') + 4096)
    csv_values = compare_csv(real, block['counts'], 24576)
    require(csv_values == 737280, 'full CSV count')
    return dict(schema=1, status='PASS_HOST_COMMAND_SHARED_IDMA_DELIVERY', tested_base_commit=source_base,
                chisel_frontend_tests=14, standalone_command_suite=numeric,
                real_shape=dict(tokens=16, hidden=1536, ffn=8960, heads=12, kv_heads=2, head_dim=128),
                block=block['final'], host=host, decoded_host_commands=binding,
                independently_rechecked_csv_values=csv_values,
                predecessor_actual_sha256=sha(td / 'phase_14_y_actual.f32le'),
                comparison_sha256=sha(real / 'all_shared_elements.csv.gz'),
                sole_idma_total_transfers=int(block['dma']['transfers']) + int(host['idma_transfers']),
                scope=dict(real_block_to_host_command_continuity=True, shared_original_idma=True,
                           original_512_matrix_in_block=True, host_opcode=[48],
                           all_block_stages_host_command_driven=False, official_weights=False,
                           full_network_q1024=False, timing_800mhz_signed_off=False))

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--unit', required=True, type=Path)
    p.add_argument('--commands', required=True, type=Path)
    p.add_argument('--real', required=True, type=Path)
    p.add_argument('--repo', required=True, type=Path)
    p.add_argument('--source-base', required=True)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    require(not a.output.exists(), 'refuse to overwrite prior seal')
    report = audit(a.unit, a.commands, a.real, a.repo, a.source_base)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        raise SystemExit('HOST_DELIVERY_REJECTED: ' + str(error))
