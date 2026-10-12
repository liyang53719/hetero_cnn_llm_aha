"""Run actual shared-resource L3 projection prefixes from verified raw hidden.

Existing compiled Matrix/Vector libraries only; no build, Torch or official
forward. Native reference tensors are compared only after actual completion.
"""
import argparse
import ctypes as C
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from . import input_fixture as fixture
from .projection_driver import L3ProjectionCoordinator, L3ProjectionPlan, ORDER
from ..qwen35_gdn_prefill import typed_dense as d, rms_owner as rms, projection_driver as projection
from ..qwen35_gdn_prefill.projection_owner import GdnProjectionOwner, PrefixWorkspace
from ..qwen35_gdn_prefill.chunk.vector import Vector16, IEEE_POLICY
from ..qwen2_resident_matrix.ffn_attention.matrix_service import configure_library

ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = tuple(dict.fromkeys((*projection.SOURCE_FILES,
    'candidates/qwen35_attention_prefill/projection_driver.py',
    'candidates/qwen35_attention_prefill/input_fixture.py',
    'candidates/qwen35_attention_prefill/run_projection_prefix.py',
    'candidates/qwen35_attention_prefill/native/capture.py',
    'candidates/qwen35_gdn_prefill/prefill_bf16_compare.py',
    'src/heteronpu/pinned_block_payload.py',
    'config/upstream/qwen3_5_0p8b/layer3_payload_pin.json',
    'config/upstream/qwen3_5_0p8b/layer3_bf16_contract.json',
    'candidates/qwen2_resident_matrix/ffn_attention/matrix_numeric.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
    'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp',
    'scripts/build_shared_matrix_recipe.py', rms.SCALAR_SOURCE, rms.OWNER_SOURCE)))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def persist(path, value):
    raw = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b'\n'
    with Path(path).open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def snapshot_bytes(output, filename, raw):
    path = output / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return dict(file=filename, bytes=len(raw), sha256=sha(raw))


def active_state(coordinator):
    if coordinator is None:
        return None
    driver = coordinator.active
    owner = None if driver is None else driver.owner
    return dict(role=coordinator.role, software_ticks=coordinator.ticks,
        completed_commands=len(coordinator.commands), fullprefix_terminal=coordinator.response is not None,
        owner_state=None if owner is None else getattr(owner, 'state', None),
        driver_counts=None if driver is None else dict(driver.counts),
        matrix_epoch=coordinator.matrix.epoch, matrix_reset_required=coordinator.matrix.reset_required,
        transport_write_pending=coordinator.memory.pending is not None,
        aborted=coordinator.aborted, locked=coordinator.locked)


def preserve_failure(report, output, coordinator):
    report['active_at_failure'] = None
    if coordinator is None:
        return
    report['partial_staging'] = {}
    report['evidence_preservation_errors'] = []
    try:
        report['active_at_failure'] = active_state(coordinator)
    except Exception as error:
        report['evidence_preservation_errors'].append(dict(role='active_state',type=type(error).__name__,message=str(error)))
    for role in ORDER:
        try:
            region = coordinator.memory.regions[getattr(coordinator.plan, role)]
            item = snapshot_bytes(output, 'failure_staging/' + role + '.partial.bf16le', region.raw())
            item.update(published=region.published, written_beats=len(region.written),
                        acknowledged_beats=len(region.acknowledged), complete_or_accepted=False)
            report['partial_staging'][role] = item
        except Exception as error:
            report['evidence_preservation_errors'].append(dict(role=role,type=type(error).__name__,message=str(error)))
    try:
        persist(output / 'failure_coordinator.json', coordinator.report())
    except Exception as error:
        report['evidence_preservation_errors'].append(dict(role='coordinator_report',type=type(error).__name__,message=str(error)))


