"""Explicit official-BF16 policy on the existing public21 transaction driver.

Only the numeric policy and read-only observations are new. Existing public
descriptor reads, Host/coordinator handshakes, SRAM banks, Matrix ownership,
DDR addresses and write-ACK publication fences remain the executing path.
"""
from array import array
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys

from ..ffn_public.execute_numeric import PublicExecution, require
from ..ffn_public.check_prefix_numeric import ReferenceGate
from .owners import OfficialPrefixOwner, OfficialAttentionOwner

IMPORTED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
POLICY_ID = 'qwen2-public21-official-bf16-v2'
POLICY = dict(id=POLICY_ID, target='frozen_official_BF16_materialization',
    approved_utc='2026-10-12T10:50:23Z', fp32_reference='diagnostic_only',
    storage='FP32 containers containing materialized BF16 values; raw QKV and split-K prefixes FP32',
    matrix='BF16 operands; increasing-K FP32 FMA; original 16-stripe QK reduction',
    rms='frozen Torch210 CPU V8/ILP4 RMS1536; direct gamma; BF16 before and after gamma',
    rope='reviewed FP32 table; BF16 table/products/sums; split-half pairing',
    softmax='original exp7 and FP32 normalization; BF16 probability at Matrix input',
    thresholds='unchanged spec/numerical_contract.md', accepted_full_block=False)

# Roles are validated against the original publicly described allocation map,
# not guessed from dimensions or a private address convention.
JOBS = {
    0: ('Norm', 'x', 'gamma0', 'n0'), 1: ('Dense', 'n0', 'wq', 'qraw'),
    2: ('Bias', 'qraw', 'bq', 'qr'), 3: ('Rope', 'qr', 'rope', 'q'),
    4: ('Dense', 'n0', 'wk', 'kraw'), 5: ('Bias', 'kraw', 'bk', 'kr'),
    6: ('Rope', 'kr', 'rope', 'k'), 7: ('Dense', 'n0', 'wv', 'vraw'),
    8: ('Bias', 'vraw', 'bv', 'v'), 9: ('KvAppend', 'k', 'v', 'kv'),
    12: ('Attention', 'q', 'cache_k', 'att'), 13: ('Dense', 'att', 'wo', 'o'),
    14: ('Add', 'x', 'o', 'r'), 15: ('Norm', 'r', 'gamma1', 'n1'),
    16: ('Dense', 'n1', 'wg', 'gate'), 17: ('Dense', 'n1', 'wu', 'up'),
    18: ('Activation', 'gate', 'up', 'act'), 19: ('Dense', 'act', 'wd', 'down'),
    20: ('Add', 'r', 'down', 'y'),
}
DENSE_ROLES = {1: 'q_raw', 4: 'k_raw', 7: 'v_raw', 13: 'dense_o',
               16: 'gate', 17: 'up', 19: 'down'}
OPCODES = (0x32, 0x20, 0x30, 0x34, 0x20, 0x30, 0x34, 0x20, 0x30,
           0x41, 0x23, 0x33, 0x24, 0x20, 0x30, 0x32, 0x20, 0x20, 0x35, 0x20, 0x30)


def validate_job(fixture, job):
    pc = job.tag & 0xffff
    require(pc in JOBS and job.tag == (fixture.config.epoch << 16) | pc,
            'official policy job is outside this public21 epoch/profile')
    kind, a, b, dst = JOBS[pc]
    specs = fixture.specs
    rows = specs['x'][1][0]
    width = 256 if pc == 9 else specs[dst][1][-1]
    k = specs[a][1][-1] if pc != 12 else 128
    expected = (kind, specs[a][0], specs[b][0], specs[dst][0], rows, width, k)
    require(tuple(getattr(job, n) for n in ('kind', 'a', 'b', 'dst', 'm', 'n', 'k')) == expected,
            'official policy public job source/shape/role mismatch at pc%d' % pc)
    require(job.write_bytes == fixture.allocations[dst].storage_bytes and
            job.weight_bf16 == (kind == 'Dense') and
            not job.activation_bf16 and not job.output_bf16,
            'official numeric policy must retain the original typed storage and bytes')
    expected_c = (specs['rope'][0] + 1024 * 64 * 4 if kind == 'Rope' else
                  specs['cache_v'][0] if kind == 'Attention' else 0)
    require(getattr(job, 'c', 0) == expected_c, 'official policy third span mismatch')
    return pc


