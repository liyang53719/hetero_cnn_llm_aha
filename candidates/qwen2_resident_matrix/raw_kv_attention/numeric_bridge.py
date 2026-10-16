"""Opt-in, test-only bridge to the unchanged original PV16 Attention owner.

Importing this module does not import numerical owners or load a library. The
CLI requires an existing, receipted MATRIX_SERVICE_LIBRARY; it never compiles.
Only accepted K/V read metadata is queued. Payloads remain in the original Bus
or the parent's raw bank response, with a transient conversion on delivery.
Software event counts and small synthetic M1/M2 runs are not RTL evidence.
"""
import json
import os
from pathlib import Path
import random
import struct
import time
from types import SimpleNamespace
import unittest

from .model import Binding, KvSupply, Read, Reply
from ..raw_kv.model import uint


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dependencies():
    # Never substitute recovered modules, change source guards, or compile a
    # fallback. These original imports are deferred until after the preflight.
    from .numeric_prepare import check
    check()
    from candidates.qwen2_resident_matrix.ffn_public import prefix_owners as p
    from candidates.qwen2_resident_matrix.ffn_public.test_prefix_owners import Bus, Harness
    from candidates.qwen2_resident_matrix.ffn_attention.attention_owner import AttentionOwner
    from candidates.qwen2_resident_matrix.ffn_attention.matrix_service import MatrixService
    from candidates.qwen2_resident_matrix.official_bf16.owners import OfficialAttentionOwner
    from candidates.qwen2_resident_matrix.official_bf16.test_owners import (
        RecordingScalar, reference_attention, verified_library)
    require(OfficialAttentionOwner.tick is AttentionOwner.tick,
            'original Attention tick must remain unchanged')
    return SimpleNamespace(p=p, Bus=Bus, Harness=Harness,
                           OfficialAttentionOwner=OfficialAttentionOwner,
                           MatrixService=MatrixService, RecordingScalar=RecordingScalar,
                           reference_attention=reference_attention,
                           verified_library=verified_library)


def decode_ddr_response(response, response_type):
    """Normalize a returned beat without inventing data or forgetting identity.

    A canonical matching tag retires even an error/short/malformed-data beat:
    the supply receives an error, and the owner is reset before delivery.
    A foreign/noncanonical tag still cannot retire the genuine request.
    """
    if type(response) is not response_type or not uint(response.tag, 64):
        return object()
    if type(response.error) is not bool or response.error or type(response.nbytes) is not int or response.nbytes != 64:
        return Reply(response.tag, 0, True)
    data = response.data
    if type(data) is bytes and len(data) == 64:
        return Reply(response.tag, int.from_bytes(data, 'little'))
    if type(data) is tuple and len(data) == 16 and all(uint(word, 32) for word in data):
        return Reply(response.tag, int.from_bytes(struct.pack('<16I', *data), 'little'))
    return Reply(response.tag, 0, True)


