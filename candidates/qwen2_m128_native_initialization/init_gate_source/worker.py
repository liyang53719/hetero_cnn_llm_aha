"""One admitted native constructor initialization, stopping before the first PC.

Imports of this wrapper use stdlib only. Actual target import/provider read/
fixture generation are possible only after the one-use parent capability.
"""
import argparse
import hashlib
import importlib
import json
import os
import sys
import types
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import need, file_id, write_new, write_payload
from init_state import inspect_state


def startup_inventory(out):
    targets = {}; vanished = []
    for name in os.listdir('/proc/self/fd'):
        try: targets[int(name)] = os.readlink('/proc/self/fd/' + name)
        except FileNotFoundError: vanished.append(int(name))
    maps = Path('/proc/self/maps').read_text()
    write_new(out / 'STARTUP_FDS_RAW.json', dict(fd_targets=targets, vanished_during_scan=vanished))
    (out / 'STARTUP_MAPS_RAW.txt').write_text(maps)
    return targets, maps


def install_oracle(config, out):
    # Unchanged exact oracle helper is the sole task-source bootstrap. Its
    # inherited FD/map inventory is persisted before validation and before any
    # runtime target import. Gate installation is never delayed to the fixture.
    root = Path(config['candidate_root'])
    for name in ('__init__.py', 'oracle_path_gate.py'):
        need(file_id(root / name) == config['runtime_files'][str(root / name)], 'oracle bootstrap source drift')
    sys.path.insert(0, str(root.parent))
    module = importlib.import_module('qwen2_ordered_fullgraph_entry.oracle_path_gate')
    need(Path(module.__file__).resolve() == root / 'oracle_path_gate.py', 'oracle gate source origin')
    gate = module.ExactOraclePathGate([config['oracle_root']], sorted(config['oracle_files']))
    fds, maps = startup_inventory(out)
    gate.install(fds, maps)
    gate.require_clean()
    write_new(out / 'ORACLE_ACTIVATION.json', dict(report=gate.report(),
        scope='Before all target imports and metadata initialization; unchanged exact root/inode/open/mmap guard',
        limits='Python audited open/mmap and inherited FD/maps, not a kernel sandbox or native syscall interception'))
    return gate


def immutable_provider(factory, record):
    read_codes = [code for code in factory.__code__.co_consts if type(code) is types.CodeType and code.co_name == 'read']
    need(len(read_codes) == 1, 'original bytes_provider nested read identity')
    payload = Path(record['path']).read_bytes()
    need(type(payload) is bytes and len(payload) == record['bytes'] and
         hashlib.sha256(payload).hexdigest() == record['sha256'], 'provider immutable identity')
    provider = factory(payload)
    need(type(provider) is types.FunctionType and provider.__code__ is read_codes[0] and
         provider.__globals__ is factory.__globals__ and provider.__closure__ is not None and
         any(cell.cell_contents is payload for cell in provider.__closure__), 'original immutable provider wrapper')
    return payload, provider


def admit_providers(config, runtime, out):
    need(len(config['providers']) == 14 and sum(r['bytes'] for r in config['providers'].values()) == 94916608,
         'exact 14-provider 94916608-byte scope')
    raw = {}; providers = {}; evidence = {}
    factory = runtime.base.bytes_provider
    for role, record in sorted(config['providers'].items()):
        payload, provider = immutable_provider(factory, record)
        raw[role] = payload
        providers[role] = provider
        evidence[role] = dict(path=record['path'], bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                              payload_type='bytes', factory_file=factory.__code__.co_filename,
                              wrapper_qualname=provider.__qualname__, wrapper_invoked=False)
    write_new(out / 'PROVIDER_ADMISSION.json', dict(providers=evidence, count=len(raw),
        total_bytes=sum(map(len, raw.values())), immutable_bytes=True, wrapped_original_factory=True,
        wrappers_read=False, oracle_not_read=True, raw13_not_supplied=True))
    return raw, providers


def plain(value):
    if value is None or type(value) in (bool, int, float, str): return value
    if isinstance(value, int): return int(value)
    if isinstance(value, (tuple, list)): return [plain(v) for v in value]
    if isinstance(value, (dict, types.MappingProxyType)): return {str(k): plain(v) for k, v in value.items()}
    if hasattr(value, '__dict__'): return {name: plain(v) for name, v in vars(value).items()}
    raise TypeError('unsupported metadata value: ' + type(value).__name__)


