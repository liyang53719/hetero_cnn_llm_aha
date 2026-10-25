"""One exact admitted public3 M16 pair; no standalone or fullgraph execution mode."""
import argparse
from dataclasses import asdict
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from admission import validate_review
from artifacts import persist_words, persist_fields
import binding
import component
from policy import ARMS, LIMITS, PROFILE
from primitives import need, digest, load_exact, lanes, compare_fields
from reference_capture import capture_reference
import runtime_observer
import selective_binding
from stage_clock import Stages
import support

RUN_OUT = RUN_CONFIG = None


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def retain_arm(out, index, state, actual=None):
    """Available actual bytes only; preserves incomplete evidence without repair."""
    record = dict(index=index, actual_terminal_verified=state.get('actual_terminal_verified', False),
                  capture_error=state.get('capture_error'), service_error=state.get('service_error'),
                  masks=state.get('mask_receipts', []), errors=[])
    capture = state.get('capture')
    fields = getattr(getattr(capture, 'data', None), 'fields', None)
    if fields is not None:
        try: record['fields'] = persist_fields(out, 'CAPTURE_' + str(index), fields)
        except Exception as error: record['errors'].append('fields: ' + type(error).__name__ + ': ' + str(error))
    if actual is not None:
        try:
            words = struct.unpack('<24576I', actual)
            record['actual_output'] = persist_words(out, 'OUTPUT_' + str(index), words)
        except Exception as error: record['errors'].append('actual: ' + type(error).__name__ + ': ' + str(error))
    tracer = state.get('tracer')
    if tracer is not None:
        try: record['raw_stream_receipt'] = tracer.raw_receipt()
        except Exception as error: record['errors'].append('raw stream: ' + type(error).__name__ + ': ' + str(error))
    record['capture_report'] = state.get('capture_report')
    record['driver_report'] = state.get('driver_report')
    record['terminal'] = state.get('terminal')
    record['job'] = state.get('job')
    record['available_control'] = state.get('available_control')
    write_json(out / ('ARM_' + str(index) + '_EVIDENCE.json'), record)
    return record


def controls(x, physical, result):
    owner = x.attention_owner
    writes = [(vars(command), vars(ack)) for command, ack in physical.regions['att']['records']]
    return dict(job=result['job'], terminal=result['terminal'], driver=result['owner'],
        public_counts=dict(x.counts), completions=x.completions, requests=x.requests,
        physical=physical.report(), writes=writes,
        service_counts=dict(x.matrix_service.counts), scalar_calls=dict(owner.scalar.calls),
        native_fmas=int(x.matrix_service.lib.matrix_normal_fmas()),
        dense_native_fmas=int(x.matrix_service.lib.matrix_dense_fmas()),
        work_events=dict(owner.ordered_adapter.events), lane_calls=dict(owner.ordered_adapter.lanes.calls),
        owner_counts=dict(owner.counts), owner_clock=owner.clock)


def causal_scores(fields):
    field = fields['scores_bf16']
    need(tuple(field['shape']) == (12, 16, 16), 'M16 score shape')
    return tuple(field['words'][(h * 16 + t) * 16 + k]
                 for t in range(16) for h in range(12) for k in range(t + 1))


def compare_pair(arms, stream, config):
    need(len(arms) == 2 and tuple(a['variant'] for a in arms) == ARMS and
         all(a['terminal_verified'] for a in arms), 'both actual component terminals required')
    a, b = arms
    need(a['actual'] == b['actual'] and a['control'] == b['control'], 'observer perturbed actual output/control')
    compare_fields(a['fields'], b['fields'])
    for name in a['fields']:
        need(tuple(a['fields'][name]['frequency']) == tuple(b['fields'][name]['frequency']),
             'observer changed actual frequency: ' + name)
    need([r['phase'] for r in b['masks']] == ['installed', 'cleaned'], 'exact candidate mask lifecycle')
    limits = dict(expected_groups=1728, expected_events=44355,
                  max_events=config['event_stream_max_events'], max_bytes=config['event_stream_max_bytes'])
    need(stream.equal(a['stream_path'], b['stream_path'], limits=limits, canonical=True),
         'observer perturbed canonical production lifecycle stream')
    return dict(status='PASS_PAIR_ACTUAL_OUTPUT_CONTROL_TEN_FIELDS_STREAM_EQUIVALENCE',
                ticket_policy='first-appearance native ticket alpha-renaming only; raw streams retained',
                frequency_equal=True, performance_adopted=False)


