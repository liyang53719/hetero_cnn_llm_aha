"""One admitted metadata-only cold attempt, never a DUT numerical launcher.

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
from metadata_guard import MetadataOnlyGuard


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
    for path in sorted(owned.rglob('*')):
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


def late_definitions(config, components, out):
    cold, inventory, binding, policy, initialization, safe = components
    source = Path(config['source_root'])
    source_files = json.loads(Path(config['source_manifest']).read_text())['source_files']
    observer = Path(config['observer_root'])
    observer_files = {str(Path(p).relative_to(observer)): pin for p, pin in config['runtime_files'].items()
                      if Path(p).is_relative_to(observer)}
    buffer = Path(config['buffer_source'])
    runtime_observer = importlib.import_module('runtime_observer')
    # Invoke the exact later observer factory as a definition-only operation.
    # No Capture/Fields/ServiceTrace or owner object is constructed.
    previous_package = sys.modules.get('_qualified_runtime_observer')
    previous_monitor = sys.modules.get('_qualified_runtime_observer.monitor')
    previous_capture = sys.modules.get('_qualified_runtime_observer.capture')
    with binding.ProjectCodeGate(source, source_files) as source_gate, \
         binding.ProjectCodeGate(observer, observer_files) as observer_gate, \
         binding.ProjectCodeGate(buffer.parent, {buffer.name: config['runtime_files'][str(buffer)]}) as buffer_gate:
        monitor, base = runtime_observer.load_observer(config)
        capture = importlib.import_module('_qualified_runtime_observer.capture')
        for name in config['metadata_project_imports']:
            importlib.import_module(name)
    write_new(out / 'LATE_DEFINITIONS.json', dict(factory=runtime_observer.load_observer.__qualname__,
        factory_source=runtime_observer.__file__, monitor=monitor.__file__, buffer=base.__file__, capture=capture.__file__,
        source_exec_events=source_gate.events, observer_exec_events=observer_gate.events, buffer_exec_events=buffer_gate.events,
        package_recreated=sys.modules['_qualified_runtime_observer'] is not previous_package,
        monitor_reused=monitor is previous_monitor, capture_reused=capture is previous_capture,
        qualification='Actual factory invocation; cached monitor/capture may be reused and remain normally source-bound',
        task_objects_constructed=False, task_work_executed=False))


def execute(config, config_sha, out, cap):
    oracle = install_oracle(config, out)
    narrow = MetadataOnlyGuard(config)
    narrow.install_audit()
    from runtime_admission import normal_initialize, snapshot
    router = None; components = None; before = None; events = []; original_error = None
    stage = 'ORACLE_INSTALLED'; result = None; raw = {}; providers = {}; fixture = None
    try:
        runtime, router, components, before, events = normal_initialize(config, out, oracle)
        stage = 'NORMAL_QUALIFIED'
        narrow.enter_metadata()
        router.phase = 'METADATA_ONLY'
        oracle.require_clean(); router.require_clean()
        need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'oracle must remain SEALED')
        raw, providers = admit_providers(config, runtime, out)
        stage = 'PROVIDER14_IMMUTABLE_WRAPPED'
        late_definitions(config, components, out)
        stage = 'LATE_DEFINITIONS_QUALIFIED'
        source = Path(config['source_root'])
        source_files = json.loads(Path(config['source_manifest']).read_text())['source_files']
        owned = out / 'fixture_metadata'; owned.mkdir()
        binding = components[2]
        with binding.ProjectCodeGate(source, source_files) as metadata_code:
            fixture = runtime.fixtures.make_qwen2_21_fixture(config['profile']['rows'], config['profile']['epoch'],
                metadata_root=owned, metadata_parent=owned / 'metadata')
        write_new(out / 'METADATA_CODE_EVENTS.json', dict(events=metadata_code.events,
            dynamic_packer_loading=True, complete_source_code_attested=True))
        summary = persist_fixture(fixture, owned, out, config['profile']['rows'], config['profile']['epoch'])
        stage = 'PUBLIC21_METADATA_PERSISTED'
        for role, payload in raw.items():
            need(type(payload) is bytes and hashlib.sha256(payload).hexdigest() == config['providers'][role]['sha256'],
                 'retained immutable provider changed: ' + role)
        need(len(providers) == 14, 'all original wrappers retained')
        oracle.require_clean(); router.require_clean(); narrow.require_clean()
        need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'oracle opened unexpectedly')
        result = dict(status='PASS_M128_METADATA_COLD_ONLY', passed=True, metadata_persisted=True,
            provider_count=len(raw), provider_bytes=sum(map(len, raw.values())), commands=summary['commands'],
            descriptors=summary['descriptors'], observer_factory_rehearsed=True)
    except BaseException as exc:
        original_error = exc
        result = dict(status='FAIL', passed=False, stage=stage, error=dict(type=type(exc).__name__, detail=str(exc)))
    finally:
        profile_error = None; audit_error = None
        try: narrow.finish_profile()
        except BaseException as exc: profile_error = dict(type=type(exc).__name__, detail=str(exc))
        # Full raw modules/maps are persisted before each snapshot validation.
        # A final audit error never overwrites the original task exception.
        try:
            if components is not None:
                snapshot(config, out, 'METADATA_FINAL', components, before, events, native=False)
            else:
                cold = sys.modules.get('cold_import'); modules = dict(sys.modules)
                raw_modules = cold.raw_modules(modules) if cold is not None else [dict(name=name,
                    file=vars(module).get('__file__') if hasattr(module, '__dict__') else None) for name, module in modules.items()]
                write_new(out / 'FAILURE_MODULES_RAW.json', raw_modules)
                (out / 'FAILURE_MAPS_RAW.txt').write_text(Path('/proc/self/maps').read_text())
            oracle.require_clean(); narrow.require_clean()
            if router is not None: router.require_clean()
            need(oracle.state == 'SEALED' and not oracle.comparison_attempted, 'oracle must finish SEALED')
        except BaseException as exc: audit_error = dict(type=type(exc).__name__, detail=str(exc))
        if audit_error is not None or profile_error is not None:
            result.update(status='FAIL', passed=False, final_runtime_audit_error=audit_error, profile_error=profile_error)
        result.update(config_sha256=config_sha, run_id=cap['run_id'], oracle=oracle.report(),
            runtime_policy=None if router is None else router.report(), metadata_guard=narrow.report(),
            observed_domain_passed=False, full29_numeric_pass=False, hardware_acceptance=False,
            actual_terminal_verified=False, event_protocol_passed=False,
            execution_attribution='QUALIFIED_METADATA_ONLY' if result['passed'] else 'UNKNOWN_NOT_QUALIFIED',
            matrix_elf_loaded=False if result['passed'] else None,
            services_constructed=False if result['passed'] else None,
            owner_constructed=False if result['passed'] else None,
            resets_executed=False if result['passed'] else None,
            pc_arithmetic_executed=False if result['passed'] else None,
            oracle_values_read=False if result['passed'] else None, no_retry=True)
        write_new(out / 'WORKER_RESULT.json', result)
    if original_error is not None: raise original_error
    need(result['passed'], 'final metadata-only runtime qualification failed')
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
