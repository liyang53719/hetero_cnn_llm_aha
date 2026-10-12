"""Continue the public21 launch through pc0–9 on one physical memory map.

The Matrix instance and its banks are the same objects as the retained FFN
path. Prefix scalar recipes use the source-bound software service. Neither
Python events nor host CPU duration estimate hardware clocks/utilization.
"""
from collections import Counter
from dataclasses import asdict
import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import time

from . import execute_numeric as execution
from .prefix_owners import MemoryResponse

require = execution.require
FULL_MASK = (1 << 64) - 1
SENTINEL = struct.pack('<I', 0xa5963cc3)


class PhysicalMemory:
    """Unique physical-address allocation index shared by metadata and owners.

    Readonly providers are input byte sources. Writable allocations are sentinel
    backed and become readable only after actual accepted stores, every ACK,
    the owner terminal, and the public Host completion. KV views never allocate
    storage and resolve into the same parent allocation.
    """
    def __init__(self, fixture, readonly):
        self.fixture = fixture
        fixture.validate_spans()
        self.regions, self.pending = {}, None
        self.counts, self.read_regions = Counter(), Counter()
        self.published_hashes = {}
        for name, allocation in fixture.allocations.items():
            region = dict(base=allocation.address, extent=allocation.storage_bytes,
                reserved=allocation.reserved_bytes, dtype=allocation.dtype,
                readonly=allocation.readonly, virtual=allocation.virtual,
                provider=readonly.get(name), data=None, written=set(), acked=set(),
                records=[], terminal=False, published=False)
            if not allocation.readonly:
                region['data'] = bytearray(SENTINEL * ((allocation.storage_bytes + 128) // 4))
            self.regions[name] = region
        unknown = set(readonly) - {n for n, r in self.regions.items() if r['readonly']}
        require(not unknown, 'readonly input provider names are not original allocations')
        for name, table in (('command_table', fixture.config.command), ('descriptor_table', fixture.config.descriptor)):
            raw = bytes(fixture.memory.mappings[table.base])
            self.regions[name] = dict(base=table.base, extent=len(raw), reserved=len(raw),
                dtype=7, readonly=True, virtual=False, provider=lambda offset, raw=raw: raw[offset:offset + 64])

    def region(self, address, size=64):
        require(type(address) is int and type(size) is int and size > 0 and address % 64 == 0,
                'physical access is unaligned or has an invalid extent')
        matches = [(n, r) for n, r in self.regions.items()
                   if r['base'] <= address and address + size <= r['base'] + r['reserved']]
        require(len(matches) == 1,
                'physical access is unaligned, unmapped or ambiguous')
        name, region = matches[0]
        require(address + size <= region['base'] + region['extent'], 'physical access entered reservation guard')
        require(not region['virtual'], 'physical access to virtual allocation')
        return name, region

    def read_bytes64(self, address):
        name, r = self.region(address)
        offset = address - r['base']
        if r['readonly']:
            require(callable(r['provider']), 'missing original readonly input: ' + name)
            raw = r['provider'](offset)
            require(isinstance(raw, bytes) and len(raw) == 64, 'readonly beat extent')
        else:
            require(r['published'] and address in r['acked'], 'read before ACK and public publication: ' + name)
            raw = bytes(r['data'][64 + offset:128 + offset])
        self.counts['read_bytes'] += 64
        self.read_regions[name] += 64
        return raw

    def read64(self, address):
        name, r = self.region(address)
        return name, struct.unpack('<32H' if r['dtype'] == 5 else '<16I', self.read_bytes64(address))

    def metadata_port(self):
        # RecordPort and numeric owners use this one allocation index.
        return SimpleNamespace(read64=self.read_bytes64, physical_memory=self)

    def raw(self, address, extent):
        _, r = self.region(address, extent)
        require(address == r['base'] and extent == r['extent'], 'raw audit must cover one exact allocation')
        if r['readonly']:
            return b''.join(r['provider'](i) for i in range(0, extent, 64))
        return bytes(r['data'][64:-64])

    def dense_source(self, job):
        _, r = self.region(job.a, job.m * job.k * 4)
        return execution.down_driver.DenseSource(job.a, job.m * job.k * 4,
            'readonly' if r['readonly'] else 'published',
            ready=lambda: callable(r['provider']) if r['readonly'] else r['published'],
            raw=lambda: self.raw(job.a, job.m * job.k * 4), write_acks=lambda: tuple(r['records']))

    def write_event(self, kind, value):
        if kind == 'command':
            command = value
            require(self.pending is None and 1 <= command.beats <= 16 and
                    command.address // 1024 == (command.address + command.beats * 64 - 1) // 1024,
                    'physical write overlap/burst boundary')
            name, r = self.region(command.address, command.beats * 64)
            require(not r['readonly'] and not r['published'] and not r['terminal'], 'write to immutable/published allocation')
            self.pending = [name, command, 0]
            self.counts['write_commands'] += 1
        elif kind == 'data':
            require(self.pending is not None, 'physical data without accepted command')
            name, command, index = self.pending
            r = self.regions[name]
            # The inherited ordinary Dense wire has words/last only and always
            # writes one complete 512-bit beat. The typed drain/prefix wire has
            # an explicit mask. Do not silently treat arbitrary missing masks
            # as full writes.
            mask = FULL_MASK if type(value) is execution.numeric.model.down.WriteBeat else getattr(value, 'mask', None)
            require(index < command.beats and mask == FULL_MASK and len(value.words) == 16 and
                    value.last == (index + 1 == command.beats), 'physical write data mask/last/extent')
            address = command.address + index * 64
            require(address not in r['written'], 'duplicate physical write')
            r['data'][64 + address - r['base']:128 + address - r['base']] = struct.pack('<16I', *value.words)
            r['written'].add(address)
            self.pending[2] += 1
            self.counts['write_data_bytes'] += 64
        elif kind == 'ack':
            require(self.pending is not None, 'physical ACK without accepted command')
            name, command, index = self.pending
            require(index == command.beats and value.tag == command.tag and not value.error and
                    value.nbytes == command.beats * 64, 'physical ACK tag/status/byte fence')
            r = self.regions[name]
            addresses = set(range(command.address, command.address + command.beats * 64, 64))
            require(not addresses.intersection(r['acked']), 'duplicate physical ACK')
            r['acked'].update(addresses)
            r['records'].append((command, value))
            self.pending = None
            self.counts['write_ack_bytes'] += value.nbytes
            self.counts['write_acks'] += 1
        else:
            raise ValueError('unknown physical write event')

    def terminal(self, job, result):
        tag, status, nbytes = ((result.tag, result.status, result.write_bytes) if hasattr(result, 'tag') else result)
        require(tag == job.tag and status is None and nbytes == job.write_bytes and self.pending is None,
                'physical terminal tag/status/byte fence')
        _, r = self.region(job.dst, job.write_bytes)
        require(job.dst == r['base'] and job.write_bytes == r['extent'] and
                r['acked'] == r['written'] == set(range(r['base'], r['base'] + r['extent'], 64)),
                'physical terminal before complete exactly-once ACK coverage')
        require(r['data'][:64] == SENTINEL * 16 and r['data'][-64:] == SENTINEL * 16,
                'physical output canary corruption')
        r['terminal'] = True

    def publish(self, job, host):
        name, r = self.region(job.dst, job.write_bytes)
        require(r['terminal'] and (job.dst, job.dst + job.write_bytes) in host.published and
                host.status is None, 'physical publish before public completion')
        self.check_coexistence()
        r['published'] = True
        self.published_hashes[name] = hashlib.sha256(r['data'][64:-64]).hexdigest()

    def check_coexistence(self, *, unpublished_pristine=False):
        for name, r in self.regions.items():
            if r['readonly']:
                continue
            require(r['data'][:64] == r['data'][-64:] == SENTINEL * 16,
                    'physical allocation canary changed: ' + name)
            if r['published']:
                require(hashlib.sha256(r['data'][64:-64]).hexdigest() == self.published_hashes[name],
                        'prior published output changed: ' + name)
            elif unpublished_pristine:
                require(not r['written'] and not r['acked'] and not r['terminal'] and
                        r['data'][64:-64] == SENTINEL * (r['extent'] // 4),
                        'unexecuted suffix or virtual allocation changed: ' + name)

    def dense_sink(self, job):
        def event(kind, value):
            if kind == 'terminal':
                self.terminal(job, value)
            else:
                self.write_event(kind, value)
        return event

    def report(self):
        return dict(accepted=dict(self.counts), reads_by_allocation=dict(self.read_regions),
            outputs={name: dict(bytes=r['extent'], written_bytes=len(r['written']) * 64,
                ack_bytes=len(r['acked']) * 64, terminal=r['terminal'], published=r['published'],
                sha256=hashlib.sha256(r['data'][64:-64]).hexdigest())
                for name, r in self.regions.items() if not r['readonly']})


def execute_prefix_owner(x, memory, job, *, final_ack_stall=5):
    """Service every accepted 64B request and its real response in this launch."""
    backend = x.prefix_owner
    counts, pending, held = Counter(), None, None
    remaining, result = final_ack_stall, None
    require(x.prefix_edge(job=job)['job_fire'], 'public prefix job was not accepted')
    while result is None:
        require(time.monotonic() <= x.deadline, 'prefix memory driver exceeded host budget')
        pp = backend.ports()
        inputs = dict(memory_ready=counts['ticks'] % 5 != 0)
        response = None
        if pending is not None:
            q, data = pending
            if q.write and backend.ack_bytes + 64 == job.write_bytes and remaining:
                require(pp['response'] is None and
                        (job.dst, job.dst + job.write_bytes) not in x.host.published,
                        'prefix output published before final ACK')
                remaining -= 1
                counts['final_ack_stall'] += 1
            else:
                response = MemoryResponse(q.tag, data)
                inputs['memory_response'] = response
        edge = x.prefix_edge(**inputs)
        counts['ticks'] += 1
        if held is not None:
            require(edge['memory'] == held, 'held prefix request changed')
        held = edge['memory'] if edge['memory'] is not None and not inputs['memory_ready'] else None
        if edge['memory_response_fire']:
            q, _ = pending
            if q.write:
                memory.write_event('ack', SimpleNamespace(tag=response.tag, error=response.error, nbytes=response.nbytes))
            pending = None
            counts['responses'] += 1
        if edge['memory_fire']:
            require(pending is None, 'prefix shared port accepted overlapping transactions')
            q = edge['memory']
            if q.write:
                memory.write_event('command', SimpleNamespace(address=q.address, beats=1, tag=q.tag))
                memory.write_event('data', SimpleNamespace(words=q.words, mask=q.mask, last=True))
                data = None
            else:
                data = memory.read_bytes64(q.address)
            pending = q, data
            counts['requests'] += 1
        if edge['response_fire']:
            result = edge['response']
            require(pending is None and result.status is None and x.host.state == 'complete',
                    'prefix owner error or premature terminal: ' + str(result))
    memory.terminal(job, result)
    return dict(job=asdict(job), result=asdict(result), accepted=dict(counts), backend=backend.report())


def execute_public_prefix(x, memory, lib, output):
    """Execute the first ten commands; leave pc10 pending in the same launch."""
    output = Path(output)
    require(len(x.host.program) == 21 and x.host.pc == 0, 'full public21 image from pc0 required')
    require(getattr(x.frontend.memory, 'physical_memory', None) is memory and
            x.frontend.port.memory is x.frontend.memory and
            x.frontend.config == memory.fixture.config,
            'public metadata and numeric owners must share the identical physical map and launch')
    reports = []
    kinds = ('Norm', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'Rope', 'Dense', 'Bias', 'KvAppend')
    for pc in range(10):
        ports = x.advance_to_request()
        job = ports['ordinary_request']
        require(job is not None and ports['group_request'] is None and (job.tag & 0xffff) == pc and
                job.kind == kinds[pc],
                'public prefix request order')
        if job.kind == 'Dense':
            path = output / ('pc%d_dense' % pc)
            path.mkdir()
            dense_job = execution.numeric.decode_job(job)
            trace = execution.numeric.CappedTrace()
            report, actual = execution.down_driver.execute_dense(execution.numeric.model, x.owner, lib,
                memory, dense_job, path, x.deadline, trace, a_source=memory.dense_source(dense_job),
                output_event=memory.dense_sink(dense_job), owner_tick=x.ordinary_edge)
            require(report['prefix']['completed_sweeps'] == report['prefix']['ack_bytes'] == 0,
                    'QKV prefix cannot use an unbound external prefix workspace')
            require(memory.raw(job.dst, job.write_bytes) == actual.raw(), 'shared DDR and actual Dense writes differ')
            x.accept_down_terminal(report)
        else:
            report = execute_prefix_owner(x, memory, job)
        x.publish_completions((pc,))
        memory.publish(job, x.host)
        if job.kind == 'Dense':
            x.retire_ordinary_bookkeeping()
        reports.append(dict(pc=pc, kind=job.kind, report=report))
    require(x.host.pc == x.host.completed == x.host.jobs == 10 and x.host.state == 'decode' and
            x.host.result is None and x.owner.state == x.prefix_owner.state == 'idle',
            'prefix checkpoint is not quiescent after ten actual public completions')
    memory.check_coexistence(unpublished_pristine=True)
    return dict(status='PUBLIC21_PREFIX_PC0_9_SOFTWARE_ONLY', reports=reports,
        host=x.report(), memory=memory.report(), full_block_executed=False,
        attention_suffix_executed=False, rtl_executed=False, hardware_cycles=None,
        full_wall_mac_utilization=None, native_acceptance='UNCHANGED_FAIL_POLICY_PENDING')
