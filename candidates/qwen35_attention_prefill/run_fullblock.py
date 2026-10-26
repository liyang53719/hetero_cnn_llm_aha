"""One live shared-resource L3 cold→carried complete typed software chain.

Uses authenticated original hidden, all eleven weights and captured trig.
Every intermediate is written by a real owner through the same TypedMemory;
only the final accepted residual publishes the staged KV roots/generation.
No official forward, model download, RTL generation, or compilation is run.
Software wall time/ticks are not fixed-resource hardware cycle measurements.
"""
import argparse
import ctypes as C
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

import numpy as np

from . import full_fixture as fixture
from .input_fixture import requested_case_names, select_windows
from . import run_norm_rope as prefix_runner
from .full_compare import FullObservations, compare_case
from .full_driver import L3FullBlockCoordinator, L3FullBlockPlan, ORDER
from .projection_driver import L3ProjectionCoordinator, L3ProjectionPlan
from .norm_rope.coordinator import L3NormRopeCoordinator, L3NormRopePlan
from .norm_rope.owner import QkNorm256Owner, PartialRope64Owner, TORCH_DEFAULT256_POLICY
from .norm_rope.scalar import NormRopeScalar
from .norm_rope.compare import ObservationRecorder
from .gqa.owner import Bf16CausalGqaOwner, SOURCE_PATHS as GQA_SOURCES
from .kv_cache.owner import KvCacheOwner, CAPACITY, TOKEN_BYTES
from .kv_cache.fence import KvBlockFence
from ..qwen35_gdn_prefill.elementwise.model import ElementwiseOwner

prior = prefix_runner.prior
ROOT = prior.ROOT
sha, persist, snapshot_bytes, require = prior.sha, prior.persist, prior.snapshot_bytes, fixture.require
NEW_FILES = ('full_fixture.py', 'full_compare.py', 'full_driver.py', 'run_fullblock.py')
SOURCE_FILES = tuple(sorted(set((*prefix_runner.SOURCE_FILES, *GQA_SOURCES,
    *('candidates/qwen35_attention_prefill/' + name for name in NEW_FILES),
    *('candidates/qwen35_attention_prefill/kv_cache/' + name for name in ('owner.py', 'driver.py', 'fence.py')),
    'candidates/qwen35_gdn_prefill/elementwise/model.py',
    'candidates/qwen35_gdn_prefill/dense_prefix.py',
    'candidates/qwen35_gdn_prefill/prep/scalar.py',
    'candidates/qwen35_gdn_prefill/chunk/vector.py',
    'candidates/qwen35_gdn_prefill/chunk/vector16.cpp',
    'candidates/qwen35_attention_prefill/kv_cache/__init__.py',
    'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/GdnElementwiseOwner.scala',
    *('src/heteronpu/' + name + '.py' for name in ('__init__', 'abi_validation', 'cgra_sfu',
       'command', 'config', 'dtypes', 'kv_engine', 'matrix_engine', 'scheduler',
       'qwen35_dense_contract', 'qwen_family_contracts', 'weight_header_contract')),
))))


def require_loaded_source_closure():
    """Reject executed in-repository Python dependencies omitted from freeze."""
    missing = []
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if path.suffix == '.py' and path.is_relative_to(ROOT):
            name = str(path.relative_to(ROOT))
            if name.startswith(('candidates/', 'src/', 'scripts/', 'python/')) and name not in SOURCE_FILES:
                missing.append(name)
    require(not missing, 'loaded execution dependencies absent from source freeze: ' + ', '.join(sorted(set(missing))))


def active_state(coordinator):
    if coordinator is None:
        return None
    driver = coordinator.active
    return dict(role=coordinator.role, ticks=coordinator.ticks, commands=len(coordinator.commands),
                terminal=coordinator.response is not None,
                owner_state=None if driver is None else getattr(driver.owner, 'state', None),
                driver_counts=None if driver is None else dict(getattr(driver, 'counts', {})))


def array_snapshot(output, name, array):
    item = snapshot_bytes(output, name, np.asarray(array, dtype='<u4').tobytes())
    item.update(shape=list(array.shape), dtype='FP32_RAW_WORDS', host_observation_only=True)
    return item


