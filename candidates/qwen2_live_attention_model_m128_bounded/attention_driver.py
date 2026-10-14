"""Original Attention driver plus one sparse post-loop read-only telemetry site.

Removing the added progress argument and the unique sampling if restores the
original function AST exactly. No owner/Host/Matrix/Scalar/observer patching.
"""
from array import array
from collections import Counter
from dataclasses import asdict
from types import SimpleNamespace
import time
from candidates.qwen2_resident_matrix.ffn_public.fullgraph_execution import require, MemoryResponse

def execute_attention_owner(x, physical, job, *, final_ack_stall=5, progress=None):
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
        if progress is not None and counts['ticks'] % 131072 == 0:
            progress.emit('attention_loop', driver=dict(accepted=dict(counts), pending=pending is not None, held=held is not None))
    physical.terminal(job, result)
    return dict(job=asdict(job), result=asdict(result), accepted=dict(counts),
                final_ack_fence=dict(held_ticks=counts['final_ack_stall'],
                    final_ack_tick=final_ack_tick, terminal_tick=backend.clock,
                    terminal_strictly_after_final_ack=True), backend=backend.report())