class AttentionKvBridge:
    """One original owner, one original Bus, and the real parent-backed supply.

    A KV request enters the supply only after the original owner's memory_fire.
    The one queue element is an immutable read request with data=None. Core
    response consumption and delayed raw ACK retirement remain independent.
    The original owner keeps its terminal until all supplier debt is retired.
    """
    def __init__(self, owner, bus, job, *, owner_id=7):
        d = dependencies()
        require(type(owner) is d.OfficialAttentionOwner, 'original OfficialAttentionOwner required')
        require(type(bus) is d.Bus, 'original Prefix test Bus required')
        require(owner.ports()['job_ready'], 'owner must be ready before binding')
        self.owner, self.bus, self.job, self.p = owner, bus, job, d.p
        self.supply = KvSupply(enabled=True)
        self.supply.bind(Binding(owner_id, job.tag, job.b, job.c, job.m,
                                 job.dst, job.write_bytes))
        self.kv_request = None  # accepted read metadata; never a payload packet
        self.kv_admitted = False
        self.bus_route = None
        self.supply_done = False
        self.fault_notified = False
        self.core_trace = []  # (tag, address, write), no copied write/read data
        self.ticks = 0

    def is_kv(self, request):
        j = self.job
        return (request is not None and not request.write and
                any(base <= request.address < base + j.m * 1024 for base in (j.b, j.c)))

    def ports(self):
        out = self.owner.ports().copy()
        if not self.supply_done:
            out['response'] = None
        return out

    def tick(self, *, job=None, memory_ready=True, respond=True, response=None,
             consumer_ready=True, response_ready=False, ddr_ready=True,
             raw_ack_ready=True, abort=False, **owner_controls):
        allowed = {'matrix_request_ready', 'matrix_result_ready',
                   'service_result_ready', 'service_done_ready', 'done_override'}
        require(set(owner_controls) <= allowed, 'unsupported owner control')
        require(all(type(v) is bool for v in (memory_ready, respond, consumer_ready,
                                             response_ready, ddr_ready, raw_ack_ready, abort)),
                'canonical bridge handshake flags')
        require(job is None or job == self.job, 'bridge is bound to one exact job')
        op = self.owner.ports()
        completion_ready = self.supply_done
        old = self.bus.pending
        require((old is None) == (self.bus_route is None), 'bus routing debt mismatch')
        require(response is None or old is not None, 'response override requires accepted bus debt')
        r = response if response is not None else self.bus.response() if old and respond else None
        incoming = None
        if self.bus_route == 'kv' and r is not None:
            incoming = decode_ddr_response(r, self.p.MemoryResponse)
        accepted = self.kv_request
        offered = Read(accepted.tag, accepted.address) if accepted and not self.kv_admitted else None
        se = self.supply.tick(
            request=offered, ddr_ready=ddr_ready and old is None,
            ddr_response=incoming,
            response_ready=bool(self.kv_admitted and consumer_ready and op['memory_response_ready']),
            raw_ack_ready=raw_ack_ready, terminal=op['response'] is not None,
            abort=abort or self.owner.poison)
        if se['request_fire']:
            require(accepted is not None and not accepted.write and accepted.data is None,
                    'only an accepted payload-free KV read may enter the supply')
            self.kv_admitted = True
        if se['done_ready']:
            self.supply_done = True
        notify_fault = se['reset_required'] and not self.fault_notified and not self.owner.poison
        if se['reset_required']:
            self.fault_notified = True
        core_response = None
        if se['response_fire']:
            require(self.kv_admitted and accepted is not None, 'KV response lacks accepted core request')
            sr = se['response']
            require(sr.tag == accepted.tag, 'KV reply tag changed')
            core_response = self.p.MemoryResponse(sr.tag, sr.data.to_bytes(64, 'little'), sr.error)
        elif self.bus_route == 'direct' and consumer_ready:
            core_response = r
        request = op['memory']
        kv = self.is_kv(request)
        core_ready = (memory_ready and self.kv_request is None and se['request_ready']) if kv else (memory_ready and old is None)
        # The unchanged tick processes local_reset before an offered response;
        # accepted read debt is drained without advancing its arithmetic program.
        edge = self.owner.tick(job=job, memory_ready=core_ready,
                               memory_response=core_response, local_reset=notify_fault,
                               response_ready=response_ready and completion_ready,
                               **owner_controls)
        if se['response_fire']:
            require(edge['memory_response_fire'], 'core did not consume supplier response')
            self.kv_request = None
            self.kv_admitted = False
        if edge['memory_response_fire'] and self.bus_route == 'direct':
            require(core_response is not None, 'direct response missing')
            self.bus.retire(core_response)
            self.bus_route = None
        if se['ddr_response_fire'] and self.bus_route == 'kv' and not self.supply.ddr_pending:
            # Foreign responses are consumed/quarantined by the supply but do
            # not retire the genuine Bus request; its matching reply still owes.
            require(r is not None, 'DDR retirement missing accepted response')
            self.bus.retire(r)
            self.bus_route = None
        if edge['memory_fire']:
            q = edge['memory']
            self.core_trace.append((q.tag, q.address, q.write))
            if self.is_kv(q):
                require(q.data is None and self.kv_request is None, 'one metadata-only KV request')
                self.kv_request, self.kv_admitted = q, False
            else:
                require(not se['ddr_fire'] and self.bus.pending is None, 'direct/DDR bus overlap')
                self.bus.accept(q)
                self.bus_route = 'direct'
        if se['ddr_fire']:
            q = se['ddr_request']
            require(self.kv_admitted and self.kv_request is not None,
                    'DDR command lacks accepted KV request')
            require((q.tag, q.address) == (self.kv_request.tag, self.kv_request.address),
                    'DDR command identity differs from accepted core read')
            require(self.bus.pending is None, 'one physical DDR request at a time')
            self.bus.accept(self.kv_request)
            self.bus_route = 'kv'
        if edge['response_fire']:
            require(self.supply_done and self.supply.parent.raw.drained and
                    not self.supply.parent.raw.blocked and not self.supply.ddr_pending and
                    self.kv_request is None and self.bus.pending is None,
                    'owner completion before supplier/bus debt release')
        self.ticks += 1
        edge['supply'] = se
        edge['completion_ready'] = self.supply_done
        return edge


def check_budget(deadline, events):
    require(time.monotonic() < deadline, 'bounded numerical wall deadline exceeded')
    require(events < 200000, 'bounded numerical event budget exceeded')


