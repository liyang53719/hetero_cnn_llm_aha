"""Stdlib-only suffix comparison after verified cleanup; never executes an owner.

Fresh mode: --plan and --reviewed-plan-sha256. Historical mode: --historical-case
and --bundle; authenticates the exact reviewed saved artifacts, not a new launch.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_chunk import bf16_metrics, pin, sha, verify
from suffix_case import NAMES, DENSE_STAGES, case, plan_case, complete, need

SCOPE_FLAGS = ('full_block_acceptance', 'single_resident_full_block_lifecycle', 'original_continuation',
               'state_committed', 'history_committed', 'generation_advanced', 'output_reference_read')
SCALAR_CALLS = {
    'gated_norm': dict(add=526336, div=264192, exp_negative=262144, mul_ieee_rne=1574912, sqrt=2048),
    'attention_residual': dict(add=131072),
    'post_norm': dict(add=275584, mul_ieee_rne=393344, sqrt=128, div=128),
    'silu_mul': dict(add=458752, div=458752, exp_negative=458752, mul_ieee_rne=1376256),
    'output': dict(add=131072),
}


def load(path):
    return json.loads(Path(path).read_text())


def supervised_admission(launch, cleanup, plan_sha):
    need(launch['plan_sha256'] == plan_sha and launch['isolated_component_complete_uncompared'] is True and
         launch['natural_exit'] is True and launch['cleanup_confirmed'] is True and launch['returncode'] == 0 and
         launch['failure'] is None and launch['all_frozen_actual_inputs_unchanged'] is True, 'supervised successful terminal')
    proof = launch['cleanup_proof']
    need(proof['status'] == 'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP' and proof['empty_complete_scans'] == 2 and
         proof['direct_leader_reaped'] is True and proof['direct_exit_code'] == 0 and
         cleanup['cleanup_complete'] is True and cleanup['proof'] == proof, 'strict owned cleanup admission')


def metrics(actual, reference, stage, byte_count):
    result = bf16_metrics(actual, reference, byte_count // 2); worst = result.pop('worst_index')
    width = 3584 if stage in ('gate', 'up', 'silu_mul') else 1024
    if stage == 'output':
        result['thresholds'] = dict(max_abs=.05, mean_abs=.01)
        result['meets_existing_node_thresholds'] = result['max_abs'] <= .05 and result['mean_abs'] <= .01
    result['worst_location'] = (dict(token=worst//2048, head=(worst//128)%16, column=worst%128)
                                if stage == 'gated_norm' else dict(batch=0, token=worst//width, column=worst%width))
    return result


def stage_admission(stage, summary, terminal, plan, plan_sha, prior_sha=None):
    expected_bytes = plan['references'][stage]['bytes']
    need(summary['stage'] == stage and summary['status'] == 'ISOLATED_STAGE_COMPLETE_UNCOMPARED' and
         summary['terminal_count'] == 1 and summary['complete'] is True and summary['output_published'] is True and
         summary['block_generation'] == 0 and not any(summary[k] for k in SCOPE_FLAGS) and
         summary['aborted_for_deadline'] is False and summary['accepted_write_beats'] == summary['accepted_ack_beats'] == expected_bytes//64,
         'complete scoped stage receipt')
    need(terminal['stage'] == stage and terminal['status'] == 'STAGE_COMPLETE_UNCOMPARED' and
         terminal['plan_sha256'] == plan_sha and terminal['real_owner_terminal'] is True and terminal['terminal_count'] == 1 and
         terminal['response'] == summary['response'] and terminal['input_sha256'] == summary['input_sha256'] and
         terminal['output_sha256'] == summary['output_sha256'] and terminal['output_bytes'] == expected_bytes and
         terminal['output_published'] is True, 'durable real stage terminal identity')
    keys = {'gated_norm': ('core', 'z', 'weight'), 'o': ('gated_norm', 'weight_kn'),
            'attention_residual': ('hidden', 'o'), 'post_norm': ('weight',),
            'gate': ('post_norm', 'gate_weight_kn'), 'up': ('post_norm', 'up_weight_kn'),
            'silu_mul': ('gate', 'up'), 'down': ('weight_kn',), 'output': ('attention_residual',)}[stage]
    expected_inputs = [plan['stage_inputs'][key]['sha256'] for key in keys]
    if stage in ('post_norm', 'down', 'output'):
        need(prior_sha is not None, 'matching actual predecessor required')
        expected_inputs.insert(1 if stage == 'output' else 0, prior_sha)
    need(summary['input_sha256'] == expected_inputs, 'actual driver input hash chain')
    if stage in DENSE_STAGES:
        counts = summary['counts']; matrix = summary['matrix']; mc = matrix['counters']
        tag, fmas, steps, reads, done, results = {
            'o': (90, 268435456, 65536, 8192, 7, 32),
            'gate': (120, 469762048, 114688, 4096, 23, 112),
            'up': (130, 469762048, 114688, 4096, 23, 112),
            'down': (150, 469762048, 114688, 14336, 14, 64)}[stage]
        cumulative = 2 if stage == 'up' else 1
        need(summary['response'] == [tag, None, expected_bytes] and summary['numeric_fault'] is None and
             summary['executed_fmas'] == fmas and counts['steps'] == steps and
             counts['a_read_beats'] == reads and counts['b_read_beats'] == steps and
             counts['write_data_bytes'] == counts['ack_bytes'] == expected_bytes and counts['done'] == done and counts['results'] == results and
             mc['owner_acquires'] == mc['owner_releases'] == mc['owner_responses'] == cumulative and mc.get('aborts', 0) == 0 and
             matrix['dense_fma_calls'] == fmas*cumulative and matrix['normal_fma_calls'] == 0 and
             matrix['same_accumulator_resource'] is True and matrix['reset_required'] is False, 'Dense recipe/lifecycle')
        if stage == 'down':
            need(all(counts[key] == value for key, value in dict(prefix_ack_bytes=524288, prefix_read_beats=8192,
                 prefix_write_data_bytes=524288, seed_acks=32, seed_beats=8192, seed_begins=32, seed_errors=0).items()) and
                 summary['prefix_bytes'] == summary['prefix_extent'] == 524288 and
                 type(summary['prefix_version']) is list and all(type(v) is int for v in summary['prefix_version']) and
                 summary['prefix_version'] == [150, 1, 0, 1, 2560] and
                 summary['prefix_published'] is False and mc['dense_seed_acks'] == 32, 'original private seeded prefix')
        else:
            need(summary['workspace_metadata'] == dict(base=0x4000000 if stage in ('gate', 'up') else 0x1000000,
                 extent=524288, generation=1, prefix_bytes=0, memory_region_allocated=False), 'ordinary metadata without prefix')
    else:
        response = summary['response']; owner = summary['owner']; accepted = owner['accepted']
        reads = {'gated_norm': 16392, 'attention_residual': 8192, 'post_norm': 4128, 'silu_mul': 28672, 'output': 8192}[stage]
        binding = summary['scalar_arithmetic_binding']
        need(response['status'] is None and response['write_bytes'] == expected_bytes and
             response['tag'] == {'gated_norm': 80, 'attention_residual': 100, 'post_norm': 110, 'silu_mul': 140, 'output': 160}[stage] and
             owner['scalar_calls'] == SCALAR_CALLS[stage] and accepted['read_requests'] == reads and
             accepted['write_requests'] == accepted['write_acks'] == expected_bytes//64 and
             accepted['memory_responses'] == reads + expected_bytes//64 and accepted['owner_results'] == 1 and
             binding['implementation'] == 'DecayScalar' and binding['enable_ieee_exp'] is True and
             binding['enable_softplus'] is True, 'original Scalar operation and transaction counts')
        if stage == 'gated_norm':
            need(summary['staging_complete'] is True and owner['production_geometry'] is True and owner['active_heads'] == 16,
                 'full original GatedNorm geometry')
        if stage in ('attention_residual', 'output', 'silu_mul'):
            need(owner['operation'] == ('SiluMul' if stage == 'silu_mul' else 'Add') and owner['hidden_width'] == 1024 and owner['test_geometry'] is False,
                 'original elementwise geometry')
            if stage == 'silu_mul':
                need(owner['ffn_width'] == 3584 and owner['production_geometry'] is True, 'full SiLUMul width')
        if stage == 'post_norm':
            need(owner['identity']['policy'] == 'torch210_cpu_default1024', 'original RMS policy')


def compare_fresh(plan_path, plan_sha):
    need(pin(plan_path)['sha256'] == plan_sha, 'reviewed plan changed')
    plan = load(plan_path); selected = plan_case(plan); run = Path(plan['run_directory']); actual = run / 'actual'
    supervised_admission(load(run / 'LAUNCH.json'), load(run / 'CLEANUP.json'), plan_sha); verify(plan)
    root = load(actual / 'summary.json')
    need(complete(root, actual, selected) and not any(root[k] for k in SCOPE_FLAGS), 'complete suffix scope')
    git = root['source_git']; need(git['complete'] is True and git['total_calls'] == sum(selected['git_calls'].values()), 'exact source-identity count')
    reports = {}; prior_sha = None; stable = {path: pin(path) for path in (run/'LAUNCH.json', run/'CLEANUP.json', actual/'summary.json')}
    for stage in selected['stages']:
        directory = actual / stage; summary = load(directory / 'summary.json'); terminal = load(directory / 'STAGE_TERMINAL.json')
        stage_admission(stage, summary, terminal, plan, plan_sha, prior_sha)
        for path in (directory/'summary.json', directory/'STAGE_TERMINAL.json'):
            stable[path] = pin(path)
        output = directory / 'output.bf16le'; reference = Path(plan['references'][stage]['path'])
        stable[output] = pin(output); stable[reference] = pin(reference)
        need(stable[output]['sha256'] == summary['output_sha256'], 'actual output hash')
        reports[stage] = metrics(output.read_bytes(), reference.read_bytes(), stage, selected['references'][stage]['bytes'])
        reports[stage].update(output_pin=stable[output], reference_pin=stable[reference], candidate_elapsed_seconds=summary['elapsed_seconds'])
        prior_sha = stable[output]['sha256']
    if selected['name'] == 'residual_post_norm':
        handoff = root['handoff']
        need(handoff['method'] == 'DIRECT_GENUINE_ACCEPTED_TYPED_REGION_NO_COPY_OR_REPLACEMENT' and
             handoff['source_sha256'] == reports['attention_residual']['output_pin']['sha256'] and
             handoff['source_bytes'] == 262144 and handoff['written_beats'] == handoff['acknowledged_beats'] == 4096 and
             all(handoff[key] is True for key in ('same_scalar', 'same_memory', 'same_region', 'same_storage')), 'direct resident pair handoff')
    if selected['name'] == 'final_triplet':
        need(len(root['handoffs']) == 2, 'two actual resident handoffs')
        for handoff, producer, consumer in zip(root['handoffs'], ('silu_mul', 'down'), ('down', 'output')):
            need(handoff['producer'] == producer and handoff['consumer'] == consumer and
                 handoff['method'] == 'DIRECT_GENUINE_ACCEPTED_TYPED_REGION_NO_COPY_OR_REPLACEMENT' and
                 handoff['source_sha256'] == reports[producer]['output_pin']['sha256'] and
                 handoff['source_bytes'] == reports[producer]['output_pin']['bytes'] and
                 handoff['written_beats'] == handoff['acknowledged_beats'] == handoff['source_bytes']//64 and
                 all(handoff[key] is True for key in ('same_memory', 'same_region', 'same_storage')), 'actual resident triplet chain')
    verify(plan)
    need(all(pin(path) == recorded for path, recorded in stable.items()) and pin(plan_path)['sha256'] == plan_sha, 'comparison artifacts changed')
    return reports


def compare_historical(name, bundle):
    """Authenticate reviewed historical evidence, then independently decode words.

    This does not exercise the relocated preparation, launcher, child or new receipt
    admission. It cannot turn those TEMP_NOT_EXECUTED helpers into a native PASS.
    """
    selected = case(name); expected = selected['historical_artifacts']
    for relative, recorded in expected.items():
        need(pin(bundle / relative) == recorded, 'historical artifact identity: ' + relative)
    plan = load(bundle / 'PLAN.json'); plan_sha = expected['PLAN.json']['sha256']
    supervised_admission(load(bundle / 'run/LAUNCH.json'), load(bundle / 'run/CLEANUP.json'), plan_sha)
    verify(plan); historical = load(bundle / 'comparison.json'); reports = {}
    for stage in selected['stages']:
        directory = bundle / 'run/actual' / (stage if len(selected['stages']) > 1 else '')
        reference = bundle / 'reference' / selected['references'][stage]['filename']
        output = directory / 'output.bf16le'; summary = load(directory / 'summary.json')
        report = metrics(output.read_bytes(), reference.read_bytes(), stage, selected['references'][stage]['bytes'])
        old = historical['stages'][stage] if len(selected['stages']) > 1 else historical
        for key in report:
            if key != 'numerical_mismatches':
                need(report[key] == old[key], 'historical comparator metric parity: ' + stage + '/' + key)
        report.update(output_pin=pin(output), reference_pin=pin(reference), candidate_elapsed_seconds=summary['elapsed_seconds'])
        reports[stage] = report
    verify(plan)
    for relative, recorded in expected.items():
        need(pin(bundle / relative) == recorded, 'historical postcompare artifact drift: ' + relative)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path); parser.add_argument('--reviewed-plan-sha256')
    parser.add_argument('--historical-case', choices=NAMES); parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    historical = args.historical_case is not None
    if (historical and (not args.bundle or args.plan or args.reviewed_plan_sha256)) or (not historical and
            (not args.plan or not args.reviewed_plan_sha256 or args.bundle)):
        parser.error('select exactly one explicit fresh-plan or historical-bundle mode')
    start = time.monotonic()
    reports = (compare_historical(args.historical_case, args.bundle) if historical else compare_fresh(args.plan, args.reviewed_plan_sha256))
    result = dict(status='SAVED_SUFFIX_COMPARISON_COMPLETE', stages=reports, before_after_pins_match=True,
        native_adaptation='TEMP_NOT_EXECUTED', historical_artifacts_only=historical,
        full_block_acceptance=False, single_resident_full_block_lifecycle=False, original_execution_status='UNKNOWN',
        block_generation=0, state_committed=False, history_committed=False, hardware_simulation=False,
        comparison_elapsed_seconds=time.monotonic()-start)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n')
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
