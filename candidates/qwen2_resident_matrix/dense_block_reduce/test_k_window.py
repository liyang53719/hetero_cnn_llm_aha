"""Physical DDR/bank/Matrix/tile protocol plus real host Matrix partial tests.

MATRIX_SERVICE_LIBRARY and adjacent compile.json are REQUIRED for the arithmetic
acceptance test. Missing inputs fail; there is no skip or compilation fallback.
Opaque transport tests are identified separately from actual arithmetic.
"""
from collections import deque
import ctypes as C
from dataclasses import replace
import importlib.util
import inspect
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
if str(P.parents[2]) not in sys.path:
    sys.path.insert(0, str(P.parents[2]))
from candidates.qwen2_resident_matrix.dense_block_reduce import k_window_model as m


def request(rows=16, cols=32, ng=0, slot=0, reuse=False, k=32, begin=0, end=None, reverse=True, block=1, native=True, **kwargs):
    j = m.Job(m=rows, k=k, n=8960, activation_bf16=native, weight_bf16=native,
              b=0x400000, dst=0x4000000, **kwargs)
    return m.KWindowRequest(j, 7, ng, cols, slot, reuse, k_begin=begin,
                           k_end=k if end is None else end, pair_reverse=reverse, block_id=block)


def owner(enabled=True):
    return m.KWindowOwnerModel(m.PrefixWorkspace(0x10000000, 8960//32*16384, 11),
                              enable_k_window=enabled, enable_ffn_window=True, enable_ffn_tiles=True)


def physical_result(ctx, block):
    # Distinct low FP32 bits ensure no accidental BF16 materialization is hidden.
    return tuple(tuple(0x3e000011 + block*0x100000 + ctx*0x10000 + bank*256+i
                       for i in range(256)) for bank in range(16))


class Harness:
    def __init__(self, q=None, instance=None, keep_events=False):
        self.owner = owner() if instance is None else instance
        self.read = None
        self.results = deque()
        self.commands, self.steps, self.events = [], [], []
        self.keep_events = keep_events
        self.completion = None
        self.q = None
        self.read_packets = []
        self.b_releases = []
        if q is not None:
            self.submit(q)

    def submit(self, q, **kwargs):
        self.q, self.completion = q, None
        e = self.owner.tick(window=q, **kwargs)
        assert e['window_fire']
        return e

    def source(self, kind, row, col):
        native = self.q.job.activation_bf16 if kind == 'a' else self.q.job.weight_bf16
        bf = 0x3c00 + ((row*131+col*17) % 512 if kind == 'a' else (row*7+col*19) % 512)
        return bf if native else (bf << 16) + 0x7fff

    def read_words(self, cmd):
        j = self.q.job
        native = j.activation_bf16 if cmd.kind == 'a' else j.weight_bf16
        base, stride = (j.a, j.k) if cmd.kind == 'a' else (j.b, j.n)
        first = (cmd.address-base)//(2 if native else 4)
        return tuple(self.source(cmd.kind, (first+i)//stride, (first+i)%stride)
                     for i in range(32 if native else 16))

    def expected_operand(self, step):
        j = self.q.job
        k = getattr(step, 'logical_k', step.k)
        a = tuple(self.source('a', row, k) if row < j.m else 0 for row in range(128))
        b = tuple(self.source('b', k, self.q.ng+32*step.context+c) for c in range(32))
        if not j.activation_bf16:
            a = tuple(m.down.bf16_rne(x) if x else 0 for x in a)
        if not j.weight_bf16:
            b = tuple(m.down.bf16_rne(x) for x in b)
        return b[:16], a+b[16:]+(0,)*112

    def cycle(self, *, dma=True, done=True, produce=True, **kwargs):
        o, q = self.owner, self.q
        p = o.ports()
        args = {}
        if dma and self.read is not None:
            args['read_beat'] = m.ReadBeat(self.read.tag, self.read_words(self.read), True)
        if produce and self.results:
            args['result'] = self.results[0]
        if p['step'] is not None and p['step'].last and len(self.results) >= 2:
            args['step_ready'] = False
        length = q.k_end-q.k_begin if isinstance(q, m.KWindowRequest) else q.job.k
        if done and o.group_started and not o.group_done and (o.error or (
                o.group_accepted_steps == length*q.cols//32 and o.results_received == q.cols//32)):
            args['matrix_done'] = m.MatrixDone(q.job.tag, bool(o.error))
        args.update(kwargs)
        pending_k = o.issue_k if o.state == 'execute' else None
        ready_before = tuple(o.ready)
        e = o.tick(**args)
        if e.get('read_fire'):
            self.read = None
        if e.get('read_command_fire'):
            assert self.read is None
            self.read = e['read_command']
            self.commands.append(self.read)
        if e.get('group_fire'):
            self.accept_group()
        if e.get('result_fire') and self.results:
            self.retire_result(self.results[0])
            self.results.popleft()
        if e.get('step_fire'):
            step = e['step']
            assert (step.a, step.b) == self.expected_operand(step), 'actual SRAM packet mismatch'
            self.steps.append(step)
            produced = self.accept_step(step)
            if produced is not None:
                self.results.append(produced)
        assert len(self.results) <= 2
        if e.get('operand_read'):
            self.read_packets.append((pending_k, dict(e['a_reads']), dict(e['b_reads'])))
            for half in range(2):
                if ready_before[half] and not o.ready[half]:
                    self.b_releases.append((pending_k, half))
        if e.get('matrix_done_fire'):
            self.retire_done(args['matrix_done'])
        if e.get('window_result_fire'):
            self.completion = e['window_result']
            self.retire_owner()
        assert e.get('write_command') is None and e.get('write_data') is None and e.get('response') is None
        for k in ('a_reads', 'a_writes', 'b_reads', 'b_writes'):
            assert len(e.get(k, {})) <= 16
        if self.keep_events:
            self.events.append(e)
        return e

    def accept_group(self):
        pass

    def accept_step(self, step):
        if step.last:
            return m.MatrixResult(step.context, physical_result(step.context, getattr(self.q, 'block_id', 1)))
        return None

    def retire_result(self, result):
        pass

    def retire_done(self, done):
        pass

    def retire_owner(self):
        pass

    def until(self, predicate, limit=300000, **kwargs):
        for _ in range(limit):
            if predicate():
                return
            self.cycle(**kwargs)
        raise AssertionError(('timeout', self.owner.state, self.owner.error, self.owner.load_k,
                              self.owner.issue_k, self.owner.adapter_phase))

    def finish(self, **kwargs):
        self.until(lambda: self.completion is not None, **kwargs)
        return self.completion


def consume(o, q):
    out = []
    for i in range(q.job.m//16*q.cols):
        assert o.tick(tile_read=m.Read(q.slot, q.identity, q.ng, i))['tile']['read_fire']
        assert not o.tick()['tile']['response_fire']
        e = o.tick()
        assert e['tile']['response_fire']
        out.append(e['tile']['response'].words)
    return out


class ActualMatrixHarness(Harness):
    """Reusable test driver: accepted DDR/bank packets feed the existing service.

    source(kind,row,column) optionally supplies real A/B BF16 or FP32 wire
    words. No result source/initial partial injection is accepted. The caller
    owns service reset and must not reuse its sole library concurrently.
    """
    def __init__(self, q=None, instance=None, *, service, source=None):
        self.service = service
        self.source_words = source
        super().__init__(q, instance)

    def submit(self, q, **kwargs):
        assert self.service.acquire(self.owner, 'dense', q.job.tag)
        self.adapter = self.service.dense_library(self.owner)
        return super().submit(q, **kwargs)

    def source(self, kind, row, col):
        if self.source_words is not None:
            return self.source_words(kind, row, col)
        return super().source(kind, row, col)

    def accept_group(self):
        assert self.adapter.td_group(0, self.q.k_end-self.q.k_begin, self.q.cols//32) == 0

    def accept_step(self, step):
        a = (C.c_uint16*16)(*step.a)
        b = (C.c_uint16*256)(*step.b)
        out = (C.c_uint32*4096)()
        rc = self.adapter.td_step(step.k, step.context, step.clear, step.last,
                                  step.finish, step.emit, a, b, out)
        assert rc == int(step.last)
        if rc == 1:
            return m.MatrixResult(step.context, tuple(tuple(out[bank*256+i] for i in range(256)) for bank in range(16)))
        return None

    def retire_result(self, result):
        self.adapter.retire_result(result)

    def retire_done(self, done):
        self.adapter.retire_done(done)

    def retire_owner(self):
        self.service.retire_owner_response(self.owner)
        self.service.release(self.owner)


class KWindowTests(unittest.TestCase):
    def check_output(self, h, q):
        for index, words in enumerate(consume(h.owner, q)):
            g, col = divmod(index, q.cols)
            ctx, n = divmod(col, 32)
            expected = physical_result(ctx, q.block_id)
            self.assertEqual(words, tuple(expected[n%16][128*(n//16)+16*g+l] for l in range(16)))
            self.assertTrue(any(x & 0xffff for x in words))

    def test_full_a_1536_two_real_k_blocks_both_m_geometries(self):
        for rows in (16, 128):
            with self.subTest(rows=rows):
                q = request(rows=rows, k=1536, end=1024)
                h = Harness(q)
                r = h.finish()
                self.assertEqual((r.k_begin, r.k_end, r.block_id, r.produced_beats), (0, 1024, 1, rows//16*32))
                o = h.owner
                self.assertIs(o.job, q.job)
                self.assertIs(o.tiles.banks, o.a_banks)
                self.assertEqual(o.lease, m.ALease.for_request(q))
                self.assertEqual(o.lease.row_stride, 1536*2)
                self.assertEqual(o.traffic['a_read_bytes'], rows*1536*2)
                self.assertEqual(o.rmw_commits, rows*1536)
                self.assertEqual([c.address for c in h.commands if c.kind == 'a'],
                                 [q.job.a+i*64 for i in range(rows*1536*2//64)])
                saved = tuple(tuple(bank[:768]) for bank in o.a_banks.words)
                command_base, step_base = len(h.commands), len(h.steps)
                q2 = replace(q, slot=1, reuse_a=True, k_begin=1024, k_end=1536, block_id=2)
                h.submit(q2)
                r2 = h.finish()
                self.assertEqual((r2.k_begin, r2.k_end, r2.block_id), (1024, 1536, 2))
                self.assertEqual(o.traffic['a_read_bytes'], rows*1536*2)
                self.assertEqual(o.k_a_fences, 1)
                self.assertEqual({c.kind for c in h.commands[command_base:]}, {'b'})
                self.assertEqual(tuple(tuple(bank[:768]) for bank in o.a_banks.words), saved)
                self.assertEqual([s.logical_k for s in h.steps[step_base:]], [1024+(i^1) for i in range(512)])
                self.assertEqual(h.steps[step_base].k, 0)
                self.assertTrue(h.steps[step_base].clear)
                self.assertTrue(h.steps[-1].last and h.steps[-1].finish)
                self.assertEqual(h.steps[-1].logical_k, 1534)
                self.check_output(h, q)
                self.check_output(h, q2)

    def test_all_rows_tail_widths_full_original_n_and_fp32_input(self):
        for rows in (16, 128):
            for cols in (32, 64, 96, 128, 160):
                with self.subTest(rows=rows, cols=cols):
                    q = request(rows=rows, cols=cols, ng=8960-cols, k=32, begin=2, end=30,
                                native=cols != 64, reverse=cols != 96)
                    h = Harness(q)
                    self.assertIsNone(h.finish().status)
                    per = 32 if q.job.weight_bf16 else 16
                    scale = 2 if q.job.weight_bf16 else 4
                    expected = [q.job.b+(k*q.job.n+q.ng+c)*scale
                                for k in range(2, 30) for c in range(0, cols, per)]
                    self.assertEqual([c.address for c in h.commands if c.kind == 'b'], expected)
                    self.assertEqual(len(h.steps), 28*cols//32)
                    for i, s in enumerate(h.steps):
                        ordinal, ctx = divmod(i, cols//32)
                        self.assertEqual((s.k, s.context, s.logical_k),
                                         (ordinal, ctx, 2+(ordinal^int(q.pair_reverse))))
                        self.assertEqual((s.job_tag, s.identity, s.block_id), (q.job.tag, q.identity, q.block_id))
                        self.assertEqual((s.clear, s.last), (ordinal == 0, ordinal == 27))
                    self.check_output(h, q)

    def test_pair_boundaries_use_real_a_b_addresses_and_no_early_half_release(self):
        q = request(k=384, begin=126, end=258, cols=64)
        h = Harness(q)
        self.assertIsNone(h.finish().status)
        for k, ars, brs in h.read_packets:
            ordinal = k-q.k_begin
            physical = q.k_begin+(ordinal^1)
            self.assertEqual(ars, {m.down.a_address(physical, 16*g)[0]: m.down.a_address(physical, 16*g)[1]
                                  for g in range(8)})
            expected_halves = [dict(m.down.b_address((physical//128)&1, physical, ctx, nh) for nh in range(2))
                               for ctx in range(2)]
            self.assertIn(brs, expected_halves)
        self.assertEqual(h.b_releases, [(127, 0), (255, 1), (257, 0)])
        self.assertEqual([s.logical_k for s in h.steps if s.context == 0][-2:], [257, 256])

    def test_small_fp32_full_k16_and_native_k128(self):
        for q in (request(k=16, native=False), request(k=128)):
            h = Harness(q)
            self.assertIsNone(h.finish().status)
            self.assertEqual(len(h.steps), q.job.k)

    def test_packet_stable_under_backpressure_and_reserved_sync_credits(self):
        h = Harness(request(k=160, cols=160))
        h.until(lambda: h.owner.ports()['step'] is not None, step_ready=False)
        held = h.owner.ports()['step']
        for _ in range(40):
            e = h.cycle(step_ready=False)
            self.assertEqual(e['step'], held)
            self.assertLessEqual(e['reserved_after'], 4)
        self.assertIsNone(h.finish().status)
        self.assertEqual(h.owner.max_reserved, 4)

    def test_result_backpressure_all_contexts_and_owner_completion_fence(self):
        q = request(rows=128, cols=160)
        h = Harness(q)
        h.until(lambda: h.owner.group_started, done=False)
        h.until(lambda: h.owner.final_value is not None, tile_accept_ready=False, done=False)
        held = h.owner.final_value
        for _ in range(30):
            e = h.cycle(tile_accept_ready=False, done=False)
            self.assertIs(h.owner.final_value, held)
            self.assertFalse(e['result_fire'])
        h.until(lambda: h.owner.results_received == 5, done=False)
        self.assertFalse(h.owner.group_done)
        self.assertIsNone(h.owner.ports()['window_result'])
        h.until(lambda: h.owner.ports()['window_result'] is not None, window_result_ready=False)
        held_result = h.owner.ports()['window_result']
        q2 = replace(q, slot=1, reuse_a=True, block_id=2)
        for _ in range(20):
            e = h.cycle(window=q2, window_result_ready=False)
            self.assertFalse(e['window_fire'])
            self.assertEqual(e['window_result'], held_result)
        h.cycle()
        self.assertEqual(h.completion, held_result)
        h.submit(q2)
        self.assertIsNone(h.finish().status)

    def test_invalid_ranges_dtype_identity_alias_before_physical_access(self):
        good = request(k=1536)
        bad = [replace(good, k_begin=-2), replace(good, k_begin=1), replace(good, k_end=3),
               replace(good, k_end=1538), replace(good, k_begin=32, k_end=32),
               replace(good, k_begin=True), replace(good, block_id=0), replace(good, block_id=2**32),
               replace(good, block_id=True), replace(good, pair_reverse=1), replace(good, identity=0),
               replace(good, job=replace(good.job, output_bf16=True)),
               replace(good, job=replace(good.job, materialize_dense_output=True)),
               replace(good, job=replace(good.job, materialize_dense_output=1)),
               replace(good, job=replace(good.job, activation_bf16=1)),
               replace(good, job=replace(good.job, weight_bf16=1)),
               # Selected block is small, but full A/B/D alias spans must win.
               replace(good, k_end=32, job=replace(good.job, dst=good.job.a+64)),
               replace(good, k_end=32, job=replace(good.job, dst=good.job.b+1535*8960*2))]
        for q in bad:
            with self.subTest(q=q):
                h = Harness(q)
                self.assertIsNotNone(h.finish().status)
                self.assertEqual(h.commands, [])
                self.assertEqual(h.owner.rmw_commits, 0)
                self.assertEqual((h.completion.useful_macs, h.completion.executed_macs), (0, 0))
                self.assertIsNone(h.owner.lease)

    def test_lease_rejects_any_full_a_metadata_or_identity_change(self):
        for field, value in [('identity', 8), ('k', 64), ('a', 0x200000), ('m', 128), ('activation_bf16', False)]:
            h = Harness(request())
            h.finish()
            q = replace(h.q, slot=1, reuse_a=True, block_id=2)
            q = replace(q, identity=value) if field == 'identity' else replace(q, job=replace(q.job, **{field:value}))
            h.submit(q)
            self.assertIsNotNone(h.finish().status)
            self.assertIsNone(h.owner.lease)

    def test_bad_result_early_done_dma_error_abort_and_local_reset_drain(self):
        for fault in ('result', 'done', 'dma', 'abort', 'local_reset'):
            h = Harness(request(k=128, cols=64))
            h.until(lambda: h.owner.group_started and h.read is not None)
            if fault == 'result':
                h.cycle(result=m.MatrixResult(0, physical_result(0, 1)), done=False)
            elif fault == 'done':
                h.cycle(matrix_done=m.MatrixDone(h.q.job.tag), done=False)
            elif fault == 'dma':
                h.cycle(read_beat=m.ReadBeat(h.read.tag+1, h.read_words(h.read), True), done=False)
            else:
                h.cycle(**{fault:True}, dma=False, done=False)
                self.assertIsNotNone(h.owner.read_active)
                self.assertIsNone(h.owner.ports()['window_result'])
            r = h.finish()
            self.assertIsNotNone(r.status)
            self.assertFalse(r.committed)
            self.assertIsNone(h.owner.lease)
            self.assertEqual(h.owner.state, 'locked')
            self.assertFalse(h.owner.ports()['window_ready'])
            h.owner.tick(coordinated_reset=True)
            self.assertTrue(h.owner.ports()['window_ready'])
            self.assertFalse(h.owner.tiles.poison)

    def test_wrong_done_tag_and_nonfinite_result_fail(self):
        for bad in ('tag', 'finite'):
            h = Harness(request())
            h.until(lambda: bool(h.results), produce=False, done=False)
            if bad == 'finite':
                data = [list(row) for row in physical_result(0, 1)]
                data[0][0] = 0x7fc00000
                h.cycle(result=m.MatrixResult(0, tuple(tuple(r) for r in data)), done=False)
            else:
                h.until(lambda: h.owner.results_received == 1, done=False)
                h.cycle(matrix_done=m.MatrixDone(h.q.job.tag+1), done=False)
            self.assertIsNotNone(h.finish().status)

    def test_held_success_completion_immutable_but_abort_requires_reset(self):
        h = Harness(request())
        h.until(lambda: h.owner.ports()['window_result'] is not None, window_result_ready=False)
        held = h.owner.ports()['window_result']
        h.cycle(abort=True, window_result_ready=False)
        self.assertEqual(h.owner.ports()['window_result'], held)
        self.assertTrue(h.owner.ports()['reset_required'])
        self.assertIsNone(h.owner.lease)
        h.cycle()
        self.assertEqual(h.owner.state, 'locked')

    def test_default_disabled_does_not_admit_k_window(self):
        o = owner(False)
        e = o.tick(window=request())
        self.assertFalse(e['window_fire'])
        self.assertFalse(e['window_ready'])
        self.assertEqual(o.state, 'idle')
        self.assertEqual(o.traffic['a_read_bytes'], 0)

    def test_legacy_tick_copy_has_three_condition_changes_and_separate_fence_counter(self):
        before = inspect.getsource(m.window.FfnWindowOwnerModel.tick)
        after = inspect.getsource(m.KWindowOwnerModel._k_window_tick)
        expected = before.replace('def tick(', 'def _k_window_tick(', 1)
        for a,b in [('self.issue_k == self.chunk_end','self.issue_k == self.execution_end'),
                    ('self.job.k*self.contexts','self.execution_length*self.contexts'),
                    ('self.issue_k < self.job.k','self.issue_k < self.execution_end'),
                    ('self.a_fences += 1','self.k_a_fences += 1')]:
            expected = expected.replace(a,b)
        self.assertEqual(after, expected)

    def test_legacy_window_trace_exact_when_disabled_or_enabled(self):
        qk = request(k=32, cols=64)
        q = m.window.FfnWindowRequest(qk.job, qk.identity, qk.ng, qk.cols, qk.slot)
        ref = Harness(q, m.window.FfnWindowOwnerModel(owner().workspace, enable_ffn_window=True, enable_ffn_tiles=True))
        for enabled in (False, True):
            h = Harness(q, owner(enabled))
            reference = ref if not enabled else Harness(q, m.window.FfnWindowOwnerModel(owner().workspace, enable_ffn_window=True, enable_ffn_tiles=True))
            cycle = 0
            while h.completion is None:
                stalls = dict(step_ready=cycle%7 != 0, read_command_ready=cycle%5 != 0,
                              tile_accept_ready=cycle%3 != 0, window_result_ready=cycle%2 == 0)
                self.assertEqual(h.cycle(**stalls), reference.cycle(**stalls))
                cycle += 1
                self.assertLess(cycle, 10000)
            self.assertEqual(h.owner.a_banks.words, reference.owner.a_banks.words)
            self.assertEqual(h.owner.b_banks.words, reference.owner.b_banks.words)


class RealMatrixPartialTests(unittest.TestCase):
    def test_accepted_physical_packets_use_one_existing_matrix_and_retire_every_edge(self):
        import os
        import struct
        from candidates.qwen2_resident_matrix.official_bf16.test_owners import verified_library
        from candidates.qwen2_resident_matrix.ffn_attention import matrix_service as svc
        self.assertTrue(os.environ.get('MATRIX_SERVICE_LIBRARY'),
                        'MATRIX_SERVICE_LIBRARY and adjacent compile.json are required; no skip or compile fallback')
        # The established verifier checks source-before/after identities,
        # strict compiler flags/argv, selected path and actual ELF digest.
        lib = verified_library()
        self.assertEqual(lib.td_reset(), 0)
        service = svc.MatrixService(lib)

        completed_executed = 0
        for rows, k, split in ((16, 32, 16), (128, 128, 64), (16, 1536, 1024)):
            q = request(rows=rows, k=k, end=split)
            # Exact dyadic input fixture; actual Matrix output is independent.
            def source(kind, row, col):
                return (0x3f80 if k > 128 else 0x3f81) if kind == 'a' else 0x3f01
            h = ActualMatrixHarness(q, service=service, source=source)
            self.assertIsNone(h.finish().status)
            for block, begin, end in ((1, 0, split), (2, split, k)):
                current = q if block == 1 else replace(q, slot=1, reuse_a=True, block_id=2,
                                                       k_begin=begin, k_end=end)
                if block == 2:
                    h.submit(current)
                    self.assertIsNone(h.finish().status)
                self.assertEqual(h.completion.useful_macs, h.owner.accepted_steps*rows*32)
                self.assertEqual(h.completion.executed_macs, h.owner.accepted_steps*4096)
                completed_executed += h.completion.executed_macs
                self.assertEqual(completed_executed, service.report()['dense_fma_calls'])
                # This exact positive dyadic sum is representable in FP32 for
                # these lengths. It proves returned values are raw FP32 partials.
                expected = struct.unpack('<I', struct.pack('<f', (end-begin)*(1 if k > 128 else 129/128)*(129/256)))[0]
                got = consume(h.owner, current)
                self.assertTrue(all(word == expected for packet in got for word in packet), (rows, k, begin, end, hex(expected), [hex(x) for x in got[0][:4]]))
                if end-begin in (16, 64):
                    self.assertNotEqual(expected & 0xffff, 0)
                self.assertIsNone(service.owner)
            self.assertEqual(h.owner.k_a_fences, 1)
        counts = service.report()['counters']
        self.assertEqual(counts['owner_acquires'], 6)
        self.assertEqual(counts['owner_responses'], 6)
        self.assertEqual(counts['owner_releases'], 6)
        self.assertEqual(counts['dense_groups'], 6)
        self.assertEqual(counts['dense_results'], 6)
        self.assertEqual(counts['dense_done'], 6)
        self.assertEqual(counts['dense_steps'], 32+128+1536)
        self.assertEqual(service.report()['normal_fma_calls'], 0)
        self.assertEqual(service.report()['dense_fma_calls'], completed_executed)
        self.assertGreater(completed_executed, 0)
        self.assertFalse(service.report()['hardware_simulation'])


if __name__ == '__main__':
    unittest.main()