def compare_reference(config, inputs, arms, base_fields, out):
    need(len(arms) == 2 and all(a['terminal_verified'] for a in arms), 'all actual terminals before reference import')
    path = Path(config['oracle_harness'])
    saved = list(sys.argv)
    sys.argv = [str(path), '--source-root', config['raw_root']]
    spec = importlib.util.spec_from_file_location('_terminal_only_m16_component_recipe', path)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try: spec.loader.exec_module(module)
    finally: sys.argv[:] = saved
    reference = capture_reference(module, 16, inputs, base_fields, config['reference_sources'], terminal_gate=True)
    expected = struct.pack('<24576I', *reference['output'])
    for arm in arms:
        need(arm['actual'] == expected, 'independent original recipe output mismatch')
        need(causal_scores(arm['fields']) == reference['scores'], 'independent original recipe score mismatch')
        compare_fields(arm['fields'], reference['fields'])
    persist_words(out, 'REFERENCE_OUTPUT', reference['output'])
    persist_words(out, 'REFERENCE_SCORES', reference['scores'])
    persist_fields(out, 'REFERENCE', reference['fields'])
    write_json(out / 'REFERENCE_REPORT.json', reference['report'])
    return dict(status='PASS_INDEPENDENT_ATTENTION_RECIPE_ONLY', fields=10,
                output_sha256=hashlib.sha256(expected).hexdigest(),
                scores_sha256=hashlib.sha256(struct.pack('<1632I', *reference['scores'])).hexdigest(),
                reference_capture=reference['report'], shared_exact_primitive_provenance_disclosed=True,
                official_full_layer_executed=False, official_m16_pair_used_as_dut_acceptance=False)