def drive(harness, job, deadline):
    events = 0
    check_budget(deadline, events)
    require(harness.tick(job=job)['job_fire'], 'original owner did not accept job')
    events += 1
    ports = harness.ports if isinstance(harness, AttentionKvBridge) else harness.owner.ports
    while ports()['response'] is None:
        check_budget(deadline, events)
        harness.tick()
        events += 1
    result = ports()['response']
    for _ in range(3):
        check_budget(deadline, events)
        harness.tick()
        events += 1
        require(ports()['response'] == result, 'held terminal changed')
    check_budget(deadline, events)
    require(harness.tick(response_ready=True)['response_fire'], 'terminal was not consumed')
    if result.status is None:
        require(harness.owner.state == 'idle' and harness.owner.ack_bytes == job.write_bytes,
                'publication requires accepted successful terminal and exact write ACKs')
        require(harness.bus.outputs[job.dst] <= harness.bus.acked, 'missing output write ACK')
        harness.bus.publish(harness.owner, job)
    return result


def fixture(tokens, d):
    require(type(tokens) is int and tokens in (1, 2), 'only synthetic M1/M2 are supported')
    j = d.p.Job('Attention', (9 << 16) | 12, 0x100000, 0x200000,
                0x400000, tokens, 1536, 128, tokens * 6144,
                c=0x200000 + tokens * 1024)
    rng = random.Random(210128)
    palette = (0, 0x3f800000, 0xbf800000, 0x3f000000, 0xbf000000,
               0x3e800000, 0xbe800000, 0x3e000000, 0xbe000000,
               0x3f400000, 0xbf400000)
    data = tuple(tuple(rng.choice(palette) for _ in range(tokens * width))
                 for width in (1536, 256, 256))
    return j, data


def make_harness(library, d, job, data, *, loan):
    require(library.td_reset() == 0, 'original Matrix reset failed')
    owner = d.OfficialAttentionOwner(d.MatrixService(library), d.RecordingScalar())
    bus = d.Bus()
    for base, words in zip((job.a, job.b, job.c), data):
        bus.input(base, words)
    bus.output(job.dst, job.write_bytes)
    return AttentionKvBridge(owner, bus, job) if loan else d.Harness(owner, bus)


def accepted_matrix_counts(owner):
    # Transport stalls change software event ticks, not accepted Matrix work.
    return {name: count for name, count in owner.matrix_counts.items()
            if name != 'legacy_model_ticks'}


def compare_case(library, d, tokens, deadline):
    job, data = fixture(tokens, d)
    direct = make_harness(library, d, job, data, loan=False)
    direct_result = drive(direct, job, deadline)
    direct_bytes = direct.bus.raw(job.dst)
    direct_trace = tuple(direct.owner.scalar.trace)
    direct_counts = accepted_matrix_counts(direct.owner)
    loan = make_harness(library, d, job, data, loan=True)
    loan_result = drive(loan, job, deadline)
    require(direct_result.status is None and loan_result.status is None, 'clean numeric case failed')
    require(direct_bytes == loan.bus.raw(job.dst), 'direct/loan output mismatch')
    require(direct_trace == tuple(loan.owner.scalar.trace), 'direct/loan scalar trace mismatch')
    require(direct_counts == accepted_matrix_counts(loan.owner), 'accepted Matrix counters differ')
    for field in ('tag', 'status', 'write_bytes', 'useful_macs', 'executed_macs'):
        require(getattr(direct_result, field) == getattr(loan_result, field), 'owner result mismatch: ' + field)
    require([(q.tag, q.address, q.write) for q in direct.bus.trace] == loan.core_trace,
            'original core request order changed')
    unique = tokens * 32
    requests = 192 * tokens * (tokens + 1) // 2
    require(loan.supply.counts['fills'] == unique and loan.supply.counts['ddr_requests'] == unique,
            'KV unique miss count differs')
    require(loan.supply.counts['core_requests'] == requests and
            loan.supply.counts['hits'] == requests - unique, 'KV source trace count differs')
    check_budget(deadline, 0)
    # The independent oracle runs only after both candidates have completed;
    # none of its words can feed either candidate's Bus or arithmetic services.
    expected, expected_dots, expected_scores = d.reference_attention(tokens, *data)
    check_budget(deadline, 0)
    require(direct_bytes == struct.pack('<' + str(len(expected)) + 'I', *expected),
            'independent original-policy reference mismatch')
    dots, scores = [], []
    for index, entry in enumerate(direct_trace):
        if entry[0] == 'mul' and entry[2] == 0x3db504f3:
            require(0 < index < len(direct_trace) - 1, 'score trace boundary missing')
            before, after = direct_trace[index - 1], direct_trace[index + 1]
            require(before[0] == 'bf' and entry[1] == before[3] and
                    after[:2] == ('bf', entry[3]), 'original QK materialization order changed')
            dots.append(before[1])
            scores.append(after[3])
    require(dots == expected_dots, 'independent completed QK dot mismatch')
    require(scores == expected_scores, 'independent scaled BF16 score mismatch')
    return dict(tokens=tokens, status='PASS', kv_requests=requests,
                unique_ddr_reads=unique, hits=requests - unique,
                accepted_matrix=direct_counts, scalar_operations=len(direct_trace),
                output_words=len(expected))


