"""Fresh native recipe producers; Public owners never consume their arrays.

Native phases only verify existing libraries. The supervisor must call the
separate compiler function with its timer disarmed, so compiler cleanup has one
owner. All original stage, export and semantic gates remain in the frozen helper.
"""
import hashlib
import os
from pathlib import Path
import signal
import tempfile
import time

from ..raw_kv_native_qk_run import phase
from ..raw_kv_native_qk import kernel
from ..raw_kv_native_qkv import kernel as qkv_kernel
from ..raw_kv_public_recipe_profile import dispatch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = 'candidates/qwen2_resident_matrix/raw_kv_public_recipe_runtime/producer.py'
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
GENERATED_SHA256 = 'd7bd12077675984ed7cc20e57a55729fd62e66b773008fa631673086a5a87a64'
CAPS = {16: 60, 128: 120, 'kernel': 30}
ROLES = {16: 'native_m16', 128: 'native'}


def need(ok):
    if not ok:
        raise ValueError('Public recipe producer contract')


def _remaining(context, end_ns, reserve=6):
    from . import runtime
    runtime.remaining(context, 1)
    if min(end_ns, context['work_deadline_ns']) - time.monotonic_ns() <= reserve * 10**9:
        raise TimeoutError('Public recipe producer deadline')


def _checked(context, workspace, end_ns, kind):
    from . import runtime
    need(type(kind) is int and kind in (16, 128) or type(kind) is str and kind == 'kernel')
    need(type(end_ns) is int and type(context) is dict and
         type(context.get('work_deadline_ns')) is int and
         time.monotonic_ns() < end_ns <= context['work_deadline_ns'] and
         end_ns <= time.monotonic_ns() + CAPS[kind] * 10**9)
    workspace = kernel.safe_path(workspace, directory=True)
    again, found = runtime.read_context(workspace / 'context.json')
    need(found == workspace and phase.same(again, context))
    sources = runtime.source_snapshot()
    need(phase.same(context['source_sha256'], sources) and sources.get(SOURCE) == IMPORTED_SHA256 and
         sources.get(phase.SOURCE) == phase.IMPORTED_SHA256)
    need(kernel.digest(context['contract_sha256']) and context['generated_module_sha256'] == GENERATED_SHA256 and
         Path(context['generated_module']) == workspace / 'generated/qwen2_layer0_model_gate.py')
    _remaining(context, end_ns)
    return workspace, sources


def _libraries(workspace, sources):
    library = kernel.verify(workspace / 'qk_library')
    qkv_library = qkv_kernel.verify(workspace / 'qkv_library')
    need(all(sources.get(name) == identity for receipt in (library, qkv_library)
             for name, identity in receipt['source_sha256'].items()))
    return library, qkv_library


def _postflight(context, workspace, sources, end_ns, library, qkv_library):
    from . import runtime
    _remaining(context, end_ns)
    need(phase.same(runtime.source_snapshot(), sources))
    again, found = runtime.read_context(workspace / 'context.json')
    need(found == workspace and phase.same(again, context))
    need(kernel.sha(kernel.read(context['generated_module'], 1048576)) == GENERATED_SHA256)
    current, current_qkv = _libraries(workspace, sources)
    need(phase.same(current, library) and phase.same(current_qkv, qkv_library))
    _remaining(context, end_ns)


def _prepare_gate(context, workspace, sources):
    from ..raw_kv_native_qk import prepare
    from ..raw_kv_native_qk_run import runtime as frozen_native
    directory = workspace / 'generated'
    need(not directory.exists() and not directory.is_symlink())
    with tempfile.TemporaryDirectory(prefix='recipe_source_', dir=workspace) as temporary:
        stage = Path(temporary) / 'generated'
        prepared = prepare.prepare(stage)
        need(prepared['generated_module_sha256'] == frozen_native.INTERMEDIATE_GENERATED_MODULE_SHA256)
        frozen_native.apply_dispatch_patch(stage, {'sources': sources})
        raw = kernel.read(stage / kernel.ORIGINAL, 1048576)
        need(kernel.sha(raw) == GENERATED_SHA256)
        directory.mkdir()
        target = Path(context['generated_module'])
        with target.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    need(kernel.sha(kernel.read(target, 1048576)) == GENERATED_SHA256)