def persist_fixture(fixture, owned, out, rows, epoch):
    need(fixture.scope == 'QWEN2_21_METADATA_ONLY' and len(fixture.commands) == 21 and
         fixture.config.command.count == 21 and fixture.config.epoch == epoch and rows == 128,
         'actual public21 metadata shape/count/epoch')
    commands = b''.join(command.to_bytes() for command in fixture.commands)
    descriptors = b''.join(record.pack().to_bytes(16, 'little') for record in fixture.records)
    command_table = bytes(fixture.memory.mappings[fixture.config.command.base])
    descriptor_table = bytes(fixture.memory.mappings[fixture.config.descriptor.base])
    need(command_table[:len(commands)] == commands and descriptor_table[:len(descriptors)] == descriptors,
         'fixture objects preserve real public table bytes')
    need(hashlib.sha256(command_table).hexdigest() == fixture.provenance['command_sha256'] and
         hashlib.sha256(descriptor_table).hexdigest() == fixture.provenance['descriptor_sha256'],
         'actual metadata tables match unchanged provenance')
    table_ids = dict(commands=write_payload(out / 'ACTUAL_COMMAND_TABLE.bin', command_table),
                     descriptors=write_payload(out / 'ACTUAL_DESCRIPTOR_TABLE.bin', descriptor_table))
    retained = {}
    for path in sorted((owned / 'metadata').rglob('*')):
        need(not path.is_symlink(), 'metadata evidence symlink forbidden')
        if path.is_file(): retained[str(path.relative_to(owned))] = file_id(path)
    need(retained and any(name.endswith('fp32/host_commands.bin') for name in retained) and
         any(name.endswith('bf16/host_descriptors.bin') for name in retained), 'persistent original and converted metadata absent')
    summary = dict(rows=rows, epoch=epoch, scope=fixture.scope, commands=len(fixture.commands),
        descriptors=len(fixture.records), table_identities=table_ids, config=plain(fixture.config),
        command_records=plain(fixture.commands), descriptor_records=plain(fixture.records),
        roots=plain(fixture.roots), specs=plain(fixture.specs), allocations=plain(fixture.allocations),
        views=plain(fixture.views), manifest=plain(fixture.manifest), provenance=plain(fixture.provenance),
        generated_metadata=retained, metadata_parent=str(owned / 'metadata'),
        no_rmtree=True, numeric_payloads_generated=False, commands_executed=False)
    write_new(out / 'FIXTURE_METADATA.json', summary)
    return summary


