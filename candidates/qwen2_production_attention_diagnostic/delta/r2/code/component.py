"""Source proposal: one genuine M16 public Attention component, not a launcher.

All target imports, complete-source gates, native/runtime identity checks,
input isolation, process budgets, artifact retention and terminal-only recipe
comparison belong to a future independently reviewed caller. No such caller is
provided here. Passing modules or a profile is NOT execution admission.

The real driver, owner arithmetic, readiness schedule and monitor callbacks are
not copied or wrapped. The only new dispatch identity is actual component pc2.
"""
from dataclasses import asdict
import time


def need(ok, message):
    if not ok:
        raise ValueError(message)


def make_fixture(f, model):
    """M16 specialization of test_fullgraph_execution.attention_fixture.

    q/k are declared component port names, mapped by the caller to the frozen
    qr/kr operand prefixes. They are NOT claimed to be public-prefix outputs.
    """
    rows = 16
    specs = dict(q=(0x1000000, (rows, 1536), 7), k=(0x2000000, (rows, 256), 7),
                 v=(0x3000000, (rows, 256), 7), scores=(0x8000000, (12, rows, rows), 7),
                 probabilities=(0x9000000, (12, rows, rows), 7), att=(0xa000000, (rows, 1536), 7))
    records, commands, roots = [], [], []

    def chain(name, extra=()):
        address, shape, dtype = specs[name]
        dims, root = shape + (1,) * (4 - len(shape)), len(records)
        records.extend((f.tensor_base_record(address, dtype=dtype, rank=len(shape), next_index=root + 1),
            f.shape4_record(dims, next_index=root + 2),
            f.stride3_record((dims[1] * dims[2] * dims[3], dims[2] * dims[3], dims[3]),
                            next_index=root + 3 if extra else f.NULL)))
        for index, record in enumerate(extra):
            records.append(f.DescriptorRecord(record.record_type, record.subtype, record.flags,
                root + 4 + index if index + 1 < len(extra) else f.NULL, record.payload))
        return root

    for opcode, a, b, dst, extra in (
        (f.Opcode.MATRIX_QK, 'q', 'k', 'scores',
         (f.matrix_op_record(m=rows, n=rows, k=128, dataflow=0, transpose_b=True), f.MatrixAux(full_c=True).to_record())),
        (f.Opcode.SFU_SOFTMAX, 'scores', None, 'probabilities',
         (f.SfuProgram(0x33, 1, input_dtype=f.TensorDType.FP32, output_dtype=f.TensorDType.FP32).to_record(),)),
        (f.Opcode.MATRIX_PV, 'probabilities', 'v', 'att',
         (f.matrix_op_record(m=rows, n=128, k=rows, dataflow=0), f.MatrixAux(full_c=True).to_record()))):
        root = chain(a, extra), chain(b) if b else f.NULL, chain(dst)
        pc = len(commands)
        commands.append(f.Command128(opcode, f.Engine.SFU_CGRA if b is None else f.Engine.MATRIX,
            event_wait=pc, event_signal=pc + 1, src0=root[0], src1=root[1], dst=root[2]))
        roots.append(root)
    cb = b''.join(command.to_bytes() for command in commands)
    db = b''.join(record.pack().to_bytes(16, 'little') for record in records)
    ct = model.Table(0xc000000, 0xc000000 + model.align64(len(cb)), len(commands))
    dt = model.Table(0xc001000, 0xc001000 + model.align64(len(db)), len(records))
    regions = (model.Region(0x1000000, 0x8000000, True, False),
               model.Region(0x8000000, 0xc000000, True, True),
               model.Region(0xc000000, 0xc010000, True, False),
               model.Region(0x10000000, 0x100c0000, True, True))
    config = model.LaunchConfig(ct, dt, regions)
    metadata = model.MetadataMemory(((ct.base, cb.ljust(model.align64(len(cb)), b'\0')),
                                    (dt.base, db.ljust(model.align64(len(db)), b'\0'))))
    allocations = {}
    for name, (address, shape, dtype) in specs.items():
        words = 1
        for dimension in shape:
            words *= dimension
        allocations[name] = f.PhysicalAllocation(address, shape, dtype, model.align64(words * 4),
            name in ('q', 'k', 'v'), name in ('scores', 'probabilities'))
    fixture = f.Fixture(config, metadata, tuple(commands), tuple(records), tuple(roots), specs,
                        scope='FROZEN_OPERANDS_M16_PUBLIC_ATTENTION_COMPONENT_ONLY', allocations=allocations)
    fixture.validate_spans()
    return fixture


