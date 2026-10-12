"""Finish the original public21 launch using actual owner and memory edges.

The caller owns source freezing, readonly inputs, service construction and
post-terminal comparison. This module never loads a reference, initializes an
intermediate, replaces a service, or interprets host ticks as hardware cycles.
"""
from array import array
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import time

from . import execute_numeric as execution
from . import prefix_execution as prefix
from .fullgraph_memory import FullGraphMemory
from .prefix_owners import MemoryResponse

require = execution.require


def execute_attention_owner(x, physical, job, *, final_ack_stall=5):
    """Feed the real Attention owner only accepted, physically addressed beats.

    The same public Host receives its actual terminal. The output stays
    unreadable until the caller accepts all three original public completions
    and calls PhysicalMemory.publish. Matrix readiness is periodically held
    independently of the memory port to exercise the shared service fences.
    """
    require(type(final_ack_stall) is int and final_ack_stall > 0,
            'Attention final ACK must have a positive bounded stall')
    backend = x.attention_owner
    require(backend is not None and backend.matrix is x.matrix_service and
            backend.scalar is x.prefix_owner.scalar,
            'Attention must use this launch shared Matrix and scalar services')
    require(getattr(x.frontend.memory, 'physical_memory', None) is physical and
            x.frontend.port.memory is x.frontend.memory,
            'Attention metadata and operands require the identical physical map')
    counts, pending, held = Counter(), None, None
    remaining, result, final_ack_tick = final_ack_stall, None, None
    require(x.attention_edge(job=job)['job_fire'], 'public Attention job was not accepted')
    while result is None:
        require(time.monotonic() <= x.deadline, 'Attention memory driver exceeded host budget')
        ports = backend.ports()
        tick = counts['ticks']
        inputs = dict(memory_ready=tick % 5 != 0, matrix_request_ready=tick % 7 != 0,
                      matrix_result_ready=tick % 11 != 0,
                      service_result_ready=tick % 13 != 0, service_done_ready=tick % 17 != 0)
        response = None
        if pending is not None:
            request, data = pending
            if request.write and backend.ack_bytes + 64 == job.write_bytes and remaining:
                require(ports['response'] is None and
                        (job.dst, job.dst + job.write_bytes) not in x.host.published,
                        'Attention terminal/publication before final ACK')
                remaining -= 1
                counts['final_ack_stall'] += 1
            else:
                response = MemoryResponse(request.tag, data)
                inputs['memory_response'] = response
        edge = x.attention_edge(**inputs)
        counts['ticks'] += 1
        if held is not None:
            require(edge['memory'] == held, 'held Attention memory request changed')
        held = edge['memory'] if edge['memory'] is not None and not inputs['memory_ready'] else None
        if edge['memory_response_fire']:
            require(pending is not None and response is not None,
                    'Attention response without accepted memory request')
            request, _ = pending
            if request.write:
                physical.write_event('ack', SimpleNamespace(tag=response.tag,
                    error=response.error, nbytes=response.nbytes))
                counts['write_acks'] += 1
                if backend.ack_bytes == job.write_bytes:
                    require(remaining == 0, 'Attention final ACK was not deliberately held')
                    final_ack_tick = backend.clock
            pending = None
            counts['responses'] += 1
        if edge['memory_fire']:
            require(pending is None, 'Attention shared port accepted overlapping memory requests')
            request = edge['memory']
            if request.write:
                physical.write_event('command', SimpleNamespace(address=request.address, beats=1, tag=request.tag))
                physical.write_event('data', SimpleNamespace(words=request.words, mask=request.mask, last=True))
                data = None
            else:
                data = physical.read_bytes64(request.address)
            pending = request, data
            counts['requests'] += 1
            counts['write_requests' if request.write else 'read_requests'] += 1
        counts['matrix_requests'] += bool(edge.get('matrix_request_fire'))
        counts['matrix_results'] += bool(edge.get('matrix_result_fire'))
        if edge['response_fire']:
            result = edge['response']
            require(pending is None and result.status is None and x.host.state == 'complete',
                    'Attention owner error or premature terminal: ' + str(result))
            require(final_ack_tick is not None and backend.clock > final_ack_tick and
                    counts['requests'] == counts['responses'] and not held and
                    x.matrix_service.owner is None and backend.state == 'idle',
                    'Attention terminal before accepted memory/Matrix obligations retire')
    physical.terminal(job, result)
    return dict(job=asdict(job), result=asdict(result), accepted=dict(counts),
                final_ack_fence=dict(held_ticks=counts['final_ack_stall'],
                    final_ack_tick=final_ack_tick, terminal_tick=backend.clock,
                    terminal_strictly_after_final_ack=True), backend=backend.report())


