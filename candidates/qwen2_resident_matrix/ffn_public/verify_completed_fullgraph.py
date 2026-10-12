"""Recompare a completed public21 capture; never execute or overwrite that run.

Only the specific post-terminal oracle timeout can be recovered. Complete old
references must match the source, binary, shape and input pinned before launch.
The original failed receipt stays failed; this emits a separate byte comparison.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
STAGES = ('n0', 'qr', 'kr', 'v', 'q', 'k', 'att', 'o', 'r', 'n1', 'gate', 'up', 'act', 'down', 'y')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, sha, size=None):
    raw = Path(path).read_bytes()
    require(digest(raw) == sha and (size is None or len(raw) == size), 'identity drift: ' + str(path))
    return raw


def terminal(summary):
    require(summary['status'] == 'FAILED' and summary.get('error') ==
            'software recipe timeout; no completion claimed', 'only post-terminal oracle timeout is recoverable')
    execution = summary.get('execution', {})
    host = execution.get('host', {})
    result = host.get('launch_result') or {}
    require(result.get('completed') == 21 and result.get('jobs') == 17 and result.get('status') is None,
            'actual whole terminal missing')
    require(host['accepted']['result_fire'] == 1 and host['accepted']['completion_fire'] == 21 and
            host['accepted']['owner_result_fire'] == 17 and not host['reset_required'], 'incomplete public retirement')
    require([x['pc'] for x in host['completions']] == list(range(21)) and
            all(x['status'] is None for x in host['completions']), 'public completion identity')
    require(execution['same_owner_and_banks'] and execution['same_physical_memory_and_services'],
            'wholegraph resource identity')
    require(summary['rows'] == 128 and summary['prelaunch_intermediate_payloads'] == [], 'M128 raw-input scope')
    require(not summary['rtl_executed'] and not summary['scala_executed'] and
            summary['native_policy'] == 'UNCHANGED_FAIL_POLICY_PENDING', 'model/precision scope')


def oracle_binding(summary, oracle, arena):
    require(oracle['completion_status'] == 'ALL_15_SOFTWARE_STAGES_COMPLETE' and oracle['shape']['tokens'] == 128,
            'incomplete or wrong-shape archived oracle')
    require(oracle['source_identity'] == summary['binaries']['oracle_provenance'] and
            oracle['input'] == summary['input_spec']['original_input'] and
            oracle['input']['readonly_sha256'] == arena['sha256'] and
            summary['loaded_inputs']['x']['sha256'] == oracle['input']['input_x_sha256'],
            'archived oracle source/binary/input mismatch')


def identical_stage(data, independent, saved, values):
    require(len(data) == values * 4 and data == independent == saved, 'actual stage byte/shape mismatch')


def verify(actual_summary, expected_sha, prefix_summary, expected_prefix_sha, *, root=ROOT):
    started = time.monotonic()
    root, actual_summary, prefix_summary = Path(root), Path(actual_summary), Path(prefix_summary)
    raw = checked(actual_summary, expected_sha); summary = json.loads(raw); terminal(summary)
    snapshot_path = Path(summary['reviewed_snapshot'])
    snapshot = json.loads(checked(snapshot_path, summary['reviewed_snapshot_sha256']))
    for key in ['rows', 'epoch', 'source_sha256', 'input_spec', 'loaded_inputs', 'binaries']:
        require(summary[key] == snapshot[key], 'capture/snapshot drift: ' + key)
    sources = summary['source_sha256']
    require(len(sources) == 75, 'complete frozen execution source set')
    for path, sha in sources.items():
        checked(root / path, sha)
    for path, sha in summary['binaries']['oracle_artifacts'].items():
        checked(path, sha)
    checked(summary['binaries']['library'], summary['binaries']['library_sha256'])
    spec = summary['input_spec']
    metadata = {p: json.loads(checked(root / p, h)) for p, h in spec['metadata_sha256'].items()}
    arena = spec['oracle_arena']; checked(root / arena['path'], arena['sha256'], arena['bytes'])
    oracle_path = root / 'work/qwen2_block_recipe_m128_release_20261011/RESULT.json'
    oracle = metadata[str(oracle_path.relative_to(root))]
    oracle_binding(summary, oracle, arena)
    saved_path = root / 'work/qwen2_fullgraph_dataflow_20261011/cold_m128/RESULT.json'
    saved = metadata[str(saved_path.relative_to(root))]
    require(saved['tokens'] == 128 and saved['all_15_stages_bit_exact'] and saved['arena_sha256'] == arena['sha256'],
            'saved producer input/scope')
    require(tuple(x['name'] for x in oracle['stages']) == STAGES == tuple(x['name'] for x in saved['stages']),
            'exact fifteen-stage reference set')
    actual = actual_summary.parent
    whole, extra, identities = {}, {}, {}
    provenance = {}
    def actual_bytes(name):
        data = (actual / ('actual_' + name + '.f32le')).read_bytes()
        output = summary['execution']['memory']['outputs'][name]
        if name not in ('gate', 'up'):
            require(output['terminal'] and output['published'] and
                    output['bytes'] == output['written_bytes'] == output['ack_bytes'] == len(data) and
                    output['sha256'] == digest(data), 'actual output differs from original terminal hash: ' + name)
            provenance[name] = 'Hash/bytes/ACK/publication recorded in the original completed-run summary.'
        else:
            require(not output['published'] and not output['terminal'] and output['written_bytes'] == 0,
                    'virtual Gate/Up unexpectedly published')
            provenance[name] = 'Original-run resident observer file; bulk hash was first recorded by postprocessing, not prebound in the failed summary.'
        return data
    for old, saved_stage in zip(oracle['stages'], saved['stages']):
        name = old['name']; width = 8960 if name in ('gate', 'up', 'act') else 256 if name in ('kr', 'v', 'k') else 1536
        require(old['shape'] == [128, width] and saved_stage['width'] == width, 'stage shape')
        data = actual_bytes(name)
        require(len(data) == 128 * width * 4, 'actual stage size')
        independent = checked(oracle_path.parent / old['path'], old['sha256'], len(data))
        saved_data = checked(saved_path.parent / saved_stage['path'], saved_stage['sha256'], len(data))
        identical_stage(data, independent, saved_data, 128 * width)
        identities[name] = digest(data)
        whole[name] = dict(values=len(data)//4, actual_sha256=digest(data), independent_sha256=digest(independent),
                           saved_sha256=digest(saved_data), independent_bit_mismatches=0, saved_bit_mismatches=0)
    prefix = json.loads(checked(prefix_summary, expected_prefix_sha))
    require(prefix['status'] == 'PASS_PUBLIC21_PREFIX_SOFTWARE_ONLY_NOT_NATIVE_ACCEPTED' and prefix['rows'] == 128,
            'archived prefix scope')
    require(all(summary['loaded_inputs'].get(k) == v for k, v in prefix['loaded_inputs'].items()) and
            set(prefix['loaded_inputs']) == {'x','gamma0','rope','bq','bk','bv','wq','wk','wv'}, 'prefix raw input identity')
    require(prefix['input_spec']['oracle_arena'] == arena and prefix['input_spec']['original_input'] == oracle['input'],
            'prefix arena/positions identity')
    old_compile = prefix['comparison']['oracle_compile']
    require(old_compile['source_sha256'] == snapshot['oracle_source_sha256'], 'prefix method source identity')
    frozen_oracle = Path(prefix['reviewed_snapshot']).parent / 'frozen_oracle'
    for name, sha in old_compile['source_sha256'].items():
        checked(frozen_oracle / name, sha)
    prefix_dir = prefix_summary.parent / 'independent_original_recipe'
    checked(prefix_dir / 'prefix_recipe', old_compile['binary_sha256'])
    for name in ('qraw', 'kraw', 'vraw', 'kv'):
        data = actual_bytes(name)
        old = prefix['comparison']['outputs'][name]
        independent = ((prefix_dir / 'k.f32le').read_bytes() + (prefix_dir / 'v.f32le').read_bytes()
                       if name == 'kv' else (prefix_dir / (name + '.f32le')).read_bytes())
        require(digest(independent) == old['independent_sha256'] and len(data) == old['values'] * 4 and
                data == independent, 'actual raw-prefix mismatch: ' + name)
        identities[name] = digest(data)
        extra[name] = dict(old, actual_sha256=digest(data))
    require(digest(actual_summary.read_bytes()) == expected_sha, 'original failure receipt was changed')
    for path, sha in sources.items():
        checked(root / path, sha)
    for name, sha in identities.items():
        checked(actual / ('actual_' + name + '.f32le'), sha)
    return dict(schema=1, status='PASS_POST_TERMINAL_COMPARE_NOT_NATIVE_ACCEPTED',
        original_actual_summary=str(actual_summary), original_actual_summary_sha256=expected_sha,
        original_run_status='FAILED', original_run_error=summary['error'], original_wall_budget_seconds=1200,
        original_run_host_wall_seconds=summary['host_wall_seconds'], original_failure_preserved=True,
        model_rerun=False, reference_rerun=False, postprocess_host_wall_seconds=time.monotonic()-started,
        reviewed_snapshot_sha256=summary['reviewed_snapshot_sha256'], source_sha256_after=sources,
        verifier_sha256=digest(Path(__file__).read_bytes()),
        reference_metadata_sha256=spec['metadata_sha256'], archived_prefix_summary_sha256=expected_prefix_sha,
        archived_prefix_oracle_source_sha256=old_compile['source_sha256'], archived_prefix_oracle_binary_sha256=old_compile['binary_sha256'],
        actual_output_sha256=identities, actual_output_provenance=provenance,
        whole_comparison=whole, additional_prefix_comparison=extra,
        checked_values=sum(x['values'] for x in [*whole.values(), *extra.values()]),
        native_acceptance='UNCHANGED_FAIL_POLICY_PENDING', rtl_executed=False, scala_host_executed=False,
        hardware_cycles=None, full_wall_mac_utilization=None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--actual-summary', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--prefix-summary', required=True, type=Path)
    p.add_argument('--prefix-sha256', required=True)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    require(not a.out.exists(), 'fresh postprocess output required')
    result = verify(a.actual_summary, a.sha256, a.prefix_summary, a.prefix_sha256)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(result['status'], result['checked_values'])


if __name__ == '__main__':
    main()
