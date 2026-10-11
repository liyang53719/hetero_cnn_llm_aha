#!/usr/bin/env python3
"""Abstract queue/interface contract, NOT a Chisel/RTL simulator or arithmetic model.

The source identity check pins this contract to the candidate. This model follows
the existing metadata/result credit and poison transitions relevant to tags.
Endpoint command latency, slice clocks and arithmetic are deliberately absent.
`token` is external scoreboard identity, never a proposed endpoint signal.
"""
from collections import deque
from dataclasses import dataclass, replace
import random
import unittest


@dataclass(frozen=True)
class Step:
    tag: int
    token: int
    context: int = 0
    clear: bool = False
    last: bool = False
    finish: bool = False
    emit: bool = True


@dataclass(frozen=True)
class Return:
    token: int
    context: int = 0
    last: bool = False


@dataclass(frozen=True)
class Result:
    tag: object
    token: int
    context: int
    last: bool
    error: bool


class QueueContract:
    def __init__(self, bits=16):
        if not 0 <= bits <= 32:
            raise ValueError("returnTagBits must be in 0..32")
        self.bits = bits
        self.reset()

    def reset(self):
        self.tags = deque()
        self.values = deque()
        self.seen = set()
        self.closed = set()
        self.state = "idle"
        self.poison = False
        self.end_issued = False

    def begin(self):
        assert self.state == "idle" and not self.poison
        assert not self.tags and not self.values
        # A legal group and its endpoint command have already handshaken.
        self.seen.clear()
        self.closed.clear()
        self.end_issued = False
        self.state = "running"

    def cycle(self, step=None, returned=None, ready=False, abort=False,
              completion=False, completion_bad=False, endpoint_error=False,
              done_ready=False, reset=False):
        if reset:
            self.reset()
            return {"reset": True}
        old = self.state
        offered = self.values[0] if self.values else None
        result_fire = offered is not None and ready
        value_credit = len(self.values) < 2 or result_fire
        done_valid = old == "finish" and not self.values
        work = old == "running" and not self.end_issued and not abort
        head = self.tags[0] if self.tags else None
        consume = (old in ("running", "ending", "draining") and
                   head is not None and returned is not None and
                   (old == "draining" or not head.emit or value_credit))
        output_bad = bool(consume and (returned.context != head.context or returned.last != head.last))
        tag_credit = len(self.tags) < 8 or consume
        legal = step is not None and (0 <= step.context < 5 and
                step.clear == (step.context not in self.seen) and
                step.context not in self.closed and
                (not step.finish or (step.last and
                 self.closed | {step.context} == self.seen | {step.context})))
        input_fire = step is not None and work and (tag_credit if legal else True)
        accepted = bool(input_fire and legal)
        next_state = old
        if result_fire:
            self.values.popleft()
        if old == "draining" and head is None:
            next_state = "finish"
        if consume:
            self.tags.popleft()
            if head.emit and old != "draining":
                self.values.append(Result(head.tag if self.bits else None, returned.token,
                                          head.context, head.last, output_bad or self.poison))
            if head.finish and old != "draining":
                next_state = "ending"
        if input_fire:
            if not legal:
                self.poison = True
                next_state = "draining"
            else:
                if self.bits and not 0 <= step.tag < (1 << self.bits):
                    raise ValueError("tag does not fit the selected wire width")
                self.tags.append(step)
                self.seen.add(step.context)
                if step.last:
                    self.closed.add(step.context)
                self.end_issued |= step.finish
        if old == "ending" and completion:
            self.poison |= completion_bad
            next_state = "finish"
        if done_valid and done_ready:
            next_state = "locked" if self.poison else "idle"
        if (abort or endpoint_error or output_bad) and old not in ("idle", "finish", "locked", "draining"):
            self.poison = True
            next_state = "draining"
        self.state = next_state
        assert len(self.tags) <= 8 and len(self.values) <= 2
        return {"accepted": accepted, "input_fire": input_fire, "consumed": bool(consume),
                "offered": offered, "delivered": offered if result_fire else None,
                "done_valid": done_valid, "done_error": self.poison,
                "output_bad": output_bad}


