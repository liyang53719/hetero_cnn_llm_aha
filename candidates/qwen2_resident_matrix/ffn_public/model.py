"""Public-byte FFN frontend, as a serial software transaction specification.

The retained Host/coordinator own admission, liveness, scan and completion.
This adapter fetches the actual public 128-bit words using physical 64-byte
reads. No command/tensor/policy cache or opaque decoded-success input exists.
RecordReader ticks describe ready/valid events, NOT Chisel execution or cycles.
The default execution subset is the explicitly named FFN4 subprogram. The
optional legacy-prefix policy decodes the existing public21 image through
pc0--9; its remaining Attention/Add suffix is not accepted by this subset.
"""
from dataclasses import dataclass, replace
import importlib.util
from math import prod
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ffn_public_group', HERE.parent / 'ffn_group/model.py')
group = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = group
spec.loader.exec_module(group)
NULL, LIMIT, U64 = group.NULL, group.LIMIT, group.U64
Rejected, Region = group.Rejected, group.Region


def align64(n):
    return (n + 63) & ~63


@dataclass(frozen=True)
class Table:
    base: int
    limit: int
    count: int


@dataclass(frozen=True)
class LaunchConfig:
    command: Table
    descriptor: Table
    regions: tuple
    epoch: int = 7
    transposed_down: bool = True

    @property
    def ordinary_regions(self):
        return self.regions[:3] if self.transposed_down else self.regions

    def validate(self, max_commands=64):
        c, d, regions = self.command, self.descriptor, self.regions
        if not (group.uint(self.epoch, 16) and len(regions) == 4
                and 0 < c.count <= max_commands and 0 < d.count <= NULL):
            raise Rejected('Bounds', 'launch counts/epoch/regions')
        for t in (c, d):
            if not (group.uint(t.base, 64) and group.uint(t.limit, 64)
                    and t.base % 64 == t.limit % 64 == 0 and t.base < t.limit <= LIMIT
                    and t.base + align64(t.count * 16) <= t.limit):
                raise Rejected('Bounds', 'launch table extent/alignment')
            if not any(r.read and not r.write and r.base <= t.base < t.limit <= r.limit
                       for r in self.ordinary_regions):
                raise Rejected('Bounds', 'launch tables must be readonly')
        if group.overlap(c.base, c.limit, d.base, d.limit):
            raise Rejected('Bounds', 'launch table overlap')
        for r in regions:
            if not (group.uint(r.base, 64) and group.uint(r.limit, 64)):
                raise Rejected('Bounds', 'launch region integers')
            if r.base == r.limit and not r.read and not r.write:
                continue
            if not (r.base < r.limit <= LIMIT and r.base % 64 == r.limit % 64 == 0):
                raise Rejected('Bounds', 'launch region extent/alignment')
        for i, a in enumerate(regions):
            for b in regions[i + 1:]:
                if a.base < a.limit and b.base < b.limit and group.overlap(a.base, a.limit, b.base, b.limit):
                    raise Rejected('Bounds', 'launch region overlap')
        if self.transposed_down:
            w = regions[3]
            if not (w.read and w.write and w.limit - w.base >= 64
                    and all(not group.overlap(w.base, w.limit, t.base, t.limit) for t in (c, d))):
                raise Rejected('Bounds', 'launch reserved transposed workspace')


@dataclass(frozen=True)
class RecordRequest:
    table: Table
    index: int
    request_tag: int


@dataclass(frozen=True)
class MemoryRequest:
    address: int
    tag: int


@dataclass(frozen=True)
class MemoryResponse:
    data: bytes
    tag: int
    error: bool = False


@dataclass(frozen=True)
class RecordResult:
    data: int
    request_tag: int
    status: str | None = None


