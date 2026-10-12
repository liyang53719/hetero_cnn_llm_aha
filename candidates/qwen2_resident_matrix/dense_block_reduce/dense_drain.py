"""Typed Dense tile writeback over the existing drain lifecycle and same SRAM.

No public opcode, private address, arithmetic, or memory resource is added.
The original full Dense Job is carried in the existing internal drain request.
Its output remains FP32: the following public Bias command owns QKV's BF16
materialization. A returned tile result counts actual DDR ACK bytes only;
the enclosing public Dense completion must accumulate every output window.
"""
from dataclasses import dataclass
from .k_window_model import Job, KWindowOwnerModel, drain


def dense_spans(job):
    return ((job.a, job.a + job.m * job.k * (2 if job.activation_bf16 else 4)),
            (job.b, job.b + job.k * job.n * (2 if job.weight_bf16 else 4)),
            (job.dst, job.dst + job.m * job.n * 4))


@dataclass(frozen=True)
class DenseDrainRequest(drain.FfnDrainRequest):
    """Existing internal request fields with an explicit Dense job contract."""
    job: Job

    def validate(self):
        if not isinstance(self.job, Job):
            raise ValueError("complete typed Dense Job required")
        j = self.job
        j.validate()
        if (any(type(v) is not bool for v in (j.activation_bf16, j.weight_bf16, j.output_bf16)) or
                any(type(v) is not int for v in (j.m, j.n, j.k, j.tag, j.a, j.b, j.dst, j.write_bytes)) or
                j.kind != "Dense" or j.m not in (16, 128) or not 0 < j.n <= j.k <= 1536 or j.k < j.m or
                j.k % 2 or j.n % 32 or j.output_bf16 or j.materialize_dense_output or
                j.write_bytes != j.m * j.n * 4):
            raise ValueError("Dense FP32 full-job QKV drain geometry")
        spans = dense_spans(j)
        if any(base % 64 or end > 1 << 56 for base, end in spans):
            raise ValueError("Dense drain aligned complete spans")
        if any(a < d and c < b for i, (a, b) in enumerate(spans) for c, d in spans[i+1:]):
            raise ValueError("Dense drain complete source/output alias")
        if (any(type(v) is not int for v in (self.identity, self.ng, self.cols)) or
                not 0 < self.identity < 1 << 32 or not 0 <= self.ng < 1 << 16 or
                self.ng % 32 or self.cols not in (32, 64, 96, 128, 160) or
                self.ng + self.cols > j.n):
            raise ValueError("Dense drain window identity/extent")


class DenseReductionOwner(KWindowOwnerModel):
    def __init__(self, workspace=None, *, enable_dense_drain=False, **kwargs):
        if type(enable_dense_drain) is not bool:
            raise ValueError("typed Dense drain policy")
        if enable_dense_drain and not kwargs.get("enable_ffn_drain", False):
            raise ValueError("Dense tile drain requires the existing drain port")
        self.enable_dense_drain = enable_dense_drain
        super().__init__(workspace, **kwargs)

    def _write_data(self):
        value = super()._write_data()
        if value is None or isinstance(value, drain.WriteBeat):
            return value
        # The same frozen Down source is loaded in distinct guarded module
        # namespaces by the public and resident paths. Its ordinary WriteBeat
        # has only words/LAST; make this owner output's always-full wire mask
        # explicit instead of weakening PhysicalMemory's exact-type guard.
        if type(value) is not drain.down.WriteBeat:
            raise ValueError("unexpected ordinary Dense write wire type")
        return drain.WriteBeat(value.words, value.last)

    def _admit_drain(self, q):
        if not isinstance(q, DenseDrainRequest):
            return super()._admit_drain(q)
        # Match the old admission lifecycle exactly, with genuine Dense spans.
        # Calling Activation admission would incorrectly enlarge BF16 A/B to
        # four-byte M*N spans and could reject a legal adjacent workspace.
        self.drain_request, self.job = q, q.job
        self.drain_result = None
        self.drain_started = self.clock
        self.drain_consumed = self.drain_column = self.write_row = self.write_row_beat = 0
        self.write_bytes = 0
        self.drain_expected = self.accepted_write = None
        self.error = None
        self.write_state = "idle"
        self.group_started = self.group_done = False
        self.final_value = None
        try:
            if not self.enable_dense_drain:
                raise ValueError("Dense drain policy is disabled")
            q.validate()
            w = self.workspace
            if (w is None or any(type(v) is not int for v in (w.base,w.extent,w.generation,w.split_k)) or
                    w.base < 0 or w.base % 64 or w.extent <= 0 or w.base+w.extent > 1<<56 or
                    not 0 < w.generation < 1<<32 or not 0 < w.split_k <= 2560 or w.split_k % 128):
                raise ValueError("prefix workspace geometry")
            if any(w.base < end and base < w.base + w.extent for base, end in dense_spans(q.job)):
                raise ValueError("prefix workspace aliases complete Dense span")
            if not (self.tiles.idle and self._slot_exact() and self.tiles.tags[2].consumed == 0):
                raise ValueError("sealed Dense sum slot identity/shape/count mismatch")
        except ValueError as exc:
            self._fault(str(exc))
        else:
            self.final_value = [[0] * 256 for _ in range(16)]
            self.state, self.drain_phase = "ffn_drain", "read"