def save_observations(output, phase, norms, observations, *, partial=False):
    prefix = 'partial_observations' if partial else 'observations'
    records = prefix_runner.freeze_observations(output, phase, norms, prefix=prefix)
    if partial:
        # Preserve only actual events. Absence stays absence on failure.
        for role, entries in observations.rms.items():
            for stage in sorted({key[0] for key in entries}):
                tokens = sorted(t for field, t in entries if field == stage)
                value = np.asarray([entries[stage, t] for t in tokens], dtype='<u4')
                item = array_snapshot(output, prefix + '/' + phase + '.' + role + '.' + stage + '.f32le', value)
                item['tokens'] = tokens; records[role + '.' + stage] = item
        for stage, values in observations.gqa.items():
            mask = observations.gqa_seen[stage]
            item = array_snapshot(output, prefix + '/' + phase + '.' + stage + '.observed.f32le', values[mask])
            item['coordinates'] = array_snapshot(output, prefix + '/' + phase + '.' + stage + '.coordinates.u32le',
                                                 np.asarray(np.argwhere(mask), dtype='<u4'))
            item['full_shape'] = list(values.shape); records[stage] = item
        for role, entries in observations.activations.items():
            values = np.asarray([(index, *words) for index, words in sorted(entries.items())], dtype='<u4')
            records[role] = array_snapshot(output, prefix + '/' + phase + '.' + role + '.events.u32le', values)
    else:
        for stage, values in observations.arrays().items():
            records[stage] = array_snapshot(output, prefix + '/' + phase + '.' + stage + '.f32le', values)
    return records



def compare_selected_windows(cases, manifest, capture_directory, output, actual, norms, observed,
                             *, started, budget_seconds):
    """Compare every selected complete window under the original run clock."""
    names = tuple(case['name'] for case in cases)
    require(names and len(set(names)) == len(names) and
            all(set(values) == set(names) for values in (actual, norms, observed)),
            'exact nonempty selected comparison inputs required')
    comparisons = {}
    for case in cases:
        require(time.monotonic() - started < budget_seconds, 'comparison software wall budget exceeded')
        name = case['name']
        comparisons[name] = compare_case(case, manifest, capture_directory,
                                         actual[name], norms[name], observed[name])
        persist(output / (name + '.comparison.json'), comparisons[name])
        require(time.monotonic() - started < budget_seconds, 'comparison software wall budget exceeded')
    return comparisons