class RecordReader:
    """Five-state Record128Reader with single outstanding physical beat."""
    def __init__(self):
        self.state = 'idle'
        self.poison = False
        self.serial = 0
        self.address = self.slot = 0
        self.result = None

    def ports(self):
        return dict(request_ready=self.state == 'idle' and not self.poison,
                    memory=MemoryRequest(self.address, self.serial) if self.state == 'issue' else None,
                    response_ready=self.state == 'waitResponse',
                    result=self.result if self.state == 'reply' else None,
                    reset_required=self.poison, state=self.state)

    def tick(self, *, request=None, memory_ready=False, response=None, result_ready=False, reset=False):
        p = self.ports()
        p.update(request_fire=False, memory_fire=False, response_fire=False, result_fire=False)
        if reset:
            self.__init__()
            return p
        state = self.state
        if request is not None and p['request_ready']:
            p['request_fire'] = True
            t, i = request.table, request.index
            span = align64(t.count * 16)
            end, beat = t.base + span, t.base + (i // 4) * 64
            legal = (group.uint(t.base, 64) and group.uint(t.limit, 64)
                     and group.uint(t.count, 25) and 0 < t.count <= NULL
                     and group.uint(i, 24) and i != NULL and i < t.count
                     and t.base % 64 == 0 and end <= t.limit <= LIMIT
                     and end > t.base and beat + 64 <= end and group.uint(request.request_tag, 64))
            self.result = RecordResult(0, request.request_tag)
            if not legal:
                self.result = replace(self.result, status='Bounds')
                self.state = 'reply'
            elif self.serial == U64:
                self.result = replace(self.result, status='Protocol')
                self.poison, self.state = True, 'reply'
            else:
                self.address, self.slot = beat, i % 4
                self.serial += 1
                self.state = 'issue'
        if state == 'issue' and memory_ready:
            p['memory_fire'] = True
            self.state = 'waitResponse'
        if state == 'waitResponse' and response is not None:
            p['response_fire'] = True
            if response.tag != self.serial:
                self.result = replace(self.result, status='Protocol')
                self.poison = True
            elif response.error:
                self.result = replace(self.result, status='Memory')
                self.poison = True
            else:
                if len(response.data) != 64:
                    raise ValueError('physical metadata response must be exactly 64 bytes')
                offset = self.slot * 16
                self.result = replace(self.result, data=int.from_bytes(response.data[offset:offset + 16], 'little'))
            self.state = 'reply'
        if state == 'reply' and result_ready:
            p['result_fire'] = True
            self.state = 'locked' if self.poison else 'idle'
        return p


class MetadataMemory:
    """Addressed public table bytes; no tensor payload or decoded objects."""
    def __init__(self, mappings=()):
        self.mappings = {}
        for base, data in mappings:
            if (not group.uint(base, 56) or base % 64 or not len(data) or len(data) % 64
                    or base + len(data) > LIMIT):
                raise ValueError('metadata mapping must contain aligned whole 64-byte beats below 56-bit limit')
            if any(group.overlap(base, base + len(data), a, a + len(raw)) for a, raw in self.mappings.items()):
                raise ValueError('duplicate/overlapping physical metadata mapping')
            self.mappings[base] = bytearray(data)
        self.reads = []
        self.before_read = None

    def read64(self, address):
        if self.before_read is not None:
            self.before_read(self, address)
        self.reads.append(address)
        if address % 64:
            raise ValueError('unaligned physical metadata read')
        for base, data in self.mappings.items():
            if base <= address and address + 64 <= base + len(data):
                return bytes(data[address - base:address - base + 64])
        raise KeyError('unmapped physical metadata beat')

    def write_word(self, table, index, word):
        """Test/fixture mutation between transactions, never a decoded injection."""
        data = self.mappings[table.base]
        if not group.uint(word, 128) or not 0 <= index < table.count or index * 16 + 16 > len(data):
            raise ValueError('mutation must target one mapped public record')
        data[index * 16:index * 16 + 16] = word.to_bytes(16, 'little')


class RecordPort:
    """Synchronous caller drives genuine RecordReader acceptance events.

    response_filter/result_filter are fault injection ports only. They can
    corrupt accepted transport responses/tags; they cannot supply tensors.
    """
    def __init__(self, memory):
        self.memory, self.machine = memory, RecordReader()
        self.trace = []
        self.response_filter = self.result_filter = None

    def read(self, table, index, request_tag, *, purpose):
        request = RecordRequest(table, index, request_tag)
        if not self.machine.ports()['request_ready']:
            raise Rejected('Protocol', 'record reader quarantined or busy')
        self.machine.tick(request=request)
        p = self.machine.ports()
        event = dict(purpose=purpose, index=index, request_tag=request_tag, address=None,
                     slot=index % 4, serial=None, physical_bytes=0)
        if p['memory'] is not None:
            q = p['memory']
            e = self.machine.tick(memory_ready=True)
            assert e['memory_fire']
            try:
                response = MemoryResponse(self.memory.read64(q.address), q.tag)
            except KeyError:
                response = MemoryResponse(bytes(64), q.tag, True)
            if self.response_filter is not None:
                response = self.response_filter(request, response)
            self.machine.tick(response=response)
            event.update(address=q.address, serial=q.tag, physical_bytes=64)
        result = self.machine.ports()['result']
        if self.result_filter is not None:
            result = self.result_filter(request, result)
        self.machine.tick(result_ready=True)
        event.update(status=result.status, word=f'{result.data:032x}')
        self.trace.append(event)
        if result.status:
            raise Rejected(result.status, 'physical Record128 terminal')
        if result.request_tag != request_tag:
            raise Rejected('Protocol', 'Record128 request tag mismatch')
        return result.data


@dataclass(frozen=True)
class DecodedTensor(group.Tensor):
    prefix_indices: tuple = ()


class TypedRootReader:
    def __init__(self, port, config):
        self.port, self.config = port, config
        self.regions = config.ordinary_regions
        self.descriptor_count = config.descriptor.count
        self.reads = []

    def read(self, root, write=False):
        self.reads.append((root, write))
        indices, index, words = [], root, []
        for step in range(3):
            word = self.port.read(self.config.descriptor, index, step, purpose='tensor_prefix')
            kind, nxt = word & 255, (word >> 32) & NULL
            if (word >> 8) & 0xffffff or index in indices:
                raise Rejected('Malformed', 'typed prefix flags/subtype/revisit')
            if kind != step + 1:
                raise Rejected('Unsupported', 'typed prefix record kind')
            indices.append(index)
            words.append(word)
            if step == 0:
                dtype, rank = (word >> 108) & 15, (word >> 116) & 15
                if ((word >> 104) & 15 or (word >> 112) & 15
                        or dtype not in (5, 7) or not 1 <= rank <= 4):
                    raise Rejected('Unsupported', 'typed dtype/rank/layout/memory space')
                address = ((word >> 56) & ((1 << 48) - 1)) | ((word >> 120) << 48)
            index = nxt
        dims = tuple((words[1] >> (56 + 18 * i)) & ((1 << 18) - 1) for i in range(4))
        strides = tuple((words[2] >> (56 + 24 * i)) & NULL for i in range(3))
        count = prod(dims)
        end = address + align64(count * (2 if dtype == 5 else 4))
        if (any(d <= 0 or (i >= rank and d != 1) for i, d in enumerate(dims))
                or count > 0xffffffff or address % 64 or end > LIMIT or end <= address):
            raise Rejected('Bounds', 'typed dimensions/full padded allocation')
        if any(s & (1 << 23) or s != prod(dims[i + 1:]) for i, s in enumerate(strides)):
            raise Rejected('Unsupported', 'typed element strides')
        tensor = DecodedTensor(address, dims[:rank], dtype, index, None, tuple(indices))
        if not any((r.write if write else r.read) and r.base < r.limit and r.contains(tensor)
                   for r in self.regions):
            raise Rejected('Permission', 'typed full padded allocation permission')
        return tensor


class PublicFrontend:
    def __init__(self, memory, config):
        self.memory, self.config = memory, config
        self.port = RecordPort(memory)
        self.reader = TypedRootReader(self.port, config)
        self.command_reads, self.policy_reads = [], []
        self.current_pc = 0

    def launch(self, host):
        if host.state != 'idle' or host.poison or self.port.machine.poison:
            return False
        self.config = replace(self.config, regions=tuple(self.config.regions))
        self.reader = TypedRootReader(self.port, self.config)
        error = None
        try:
            self.config.validate(host.max_commands)
        except Rejected as exc:
            error = exc
        accepted = host.launch(range(self.config.command.count), self.reader, {},
                               epoch=self.config.epoch, frontend=self)
        if accepted and error:
            # Host launch admission failure issues no metadata and is retryable.
            host.status, host.reason, host.state = error.status, str(error), 'finish'
            host.result = dict(status=error.status, completed=0, jobs=0,
                               useful_macs=0, executed_macs=0, write_bytes=0)
        return accepted

    def fetch_command(self, pc):
        tag = (self.config.epoch << 48) | (pc << 32)
        word = self.port.read(self.config.command, pc, tag, purpose='command')
        self.current_pc = pc
        self.command_reads.append(pc)
        # Deliberately extract public bit fields instead of enum-validating
        # Command128.from_bytes: the root scanner must see unknown opcodes too.
        return group.Command(word & 255, (word >> 8) & 7, (word >> 56) & NULL,
                             (word >> 80) & NULL, (word >> 104) & NULL,
                             (word >> 24) & 0xffff, (word >> 40) & 0xffff,
                             (word >> 11) & 0x1fff)

    def validate_command(self, command):
        if any(root == NULL or not 0 <= root < self.config.descriptor.count for root in command.roots):
            raise Rejected('Malformed', 'public primary root bounds')

    def _readonly(self, tensor):
        return any(r.read and not r.write and r.contains(tensor) for r in self.reader.regions)

    def _readwrite(self, tensor):
        return any(r.read and r.write and r.contains(tensor) for r in self.reader.regions)

    def validate_resident_gate(self, tensors):
        a, b, d = tensors
        if not self._readonly(b) or not self._readwrite(d) or a.overlaps(b):
            raise Rejected('Permission', 'resident Gate allocation permissions/alias')

    def validate_resident_up(self, tensors, gate_tensors):
        a, b, d = tensors
        ga, gb, gd = gate_tensors
        if not a.same_allocation(ga):
            raise Rejected('Dependency', 'Up requires exact A allocation')
        operands = (ga, gb, gd, b, d)
        if (not self._readonly(b) or not self._readwrite(d)
                or any(x.overlaps(y) for i, x in enumerate(operands) for y in operands[i + 1:])):
            raise Rejected('Permission', 'resident Up allocation permissions/alias')

    def read_policy(self, command, tensors):
        if command.opcode == 0x41:
            # Original KV_APPEND has no policy record and never reads NULL.
            return group.Policy('kv', valid=tensors[0].tail == NULL)
        index, visited = tensors[0].tail, []
        prefixes = {i for t in tensors for i in t.prefix_indices}
        tag = (self.config.epoch << 48) | (self.current_pc << 32)
        words = []
        for slot in range(2 if command.opcode == 0x20 else 1):
            word = self.port.read(self.config.descriptor, index, tag, purpose='policy')
            self.policy_reads.append((self.current_pc, index))
            if (word >> 8) & 0xffffff or index in visited or index in prefixes:
                raise Rejected('Malformed', 'policy flags/subtype/prefix/revisit')
            words.append(word)
            visited.append(index)
            kind, nxt = word & 255, (word >> 32) & NULL
            if command.opcode == 0x20 and slot == 0 and (kind != 0x10 or nxt == NULL):
                raise Rejected('Malformed', 'matrix policy chain first record')
            if command.opcode == 0x20 and slot == 1 and nxt != NULL:
                raise Rejected('Unsupported', 'legacy FFN excludes extended policy profiles')
            index = nxt
        if command.opcode == 0x20:
            p, aux = words[0] >> 56, words[1]
            valid = ((words[0] & 255) == 0x10 and p >> 56 == 0
                     and (aux & 255) == 0x12 and aux >> 56 == 0x4000040024ffffff)
            return group.Policy('matrix', p & 0xffff, (p >> 16) & 0xffff,
                                (p >> 32) & 0xffffff, valid=valid)
        word, p = words[0], words[0] >> 56
        expected = command.opcode | (2 << 16) | (1 << 24) | (7 << 32) | (7 << 36) | (16 << 40)
        return group.Policy('sfu', opcode=p & 0xffff, inputs=(p >> 16) & 255,
                            valid=(word & 255) == 0x20 and index == NULL and p == expected)
