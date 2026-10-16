"""Owner-backed protocol checks. Opaque Matrix tokens are not numeric or RTL proof."""
from collections import Counter, deque
from dataclasses import replace
import unittest

from candidates.qwen2_resident_matrix.raw_kv_parent import model as m
from candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain import DenseDrainRequest
from candidates.qwen2_resident_matrix.raw_kv.model import Key, Request, location


class DenseHarness:
    """Drive the original owner through real DMA, Matrix, and write-ACK ports."""
    def __init__(self, enabled=True):
        self.parent = m.ParentLoan(enabled=enabled)
        self.owner = self.parent.owner
        self.job = m.Job(m=16, k=32, n=32, write_bytes=2048)
        self.read = self.write = self.ack = None
        self.results = deque()
        self.counts = Counter()
        self.output = {}
        self.response = None
        self.tokens = tuple(tuple(0x3f000000 + row * 256 + col
                                 for col in range(256)) for row in range(16))
        self.parent.tick(job=self.job)

    def cycle(self, **overrides):
        o = self.owner
        inputs = {}
        if self.read is not None:
            inputs['read_beat'] = m.down.ReadBeat(self.read.tag, (0x3f80,) * 32, True)
        if self.results:
            inputs['result'] = self.results[0]
        if (o.group_started and not o.group_done and
                o.group_accepted_steps == self.job.k * o.contexts and
                o.results_received == o.contexts):
            inputs['matrix_done'] = m.down.MatrixDone(self.job.tag)
        if self.ack is not None:
            inputs['write_ack'] = self.ack
        inputs.update(overrides)
        edge = self.parent.tick(**inputs)
        e = edge['owner']
        for name, value in e.items():
            if name.endswith('_fire') and value:
                self.counts[name] += 1
        if e.get('read_fire'):
            self.read = None
        if e.get('read_command_fire'):
            self.read = e['read_command']
            self.counts[self.read.kind + '_reads'] += 1
        if e.get('step_fire') and e['step'].last:
            self.results.append(m.down.MatrixResult(e['step'].context, self.tokens))
        if e.get('result_fire'):
            self.results.popleft()
        if e.get('write_command_fire'):
            self.write = (e['write_command'], 0)
        if e.get('write_data_fire'):
            command, index = self.write
            self.output[command.address + 64 * index] = e['write_data'].words
            self.write = (command, index + 1)
            if e['write_data'].last:
                self.ack = m.down.WriteAck(command.tag, nbytes=command.beats * 64)
        if e.get('write_ack_fire'):
            self.ack = self.write = None
        if e.get('response_fire'):
            self.response = e['response']
        return edge

    def until(self, predicate, check=None, **inputs):
        for _ in range(10000):
            if predicate():
                return
            edge = self.cycle(**inputs)
            if check is not None:
                check(edge)
        raise AssertionError(('owner did not finish', self.owner.state,
                              self.owner.error, dict(self.counts)))