class ReturnTagContractTests(unittest.TestCase):
    def running(self, bits=16):
        model = QueueContract(bits)
        model.begin()
        return model

    def test_width_contract(self):
        for bits in (0, 1, 16, 32):
            self.assertEqual(QueueContract(bits).bits, bits)
        for bits in (-1, 33, 1024):
            with self.assertRaises(ValueError):
                QueueContract(bits)

    def test_eight_metadata_entries_and_pipe_replacement(self):
        m = self.running()
        for i in range(8):
            self.assertTrue(m.cycle(Step(i, i, clear=(i == 0)))["accepted"])
        self.assertFalse(m.cycle(Step(8, 8))["accepted"])
        self.assertEqual([s.tag for s in m.tags], list(range(8)))
        r = m.cycle(Step(8, 8), Return(0))
        self.assertTrue(r["accepted"] and r["consumed"])
        self.assertEqual([s.tag for s in m.tags], list(range(1, 9)))
        self.assertEqual(m.values[0].tag, 0)

    def test_two_results_and_backpressure_hold(self):
        m = self.running()
        for i in range(3):
            m.cycle(Step(i, i, clear=(i == 0)))
        m.cycle(returned=Return(0))
        m.cycle(returned=Return(1))
        held = m.values[0]
        for _ in range(20):
            r = m.cycle(returned=Return(2))
            self.assertFalse(r["consumed"])
            self.assertEqual(r["offered"], held)
        r = m.cycle(returned=Return(2), ready=True)
        self.assertEqual(r["delivered"].tag, 0)
        self.assertTrue(r["consumed"])
        self.assertEqual([v.tag for v in m.values], [1, 2])

    def test_live_input_tag_never_leaks_and_nonemit_is_discarded(self):
        m = self.running()
        m.cycle(Step(31, 0, clear=True, emit=False))
        m.cycle(Step(47, 1))
        self.assertTrue(m.cycle(returned=Return(0))["consumed"])
        self.assertFalse(m.values)
        # A distinct live input is simultaneously accepted; return uses old head.
        m.cycle(Step(65535, 2), Return(1))
        self.assertEqual(m.values[0].tag, 47)
        self.assertEqual(m.tags[0].tag, 65535)

    def test_result_waits_for_actual_return_and_done_waits_for_drain(self):
        m = self.running()
        m.cycle(Step(7, 0, clear=True, last=True, finish=True))
        for _ in range(12):
            r = m.cycle(ready=True, completion=True)
            self.assertIsNone(r["offered"])
            self.assertFalse(r["done_valid"])
        m.cycle(returned=Return(0, last=True))
        self.assertEqual(m.state, "ending")
        self.assertFalse(m.cycle(completion=True)["done_valid"])
        self.assertEqual(m.state, "finish")
        self.assertFalse(m.cycle()["done_valid"])
        self.assertFalse(m.cycle(ready=True)["done_valid"])
        self.assertTrue(m.cycle(done_ready=True)["done_valid"])
        self.assertEqual(m.state, "idle")

    def test_causal_last_tag_survives_inactive_suffix(self):
        m = self.running()
        for k in range(6):
            m.cycle(Step(k, k, clear=(k == 0), emit=(k == 3), last=(k == 5), finish=(k == 5)))
        for k in range(6):
            m.cycle(returned=Return(k, last=(k == 5)))
        self.assertEqual([(v.tag, v.token) for v in m.values], [(3, 3)])
        self.assertEqual(m.state, "ending")

    def test_abort_preserves_buffered_provisional_values_then_locks(self):
        m = self.running()
        for i in range(3):
            m.cycle(Step(i, i, clear=(i == 0)))
        m.cycle(returned=Return(0))
        # Existing service can enqueue a return on the cycle abort arrives.
        m.cycle(returned=Return(1), abort=True)
        self.assertEqual([v.tag for v in m.values], [0, 1])
        self.assertTrue(m.poison)
        self.assertEqual(m.state, "draining")
        m.cycle(returned=Return(2), abort=True)
        self.assertEqual([v.tag for v in m.values], [0, 1])
        m.cycle(abort=True)
        self.assertEqual(m.state, "finish")
        self.assertFalse(m.cycle(ready=True)["done_valid"])
        self.assertFalse(m.cycle(ready=True)["done_valid"])
        r = m.cycle(done_ready=True, abort=True)
        self.assertTrue(r["done_valid"] and r["done_error"])
        self.assertEqual(m.state, "locked")
        self.assertFalse(m.cycle(Step(50, 50, clear=True))["accepted"])

    def test_reset_discards_metadata_and_results(self):
        m = self.running()
        m.cycle(Step(10, 0, clear=True))
        m.cycle(Step(20, 1), Return(0))
        m.cycle(reset=True)
        self.assertFalse(m.tags or m.values or m.poison)
        m.begin()
        m.cycle(Step(99, 2, clear=True))
        m.cycle(returned=Return(2))
        self.assertEqual([v.tag for v in m.values], [99])

    def test_context_or_last_mismatch_poison_without_retagging(self):
        for returned in (Return(77, context=1), Return(77, last=True)):
            m = self.running()
            m.cycle(Step(12, 0, clear=True))
            r = m.cycle(returned=returned)
            self.assertTrue(r["output_bad"])
            self.assertEqual(m.values[0].tag, 12)
            self.assertTrue(m.values[0].error)
            self.assertEqual(m.state, "draining")

    def test_same_context_same_last_reordering_is_not_detectable(self):
        m = self.running()
        m.cycle(Step(10, 0, clear=True))
        m.cycle(Step(11, 1))
        r = m.cycle(returned=Return(1))  # An illegal external reorder.
        self.assertFalse(r["output_bad"])
        self.assertEqual((m.values[0].tag, m.values[0].token), (10, 1))
        self.assertFalse(m.values[0].error)
        # External token oracle catches association failure; hardware cannot.
        self.assertNotEqual(m.values[0].tag, {0: 10, 1: 11}[m.values[0].token])

    def test_illegal_clear_is_not_tagged(self):
        m = self.running()
        r = m.cycle(Step(42, 0, clear=False))
        self.assertTrue(r["input_fire"])
        self.assertFalse(r["accepted"])
        self.assertFalse(m.tags)
        self.assertEqual(m.state, "draining")

    def test_multicontext_closure_and_opaque_duplicate_tags(self):
        m = self.running()
        steps = [Step(65535, 0, context=0, clear=True),
                 Step(0, 1, context=1, clear=True, last=True),
                 Step(65535, 2, context=0, last=True, finish=True)]
        for step in steps:
            self.assertTrue(m.cycle(step)["accepted"])
        observed = []
        for step in steps:
            r = m.cycle(returned=Return(step.token, step.context, step.last), ready=True)
            if r["delivered"]:
                observed.append(r["delivered"])
        observed.append(m.cycle(ready=True, completion=True)["delivered"])
        self.assertEqual([(v.tag, v.context, v.last) for v in observed],
                         [(s.tag, s.context, s.last) for s in steps])
        self.assertFalse(m.poison)
        self.assertTrue(m.cycle()["done_valid"])

    def test_random_ordering_backpressure_default_zero_equivalence(self):
        for seed in range(12):
            rng = random.Random(seed)
            enabled, disabled = self.running(), self.running(0)
            issued, expected, observed = deque(), [], []
            next_token = 0
            previous_stall = None
            for cycle in range(20000):
                step = None
                if next_token < 200 and rng.random() < .78:
                    step = Step(rng.randrange(65536), next_token, clear=(next_token == 0),
                                emit=(rng.random() < .65), last=(next_token == 199), finish=(next_token == 199))
                ret = Return(issued[0].token, last=issued[0].last) if issued and rng.random() < .63 else None
                ready = rng.random() < .43
                completion = rng.random() < .55
                args = dict(step=step, returned=ret, ready=ready, completion=completion, done_ready=True)
                a, b = enabled.cycle(**args), disabled.cycle(**args)
                for key in ("accepted", "input_fire", "consumed", "done_valid", "done_error", "output_bad"):
                    self.assertEqual(a[key], b[key])
                for key in ("offered", "delivered"):
                    self.assertEqual(replace(a[key], tag=None) if a[key] else None, b[key])
                self.assertEqual(enabled.state, disabled.state)
                if previous_stall:
                    self.assertEqual(a["offered"], previous_stall)
                previous_stall = a["offered"] if a["offered"] and not ready else None
                if a["consumed"]:
                    issued.popleft()
                if a["accepted"]:
                    issued.append(step)
                    if step.emit:
                        expected.append((step.tag, step.token))
                    next_token += 1
                if a["delivered"]:
                    observed.append((a["delivered"].tag, a["delivered"].token))
                    self.assertEqual(observed, expected[:len(observed)])
                if a["done_valid"]:
                    self.assertEqual(observed, expected)
                    self.assertEqual(next_token, 200)
                    break
            else:
                self.fail("random contract scenario did not finish")


if __name__ == "__main__":
    unittest.main(verbosity=2)
