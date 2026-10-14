#!/usr/bin/env python3
"""Cold, local-only preparation of pinned actual H2048 full-chain RTL replay.

This script imports no model, evaluates no floating-point recipe, and never runs
RTL. Its only DUT stimuli are original BF16 input and BF16 checkpoint weight.
Every FP32 observation (including inverse) is written under expected/ for host
assertions only. The input summary SHA must be supplied from a pre-existing
external pin; this script has no mode that learns or refreshes that trust anchor.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

WIDTH = 2048
LANES = 16
ROW_BYTES = WIDTH * 2
TERMINALS = ('input_norm', 'qkv_columns_0', 'conv4_silu', 'a', 'b', 'ab_pack',
             'prep', 'z', 'chunk', 'gated_norm', 'output_projection',
             'attention_residual', 'post_attention_norm')
OBSERVATIONS = set(TERMINALS) | {'conv_history_staging', 'chunk_state_staging', 'chunk_scratch_staging'}
SCALAR_NODES = ('sum', 'mean', 'mean_eps', 'root', 'inverse')
VECTOR_NODES = ('squares', 'scaled', 'gamma', 'weighted', 'output')
REQUIRED_OWNER_SOURCES = (
    'HEAD:chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnRmsNormOwner.scala',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BlockFloat.scala',
    'candidates/qwen35_35b_rms/owner.py',
    'candidates/qwen35_gdn_prefill/rms_owner.py',
)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None,
            label + ': explicit lowercase SHA256 required')
    return value


def within(root, path):
    path = Path(path)
    path = path if path.is_absolute() else root / path
    path = path.resolve(strict=True)
    require(path.is_relative_to(root), 'source outside checkout: ' + str(path))
    require(path.is_file(), 'source must be a regular file: ' + str(path))
    return path


def checked(root, record, expected_bytes=None):
    require(type(record.get('bytes')) is int and record['bytes'] >= 0, 'record bytes')
    if expected_bytes is not None:
        require(record['bytes'] == expected_bytes, 'record shape: ' + record['path'])
    digest = pin(record.get('sha256'), 'record ' + str(record.get('path')))
    path = within(root, record['path'])
    raw = path.read_bytes()
    require(len(raw) == record['bytes'], 'record byte count: ' + str(path))
    require(sha(raw) == digest, 'record SHA256: ' + str(path))
    return raw


def json_object(raw):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, 'duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=unique)


def git_blob(root, path):
    require(not path.startswith('/') and '..' not in Path(path).parts, 'git source path')
    return subprocess.run(['git', '-C', str(root), 'show', 'HEAD:' + path],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def source_records(root, mapping):
    require(isinstance(mapping, dict) and mapping, 'nonempty producer source pins required')
    records = {}
    for path, digest in mapping.items():
        pin(digest, 'producer ' + path)
        local = path.removeprefix('HEAD:')
        current = within(root, local).read_bytes()
        require(sha(current) == digest, 'current producer source SHA256: ' + path)
        if path.startswith('HEAD:'):
            require(sha(git_blob(root, local)) == digest, 'committed producer source SHA256: ' + path)
        records[path] = {'bytes': len(current), 'sha256': digest,
                         'working_tree_verified': True,
                         'git_head_verified': path.startswith('HEAD:')}
    return records


def require_fresh_ignored(root, out):
    # lexists also catches a dangling symlink; resolve cannot silently reuse it.
    require(not os.path.lexists(out), 'fresh output directory required')
    out = Path(out).absolute()
    require(out.parent.resolve(strict=True) == root / 'work',
            'output must be a fresh direct child of checkout/work')
    check = subprocess.run(['git', '-C', str(root), 'check-ignore', '--quiet', '--', str(out)],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(check.returncode == 0, 'output must already be Git-ignored')
    return out


def expand_bf16(raw):
    return b''.join(struct.pack('<I', x[0] << 16) for x in struct.iter_unpack('<H', raw))


def prepare(*, root, summary, summary_sha256, out, tokens, row_start=0):
    root = Path(root).resolve(strict=True)
    out = require_fresh_ignored(root, out)
    summary_path = within(root, summary)
    digest = pin(summary_sha256, 'summary pin')
    summary_raw = summary_path.read_bytes()
    require(sha(summary_raw) == digest, 'summary SHA256 differs from supplied external pin')
    s = json_object(summary_raw)
    source_tokens = s['tokens']
    require(type(source_tokens) is int and source_tokens in (16, 128), 'source M16/M128 required')
    require(type(tokens) is int and tokens in (1, 16, 128), 'replay M1/M16/M128 required')
    require(type(row_start) is int and 0 <= row_start < source_tokens, 'row_start range')
    require(tokens == 1 or (tokens == source_tokens and row_start == 0),
            'M16/M128 must replay the entire matching producer; only M1 may slice a row')
    require(row_start + tokens <= source_tokens, 'row slice exceeds original producer')
    require(s['sources_unchanged'] is True and s['source_sha256'] == s['source_sha256_after'] and
            s['native_artifacts_unchanged'] is True, 'sealed producer source/native identity')
    sources = source_records(root, s['source_sha256'])
    require('candidates/qwen35_35b_prefill/run_prefix.py' in sources,
            'actual prefix producer implementation identity required')
    for rec in s['native_artifact_records']:
        checked(root, rec)
    require(bool(s['native_artifact_records']), 'native artifact closure required')
    arithmetic_sources = source_records(root, s['arithmetic_source_sha256'])
    execution = s['execution']
    require(execution['tokens'] == source_tokens, 'execution/source token identity')
    terms = execution['terminals']
    require([v['stage'] for v in terms] == list(TERMINALS) and
            all(v['status'] is None for v in terms), '13 successful ordered actual terminals')
    require(execution['same_rms_owner_and_banks_reused'] is True and
            execution['postnorm_matrix_vector_unchanged'] is True,
            'actual owner/bank and unchanged unrelated resources')
    observations = s['observations']
    obs = {v['stage']: v for v in observations}
    require(len(observations) == len(obs) == 16 and set(obs) == OBSERVATIONS,
            'complete unique actual prefix observations')
    src = obs['attention_residual']
    dst = obs['post_attention_norm']
    input_raw = checked(root, src['output'], source_tokens * ROW_BYTES)
    bf16_output = checked(root, dst['output'], source_tokens * ROW_BYTES)
    weight_fp32_record = s['postnorm_reference_records']['weight_fp32']
    weight_fp32 = checked(root, weight_fp32_record, WIDTH * 4)
    weight_words = [v[0] for v in struct.iter_unpack('<I', weight_fp32)]
    require(all(v & 0xffff == 0 for v in weight_words), 'weights must be exact BF16 expansion')
    weights_raw = struct.pack('<' + 'H' * WIDTH, *(v >> 16 for v in weight_words))
    weight_sha = pin(execution['postnorm_weight_sha256'], 'checkpoint weight pin')
    require(sha(weights_raw) == weight_sha, 'original checkpoint BF16 weight identity')
    for item in (src, dst):
        report = item['owner']
        require(report['complete'] is True and report['output_published'] is True and
                report['status'] is None and report['output_sha256'] == item['output']['sha256'],
                'actual completed producer boundary: ' + item['stage'])
    require(dst['owner']['input_sha256'] == [src['output']['sha256'], weight_sha],
            'postnorm consumed these exact residual and checkpoint-weight bytes')
    stages = [v for v in execution['stages'] if v['stage'] == 'post_attention_norm']
    require(len(stages) == 1 and stages[0]['report'] == dst['owner'],
            'postnorm stage and observation report identity')
    owner = dst['owner']['owner']
    require(owner['scope'] == 'PACKED_BF16_H2048_RMS_SOFTWARE_OWNER' and
            owner['shared_scalar_service_count'] == 1, 'actual H2048 Scalar owner identity')
    require([owner[k] for k in ('retained_bf16_row_capacity', 'retained_bf16_weight_capacity',
                               'retained_bf16_output_capacity')] == [1024, 1024, 1024] and
            owner['retained_physical_bank_bytes'] == 6144, 'fixed original three-bank identity')
    identity = owner['identity']
    require(identity['policy'] == 'torch210_cpu_default2048' and
            all(name in identity['source_sha256'] for name in REQUIRED_OWNER_SOURCES),
            'exact H2048 producer policy and original Scalar sources')
    require(identity['implementation_sha256'] ==
            identity['source_sha256']['candidates/qwen35_35b_rms/owner.py'],
            'producer implementation digest identity')
    owner_sources = source_records(root, identity['source_sha256'])
    nodes = {}
    for name in SCALAR_NODES + VECTOR_NODES:
        rec = s['postnorm_actual_nodes'][name]
        require(rec['actual_observed'] is True, 'expected must be actual observed node: ' + name)
        count = source_tokens if name in SCALAR_NODES else source_tokens * WIDTH
        nodes[name] = checked(root, rec['actual'], count * 4)
    rows = owner['row_scalars']
    require(len(rows) == source_tokens and [row['token'] for row in rows] == list(range(source_tokens)),
            'actual row-scalar token sequence')
    for name, field in (('sum', 'sum'), ('mean', 'mean'), ('mean_eps', 'variance'),
                        ('root', 'root'), ('inverse', 'inverse')):
        encoded = b''.join(struct.pack('<I', row[field]) for row in rows)
        require(encoded == nodes[name], 'actual row-scalar/node identity: ' + name)
    require(expand_bf16(bf16_output) == nodes['output'], 'observed FP32-expanded BF16 output identity')
    rounded = b''.join(struct.pack('<H', ((v[0] + 0x7fff + ((v[0] >> 16) & 1)) & 0xffffffff) >> 16)
                       for v in struct.iter_unpack('<I', nodes['weighted']))
    require(rounded == bf16_output, 'observed weighted-to-BF16 RNE byte identity')
    payloads = {
        'stimulus/input.bf16le': (input_raw[row_start * ROW_BYTES:(row_start + tokens) * ROW_BYTES],
                                'bf16le', [tokens, WIDTH], 'DUT_MEMORY_INPUT'),
        'stimulus/weights.bf16le': (weights_raw, 'bf16le', [WIDTH], 'DUT_MEMORY_INPUT'),
        'expected/output.bf16le': (bf16_output[row_start * ROW_BYTES:(row_start + tokens) * ROW_BYTES],
                                 'bf16le', [tokens, WIDTH], 'HOST_ASSERTION_ONLY'),
    }
    for name, raw in nodes.items():
        stride = 4 if name in SCALAR_NODES else WIDTH * 4
        shape = [tokens] if name in SCALAR_NODES else [tokens, WIDTH]
        payloads['expected/' + name + '.fp32le'] = (
            raw[row_start * stride:(row_start + tokens) * stride],
            'fp32le', shape, 'HOST_ASSERTION_ONLY')
    original_records = {
        'input': src['output'], 'weight_fp32_transport': weight_fp32_record,
        'output_bf16': dst['output'],
        'nodes': {name: s['postnorm_actual_nodes'][name]['actual'] for name in nodes},
    }
    manifest = {
        'schema_version': 1,
        'scope': 'LOCAL_FROZEN_ACTUAL_H2048_FULL_CHAIN_REPLAY_FIXTURE_ONLY',
        'tokens': tokens, 'source_tokens': source_tokens, 'source_row_start': row_start,
        'width': WIDTH, 'lanes': LANES,
        'summary': {'path': str(summary_path), 'bytes': len(summary_raw), 'sha256': digest,
                    'trust': 'MANDATORY_EXTERNALLY_SUPPLIED_PREEXISTING_PIN'},
        'producer': {'execution_status': execution['status'], 'summary_status': s['status'],
                     'implementation_identity': identity, 'owner_sources_verified': owner_sources,
                     'prefix_sources_verified': sources, 'arithmetic_sources_verified': arithmetic_sources,
                     'native_artifact_records_verified': s['native_artifact_records'],
                     'original_records_verified': original_records,
                     'checkpoint_bf16_weight_sha256': weight_sha,
                     'actual_postnorm_input_sha256': dst['owner']['input_sha256'],
                     'actual_postnorm_output_sha256': dst['output']['sha256'],
                     'original_scope': owner['scope'],
                     'original_reduction_policy': s['reduction_policy']},
        'allowed_dut_input_files': ['stimulus/input.bf16le', 'stimulus/weights.bf16le'],
        'assertion_only_files': sorted(name for name in payloads if name.startswith('expected/')),
        'runner_contract': {
            'arithmetic': 'Unmodified real BlockScalarFloat and ElementwiseRegisterLoan compute all arithmetic',
            'memory': 'Serve only allowlisted BF16 input/weight reads; ACK accepted DUT writes; record actual outputs',
            'inverse': 'DUT computes sum, mean, mean_eps, sqrt and reciprocal; never load expected/inverse into DUT',
            'assertions': 'Compare actual Scalar boundaries, each real 16-lane loan result, and every ACKed BF16 write',
            'counts_are_shape_expectations_not_observations': True,
            'expected_scalar_requests': tokens * 4268,
            'expected_loan_requests': tokens * 128,
            'expected_memory_reads': tokens * 192,
            'expected_memory_writes': tokens * 64,
            'expected_read_bytes': tokens * ROW_BYTES * 3,
            'expected_acknowledged_write_bytes': tokens * ROW_BYTES,
            'row_policy': 'M1 is one unchanged row from the frozen M16/M128 producer, not a newly executed original M1 model',
            'stall_and_failure_checks': 'Preserve existing held request/result, bad-tag, error, abort, drain, lock and reset checks',
        },
        'expected_source': 'Original actual owner observations; copied/sliced, never recomputed floating-point recipe',
        'preparer': {'path': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__).read_bytes()),
                     'identity_only_not_input_trust_anchor': True},
        'files': {},
        'rtl_executed': False, 'model_rerun': False, 'full_block': False,
        'native_acceptance': False, 'published': False,
    }
    # All input validation precedes the exclusive output reservation. No existing
    # directory or file can be overwritten, including a competing writer's path.
    out.mkdir(mode=0o700)
    (out / 'stimulus').mkdir(mode=0o700)
    (out / 'expected').mkdir(mode=0o700)
    for name, (raw, dtype, shape, role) in payloads.items():
        with (out / name).open('xb') as handle:
            handle.write(raw)
        require((out / name).read_bytes() == raw, 'output verification: ' + name)
        manifest['files'][name] = {'bytes': len(raw), 'sha256': sha(raw), 'dtype': dtype,
                                   'shape': shape, 'role': role}
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    with (out / 'manifest.json').open('xb') as handle:
        handle.write(manifest_raw)
    require((out / 'manifest.json').read_bytes() == manifest_raw, 'manifest write verification')
    return {'tokens': tokens, 'source_tokens': source_tokens, 'source_row_start': row_start,
            'manifest': str(out / 'manifest.json'), 'manifest_sha256': sha(manifest_raw),
            'producer_summary_sha256': digest, 'rtl_executed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--summary-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tokens', type=int, choices=(1, 16, 128), required=True)
    parser.add_argument('--row-start', type=int, default=0)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(**vars(args)), sort_keys=True))


if __name__ == '__main__':
    main()
