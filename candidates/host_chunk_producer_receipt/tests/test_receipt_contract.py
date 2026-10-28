"""Executable provenance contract model only; NOT Scala, Chisel or DUT evidence."""
from copy import deepcopy
import unittest

MAX_OWNER = (1 << 32) - 1


def fixture(p=0, c=1, txn=7, epoch=11, heads=16, tokens=128):
    source = dict(tokens=tokens, layout=dict(keyHeads=16, valueHeads=heads,
        layoutId=0, layoutVersion=1, rowBytes=heads * 1600),
        reductionPolicy=int(heads == 32), gatePolicy=2 if heads == 32 else 0,
        conv=0x100000, ab=0x300000, aLog=0x400000, dtBias=0x500000,
        output=0x600000, tag=p)
    receipt = dict(producer=dict(transactionId=txn, hostEpoch=epoch, ownerSequence=p),
        result=dict(accepted=deepcopy(source), tag=p, status=0,
                    writeBytes=tokens * heads * 1600, cycles=9001, outputCommitted=True))
    job = dict(tag=c, tokens=tokens, input=source['output'], layout=deepcopy(source['layout']),
        reductionPolicy=source['reductionPolicy'], gatePolicy=source['gatePolicy'],
        binding=dict(transactionId=txn, hostEpoch=epoch, producerOwner=p, source=deepcopy(source)))
    return receipt, job


class Capture:
    def __init__(self):
        self.receipt = None
        self.poison = False

    def tick(self, receipt, job, *, child_fire=True, physical_fire=True, owned=True,
             prep_shape=True, context_current=True, physical_owner=None,
             generic=None, lease=True, await_prepare=False, fault=False,
             replacement=False, authority_accepted=True, current_txn=None,
             current_epoch=None, full_host_equal=True):
        """State update matching the installed helper's actual event conditions."""
        r = receipt['result']; p = receipt['producer']; b = job['binding']
        old_valid = self.receipt is not None
        physical_owner = b['producerOwner'] if physical_owner is None else physical_owner
        generic = {k: r[k] for k in ('tag', 'status', 'writeBytes', 'cycles')} if generic is None else generic
        current_txn = b['transactionId'] if current_txn is None else current_txn
        current_epoch = b['hostEpoch'] if current_epoch is None else current_epoch
        old_current = not old_valid or (authority_accepted and full_host_equal and
            current_txn == self.receipt['producer']['transactionId'] and
            current_epoch == self.receipt['producer']['hostEpoch'])
        old_fault = fault or self.poison
        if replacement:
            self.receipt = None
        if child_fire:
            exact = owned and prep_shape and context_current and physical_fire and (
                r['tag'] == physical_owner and r['accepted'] == b['source'] and
                all(generic[k] == r[k] for k in generic))
            success = exact and lease and not await_prepare and r['status'] == 0 and r['outputCommitted'] and (
                r['writeBytes'] == job['tokens'] * job['layout']['rowBytes'])
            if not exact or (r['status'] == 0 and not success) or old_valid:
                self.poison = True
                self.receipt = None
            elif success and not old_fault:
                # Identity comes from actual retained lease, never receipt caller.
                self.receipt = dict(producer=dict(transactionId=b['transactionId'],
                    hostEpoch=b['hostEpoch'], ownerSequence=physical_owner), result=deepcopy(r))
        if old_fault or (old_valid and not old_current):
            self.receipt = None

    def eligible(self, *, current=True, fault=False, replacement=False, busy=False, slots_drained=True,
                 borrower_drained=True):
        return bool(self.receipt is not None and current and not fault and not self.poison and not replacement and
                    not busy and slots_drained and borrower_drained)


class Consumer:
    def __init__(self):
        self.last = None

    def accept(self, receipt, job, *, fire=True, fault=False, drained=True, waiting=True):
        p = receipt['producer']; r = receipt['result']; a = r['accepted']; b = job['binding']
        fresh = self.last is None or (p['transactionId'] >= self.last[0] and
            p['ownerSequence'] > self.last[1] and p['ownerSequence'] > self.last[2] and job['tag'] > self.last[2])
        good = r['status'] == 0 and r['outputCommitted'] and fresh and (
            p['transactionId'] == b['transactionId'] and p['hostEpoch'] == b['hostEpoch'] and
            p['ownerSequence'] == b['producerOwner'] and p['ownerSequence'] != MAX_OWNER and
            job['tag'] != MAX_OWNER and job['tag'] > p['ownerSequence'] and
            r['tag'] == p['ownerSequence'] and a['tag'] == p['ownerSequence'] and
            a == b['source'] and a['tokens'] == job['tokens'] and a['layout'] == job['layout'] and
            a['output'] == job['input'] and a['reductionPolicy'] == job['reductionPolicy'] and
            a['gatePolicy'] == job['gatePolicy'] and r['writeBytes'] == job['tokens'] * job['layout']['rowBytes'])
        if fire and waiting and drained and not fault and good:
            self.last = p['transactionId'], p['ownerSequence'], job['tag']
            return True
        return False


