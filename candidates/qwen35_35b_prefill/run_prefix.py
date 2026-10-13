"""Bounded actual typed RMS→selected original Q/K/V columns, no RTL.

References retain the original full [M,2048]×[8192,2048] operator shape.
They are compared only after the new prefix publishes its actual outputs.
Raw tensors remain under ignored work/; Git receives only source and summaries.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

from ..qwen35_35b_payload.packer import load_payload
from ..qwen35_35b_rms import reference as rms_reference
from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library
from ..qwen2_resident_matrix.dense_block_reduce.profile import ReductionProfile
# The existing shared Add adapter imports its Request lazily on first issue.
# Load that exact source closure before freezing the execution identity.
from ..qwen2_resident_matrix.dense_block_reduce import vector_add_model
from . import prefix_driver as p
from ..qwen35_35b_conv import payload as conv_payload, reference as conv_reference, verify as conv_verify

ROOT = Path(__file__).resolve().parents[2]


def record(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=p.sha(raw))


def checked_record(item):
    p.require(type(item) is dict and set(('path', 'bytes', 'sha256')) <= item.keys(), 'file identity fields')
    raw = Path(item['path']).resolve(strict=True).read_bytes()
    p.require(len(raw) == item['bytes'] and p.sha(raw) == item['sha256'], 'frozen file bytes/hash drift')
    return raw


def source_closure():
    paths = {Path(__file__).resolve()}
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        # Torch's synthetic torch.classes advertises relative '_classes.py';
        # it is not a repository source. Real imported files have absolute paths.
        if name and Path(name).is_absolute():
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py' and not path.is_relative_to(ROOT / 'work'):
                paths.add(path)
    return {str(path.relative_to(ROOT)): p.sha(path.read_bytes()) for path in sorted(paths)}


def compare_window(actual, full_reference, tokens, window):
    p.require(len(full_reference) == tokens * 8192 * 2, 'original full-shape reference required')
    expected = np.frombuffer(full_reference, '<u2').reshape(tokens, 8192)[
        :, window.start:window.start + window.columns].copy().tobytes()
    result = compare_finite_bf16(actual, expected)
    segments = {}
    aa = np.frombuffer(actual, '<u2').reshape(tokens, window.columns)
    bb = np.frombuffer(expected, '<u2').reshape(tokens, window.columns)
    for name, begin, end in (('q', 0, 2048), ('k', 2048, 4096), ('v', 4096, 8192)):
        start, stop = max(begin, window.start), min(end, window.start + window.columns)
        if start < stop:
            a, b = start-window.start, stop-window.start
            segment = compare_finite_bf16(aa[:, a:b].copy().tobytes(), bb[:, a:b].copy().tobytes())
            segment['passed'] = segment['max_abs'] <= .03125 and segment['mean_abs'] <= .005
            segments[name] = segment
    whole_pass = result['max_abs'] <= .03125 and result['mean_abs'] <= .005
    return dict(result, passed=whole_pass and all(s['passed'] for s in segments.values()),
                whole_passed=whole_pass, segments=segments,
                thresholds=dict(max_abs=.03125, mean_abs=.005), original_full_shape_sliced=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--reference-report', type=Path, required=True)
    parser.add_argument('--reference-report-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tokens', type=int, choices=(16, 128), default=16)
    parser.add_argument('--full-qkv', action='store_true')
    parser.add_argument('--conv-payload', type=Path)
    parser.add_argument('--conv-manifest-sha256')
    parser.add_argument('--wall-seconds', type=int, default=180)
    args = parser.parse_args(argv)
    p.require(not args.output.exists() and not args.output.is_symlink() and
              args.output.resolve().is_relative_to(ROOT / 'work'), 'fresh ignored work output required')
    p.require(30 <= args.wall_seconds <= 1800, 'bounded explicit software budget 30..1800 seconds')
    reference_record = record(args.reference_report)
    p.require(reference_record['sha256'] == args.reference_report_sha256, 'independently retained reference digest')
    reference = json.loads(checked_record(reference_record))
    p.require((reference['m'], reference['k'], reference['n']) == (args.tokens, 2048, 8192), 'full native geometry')
    p.require(reference['status'] == 'PASS_PAIR_PROFILE_ORIGINAL_GATES', 'reference numerical status')
    manifest, payload = load_payload(ROOT, args.payload, include_qkv=True,
                                     manifest_sha256=args.manifest_sha256)
    hidden = payload['embed_tokens.rows_0_255'][:args.tokens * 4096]
    norm_weight = payload['layers.0.input_layernorm.weight']
    qkv = payload['layers.0.linear_attn.in_proj_qkv.weight']
    p.require((args.conv_payload is None) == (args.conv_manifest_sha256 is None), 'Conv payload and digest together')
    conv_weight = None
    if args.conv_payload is not None:
        p.require(args.full_qkv, 'Conv requires complete QKV')
        _, conv_values = conv_payload.load(args.conv_payload.resolve(), args.conv_manifest_sha256)
        conv_weight = conv_values[conv_payload.LOCAL]
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        rms_reference.runtime_identity()
    p.require(p.sha(qkv) == reference['weight']['sha256'] and
              len(qkv) == reference['weight']['bytes'], 'same native NK weight identity')
    rms_identity = rms_reference.source_identity()
    p.require(reference['official_source']['sha256'] == rms_identity['source_sha256'], 'official source identity')
    pair_source = ROOT / 'candidates/qwen35_35b_projection_reference/reference.c'
    p.require(reference['source_frozen'].get(str(pair_source)) == p.sha(pair_source.read_bytes()),
              'same independent fixed arithmetic source')
    profile = ReductionProfile('diagnostic_35b_onednn371_avx512bf16_two_k1024_pair_high',
                               ((0, 1024), (1024, 2048)), True, p.sha(pair_source.read_bytes()))
    windows = ((p.ColumnWindow(0, 8192),) if args.full_qkv else
               tuple(p.ColumnWindow(i, 160) for i in (0, 2048, 4096)))
    library = p.dense.library_from_environment(ROOT)
    lib = configure_library(ctypes.CDLL(str(library)))
    p.require(lib.td_reset() == 0, 'fresh shared Matrix')
    matrix = p.dense.MatrixService(lib)
    vector = p.Vector16(Path(os.environ['GDN_VECTOR16_LIBRARY']), exception_policy=p.IEEE_POLICY)
    compile_receipt = Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT'])
    native_paths = [pair_source, library, compile_receipt, vector.library,
                    vector.library.with_suffix('.json'),
                    ROOT / 'candidates/qwen35_gdn_prefill/chunk/vector16.cpp']
    native_paths += [ROOT / name for name in json.loads(compile_receipt.read_bytes())['sources_before']]
    conv_preact = np.zeros((args.tokens,8192), dtype='<u2') if conv_weight is not None else None
    conv_seen = set()
    def conv_observe(tag, token, channel, bits):
        p.require((token,channel) not in conv_seen, 'duplicate Conv preactivation observation')
        conv_seen.add((token,channel)); conv_preact[token,channel] = bits
    args.output.mkdir(parents=True)
    started = time.monotonic()
    report = dict(status='RUNNING', tokens=args.tokens, windows=[vars(w) for w in windows],
                  full_qkv=args.full_qkv, conv_requested=conv_weight is not None, full_block=False, rtl_executed=False,
                  conv_manifest_sha256=args.conv_manifest_sha256,
                  reference=reference_record, manifest_sha256=args.manifest_sha256,
                  input_identity=dict(hidden_sha256=p.sha(hidden), norm_weight_sha256=p.sha(norm_weight),
                                      qkv_nk_sha256=p.sha(qkv)),
                  matrix_library=record(library), vector_library=record(os.environ['GDN_VECTOR16_LIBRARY']),
                  matrix_compile_receipt=record(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']),
                  source_sha256=source_closure(), arithmetic_source_sha256={
                      str(pair_source.relative_to(ROOT)): p.sha(pair_source.read_bytes())},
                  native_artifact_records=[record(path) for path in native_paths],
                  observations=[], comparisons={})

    def save():
        report['host_seconds'] = time.monotonic() - started
        (args.output / 'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def observe(stage, details, raw):
        path = args.output / (stage + '.actual.bf16le')
        path.write_bytes(raw)
        report['observations'].append(dict(stage=stage, output=record(path), owner=details))
        save()
        print(json.dumps(dict(stage=stage, host_seconds=time.monotonic()-started,
                              output_sha256=p.sha(raw))), flush=True)

    def timeout(*_):
        raise TimeoutError('bounded typed prefix software budget')

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.wall_seconds)
    save()
    try:
        execution, _ = p.execute_prefix(hidden, norm_weight, qkv, tokens=args.tokens, windows=windows,
            profile=profile, matrix=matrix, vector=vector, deadline=started+args.wall_seconds, observe=observe,
            conv_weights=conv_weight, conv_observe=conv_observe if conv_weight is not None else None)
        report['execution'] = execution
        p.require(execution['status'] == 'PASS_TYPED_PREFIX_EXECUTION_ONLY', 'actual typed prefix failed')
        p.require(execution['actual_rms_output_sha256'] == reference['input']['sha256'], 'actual RMS differs from reference input')
        native = checked_record(reference['official_output'])
        fixed = checked_record(reference['results']['pair_hi_first_two_k1024']['output'])
        expected_stages = ['input_norm'] + ['qkv_columns_' + str(w.start) for w in windows]
        if conv_weight is not None:
            expected_stages += ['conv4_silu', 'conv_history_staging']
        p.require([o['stage'] for o in report['observations']] == expected_stages, 'exact observation inventory')
        p.require(len(execution['terminals']) == len(windows)+1+(conv_weight is not None), 'exact owner terminal count')
        for window, observation in zip(windows, report['observations'][1:1+len(windows)], strict=True):
            actual = checked_record(observation['output'])
            numeric = dict(native=compare_window(actual, native, args.tokens, window),
                           fixed=compare_window(actual, fixed, args.tokens, window))
            report['comparisons'][observation['stage']] = numeric
            p.require(numeric['fixed']['bit_mismatches'] == 0, 'actual Matrix/Vector differs from independent fixed recipe')
            p.require(numeric['native']['passed'], 'original native threshold failed')
        if conv_weight is not None:
            p.require(len(conv_seen) == args.tokens*8192, 'complete actual Conv preactivation coverage')
            qkv_actual = checked_record(report['observations'][1]['output'])
            post_actual = checked_record(report['observations'][2]['output'])
            history_actual = checked_record(report['observations'][3]['output'])
            pre_actual = conv_preact.tobytes()
            pre_path = args.output / 'conv_preact.actual.bf16le'; pre_path.write_bytes(pre_actual)
            report['conv_preact_record'] = record(pre_path)
            fixed_conv, fixed_id = conv_reference.fixed_conv(qkv_actual, conv_weight, args.tokens)
            native_conv, native_id = conv_reference.native_conv(qkv_actual, conv_weight, args.tokens)
            # Also check end-to-end inherited QKV rounding against the frozen official producer.
            end_conv, end_id = conv_reference.native_conv(native, conv_weight, args.tokens)
            actual_conv = dict(conv=pre_actual,silu=post_actual,history=history_actual)
            strict = conv_verify.compare(actual_conv,fixed_conv,native_conv,end_conv)
            report['conv_strict_gates'] = strict
            report['conv_comparisons'] = strict['comparisons']
            report['conv_reference_records'] = conv_verify.save_raw(args.output/'conv_references',
                dict(fixed=fixed_conv,same_input=native_conv,end_to_end=end_conv))
            p.require(strict['passed'], 'original strict Conv gates failed')
            report['conv_references'] = dict(fixed=fixed_id,native=native_id,end_to_end=end_id)
            p.require(execution['conv_history_staging']['published'] is False and
                      execution['conv_history_staging']['generation_advanced'] is False, 'no local block commit')
        report['source_sha256_after'] = source_closure()
        report['sources_unchanged'] = report['source_sha256'] == report['source_sha256_after']
        p.require(report['sources_unchanged'], 'execution source drift')
        for item in report['native_artifact_records']:
            checked_record(item)
        report['native_artifacts_unchanged'] = True
        report['status'] = 'PASS_TYPED_PREFIX_ORIGINAL_NATIVE_GATES'
    except BaseException as error:
        report.update(status='FAILED', error=dict(type=type(error).__name__, message=str(error)))
        if isinstance(error, p.PrefixExecutionError):
            report['execution'] = error.execution_report
            report['interrupted_owner'] = error.snapshot
            partial = args.output / 'interrupted_owner.partial.bf16le'
            partial.write_bytes(error.partial_output)
            report['interrupted_output'] = record(partial)
            if error.partial_history is not None:
                history_path = args.output / 'interrupted_owner.history.bf16le'
                history_path.write_bytes(error.partial_history)
                report['interrupted_history'] = record(history_path)
        save()
        raise
    finally:
        signal.alarm(0)
    save()


if __name__ == '__main__':
    main()