def build_libraries(context, workspace, end_ns):
    """Supervisor-only: both compiler groups share this same 30-second end."""
    need(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0))
    workspace, sources = _checked(context, workspace, end_ns, 'kernel')
    destination = workspace / 'phase_kernel.json'
    need(not destination.exists() and not destination.is_symlink())
    _prepare_gate(context, workspace, sources)
    _remaining(context, end_ns)
    qkv_library = qkv_kernel.build(workspace / 'qkv_library', execute=True, deadline_ns=end_ns - 10**9)
    _remaining(context, end_ns)
    library = kernel.build(workspace / 'qk_library', execute=True, deadline_ns=end_ns - 10**9)
    _postflight(context, workspace, sources, end_ns, library, qkv_library)
    report = phase.validate_kernel_report(dict(schema=1, status='COMPLETE_KERNEL_BUILD',
        numerical_execution=False, backend_order_proven=False,
        library_sha256=library['library_sha256'], library_receipt_sha256=library['receipt_sha256'],
        qkv_library_sha256=qkv_library['library_sha256'], qkv_library_receipt_sha256=qkv_library['receipt_sha256'],
        qkv_recipe_pins_sha256=qkv_library['pins_sha256'], recipe_pins_sha256=library['pins_sha256'],
        source_manifest_sha256=kernel.sha(kernel.encoded(sources)), contract_sha256=context['contract_sha256'],
        generated_module_sha256=GENERATED_SHA256))
    kernel._atomic(destination, report)
    _remaining(context, end_ns, 1)
    return report


def _shared(context, sources, library, qkv_library, payload_raw):
    from ..raw_kv_native_qk_run import dispatch_diagnostic
    payload = kernel.json_bytes(payload_raw, 1048576)
    tensor_hashes = dispatch_diagnostic.payload_hashes(payload)
    return dict(source_manifest_sha256=kernel.sha(kernel.encoded(sources)),
        contract_sha256=context['contract_sha256'], original_module_sha256=qkv_kernel.FIXED[kernel.ORIGINAL],
        generated_module_sha256=GENERATED_SHA256, library_sha256=library['library_sha256'],
        library_receipt_sha256=library['receipt_sha256'], recipe_pins_sha256=library['pins_sha256'],
        qkv_library_sha256=qkv_library['library_sha256'], qkv_library_receipt_sha256=qkv_library['receipt_sha256'],
        qkv_recipe_pins_sha256=qkv_library['pins_sha256'], payload_manifest_sha256=kernel.sha(payload_raw),
        payload_tensor_map_sha256=kernel.sha(kernel.encoded(tensor_hashes)))


def _case(workspace, tokens, shared):
    name = 'native' + str(tokens)
    report_raw = kernel.read(workspace / ('phase_' + name + '.json'), phase.MAX_REPORT)
    diagnostic_raw = kernel.read(workspace / ('phase_' + name + '_diagnostics.json'), phase.MAX_DIAGNOSTICS)
    report = phase.validate_report(kernel.json_bytes(report_raw, phase.MAX_REPORT))
    observation = phase.validate_diagnostics(kernel.json_bytes(diagnostic_raw, phase.MAX_DIAGNOSTICS))
    expected = dict(result_sha256=kernel.sha(kernel.read(workspace / ROLES[tokens] / 'RESULT.json', 1048576)),
        source_manifest_sha256=shared['source_manifest_sha256'], report_sha256=kernel.sha(report_raw),
        diagnostics_sha256=kernel.sha(diagnostic_raw))
    dispatch._case(report, observation, tokens, expected, shared)
    return report, observation, expected


