#!/usr/bin/env python3
"""Fresh all-Q8/K2 owner gate on frozen cold/carried two-token windows.

Runs the real unchanged512-lane arithmetic and true1.5MiB SharedL2. No intermediate
native projection is injected. Source-native failures are saved separately from
bit-exact RTL/oracle outcomes, and are never hidden by successful hardware replay.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from heteronpu.model_geometry import require
import run_matrix_norm_rope_candidate as legacy

CONTRACT = 'config/upstream/qwen3_5_0p8b/matrix_norm_rope_tensor_contract.json'
RTL_SOURCES = tuple(p for p in legacy.RTL_SOURCES if not p.startswith('tb/')) + (
    'tb/tb_qwen35_matrix_norm_rope_tensor.sv',)
EXTRA_SOURCES = legacy.EXTRA_SOURCES + (
    CONTRACT, 'scripts/run_matrix_norm_rope_tensor_candidate.py',
    'scripts/verify_matrix_norm_rope_tensor_trace.py',
    'scripts/materialize_matrix_norm_rope_tensor_vectors.py',
    'src/heteronpu/matrix_norm_rope_tensor_candidate.py')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_log(text, suite):
    markers = re.findall(r'QWEN35_MATRIX_NORM_ROPE_TENSOR_PASS ([^\n]+)', text)
    require(len(markers) == 1, 'missing/duplicate tensor PASS marker')
    require(re.search(r'\bsuite=' + re.escape(suite) + r'\b', markers[0]) is not None,
            'tensor suite mismatch')
    metrics = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', markers[0])}
    expected = {'main': (4, 0, 0, 0), 'all': (7, 30, 2, 2)}
    require(suite in expected, 'unsupported tensor acceptance suite')
    require(tuple(metrics.get(k) for k in ('successes', 'rejects', 'faults', 'resets')) == expected[suite],
            'tensor command inventory mismatch')
    require(metrics.get('capacity_bytes') == 1572864 and metrics.get('source_injection') == 0,
            'tensor capacity/source-injection claim mismatch')
    for key in ('actual_matrix_inputs', 'actual_matrix_outputs', 'explicit_write_acks',
                'read_stall_cycles', 'write_stall_cycles', 'dma_stall_cycles',
                'delayed_ACK_cycles', 'same_cycle_ACKs'):
        require(metrics.get(key, 0) > 0, 'missing real tensor handshake/ACK/stall evidence: ' + key)
    if suite == 'main':
        require(metrics['actual_matrix_inputs'] == 589824 and metrics['actual_matrix_outputs'] == 589824,
                'main all-head accepted Matrix coverage mismatch')
    return metrics


def build(verilator, generated, output, jobs):
    obj = output / 'obj_tensor'
    command = [verilator, '--binary', '--timing', '-Wno-fatal', '-j', str(jobs),
               '--output-split', '12000', '--output-split-cfuncs', '300',
               '--top-module', 'tb_qwen35_matrix_norm_rope_tensor', '--Mdir', obj, '-o', 'tb',
               generated / 'HeteroMatrixNormRoPEHardwarePrimitives.sv']
    command.extend(ROOT / p for p in RTL_SOURCES)
    legacy.run_logged(command, output / 'build.log', timeout=3600)
    return obj / 'tb', [str(x) for x in command]


def run(args):
    from heteronpu.matrix_norm_rope_tensor_candidate import materialize, verify_materialized, MATERIALIZER_SOURCES
    from verify_matrix_norm_rope_tensor_trace import verify_trace
    require(not args.output.exists() or not any(args.output.iterdir()), 'output must be new/empty')
    args.output.mkdir(parents=True, exist_ok=True)
    names = sorted(set(RTL_SOURCES + legacy.EMISSION_SOURCES + EXTRA_SOURCES + tuple(MATERIALIZER_SOURCES)))
    hashes = {p: sha256(ROOT / p) for p in names}
    fixture_dir = args.output / 'vectors'
    started = time.monotonic()
    fixture = materialize(ROOT, args.payload_layer0, args.payload_layer3, args.payload_extra, fixture_dir)
    fixture_hash = fixture['summary_sha256']
    require(fixture_hash == sha256(fixture_dir / 'summary.json'), 'materializer receipt mismatch')
    print('Fresh complete Q8/K2 inputs and integer/C independent oracle materialized; native gate=' +
          str(fixture['native_gate_pass']), flush=True)
    # Do not abort hardware replay merely because the independent native gate
    # failed. Preserve both outcomes in the final summary, then reject the gate.
    env = os.environ.copy()
    env.update(OUT=str(args.generated), PYTHON_BIN=sys.executable)
    if args.verilator:
        env['VERILATOR_BIN'] = str(args.verilator)
    else:
        env.pop('VERILATOR_BIN', None)
    verilator = args.verilator or ROOT / 'work/rope_hardware_oracle/bin/verilator'
    legacy.run_logged(['bash', ROOT / 'scripts/generate_matrix_norm_rope_primitives.sh'],
                      args.output / 'emission.log', env=env)
    verify_hardware = [sys.executable, ROOT / 'chisel/matrix_norm_rope_hardware/manifest.py',
                       'verify', ROOT, args.generated]
    subprocess.run([str(x) for x in verify_hardware], check=True, timeout=90, env=env)
    binary, command = build(verilator, args.generated, args.output, args.jobs)
    print('Actual Matrix512 and tensor-owner Norm/RoPE RTL built', flush=True)
    suites = []
    for source, suite, root in [('baseline', 'all', fixture_dir), ('avx2', 'main', fixture_dir / 'avx2')]:
        prefix = source + '_' + suite
        log, trace = args.output / (prefix + '.log'), args.output / (prefix + '.jsonl')
        t = time.monotonic()
        # Bounded finite test inventory; allow long full-lane simulation to
        # reach its hardware watchdog instead of dropping a still-running run.
        legacy.run_logged([binary, '+vectors=' + str(root), '+suite=' + suite, '+trace=' + str(trace)],
                          log, timeout=28800)
        elapsed = time.monotonic() - t
        metrics = verify_log(log.read_text(), suite)
        check = verify_trace(trace, root, suite=suite)
        suites.append({'source': source, 'suite': suite, 'metrics': metrics,
                       'simulation_tool_wall_seconds': elapsed,
                       'trace_sha256': sha256(trace), 'log_sha256': sha256(log),
                       'independent_trace': check})
        print(source + '/' + suite + ' actual RTL and independent events passed', flush=True)
    verify_materialized(fixture_dir, trusted_summary_sha256=fixture_hash)
    subprocess.run([str(x) for x in verify_hardware], check=True, timeout=90, env=env)
    require(hashes == {p: sha256(ROOT / p) for p in names}, 'source changed during tensor verification')
    hardware = json.loads((args.generated / 'manifest.json').read_text())
    native_pass = fixture['native_gate_pass']
    summary = {
        'schema_version': 1,
        'status': 'PASS_Q8_K2_TOKEN_WINDOW_OWNER_RTL' if native_pass else 'REJECTED_NATIVE_SOURCE_THRESHOLD_RTL_MATCHED',
        'hardware_manifest_sha256': sha256(args.generated / 'manifest.json'),
        'generated_rtl_sha256': hardware['emitted_sha256'], 'tool_versions': hardware['tool_versions'],
        'build_command': command, 'source_sha256': hashes,
        'fixture_summary_sha256': fixture_hash, 'fixture_summary': fixture,
        'native_all_head_selected_tokens_gate_pass': native_pass,
        'native_full_block_gate_pass': fixture['native_full_block_gate_pass'],
        'rtl_suites': suites, 'total_tool_wall_seconds': time.monotonic() - started,
        'production_policy_changed': False, 'matrix_producer_injected': False,
        'all_Q8_K2_selected_token_window_owner_verified': True,
        'all_M128_tokens_rtl_verified': False, 'generic_Command128_fulltensor_complete': False,
        'full_block_numerical_complete': False, 'PPA_measured': False,
        'mac_utilization_measured': False, 'U00_2_complete': False, 'U01_complete': False}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated', type=Path, default=ROOT / 'work/generated/matrix_norm_rope_tensor_candidate')
    parser.add_argument('--verilator', type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--payload-layer0', type=Path, default=ROOT / 'work/qwen35_layer0_payload')
    parser.add_argument('--payload-layer3', type=Path, default=ROOT / 'work/qwen35_layer3_payload')
    parser.add_argument('--payload-extra', type=Path, default=ROOT / 'work/qwen35_prefix_payload')
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    try:
        require(1 <= args.jobs <= 4, 'jobs must be1..4')
        result = run(args)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print('MATRIX_NORM_ROPE_TENSOR_REJECTED: ' + str(error), file=sys.stderr)
        raise SystemExit(3)
    print(result['status'])
    raise SystemExit(0 if result['native_all_head_selected_tokens_gate_pass'] else 3)