class ParentLoanTests(unittest.TestCase):
    def test_actual_dense_dma_matrix_ack_and_held_completion_fence(self):
        h = DenseHarness()
        p, o = h.parent, h.owner
        bank_words = o.a_banks.words
        self.assertIsInstance(o, m.DenseReductionOwner)
        self.assertIs(p.raw.banks, o.a_banks)
        self.assertIs(o.tiles.banks, o.a_banks)
        self.assertEqual(o.state, 'clear')

        def denied(edge):
            self.assertFalse(edge['drained'])
            self.assertFalse(edge['raw']['acquired'])
            self.assertTrue(edge['reserved'])

        h.until(lambda: o.ports()['response'] is not None,
                check=denied, acquire=7, response_ready=False)
        self.assertIsNone(o.error)
        self.assertEqual(h.counts['a_reads'], 16)
        self.assertEqual(h.counts['b_reads'], 32)
        self.assertEqual(o.rmw_commits, 512)
        self.assertEqual(h.counts['group_fire'], 1)
        self.assertEqual(h.counts['step_fire'], 32)
        self.assertEqual(h.counts['result_fire'], 1)
        self.assertEqual(h.counts['write_command_fire'], 16)
        self.assertEqual(h.counts['write_data_fire'], 32)
        self.assertEqual(h.counts['write_ack_fire'], 16)
        self.assertTrue(o.group_done)
        self.assertEqual(o.write_bytes, 2048)
        for row in range(16):
            for beat in range(2):
                expected = tuple(h.tokens[r][c] for r, c in
                                 (m.down.output_coordinate(row, beat * 16 + i)
                                  for i in range(16)))
                self.assertEqual(h.output[h.job.dst + row * 128 + beat * 64], expected)
        held = o.ports()['response']
        for _ in range(4):
            denied(h.cycle(acquire=7, response_ready=False))
            self.assertEqual(o.ports()['response'], held)
        edge = h.cycle(acquire=7)
        denied(edge)  # Consuming a completion cannot authorize this same edge.
        self.assertTrue(edge['owner']['response_fire'])
        self.assertEqual(h.response, (h.job.tag, None, 2048))
        self.assertEqual(o.state, 'idle')
        self.assertFalse(any(p.debts().values()))
        edge = p.tick(acquire=7, job=replace(h.job, tag=2))
        self.assertTrue(edge['drained'])
        self.assertTrue(edge['raw']['acquired'])
        self.assertFalse(edge['owner']['job_ready'])
        self.assertIs(o.job, h.job)
        self.assertIs(o.a_banks.words, bank_words)

    def test_default_off_preserves_actual_dense_execution(self):
        h = DenseHarness(enabled=False)
        h.until(lambda: h.response is not None, acquire=7)
        self.assertEqual(h.response, (1, None, 2048))
        self.assertIsNone(h.parent.raw.owner)
        self.assertFalse(h.parent.poison)
        self.assertEqual(h.owner.accepted_steps, 32)
        self.assertEqual(h.owner.rmw_commits, 512)
        p = m.ParentLoan()
        edge = p.tick(acquire=7, request=Request(Key(7, 1, 0, True), 99),
                      job=m.Job(m=16, k=32, n=32))
        self.assertFalse(edge['reserved'])
        self.assertFalse(edge['raw']['acquired'] or edge['raw']['accepted'])
        self.assertEqual(p.owner.state, 'clear')

    def test_raw_write_hold_abort_ack_release_cannot_admit_dense(self):
        p = m.ParentLoan(enabled=True)
        o = p.owner
        job = m.Job(m=16, k=32, n=32)
        self.assertTrue(p.tick(acquire=7, job=job)['raw']['acquired'])
        self.assertIsNone(o.job)
        key = Key(7, 11, 4095, True)
        payload = int.from_bytes(bytes.fromhex('0000807f000080ff0100c07f00000080') * 4, 'little')
        edge = p.tick(request=Request(key, payload), job=job)
        self.assertTrue(edge['raw']['accepted'])
        lo, hi, word = location(key.line)
        self.assertEqual(o.a_banks.writes, {lo: word, hi: word})
        self.assertEqual(o.a_banks.words[lo][word], payload & ((1 << 256) - 1))
        self.assertEqual(o.a_banks.words[hi][word], payload >> 256)
        self.assertIsNone(p.raw.response)
        edge = p.tick(ack=key, release=7, abort=True, soft_reset=True, job=job)
        self.assertFalse(edge['raw']['acked'] or edge['raw']['released'])
        held = p.raw.response
        self.assertEqual(held.key, key)
        self.assertTrue(p.raw.poison)
        self.assertIsNone(o.error)  # Borrower reset is not Dense/backend reset.
        for _ in range(4):
            edge = p.tick(ack=Key(8, 11, 4095, True), release=7, job=job)
            self.assertFalse(edge['raw']['acked'] or edge['raw']['released'])
            self.assertEqual(p.raw.response, held)
            self.assertFalse(edge['owner']['job_ready'])
            self.assertIsNone(o.job)
            self.assertFalse(o.a_banks.reads or o.a_banks.writes)
        edge = p.tick(ack=key, release=7, job=job)
        self.assertTrue(edge['raw']['acked'])
        self.assertFalse(edge['raw']['released'])
        edge = p.tick(release=7, job=job)
        self.assertTrue(edge['raw']['released'])
        self.assertIsNone(o.job)
        self.assertFalse(p.tick(job=job)['owner']['job_ready'])
        p.tick(soft_reset=True, job=job)
        self.assertIsNone(o.job)
        self.assertFalse(p.raw.poison)
        p.tick(job=job)
        self.assertIs(o.job, job)
        self.assertEqual(o.state, 'clear')

    def test_raw_abort_blocks_same_edge_job_window_drain_and_tile(self):
        job = m.Job(m=16, k=32, n=32, write_bytes=2048)
        offers = dict(job=job,
                      window=m.drain.FfnWindowRequest(job, 9, 0, 32, 0),
                      drain=DenseDrainRequest(job, 9, 0, 32),
                      tile_control=m.drain.Control(0, 0, 9, 0, 16, 32))
        for name, offer in offers.items():
            with self.subTest(offer=name):
                p = m.ParentLoan(enabled=True)
                edge = p.tick(abort=True, **{name: offer})
                self.assertTrue(edge['reserved'])
                self.assertFalse(edge['raw']['acquired'] or edge['raw']['accepted'])
                self.assertFalse(any(edge['owner'][k] for k in
                                     ('job_ready', 'window_ready', 'drain_ready')))
                self.assertFalse(edge['owner'].get('window_fire', False))
                self.assertFalse(edge['owner'].get('drain_fire', False))
                self.assertFalse(edge['owner']['tile']['ctl_fire'])
                self.assertFalse(edge['owner']['tile']['ctl_ready'])
                self.assertEqual(p.owner.state, 'idle')
                self.assertIsNone(p.owner.job)
                self.assertIsNone(p.owner.window_request)
                self.assertIsNone(p.owner.drain_request)
                self.assertFalse(p.owner.a_banks.reads or p.owner.a_banks.writes)

    def test_backend_abort_cannot_grant_a_simultaneous_acquire(self):
        p = m.ParentLoan(enabled=True)
        edge = p.tick(acquire=7, backend_abort=True)
        self.assertFalse(edge['drained'])
        self.assertFalse(edge['raw']['acquired'])
        self.assertIsNone(p.raw.owner)
        self.assertIsNotNone(p.owner.error)
        self.assertFalse(p.tick(acquire=7)['raw']['acquired'])

    def test_backend_abort_with_matching_fill_ack_drains_without_publication(self):
        p = m.ParentLoan(enabled=True)
        key = Key(7, 1, 8, True)
        self.assertTrue(p.tick(acquire=7)['raw']['acquired'])
        self.assertTrue(p.tick(request=Request(key, 0x123456))['raw']['accepted'])
        p.tick()
        self.assertEqual(p.raw.response.key, key)
        valid = set()
        edge = p.tick(backend_abort=True, ack=key, release=7)
        self.assertTrue(edge['raw']['acked'])
        self.assertTrue(p.raw.poison)
        if edge['raw']['acked'] and not p.raw.poison:
            valid.add(key.line)
        self.assertFalse(valid)
        self.assertIsNone(p.raw.response)
        self.assertTrue(p.raw.drained)
        self.assertFalse(edge['raw']['released'])
        self.assertIsNotNone(p.owner.error)
        next_request = Request(Key(7, 2, 9, True), 0xabcdef)
        self.assertFalse(p.tick(request=next_request)['raw']['accepted'])
        self.assertFalse(p.owner.a_banks.reads or p.owner.a_banks.writes)
        self.assertTrue(p.tick(release=7)['raw']['released'])
        self.assertIsNone(p.raw.owner)
        self.assertFalse(p.tick(acquire=8)['raw']['acquired'])

    def test_borrower_abort_reset_preserves_active_dense_debt_and_completion(self):
        h = DenseHarness()
        p, o = h.parent, h.owner
        h.until(lambda: h.read is not None)
        read_debt = o.read_active
        self.assertIsNotNone(read_debt)
        edge = h.cycle(acquire=7, abort=True, soft_reset=True, read_beat=None)
        self.assertFalse(edge['raw']['acquired'])
        self.assertFalse(edge['owner']['read_fire'])
        self.assertEqual(o.read_active, read_debt)
        self.assertIsNone(o.error)
        h.until(lambda: h.ack is not None, matrix_done=None)
        write_debt = o.accepted_write
        self.assertEqual(o.write_state, 'ack')
        self.assertTrue(o.group_started)
        self.assertFalse(o.group_done)
        edge = h.cycle(acquire=7, abort=True, soft_reset=True,
                       write_ack=None, matrix_done=None)
        self.assertFalse(edge['raw']['acquired'])
        self.assertFalse(edge['owner']['write_ack_fire'])
        self.assertEqual(o.write_state, 'ack')
        self.assertIs(o.accepted_write, write_debt)
        self.assertFalse(o.group_done)
        self.assertIsNone(o.error)
        h.until(lambda: h.response is not None)
        self.assertEqual(h.response, (1, None, 2048))
        self.assertEqual(o.rmw_commits, 512)
        self.assertEqual(h.counts['write_ack_fire'], 16)
        self.assertTrue(p.tick(acquire=7)['raw']['acquired'])

    def test_retained_a_requires_prior_edge_invalidation(self):
        p = m.ParentLoan(enabled=True)
        p.owner.lease = m.drain.ALease(0x100000, True, 16, 32, 64, 9)
        self.assertTrue(p.debts()['retained_a'])
        edge = p.tick(acquire=7, invalidate_lease=True)
        self.assertFalse(edge['drained'])
        self.assertFalse(edge['raw']['acquired'])
        self.assertIsNone(p.owner.lease)
        self.assertTrue(p.tick(acquire=7)['raw']['acquired'])

    def test_real_tile_lease_blocks_raw_and_acquire_reserves_external_ports(self):
        p = m.ParentLoan(enabled=True)
        control = m.drain.Control(0, 0, 9, 0, 16, 32)
        edge = p.tick(tile_control=control)
        self.assertTrue(edge['owner']['tile']['ctl_fire'])
        self.assertTrue(p.owner.tiles.leased)
        self.assertTrue(p.debts()['tile'])
        edge = p.tick(acquire=7, tile_write=m.drain.Write(0, 9, 0, 0, (0,) * 16))
        self.assertFalse(edge['raw']['acquired'])
        self.assertFalse(edge['owner']['tile']['write_fire'])
        self.assertEqual(p.owner.tiles.tags[0].produced, 0)
        self.assertFalse(p.owner.a_banks.reads or p.owner.a_banks.writes)

    def test_unsolicited_original_replies_poison_and_cannot_grant(self):
        replies = dict(read_beat=m.down.ReadBeat(1, (0,) * 32, True),
                       result=m.down.MatrixResult(0, ((0,) * 256,) * 16),
                       matrix_done=m.down.MatrixDone(1),
                       write_ack=m.down.WriteAck(1),
                       seed_ack=m.down.SeedAck(m.down.SeedRequest(1, 1, 1, 0)))
        for name, reply in replies.items():
            with self.subTest(reply=name):
                p = m.ParentLoan(enabled=True)
                edge = p.tick(acquire=7, **{name: reply})
                self.assertFalse(edge['drained'])
                self.assertFalse(edge['raw']['acquired'])
                self.assertTrue(p.poison)
                self.assertFalse(p.tick(acquire=7)['raw']['acquired'])
        p = m.ParentLoan(enabled=True)
        p.tick(acquire=7)
        key = Key(7, 1, 0, False)
        p.tick(request=Request(key))
        p.tick(read_beat=replies['read_beat'])
        self.assertTrue(p.poison)
        self.assertTrue(p.raw.poison)
        self.assertEqual(p.raw.response.key, key)
        p.tick(soft_reset=True)
        self.assertEqual(p.raw.response.key, key)
        self.assertTrue(p.poison)
        edge = p.tick(ack=key, release=7)
        self.assertTrue(edge['raw']['acked'])
        self.assertFalse(edge['raw']['released'])
        self.assertIsNone(p.raw.response)
        self.assertTrue(p.raw.drained)
        self.assertTrue(p.raw.poison)
        self.assertTrue(p.tick(release=7)['raw']['released'])
        self.assertFalse(p.tick(acquire=8)['raw']['acquired'])

    def test_all_owner_debt_categories_are_conservative(self):
        # Deliberately isolated register snapshots test the mapper, separately
        # from the real transfer lifecycle above. No synthetic grant attestation.
        cases = [
            ('state', 'state', 'locked'), ('status', 'error', 'fault'),
            ('burst', 'read_active', object()),
            ('activation_high', 'a_hold', deque()),
            ('activation_rmw', 'a_rmw_pending', []),
            ('operand_return', 'pending', object()),
            ('operand_fifo', 'fifo', deque([object()])),
            ('seed', 'seed_outstanding', True), ('seed', 'seed_state', 'ack'),
            ('matrix', 'group_started', True), ('write', 'write_state', 'ack'),
            ('window', 'window_request', object()), ('window', 'window_result', object()),
            ('drain', 'drain_request', object()), ('drain', 'drain_result', object()),
            ('drain', 'drain_expected', object()), ('retained_a', 'lease', object()),
            ('drain_poison', 'drain_poison', True), ('completion', 'state', 'finish'),
        ]
        observed = set()
        for debt, field, value in cases:
            with self.subTest(debt=debt, field=field):
                p = m.ParentLoan(enabled=True)
                self.assertFalse(any(p.debts().values()))
                setattr(p.owner, field, value)
                self.assertTrue(p.debts()[debt])
                observed.add(debt)
        for field, value in (('pending', object()), ('response', object()), ('poison', True)):
            p = m.ParentLoan(enabled=True)
            setattr(p.owner.tiles, field, value)
            self.assertTrue(p.debts()['tile'])
        p = m.ParentLoan(enabled=True)
        p.owner.tiles.tags[2].live = True
        self.assertTrue(p.debts()['tile'])
        p = m.ParentLoan(enabled=True)
        p.poison = True
        self.assertTrue(p.debts()['parent_poison'])
        self.assertEqual(observed | {'tile', 'parent_poison'}, set(p.debts()))


if __name__ == '__main__':
    unittest.main()