def execute(config, config_sha, out, cap):
    oracle = install_oracle(config, out)
    from runtime_admission import normal_initialize, snapshot
    from native_binding import load_library
    router = None; components = None; before = None; events = []
    original_error = None; native = False; raw = {}; providers = {}; summary = None
    stage = 'ORACLE_INSTALLED'; result = None; checkpoints = []
    try:
        runtime, router, components, before, events = normal_initialize(config, out, oracle)
        stage = 'NORMAL_QUALIFIED'
        import tempfile
        need(Path(tempfile.gettempdir()).resolve() == out / 'tmp', 'fresh run metadata TMPDIR')
        closure = importlib.import_module('runtime_closure')
        closure.verify_graph(config['runtime_graph'], config['runtime_files'])
        library, identity = load_library(config, out)
        runtime.matrix.configure_library(library)
        runtime.library = library
        runtime.selected = runtime.dense.selected_library(library)
        native = True; stage = 'NATIVE_ABI_CONFIGURED'
        write_new(out / 'NATIVE_BINDING.json', identity)
        snapshot(config, out, 'NATIVE_LOADED', components, before, events, native=True)
        raw, providers = admit_providers(config, runtime, out)
        stage = 'PROVIDER14_IMMUTABLE_WRAPPED'
        profile = dict(config['profile']); profile['files'] = config['runtime_files']
        runner = importlib.import_module('qwen2_ordered_fullgraph_entry.runner')
        comparator = importlib.import_module('qwen2_ordered_fullgraph_entry.terminal_comparator')
        def terminal_guard():
            oracle.require_clean()
            need(oracle.state == 'COMPARING' and oracle.comparison_attempted,
                 'no terminal comparison window in initialization')
        compare = comparator.make_comparator(Path(config['oracle_root']) / 'capture',
            config['oracle_exports'], rows=128, terminal_guard=terminal_guard)
        need(callable(compare), 'original terminal comparator factory')
        write_new(out / 'COMPARATOR_FACTORY.json', dict(original_factory_constructed=True,
            closure_invoked=False, oracle_values_read=False, supplied_to_runner=False))
        def initialization_probe(**objects):
            nonlocal stage, summary
            after = objects['after_cleanup']
            name = 'INITIALIZATION_CLEANUP' if after else 'INITIALIZATION_ENTRY'
            stage = name + '_REACHED'
            need(checkpoints == ([False] if after else []), 'exact entry then cleanup checkpoint order')
            # Persist complete raw namespace/maps BEFORE qualification or state validation.
            snapshot(config, out, name, components, before, events, native=True)
            if not after:
                summary = persist_fixture(objects['fixture'], out / 'dut', out,
                    profile['rows'], profile['epoch'])
                write_new(out / 'SCALAR_SOURCE_IDENTITY.json', objects['scalar'].__dict__['identity'])
            oracle.require_clean(); router.require_clean()
            need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'oracle remained SEALED')
            try:
                state = inspect_state(providers=providers, **objects)
            except BaseException as exc:
                write_new(out / (name + '_ERROR.json'), dict(type=type(exc).__name__, detail=str(exc)))
                raise
            write_new(out / (name + '_STATE.json'), state)
            checkpoints.append(after); stage = name + '_QUALIFIED'
            return state
        admission = dict(initialization_authorized=True, execution_authorized=False,
            scope=config['scope'], source_manifest_sha256=config['source_manifest_sha256'],
            profile_sha256=config['profile_sha256'], elf_sha256=config['runtime_files'][config['elf']]['sha256'],
            runtime_manifest_sha256=config['runtime_manifest_sha256'],
            input_manifest_sha256=config['input_manifest_sha256'], run_id=cap['run_id'])
        stage = 'ORIGINAL_CONSTRUCTORS_RUNNING'
        actual, report = runner.run_actual(runtime, providers, profile, out / 'dut', enabled=True,
            admission=admission, compare_after_terminal=None, oracle_gate=oracle,
            initialization_only=True, initialization_probe=initialization_probe)
        need(actual is None and report['status'] == 'PASS_PRE_FIRST_PC_INITIALIZATION_ONLY' and
             report['first_pc_entered'] is False and checkpoints == [False, True],
             'exact initialized boundary and normal monitor cleanup required')
        for role, payload in raw.items():
            record = config['providers'][role]
            need(type(payload) is bytes and len(payload) == record['bytes'] and
                 hashlib.sha256(payload).hexdigest() == record['sha256'], 'provider postimage ' + role)
        need(summary is not None and len(summary['generated_metadata']) == 8,
             'exact eight retained metadata files')
        oracle.require_clean(); router.require_clean()
        need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'oracle finish SEALED')
        result = dict(status='PASS_PRE_FIRST_PC_INITIALIZATION_ONLY', passed=True,
            initialization_verified=True, monitor_cleanup_verified=True, first_pc_entered=False,
            metadata_persisted=True, provider_count=len(raw), provider_bytes=sum(map(len, raw.values())),
            commands=summary['commands'], descriptors=summary['descriptors'],
            fixed_scalar_environment_probes=5, environment_probes_are_not_user_tensor_work=True,
            oracle_comparator_factory_only=True, zero_task_counters_verified=True,
            workload_numerical_execution=False, additional_cleanup_reset_or_abort=False)
    except BaseException as exc:
        original_error = exc
        result = dict(status='FAIL', passed=False, stage=stage,
            error=dict(type=type(exc).__name__, detail=str(exc)))
    finally:
        audit_error = None
        try:
            if components is not None:
                snapshot(config, out, 'INITIALIZATION_FINAL', components, before, events, native=native)
            else:
                cold = sys.modules.get('cold_import'); modules = dict(sys.modules)
                raw_modules = cold.raw_modules(modules) if cold is not None else [dict(name=name,
                    file=vars(module).get('__file__') if hasattr(module, '__dict__') else None)
                    for name, module in modules.items()]
                write_new(out / 'FAILURE_MODULES_RAW.json', raw_modules)
                (out / 'FAILURE_MAPS_RAW.txt').write_text(Path('/proc/self/maps').read_text())
            oracle.require_clean()
            if router is not None: router.require_clean()
            need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'final oracle remained SEALED')
        except BaseException as exc:
            audit_error = dict(type=type(exc).__name__, detail=str(exc))
        if audit_error is not None:
            result.update(status='FAIL', passed=False, final_runtime_audit_error=audit_error)
        qualified = result['passed']
        result.update(config_sha256=config_sha, run_id=cap['run_id'], oracle=oracle.report(),
            runtime_policy=None if router is None else router.report(), reached_stage=stage,
            completed_checkpoints=checkpoints, observed_domain_passed=False, full29_numeric_pass=False,
            hardware_acceptance=False, actual_terminal_verified=False, event_protocol_passed=False,
            execution_attribution='QUALIFIED_PRE_FIRST_PC_INITIALIZATION_ONLY' if qualified else 'UNKNOWN_NOT_QUALIFIED',
            matrix_elf_loaded=True if qualified else None, services_constructed=True if qualified else None,
            owner_constructed=True if qualified else None, resets_executed=True if qualified else None,
            pc_arithmetic_executed=False if qualified else None,
            oracle_values_read=False if qualified else None, no_retry=True)
        write_new(out / 'WORKER_RESULT.json', result)
    if original_error is not None: raise original_error
    need(result['passed'], 'final pre-first-PC initialization qualification failed')
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ('config', 'config-sha', 'output', 'parent-start-ticks'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--cap-fd', type=int, required=True); parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    config_path = Path(args.config).resolve(); need(file_id(config_path)['sha256'] == args.config_sha, 'config hash')
    config = json.loads(config_path.read_text()); out = Path(args.output).resolve()
    from admission import claim
    cap = claim(args.cap_fd, config, args.config_sha, out, args.parent_pid, args.parent_start_ticks)
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize,
         'fixed worker interpreter flags')
    need(not any(key.startswith('LD_') for key in os.environ), 'loader overrides forbidden')
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        need(os.environ.get(key) == '1', 'single-thread environment ' + key)
    execute(config, args.config_sha, out, cap)

if __name__ == '__main__': main()