def _dense(x, physical, memory, lib, job, out, *, down=False):
    """Route DenseO and Down through the same original owner and accumulator."""
    out = Path(out)
    out.mkdir()
    decoded = execution.numeric.decode_job(job)
    service = x.matrix_service
    require(service.acquire(x.owner, 'dense', job.tag),
            'ordinary Dense could not acquire this launch shared Matrix resource')
    bridge = service.dense_library(x.owner)
    trace = execution.numeric.CappedTrace(out / 'owner_events_prefix.jsonl')
    try:
        if down:
            report, actual = execution.down_driver.execute_down(execution.numeric.model,
                x.owner, bridge, memory, decoded, out, x.deadline, trace,
                owner_tick=x.ordinary_edge, matrix_bridge=bridge,
                workspace_transport=memory.workspace, output_event=physical.dense_sink(decoded))
            raw = actual.tobytes()
        else:
            report, actual = execution.down_driver.execute_dense(execution.numeric.model,
                x.owner, bridge, memory, decoded, out, x.deadline, trace,
                a_source=physical.dense_source(decoded), output_event=physical.dense_sink(decoded),
                owner_tick=x.ordinary_edge, matrix_bridge=bridge)
            raw = actual.raw()
            require(report['prefix']['completed_sweeps'] == report['prefix']['ack_bytes'] == 0,
                    'DenseO cannot use an unbound private prefix workspace')
        require(raw == physical.raw(job.dst, job.write_bytes),
                'shared physical Dense output differs from accepted driver stores')
        x.accept_down_terminal(report)
        service.retire_owner_response(x.owner)
        service.release(x.owner)
        return report
    finally:
        trace.close()


def _request(x, pc, kind):
    ports = x.advance_to_request()
    job = ports['ordinary_request']
    require(job is not None and ports['group_request'] is None and
            (job.tag & 0xffff) == pc and job.kind == kind,
            'public suffix request order/kind at pc%d' % pc)
    return job


def _checkpoint(x, physical, memory):
    require(len(x.host.program) == 21 and x.host.pc == x.host.completed == x.host.jobs == 10 and
            x.host.state == 'decode' and x.host.status is None and x.host.result is None and
            x.launch_result is None and [c['pc'] for c in x.completions] == list(range(10)) and
            x.counts['completion_fire'] == x.counts['owner_result_fire'] == 10 and
            x.counts['result_fire'] == 0,
            'fullgraph continuation requires ten actual public prefix completions at pc10')
    require(getattr(x.frontend.memory, 'physical_memory', None) is physical and
            x.frontend.port.memory is x.frontend.memory and x.frontend.config == physical.fixture.config and
            memory.physical_memory is physical and memory.act.data is physical.regions['act']['data'] and
            memory.workspace.physical_memory is physical,
            'fullgraph metadata/owners/act/workspace must share the identical physical map')
    require(x.attention_owner is not None and x.prefix_owner is not None and x.matrix_service is not None and
            x.attention_owner.matrix is x.matrix_service and
            x.attention_owner.scalar is x.prefix_owner.scalar,
            'fullgraph requires the same Attention/prefix scalar and Matrix services')
    require(x.owner.state == x.prefix_owner.state == x.attention_owner.state == 'idle' and
            x.owner.lease is None and x.owner.tiles.idle and not x.owner.tiles.leased and
            x.matrix_service.owner is None and x.prefix_owner.scalar.client is None and
            x.coupled is None and x.down_job is None and not x.reset_required() and
            physical.pending is None and x.owner.workspace.split_k == 2560,
            'fullgraph prefix checkpoint has unfinished owner/service obligations')
    physical.check_coexistence(unpublished_pristine=True)