def run(capture_directory, payload_directory, output, *, budget_seconds=300):
    output = Path(output)
    fixture.require(not output.exists() and type(budget_seconds) is int and 0 < budget_seconds <= 900,
                    'fresh output and explicit software wall budget 1..900 required')
    output.mkdir(parents=True)
    start, coordinator, memory = time.monotonic(), None, None
    source_bytes = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
    sources = {name: sha(raw) for name, raw in source_bytes.items()}
    (output / 'source_snapshot').mkdir()
    for name in sources:
        path = output / 'source_snapshot' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source_bytes[name])
    report = dict(status='RUNNING', scope='ACTUAL_TYPED_L3_RMS_QKV_PREFIX_ONLY',
        source_sha256=sources, budget_seconds=budget_seconds, windows=[], actual_outputs={},
        rtl_executed=False, public_command128_executed=False, full_block_executed=False,
        hardware_cycles=None, hardware_mac_utilization=None)
    persist(output / 'summary.json', report)
    try:
        manifest, weights, inputs, identity = fixture.load_fixture(capture_directory, payload_directory)
        library = d.library_from_environment(ROOT)
        vector = Vector16(os.environ['GDN_VECTOR16_LIBRARY'], exception_policy=IEEE_POLICY)
        lib = configure_library(C.CDLL(str(library)))
        fixture.require(lib.td_reset() == 0, 'one initial Matrix reset')
        matrix, memory, scalar = d.MatrixService(lib), d.TypedMemory(), rms.SharedScalar()
        norm = rms.RmsOwner(scalar)
        address = 0x100000
        def allocate(extent, raw=None):
            nonlocal address
            base = address
            address += extent + 64
            memory.add_readonly(base, raw) if raw is not None else memory.allocate_output(base, extent)
            return base
        parameters = {}
        for role, raw in weights.items():
            if role != 'input_norm':
                raw = np.frombuffer(raw, '<u2').reshape(fixture.WIDTHS[role], 1024).T.copy().tobytes()
            parameters[role] = allocate(len(raw), raw)
        plans = []
        rows = identity['rows']
        for index, (name, hidden) in enumerate(inputs.items()):
            addresses = {role: allocate(rows * width * 2) for role, width in fixture.WIDTHS.items()}
            plan = L3ProjectionPlan(tokens=rows, hidden=allocate(len(hidden), hidden),
                input_weight=parameters['input_norm'], packed_q_gate_weight=parameters['packed_q_gate'],
                k_weight=parameters['k'], v_weight=parameters['v'], tag_base=1 + index * 4, **addresses)
            plans.append((name, plan))
        workspace = PrefixWorkspace(allocate(16384), 16384, 1)
        owner = GdnProjectionOwner(workspace)
        coordinators = [(name, L3ProjectionCoordinator(memory=memory, dense=owner, matrix=matrix,
            vector=vector, rms_owner=norm, plan=plan)) for name, plan in plans]
        library_paths = (library, Path(os.environ['MATRIX_SERVICE_COMPILE_RECEIPT']), vector.library,
                         vector.library.with_suffix('.json'))
        identity.update(source_sha256=sources, libraries={str(p): sha(p.read_bytes()) for p in library_paths},
            plans={name: asdict(plan) for name, plan in plans},
            actual_resource_reused_between_windows=True, matrix_reset_count=1,
            raw_weight_layout='checkpoint[N,K] -> physical[K,N] bytes only',
            packed_q_gate_layout='[M,8,query256_then_gate256]',
            rms_implementation=rms.source_identity(rms.ReductionPolicy.Torch210CpuDefault1024))
        snapshots = {}
        for name, raw in inputs.items():
            snapshots['input:' + name] = snapshot_bytes(output, 'raw_inputs/' + name + '.bf16le', raw)
        for role, raw in weights.items():
            snapshots['weight:' + role] = snapshot_bytes(output, 'raw_weights/' + role + '.bf16le', raw)
        for index, path in enumerate(library_paths):
            snapshots['library:' + str(path)] = snapshot_bytes(output, 'libraries/' + str(index) + '_' + path.name,
                                                             path.read_bytes())
        snapshots['capture_manifest'] = snapshot_bytes(output, 'capture_manifest.json',
                                                      (Path(capture_directory) / 'manifest.json').read_bytes())
        identity['local_snapshot_files'] = snapshots
        report['identity'] = identity
        persist(output / 'identity.json', identity)
        resource = (matrix.resource_address, vector.resource_address, id(owner), id(owner.a_banks),
                    id(owner.b_banks), id(owner.tiles.banks), id(norm), id(scalar), id(memory), matrix.epoch)
        for name, coordinator in coordinators:
            window_start, recorded = time.monotonic(), 0
            coordinator.start()
            while coordinator.response is None:
                fixture.require(time.monotonic() - start < budget_seconds, 'software wall budget exceeded')
                coordinator.tick()
                if coordinator.ticks % 8192 == 0:
                    persist(output / 'live_progress.json', dict(window=name,
                        elapsed_seconds=time.monotonic()-start, active=active_state(coordinator)))
                if len(coordinator.commands) != recorded:
                    command = coordinator.commands[-1]
                    role = command['role']
                    raw = memory.regions[getattr(coordinator.plan, role)].raw()
                    filename = name + '.' + role + '.actual.bf16le'
                    with (output / filename).open('wb') as stream:
                        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                    report['actual_outputs'][filename] = dict(bytes=len(raw), sha256=sha(raw),
                        owner_terminal_status=command['terminal_status'])
                    recorded = len(coordinator.commands)
                    persist(output / 'progress.json', dict(window=name, elapsed_seconds=time.monotonic()-start,
                        actual_outputs=report['actual_outputs'], coordinator=coordinator.report()))
            receipt = coordinator.report()
            receipt['name'], receipt['elapsed_seconds'] = name, time.monotonic() - window_start
            report['windows'].append(receipt)
            persist(output / (name + '.terminal.json'), receipt)
            fixture.require(coordinator.response.status is None, 'actual owner failed: ' + str(coordinator.response))
            fixture.require(resource == (matrix.resource_address, vector.resource_address, id(owner), id(owner.a_banks),
                id(owner.b_banks), id(owner.tiles.banks), id(norm), id(scalar), id(memory), matrix.epoch),
                'shared resources changed between windows')
        report.update(status='ACTUAL_COMPLETE_UNCOMPARED', elapsed_seconds=time.monotonic()-start,
                      terminal_count=sum(len(x['commands']) for x in report['windows']))
        persist(output / 'actual_terminal.json', report)
        # Only post-execution comparison can open native intermediates.
        from ..qwen35_gdn_prefill.prefill_bf16_compare import compare_finite_bf16
        contract_raw = (ROOT / fixture.capture.CONTRACT).read_bytes()
        fixture.require(sha(contract_raw) == fixture.capture.CONTRACT_SHA256, 'original operator contract drift')
        thresholds = json.loads(contract_raw)['thresholds']['operator']
        gates = {}
        for case in identity['selections']:
            for role, key in case['references'].items():
                actual = (output / (case['name'] + '.' + role + '.actual.bf16le')).read_bytes()
                native = fixture.read_tensor(capture_directory, manifest, key)
                result = compare_finite_bf16(actual, native)
                result.update(thresholds=thresholds, passed=result['max_abs'] <= thresholds['max_abs'] and
                              result['mean_abs'] <= thresholds['mean_abs'])
                gates[case['name'] + '.' + role] = result
        report['gates'] = gates
        report['source_unchanged'] = sources == {name: sha((ROOT / name).read_bytes()) for name in sources}
        report['source_snapshots_unchanged'] = all(sha((output/'source_snapshot'/name).read_bytes()) == h
                                                  for name,h in sources.items())
        report['libraries_unchanged'] = all(sha(Path(p).read_bytes()) == h for p, h in identity['libraries'].items())
        report['capture_manifest_unchanged'] = sha((Path(capture_directory) / 'manifest.json').read_bytes()) == identity['capture_manifest_sha256']
        report['actual_outputs_unchanged'] = all(len((output/name).read_bytes()) == item['bytes'] and
            sha((output/name).read_bytes()) == item['sha256'] for name,item in report['actual_outputs'].items())
        report['snapshots_unchanged'] = all(len((output/item['file']).read_bytes()) == item['bytes'] and
            sha((output/item['file']).read_bytes()) == item['sha256'] for item in snapshots.values())
        valid = all(report[k] for k in ('source_unchanged', 'source_snapshots_unchanged', 'libraries_unchanged', 'capture_manifest_unchanged',
                                       'actual_outputs_unchanged', 'snapshots_unchanged'))
        report['status'] = 'PASS_ACTUAL_TYPED_PROJECTION_PREFIX_ONLY' if valid and all(g['passed'] for g in gates.values()) else 'FAILED'
        report['elapsed_seconds'] = time.monotonic() - start
        persist(output / 'summary.json', report)
        return report
    except BaseException as error:
        report.update(status='FAILED', elapsed_seconds=time.monotonic()-start,
                      error=dict(type=type(error).__name__, message=str(error)))
        preserve_failure(report, output, coordinator)
        persist(output / 'summary.json', report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--budget-seconds', type=int, default=300)
    args = parser.parse_args()
    report = run(args.capture, args.payload, args.out, budget_seconds=args.budget_seconds)
    print(json.dumps({k: report[k] for k in ('status', 'elapsed_seconds', 'terminal_count')}))
    raise SystemExit(0 if report['status'].startswith('PASS_') else 1)


if __name__ == '__main__':
    main()
