#!/usr/bin/env python3
"""Native BF16 weight storage for the unchanged ordered-BF16 owner recipe.

Only Dense B tensors change storage dtype. Command bytes, addresses, activation
formats, bias/norm/RoPE parameters, reduction order and output precision stay
unchanged. Unused halves of the old allocations remain guard space, not inputs.
This fixture converter does not claim to load official model weights.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.command import Command128
from heteronpu.descriptor_chain import DescriptorRecord, validate_descriptor_chain


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def pack_words(raw: bytes) -> bytes:
    """FP32 bits -> finite BF16 RNE bits, in little-endian tensor order."""
    require(len(raw) % 4 == 0, 'truncated FP32 weight')
    dst = bytearray(len(raw) // 2)
    for i, (u,) in enumerate(struct.iter_unpack('<I', raw)):
        require((u & 0x7f800000) != 0x7f800000, 'nonfinite FP32 weight')
        b = ((u + 0x7fff + ((u >> 16) & 1)) >> 16) & 0xffff
        require((b & 0x7f80) != 0x7f80, 'BF16 conversion overflows')
        struct.pack_into('<H', dst, 2 * i, b)
    return bytes(dst)


def convert(source: Path, output: Path) -> dict:
    require(source.is_dir() and not source.is_symlink(), 'missing fixture')
    require(not output.exists() and not output.is_symlink(), 'preserve old fixture')
    manifest = json.loads((source / 'manifest.json').read_text())
    require(manifest.get('weight_storage', 'fp32') == 'fp32', 'fixture already converted')
    raw = (source / 'host_descriptors.bin').read_bytes()
    commands = (source / 'host_commands.bin').read_bytes()
    require(len(raw) == (manifest['descriptors'] * 16 + 63) // 64 * 64, 'descriptor length')
    require(len(commands) == (manifest['commands'] * 16 + 63) // 64 * 64, 'command length')
    for name, data in [('host_descriptors.bin', raw), ('host_commands.bin', commands)]:
        require(hashlib.sha256(data).hexdigest() == manifest['table_sha256'][name], 'untrusted table bytes')
    records = {i: DescriptorRecord.unpack(int.from_bytes(raw[16*i:16*i+16], 'little'))
               for i in range(manifest['descriptors'])}
    converted = copy.deepcopy(manifest)
    weights = {}
    edited = set()
    for op in manifest['schedule']:
        cmd = Command128.from_bytes(commands[16*op['pc']:16*op['pc']+16])
        require(cmd.opcode.name == op['opcode'] and [cmd.src0,cmd.src1,cmd.dst] == op['roots'], 'command binding drift')
        if op['opcode'] != 'MATRIX_GEMM':
            continue
        name = op['b']; t = manifest['tensors'][name]
        require(re.fullmatch(r'(?:l[0-9]+_)?w[qkvogud]', name) is not None, 'not a matrix weight')
        require(t['readonly'] and not t['virtual'] and len(t['dims']) == 2, 'weight ownership/shape')
        require(t['dims'][1] % 32 == 0 and t['words'] == t['dims'][0] * t['dims'][1], 'native BF16 row geometry')
        chain = validate_descriptor_chain(cmd.src1, records)
        require(len(chain) == 3, 'weight chain length')
        rec = chain[0][1]; p = rec.payload
        addr = (p & ((1 << 48) - 1)) | ((p >> 64) << 48)
        require(((p >> 52) & 15) == 7 and addr == t['address'] and addr % 64 == 0, 'weight binding')
        require(cmd.src1 not in edited, 'duplicate weight descriptor root')
        edited.add(cmd.src1)
        records[cmd.src1] = DescriptorRecord(rec.record_type, rec.subtype, rec.flags,
                                             rec.next_index, (p & ~(15 << 52)) | (5 << 52))
        converted['tensors'][name]['storage_dtype'] = 5
        converted['tensors'][name]['storage_bytes'] = 2 * t['words']
        weights[name] = dict(address=t['address'], elements=t['words'], bytes=2*t['words'])
    require(len(weights) == len(edited) == 7 * manifest.get('layers', 1), 'incomplete Dense weights')
    db = b''.join(records[i].pack().to_bytes(16, 'little') for i in range(manifest['descriptors']))
    db = db.ljust(len(raw), b'\0')
    for i in range(manifest['commands']):
        c = Command128.from_bytes(commands[16*i:16*i+16])
        for root in (c.src0,c.src1,c.dst):
            if root != 0xffffff:
                validate_descriptor_chain(root, records)
    converted['weight_storage'] = 'bf16'
    converted['weight_contract'] = dict(recipe='BF16_RNE_before_ordered_BF16_FP32_FMA', weights=weights,
        command_bytes_unchanged=True, addresses_unchanged=True, other_tensors_unchanged=True,
        original_descriptor_sha256=hashlib.sha256(raw).hexdigest())
    converted['table_sha256']['host_descriptors.bin'] = hashlib.sha256(db).hexdigest()
    # Every validation precedes creation of the new output. No existing proof
    # directory, weight file, test threshold or simulator state is modified.
    shutil.copytree(source, output)
    (output / 'host_descriptors.bin').write_bytes(db)
    (output / 'manifest.json').write_text(json.dumps(converted, indent=2) + '\n')
    with (output / 'owner_fixture.h').open('a') as h:
        h.write('\n#define OWNER_BF16_WEIGHTS 1\n')
    return converted


if __name__ == '__main__':
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('source', type=Path); a.add_argument('output', type=Path)
    args = a.parse_args()
    try:
        result = convert(args.source.resolve(), args.output.absolute())
        print(json.dumps(result['weight_contract'], indent=2))
    except (ValueError, KeyError, TypeError, OSError) as e:
        raise SystemExit('NATIVE_WEIGHT_FIXTURE_REJECTED: ' + str(e))
