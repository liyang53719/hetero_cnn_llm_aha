"""Bounded, source-pinned direct-public control fixtures, not numeric evidence.

The Attention owner, selected schedule/clients, PublicExecution, physical memory
and driver are source definition ASTs. Host and Dense below are explicitly
synthetic idle/control fixtures. Matrix/scalar adapters are the already frozen
synthetic controls, not native arithmetic, RTL, or full-prefill acceptance.
"""
from collections import Counter
from dataclasses import asdict, dataclass
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import os
import struct
import sys
import time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def need(condition, message):
    if not condition:
        raise AssertionError(message)


def bound_process():
    """Enforce the advertised process bounds before loading source definitions."""
    for kind, limit in ((resource.RLIMIT_CPU, 20), (resource.RLIMIT_AS, 256 * 1024 * 1024)):
        soft, hard = resource.getrlimit(kind)
        limit = min(limit, hard) if hard != resource.RLIM_INFINITY else limit
        resource.setrlimit(kind, (limit, limit))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})


bound_process()
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--source-root', required=True, type=Path)
_options, _remaining = _parser.parse_known_args()
SOURCE_ROOT = _options.source_root.resolve(strict=True)
SOURCE_PACKAGE = SOURCE_ROOT / 'candidates/qwen2_resident_matrix'


def verify_source(root):
    pins = json.loads((HERE / 'INPUT_PINS.json').read_text())
    for relative, pin in pins['sources'].items():
        raw = (root / relative).read_bytes()
        need(len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
             'source pin mismatch: ' + relative)
    return pins


# This happens before importlib executes the prior support and before ast.parse.
PINS = verify_source(SOURCE_ROOT)
_support_path = SOURCE_ROOT / 'candidates/qwen2_selected_scala_model/routing_test_support.py'
_spec = importlib.util.spec_from_file_location('_selected_direct_prior_support', _support_path)
prior = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = prior
_spec.loader.exec_module(prior)
sys.argv[:] = [sys.argv[0], *_remaining]
modules = prior.load_owner_modules()


def definitions(relative, names, *, source=None, environment=None):
    """Reuse the prior AST-only loader; never import a source module prelude."""
    return prior.definitions(relative, names, source=source, environment=environment)


class SyntheticHostControl:
    """One request/terminal handshake, NOT the real public21 Host decoder/FSM."""
    def __init__(self, job):
        self.job = job
        self.state, self.status, self.reason = 'request', None, None
        self.published, self.virtual, self.events = [], [], set()
        self.request_fires = self.terminal_fires = self.ticks = 0
        self.accepted_results = []

    def ports(self, *, reset_required=False):
        need(not reset_required, 'synthetic Host refuses reset-required launch')
        return dict(ordinary_request=self.job if self.state == 'request' else None,
                    group_request=None, owner_result_ready=self.state == 'waitDone',
                    completion=None, launch_result=None)

    def tick(self, *, request_ready=False, owner_result=None, completion_ready=False,
             result_ready=False, reset_required=False):
        edge = self.ports(reset_required=reset_required)
        edge.update(request_fire=False, owner_result_fire=False,
                    completion_fire=False, result_fire=False)
        self.ticks += 1
        need(not completion_ready and not result_ready,
             'synthetic fixture does not stand in for actual public completion decoding')
        if edge['ordinary_request'] is not None and request_ready:
            edge['request_fire'] = True
            self.request_fires += 1
            self.state = 'waitDone'
        if owner_result is not None:
            need(edge['owner_result_ready'] and owner_result.tag == self.job.tag,
                 'synthetic Host terminal handshake identity')
            self.accepted_results.append(owner_result)
            self.terminal_fires += 1
            edge['owner_result_fire'] = True
            self.state = 'complete'
        return edge


