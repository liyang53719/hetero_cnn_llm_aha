#!/usr/bin/env python3
"""Actual opt-in existing SharedL2 consumer, immutable native rotary payloads.

The 192 bypass channels are explicitly synthetic adversarial transport data.
No model is re-executed to manufacture expected values on the current host.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.model_geometry import require
from heteronpu.rope_bf16_l2_candidate import (
    POLICY, DATA_BASE, TRIG_BASE, DST_BASE, admit, tensor_from_pairs,
    adversarial_tail, pack_beat, expected_packets)
from heteronpu.rope_bf16_candidate import pair_trace


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


component = load('run_rope_bf16_candidate')
CONTRACT = 'config/upstream/qwen3_5_0p8b/rope_bf16_l2_candidate_contract.json'
SOURCES = (
    CONTRACT, 'scripts/run_rope_bf16_l2_candidate.py',
    'src/heteronpu/rope_bf16_l2_candidate.py',
    'rtl/integration/rope_bf16_l2_candidate.sv',
    'rtl/integration/qwen2_shared_l2_rope_payload.sv',
    'rtl/integration/qwen2_rope_stage_top.sv',
    'rtl/integration/qwen2_rope_tile16_controller.sv',
    'tb/tb_qwen2_rope_token01_payload.sv',
    'rtl/fabric/shared_l2_fabric.sv', 'rtl/sfu/qwen2_rope_base_coeff_q46.sv',
    'rtl/sfu/fp32_rope_pair.sv', 'rtl/sfu/fp32_to_bf16_rne_candidate.sv',
    'rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',
    'src/heteronpu/rope_bf16_candidate.py', 'tb/tb_rope_bf16_l2_candidate.sv',
)


def record(path):
    return {'file': path.name, 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def make_records():
    component.contract()
    component.frozen.verify_fixtures()
    records, provenance, real_pairs = [], {}, 0
    extra = []
    for name in ('local', 'remote'):
        data, origin = component.frozen.load_corpus(name)
        provenance[name] = origin
        trace = np.array([pair_trace(*(int(w) for w in row)) for row in data['inputs']], dtype=np.uint32)
        require(np.array_equal(trace[:, 20:22], data['native_outputs']), 'frozen native mismatch')
        require(np.array_equal(trace[:, 8:12], data['native_products']), 'frozen products mismatch')
        for start in range(0, len(data['inputs']), 32):
            sl = slice(start, start + 32)
            records.append(make_record(data['inputs'][sl], data['native_outputs'][sl],
                                       trace[sl, 24], len(records), name, start, False))
            real_pairs += 32
        # Adjacent heads in the first token share coefficients. Explicitly
        # retain supplemental replay accounting instead of counting unique data twice.
        for start in range(0, 2048, 64):
            sl = slice(start, start + 64)
            extra.append((data['inputs'][sl], data['native_outputs'][sl], trace[sl, 24], name, start))
    for inputs, native, flags, name, start in extra:
        records.append(make_record(inputs, native, flags, len(records), name, start, True))
    require(real_pairs == 163840 and len(records) == 5184, 'incomplete frozen replay')
    return records, provenance


def make_record(inputs, native, flags, index, corpus, start, supplemental):
    heads = len(inputs) // 32
    source, trig, expected = tensor_from_pairs(inputs, native, adversarial_tail(0xB160000 + index, heads))
    offset = (index % 32) * 2
    overlap = index % 37 == 0
    destination = (DATA_BASE if overlap else DST_BASE) + offset
    counts = admit(heads=heads, head_dim=256, rotary_dim=64, data_beats=8 * heads,
                   policy=POLICY, source=DATA_BASE, trig=TRIG_BASE, destination=destination)
    return {'source': source, 'trig': trig, 'expected': expected,
            'heads': heads, 'offset': offset, 'overlap': overlap,
            'destination': destination, 'flags': int(np.bitwise_or.reduce(flags)),
            'counts': counts, 'corpus': corpus, 'first_pair': start,
            'supplemental_replay': supplemental}


def write_vectors(path, records):
    lines = []
    for r in records:
        words = [0] * 35
        words[0] = r['heads'] | (r['offset'] << 8) | (r['flags'] << 16) | (int(r['overlap']) << 24)
        for index, beat in enumerate(r['source'].reshape(-1, 32)):
            words[1 + index] = pack_beat(beat)
        for index, beat in enumerate(r['trig']):
            words[17 + index] = pack_beat(beat)
        for index, beat in enumerate(r['expected'].reshape(-1, 32)):
            words[19 + index] = pack_beat(beat)
        lines.extend(f'{word:0128x}\n' for word in words)
    path.write_text(''.join(lines))


def verify_store_trace(path, records):
    """Reject missing/extra/reordered data or completion and byte-mask drift."""
    transaction, packet = 0, 0
    values, masks, addresses = [], [], []
    for line in path.read_text().splitlines():
        fields = line.split()
        require(fields and fields[0] in ('W', 'D'), 'malformed store trace')
        require(len(fields) == (5 if fields[0] == 'W' else 6), 'store trace column count')
        require(re.fullmatch(r'-?\d+', fields[1]) is not None, 'bad transaction index')
        index = int(fields[1])
        if index < 0:
            continue  # Explicit auxiliary reset/rejection/legacy tests, scored in RTL.
        require(transaction < len(records) and index == transaction, 'transaction reordered or duplicated')
        r = records[transaction]
        packets = expected_packets(r['expected'], r['destination'])
        if fields[0] == 'W':
            require(all(re.fullmatch(r'[0-9a-fA-F]+', x) for x in fields[2:]), 'malformed hexadecimal store')
            require(len(fields[3]) == 16 and len(fields[4]) == 128, 'store width mismatch')
            actual = tuple(int(x, 16) for x in fields[2:])
            require(packet < len(packets) and actual == packets[packet], 'store address/mask/data mismatch')
            addresses.append(actual[0]); masks.append(actual[1])
            values.append([(actual[2] >> (16 * i)) & 65535 for i in range(32)])
            packet += 1
        else:
            require(all(re.fullmatch(r'\d+', x) for x in fields[2:]), 'malformed completion')
            require(packet == len(packets), 'premature or missing store completion')
            actual = tuple(int(x) for x in fields[2:])
            expected = (r['counts']['reads'], r['counts']['pairs'], r['counts']['writes'], r['flags'])
            require(actual == expected, 'completion counter/flag mismatch')
            transaction += 1
            packet = 0
    require(transaction == len(records) and packet == 0, 'incomplete store trace')
    return {'transactions': transaction, 'physical_write_beats': len(values),
            'BF16_payload_words': sum(r['heads'] * 256 for r in records),
            'masked_bytes': sum(mask.bit_count() for mask in masks),
            'addresses': np.array(addresses, dtype=np.uint32),
            'masks': np.array(masks, dtype=np.uint64),
            'data': np.array(values, dtype=np.uint16)}


def run(args):
    require(not args.output.exists() or not any(args.output.iterdir()), 'output must be fresh or empty')
    args.output.mkdir(parents=True, exist_ok=True)
    hashes = {p: record(ROOT / p)['sha256'] for p in SOURCES}
    records, provenance = make_records()
    write_vectors(args.output / 'vectors.memh', records)
    metadata = [{k: v for k, v in r.items() if k not in ('source', 'trig', 'expected')} for r in records]
    (args.output / 'transactions.json').write_text(json.dumps(metadata, indent=2) + '\n')
    np.savez_compressed(args.output / 'tensors.npz', **{
        f'{i}_{key}': r[key] for i, r in enumerate(records) for key in ('source', 'trig', 'expected')})
    env, verilator = component.old.emission_environment(args.generated, args.verilator)
    with (args.output / 'emission.log').open('w') as log:
        subprocess.run(['bash', str(ROOT / 'scripts/generate_rope_hardware_primitives.sh')],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
    verify = [sys.executable, str(ROOT / 'chisel/rope_hardware_oracle/manifest.py'),
              'verify', str(ROOT), str(args.generated)]
    subprocess.run(verify, check=True, timeout=60)
    sources = [args.generated / 'HeteroRoPEHardwarePrimitives.sv'] + [ROOT / p for p in (
        'rtl/sfu/fp32_to_bf16_rne_candidate.sv', 'rtl/sfu/fp32_rope_pair_bf16_pipe_candidate.sv',
        'rtl/sfu/fp32_rope_pair.sv', 'rtl/sfu/qwen2_rope_base_coeff_q46.sv',
        'rtl/integration/rope_bf16_l2_candidate.sv', 'rtl/integration/qwen2_shared_l2_rope_payload.sv',
        'rtl/fabric/shared_l2_fabric.sv', 'tb/tb_rope_bf16_l2_candidate.sv')]
    runs = []
    for mode in (1, 0):
        label = 'candidate' if mode else 'legacy_default'
        obj = args.output / ('obj_' + label)
        command = component.sim_build(verilator, sources, 'tb_rope_bf16_l2_candidate', obj,
                                      {'COUNT': len(records), 'MODE': mode}, args.output / (label + '_build.log'))
        trace = args.output / (label + '_stores.txt')
        with (args.output / (label + '_run.log')).open('w') as log:
            subprocess.run([str(obj / 'tb'), '+VECTORS=' + str(args.output / 'vectors.memh'),
                            '+OUTPUTS=' + str(trace)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=600)
        logtext = (args.output / (label + '_run.log')).read_text()
        marker = re.findall(r'ROPE_BF16_L2_PASS ([^\n]+)', logtext)
        require(len(marker) == 1, 'missing/duplicate L2 pass marker')
        metrics = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', marker[0])}
        if mode:
            checked = verify_store_trace(trace, records)
            arrays = {k: checked.pop(k) for k in ('addresses', 'masks', 'data')}
            np.savez_compressed(args.output / 'actual_stores.npz', **arrays)
            require(metrics.get('transactions') == len(records), 'incomplete RTL transaction count')
            require(metrics.get('rejects') == 38 and metrics.get('resets') == 4,
                    'missing rejection/reset coverage')
            require(metrics.get('main_pairs') == 167936 and metrics.get('main_tail_bf16') == 1007616,
                    'incomplete pair/tail coverage')
            require(all(metrics.get(k, 0) > 0 for k in ('rd_stalls', 'wr_stalls', 'rsp_stalls')),
                    'missing backpressure coverage')
            require('offsets=ffffffff' in marker[0] and metrics.get('actual_shared_l2') == 1 and
                    metrics.get('no_memory_pokes') == 1, 'fabric/offset coverage missing')
        else:
            require(metrics.get('mode') == 0 and metrics.get('transactions') == 2,
                    'production-default smoke incomplete')
            checked = {'production_default_identity': True}
        runs.append({'mode': mode, 'command': command, 'metrics': metrics, 'independent_packet_check': checked})
    subprocess.run(verify, check=True, timeout=60)
    require(hashes == {p: record(ROOT / p)['sha256'] for p in SOURCES}, 'source changed during execution')
    component.contract(); component.frozen.verify_fixtures()
    report = {'schema_version': 1, 'status': 'PASS_EXPERIMENTAL_BF16_ROPE_SHARED_L2_HEAD_TRANSPORT',
              'unique_real_pairs': 163840, 'unique_real_native_outputs': 327680,
              'supplemental_real_pair_replays': 4096, 'transactions': len(records),
              'real_rotary_fixture_provenance': provenance,
              'unrotated_tail_source': 'synthetic adversarial raw BF16 transport fixtures, 192 words per head',
              'native_expectations_regenerated': False, 'production_policy_changed': False,
              'actual_shared_l2_fabric_tested': True, 'BF16_packing_and_byte_masks_tested': True,
              'completion_boundary': 'last accepted SharedL2 write, not DDR acknowledgement',
              'reset_boundary': 'coordinated consumer+fabric reset; previously accepted stores remain',
              'generic_SFU_owner_integrated': False, 'Command128_integrated': False,
              'position_coefficient_generation_tested': False, 'Q8_whole_tensor_command_tested': False,
              'full_block_numerical_complete': False, 'PPA_measured': False,
              'mac_utilization_measured': False, 'U00_2_complete': False, 'U01_complete': False,
              'source_sha256': hashes, 'fixture_sha256': component.frozen.FIXTURE_PINS,
              'rtl_runs': runs, 'emission_manifest': json.loads((args.generated / 'manifest.json').read_text())}
    report['artifacts'] = {p.name: record(p) for p in sorted(args.output.iterdir()) if p.is_file()}
    (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated', type=Path, default=ROOT / 'work/generated/rope_bf16_l2_candidate')
    parser.add_argument('--verilator', type=Path)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    try:
        report = run(args)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print('ROPE_BF16_L2_REJECTED: ' + str(error), file=sys.stderr)
        raise SystemExit(3)
    print(report['status'])
