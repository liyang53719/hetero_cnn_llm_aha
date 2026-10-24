"""Strict arithmetic on the ORIGINAL chunk matmul coroutine, software only.

This bounded phase replay reuses the actual row/beat/K control and byte I/O
methods. It does not install a policy in ChunkOwner, instantiate Vector16,
reuse Contraction's proposed whole-plane schedule, or admit a ChunkJob.
MemoryRequest/MemoryResponse are the existing wire dataclasses. The caller
must complete/drain physical transactions; closing this generator is NOT
abort/drain and never publishes output/state or advances generation.
"""
from collections import Counter

from candidates.qwen35_gdn_prefill.chunk.model import ChunkOwner, LEGACY_MATMUL
from candidates.qwen35_gdn_prefill.rms_owner import MemoryRequest, MemoryResponse
from .model import ArithmeticFault, validate_contraction
from candidates.qwen35_strict_fp32_lane import lane_model as fp


class ResponseFault(ValueError):
    pass


class StrictUpstreamCoroutine:
    # These are the existing executable methods, not copied/predicted schedules.
    _matmul = ChunkOwner._matmul
    _read = ChunkOwner._read
    _write = ChunkOwner._write
    _mul_add = ChunkOwner._mul_add
    _remember_failure = ChunkOwner._remember_failure

    def __init__(self, observe=None):
        self.host_batch = False
        self.matmul_policy = LEGACY_MATMUL
        self.observe = observe
        self.busy = False
        self.counts = Counter()
        self.context, self.position = {}, {}
        self.sequence = 0
        self.first_numerical_failure = None

    def _op(self, operation, a, b):
        # No native Vector16 call or hardware claim. This is the same strict
        # integer primitive as Contraction, including fatal-mask 30 semantics.
        if operation not in ('mul', 'add') or len(a) != 16 or len(b) != 16:
            raise ValueError('full strict Add/Mul beat required')
        results = [getattr(fp, operation)(x, y) for x, y in zip(a, b)]
        words, flags = map(list, zip(*results))
        stage = 'pair' if self.position.get('node') == 'pair_decay_mul' else operation
        self.counts[stage + '_lane_ops'] += 16
        if self.observe:
            self.observe(stage, dict(self.position), words, flags)
        for lane, (word, flag) in enumerate(results):
            if flag & 30 or not fp.finite(word):
                raise ArithmeticFault(stage, self.position['reduction_k'],
                                      self.position['row'] * 64 + self.position['column'] + lane,
                                      word, flag)
        return words

    def program(self, a, kt, pair, destination, *, phase, tag=0):
        """Yield one typed request; resume ONLY with its completed response.

        Not resuming holds the actual upstream generator at that byte read or
        write. There are no tick/cycle semantics, request-ready handshake, DMA
        arbitration, owner terminal, duplicate-ACK drain or publication here.
        A failed response stops before advancing the original coroutine.
        """
        if self.busy:
            raise RuntimeError('upstream coroutine already active')
        validate_contraction(a, kt, pair, destination, phase)
        if type(tag) is not int or not 0 <= tag < 1 << 32:
            raise ValueError('32-bit phase replay tag required')
        self.busy = True
        self.counts = Counter()
        self.context = dict(phase='ut_matmul' if phase == 5 else 'intra_matmul',
                            head=None, chunk=None)
        self.position, self.sequence, self.first_numerical_failure = {}, 0, None
        inner = self._matmul(a, kt, destination, factor=pair)
        reply = None
        try:
            while True:
                try:
                    address, data = inner.send(reply)
                except StopIteration:
                    return dict(self.counts)
                if self.sequence >= 1 << 32:
                    raise ResponseFault('memory sequence overflow')
                request = MemoryRequest(address, (tag << 32) | self.sequence, data)
                self.sequence += 1
                self.counts['write_requests' if request.write else 'read_requests'] += 1
                response = yield request
                if (type(response) is not MemoryResponse or
                        type(response.tag) is not int or response.tag != request.tag or
                        type(response.nbytes) is not int or response.nbytes != 64 or
                        type(response.error) is not bool):
                    raise ResponseFault('memory response identity/byte count/type')
                if response.error:
                    raise ResponseFault('memory response error')
                if not request.write and (type(response.data) is not bytes or len(response.data) != 64):
                    raise ResponseFault('memory read requires 64 bytes')
                self.counts['write_acks' if request.write else 'read_responses'] += 1
                reply = None if request.write else response.data
        finally:
            inner.close()
            self.busy = False