def execute_public_suffix(x, physical, lib, output, *, memory=None):
    """Continue pc10 through pc20 in the caller's original public21 launch.

    Return (actual_outputs, report) only after its whole-launch terminal.
    Gate/Up arrays are audit copies of actual tile reads; they never populate
    virtual DDR or feed a later owner. All subsequent operand reads go through
    the same addressed PhysicalMemory, including acknowledged act and Down.
    """
    # Check the launch before allocating the optional names-only adapter.
    require(len(x.host.program) == 21 and x.host.pc == x.host.completed == x.host.jobs == 10,
            'fullgraph continuation requires ten actual public prefix completions at pc10')
    memory = FullGraphMemory(physical) if memory is None else memory
    _checkpoint(x, physical, memory)
    out = Path(output)
    require(out.is_dir(), 'fullgraph output directory must already exist')
    identities = (id(x.owner), id(x.prefix_owner), id(x.attention_owner), id(x.matrix_service),
                  id(x.prefix_owner.scalar), id(physical), id(memory.act.data), id(memory.workspace.data))
    reports = []
    job = _request(x, 12, 'Attention')
    report = execute_attention_owner(x, physical, job)
    x.publish_completions((10, 11, 12))
    physical.publish(job, x.host)
    reports.append(dict(pcs=[10, 11, 12], kind='Attention', report=report))

    for pc, kind in ((13, 'Dense'), (14, 'Add'), (15, 'Norm')):
        job = _request(x, pc, kind)
        report = (_dense(x, physical, memory, lib, job, out / 'pc13_dense_o') if kind == 'Dense'
                  else prefix.execute_prefix_owner(x, physical, job))
        x.publish_completions((pc,))
        physical.publish(job, x.host)
        if kind == 'Dense':
            x.retire_ordinary_bookkeeping()
        reports.append(dict(pcs=[pc], kind=kind, report=report))

    ports = x.advance_to_request()
    call = ports['group_request']
    require(call is not None and ports['ordinary_request'] is None and
            tuple(getattr(call, role).tag & 0xffff for role in ('gate', 'up', 'act')) == (16, 17, 18),
            'fullgraph requires the original Gate/Up/SiLU public group')
    h = x.start_group()
    group_out = out / 'pc16_18_ffn'
    group_out.mkdir()
    outputs = {role: array('I', [execution.numeric.drain_check.SENTINEL_WORD]) *
               (h.call.gate.m * execution.numeric.WIDTH) for role in ('gate', 'up')}
    group_report = execution.execute_windows(x, lib, memory, outputs, group_out)
    for _ in range(16):
        if h.terminal is not None:
            break
        h.tick()
    require(h.terminal is not None and h.terminal.status is None and
            h.c.state == 'idle' and x.owner.lease is None and x.matrix_service.owner is None,
            'actual fullgraph FFN group did not retire')
    _, act_report = memory.act.validate_full()
    require(h.terminal.write_bytes == memory.act.ack_bytes and
            h.terminal.useful_macs == sum(r['useful_macs'] for r in h.window_reports) and
            h.terminal.executed_macs == sum(r['executed_macs'] for r in h.window_reports),
            'fullgraph FFN terminal differs from actual accepted traffic')
    physical.terminal(h.call.act, h.terminal)
    x.publish_completions((16, 17, 18))
    physical.publish(h.call.act, x.host)
    group_report.update(act_ddr=act_report, coordinator=dict(accepted=dict(h.counts),
        terminal=asdict(h.terminal), window_terminals=h.window_reports,
        drain_terminals=h.drain_reports, handoffs=h.handoffs))
    reports.append(dict(pcs=[16, 17, 18], kind='FFN', report=group_report))

    job = _request(x, 19, 'Dense')
    report = _dense(x, physical, memory, lib, job, out / 'pc19_down', down=True)
    x.publish_completions((19,))
    physical.publish(job, x.host)
    x.retire_ordinary_bookkeeping()
    reports.append(dict(pcs=[19], kind='Dense', report=report))

    job = _request(x, 20, 'Add')
    report = prefix.execute_prefix_owner(x, physical, job)
    x.publish_completions((20,))
    physical.publish(job, x.host)
    reports.append(dict(pcs=[20], kind='Add', report=report))
    result = x.finish()
    require(result['status'] is None and result['completed'] == 21 and result['jobs'] == 17 and
            [c['pc'] for c in x.completions] == list(range(21)) and
            all(c['status'] is None for c in x.completions) and
            x.counts['completion_fire'] == 21 and x.counts['request_fire'] == x.counts['owner_result_fire'] == 17 and
            x.counts['result_fire'] == 1 and x.host.events == set(range(22)),
            'whole public21 terminal lacks exactly 21 completions and 17 actual owner jobs')
    require(identities == (id(x.owner), id(x.prefix_owner), id(x.attention_owner), id(x.matrix_service),
            id(x.prefix_owner.scalar), id(physical), id(memory.act.data), id(memory.workspace.data)) and
            x.owner.state == x.prefix_owner.state == x.attention_owner.state == 'idle' and
            x.matrix_service.owner is None and x.prefix_owner.scalar.client is None and
            x.owner.lease is None and x.owner.tiles.idle and not x.owner.tiles.leased and
            not x.reset_required() and physical.pending is None and memory.workspace.finished,
            'whole public21 terminal changed resources or left obligations outstanding')
    physical.check_coexistence()
    virtual_spans = set(x.host.virtual)
    # Gate/Up are ordinary reservations in the original public manifest. The
    # actual Host's accepted FFN group gives them their virtual lifetime; do
    # not mistake their untouched DDR reservations for missing output jobs.
    require(all((physical.regions[name]['base'], physical.regions[name]['base'] +
                 physical.regions[name]['extent']) in virtual_spans
                for name in ('scores', 'probabilities', 'gate', 'up')),
            'whole public21 terminal lost original Attention/FFN virtual reservations')
    for name, region in physical.regions.items():
        if region['readonly'] or name == 'workspace':
            continue
        if (region['base'], region['base'] + region['extent']) in virtual_spans:
            require(not region['written'] and not region['acked'] and not region['terminal'] and
                    not region['published'] and
                    region['data'][64:-64] == prefix.SENTINEL * (region['extent'] // 4),
                    'virtual intermediate became a physical output: ' + name)
            continue
        require(region['terminal'] and region['published'], 'unexecuted fullgraph output: ' + name)
        words = array('I')
        words.frombytes(physical.raw(region['base'], region['extent']))
        outputs[name] = words
    require(result['write_bytes'] == sum(len(r['acked']) * 64 for name, r in physical.regions.items()
            if not r['readonly'] and not r['virtual'] and name != 'workspace'),
            'whole public21 written total differs from actual physical output ACK coverage')
    for name, words in outputs.items():
        (out / ('actual_' + name + '.f32le')).write_bytes(words.tobytes())
    return outputs, dict(status='PUBLIC21_PC0_20_SOFTWARE_EXECUTED', reports=reports,
        host=x.report(), memory=physical.report(), matrix=x.matrix_service.report(),
        virtual_outputs=memory.check_virtual(), same_owner_and_banks=True,
        same_physical_memory_and_services=True, full_block_executed=True,
        full_block_software_model_executed=True, attention_suffix_executed=True,
        public_host_python_model_executed=True, scala_host_executed=False,
        rtl_executed=False, actual_idma=False, hardware_cycles=None,
        protocol_model_ticks_are_hardware_cycles=False, full_wall_mac_utilization=None,
        reference_arithmetic_executed=False, native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
