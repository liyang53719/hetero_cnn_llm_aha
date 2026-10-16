"""Owner-backed control evidence; no claim of Chisel cycle equivalence.

The original DenseReductionOwner executes every accepted ordinary transaction.
Raw traffic uses that owner's sole Banks instance. The two existing model tick
methods each reset access counters; this adapter merges their counters and
rejects any same-edge overlap. It does not allocate a payload bank or repair a
poisoned backend with a borrower reset.
"""
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseReductionOwner, Job, drain
from candidates.qwen2_resident_matrix.raw_kv.model import RawKvPort, Obligations

down = drain.down


class ParentLoan:
    def __init__(self, owner=None, *, enabled=False):
        self.owner = owner if owner is not None else DenseReductionOwner(
            down.PrefixWorkspace(0x10000000, 16384, 1, 128),
            enable_ffn_tiles=True, enable_ffn_window=True, enable_ffn_drain=True,
            enable_dense_drain=True, enable_k_window=True)
        self.raw = RawKvPort(self.owner.a_banks, enabled=enabled)
        self.enabled = enabled
        self.poison = False

    def debts(self):
        o = self.owner
        return dict(state=o.state != 'idle', status=o.error is not None,
            burst=o.read_active is not None, activation_high=o.a_hold is not None,
            activation_rmw=o.a_rmw_pending is not None,
            operand_return=o.pending is not None, operand_fifo=bool(o.fifo),
            seed=o.seed_outstanding or o.seed_state != 'idle',
            matrix=o.group_started and not o.group_done,
            write=o.write_state != 'idle',
            window=o.window_request is not None or o.window_result is not None,
            drain=o.drain_request is not None or o.drain_result is not None or o.drain_expected is not None,
            retained_a=o.lease is not None, drain_poison=o.drain_poison,
            tile=not o.tiles.idle or o.tiles.leased or o.tiles.poison,
            completion=o.ports()['response'] is not None, parent_poison=self.poison)

    def tick(self, *, acquire=None, release=None, request=None, ack=None,
             abort=False, soft_reset=False, backend_abort=False, **inputs):
        o = self.owner
        replies = any(inputs.get(k) is not None for k in
                      ('read_beat', 'result', 'matrix_done', 'write_ack', 'seed_ack'))
        unsolicited = self.enabled and (o.state == 'idle' or self.raw.blocked) and replies
        parent_fault = backend_abort or o.error is not None or o.tiles.poison or o.drain_poison
        drained = not any(self.debts().values()) and not unsolicited and not backend_abort
        reserved = self.enabled and (acquire is not None or self.raw.blocked or
            not self.raw.drained or self.raw.poison or self.poison or unsolicited or soft_reset or abort or parent_fault)
        if reserved:
            for k in ('job', 'window', 'drain', 'tile_control', 'tile_write', 'tile_read', 'dense_reads', 'dense_writes'):
                inputs.pop(k, None)
            inputs.update(loan_busy=True, loan_request=acquire is not None)
        # Borrower abort/reset are never forwarded as backend abort/reset.
        # Original model merges its tile/drain abort inputs into one backend abort.
        if backend_abort:
            inputs["abort"] = True
        e = o.tick(**inputs)
        reads, writes = dict(o.a_banks.reads), dict(o.a_banks.writes)
        if unsolicited:
            self.poison = True
        elif soft_reset and not self.raw.blocked and self.raw.drained and o.state == 'idle' and o.error is None:
            self.poison = False
        r = self.raw.tick(acquire=acquire, release=release, request=request, ack=ack,
            obligations=Obligations(dense=not drained), abort=abort or self.poison or unsolicited or parent_fault,
            soft_reset=soft_reset)
        if (reads or writes) and (o.a_banks.reads or o.a_banks.writes):
            raise RuntimeError('raw and original owner touched SRAM on the same edge')
        o.a_banks.reads.update(reads)
        o.a_banks.writes.update(writes)
        if reserved:
            e.update(job_ready=False, window_ready=False, drain_ready=False)
            if 'tile' in e:
                e['tile'].update(ctl_ready=False, write_ready=False, read_ready=False)
        return dict(owner=e, raw=r, drained=drained, reserved=reserved)
