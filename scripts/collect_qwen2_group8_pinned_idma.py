#!/usr/bin/env python3
"""Collect actual projection-fragment counters, never full-model throughput."""
import hashlib
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--projection',type=int,choices=(0,1,2),default=0)
args=parser.parse_args()
LOG = ROOT/f'work/results/qwen2_group8_pinned_idma/tb_p{args.projection}.log'
text = LOG.read_text()
pattern = (r'GROUP8_PINNED_IDMA_NUMERICAL_PASS projection=(\d+) batches=(\d+) checked_bf16=(\d+) '
           r'flat_requests=(\d+) wall_cycles=(\d+) useful_macs=(\d+) read_bytes=(\d+) '
           r'write_bytes=(\d+) read_throttle=(\d+) write_throttle=(\d+) no_intermediate_injection=1 distinct_token_rows=1')
matches = re.findall(pattern, text)
assert len(matches) == 1 and 'Fatal:' not in text and 'Error:' not in text
projection, batches, checked, flat, cycles, macs, read, write, rstall, wstall = map(int, matches[0])
assert projection == args.projection
kind = ('q','k','v')[projection]
columns = 1536 if projection == 0 else 256
tiles = columns//32; groups = (tiles+7)//8
weight_flats = tiles*96 if tiles<=8 else groups*1536
assert 1 <= batches <= 2 and cycles > 0
assert checked == 16*columns*batches and flat == weight_flats+(groups*48+tiles*16)*batches
assert macs == 16*batches*columns*1536 and macs <= 512*cycles
assert read == 1536*columns*2+groups*49152*batches and write == 32*columns*batches
row_manifest_paths = ['work/results/qwen2_canonical_tile16_vectors/result.json']
if batches == 2:
    row_manifest_paths.append('work/results/qwen2_true_rows16_31/result.json')
row_manifests = [json.loads((ROOT/p).read_text()) for p in row_manifest_paths]
for index, manifest in enumerate(row_manifests):
    assert manifest['token_start'] == index*16 and manifest['rows'] == 16
    assert manifest['revision'] == 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
    for name, sha in manifest['files'].items():
        assert hashlib.sha256((ROOT/row_manifest_paths[index]).parent.joinpath(name).read_bytes()).hexdigest() == sha
if batches == 2:
    assert row_manifests[0]['token_slice_sha256'] != row_manifests[1]['token_slice_sha256']
sources = [
    'scripts/generate_qwen2_canonical_tile16_vectors.py',
    'scripts/generate_qwen2_canonical_q_tile16_all.py',
    'scripts/generate_l5_q128_qkv_batch_vectors.py',
    'tb/tb_qwen2_group8_pinned_idma.sv',
    'rtl/integration/qwen2_projection_q1024_group8_controller.sv',
    'rtl/integration/qwen2_shared_l2_matrix_tile16_payload.sv',
    'rtl/integration/qwen2_matrix_command_endpoint.sv',
    'rtl/matrix/candidates/rev8b_b/bf16_outer_product_context_array_rev8b_b_candidate.sv',
    'work/generated/l5_all_primitives/HeteroAllPrimitives.sv',
    'rtl/integration/bf16_tile_transpose_stager.sv',
    'rtl/integration/qwen2_norm_tile16_loader.sv',
    'rtl/integration/idma_backend_rw_axi_flat_wrap.sv',
    'rtl/integration/qwen2_tile_idma_expand.sv',
    'rtl/integration/qwen2_axi_shared_l2_bridge.sv',
    'rtl/fabric/shared_l2_fabric.sv',
    'tb/models/axi_ddr_100_40_800mhz.sv',
    'tb/models/ddr_beat_credit.sv',
]
golden_files = [f'work/results/qwen2_canonical_q_tile16_all/{kind}_weight_ddr_beats.memh',
                f'work/results/qwen2_canonical_q_tile16_all/{kind}_expected_token_major.memh']
if batches == 2:
    golden_files.append(f'work/results/qwen2_true_rows16_31_projection/{kind}_expected_token_major.memh')
result = dict(
    status='PASS_JOINT_PACKED_PROJECTION_FRAGMENT', clock_hz=800000000,
    projection=kind.upper(), runtime_batches=batches, rows=16*batches, columns=columns, depth=1536,
    golden_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in golden_files},
    token_start=0, repeated_input_fixture=False,
    row_manifest_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in row_manifest_paths},
    checked_bf16_outputs=checked, flat_idma_requests=flat,
    wall_cycles=cycles, useful_macs=macs,
    useful_mac_utilization=macs/(512*cycles),
    converted_fragment_latency_seconds=cycles/800000000,
    ddr_read_bytes=read, ddr_write_bytes=write,
    ddr_read_throttle_cycles=rstall, ddr_write_throttle_cycles=wstall,
    full_model_q1024_tokens_per_second=None,
    command='MIN_AVAILABLE_KIB=10485760 bash scripts/run_memory_capped.sh timeout 600 bash scripts/run_qwen2_group8_pinned_idma_vcs.sh',
    idma_commit='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d',
    source_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
    log_sha256=hashlib.sha256(LOG.read_bytes()).hexdigest(),
    nonclaims=[
        'Projection input is canonical layer0 norm; RMSNorm is outside this ROI',
        'True token rows0_31 but only a layer0 projection, not a complete model execution',
        'No attention, MLP, other layers or complete q1024',
        'Do not compare against first9 rows16 as a matched speedup baseline',
        '100/40GBps bandwidth ceiling, not a DRAM bank/refresh/latency model',
        'Current modified RTL DC/PPA remains open',
    ])
filename = 'Q1024_GROUP8_JOINT_PINNED_IDMA_RESULT.json' if projection==0 else f'Q1024_GROUP8_JOINT_PINNED_IDMA_{kind.upper()}_RESULT.json'
(ROOT/'reports/execution'/filename).write_text(
    json.dumps(result, indent=2, sort_keys=True)+'\n')
print(json.dumps({k: result[k] for k in ('status','wall_cycles','useful_mac_utilization')}))
