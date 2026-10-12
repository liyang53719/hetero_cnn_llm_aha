#!/usr/bin/env python3
"""Freeze, then capture actual raw public FFN4 commands through the Host model.

Preparation copies only source and public metadata, and does not compile or
read tensor payloads. Execution requires that exact snapshot hash. Only frozen
phase-9 n1 and the three official weights initialize numeric execution; saved
phase 10/11/12/13 and reference entry points stay blocked until the original
public terminal and final Down ACK have retired. No RTL/native acceptance.
"""
import argparse
from array import array
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import importlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
PUBLISHED_BASELINE = '812d858f8e33e1e6da0cac354846465e971aa975'
PRECISION_PATH = 'candidates/qwen2_resident_matrix/ffn_fullgroup/precision_pins.json'
PRECISION_SHA256 = 'fb6fc2ea116e708c7560f37144625a3b12d1ad93e4bc69178e8e8509ded5b0c0'
REVISED_BASELINE_SOURCES = {
    'candidates/qwen2_resident_matrix/ffn_group/model.py',
    'candidates/qwen2_resident_matrix/ffn_group/source_pins.json',
}
INTERFACE_REVISION_SOURCES = REVISED_BASELINE_SOURCES | {
    'candidates/qwen2_resident_matrix/ffn_fullgroup/down_driver.py',
    'candidates/qwen2_resident_matrix/ffn_group/group.patch',
}
RUNTIME_PREFIX = 'candidates.qwen2_resident_matrix.ffn_public'
_runtime = None
_import_hashes = None
_imported_python_paths = None

RUNTIME_MODULES = {
    'ffn_public': ('check_numeric', 'execute_numeric', 'fixture', 'model'),
    'ffn_fullgroup': ('check_numeric', 'down_driver'),
    'ffn_drain': ('check_numeric', 'model'),
    'ffn_window': ('check_numeric', 'model'),
    'ffn_tiles': ('check_numeric', 'model'),
    'ffn_group': ('model',),
    'transposed_down': ('model',),
}
ENCODER_MODULES = ('__init__', 'abi_validation', 'cgra_sfu', 'command', 'config',
                   'descriptor_chain', 'dtypes', 'gemmini_descriptor_v2',
                   'gemmini_rocc_lowering', 'kv_engine', 'matrix_engine', 'scheduler')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def python_dependency_paths():
    paths = {f'candidates/qwen2_resident_matrix/{directory}/{name}.py'
             for directory, names in RUNTIME_MODULES.items() for name in names}
    paths.update('src/heteronpu/' + name + '.py' for name in ENCODER_MODULES)
    return paths


def source_paths():
    """Strict execution and consumed-contract closure, never delivery receipts."""
    paths = python_dependency_paths()
    pins = json.loads((ROOT / PRECISION_PATH).read_text())
    paths.update(pins['sources'])
    paths.update('candidates/qwen2_resident_matrix/' + directory + '/precision_pins.json'
                 for directory in ('ffn_fullgroup', 'ffn_drain', 'ffn_window', 'ffn_tiles'))
    composition = json.loads((TASK.parent / 'ffn_group/source_pins.json').read_text())
    paths.update(composition['patches'])
    return sorted(paths)


def repository_source_path(filename):
    path = Path(filename).resolve()
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return None
    # A task-local Python environment is tooling, not this repository's
    # implementation. Keep every other in-repository import fail-closed.
    if path.is_relative_to(Path(sys.prefix).resolve()) and any(
            part in ('site-packages', 'dist-packages') for part in path.parts):
        return None
    return str(relative)


def host_tool_identity():
    third_party = {}
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if '.' not in name and filename and any(
                part in ('site-packages', 'dist-packages') for part in Path(filename).parts):
            third_party[name] = dict(version=str(getattr(module, '__version__', 'not exposed')),
                                     module_path=str(Path(filename).resolve()))
    return dict(python_executable=str(Path(sys.executable).resolve()), python_version=sys.version,
                python_prefix=str(Path(sys.prefix).resolve()), imported_third_party=third_party)