def validate_pair(context, workspace, end_ns):
    """Rebind both private cases to current sources, libraries and payload bytes."""
    workspace, sources = _checked(context, workspace, end_ns, 128)
    library, qkv_library = _libraries(workspace, sources)
    payload_raw = kernel.read(workspace / 'payload/manifest.json', 1048576)
    shared = _shared(context, sources, library, qkv_library, payload_raw)
    small, small_observation, small_expected = _case(workspace, 16, shared)
    large, large_observation, large_expected = _case(workspace, 128, shared)
    trusted = dict(schema=1, profile=dispatch.PROFILE, shared=shared,
                   native16=small_expected, native128=large_expected)
    result = dispatch.validate_pair(small, small_observation, large, large_observation, context=trusted)
    for tokens in (16, 128):
        raw = kernel.read(workspace / ROLES[tokens] / 'RESULT.json', 1048576)
        expected = small_expected if tokens == 16 else large_expected
        need(kernel.sha(raw) == expected['result_sha256'])
        phase.verify_exports(kernel.json_bytes(raw, 1048576), workspace / ROLES[tokens], tokens)
    _postflight(context, workspace, sources, end_ns, library, qkv_library)
    need(kernel.read(workspace / 'payload/manifest.json', 1048576) == payload_raw)
    for tokens, expected in ((16, small_expected), (128, large_expected)):
        _, _, current = _case(workspace, tokens, shared)
        need(phase.same(current, expected))
    return result


def _failure(error, name, context, workspace, end_ns):
    """No exception text, paths, payloads or arbitrary child output is exported."""
    try:
        _remaining(context, end_ns, 1)
        from ..raw_kv_public_fresh import setup
        value = setup.safe_diagnostic(error, phase='preflight', sources=context['source_sha256'])
        setup.validate_diagnostic(value, 'preflight', context['source_sha256'])
        value['phase'] = name
        need(len(kernel.encoded(value)) <= 4096)
        path = workspace / ('producer_' + name + '.failure.json')
        need(not path.exists() and not path.is_symlink())
        kernel._atomic(path, value)
    except BaseException:
        pass


