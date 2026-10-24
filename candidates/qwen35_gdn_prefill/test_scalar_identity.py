"""Bounded scalar integrity tests, not full-block or numerical acceptance.

The first class uses bare scalar objects and NO scalar arithmetic/native load.
The second uses actual tiny PrepScalar/DecayScalar arithmetic, no owner, native
Vector/Matrix, checkpoint or transport. Coordinator tests live separately in
test_full_driver and explicitly use mocked numerical transports.
"""
from collections import Counter
from contextlib import contextmanager
from types import MethodType
import unittest
from unittest.mock import patch

from . import scalar_identity as s


@contextmanager
def replaced_function_attribute(function, name, changed):
    # Function descriptors are not in __dict__. mock.patch cleanup may attempt
    # delattr(__code__), which is forbidden and would leak a mutated function.
    original = getattr(function, name)
    setattr(function, name, changed)
    try:
        yield
    finally:
        setattr(function, name, original)


def bare(cls=s.prep.PrepScalar):
    scalar = object.__new__(cls)
    scalar.client, scalar.enable_softplus = None, True
    scalar.calls, scalar.internal_calls, scalar.soft_internal_calls = (Counter() for _ in range(3))
    if cls is s.decay.DecayScalar:
        scalar.enable_ieee_exp = True
        scalar.decay_internal_calls = Counter()
    return scalar


class ScalarBindingColdTests(unittest.TestCase):
    def rejected(self, scalar, guard=None):
        with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
            (s.ScalarIdentityGuard(scalar) if guard is None else guard.check(scalar))

    def test_instance_override_rejected_before_and_after_admission(self):
        for cls in (s.prep.PrepScalar, s.decay.DecayScalar):
            scalar = bare(cls)
            guard = s.ScalarIdentityGuard(scalar)
            for name in guard.report(scalar)['guarded_methods']:
                with self.subTest(cls=cls.__name__, method=name):
                    with patch.object(scalar, name, lambda *args: 0):
                        self.rejected(scalar)
                        self.rejected(scalar, guard)
                    # Even assigning the original bound method shadows dispatch.
                    with patch.object(scalar, name, MethodType(getattr(cls, name), scalar)):
                        self.rejected(scalar, guard)
            guard.check(scalar)

    def test_every_defining_method_and_inherited_op_is_frozen(self):
        for cls, names in zip(s._CLASSES, s._METHODS):
            scalar = bare(s.decay.DecayScalar)
            guard = s.ScalarIdentityGuard(scalar)
            for name in names:
                with self.subTest(cls=cls.__name__, method=name):
                    with patch.object(cls, name, lambda *args: 0):
                        self.rejected(scalar)
                        self.rejected(scalar, guard)

    def test_same_function_code_defaults_and_super_closure_are_frozen(self):
        scalar = bare(s.decay.DecayScalar)
        guard = s.ScalarIdentityGuard(scalar)
        for fn in (s.rms.SharedScalar.op, s.conv.ConvScalar.op, s.prep.PrepScalar.op,
                   s.decay.DecayScalar.op, s.decay.DecayScalar._evaluate_exp):
            with self.subTest(function=fn.__qualname__):
                # Code retains the required free-variable count for super().
                with replaced_function_attribute(fn, '__code__', fn.__code__.replace(co_name='mutated')):
                    self.rejected(scalar)
                    self.rejected(scalar, guard)
                guard.check(scalar)
                with replaced_function_attribute(fn, '__defaults__', (1,)):
                    self.rejected(scalar, guard)
                guard.check(scalar)
                with replaced_function_attribute(fn, '__kwdefaults__', {'unexpected': 1}):
                    self.rejected(scalar, guard)
                guard.check(scalar)
        cell = s.prep.PrepScalar.op.__closure__[0]
        old = cell.cell_contents
        try:
            cell.cell_contents = s.conv.ConvScalar
            self.rejected(scalar, guard)
        finally:
            cell.cell_contents = old
        guard.check(scalar)

    def test_module_local_numeric_helpers_constants_and_aliases_are_frozen(self):
        scalar = bare(s.decay.DecayScalar)
        guard = s.ScalarIdentityGuard(scalar)
        for pins in s._MODULE_PINS:
            for pin in pins:
                with self.subTest(module=pin.owner.__name__, binding=pin.name):
                    with patch.object(pin.owner, pin.name, object()):
                        self.rejected(scalar)
                        self.rejected(scalar, guard)
        for pin in (*s._NUMPY_PINS, *s._STRUCT_PINS, s._DECAY_NUMPY_PIN):
            with self.subTest(binding=pin.name):
                with patch.object(pin.owner, pin.name, object()):
                    self.rejected(scalar, guard)

    def test_helper_function_code_cannot_change_behind_same_alias(self):
        scalar = bare()
        guard = s.ScalarIdentityGuard(scalar)
        for fn in (s.rms.word, s.rms.value, s.rms.finite, s.rms._tiny_inexact, s.rms.require):
            with replaced_function_attribute(fn, '__code__', fn.__code__.replace(co_name='changed')):
                self.rejected(scalar)
                self.rejected(scalar, guard)
            guard.check(scalar)

    def test_exact_types_and_literal_enable_flags_are_frozen(self):
        class Subclass(s.prep.PrepScalar):
            pass
        self.rejected(bare(Subclass))
        for cls in (s.prep.PrepScalar, s.decay.DecayScalar):
            scalar = bare(cls)
            guard = s.ScalarIdentityGuard(scalar)
            self.rejected(bare(cls), guard)
            names = ('enable_softplus', 'enable_ieee_exp') if cls is s.decay.DecayScalar else ('enable_softplus',)
            for name in names:
                for changed in (False, 1, None):
                    with patch.object(scalar, name, changed):
                        self.rejected(scalar, guard)
                        if changed is not False:
                            self.rejected(scalar)

    def test_mro_resolution_and_class_alias_rebinding_are_rejected(self):
        scalar = bare()
        guard = s.ScalarIdentityGuard(scalar)
        with patch.object(s.prep.PrepScalar, '__getattribute__', object.__getattribute__, create=True):
            self.rejected(scalar, guard)
        old = s.prep.PrepScalar.__bases__
        try:
            s.prep.PrepScalar.__bases__ = (s.rms.SharedScalar,)
            self.rejected(scalar, guard)
        finally:
            s.prep.PrepScalar.__bases__ = old
        guard.check(scalar)

    def test_counters_and_lease_state_are_not_identity(self):
        scalar = bare()
        guard = s.ScalarIdentityGuard(scalar)
        before = guard.check(scalar)
        client = object()
        self.assertTrue(scalar.acquire(client))
        scalar.calls['softplus'] += 2
        scalar.internal_calls['mul'] += 7
        scalar.soft_internal_calls['add'] += 9
        self.assertEqual(guard.check(scalar), before)
        scalar.release(client)
        self.assertEqual(guard.check(scalar), before)
        report = guard.report(scalar)
        self.assertEqual(report['implementation'], 'PrepScalar')
        self.assertIsNone(report['enable_ieee_exp'])
        self.assertIsNone(report['numerical_acceptance'])
        self.assertTrue(report['boundary_integrity_only'])

    def test_legacy_exp_dispatch_is_import_anchored(self):
        before = s.legacy_exp_routing_identity(s.exp_policy)
        for pin in s._ROUTE_PINS:
            with patch.object(pin.owner, pin.name, object()):
                with self.assertRaisesRegex(ValueError, 'Scalar arithmetic binding changed'):
                    s.legacy_exp_routing_identity(s.exp_policy)
        self.assertEqual(s.legacy_exp_routing_identity(s.exp_policy), before)