def imported_python_paths(modules):
    """Observe the dynamic helper modules as well as public encoder imports."""
    from types import ModuleType
    found, pending = set(), list(modules)
    pending.extend(module for name, module in sys.modules.items() if name == 'heteronpu' or name.startswith('heteronpu.'))
    while pending:
        module = pending.pop()
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        relative = repository_source_path(filename)
        if relative is None or relative in found:
            continue
        found.add(relative)
        pending.extend(value for value in vars(module).values() if isinstance(value, ModuleType))
    found.add(str(Path(__file__).resolve().relative_to(ROOT)))
    return found


def source_hashes():
    return {path: file_sha(ROOT / path) for path in source_paths()}


def runtime():
    """Record the file identity around imports, then reject later live drift."""
    global _runtime, _import_hashes, _imported_python_paths
    if _runtime is None:
        before = source_hashes()
        sys.path.insert(0, str(ROOT))
        execution = importlib.import_module(RUNTIME_PREFIX + '.execute_numeric')
        fixture = importlib.import_module(RUNTIME_PREFIX + '.fixture')
        frontend = importlib.import_module(RUNTIME_PREFIX + '.model')
        require(before == source_hashes(), 'source changed while loading public runtime')
        _runtime, _import_hashes = (execution, fixture, frontend), before
        _imported_python_paths = imported_python_paths(_runtime)
        require(_imported_python_paths == python_dependency_paths(),
                'actual imported Python dependency closure changed: ' +
                str(sorted(_imported_python_paths.symmetric_difference(python_dependency_paths()))))
    return _runtime


def load_precision_pins(numeric):
    require(file_sha(ROOT / PRECISION_PATH) == PRECISION_SHA256,
            'published arithmetic/input precision pins changed')
    pins = json.loads((ROOT / PRECISION_PATH).read_text())
    for path, digest in pins['sources'].items():
        if path not in REVISED_BASELINE_SOURCES:
            require(file_sha(ROOT / path) == digest, 'unchanged arithmetic/model source drift: ' + path)
    # The older drain pins cover the immutable arithmetic and physical models,
    # without asking the revised public Host to inherit its old source hash.
    numeric.drain_check.load_pins(check_provenance=False)
    return pins


def metadata_identity(fixture):
    fixture.config.validate()
    fixture.validate_spans()
    tables = {}
    for name in ('command', 'descriptor'):
        table = getattr(fixture.config, name)
        raw = bytes(fixture.memory.mappings[table.base])
        require(len(raw) == table.limit - table.base, 'metadata mapping/table extent differs')
        tables[name] = dict(**asdict(table), bytes=len(raw), sha256=sha(raw),
                            record_hex=[raw[i:i + 16].hex() for i in range(0, table.count * 16, 16)])
    require(set(fixture.memory.mappings) == {fixture.config.command.base, fixture.config.descriptor.base},
            'unexpected preloaded metadata mapping')
    return json.loads(encoded(dict(config=asdict(fixture.config), tables=tables,
                physical_spans=fixture.physical_spans(), scope=fixture.scope)))


def validate_layout(fixture, memory, owner):
    """Check the actual full data allocations, metadata and reserved workspace."""
    spans = list(memory.spans)
    for name in ('command', 'descriptor'):
        table = getattr(fixture.config, name)
        spans.append((table.base, table.limit, name + '_table'))
    for index, (base, limit, name) in enumerate(spans):
        require(base % 64 == limit % 64 == 0 and base < limit,
                'unaligned/empty full allocation: ' + name)
        for other_base, other_limit, other in spans[index + 1:]:
            require(limit <= other_base or other_limit <= base,
                    'metadata/data/workspace full spans alias: ' + name + ', ' + other)
    actual = {name: (base, limit) for base, limit, name in spans}
    require(len(actual) == len(spans), 'duplicate physical allocation name')
    expected = {name: (base, limit) for name, base, limit in fixture.physical_spans()}
    require(actual == expected, 'raw fixture and actual numeric allocation spans differ')
    region = fixture.config.regions[3]
    require(owner.workspace.base == region.base and owner.workspace.extent == region.limit - region.base and
            owner.workspace.generation == fixture.config.epoch + 1 and owner.workspace.split_k == 2560,
            'actual owner workspace differs from public launch')
    return spans