def main():
    global RUN_OUT, RUN_CONFIG
    parser = argparse.ArgumentParser()
    for name in ('config', 'sha', 'review', 'review-sha', 'out'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--m', type=int, choices=(16,), required=True)
    args = parser.parse_args()
    stages = Stages()
    need(os.environ.get('ORDERED_NATIVE_PARENT') == str(os.getppid()), 'supervised worker required')
    need(digest(args.config) == args.sha, 'exact config identity')
    config, review = validate_review(args.config, args.review, args.review_sha, HERE)
    support.check_manifest(config)
    need(config['profile'] == PROFILE and config['arm_order'] == list(ARMS), 'exact public3 M16 pair profile')
    need(len(os.sched_getaffinity(0)) == 1 and resource.getrlimit(resource.RLIMIT_AS)[0] == LIMITS['address_space_bytes'], 'resource caps')
    need(not any(k.startswith('LD_') for k in os.environ), 'loader override')
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        need(os.environ.get(key) == '1', 'one-thread runtime setting: ' + key)
    out = Path(args.out); RUN_OUT, RUN_CONFIG = out, config
    for name in ('streams', 'artifacts', 'audits', 'metadata'): (out / name).mkdir()
    identity = support.process_identity(); write_json(out / 'metadata/IDENTITY.json', identity)
    for key, value in config['git_environment'].items(): os.environ[key] = value
    sys.path[:0] = [config['source_root'], config['numpy_root'], config['yaml_root']]
    guard = support.Isolation(config); sys.addaudithook(guard.audit)
    stages.mark('source_runtime_pins_isolation_setup')
    input_words, providers = [], {}
    for name, width, port in (('qr', 1536, 'q'), ('kr', 256, 'k'), ('v', 256, 'v')):
        pin = config['inputs'][name]
        need(digest(pin['path']) == pin['sha256'], 'whole frozen operand hash')
        with Path(pin['path']).open('rb') as file: raw = file.read(16 * width * 4)
        need(len(raw) == 16 * width * 4 and hashlib.sha256(raw).hexdigest() == config['input_prefixes'][name]['sha256'], 'exact M16 prefix bytes')
        input_words.append(struct.unpack('<%dI' % (16 * width), raw))
        providers[port] = lambda offset, raw=raw: raw[offset:offset + 64]
    stages.mark('frozen_operand_prefix_hash_and_read')
    runtime, production, direct, ordered, source_receipt = binding.load(config, guard)
    write_json(out / 'metadata/SOURCE_BINDING.json', source_receipt)
    exact = load_exact(config['exact_helper'])
    library, loaded = support.load_library(config, out / 'audits')
    runtime.matrix.configure_library(library); runtime.library = library
    monitor, base = runtime_observer.load_observer(config)
    candidate, candidate_receipt = selective_binding.load_candidate(config)
    write_json(out / 'metadata/CANDIDATE_BINDING.json', candidate_receipt)
    support.audit_runtime(config, out / 'audits', 'SETUP')
    stages.mark('source_bound_modules_exact_primitives_native_load_initial_audit')
    deadline = time.monotonic() + LIMITS['child_wall_seconds']
    arms = []
    for index, variant in enumerate(ARMS):
        arm_stages = Stages(); profile = dict(config, observer_variant=variant)
        x, physical = component.construct_component(runtime, providers, profile, deadline)
        arm_stages.mark('original_resources_reset_and_fixed_scalar_probes')
        state = {}; result = None; failed = True
        path = out / 'streams' / (variant + '.q2evt')
        try:
            result = component.execute_component(x, physical, profile,
                direct_transport=direct, lanes=lanes(ordered, exact),
                production_bridge=production['bridge'], observer=runtime_observer,
                monitor=monitor, base_fields=base.PackedFields, stream_path=path, state=state,
                candidate_capture=(functools.partial(selective_binding.make_capture, candidate)
                                   if variant != 'original' else None),
                candidate_mask_snapshot=(selective_binding.mask_snapshot if variant != 'original' else None),
                mark=arm_stages.mark)
            control = controls(x, physical, result)
            need(control['dense_native_fmas'] == 0 and control['native_fmas'] == 12976128,
                 'zero Dense work and actual successful M16 native FMA witness')
            stream_receipt = production['stream'].verify(path, expected_groups=1728, expected_events=44355,
                max_events=config['event_stream_max_events'], max_bytes=config['event_stream_max_bytes'])
            arm_stages.mark('independent_stream_replay')
            write_json(out / 'metadata' / ('CONTROL_' + str(index) + '.json'), control)
            write_json(out / 'metadata' / ('STREAM_' + str(index) + '.json'), stream_receipt)
            failed = False
        finally:
            original_error = sys.exc_info()[1]
            try:
                actual = (result['actual'] if result is not None else
                          physical.raw(physical.fixture.specs['att'][0], 98304)
                          if state.get('actual_terminal_verified') is True else None)
                if result is None and state.get('actual_terminal_verified') is True:
                    state['available_control'] = controls(x, physical, dict(
                        job=state['job'], terminal=state['terminal'], owner=state['driver_report']))
                retained = retain_arm(out / 'artifacts', index, state, actual)
                if not failed: need(not retained['errors'], 'actual evidence persistence failed')
            except BaseException:
                if original_error is None: raise
        arm_stages.mark('actual_evidence_retention')
        support.audit_runtime(config, out / 'audits', 'ARM_' + str(index) + '_TERMINAL')
        arm_stages.mark('post_arm_runtime_audit')
        arms.append(dict(variant=variant, actual=result['actual'], control=control,
            fields=state['capture'].data.fields, masks=state['mask_receipts'],
            terminal_verified=state.get('actual_terminal_verified') is True,
            stream_path=path, stages=arm_stages.rows, capture_report=state['capture_report']))
        write_json(out / 'metadata' / ('TIMING_' + str(index) + '.json'), arm_stages.rows)
    stages.mark('two_actual_public3_arms_with_complete_retention_and_audit')
    pair = compare_pair(arms, production['stream'], config)
    stages.mark('pair_actual_control_capture_and_stream_comparison')
    need(all(a['terminal_verified'] for a in arms), 'two terminal gate')
    guard.terminal = True
    reference = compare_reference(config, input_words, arms, base.PackedFields, out / 'artifacts')
    stages.mark('terminal_only_independent_attention_recipe_comparison')
    guard.integrity = True
    try: support.check_manifest(config)
    finally: guard.integrity = False
    support.audit_runtime(config, out / 'audits', 'POSTFLIGHT')
    stages.mark('final_sources_inputs_runtime_inventory')
    summaries = [{k: v for k, v in arm.items() if k not in ('actual', 'fields', 'stream_path', 'control')} for arm in arms]
    write_json(out / 'RESULT.json', dict(status='PASS_M16_PUBLIC3_PRODUCTION_STREAM_PAIR_DIAGNOSTIC_ONLY',
        profile=PROFILE, rows=16, execution_order=list(ARMS), identity=identity, loaded=loaded,
        arms=summaries, control=pair, comparison=reference, stages=stages.rows,
        inputs_reverified=True, reference_after_both_component_terminals=True,
        fullblock=False, hardware_cycles=False, performance_adopted=False,
        process_cpu_ns=time.process_time_ns()))


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        if RUN_OUT is not None:
            try: write_json(RUN_OUT / 'metadata/FAILED_RETAINED.json', dict(type=type(error).__name__, detail=str(error)))
            except BaseException: pass
            if RUN_CONFIG is not None:
                try: support.audit_runtime(RUN_CONFIG, RUN_OUT / 'audits', 'FAILURE')
                except BaseException: pass
        raise