def run_native(context, workspace, end_ns, *, tokens):
    """One fresh size per child; success is only a native prerequisite."""
    need(type(tokens) is int and tokens in ROLES)
    workspace, sources = _checked(context, workspace, end_ns, tokens)
    name = 'native' + str(tokens)
    destination = workspace / ('phase_' + name + '.json')
    diagnostic_destination = workspace / ('phase_' + name + '_diagnostics.json')
    for path in (destination, diagnostic_destination, workspace / ROLES[tokens]):
        need(not path.exists() and not path.is_symlink())
    library, qkv_library = _libraries(workspace, sources)
    native = phase._generated(context['generated_module'], GENERATED_SHA256)
    from ..raw_kv_public_fresh import setup
    need(setup.IMPORTED_SETUP_SHA256 == sources.get('candidates/qwen2_resident_matrix/raw_kv_public_fresh/setup.py'))
    torch, backend_identity = setup.backend_identity()
    from ..raw_kv_native_qk_run import dispatch_capture as capture_module
    capture = capture_module.Capture(workspace / (name + '_dispatch'), torch)
    environment = dict(libraries=None, before_recipe=None, after_recipe=None, after_gate=None)
    backend = cpu = validated = None
    try:
        backend = phase.backend_build(backend_identity)
        cpu = phase.read_cpu_features()
        environment['libraries'] = capture_module.library_fenv(qkv_library['library_path'], library['library_path'])
        from ..raw_kv_native_qk.adapter import Recipe
        environment['before_recipe'] = capture_module.fenv_snapshot()
        try:
            recipe = Recipe(workspace / 'qkv_library', workspace / 'qk_library')
        finally:
            environment['after_recipe'] = capture_module.fenv_snapshot()
        recipe_identity = recipe.identity()
        need(phase.same(recipe_identity, phase.combined_identity(library, qkv_library)))
        payload_raw = kernel.read(workspace / 'payload/manifest.json', 1048576)
        small = small_sha = None
        if tokens == 128:
            shared = _shared(context, sources, library, qkv_library, payload_raw)
            prior, _, expected = _case(workspace, 16, shared)
            need(prior['m16_result_sha256'] is None)
            small = workspace / 'native_m16/RESULT.json'; small_sha = expected['result_sha256']
            phase.verify_exports(kernel.json_bytes(kernel.read(small, 1048576), 1048576), small.parent, 16)
        _remaining(context, end_ns)
        try:
            result = native.run_gate(ROOT, workspace / 'payload', workspace / ROLES[tokens], tokens,
                carried=False, threads=4, small_gate=small, qkv_recipe=recipe, diagnostics=capture)
        finally:
            environment['after_gate'] = capture_module.fenv_snapshot()
        setup.backend_threads(torch)
        _remaining(context, end_ns)
        raw = kernel.read(workspace / ROLES[tokens] / 'RESULT.json', 1048576)
        disk = kernel.json_bytes(raw, 1048576)
        need(phase.same(phase.canonical(result), disk))
        _, identity = native.runtime_identity(ROOT)
        identity['independent_qkv_recipe'] = recipe_identity
        need(phase.same(disk.get('identity'), identity))
        kwargs = dict(tokens=tokens, result_sha256=kernel.sha(raw), source_sha256=sources,
            contract_sha256=context['contract_sha256'], generated_module_sha256=GENERATED_SHA256,
            library=library, qkv_library=qkv_library, payload_manifest_sha256=kernel.sha(payload_raw),
            m16_result_sha256=small_sha)
        report = phase.project_result(disk, **kwargs)
        need(phase.same(phase.project_result(phase.canonical(result), **kwargs), report))
        phase.verify_exports(disk, workspace / ROLES[tokens], tokens)
        recipe.revalidate()
        need(kernel.read(workspace / 'payload/manifest.json', 1048576) == payload_raw and
             kernel.read(workspace / ROLES[tokens] / 'RESULT.json', 1048576) == raw)
        if small is not None:
            need(kernel.sha(kernel.read(small, 1048576)) == small_sha)
        _postflight(context, workspace, sources, end_ns, library, qkv_library)
        kernel._atomic(destination, report)
        validated = (disk, report, kernel.json_bytes(payload_raw, 1048576))
        observation = phase.diagnostic_record(context, tokens, library, qkv_library, capture.report(),
            cpu, backend, environment, validated)
        kernel._atomic(diagnostic_destination, observation)
        shared = _shared(context, sources, library, qkv_library, payload_raw)
        _case(workspace, tokens, shared)  # Strict ISA/fenv/completeness before the next shape.
        if tokens == 128:
            pair = validate_pair(context, workspace, end_ns)
            path = workspace / 'recipe_pair.json'
            need(not path.exists() and not path.is_symlink())
            kernel._atomic(path, pair)
        _remaining(context, end_ns, 1)
        return report
    except BaseException as error:
        try:
            _remaining(context, end_ns, 1)
            if not diagnostic_destination.exists() and not diagnostic_destination.is_symlink():
                observed = None
                try:
                    observed = capture.report()
                except BaseException:
                    pass
                observation = phase.diagnostic_record(context, tokens, library, qkv_library,
                    observed, cpu, backend, environment, validated)
                kernel._atomic(diagnostic_destination, observation)
        except BaseException:
            pass
        _failure(error, name, context, workspace, end_ns)
        raise


def manifest_extension(workspace):
    """Exact bounded file records; the assets verifier independently admits them."""
    workspace = kernel.safe_path(workspace, directory=True)
    def record(relative, limit):
        path = kernel.safe_path(workspace / relative)
        need(path.is_relative_to(workspace))
        raw = kernel.read(path, limit)
        return dict(path=relative, bytes=len(raw), sha256=kernel.sha(raw))
    return dict(
        generated_module=record('generated/qwen2_layer0_model_gate.py', 1048576),
        qk=dict(binary=record('qk_library/' + kernel.LIBRARY, 16*1024*1024),
                receipt=record('qk_library/' + kernel.RECEIPT, 131072)),
        qkv=dict(binary=record('qkv_library/' + qkv_kernel.LIBRARY, 16*1024*1024),
                 receipt=record('qkv_library/' + qkv_kernel.RECEIPT, 131072)),
        **{name:dict(report=record('phase_' + name + '.json', phase.MAX_REPORT),
                     diagnostics=record('phase_' + name + '_diagnostics.json', phase.MAX_DIAGNOSTICS))
           for name in ('native16', 'native128')})
