"""Real H2048 typed-memory RMS gate; no full block, Matrix, Chisel or RTL.

The owner completes first. Original upstream component and independent formula
are then evaluated from the same immutable raw inputs, never fed to the owner.
Only compact hashes/results are suitable for Git; raw tensors stay in work/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import time

from . import reference as r


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--include-qkv', action='store_true', help='Verify the explicitly acquired three-tensor payload')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wall-seconds', type=int, default=120)
    args = parser.parse_args(argv)
    r.require(not args.output.is_symlink() and args.output.resolve().is_relative_to(r.ROOT / 'work'),
              'raw evidence must stay under ignored work/')
    r.require(not args.output.exists(), 'fresh evidence directory required')
    r.require(30 <= args.wall_seconds <= 600, 'bounded software budget 30..600 seconds')
    args.output.mkdir(parents=True)
    report = dict(status='RUNNING', cases=[], claim_boundary=dict(
        typed_memory_owner_executed=True, official_rms_component_executed=False,
        full_block_executed=False, command128_executed=False,
        chisel_executed=False, rtl_executed=False, hardware_cycles=None))
    started = time.monotonic()
    driver = None

    def save():
        report['elapsed_seconds'] = time.monotonic() - started
        (args.output / 'summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def timeout(signum, frame):
        raise TimeoutError('H2048 typed owner software wall budget exhausted')

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.wall_seconds)
    try:
        import numpy as np
        import torch
        from . import owner as o
        from .formula import formula, decode
        from .diagnose import fp32_stats
        from candidates.qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
        from heteronpu.matrix_norm_rope_candidate import MAX_ABS, MEAN_ABS
        r.require((MAX_ABS, MEAN_ABS) == (.03125, .005), 'original per-node thresholds changed')
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        report['runtime'] = r.runtime_identity()
        report['runner_sha256'] = r.file_sha(__file__)
        memory, scalar = o.TypedMemory(), o.SharedScalar()
        events = {}

        def observe(stage, token, words):
            r.require((stage, token) not in events, 'duplicate actual observation')
            events[stage, token] = words

        engine = o.RmsOwner(scalar, observe)
        identities = (id(memory), id(scalar), id(engine))
        old_outputs = []
        for number, tokens in enumerate((16, 128)):
            events.clear()
            report['active_case'] = dict(tokens=tokens, status='RUNNING')
            hidden, weight, provenance = r.payload_case(args.payload, args.manifest_sha256, list(range(tokens)), include_qkv=args.include_qkv)
            base = 0x100000 + number * 0x400000
            memory.add_readonly(base, hidden)
            memory.add_readonly(base + 0x100000, weight)
            memory.allocate_output(base + 0x200000, len(hidden))
            job = o.RmsJob(3516 + number, base, base + 0x100000, base + 0x200000, tokens)
            driver = o.TypedRmsDriver(engine, memory, job)
            begin = time.monotonic()
            for tick in range(tokens * 2048):
                driver.tick(memory_ready=tick % 3 != 0, memory_response_ready=tick % 4 != 0,
                            response_ready=tick % 5 != 0)
                if driver.response is not None:
                    break
            r.require(driver.response is not None and driver.response.status is None, 'owner did not complete successfully')
            r.require(driver.output.published and driver.response.write_bytes == len(hidden), 'public output/ACK boundary')
            r.require((id(memory), id(scalar), id(engine)) == identities and scalar.client is None and memory.pending is None,
                      'shared resources changed or failed to drain')
            actual = driver.output.raw()
            for region, previous in old_outputs:
                r.require(region.published and region.raw() == previous, 'prior actual output changed')
            old_outputs.append((driver.output, actual))
            owner_seconds = time.monotonic() - begin
            official = r.component(hidden, weight, tokens)
            independent = formula(hidden, weight, tokens)
            r.require(actual == independent['output'], 'actual owner differs from independent fixed arithmetic')
            stages = {}
            for stage in ('squares', 'sum', 'mean', 'mean_eps', 'root', 'inverse', 'scaled', 'gamma', 'weighted', 'output'):
                r.require(all((stage, token) in events for token in range(tokens)), 'missing actual causal stage: ' + stage)
                words = np.asarray([events[stage, token] for token in range(tokens)], dtype='<u4')
                value = words.view('<f4').reshape(1, tokens, -1)
                expected = (decode(independent['output'], (1, tokens, o.WIDTH)) if stage == 'output'
                            else independent['trace'][stage])
                expected = np.broadcast_to(expected, value.shape)
                fixed = fp32_stats(value, expected)
                r.require(fixed['bit_mismatches'] == 0, 'fixed arithmetic node mismatch: ' + stage)
                native_key = 'sum_auxiliary' if stage == 'sum' else stage
                if stage == 'root':
                    native = None  # upstream has rsqrt, no standalone sqrt tensor
                else:
                    target = (decode(official['output'], value.shape) if stage == 'output'
                              else np.broadcast_to(official['trace'][native_key], value.shape))
                    native = fp32_stats(value, target)
                stages[stage] = dict(fixed=fixed, official=native,
                                    auxiliary_native_sum=stage == 'sum', official_root_not_materialized=stage == 'root')
            comparison = compare_finite_bf16(actual, official['output'])
            passed = comparison['max_abs'] <= MAX_ABS and comparison['mean_abs'] <= MEAN_ABS
            r.require(passed, 'original official BF16 output gate failed')
            calls = engine.report()['scalar_calls']
            expected_calls = {'mul_ieee_rne': tokens * 6145, 'add': tokens * 4265, 'sqrt': tokens, 'div': tokens}
            r.require(calls == expected_calls, 'logical scalar request count drift')
            r.require(driver.counts['read_bytes'] == tokens * 12288 and driver.counts['write_bytes'] == tokens * 4096,
                      'physical software byte traffic drift')
            case = dict(name='actual_embedding_rms_m' + str(tokens), tokens=tokens, provenance=provenance,
                owner=driver.report(), stages=stages, official_output={**comparison, 'passed': passed,
                    'thresholds': dict(max_abs=MAX_ABS, mean_abs=MEAN_ABS)},
                shared_resources_reused=True, earlier_outputs_unchanged=True, owner_host_seconds=owner_seconds,
                performance=dict(scope='RMS_COMPONENT_TYPED_SOFTWARE_REQUESTS_ONLY', matrix_mac_capacity=4096,
                    vector_lane_capacity=16, shared_scalar_units=1, useful_matrix_macs=0, executed_matrix_macs=0,
                    scalar_requests=sum(calls.values()), scalar_requests_by_operation=calls,
                    software_model_ticks=driver.counts['ticks'], hardware_cycles=None, matrix_utilization=None,
                    busy_duty=None, active_lane_duty=None, stalls=None, overlap=None,
                    missing='Cycle/port model and actual RTL timeline; software ticks and host seconds are not cycles'))
            report['cases'].append(case)
            report['active_case'] = None
            report['claim_boundary']['official_rms_component_executed'] = True
            for name, data in (('input', hidden), ('weight', weight), ('actual_output', actual), ('official_output', official['output'])):
                (args.output / (case['name'] + '.' + name + '.bin')).write_bytes(data)
            save()
            print(json.dumps(dict(case=case['name'], official_output_bit_mismatches=comparison['bit_mismatches'],
                scalar_requests=sum(calls.values()), owner_seconds=owner_seconds)), flush=True)
        report['status'] = 'PASS_H2048_TYPED_RMS_COMPONENT_M16_M128'
    except BaseException as error:
        report['status'] = 'FAILED'
        report['error'] = dict(type=type(error).__name__, message=str(error))
        if driver is not None:
            report['failed_owner_snapshot'] = driver.report()
            (args.output / 'failed_owner_output.bin').write_bytes(driver.output.raw())
        save()
        raise
    finally:
        signal.alarm(0)
    save()


if __name__ == '__main__':
    main()