def prepare(out, rows=16, epoch=7, expected_head=PUBLISHED_BASELINE):
    """Create a new reviewable source/metadata snapshot; no numeric payload IO."""
    out = Path(out).resolve()
    require(not out.exists(), 'use a new source snapshot directory')
    require(rows in (16, 128), 'public capture rows must be 16 or 128')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(head == expected_head, 'expected execution checkout HEAD mismatch')
    execution, fixtures, _ = runtime()
    pins = load_precision_pins(execution.numeric)
    fixture = fixtures.make_ffn4_fixture(rows, epoch)
    metadata = metadata_identity(fixture)
    before = source_hashes()
    require(before == _import_hashes, 'source changed after runtime import')
    out.mkdir(parents=True)
    # Preserve the original snapshot machinery, then extend its dependency
    # closure with the actual public adapter, Host, encoder and source inputs.
    hashes, frozen = execution.numeric.freeze_sources(out, pins)
    for path, digest in before.items():
        raw = (ROOT / path).read_bytes()
        require(sha(raw) == digest, 'source changed during snapshot: ' + path)
        target = frozen / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[path] = digest
    require(all(hashes.get(path) == digest for path, digest in before.items()) and before == source_hashes(),
            'incomplete or changing source snapshot')
    inventory = {path: digest for path, digest in hashes.items() if path not in before}
    for name in ('command', 'descriptor'):
        table = getattr(fixture.config, name)
        (out / (name + '_table.bin')).write_bytes(fixture.memory.mappings[table.base])
    revisions = {}
    for path in sorted(INTERFACE_REVISION_SOURCES):
        old = subprocess.check_output(['git', 'show', PUBLISHED_BASELINE + ':' + path], cwd=ROOT)
        revisions[path] = dict(published_sha256=sha(old), snapshot_sha256=before[path])
    new_pins = dict(schema=1, scope='NEW_PUBLIC_FFN4_SNAPSHOT_ONLY',
        original_precision_pins_path=PRECISION_PATH, original_precision_pins_sha256=PRECISION_SHA256,
        model=pins['model'], revision=pins['revision'], layer=pins['layer'],
        unchanged_arithmetic_sources={path: digest for path, digest in pins['sources'].items()
                                     if path not in REVISED_BASELINE_SOURCES},
        explicit_interface_revisions=revisions, complete_execution_and_contract_sha256=before,
        public_metadata=metadata, predecessor_numeric_acceptance_inherited=False)
    (out / 'precision_pins.json').write_bytes(encoded(new_pins))
    snapshot = dict(schema=1, status='PREPARED_NOT_EXECUTED', rows=rows, epoch=epoch,
        host_tool_identity=host_tool_identity(),
        published_baseline_commit=PUBLISHED_BASELINE, execution_checkout_head=head,
        source_identity='Explicit new public-byte/Host snapshot; older 812d858 receipts remain unchanged and confer no PASS.',
        source_sha256=before, source_manifest_sha256=sha(encoded(before)),
        imported_python_sha256={path: before[path] for path in sorted(_imported_python_paths)},
        numeric_translation_units=['candidates/qwen2_resident_matrix/ffn_window/numeric_recipe.cpp',
                                   'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp'],
        compiled_include='candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
        frozen_inventory_only_sha256=inventory,
        inventory_scope='Additional predecessor source/test/receipt copies, not executed dependencies. Composed Scala postimages are described by source_pins; no current unrelated worktree source or Scala compilation is claimed.',
        changed_predecessor_sources=revisions, new_precision_pins_sha256=sha(encoded(new_pins)),
        precision_pins=pins, metadata=metadata, tensor_payloads_read=False,
        compilation_executed=False, public_execution_executed=False,
        native_m128_and_fp32_final_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
    path = out / 'SNAPSHOT.json'
    path.write_bytes(encoded(snapshot))
    return path, snapshot


def verify_snapshot(path, expected_sha256):
    path = Path(path).resolve()
    require(type(expected_sha256) is str and len(expected_sha256) == 64,
            'supply the reviewed SNAPSHOT.json SHA-256')
    require(file_sha(path) == expected_sha256, 'reviewed source snapshot hash mismatch')
    snapshot = json.loads(path.read_text())
    require(snapshot['status'] == 'PREPARED_NOT_EXECUTED' and not snapshot['tensor_payloads_read'] and
            not snapshot['compilation_executed'] and not snapshot['public_execution_executed'],
            'snapshot must be fresh unexecuted source/metadata preparation')
    require(snapshot['published_baseline_commit'] == PUBLISHED_BASELINE and
            snapshot['source_manifest_sha256'] == sha(encoded(snapshot['source_sha256'])),
            'snapshot source manifest identity mismatch')
    require(source_hashes() == snapshot['source_sha256'], 'live source differs from reviewed snapshot')
    for rel, digest in snapshot['source_sha256'].items():
        require(file_sha(path.parent / 'frozen_sources' / rel) == digest, 'frozen source changed: ' + rel)
    require(file_sha(path.parent / 'precision_pins.json') == snapshot['new_precision_pins_sha256'],
            'new public precision pins changed')
    for name, table in snapshot['metadata']['tables'].items():
        require(name in ('command', 'descriptor'), 'unexpected snapshot metadata table')
        raw = (path.parent / (name + '_table.bin')).read_bytes()
        require(len(raw) == table['bytes'] and sha(raw) == table['sha256'],
                'frozen metadata changed: ' + name)
    return snapshot


class ReferenceGate:
    """Refuse saved phase payload opens and reference calls before retirement."""
    def __init__(self, pins):
        self.paths = {(ROOT / entry['path']).resolve() for entry in pins['comparison_only'].values()}
        self.opened = False
        self.active = True

    def audit(self, event, args):
        if self.active and not self.opened and event == 'open' and isinstance(args[0], (str, bytes)):
            require(Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve() not in self.paths,
                    'saved comparison payload accessed before public final ACK/terminal')

    def library(self, lib):
        gate = self
        class GuardedLibrary:
            def __getattr__(self, name):
                require(gate.opened or name not in ('fw_reference', 'sf_reference', 'td_reference'),
                        'independent reference accessed before public final ACK/terminal')
                return getattr(lib, name)
        return GuardedLibrary()


@contextmanager
def reference_gate(pins):
    gate = ReferenceGate(pins)
    sys.addaudithook(gate.audit)
    try:
        yield gate
    finally:
        gate.active = False


def validate_terminal(evidence, memory, owner, outputs, rows):
    """The original reports and observed state jointly open the oracle gate."""
    host, coordinator, down = (evidence[key] for key in ('host', 'coordinator', 'down'))
    terminal = host['launch_result']
    require(evidence['full_ffn_host_model_executed'] and evidence['same_owner_and_banks'] and
            terminal is not None and terminal['status'] is None and terminal['completed'] == 4 and
            terminal['jobs'] == 2 and host['accepted']['result_fire'] == 1 and not host['reset_required'],
            'public terminal not successfully retired')
    completions = host['completions']
    require([item['pc'] for item in completions] == [0, 1, 2, 3] and
            all(item['status'] is None for item in completions) and
            host['accepted']['completion_fire'] == 4 and host['accepted']['owner_result_fire'] == 2,
            'all four public completions must retire before comparison')
    require(len(evidence['group']['windows']) == 56 and
            coordinator['accepted']['window_result_fire'] == 112 and
            coordinator['accepted']['drain_result_fire'] == 56 and
            coordinator['terminal']['status'] is None,
            'actual full56 coordinator terminals incomplete')
    require(down['completed'] and down['same_owner_and_banks'] and down['owner_resets'] == 0 and
            down['accepted']['response_handshakes'] == 1 and down['completion'][1] is None and
            not down['synthetic_geometry'], 'actual original Down terminal missing')
    fence, ddr = down['final_ack_fence'], down['ddr']
    require(fence['held_ticks'] > 0 and fence['final_ack_tick'] < fence['terminal_tick'] and
            fence['terminal_strictly_after_final_ack'] and down['completion'][2] == ddr['ack_bytes'] ==
            ddr['bytes'] == ddr['data_bytes'] == rows * 1536 * 4 and
            down['physical_traffic']['down_ack_bytes'] == ddr['ack_bytes'], 'Down final ACK fence incomplete')
    actual_act, act = memory.act.validate_full()
    require(actual_act == outputs['act'].tobytes() and sha(actual_act) == down['actual_act_source']['sha256'] and
            down['actual_act_source']['actual_prior_ack_written'] and
            coordinator['terminal']['write_bytes'] == act['ack_bytes'] and
            terminal['write_bytes'] == act['ack_bytes'] + ddr['ack_bytes'],
            'actual act-to-Down data/ACK continuity missing')
    require(owner.state == 'idle' and owner.lease is None and not owner.tiles.leased and
            not owner.ports()['reset_required'], 'owner not quiescent at comparison boundary')
    require(sha(outputs['down'].tobytes()) == ddr['sha256'], 'Down output differs from actual write receipt')
    return dict(public_completion_pcs=[item['pc'] for item in completions],
                launch_result=terminal, final_ack=fence, actual_act_sha256=sha(actual_act),
                all_actual_final_acks_and_terminals_before_comparison=True)


def metadata_observations(frontend):
    observed_bytes = sum(record['physical_bytes'] for record in frontend.port.trace)
    require(observed_bytes == len(frontend.memory.reads) * 64, 'metadata physical read record mismatch')
    return dict(physical_read_beats=len(frontend.memory.reads), physical_read_bytes=observed_bytes,
                counter_source='Accepted RecordReader physical transactions; no shared-arbiter latency or hardware-cycle claim.',
                command_reads=frontend.command_reads, policy_reads=frontend.policy_reads,
                typed_root_reads=frontend.reader.reads, physical_read_addresses=frontend.memory.reads,
                accepted_records=frontend.port.trace, record_reader_poison=frontend.port.machine.poison,
                model_ticks_are_hardware_cycles=False)


def load_inputs(numeric, pins, rows):
    inputs, loaded = {}, {}
    require(set(pins['inputs']) == {'n1', 'gate_weight', 'up_weight', 'down_weight'},
            'unexpected initial numeric payload')
    for name, spec in pins['inputs'].items():
        raw = numeric.drain_check.checked_file(spec)
        if name == 'n1':
            raw = raw[:rows * numeric.K * 4]
        inputs[name] = array('I' if name == 'n1' else 'H')
        inputs[name].frombytes(raw)
        loaded[name] = dict(bytes=len(raw), sha256=sha(raw), source_sha256=spec['sha256'])
    return inputs, loaded


def run(out, snapshot_path, expected_snapshot_sha256, wall_budget=900):
    out, snapshot_path = Path(out).resolve(), Path(snapshot_path).resolve()
    require(not out.exists(), 'use a new actual evidence directory')
    require(wall_budget > 0, 'positive capture wall budget required')
    snapshot = verify_snapshot(snapshot_path, expected_snapshot_sha256)
    execution, fixtures, public = runtime()
    require(_import_hashes == snapshot['source_sha256'], 'executed imports differ from reviewed snapshot')
    require(host_tool_identity() == snapshot['host_tool_identity'],
            'Python or imported third-party tooling differs from reviewed snapshot')
    numeric, rows = execution.numeric, snapshot['rows']
    pins = load_precision_pins(numeric)
    require(pins == snapshot['precision_pins'], 'snapshot precision pins differ')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(head == snapshot['execution_checkout_head'], 'checkout changed since snapshot')
    out.mkdir(parents=True)
    started, cpu_started = time.monotonic(), time.process_time()
    deadline = started + wall_budget
    report = dict(status='PREPARING', scope='RAW_PUBLIC_COMMAND128_FULL56_FFN_THEN_DOWN_HOST_MODEL_ONLY',
        rows=rows, epoch=snapshot['epoch'], execution_checkout_head=head,
        reviewed_snapshot_path=str(snapshot_path), reviewed_snapshot_sha256=expected_snapshot_sha256,
        source_sha256=snapshot['source_sha256'], pins=pins, host_tool_identity=snapshot['host_tool_identity'],
        row_scope=('Frozen M128 phase9_n1 rows 0:16; not an independent official 16-token forward.' if rows == 16
                   else 'All 128 frozen v0 phase9_n1 rows, official pinned weights and saved producer comparisons.'),
        rtl_executed=False, scala_host_executed=False, hardware_arithmetic_executed=False,
        actual_idma=False, official_framework_forward=False, full_block_executed=False,
        protocol_model_ticks_are_hardware_cycles=False, physical_resource_qor_established=False,
        native_m128_and_fp32_final_acceptance='UNCHANGED_FAIL_POLICY_PENDING',
        predicted_hardware_cycles=None, full_wall_utilization=None,
        budget=dict(wall_seconds=wall_budget, compile_timeout_seconds=30, no_rtl_or_eda=True))
    def save():
        (out / 'summary.json').write_bytes(encoded(report))
    try:
        require(sys.byteorder == 'little', 'little-endian host required')
        with reference_gate(pins) as gate:
            report['host_resources_before'] = numeric.drain_check.host_preflight()
            baseline = numeric.drain_check.load_pins()
            report['origin'] = numeric.window_check.verify_provenance(baseline)
            manifest = json.loads((ROOT / 'work/qwen2_layer0_payload_20261011/manifest.json').read_text())
            down_tensors = [t for t in manifest['tensors'] if t['local_name'] == 'mlp.down_proj.weight']
            require(len(down_tensors) == 1 and down_tensors[0]['shape'] == [1536, 8960] and
                    down_tensors[0]['dtype'] == 'BF16' and
                    down_tensors[0]['sha256'] == pins['inputs']['down_weight']['sha256'],
                    'official Down weight provenance/shape mismatch')
            fixture = fixtures.make_ffn4_fixture(rows, snapshot['epoch'])
            require(metadata_identity(fixture) == snapshot['metadata'], 'raw public fixture changed since snapshot')
            for name in ('command', 'descriptor'):
                table = getattr(fixture.config, name)
                raw = (snapshot_path.parent / (name + '_table.bin')).read_bytes()
                require(raw == bytes(fixture.memory.mappings[table.base]), 'frozen metadata bytes changed')
                (out / (name + '_table.bin')).write_bytes(raw)
            inputs, report['loaded_inputs'] = load_inputs(numeric, pins, rows)
            memory = numeric.Memory(inputs, rows)
            workspace = fixture.config.regions[3]
            owner = numeric.model.FfnDrainOwnerModel(numeric.model.PrefixWorkspace(workspace.base,
                workspace.limit - workspace.base, fixture.config.epoch + 1, 2560),
                enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
            report['source_memory'] = dict(spans=validate_layout(fixture, memory, owner),
                selection='physical address only; output-major official weights lazily viewed K-major',
                prelaunch_payloads=list(inputs), intermediate_prelaunch_payloads=[],
                n1_rows=rows, n1_allocation_note=('M16 maps only rows 0:16 (98,304 bytes), unlike the older decoded capture whole-M128 readonly allocation; the consumed first 16 rows are identical.' if rows == 16 else 'Whole frozen M128 readonly allocation.'),
                gate_up_act_down_prefix_initial='sentinel only',
                metadata_readonly=True, virtual_outputs=memory.check_virtual())
            report['metadata'] = snapshot['metadata']
            report['comparison_boundary'] = 'Saved phase10/11/12/13 opens and independent reference calls blocked until public final terminal plus all actual ACKs.'
            require(source_hashes() == snapshot['source_sha256'], 'source drift before numeric launch')
            report['status'] = 'PINNED_BEFORE_EXECUTION'
            save()
            (out / 'FROZEN_PINS.json').write_bytes(encoded(report))
            lib, report['compile'] = numeric.drain_check.build_library(out, pins, snapshot_path.parent / 'frozen_sources')
            numeric.configure_down_library(lib)
            frontend = public.PublicFrontend(fixture.memory, fixture.config)
            outputs, evidence = execution.execute_program(frontend, gate.library(lib), memory, owner, out, deadline)
            report['execution'] = evidence
            report['public_metadata_observations'] = metadata_observations(frontend)
            require(metadata_identity(fixture) == snapshot['metadata'], 'read-only metadata changed during capture')
            report['comparison_gate'] = validate_terminal(evidence, memory, owner, outputs, rows)
            require(source_hashes() == snapshot['source_sha256'], 'source drift during numeric execution')
            report['status'] = 'PUBLIC_DONE_COMPARISON_PENDING'
            save()
            gate.opened = True
            report['comparison'] = numeric.compare_after_terminal(pins, inputs, outputs, outputs['down'],
                                                                  gate.library(lib), rows, out, deadline)
            require(all(item['independent_direct_bit_mismatches'] == item['saved_producer_bit_mismatches'] == 0
                        for item in report['comparison'].values()), 'actual public FFN differs from direct/saved outputs')
            require(all(sha(raw.tobytes()) == report['loaded_inputs'][name]['sha256'] for name, raw in inputs.items()),
                    'actual initial numeric payload changed')
            report['source_sha256_after'] = source_hashes()
            require(report['source_sha256_after'] == snapshot['source_sha256'], 'source changed during comparison')
            report.update(status='PASS_ACTUAL_PUBLIC_FFN4_HOST_MODEL_ONLY', public_host_python_model_executed=True,
                full_ffn_host_model_executed=True, same_owner_and_banks_through_down=True,
                host_wall_seconds=time.monotonic() - started, host_cpu_seconds=time.process_time() - cpu_started,
                host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save()
            return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), host_wall_seconds=time.monotonic() - started,
                      host_cpu_seconds=time.process_time() - cpu_started)
        if 'frontend' in locals():
            report['public_metadata_observations'] = metadata_observations(frontend)
        if 'memory' in locals():
            report['failed_capture_act'] = dict(accepted_data_bytes=memory.act.data_bytes,
                accepted_ack_bytes=memory.act.ack_bytes, sha256=sha(memory.act.data), comparison_permitted=False)
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--rows', type=int, choices=(16, 128), default=16)
    parser.add_argument('--epoch', type=int, default=7)
    parser.add_argument('--expected-head', default=PUBLISHED_BASELINE)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--expected-snapshot-sha256')
    parser.add_argument('--wall-budget', type=int, default=900)
    args = parser.parse_args()
    if args.prepare_only:
        if args.snapshot or args.expected_snapshot_sha256:
            parser.error('preparation does not accept an execution snapshot')
        path, result = prepare(args.out, args.rows, args.epoch, args.expected_head)
        print(json.dumps(dict(status=result['status'], path=str(path), sha256=file_sha(path))))
    else:
        if not args.snapshot or not args.expected_snapshot_sha256:
            parser.error('execution requires --snapshot and --expected-snapshot-sha256')
        result = run(args.out, args.snapshot, args.expected_snapshot_sha256, args.wall_budget)
        print(json.dumps({key: result[key] for key in ('status', 'rows', 'host_wall_seconds', 'host_cpu_seconds')}))