def fault_case(library, d, deadline):
    job, data = fixture(1, d)
    h = make_harness(library, d, job, data, loan=True)
    check_budget(deadline, 0)
    require(h.tick(job=job)['job_fire'], 'fault-case owner admission failed')
    events = 1
    while not (h.supply.state == 'read_wait' and h.supply.parent.raw.response is not None):
        check_budget(deadline, events)
        h.tick(consumer_ready=False if h.kv_admitted else True, raw_ack_ready=False)
        events += 1
        # Fill ACK must retire before the raw reread can be issued.
        if h.supply.state == 'fill_wait':
            check_budget(deadline, events)
            h.tick(consumer_ready=False, raw_ack_ready=True)
            events += 1
    held = h.supply.parent.raw.response
    scalar_before = tuple(h.owner.scalar.trace)
    fmas_before = int(library.matrix_normal_fmas())
    check_budget(deadline, events)
    e = h.tick(abort=True, raw_ack_ready=False)
    events += 1
    require(e['supply']['response_fire'] and e['memory_response_fire'], 'fault did not drain accepted core read')
    require(h.supply.parent.raw.response is held and not h.supply.parent.raw.drained,
            'fault erased independent raw ACK debt')
    require(tuple(h.owner.scalar.trace) == scalar_before and
            int(library.matrix_normal_fmas()) == fmas_before,
            'revoked held reply advanced original arithmetic')
    for _ in range(3):
        check_budget(deadline, events)
        e = h.tick(raw_ack_ready=False, response_ready=True)
        events += 1
        require(not e['response_fire'] and not e['supply']['done_ready'],
                'completion escaped delayed raw ACK fence')
        require(e['supply']['response'] is None, 'consumed KV response was duplicated')
        require(h.supply.parent.raw.response is held, 'raw debt changed while stalled')
    while h.ports()['response'] is None:
        check_budget(deadline, events)
        h.tick()
        events += 1
    result = h.ports()['response']
    require(result.status == 'Protocol', 'supply fault did not reject original owner')
    check_budget(deadline, events)
    require(h.tick(response_ready=True)['response_fire'], 'rejected terminal did not retire')
    require(not h.bus.outputs[job.dst].intersection(h.bus.readable), 'fault published output')
    require(h.supply.counts['core_responses'] == 1, 'fault duplicated core response')
    return dict(tokens=1, status='PASS', revoked_reply_arithmetic_operations=0,
                core_replies=1, output_published=False)


def run_numeric():
    name = os.environ.get('MATRIX_SERVICE_LIBRARY')
    if not name:
        return 2, dict(status='NOT_RUN', reason='MATRIX_SERVICE_LIBRARY and adjacent verified compile.json required',
                       arithmetic_executed=False, hardware_simulation=False)
    path = Path(name).expanduser().resolve()
    if not path.is_file() or not path.with_name('compile.json').is_file():
        return 2, dict(status='NOT_RUN', reason='existing library or adjacent compile.json is missing',
                       arithmetic_executed=False, hardware_simulation=False)
    deadline = time.monotonic() + 120.0
    started = False
    try:
        d = dependencies()
        library = d.verified_library()
        check_budget(deadline, 0)
        started = True
        cases = [compare_case(library, d, tokens, deadline) for tokens in (1, 2)]
        fault = fault_case(library, d, deadline)
        return 0, dict(status='PASS_BOUNDED_NUMERIC', cases=cases, fault=fault,
                       arithmetic_executed=True, hardware_simulation=False,
                       public_profiles_executed=False, model_ticks_are_hardware_cycles=False,
                       native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
    except unittest.SkipTest:
        if started:
            return 1, dict(status='FAIL', reason='unexpected skip after numerical run started',
                           numerical_run_started=True, hardware_simulation=False)
        return 2, dict(status='NOT_RUN', reason='verified library prerequisite unavailable',
                       arithmetic_executed=False, hardware_simulation=False)
    except Exception as error:
        # No payloads, paths, raw traces, or reference words are printed.
        summary = dict(status='FAIL' if started else 'NOT_RUN',
                       reason=type(error).__name__, numerical_run_started=started,
                       hardware_simulation=False)
        if not started:
            summary['arithmetic_executed'] = False
        return 1, summary


def main():
    code, summary = run_numeric()
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