def construct_component(runtime, providers, profile, deadline):
    """Future caller only: same production idle owners/banks and service MRO.

    runtime is the existing runtime_binding.load_runtime result, supplemented
    by the separately admitted configured Matrix library, never a new loader.
    No Dense, Prefix, SiLU or fullgraph driver is invoked by this function.
    """
    need(profile['rows'] == 16 and set(providers) == {'q', 'k', 'v'}, 'exact M16 component inputs')
    need(type(deadline) in (int, float) and time.monotonic() < deadline, 'live admitted deadline')
    fixture = make_fixture(runtime.fixtures, runtime.public)
    physical = runtime.prefix.PhysicalMemory(fixture, providers)
    numeric, region = runtime.original.numeric, fixture.config.regions[3]
    owner = runtime.owner_module.DenseReductionOwner(
        numeric.model.PrefixWorkspace(region.base, region.limit - region.base,
                                      fixture.config.epoch + 1, 2560),
        enable_dense_drain=True, enable_k_window=True,
        enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
    need(runtime.library.td_reset() == 0, 'initial arithmetic reset failed')
    service = runtime.binding.ProfiledMatrixService(runtime.library, runtime.profiles.QWEN2_QKV_PROFILE)
    scalar = runtime.scalar.ScalarService(
        committed_source_witness=profile['committed_source_witness'],
        committed_source_manifest=profile['committed_source_manifest'])
    x = runtime.original.PublicExecution(
        runtime.public.PublicFrontend(physical.metadata_port(), fixture.config), owner,
        numeric.CappedTrace(), deadline,
        host=runtime.public.group.HostControl(enabled=True, legacy_prefix=True, legacy_attention=True),
        prefix_owner=runtime.policy.OfficialPrefixOwner(scalar),
        attention_owner=runtime.policy.OfficialAttentionOwner(service, scalar), matrix_service=service)
    return x, physical


def validate_component_request(x, physical, job):
    """Reject full21 or synthetic prefix accounting; do not modify Host state."""
    f = physical.fixture
    need(f.scope == 'FROZEN_OPERANDS_M16_PUBLIC_ATTENTION_COMPONENT_ONLY' and
         f.config.command.count == len(f.commands) == 3 and
         tuple(int(c.opcode) for c in f.commands) == (0x23, 0x33, 0x24) and
         all(c.event_wait == i and c.event_signal == i + 1 for i, c in enumerate(f.commands)),
         'exact three actual public commands required')
    need(len(x.host.program) == 3 and x.host.completed == x.host.jobs == 0 and
         x.completions == [] and x.requests == [] and x.launch_result is None and
         x.counts['request_fire'] == x.counts['completion_fire'] == x.counts['owner_result_fire'] == 0,
         'component must not inherit prefix completions or jobs')
    need(not hasattr(x, 'policy_jobs'), 'public21 official policy is not a component policy')
    need(x.ports()['ordinary_request'] is job and x.ports()['group_request'] is None and
         job.tag == (f.config.epoch << 16) | 2 and job.kind == 'Attention' and
         (job.m, job.n, job.k, job.write_bytes) == (16, 1536, 128, 16 * 1536 * 4) and
         (job.a, job.b, job.c, job.dst) == tuple(f.specs[n][0] for n in ('q', 'k', 'v', 'att')) and
         not job.weight_bf16 and not job.activation_bf16 and not job.output_bf16,
         'one real fused pc2 M16 request and exact operand layout required')
    physical.check_coexistence(unpublished_pristine=True)


def execute_component(x, physical, profile, *, direct_transport, lanes,
                      production_bridge, observer, monitor, base_fields,
                      stream_path, state, candidate_capture=None, candidate_mask_snapshot=None,
                      mark=lambda name: None):
    """Proposed common dispatch; never call fullgraph bridge.make_dispatch.

    Baseline uses production_bridge.make_observation. Candidate capture is the
    exact existing selective_binding.make_capture partial, normal-source loaded
    through its existing ProjectCodeGate. Both arms use the same original
    production streaming tracer and observe_driver. Caller must retain partial
    fields/raw receipts on every exception; this API is not a failure recorder.
    """
    need(profile['rows'] == 16 and profile['qk_profile'] == 2 and profile['pv_profile'] == 0 and
         profile['raw_kv_transport'] is False, 'exact component production profile')
    need(profile['observer_variant'] in ('original', 'selective_identity_r1') and
         (candidate_capture is not None) == (profile['observer_variant'] == 'selective_identity_r1') and
         (candidate_mask_snapshot is not None) == (candidate_capture is not None),
         'explicit baseline or exact identity candidate only')
    need(type(state) is dict and not state, 'fresh caller-owned failure evidence holder')
    state.update(capture=None, tracer=None, capture_error=None, service_error=None, mask_receipts=[])
    job = x.advance_to_request()['ordinary_request']
    validate_component_request(x, physical, job)
    state['job'] = asdict(job)
    need(getattr(x, 'selected_direct_binding', None) is None, 'single component dispatch')
    binding = direct_transport.bind(x, physical, job, ordered_fold=True, ordered_lanes=lanes)
    owner = x.attention_owner
    bindings = observer.bindings(owner, profile)
    capture = (production_bridge.make_observation(monitor, owner, 16, base_fields, bindings)
               if candidate_capture is None else candidate_capture(owner, 16, base_fields, bindings))
    state['capture'] = capture
    tracer = production_bridge.make_service_trace(observer, x.matrix_service, profile, monitor.bind, stream_path)
    state['tracer'] = tracer
    mark('binding_and_monitor_setup')
    def drive():
        if candidate_mask_snapshot is not None:
            try:
                state['mask_receipts'].append(candidate_mask_snapshot(capture, installed=True))
            except KeyboardInterrupt:
                raise
            except BaseException as error:
                message = 'installed mask validation: ' + type(error).__name__ + ': ' + str(error)
                state['mask_receipts'].append(dict(phase='installed_check_failed', error=message))
                state['capture_error'] = (message if state['capture_error'] is None else
                                          state['capture_error'] + '; ' + message)
        mark('monitor_enter_and_installed_mask_validation')
        return direct_transport.execute_attention_owner(x, physical, job,
            final_ack_stall=5, enable_raw_kv=False)
    # No replacement edge loop, altered readiness, callback wrapper or prefix.
    try:
        report = production_bridge.observe_driver(tracer, capture, drive, state)
    finally:
        # Caller can persist partial capture and the original framed prefix even
        # when the real driver or monitor fails; never create a success footer.
        try:
            state['service_events_raw'] = tracer.raw_receipt()
        except Exception as error:
            state['service_events_raw_error'] = type(error).__name__ + ': ' + str(error)
            if state['service_error'] is None:
                state['service_error'] = state['service_events_raw_error']
    mark('actual_owner_job_and_monitor_cleanup_including_stream_footer')
    state['driver_report'] = report
    binding.check(x)
    need(physical.pending is None and x.matrix_service.owner is None and owner.state == 'idle' and
         x.host.completed == 0 and x.counts['request_fire'] == x.counts['owner_result_fire'] == 1,
         'actual component terminal and release must precede public completions')
    need(report['accepted']['ticks'] + 1 <= 202951, 'source-derived successful owner-edge bound')
    need(report['accepted']['read_requests'] == 27648 and report['accepted']['write_requests'] == 1536 and
         report['accepted']['requests'] == report['accepted']['responses'] == 29184 and
         report['accepted']['final_ack_stall'] == 5, 'exact M16 memory work and ACK hold')
    for pc in (0, 1, 2):
        x.publish_completions((pc,))
    physical.publish(job, x.host)
    terminal = x.finish()
    need((terminal['completed'], terminal['jobs'], terminal['write_bytes']) == (3, 1, 98304) and
         [c['pc'] for c in x.completions] == [0, 1, 2] and
         x.counts['result_fire'] == 1 and x.attention_jobs == x.attention_results == 1,
         'three true completions / one Attention job / one actual public result')
    physical.check_coexistence(unpublished_pristine=True)
    mark('public_completions_publication_and_component_terminal')
    state['actual_terminal_verified'] = True
    state['terminal'] = dict(terminal)
    if (candidate_mask_snapshot is not None and state['mask_receipts'] and
            state['mask_receipts'][0]['phase'] == 'installed'):
        state['mask_receipts'].append(candidate_mask_snapshot(capture, installed=False,
            previous=state['mask_receipts'][0]))
    mark('post_terminal_mask_cleanup_validation')
    need(state['capture_error'] is None and state['service_error'] is None, 'monitor lifetime failed')
    state['capture_report'], state['service_events'] = capture.seal(), tracer.seal()
    mark('capture_and_stream_receipt_seals')
    return dict(job=asdict(job), owner=report, terminal=terminal, observation=state,
                actual=physical.raw(job.dst, job.write_bytes), fullblock=False,
                native_execution_admission=False, hardware_cycles=False, performance_adopted=False)


if __name__ == '__main__':
    raise SystemExit('SOURCE PROPOSAL ONLY: no executable admission, worker or native launcher')