class OfficialPublicExecution(PublicExecution):
    """Bind arithmetic roles after the original Host's validated dispatch."""
    def __init__(self, *args, fixture, **kwargs):
        from .dense_silu import OfficialMatrixService
        require(fixture.scope == 'QWEN2_21_METADATA_ONLY' and
                fixture.config.command.count == len(fixture.commands) == 21 and
                tuple(int(c.opcode) for c in fixture.commands) == OPCODES and
                all(c.event_wait == i and c.event_signal == i + 1
                    for i, c in enumerate(fixture.commands)), 'official policy requires public21 profile')
        require(type(kwargs.get('prefix_owner')) is OfficialPrefixOwner and
                type(kwargs.get('attention_owner')) is OfficialAttentionOwner and
                type(kwargs.get('matrix_service')) is OfficialMatrixService,
                'mixed numerical policies within one launch')
        physical = getattr(args[0].memory, 'physical_memory', None)
        require(args[0].config == fixture.config and physical is not None and
                physical.fixture is fixture,
                'official policy fixture must be this actual physical public memory')
        self.policy_fixture = fixture
        self.policy_jobs = {}
        super().__init__(*args, **kwargs)

    def advance_to_request(self, limit=4096):
        ports = super().advance_to_request(limit)
        group = ports['group_request']
        jobs = ((group.gate, group.up, group.act) if group is not None else
                (ports['ordinary_request'],))
        for job in jobs:
            pc = validate_job(self.policy_fixture, job)
            value = asdict(job)
            require(pc not in self.policy_jobs or self.policy_jobs[pc] == value,
                    'official role binding changed after first validated dispatch')
            self.policy_jobs[pc] = value
            if pc in DENSE_ROLES:
                self.matrix_service.bind_dense_job(job, DENSE_ROLES[pc])
        return ports

    def report(self):
        result = super().report()
        result.update(numerical_policy=POLICY_ID, validated_policy_jobs=self.policy_jobs)
        return result


class ObservedSiluLibrary:
    """Read actual phase4 returns; never supply tensors to a later operation."""
    def __init__(self, selected, rows):
        require(rows in (16, 128), 'SiLU observer geometry')
        self.selected, self.rows, self.calls = selected, rows, 0
        self.silu = array('I', [0xa5963cc3]) * (rows * 8960)
        self.product = array('I', [0xa5963cc3]) * (rows * 8960)
        self.observed = bytearray(rows * 8960)

    def __getattr__(self, name):
        return getattr(self.selected, name)

    def sf_vector(self, gate, up, output, phases, flags, errors):
        rc = self.selected.sf_vector(gate, up, output, phases, flags, errors)
        if rc == 0:
            per_window = self.rows // 16 * 160
            window, index = divmod(self.calls, per_window)
            row_group, col = divmod(index, 160)
            require(window < 56, 'excess actual SiLU vector observations')
            for lane in range(16):
                offset = (row_group * 16 + lane) * 8960 + window * 160 + col
                require(not self.observed[offset], 'duplicate SiLU observation')
                self.silu[offset], self.product[offset] = int(phases[64 + lane]), int(output[lane])
                self.observed[offset] = 1
            self.calls += 1
        return rc

    def seal(self, actual_act):
        require(self.calls == self.rows * 8960 // 16 and all(self.observed) and
                self.product.tobytes() == actual_act,
                'SiLU observation incomplete or different from actual ACKed act output')
        return self.silu.tobytes()


class WholeReferenceGate(ReferenceGate):
    """Comparison payloads remain unreadable until the whole public terminal."""
    def audit(self, event, args):
        super().audit(event, args)
        if not self.active or self.opened:
            return
        if event == 'open' and isinstance(args[0], (str, bytes)):
            name = args[0].decode() if isinstance(args[0], bytes) else args[0]
            path = Path(name)
            require(not (set(path.parts) & {'raw_stages', 'references', 'tensors'}) and
                    not path.name.startswith('candidate_'),
                    'BF16 comparison payload accessed before whole public terminal')
        elif event == 'subprocess.Popen':
            require(not any(Path(str(v)).name in ('candidate', 'software_recipe', 'prefix_recipe')
                            for v in args[1]), 'BF16 oracle executed before whole public terminal')

    def library(self, library):
        gate = self
        class Guarded:
            def __getattr__(self, name):
                require(gate.opened or not any(name.startswith(p) for p in
                        ('fw_reference', 'sf_reference', 'td_reference')),
                        'BF16 reference ABI accessed before whole public terminal')
                return getattr(library, name)
        return Guarded()


@contextmanager
def reference_gate(spec):
    gate = WholeReferenceGate(spec)
    sys.addaudithook(gate.audit)
    try:
        yield gate
    finally:
        gate.active = False