class ReceiptContract(unittest.TestCase):
    def test_real_fire_required(self):
        r, j = fixture()
        for key in ('child_fire', 'physical_fire', 'owned', 'prep_shape', 'context_current', 'lease'):
            with self.subTest(key=key):
                capture = Capture(); capture.tick(r, j, **{key: False})
                self.assertFalse(capture.eligible())
        capture = Capture(); capture.tick(r, j)
        self.assertEqual(capture.receipt, r)

    def test_capture_exact_payload_and_generic_identity(self):
        r, j = fixture()
        for key in ('tag', 'status', 'writeBytes', 'cycles'):
            with self.subTest(key=key):
                generic = {k: r['result'][k] for k in ('tag', 'status', 'writeBytes', 'cycles')}
                generic[key] += 1
                capture = Capture(); capture.tick(r, j, generic=generic)
                self.assertFalse(capture.eligible())
        for key in ('conv', 'ab', 'aLog', 'dtBias', 'output', 'tag', 'tokens'):
            with self.subTest(key=key):
                bad = deepcopy(r); bad['result']['accepted'][key] += 64
                capture = Capture(); capture.tick(bad, j)
                self.assertFalse(capture.eligible())

    def test_capture_not_geometry_success(self):
        r, j = fixture()
        for changes in ({'status': 4}, {'outputCommitted': False}, {'writeBytes': 6553600}):
            bad = deepcopy(r); bad['result'].update(changes)
            capture = Capture(); capture.tick(bad, j)
            self.assertFalse(capture.eligible())
        for changes in ({'await_prepare': True}, {'fault': True}):
            capture = Capture(); capture.tick(r, j, **changes)
            self.assertFalse(capture.eligible())

    def test_lifetime_kills_snapshot(self):
        r, j = fixture()
        for changes in ({'fault': True}, {'replacement': True}, {'authority_accepted': False},
                        {'current_txn': 8}, {'current_epoch': 12}, {'full_host_equal': False}):
            capture = Capture(); capture.tick(r, j)
            self.assertTrue(capture.eligible())
            capture.tick(r, j, child_fire=False, **changes)
            self.assertFalse(capture.eligible())
        capture = Capture(); capture.tick(r, j); capture.tick(r, j)
        self.assertTrue(capture.poison); self.assertFalse(capture.eligible())
        self.assertFalse(Capture().eligible())  # reset

    def test_success_does_not_forge_lease_retirement(self):
        r, j = fixture(); capture = Capture(); capture.tick(r, j)
        for changes in ({'current': False}, {'fault': True}, {'replacement': True}, {'busy': True},
                        {'slots_drained': False}, {'borrower_drained': False}):
            self.assertFalse(capture.eligible(**changes))
        self.assertTrue(capture.eligible())

    def test_two_runtime_layouts_and_zero_producer(self):
        for heads in (16, 32):
            for tokens in (16, 128):
                r, j = fixture(heads=heads, tokens=tokens)
                self.assertTrue(Consumer().accept(r, j))
                self.assertEqual(r['result']['tag'], 0)  # original P not C

    def test_stale_transaction_epoch_wrong_producer(self):
        r, j = fixture()
        for key in ('transactionId', 'hostEpoch', 'ownerSequence'):
            bad = deepcopy(r); bad['producer'][key] += 1
            self.assertFalse(Consumer().accept(bad, j), key)
        for key in ('tag',):
            bad = deepcopy(r); bad['result'][key] += 1
            self.assertFalse(Consumer().accept(bad, j), key)

    def test_all_source_addresses_layout_and_policies(self):
        r, j = fixture()
        for key in ('conv', 'ab', 'aLog', 'dtBias', 'output', 'tag', 'tokens', 'reductionPolicy', 'gatePolicy'):
            bad = deepcopy(r); bad['result']['accepted'][key] += 1
            self.assertFalse(Consumer().accept(bad, j), key)
        for key in r['result']['accepted']['layout']:
            bad = deepcopy(r); bad['result']['accepted']['layout'][key] += 1
            self.assertFalse(Consumer().accept(bad, j), key)

    def test_wrong_bytes_status_commit_and_owner_order(self):
        r, j = fixture(p=2, c=3)
        for changes in ({'status': 1}, {'outputCommitted': False}, {'writeBytes': r['result']['writeBytes'] + 64}):
            bad = deepcopy(r); bad['result'].update(changes)
            self.assertFalse(Consumer().accept(bad, j))
        for c in (0, 1, 2, MAX_OWNER):
            bad = deepcopy(j); bad['tag'] = c
            self.assertFalse(Consumer().accept(r, bad))
        r, j = fixture(p=MAX_OWNER, c=MAX_OWNER)
        self.assertFalse(Consumer().accept(r, j))

    def test_no_consumption_on_valid_only_poison_or_no_drain(self):
        r, j = fixture(); consumer = Consumer()
        for changes in ({'fire': False}, {'fault': True}, {'drained': False}, {'waiting': False}):
            self.assertFalse(consumer.accept(r, j, **changes))
            self.assertIsNone(consumer.last)
        self.assertTrue(consumer.accept(r, j))

    def test_duplicate_and_reuse_rejected(self):
        r, j = fixture(p=2, c=3); consumer = Consumer()
        self.assertTrue(consumer.accept(r, j))
        self.assertFalse(consumer.accept(r, j))
        later_c = deepcopy(j); later_c['tag'] = 4
        self.assertFalse(consumer.accept(r, later_c))
        # New transaction is not permission to reuse an old physical owner.
        reused, reused_job = fixture(p=2, c=5, txn=8)
        self.assertFalse(consumer.accept(reused, reused_job))
        stale, stale_job = fixture(p=4, c=5, txn=6)
        self.assertFalse(consumer.accept(stale, stale_job))
        next_r, next_j = fixture(p=4, c=5, txn=8)
        self.assertTrue(consumer.accept(next_r, next_j))


if __name__ == '__main__':
    unittest.main(verbosity=2)