class UntouchedBanks:
    """No payload allocation; any attempted retained SRAM use fails loudly."""
    def __init__(self):
        self.reads, self.writes = {}, {}
        self.calls = 0

    def read(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('direct transport touched synthetic retained banks')

    write = read
    tick = read


class SyntheticIdleDense:
    """Only quiescence fields and idle ticks, not Dense execution evidence."""
    def __init__(self):
        self.a_banks, self.b_banks = UntouchedBanks(), UntouchedBanks()
        self.tiles = SimpleNamespace(banks=self.a_banks, idle=True, leased=False, poison=False)
        self.workspace = SimpleNamespace(base=0x80000, extent=0x10000, generation=2)
        self.clock, self.state, self.error = 0, 'idle', None
        self.lease = self.read_active = self.a_hold = self.a_rmw_pending = None
        self.pending = self.window_request = self.window_result = None
        self.drain_request = self.drain_result = self.drain_expected = None
        self.fifo = []
        self.seed_outstanding = self.group_started = self.drain_poison = False
        self.seed_state = self.write_state = 'idle'
        self.group_done = True
        self.response = None

    def ports(self):
        return dict(reset_required=False, response=self.response)

    def tick(self, **inputs):
        need(not inputs, 'synthetic Dense fixture supports idle ticks only')
        self.clock += 1
        return self.ports()


class SyntheticTrace:
    def __init__(self):
        self.events = []

    def event(self, value):
        self.events.append(value)

    def report(self):
        return dict(events=len(self.events), synthetic_control_only=True)


def synthetic_fixture(job):
    """Small physical allocation descriptions; no frozen fixture is changed."""
    allocations = {}
    for name, address, extent, readonly in (
            ('q', job.a, job.m * 1536 * 4, True),
            ('k', job.b, job.m * 256 * 4, True),
            ('v', job.c, job.m * 256 * 4, True),
            ('attention_output', job.dst, job.write_bytes, False)):
        allocations[name] = SimpleNamespace(address=address, storage_bytes=extent,
            reserved_bytes=extent, dtype=0, readonly=readonly, virtual=False)
    config = SimpleNamespace(transposed_down=True, epoch=1,
        regions=[None, None, None, SimpleNamespace(base=0x80000, limit=0x90000)],
        command=SimpleNamespace(base=0x60000), descriptor=SimpleNamespace(base=0x70000))
    def validate_spans():
        spans = sorted((a.address, a.address + a.reserved_bytes) for a in allocations.values())
        need(all(a % 64 == b % 64 == 0 for a, b in spans), 'synthetic span alignment')
        need(all(b <= c for (_, b), (c, _) in zip(spans, spans[1:])), 'synthetic span overlap')
    return SimpleNamespace(allocations=allocations, config=config, validate_spans=validate_spans,
        memory=SimpleNamespace(mappings={0x60000: bytes(64), 0x70000: bytes(64)}))


class TrafficProbe:
    """Observer only. The original owner/physical methods still execute once."""
    def __init__(self, owner, physical):
        self.owner, self.physical = owner, physical
        self.core_requests, self.core_responses, self.external_reads = [], [], []
        self.write_events, self.events, self.accepted_jobs = [], [], []
        self.pending, self.terminal_clock = None, None
        self.scratch_events = self.terminal_fires = 0
        tick = owner.tick
        read = physical.read_bytes64
        write = physical.write_event
        terminal = physical.terminal

        def observed_tick(**inputs):
            edge = tick(**inputs)
            self.scratch_events += bool(edge.get('scratch_fire')) + bool(edge.get('scratch_response_fire'))
            need(edge.get('scratch') is None, 'selected direct owner offered scratch payload/operation')
            if edge.get('job_fire'):
                self.accepted_jobs.append(inputs['job'])
            if edge.get('memory_response_fire'):
                need(self.pending is not None, 'core response without accepted core request')
                request, response = self.pending, inputs['memory_response']
                need(response.tag == request.tag, 'core response tag changed')
                self.core_responses.append((request, response))
                self.events.append(('core_response', request, owner.clock))
                self.pending = None
            if edge.get('memory_fire'):
                need(self.pending is None, 'core overlapping direct memory debt')
                request = edge['memory']
                self.pending = request
                self.core_requests.append(request)
                self.events.append(('core_request', request, owner.clock))
            if edge.get('response_fire'):
                need(self.pending is None, 'core terminal before final memory reply')
                self.terminal_fires += 1
                self.terminal_clock = owner.clock
                self.events.append(('core_terminal', edge['response'], owner.clock))
            return edge

        def observed_read(address):
            need(self.pending is not None and not self.pending.write and self.pending.address == address,
                 'external DDR read does not match the exact outstanding core read')
            data = read(address)
            self.external_reads.append((self.pending, data))
            self.events.append(('physical_read', self.pending, owner.clock))
            return data

        def observed_write(kind, value):
            if kind == 'command':
                need(self.pending is not None and self.pending.write and
                     (self.pending.address, self.pending.tag) == (value.address, value.tag),
                     'external DDR write does not match the exact outstanding core write')
            before_acked = set(physical.regions['attention_output']['acked'])
            write(kind, value)
            after_acked = set(physical.regions['attention_output']['acked'])
            need((len(after_acked) == len(before_acked) + 1) if kind == 'ack'
                 else after_acked == before_acked, 'physical ACK ledger advanced without matching ACK')
            self.write_events.append((kind, value, owner.clock))
            self.events.append(('physical_' + kind, value, owner.clock))
            need(not physical.regions['attention_output']['published'], 'output published within direct driver')

        def observed_terminal(job, result):
            need(self.terminal_clock is not None and owner.clock == self.terminal_clock,
                 'physical terminal without accepted core terminal')
            terminal(job, result)
            self.events.append(('physical_terminal', result, owner.clock))

        owner.tick = observed_tick
        physical.read_bytes64 = observed_read
        physical.write_event = observed_write
        physical.terminal = observed_terminal


def expected_requests(job):
    """Independent address-only ordering for the pinned selected QK16 schedule."""
    expected = []
    for token in range(job.m):
        for head in range(12):
            kv_head = head // 6
            for depth in range(0, 128, 16):
                expected.append((False, job.a + 4 * (token * 1536 + head * 128 + depth)))
            for first in range(0, token + 1, 16):
                for depth in range(0, 128, 16):
                    for key in range(first, min(first + 16, token + 1)):
                        expected.append((False, job.b + 4 * (key * 256 + kv_head * 128 + depth)))
            for column in range(0, 128, 16):
                for key in range(token + 1):
                    expected.append((False, job.c + 4 * (key * 256 + kv_head * 128 + column)))
                expected.append((True, job.dst + 4 * (token * 1536 + head * 128 + column)))
    return expected


def snapshot(case):
    return (case.owner.clock, case.dense.clock, case.host.ticks,
            tuple(sorted(case.physical.counts.items())), len(case.probe.core_requests),
            len(case.probe.core_responses), len(case.probe.external_reads),
            len(case.probe.write_events), tuple(sorted(case.service.counts.items())))


def apply_exact_patch(source, patch_path, target):
    """Compose pinned hunks by unique exact context, never fuzzy offset repair."""
    lines = patch_path.read_text().splitlines(keepends=True)
    selected, cursor, hunks = False, 0, 0
    while cursor < len(lines):
        line = lines[cursor]
        if line.startswith('--- a/'):
            selected = line[6:].strip() == target
            cursor += 2
            continue
        if not selected or not line.startswith('@@'):
            cursor += 1
            continue
        before, after = [], []
        cursor += 1
        while cursor < len(lines) and not lines[cursor].startswith(('@@', '--- a/')):
            line = lines[cursor]
            need(line[0] in (' ', '-', '+'), 'unsupported patch record')
            if line[0] in (' ', '-'):
                before.append(line[1:])
            if line[0] in (' ', '+'):
                after.append(line[1:])
            cursor += 1
        before, after = ''.join(before), ''.join(after)
        need(before and source.count(before) == 1, 'non-unique or missing exact patch context')
        source = source.replace(before, after, 1)
        hunks += 1
    need(hunks > 0, 'patch has no selected target')
    return source


def load_runtime():
    raw_patch = SOURCE_PACKAGE / 'raw_kv_public/public_execution.patch'
    public_path = 'ffn_public/execute_numeric.py'
    public_source = apply_exact_patch((SOURCE_PACKAGE / public_path).read_text(), raw_patch,
        'candidates/qwen2_resident_matrix/' + public_path)
    need(hashlib.sha256(public_source.encode()).hexdigest() ==
         'cdf203f9e7113db7fb29dd290ea6355adf3f7df86e145e5828daf13a5ac51b73',
         'raw-public PublicExecution postimage mismatch')
    public_source = apply_exact_patch(public_source, HERE / 'direct_guard.patch',
        'candidates/qwen2_resident_matrix/' + public_path)
    need(hashlib.sha256(public_source.encode()).hexdigest() ==
         'e67f3bf53dec946e0ee423f591ecf345f52636ea00fd8796d17312df17a714f8',
         'selected-direct PublicExecution postimage mismatch')
    driver_path = 'ffn_public/fullgraph_execution.py'
    driver_source = apply_exact_patch((SOURCE_PACKAGE / driver_path).read_text(), raw_patch,
        'candidates/qwen2_resident_matrix/' + driver_path)
    need(hashlib.sha256(driver_source.encode()).hexdigest() ==
         'bdc4218fcc6136c1c1c2b6d9c15338b539e4b6abe46b96bd6baeb93379a6e9ab',
         'raw-public physical driver postimage mismatch')
    environment = dict(Counter=Counter, asdict=asdict, dataclass=dataclass, time=time,
        SimpleNamespace=SimpleNamespace, require=prior.matrix.require)
    public = definitions(public_path, ('PublicExecution',), source=public_source,
                         environment=environment)
    driver = definitions(driver_path, ('execute_attention_owner',), source=driver_source,
        environment={**environment, 'MemoryResponse': modules.prefix.MemoryResponse})
    direct_path = HERE / 'direct_transport.py'
    direct = definitions('production_qk16_model/direct_transport.py',
        ('require', 'dense_retired', 'no_scratch', 'DirectBinding', 'bind', 'run'),
        source=direct_path.read_text(), environment={**environment,
            'install_schedule': modules.entry.install,
            'Qk16LegacyPvClient': modules.routing.Qk16LegacyPvClient,
            'execute_attention_owner': driver.execute_attention_owner})
    prior.EXTRACTED['production_qk16_model/direct_transport.py']['source'] = str(direct_path)
    canonical = 'candidates.qwen2_resident_matrix.production_qk16_model.direct_transport'
    parent = canonical.rpartition('.')[0]
    while parent:
        prior._package(parent)
        parent = parent.rpartition('.')[0]
    sys.modules[canonical] = direct
    sys.modules['candidates.qwen2_resident_matrix.production_qk16_model.schedule'] = modules.selected
    # This dummy type is used only by PhysicalMemory's original typed-wire
    # distinction. No ordinary Dense write is produced or accepted by the test.
    opaque_dense_wire = type('UnusedSyntheticDenseWriteBeat', (), {})
    execution = SimpleNamespace(numeric=SimpleNamespace(
        model=SimpleNamespace(down=SimpleNamespace(WriteBeat=opaque_dense_wire))))
    physical = definitions('ffn_public/prefix_execution.py', ('PhysicalMemory',),
        environment={**environment, 'struct': struct, 'hashlib': hashlib,
                     'execution': execution, 'FULL_MASK': (1 << 64) - 1,
                     'SENTINEL': struct.pack('<I', 0xa5963cc3)})
    return SimpleNamespace(public=public, driver=driver, direct=direct,
                           physical=physical, public_source=public_source,
                           driver_source=driver_source)


runtime = load_runtime()


def make_case():
    _, service, scalar, owner, job = prior.make_owner(2, schedule=False)
    fixture = synthetic_fixture(job)
    readonly = {name: (lambda offset: struct.pack('<16I', *([0x3f800000] * 16)))
                for name in ('q', 'k', 'v')}
    physical = runtime.physical.PhysicalMemory(fixture, readonly)
    memory = physical.metadata_port()
    frontend = SimpleNamespace(memory=memory, port=SimpleNamespace(memory=memory),
        config=fixture.config, launch=lambda host: host.state == 'request')
    host, dense, trace = SyntheticHostControl(job), SyntheticIdleDense(), SyntheticTrace()
    prefix = modules.prefix.PrefixOwner(scalar, max_tokens=128)
    x = runtime.public.PublicExecution(frontend, dense, trace, time.monotonic() + 15,
        host=host, prefix_owner=prefix, attention_owner=owner, matrix_service=service)
    probe = TrafficProbe(owner, physical)
    return SimpleNamespace(x=x, owner=owner, job=job, service=service, scalar=scalar,
        host=host, dense=dense, prefix=prefix, physical=physical, probe=probe,
        fixture=fixture, frontend=frontend)
