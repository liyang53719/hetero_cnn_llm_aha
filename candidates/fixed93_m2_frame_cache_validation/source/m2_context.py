"""Inert source-only bridge for a separately admitted fresh success-M2 child.

Import performs no runtime/DUT/native/model/codec import or execution. The
caller source-pins F and this file, supplies the exact initialized 17-key runtime
context, and owns the one-shot root authority, total deadline and constructor
timing. This bridge does not call the original M128 authority/budget/factory,
any public advance, numerical step, input provider, reference, or fullblock seal.
The raw WholeblockObservation and original lazy M128 binding fixture are kept;
only the independent caller may subsequently submit the declared M2 owner job.
"""
import json
from pathlib import Path
import sys
import tempfile
import time
import types

_USED = False


def construct_m2_context(*, F, runtime_context, source_manifest, declaration,
                         library, out, trace_limits, attention_trace_limits,
                         root_guard, deadline, native_check, whole_module, verify_whole_module):
    """Construct once, after real M2 authority and one verified existing ELF load.

    native_check must be the parent's pinned callback that invokes the actual
    native_adapter._loaded_receipt, checks _LOADED and the original build/runtime
    pins, and returns (fresh receipt, exact ctypes.CDLL). No caller-supplied bool
    is accepted as native evidence. declaration['files'] contains the original
    baseline preparation specs plus its separately pinned SOURCE_MANIFEST.json.
    source_manifest is the parsed original baseline manifest, not an M128 grant.
    The parent first creates out/tmp and binds tempfile.tempdir to that directory.
    """
    global _USED
    root_guard('construct_m2_observers')
    need, checked = F.need, F.checked
    need(not _USED, 'M2 context factory is one-use in this fresh child')
    _USED = True  # No reconstruction retry after independently admitted entry.
    need(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12) and
         not sys.flags.optimize, 'pinned CPython3.12 unoptimized verification required')
    need(type(deadline) in (int, float) and time.monotonic() < deadline < float('inf'),
         'finite current M2 deadline required')
    HERE, SOURCE = F.HERE, F.SOURCE
    F.module_path(F, HERE / 'fullblock_runtime.py')
    checked(HERE / 'fullblock_runtime.py', declaration['files']['fullblock_runtime.py'])
    out = Path(out)
    need(out.is_absolute() and out.resolve() == out and out.is_dir() and
         not any(p.is_symlink() for p in (out, *out.parents)), 'fresh absolute M2 output required')
    need(tempfile.tempdir == str(out / 'tmp') and (out / 'tmp').is_dir() and
         not (out / 'tmp').is_symlink(), 'fixture temporary writes must stay inside this M2 arm')
    raw, manifest_identity = checked(HERE / 'SOURCE_MANIFEST.json',
                                    declaration['files']['SOURCE_MANIFEST.json'])
    manifest = json.loads(raw)
    need(type(source_manifest) is dict and source_manifest == manifest,
         'exact source-pinned baseline manifest required')
    hashes, sizes = manifest['source_sha256'], manifest['source_bytes']
    need(type(hashes) is dict and type(sizes) is dict and hashes.keys() == sizes.keys() and
         len(hashes) == 306, 'exact frozen306 source closure required')
    sources = {}
    for relative, digest in hashes.items():
        need(type(relative) is str and not Path(relative).is_absolute() and
             '..' not in Path(relative).parts, 'source path escape')
        path = SOURCE / relative
        checked(path, dict(bytes=sizes[relative], sha256=digest))
        sources[str(path)] = digest
    # These are the separate finite M2 limits, never the baseline M128 budget.
    whole_limits, attention_limits = trace_limits, attention_trace_limits
    need(type(whole_limits) is dict and set(whole_limits) == F.TRACE_FIELDS and
         type(whole_limits['codec']) is dict and set(whole_limits['codec']) == F.CODEC_FIELDS,
         'exact finite wholeblock trace limits required')
    need(type(attention_limits) is dict and type(attention_limits.get('max_m')) is int and
         attention_limits['max_m'] == 2 and
         attention_limits.get('source_manifest_sha256') == manifest_identity['sha256'],
         'M2-only Attention limits and exact source manifest binding required')
    required = {'fullblock_runtime.py', 'capture/anchors.json', 'capture/CODEC_PINS.json',
                'observation/TRACE_CODES.json', 'observation/source_guard.py',
                'observation/event_stream.py', 'capture/wholeblock.py',
                'capture/fixed_token_table.py', 'capture/token_encoder.py'}
    need(required <= declaration['files'].keys(), 'original factory helper pins required')
    for relative in required:
        checked(HERE / relative, declaration['files'][relative])

    def checked_native():
        fresh, library_type = native_check()
        ctypes_module = sys.modules.get('ctypes')
        need(type(ctypes_module) is types.ModuleType and runtime_context['dense'].C is ctypes_module and
             library_type is ctypes_module.CDLL and type(library) is library_type,
             'exact real loaded ctypes/CDLL identity required')
        need(type(fresh) is dict and fresh == runtime_context['reuse'] and
             fresh.get('status') == 'VERIFIED_EXISTING_ELF_LOAD_ONLY' and
             fresh.get('compilation_performed') is False and fresh.get('fresh_build') is False and
             fresh.get('old_numeric_state_reused') is False and
             fresh.get('reset_performed_by_loader') is False and
             fresh.get('library') == library._name == attention_limits['native_library_path'] and
             fresh.get('library_sha256') == attention_limits['native_library_sha256'],
             'real fresh native receipt/map/symbol identity required')
        return fresh, library_type

    explicit = F._modules(runtime_context)
    native_identity, library_type = checked_native()
    closure = F.LoadedClosure(sources)
    anchors = json.loads(checked(HERE / 'capture/anchors.json', declaration['files']['capture/anchors.json'])[0])
    need(len(anchors) == 50, 'reviewed sparse capture anchor inventory changed')
    descriptors = {}
    for key, expected in anchors.items():
        module = F._resolve(expected['relative_path'], explicit)
        d = closure.function(module, expected['qualname'])
        need(d['sha256'] == expected['sha256'] and d['firstlineno'] == expected['firstlineno'], 'capture anchor source differs: ' + key)
        descriptors[key] = d
    trace_codes = json.loads(checked(HERE / 'observation/TRACE_CODES.json', declaration['files']['observation/TRACE_CODES.json'])[0])['loaded_code_descriptors']
    need(len(trace_codes) == 24, 'reviewed Attention code inventory changed')
    for i, (name, cls, member) in enumerate(trace_codes):
        module = F._resolve(name.replace('.', '/') + '.py', explicit)
        descriptors['attention_' + str(i)] = closure.function(module, (cls + '.' if cls else '') + member)
    names = dict(fixed_binding='candidates.qwen2_fixed93_attention.binding',
        fixed_owner='candidates.qwen2_fixed93_attention.owner',
        dense_owner='candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain',
        official_owners='candidates.qwen2_resident_matrix.official_bf16.owners',
        profiled='candidates.qwen2_resident_matrix.dense_block_reduce.matrix_binding',
        scalar='candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic',
        physical='candidates.qwen2_resident_matrix.ffn_public.prefix_execution',
        memory='candidates.qwen2_resident_matrix.ffn_public.fullgraph_memory',
        silu='candidates.qwen2_resident_matrix.official_bf16.execution')
    modules = {key: F._resolve(name.replace('.', '/') + '.py', explicit) for key, name in names.items()}
    selected_classes = [(modules['fixed_binding'], 'Fixed93PublicExecution'), (modules['fixed_binding'], 'Fixed93ReductionDriver'),
        (modules['fixed_owner'], 'Fixed93AttentionOwner'), (modules['dense_owner'], 'DenseReductionOwner'),
        (modules['official_owners'], 'OfficialPrefixOwner'), (modules['profiled'], 'ProfiledMatrixService'),
        (modules['scalar'], 'ScalarService'), (modules['physical'], 'PhysicalMemory'),
        (modules['memory'], 'FullGraphMemory'), (modules['memory'], 'SharedWorkspace'),
        (modules['silu'], 'ObservedSiluLibrary')]
    for module, name in selected_classes:
        closure.cls(vars(module)[name])
    matrix_globals = descriptors['matrix_accept_step']['function'].__globals__
    ordinary_globals = descriptors['public_ordinary_edge']['function'].__globals__
    matrix_payload_types = dict(
        normal_result=matrix_globals['MatrixResult'],
        matrix_value=matrix_globals['MatrixValue'],
        dense_result=ordinary_globals['numeric'].model.MatrixResult)
    need(matrix_payload_types['dense_result'] is
         descriptors['silu_execute']['function'].__globals__['model'].MatrixResult and
         matrix_payload_types['dense_result'] is
         descriptors['reduce_tick']['function'].__globals__['MatrixResult'],
         'one source-selected Dense result class across driver families')
    for cls in matrix_payload_types.values():
        closure.cls(cls)
    closure.cls(matrix_globals['_MatrixRow'])
    attention_globals = descriptors['owner_attention']['function'].__globals__
    reduction_globals = descriptors['reduce_tick']['function'].__globals__
    operand_payload_types = dict(
        dense_step=ordinary_globals['numeric'].model.Step,
        window_step=reduction_globals['DenseReductionOwner']._operand_response.__globals__['KWindowStep'],
        normal_step=matrix_globals['NormalStep'],
        legacy_request=attention_globals['LegacyRequest'],
        packed_request=attention_globals['PackedQkRequest'])
    for cls in operand_payload_types.values():
        closure.cls(cls)
    # These observation modules were hash-pinned before their actual import.
    from observation import source_guard
    from observation.event_stream import load_codec
    overlay_sources = verify_whole_module()
    WholeblockObservation = whole_module.WholeblockObservation
    need(WholeblockObservation.__module__ == 'capture.cached_wholeblock' and
         sys.modules.get('capture.cached_wholeblock') is whole_module, 'explicit new observer module required')
    from capture import token_encoder
    need(F._check_observation_helpers(declaration) is source_guard, 'observation guard module identity differs')
    F._check_token_helpers(declaration)
    codec_root = Path(attention_limits['codec_root'])
    need(codec_root.is_absolute() and codec_root.resolve() == codec_root and codec_root.is_dir(), 'exact reviewed codec root required')
    codec_pins = json.loads(checked(HERE / 'capture/CODEC_PINS.json', declaration['files']['capture/CODEC_PINS.json'])[0])
    for name, digest in codec_pins.items():
        _, identity = checked(codec_root / name)
        need(identity['sha256'] == digest, 'r3 codec source differs')
    fmt, writer = load_codec(codec_root)
    need(writer.Writer.__module__ == 'writer' and fmt.Limits.__module__ == 'format', 'codec real type identity required')
    codec = dict(Writer=writer.Writer, Limits=fmt.Limits,
                 source_sha256={str(codec_root / name): digest for name, digest in codec_pins.items()})
    identity_types = dict(x=modules['fixed_binding'].Fixed93PublicExecution,
        physical=modules['physical'].PhysicalMemory, memory=modules['memory'].FullGraphMemory,
        silu=modules['silu'].ObservedSiluLibrary, library=library_type)
    admission = dict(source_roots=[str(SOURCE), str(Path(whole_module.__file__).parent)],
        sources=dict(sources, **overlay_sources), loaded_codes=descriptors,
        identity_types=identity_types, source_verified=True, native_verified=True,
        native_identity=native_identity, jsonable=descriptors['jsonable']['function'], codec=codec,
        matrix_payload_types=matrix_payload_types, operand_payload_types=operand_payload_types)
    # The booleans above summarize the preceding checks, not an input authority.
    whole = WholeblockObservation(out, admission=admission, trace_limits=whole_limits)
    need(type(whole.trace_dispatcher) is whole_module.TraceDispatcher and
         whole.trace_dispatcher.callback.__func__ is whole_module.TraceDispatcher._dispatch and
         whole._observe.__func__ is WholeblockObservation._observe, 'new dispatcher and subscriber actually selected')
    try:
        # The already-observed startup initializer, with no readonly input
        # providers and no producer/advance body. M128 geometry is binding only.
        fixtures = runtime_context['fixtures']
        prefix, original = runtime_context['prefix'], runtime_context['original']
        owner_module, dense = runtime_context['owner_module'], runtime_context['dense']
        binding, profiles = runtime_context['binding'], runtime_context['profiles']
        scalar, public = runtime_context['scalar'], runtime_context['public']
        execution = runtime_context['execution']
        f = fixtures.make_qwen2_21_fixture(128, 7)
        physical = prefix.PhysicalMemory(f, {})
        memory = modules['memory'].FullGraphMemory(physical)
        region = f.config.regions[3]
        dense_owner = owner_module.DenseReductionOwner(original.numeric.model.PrefixWorkspace(
            region.base, region.limit-region.base, 8, 2560), enable_dense_drain=True,
            enable_k_window=True, enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
        selected = dense.selected_library(library)
        need(selected.sf_entrypoint == 'sf_vector_bf16_v1', 'original BF16 SiLU selection required')
        need(library.td_reset() == 0 and selected.sf_reset() == 0,
             'fresh Matrix/selected SiLU reset failed')
        silu = modules['silu'].ObservedSiluLibrary(selected, 128)
        service = binding.ProfiledMatrixService(library, profiles.QWEN2_QKV_PROFILE)
        shared = scalar.ScalarService()
        x = modules['fixed_binding'].Fixed93PublicExecution(
            public.PublicFrontend(physical.metadata_port(), f.config), dense_owner,
            whole.public_trace, deadline, fixture=f,
            host=public.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True),
            prefix_owner=execution.OfficialPrefixOwner(shared),
            attention_owner=modules['fixed_owner'].Fixed93AttentionOwner(service, shared),
            matrix_service=service)
        owner = x.attention_owner
        # The raw original constructor and bind checks are unchanged.
        whole.bind(x=x, physical=physical, memory=memory, silu=silu, library=library)
        prefix_owners = F._resolve(
            'candidates/qwen2_resident_matrix/ffn_public/prefix_owners.py', explicit)
        Job, Response = prefix_owners.Job, prefix_owners.MemoryResponse
        closure.cls(Job)
        closure.cls(Response)
        need(modules['fixed_owner'].MemoryResponse is Response,
             'one real source-selected Attention MemoryResponse class required')
        bank_identity = None

        def verify_context():
            # Original BoundWholeblock._verify checks, without a wrapper or
            # fullblock seal. Parent calls this before and after the finite case.
            nonlocal bank_identity
            closure.revalidate()
            need(verify_whole_module() == overlay_sources and type(whole) is whole_module.WholeblockObservation and
                 type(whole.trace_dispatcher) is whole_module.TraceDispatcher and
                 whole.trace_dispatcher.callback.__func__ is whole_module.TraceDispatcher._dispatch,
                 'new observer source/selection changed')
            need(type(x.owner) is modules['dense_owner'].DenseReductionOwner and
                 type(x.prefix_owner) is modules['official_owners'].OfficialPrefixOwner and
                 type(x.attention_owner) is modules['fixed_owner'].Fixed93AttentionOwner and
                 type(x.matrix_service) is modules['profiled'].ProfiledMatrixService and
                 type(x.prefix_owner.scalar) is modules['scalar'].ScalarService and
                 x.prefix_owner.scalar is x.attention_owner.scalar and
                 x.matrix_service is x.attention_owner.matrix,
                 'exact shared owner/service types changed')
            need(F._check_observation_helpers(declaration) is source_guard,
                 'observation guard module replaced')
            F._check_token_helpers(declaration)
            source_guard.verify_loaded(owner, SOURCE)
            checked_native()
            bank = F.accumulator_mapping(service.resource_address, library._name)
            if bank_identity is None:
                bank_identity = bank
            stable = ('address', 'bytes', 'library', 'library_sha256', 'load_bias',
                      'writable_segment_start', 'writable_segment_end')
            need(all(bank[k] == bank_identity[k] for k in stable),
                 'whole original accumulator interval identity changed')
            return bank

        initial_bank = verify_context()
        whole.check()
        need(deadline > time.monotonic(), 'M2 construction exhausted total deadline')
        need(x.host.pc == x.host.completed == x.host.jobs == 0 and
             not x.completions and x.launch_result is None and not dict(physical.counts) and
             physical.pending is None and silu.calls == 0 and
             owner.state == dense_owner.state == x.prefix_owner.state == 'idle' and
             service.owner is None and shared.client is None,
             'lazy initializer crossed into public or numeric execution')
        need(all(physical.regions[name]['provider'] is None
                 for name, a in f.allocations.items() if a.readonly),
             'M2 context must not bind any readonly input/reference provider')
        return dict(whole=whole, owner=owner, Job=Job, Response=Response,
                    x=x, physical=physical, memory=memory, silu=silu, fixture=f,
                    service=service, shared=shared, library=library, closure=closure,
                    verify_context=verify_context, accumulator_mapping_initial=initial_bank,
                    native_identity=native_identity, source_root=SOURCE,
                    source_manifest=HERE / 'SOURCE_MANIFEST.json')
    except BaseException:
        whole.close()
        raise
