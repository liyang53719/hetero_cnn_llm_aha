"""Bounded real InputPrep -> original chunk producer -> UT/QK diagnostic.

Only the ChunkOwner instance's Add/Mul _op is substituted. Its original
_compute, exp, byte transport and lifecycle remain intact. Raw Conv/AB are
synthetic upstream-boundary inputs, not outputs of an executed convolution.
The actual Prep computes all M128 tokens. Only head 0 / chunk 0 is consumed:
after UT and QK final ACK, abort/drain the first solve read before its data is
consumed. This is explicitly NOT a successful ChunkJob or full M128 chain.
"""
from collections import Counter
import struct

from candidates.qwen35_gdn_prefill.chunk import model as chunk
from candidates.qwen35_gdn_prefill.chunk.vector import Vector16, LEGACY_POLICY
from candidates.qwen35_gdn_prefill.prep import model as prep
from candidates.qwen35_gdn_prefill.prep.scalar import PrepScalar
from candidates.qwen35_gdn_prefill.rms_owner import ArithmeticFault, word
from candidates.qwen35_strict_fp32_lane import lane_model as fp
from candidates.qwen2_resident_matrix.transposed_down.model import WriteCommand, WriteAck


class StrictProducerArithmetic:
    """One test-only instance hook, with 1..16 active strict software lanes.

    This does not change a production policy or implement native Vector16.
    Prep's original Div/Sqrt/Softplus and chunk's original ExpNegative are NOT
    replaced or claimed to have strict integer Add/Mul semantics.
    """
    def __init__(self, owner, observe=None):
        chunk.require(type(owner) is chunk.ChunkOwner and owner.job is None and
                      owner.ports()['job_ready'], 'fresh exact test owner')
        chunk.require(not owner.host_batch and owner.matmul_policy == chunk.LEGACY_MATMUL,
                      'original separate Mul/Add row schedule required')
        chunk.require(owner.vector.exception_policy == LEGACY_POLICY and
                      owner.vector.fatal_mask == 30, 'unchanged fatal mask 30')
        chunk.require('_compute' not in owner.__dict__ and '_op' not in owner.__dict__,
                      'no stacked instance hooks')
        self.owner, self.observe = owner, observe
        self.lane_ops, self.issues, self.widths, self.flags = (Counter() for _ in range(4))
        owner._op = self._op

    def _op(self, operation, a, b):
        owner = self.owner
        chunk.require(owner.scalar.client is owner and owner.vector.client is owner,
                      'strict test arithmetic requires real owner leases')
        chunk.require(operation in ('add', 'mul') and len(a) == len(b) and
                      1 <= len(a) <= 16, '1..16 active Add/Mul lanes required')
        chunk.require(all(type(x) is int and 0 <= x < 1 << 32 for x in (*a, *b)),
                      'uint32 raw operands required')
        diagnostic = dict(resource='strict_integer_software_test_hook', operation=operation,
                          active_lanes=len(a), a_words=list(a), b_words=list(b),
                          result_words=None, lane_exception_flags=None, exception_flags=None)
        if not all(fp.finite(x) for x in (*a, *b)):
            error = ArithmeticFault('nonfinite strict Add/Mul input')
            error.diagnostic = diagnostic
            owner._remember_failure(error)
            raise error
        result = [getattr(fp, operation)(x, y) for x, y in zip(a, b)]
        words, flags = map(list, zip(*result))
        phase = owner.context.get('phase', 'unspecified')
        self.lane_ops[operation] += len(a)
        self.issues[(phase, operation)] += 1
        self.widths[len(a)] += 1
        self.flags.update(flags)
        if self.observe is not None:
            self.observe(dict(owner.context), dict(owner.position), operation, a, b, words, flags)
        for lane, (bits, status) in enumerate(result):
            if status & 30 or not fp.finite(bits):
                # Producer operations may have only {row}, or no position at
                # all. Never mask a numerical error with a missing-key error.
                error = ArithmeticFault('strict Add/Mul fatal result')
                error.diagnostic = dict(diagnostic, lane=lane, result_word=bits,
                    exception_flags=status, result_words=words, lane_exception_flags=flags,
                    reduction_k=owner.position.get('reduction_k'),
                    row=owner.position.get('row'), column=owner.position.get('column'))
                owner._remember_failure(error)
                raise error
        return words

    def detach(self):
        owner = self.owner
        chunk.require(owner.state in ('idle', 'locked') and owner.request is None and
                      owner.program is None and owner.scalar.client is not owner and
                      owner.vector.client is not owner, 'detach requires drained retired owner')
        chunk.require(owner.__dict__.get('_op') == self._op and
                      '_compute' not in owner.__dict__, 'test hook replaced')
        del owner._op


