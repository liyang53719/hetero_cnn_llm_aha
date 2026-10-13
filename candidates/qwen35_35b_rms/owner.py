"""H2048 memory-fed RMS software owner over the original scalar/transport.

The three retained banks remain 1024 BF16 entries each. During the reduction,
32 FP32 residue sums occupy the first 64 BF16 entries of the output bank. The
input is read in two chunks, then read again alongside weight chunks once the
inverse is available. No diagnostic/reference array is an arithmetic input.
This is a model-only schedule; physical allocation and control QoR are unproven.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import struct

from ..qwen35_gdn_prefill import rms_owner as base
from . import reference

ROOT = reference.ROOT
WIDTH, ROW_BYTES, CHUNK_WORDS, CHUNK_BYTES, BEAT_BYTES = 2048, 4096, 1024, 2048, 64
TypedMemory, SharedScalar = base.TypedMemory, base.SharedScalar
MemoryRequest, MemoryResponse, RmsResult = base.MemoryRequest, base.MemoryResponse, base.RmsResult
ArithmeticFault, word, finite, sha, require = base.ArithmeticFault, base.word, base.finite, base.sha, base.require


class ReductionPolicy(str, Enum):
    Torch210CpuDefault2048 = 'torch210_cpu_default2048'


def source_identity(policy, root=ROOT):
    """Bind this path, its reference and the unchanged committed scalar source.

    Source association does not inherit acceptance from the legacy owner or
    imply that the official component or RTL ran during this owner invocation.
    """
    policy, root = ReductionPolicy(policy), Path(root)
    original = base.source_identity(base.ReductionPolicy.LegacyAscending, root)
    sources = dict(original['source_sha256'])
    for name, digest in ((reference.SOURCE, reference.SOURCE_SHA),
                         (reference.CONFIG, reference.CONFIG_SHA)):
        require(sha((root / name).read_bytes()) == digest, 'H2048 official source/config drift')
        sources[name] = digest
    for name in ('candidates/qwen35_35b_rms/owner.py',
                 'candidates/qwen35_35b_rms/reference.py',
                 'candidates/qwen35_35b_rms/formula.py',
                 'candidates/qwen35_gdn_prefill/rms_owner.py',
                 'candidates/qwen35_gdn_prefill/typed_dense.py'):
        sources[name] = sha((root / name).read_bytes())
    return dict(policy=policy.value, source_sha256=sources,
                model_revision=reference.MODEL_REVISION,
                transformers_revision=reference.TRANSFORMERS_REVISION,
                official_class_sha256=reference.CLASS_SHA,
                implementation_sha256=sources['candidates/qwen35_35b_rms/owner.py'],
                torch_policy_model_only=True, official_component_executed=False,
                historical_m1_pass_inherited=False, candidate_mapping_verified=False,
                native_acceptance=False, full_native_forward=False, rtl_executed=False)


@dataclass(frozen=True)
class RmsJob:
    tag: int
    input: int
    weight: int
    output: int
    tokens: int
    policy: ReductionPolicy = ReductionPolicy.Torch210CpuDefault2048
    width: int = WIDTH
    dtype: str = 'bf16'

    @property
    def write_bytes(self):
        return self.tokens * ROW_BYTES

    def validate(self):
        require(type(self.tag) is int and 0 <= self.tag < 1 << 32, 'job tag domain')
        require(type(self.tokens) is int and 1 <= self.tokens <= 128 and
                type(self.width) is int and self.width == WIDTH and
                type(self.dtype) is str and self.dtype == 'bf16', 'packed BF16 H2048/M1..128 required')
        ReductionPolicy(self.policy)
        spans = ((self.input, self.write_bytes), (self.weight, ROW_BYTES), (self.output, self.write_bytes))
        for address, extent in spans:
            require(type(address) is int and address >= 0 and address % BEAT_BYTES == 0 and
                    address + extent <= 1 << 56, 'aligned 56-bit physical span required')
        require(all(a + n <= b or b + m <= a for i, (a, n) in enumerate(spans)
                    for b, m in spans[:i]), 'input, weight and output spans must be disjoint')


class RmsOwner(base.RmsOwner):
    """Inherit admission, scalar ownership, drain, poison and held completion.

    Observer callbacks receive the inherited immutable host-only snapshots,
    plus the explicit sqrt node named ``root``. Return values are ignored.
    Snapshots, row_scalars and Python transport objects are diagnostic host
    storage, not physical banks. A callback can fail after an earlier chunk's
    writes were ACKed; such a failure never publishes the output region.
    """
    JOB_TYPE = RmsJob
    source_identity = staticmethod(source_identity)

    def __init__(self, scalar=None, observer=None):
        super().__init__(scalar, observer)
        self.row_bank = bytearray(CHUNK_BYTES)
        self.weight_bank = bytearray(CHUNK_BYTES)
        self.output_bank = bytearray(CHUNK_BYTES)
        self.scratch_phase = 'idle'

    def _read_chunk(self, address, bank):
        require(bank is self.row_bank or bank is self.weight_bank, 'read must target an existing bank')
        require(len(bank) == CHUNK_BYTES, 'H1024 bank capacity changed')
        for offset in range(0, CHUNK_BYTES, BEAT_BYTES):
            raw = yield (address + offset, None)
            if any(not finite(bits[0] << 16) for bits in struct.iter_unpack('<H', raw)):
                raise ArithmeticFault('nonfinite BF16 input/weight')
            bank[offset:offset + BEAT_BYTES] = raw

    def _partial(self, lane, residue, bits=None):
        require(self.scratch_phase == 'partials' and 0 <= lane < 8 and 0 <= residue < 4,
                'FP32 residue access outside output scratch partial phase')
        offset = 4 * (4 * lane + residue)
        if bits is None:
            return struct.unpack_from('<I', self.output_bank, offset)[0]
        struct.pack_into('<I', self.output_bank, offset, bits)

    def _compute(self, job):
        for token in range(job.tokens):
            self.scratch_phase = 'partials'
            squares = [0] * WIDTH if self.observer is not None else None
            # Only independent residue sums are interleaved. Each individual
            # residue still adds block0, block1, block2, block3 in that order.
            for chunk in range(2):
                yield from self._read_chunk(job.input + token * ROW_BYTES + chunk * CHUNK_BYTES,
                                            self.row_bank)
                for lane in range(8):
                    for residue in range(4):
                        for block in range(2):
                            partial = 0
                            for term in range(16):
                                index = block * 512 + term * 32 + residue * 8 + lane
                                x = struct.unpack_from('<H', self.row_bank, index * 2)[0] << 16
                                square = self._op('mul_ieee_rne', x, x)
                                if squares is not None:
                                    squares[chunk * CHUNK_WORDS + index] = square
                                partial = self._op('add', partial, square)
                            # The first block's explicit add starts from +0;
                            # its store initializes this scratch slot. Later
                            # blocks consume only that initialized slot.
                            previous = 0 if chunk == 0 and block == 0 else self._partial(lane, residue)
                            self._partial(lane, residue, self._op('add', previous, partial))
            total = 0
            for lane in range(8):
                lane_total = 0
                for residue in range(4):
                    lane_total = self._op('add', lane_total, self._partial(lane, residue))
                total = self._op('add', total, lane_total)
            if squares is not None:
                self._observe('squares', token, squares)
            self._observe('sum', token, (total,))
            mean = self._op('mul_ieee_rne', total, word(1 / WIDTH))
            self._observe('mean', token, (mean,))
            variance = self._op('add', mean, word(reference.EPS))
            self._observe('mean_eps', token, (variance,))
            root = self._op('sqrt', variance)
            self._observe('root', token, (root,))
            inverse = self._op('div', word(1), root)
            self._observe('inverse', token, (inverse,))
            self.row_scalars.append(dict(token=token, sum=total, mean=mean, variance=variance,
                                         root=root, inverse=inverse))
            # Release the overlaid FP32 residues before any BF16 output stores.
            self.scratch_phase = 'output'
            scaled, gamma, weighted_nodes, rounded_nodes = (([], [], [], []) if self.observer is not None
                                                          else (None, None, None, None))
            for chunk in range(2):
                yield from self._read_chunk(job.input + token * ROW_BYTES + chunk * CHUNK_BYTES,
                                            self.row_bank)
                yield from self._read_chunk(job.weight + chunk * CHUNK_BYTES, self.weight_bank)
                for index in range(CHUNK_WORDS):
                    x = struct.unpack_from('<H', self.row_bank, index * 2)[0] << 16
                    w = struct.unpack_from('<H', self.weight_bank, index * 2)[0] << 16
                    normalized = self._op('mul_ieee_rne', x, inverse)
                    scale = self._op('add', word(1), w)
                    weighted = self._op('mul_ieee_rne', normalized, scale)
                    rounded = ((weighted + 0x7fff + ((weighted >> 16) & 1)) & 0xffffffff) >> 16
                    if not finite(rounded << 16):
                        raise ArithmeticFault('terminal BF16 conversion overflow')
                    struct.pack_into('<H', self.output_bank, index * 2, rounded)
                    if scaled is not None:
                        scaled.append(normalized)
                        gamma.append(scale)
                        weighted_nodes.append(weighted)
                        rounded_nodes.append(rounded << 16)
                if chunk == 1 and scaled is not None:
                    self._observe('scaled', token, scaled)
                    self._observe('gamma', token, gamma)
                    self._observe('weighted', token, weighted_nodes)
                    self._observe('output', token, rounded_nodes)
                for offset in range(0, CHUNK_BYTES, BEAT_BYTES):
                    yield (job.output + token * ROW_BYTES + chunk * CHUNK_BYTES + offset,
                           bytes(self.output_bank[offset:offset + BEAT_BYTES]))

    def _finish(self, status=None):
        super()._finish(status)
        self.scratch_phase = 'retired'

    def report(self):
        result = super().report()
        result.update(scope='PACKED_BF16_H2048_RMS_SOFTWARE_OWNER',
                      retained_bf16_row_capacity=len(self.row_bank) // 2,
                      retained_bf16_weight_capacity=len(self.weight_bank) // 2,
                      retained_bf16_output_capacity=len(self.output_bank) // 2,
                      retained_physical_bank_bytes=sum(map(len, (self.row_bank, self.weight_bank, self.output_bank))),
                      residue_partial_count=32, residue_partial_bits=32,
                      residue_overlay_bf16_entries=64, residue_overlay_bank='output',
                      scratch_phase=self.scratch_phase, input_passes_per_token=2,
                      expected_read_bytes_per_token=3 * ROW_BYTES,
                      observer_snapshots_host_only=True, row_scalars_host_only=True,
                      added_physical_array=False, shared_scalar_service_count=1,
                      additional_memory_ports=0, control_overhead_proven=False,
                      full_native_forward=False)
        return result


class TypedRmsDriver(base.TypedRmsDriver):
    OWNER_TYPE = RmsOwner
    JOB_TYPE = RmsJob
    WEIGHT_BYTES = ROW_BYTES