def run(capture_directory, payload_directory, output, *, budget_seconds, windows=('cold', 'carried')):
    requested_case_names(128, windows)  # Reject illegal selection before any output/native work.
    cold_only = windows == ('cold',)
    output = Path(output)
    require(not output.exists() and type(budget_seconds) is int and 1 <= budget_seconds <= 7200,
            'fresh output and explicit software wall budget 1..7200')
    output.mkdir(parents=True)
    started = time.monotonic()
    coordinator = memory = None
    observed = norms = active_outputs = active_name = None
    report = dict(status='RUNNING', scope='QWEN35_L3_COMPLETE_TYPED_SOFTWARE_COORDINATOR',
        budget_seconds=budget_seconds, windows=[], actual_outputs={}, observations={},
        requested_windows=list(windows), execution_window_scope='COLD_ONLY' if cold_only else 'COLD_THEN_CARRIED',
        carried_window_executed=False, complete_capture_seal_required=True,
        rtl_executed=False, chisel_executed=False, public_command128_executed=False,
        full_block_executed=False, original_57_producer_contract_accepted=False,
        hardware_cycles=None, hardware_mac_utilization=None,
        source_initialization='raw_hidden_weights_trig_only_before_any_launch',
        carried_dependency='NOT_EXECUTED_COLD_ONLY' if cold_only else 'preceding_actual_committed_KV_roots_and_generation')
    persist(output / 'summary.json', report)
    try:
        sources = {p: (ROOT / p).read_bytes() for p in SOURCE_FILES}
        report['source_sha256'] = {p: sha(raw) for p, raw in sources.items()}
        for name, raw in sources.items(): snapshot_bytes(output, 'source_snapshot/' + name, raw)
        manifest, weights, inputs, identity, extra = fixture.load_fixture(capture_directory, payload_directory, windows=windows)
        require_loaded_source_closure()
        selected_cases = select_windows(manifest, windows)
        require(tuple(inputs) == tuple(case['name'] for case in selected_cases), 'selected input order/identity')
        report['selected_case_names'] = list(inputs)
        rows = identity['rows']
        library = prior.d.library_from_environment(ROOT)
        vector = prior.Vector16(os.environ['GDN_VECTOR16_LIBRARY'], exception_policy=prior.IEEE_POLICY)
        lib = prior.configure_library(C.CDLL(str(library)))
        require(lib.td_reset() == 0, 'one initial Matrix reset')
        matrix, memory, scalar = prior.d.MatrixService(lib), prior.d.TypedMemory(), NormRopeScalar()
        callbacks = {}
        def rms_observe(stage, token, words):
            role = 'input_norm' if rms.job.output == callbacks['plan'].norm_rope.projection.input_norm else 'post_norm'
            callbacks['full'].rms_callback(role)(stage, token, words)
        def qk_observe(stage, token, head, words):
            role = 'q_norm' if norm.job.role == 0 else 'k_norm'
            callbacks['norm'][role](stage, token, head, words)
        def rope_observe(stage, token, head, words):
            role = 'q_rope' if rope.job.heads == 8 else 'k_rope'
            callbacks['norm'][role](stage, token, head, words)
        def gqa_observe(*args): callbacks['full'].gqa_callback(*args)
        def sigmoid_observe(*args): callbacks['sigmoid'](*args)
        def silu_observe(*args): callbacks['silu'](*args)
        rms = prior.rms.RmsOwner(scalar, observer=rms_observe)
        norm, rope = QkNorm256Owner(scalar, qk_observe), PartialRope64Owner(scalar, rope_observe)
        kv_owner, fence = KvCacheOwner(), KvBlockFence(memory)
        gqa = Bf16CausalGqaOwner(matrix, scalar, gqa_observe)
        elementwise = ElementwiseOwner(scalar, enable_attention_sigmoid_mul=True,
                                      sigmoid_observer=sigmoid_observe, silu_observer=silu_observe)
        address = 0x100000
        def allocate(extent, raw=None):
            nonlocal address
            require(type(extent) is int and extent > 0 and extent % 64 == 0, 'full aligned physical allocation')
            base = address; address += extent + 64
            memory.add_readonly(base, raw) if raw is not None else memory.allocate_output(base, extent)
            return base
        parameters = {}
        for role, raw in weights.items():
            physical = raw if role == 'input_norm' else np.frombuffer(raw, '<u2').reshape(prior.fixture.WIDTHS[role], 1024).T.copy().tobytes()
            parameters[role] = allocate(len(physical), physical)
        for role, raw in extra['weights'].items(): parameters[role] = allocate(len(raw), raw)
        for role, raw in extra['tail_weights'].items():
            shape = fixture.TAIL_WEIGHTS[role][1]
            physical = raw if len(shape) == 1 else np.frombuffer(raw, '<u2').reshape(shape).T.copy().tobytes()
            parameters[role] = allocate(len(physical), physical)
        plans = []
        for index, (name, hidden) in enumerate(inputs.items()):
            outputs = {role: allocate(rows * width * 2) for role, width in fixture.WIDTHS.items()}
            p = L3ProjectionPlan(tokens=rows, hidden=allocate(len(hidden), hidden), input_weight=parameters['input_norm'],
                packed_q_gate_weight=parameters['packed_q_gate'], k_weight=parameters['k'], v_weight=parameters['v'],
                tag_base=1 + index * len(ORDER), **{role: outputs[role] for role in prior.fixture.WIDTHS})
            trig = extra['cases'][name]
            nr = L3NormRopePlan(projection=p, q_norm_weight=parameters['q_norm'], k_norm_weight=parameters['k_norm'],
                q_norm=outputs['q_norm'], k_norm=outputs['k_norm'], gate=outputs['raw_gate'],
                q_rope=outputs['q_rope'], k_rope=outputs['k_rope'], trig=allocate(len(trig['trig']), trig['trig']),
                position_base=trig['position_base'], trig_tokens=trig['trig_tokens'], norm_policy=TORCH_DEFAULT256_POLICY)
            # Two full capacity reservations; physical readable regions cover
            # only actual valid prefixes. Reserved holes never become tensors.
            staging_k = address; address += 2 * CAPACITY * TOKEN_BYTES + 64
            valid_tokens = (index + 1) * rows
            memory.allocate_output(staging_k, valid_tokens * TOKEN_BYTES)
            memory.allocate_output(staging_k + CAPACITY * TOKEN_BYTES, valid_tokens * TOKEN_BYTES)
            outputs['cache_k'], outputs['cache_v'] = staging_k, staging_k + CAPACITY * TOKEN_BYTES
            workspace = prior.PrefixWorkspace(allocate(524288), 524288, index + 1, 2560)
            plan = L3FullBlockPlan(norm_rope=nr, o_weight=parameters['o'], post_norm_weight=parameters['post_norm'],
                gate_weight=parameters['gate'], up_weight=parameters['up'], down_weight=parameters['down'],
                staging_k=staging_k, expected_generation=index,
                **{role: outputs[role] for role in ('context', 'gated_context', 'o', 'attention_residual',
                                                   'post_norm', 'gate', 'up', 'silu_mul', 'down', 'output')})
            plans.append((name, plan, outputs, workspace))
        dense = prior.GdnProjectionOwner(plans[0][3])
        libraries = (library, Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']), vector.library, vector.library.with_suffix('.json'))
        local_files = {}
        for name, raw in inputs.items(): local_files['input:' + name] = snapshot_bytes(output, 'raw_inputs/' + name + '.bf16le', raw)
        # Downloadable checkpoint weights stay local and are not copied again.
        for name, trig in extra['cases'].items(): local_files['trig:' + name] = snapshot_bytes(output, 'trig/' + name + '.bf16le', trig['trig'])
        for index, path in enumerate(libraries): local_files['library:' + str(path)] = snapshot_bytes(output, 'libraries/' + str(index) + '_' + path.name, path.read_bytes())
        local_files['manifest'] = snapshot_bytes(output, 'capture_manifest.json', (Path(capture_directory) / 'manifest.json').read_bytes())
        identity.update(source_sha256=report['source_sha256'], libraries={str(p): sha(p.read_bytes()) for p in libraries},
            source_files=local_files, plans={name: asdict(plan) for name, plan, _, _ in plans},
            workspace_plans={name: asdict(ws) for name, _, _, ws in plans}, matrix_reset_count=1,
            raw_weight_layout='checkpoint[N,K] -> physical[K,N]; BF16 bytes only',
            native_intermediates_injected=False, native_trig_constants_used=True,
            norm_policy=TORCH_DEFAULT256_POLICY, qk_policy='PairHighFirst',
            production_chisel_policies_wired=False, production_command128_executed=False,
            software_runtime=dict(python=sys.version, executable=sys.executable,
                executable_sha256=sha(Path(sys.executable).read_bytes()), numpy=np.__version__, machine=platform.machine()))
        report['identity'] = identity; persist(output / 'identity.json', identity)
        initial = (matrix.resource_address, vector.resource_address, id(memory), id(scalar), id(dense), id(dense.a_banks),
                   id(dense.b_banks), id(rms), id(norm), id(rope), id(kv_owner), id(gqa), id(elementwise), matrix.epoch)
        all_actual, all_norms, all_observed = {}, {}, {}
        for index, (name, plan, active_outputs, workspace) in enumerate(plans):
            require(matrix.owner is None and vector.client is None and scalar.client is None and memory.pending is None,
                    'shared resources not drained at complete-block boundary')
            dense.workspace = workspace
            active_name = name
            observed = FullObservations(rows, (index + 1) * rows)
            recorders = {role: ObservationRecorder(rows, heads, kind) for role, heads, kind in
                         (('q_norm', 8, 'norm'), ('k_norm', 2, 'norm'), ('q_rope', 8, 'rope'), ('k_rope', 2, 'rope'))}
            norms = {role: value.events for role, value in recorders.items()}
            callbacks.update(plan=plan, full=observed, norm=recorders,
                             sigmoid=observed.activation_callback('sigmoid'), silu=observed.activation_callback('silu'))
            prefix = L3ProjectionCoordinator(memory=memory, dense=dense, matrix=matrix, vector=vector,
                                             rms_owner=rms, plan=plan.norm_rope.projection)
            nr = L3NormRopeCoordinator(prefix=prefix, norm_owner=norm, rope_owner=rope, plan=plan.norm_rope)
            coordinator = L3FullBlockCoordinator(prefix=nr, kv_owner=kv_owner, gqa_owner=gqa,
                                                 elementwise_owner=elementwise, fence=fence, plan=plan)
            window_start, stage_start, last_progress, recorded = time.monotonic(), time.monotonic(), time.monotonic(), 0
            before = asdict(fence.state)
            fma_before = (int(matrix.lib.matrix_dense_fmas()), int(matrix.lib.matrix_normal_fmas()))
            coordinator.start()
            stage_timings = []
            while coordinator.response is None:
                require(time.monotonic() - started < budget_seconds, 'complete software wall budget exceeded')
                coordinator.tick()
                now = time.monotonic()
                if now - last_progress >= 10:
                    progress = dict(window=name, seconds=now - started, active=active_state(coordinator))
                    persist(output / 'live_progress.json', progress); print(json.dumps(progress), flush=True); last_progress = now
                if len(coordinator.commands) != recorded:
                    require(len(coordinator.commands) == recorded + 1, 'one real command terminal at a time')
                    command = coordinator.commands[-1]; role = command['role']
                    target_role = {'gqa': 'context', 'sigmoid_mul': 'gated_context'}.get(role, role)
                    targets = ('cache_k', 'cache_v') if role == 'kv_append' else ('q_norm', 'raw_gate') if role == 'q_norm' else (target_role,)
                    for target in targets:
                        region = memory.regions[active_outputs[target]]
                        item = snapshot_bytes(output, name + '.' + target + '.actual.bf16le', region.raw())
                        item.update(published=region.published, written_beats=len(region.written), acknowledged_beats=len(region.acknowledged))
                        report['actual_outputs'][name + '.' + target] = item
                    stage_timings.append(dict(role=role, seconds=now - stage_start)); stage_start = now
                    recorded += 1
                    progress = dict(window=name, seconds=now - started, active=active_state(coordinator),
                                    stage_timings=stage_timings, actual_outputs=report['actual_outputs'])
                    persist(output / 'progress.json', progress)
                    print(json.dumps(dict(window=name, terminal=role, seconds=now - started)), flush=True)
            receipt = coordinator.report()
            receipt.update(name=name, elapsed_seconds=time.monotonic() - window_start,
                           stage_timings=stage_timings, roots_before=before, roots_after=asdict(fence.state))
            fma_after = (int(matrix.lib.matrix_dense_fmas()), int(matrix.lib.matrix_normal_fmas()))
            receipt['matrix_software_fma_calls'] = dict(dense=fma_after[0] - fma_before[0],
                normal_qk_pv=fma_after[1] - fma_before[1], total=sum(fma_after) - sum(fma_before),
                before=list(fma_before), after=list(fma_after), scope='actual shared C++ recipe FMA call counters; not hardware cycles or useful MAC utilization')
            report['windows'].append(receipt); persist(output / (name + '.terminal.json'), receipt)
            require(coordinator.response.status is None and len(coordinator.commands) == len(ORDER), 'complete block owner failure')
            require(fence.state.generation == index + 1 and fence.state.valid_tokens == (index + 1) * rows
                    and fence.state.k_root == plan.staging_k, 'actual final residual/KV fence did not commit')
            require(initial == (matrix.resource_address, vector.resource_address, id(memory), id(scalar), id(dense),
                id(dense.a_banks), id(dense.b_banks), id(rms), id(norm), id(rope), id(kv_owner), id(gqa), id(elementwise), matrix.epoch),
                'shared resource identity or reset epoch changed')
            report['observations'][name] = save_observations(output, name, norms, observed)
            all_actual[name] = {role: memory.regions[base].raw() for role, base in active_outputs.items()}
            all_norms[name], all_observed[name] = norms, observed
        report.update(status='ACTUAL_COMPLETE_UNCOMPARED', full_block_executed=True,
                      carried_window_executed=not cold_only,
                      terminal_count=sum(len(w['commands']) for w in report['windows']),
                      roots=asdict(fence.state), elapsed_seconds=time.monotonic() - started)
        persist(output / 'actual_terminal.json', report)
        comparisons = compare_selected_windows(selected_cases, manifest, capture_directory, output,
            all_actual, all_norms, all_observed, started=started, budget_seconds=budget_seconds)
        report['comparisons'] = comparisons
        require_loaded_source_closure()
        report['seals'] = dict(source=all((ROOT / p).read_bytes() == raw for p, raw in sources.items()),
            libraries=all(sha(Path(p).read_bytes()) == h for p, h in identity['libraries'].items()),
            capture_manifest=sha((Path(capture_directory) / 'manifest.json').read_bytes()) == identity['capture_manifest_sha256'],
            outputs=all(sha((output / r['file']).read_bytes()) == r['sha256'] for r in report['actual_outputs'].values()))
        require(time.monotonic() - started < budget_seconds, 'final sealing software wall budget exceeded')
        passed = all(report['seals'].values()) and all(c['all_computed_stages_pass'] for c in comparisons.values())
        success = 'PASS_COLD_CHAIN_COMPUTED_GATES_ONLY' if cold_only else 'PASS_COMPLETE_CHAIN_COMPUTED_GATES_ONLY'
        report.update(status=success if passed else 'FAILED_NATIVE_OR_IDENTITY_GATE',
                      elapsed_seconds=time.monotonic() - started)
        persist(output / 'summary.json', report)
        return report
    except BaseException as error:
        report.update(status='FAILED', elapsed_seconds=time.monotonic() - started,
                      error=dict(type=type(error).__name__, message=str(error)), traceback=traceback.format_exc(),
                      evidence_preservation_errors=[])
        try: report['active_at_failure'] = active_state(coordinator)
        except BaseException as extra_error: report['evidence_preservation_errors'].append(str(extra_error))
        if coordinator is not None:
            try: persist(output / 'failure_coordinator.json', coordinator.report())
            except BaseException as extra_error: report['evidence_preservation_errors'].append(str(extra_error))
        if observed is not None:
            try: report['failure_observations'] = save_observations(output, active_name, norms, observed, partial=True)
            except BaseException as extra_error: report['evidence_preservation_errors'].append(str(extra_error))
        if memory is not None and active_outputs is not None:
            for role, base in active_outputs.items():
                try:
                    region = memory.regions[base]
                    item = snapshot_bytes(output, 'failure_staging/' + role + '.partial.bf16le', region.raw())
                    item.update(published=region.published, written_beats=len(region.written), acknowledged_beats=len(region.acknowledged))
                    report.setdefault('failure_staging', {})[role] = item
                except BaseException as extra_error: report['evidence_preservation_errors'].append(str(extra_error))
        persist(output / 'summary.json', report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'payload', 'out'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--budget-seconds', type=int, required=True)
    parser.add_argument('--cold-only', action='store_true',
                        help='Run/compare only cold; still verify the complete two-window capture seal')
    args = parser.parse_args()
    report = run(args.capture, args.payload, args.out, budget_seconds=args.budget_seconds,
                 windows=('cold',) if args.cold_only else ('cold', 'carried'))
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds', 'terminal_count')}))
    raise SystemExit(0 if report['status'] in ('PASS_COMPLETE_CHAIN_COMPUTED_GATES_ONLY',
                                            'PASS_COLD_CHAIN_COMPUTED_GATES_ONLY') else 1)


if __name__ == '__main__': main()