def lease_shell():
    """Original Vector16 acquire/release only; never load or call a library."""
    vector = object.__new__(Vector16)
    vector.client, vector.resource_address = None, id(vector)
    vector.exception_policy, vector.fatal_mask = LEGACY_POLICY, 30
    vector.calls, vector.lane_ops, vector.host_calls, vector.flags = (Counter() for _ in range(4))
    return vector


def synthetic_raw_inputs():
    """Distinct full128 raw BF16 rows, deliberately benign decay range.

    The cold job uses no warm recurrent state. 'Warm range' means the modest
    synthetic decay magnitude, not pretrained values or a measured workload.
    A_log=-2, dt_bias=1/8, A=-4..-61/16 and B=-1/2..1/2. All
    Q/K/V and AB values are exactly representable in BF16 before Prep.
    """
    conv, ab = bytearray(), bytearray()
    for token in range(128):
        row = [0] * 6144
        for role in range(3):
            for col in range(128):
                value = (((token * 17 + col * 7 + role * 43) % 257) - 128) / 128
                row[role * 2048 + col] = word(value) >> 16
        row[0] = word(1 + token / 128) >> 16
        conv.extend(struct.pack('<6144H', *row))
        gates = [0] * 32
        gates[0], gates[16] = word(-4 + (token % 4) / 16) >> 16, word((token % 9 - 4) / 8) >> 16
        ab.extend(struct.pack('<32H', *gates))
    log = struct.pack('<16I', word(-2), *([0] * 15))
    bias = struct.pack('<32H', word(.125) >> 16, *([0] * 31))
    return bytes(conv), bytes(ab), log, bias


def write_raw_fixture(memory, base, raw, tag):
    """External synthetic RAW boundary transport; not producer arithmetic."""
    region = memory.allocate_output(base, len(raw))
    for offset in range(0, len(raw), 64):
        memory.begin_write(WriteCommand(base + offset, 1, tag))
        memory.write_data(struct.unpack('<32H', raw[offset:offset + 64]), True)
        memory.acknowledge(WriteAck(tag, False, 64))
    memory.publish(base, (tag, None, len(raw)))
    return region


def make_prep():
    memory, scalar = chunk.TypedMemory(), PrepScalar(enable_softplus=True)
    raw = synthetic_raw_inputs()
    job = prep.InputPrepJob(71, 0x100000, 0x300000, 0x310000, 0x320000,
                            0x400000, 128, heads=1)
    write_raw_fixture(memory, job.conv, raw[0], 1)
    write_raw_fixture(memory, job.ab, raw[1], 2)
    memory.add_readonly(job.a_log, raw[2])
    memory.add_readonly(job.dt_bias, raw[3])
    memory.allocate_output(job.output, job.write_bytes)
    driver = prep.TypedInputPrepDriver(prep.InputPrepOwner(scalar, heads=1), memory, job)
    return driver


def make_chunk(prep_driver, observe=None):
    chunk.require(prep_driver.response is not None and prep_driver.response.status is None and
                  prep_driver.output.published, 'actual successful Prep publication required')
    memory, scalar = prep_driver.memory, prep_driver.scalar_resource
    job = chunk.ChunkJob(72, prep_driver.job.output, 0x800000, 0x810000, 0x820000,
                         0x900000, 128, heads=1)
    for base, size in ((job.output, job.output_bytes), (job.state_out, job.state_bytes),
                       (job.scratch, job.scratch_bytes)):
        memory.allocate_output(base, size)
    owner = chunk.ChunkOwner(scalar, lease_shell(), heads=1)
    arithmetic = StrictProducerArithmetic(owner, observe)
    return chunk.TypedChunkDriver(owner, memory, job), arithmetic