class ScalarBindingActualArithmeticTests(unittest.TestCase):
    def test_actual_prep_scalar_unchanged_small_raw_word_operations(self):
        scalar = s.prep.PrepScalar(enable_softplus=True)
        guard = s.ScalarIdentityGuard(scalar)
        client = object()
        self.assertTrue(scalar.acquire(client))
        for operation, a, b, expected in (
                ('add', 0x3f800000, 0x3f800000, 0x40000000),
                ('mul', 0x3f800000, 0x40000000, 0x40000000),
                ('mul_ieee_rne', 0x00800000, 0x3f000000, 0x00400000),
                ('div', 0x40000000, 0x40000000, 0x3f800000),
                ('sqrt', 0x40800000, 0, 0x40000000),
                ('exp_negative', 0, 0, 0x3f800000),
                ('exp_negative', 0xc2a00000, 0, 0),
                ('softplus', 0x41a80000, 0, 0x41a80000)):
            self.assertEqual(scalar.op(client, operation, a, b), expected)
            guard.check(scalar)
        scalar.release(client)
        guard.check(scalar)
        self.assertEqual(sum(scalar.calls.values()), 8)

    def test_actual_decay_evaluator_uses_original_five_word_diagnostic(self):
        scalar = s.decay.DecayScalar(enable_softplus=True, enable_ieee_exp=True)
        guard = s.ScalarIdentityGuard(scalar)
        client = object()
        self.assertTrue(scalar.acquire(client))
        # Recorded raw-word diagnostic regression, NOT a newly assigned accuracy tolerance.
        for raw, expected in ((0xc2a00000, 0x05bfecba), (0xc2aeac50, 0x007fffe6),
                              (0xc2b72752, 0x0001d7fd), (0xc2cff1b4, 1), (0xc2cff1b5, 0)):
            self.assertEqual(scalar.op(client, s.decay.OPERATION, raw), expected)
            guard.check(scalar)
        scalar.release(client)
        guard.check(scalar)
        self.assertEqual(scalar.calls[s.decay.OPERATION], 5)
        self.assertEqual(scalar.decay_internal_calls, Counter(mul=63, add=45, integer_rne=5))


if __name__ == '__main__':
    unittest.main()
