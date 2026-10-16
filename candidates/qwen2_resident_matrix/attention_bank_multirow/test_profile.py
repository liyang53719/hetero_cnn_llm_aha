"""Short, cold tests: no M4+ execution, native library or RTL run."""
import ast
import gc
import hashlib
import struct
import unittest
import weakref
from types import SimpleNamespace

from . import profile
from ..attention_bank_scratch.controller import Controller as Frozen, Timing
from ..attention_matrix_batch.test_model import ExactScalar, fixture, ref_fma, exp_negative


class ProfileTests(unittest.TestCase):
    def make(self, cls):
        scalar = ExactScalar(object())
        return cls(scalar, ref_fma, lambda a: exp_negative(scalar, scalar.client, a),
                   timing=Timing(2, 3, 1, 2), scratch_enabled=True, bank_stalls=1)

    def test_source_pin_and_only_bound_changed(self):
        source = profile.SOURCE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), profile.SOURCE_SHA256)
        tree = ast.parse(source)
        original = next(n for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'Controller'
                        for n in c.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        changed = profile.transform_run(source)
        calls = [n for n in ast.walk(changed) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'integer']
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args[2].value, 16)
        calls[0].args[2].value = 2
        self.assertEqual(ast.dump(changed), ast.dump(original))
        for bad in (source+b'\n', source.replace(b'integer(tokens, 1, 2)', b'integer(tokens, 1, 16)'),
                    source.replace(b'self.tmp = [0]*16', b'self.tmp = [0]*128'),
                    source.replace(b'integer(tokens, 1, 2)', b'integer(tokens, 1, 2); integer(tokens, 1, 2)')):
            with self.subTest(change=hashlib.sha256(bad).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    profile.build_run(bad)

    def test_shapes_reject_before_compute(self):
        for n in (1, 2, 4, 8, 16):
            profile.admit(n)
        for n in (0, 3, 5, 15, 17, 128, True, 1.0, '2', None):
            c = self.make(profile.Controller)
            with self.subTest(tokens=n), self.assertRaisesRegex(ValueError, 'admitted shapes'):
                c.run(n, (), (), ())
            self.assertEqual(c.ticks, 0)
            self.assertFalse(c.active)
            self.assertEqual(c.scratch.events.count, 0)

    def test_m1_m2_same_scores_outputs_counts_ticks_and_observations(self):
        for n in (1, 2):
            with self.subTest(tokens=n):
                old, new = self.make(Frozen), self.make(profile.Controller)
                data = fixture(n)
                expected, actual = old.run(n, *data), new.run(n, *data)
                self.assertEqual(actual.output, expected.output)
                self.assertEqual(actual.scores, expected.scores)
                self.assertEqual(actual.counts, expected.counts)
                self.assertEqual(actual.hypothetical_ticks, expected.hypothetical_ticks)
                self.assertIs(new.scratch.banks, new.scratch.parent.owner.a_banks)
                self.assertIs(new.scratch.banks, new.scratch.parent.raw.banks)
                for name in ('read_events', 'ack_events', 'views', 'scratch.events'):
                    objects = old.scratch.events if name == 'scratch.events' else getattr(old, name)
                    reference = profile.EventSink(name)
                    for event in objects:
                        reference.append(event)
                    self.assertEqual(new.observation_summary()[name], reference.summary())
                self.assertTrue(new.ordinary_owner_ready())
                self.assertIsNone(new.slot)
                self.assertIs(profile.Controller.matrix_group, Frozen.matrix_group)
                self.assertIs(profile.Controller.scalar_phase, Frozen.scalar_phase)

    def test_sink_hash_schema_order_and_bounded_retention(self):
        events = ((1, 2, 3), (4, 5, 6))
        sink = profile.EventSink('read_events')
        digest = hashlib.sha256((profile.SCHEMA+'\0read_events\0').encode('ascii'))
        for event in events:
            sink.append(event)
            digest.update(struct.pack('>QQQ', *event))
        self.assertEqual(sink.hexdigest(), digest.hexdigest())
        self.assertEqual(len(sink), 2)
        reversed_sink = profile.EventSink('read_events')
        for event in reversed(events):
            reversed_sink.append(event)
        self.assertNotEqual(sink.hexdigest(), reversed_sink.hexdigest())
        for _ in range(10000):
            sink.append(events[0])
        self.assertEqual(sink.count, 10002)
        self.assertEqual(sink.summary()['retained_events'], 0)
        self.assertFalse(hasattr(sink, '__dict__'))
        self.assertEqual(profile.EventSink.__slots__, ('kind', 'count', '_hash'))
        before = sink.summary()
        with self.assertRaises(ValueError):
            sink.append((True, 2, 3))
        self.assertEqual(sink.summary(), before)

    def test_views_keep_no_controller_or_view_reference(self):
        class Owner:
            pass
        owner = Owner()
        owner_ref = weakref.ref(owner)
        view = SimpleNamespace(controller=owner, group=7)
        sink = profile.EventSink('views')
        sink.append(view)
        same_group = profile.EventSink('views')
        same_group.append(SimpleNamespace(group=7))
        self.assertEqual(sink.summary(), same_group.summary())
        del owner, view
        gc.collect()
        self.assertIsNone(owner_ref())

    def test_scratch_schema_rejects_unbounded_or_unsorted_records(self):
        sink = profile.EventSink('scratch.events')
        sink.append((1, ((0, 12), (1, 13)), (), True, False))
        before = sink.summary()
        for event in ((2, tuple((n, 0) for n in range(17)), (), False, False),
                      (2, ((1, 0), (0, 0)), (), False, False),
                      (2, (), (), 1, False)):
            with self.assertRaises(ValueError):
                sink.append(event)
            self.assertEqual(sink.summary(), before)


if __name__ == '__main__':
    unittest.main()
