"""Memory-only differential tests; no Matrix, owner arithmetic, build, or RTL.

The reference resolver is the exact pre-hoist implementation from b74aa569.
All writes below use synthetic transport words, not model numerical results.
"""
from dataclasses import replace
import random
import unittest

from . import typed_dense as t


class LegacyTypedMemory(t.TypedMemory):
    def _resolve(self, address, size=64):
        t.require(type(address) is int and address % 64 == 0 and size > 0 and size % 64 == 0,
                  'physical access alignment')
        matches = [r for r in self.regions.values() if r.base <= address and address + size <= r.base + r.extent]
        t.require(len(matches) == 1, 'physical access outside one allocation')
        return matches[0]


def outcome(memory, address, size=64):
    try:
        return ('region', memory._resolve(address, size))
    except Exception as error:
        return ('error', type(error), str(error))


def snapshot(memory):
    pending = None if memory.pending is None else tuple(memory.pending)
    return (pending, tuple((key, id(region), region.base, region.extent,
                            bytes(region.storage), region.readonly, region.published,
                            frozenset(region.written), frozenset(region.acknowledged))
                           for key, region in memory.regions.items()))


class TypedMemoryLookupTests(unittest.TestCase):
    def assert_same(self, memory, address, size=64):
        legacy = LegacyTypedMemory()
        legacy.regions = memory.regions
        expected = outcome(legacy, address, size)
        actual = outcome(memory, address, size)
        if expected[0] == 'region':
            self.assertEqual(actual[0], 'region')
            self.assertIs(actual[1], expected[1])
        else:
            self.assertEqual(actual, expected)
        return actual

    def reject_without_change(self, memory, message, action):
        before = snapshot(memory)
        with self.assertRaisesRegex(ValueError, message):
            action()
        self.assertEqual(snapshot(memory), before)

    def test_57_regions_shuffled_boundaries_gaps_and_whole_spans(self):
        memory = t.TypedMemory()
        spans = [(0x1000 + i * 512, (1 + i % 4) * 64) for i in range(57)]
        random.Random(913).shuffle(spans)
        for base, extent in spans:
            memory.allocate_output(base, extent)
        self.assertEqual(type(memory.regions), dict)
        for base, extent in spans:
            for address, size in ((base, 64), (base + extent - 64, 64),
                                  (base, extent), (base - 64, 64),
                                  (base + extent, 64), (base, extent + 64)):
                with self.subTest(address=address, size=size):
                    self.assert_same(memory, address, size)

    def test_adjacent_allocations_are_not_one_span(self):
        memory = t.TypedMemory()
        first = memory.allocate_output(0x1000, 128)
        second = memory.allocate_output(0x1080, 128)
        self.assertIs(self.assert_same(memory, 0x1040)[1], first)
        self.assertIs(self.assert_same(memory, 0x1080)[1], second)
        self.assertEqual(self.assert_same(memory, 0x1040, 128)[0], 'error')
        self.assertEqual(self.assert_same(memory, 0x1000, 256)[0], 'error')

    def test_alignment_types_negative_and_upper_boundary(self):
        memory = t.TypedMemory()
        memory.allocate_output(0, 64)
        memory.allocate_output((1 << 56) - 64, 64)
        queries = [(True, 64), (False, 64), (0.0, 64), ('0', 64), (1, 64),
                   (-64, 64), (0, 0), (0, -64), (0, 1), (0, True),
                   (0, None), (0, '64'), (0, 64.0), (0, 128.0),
                   (0, float('nan')), (0, float('inf')),
                   ((1 << 56) - 64, 64), ((1 << 56) - 64, 128), (1 << 56, 64)]
        for address, size in queries:
            with self.subTest(address=address, size=size):
                self.assert_same(memory, address, size)
        self.assertIs(self.assert_same(memory, 0, 64.0)[1], memory.regions[0])

    def test_nonexact_int_size_preserves_per_region_addition_and_short_circuit(self):
        class Size(int):
            def __radd__(self, other):
                calls.append(other)
                return other + int(self)

        memory = t.TypedMemory()
        for base in (0, 64, 128, 192):
            memory.allocate_output(base, 64)
        calls = []
        for kind in (LegacyTypedMemory, t.TypedMemory):
            candidate = kind()
            candidate.regions = memory.regions
            calls.clear()
            self.assertIs(candidate._resolve(128, Size(64)), memory.regions[128])
            self.assertEqual(calls, [128, 128, 128])
            calls.clear()
            candidate.regions = {}
            self.assertEqual(outcome(candidate, 128, Size(64))[0], 'error')
            self.assertEqual(calls, [])

    def test_same_count_replacement_deletion_map_replacement_and_restoration(self):
        memory = t.TypedMemory()
        original = memory.allocate_output(0x1000, 128)
        other = memory.allocate_output(0x2000, 128)
        self.assertIs(self.assert_same(memory, 0x1000)[1], original)
        replacement = replace(original)
        memory.regions[0x1000] = replacement
        self.assertIs(self.assert_same(memory, 0x1000)[1], replacement)
        del memory.regions[0x1000]
        memory.regions[0x3000] = replace(other, base=0x3000)
        self.assertEqual(self.assert_same(memory, 0x1000)[0], 'error')
        memory.regions = {0x1000: original, 0x2000: other}
        self.assertIs(self.assert_same(memory, 0x1000)[1], original)
        memory.regions = dict(memory.regions)
        self.assertIs(self.assert_same(memory, 0x1000)[1], original)

    def test_alias_under_other_key_and_duplicate_object_are_counted(self):
        for same_object in (False, True):
            memory = t.TypedMemory()
            original = memory.allocate_output(0x1000, 128)
            self.assert_same(memory, 0x1000)
            memory.regions[0x9000] = original if same_object else replace(original)
            self.assertEqual(self.assert_same(memory, 0x1000)[0], 'error')
            del memory.regions[0x9000]
            self.assertIs(self.assert_same(memory, 0x1000)[1], original)

    def test_selected_geometry_mutation_and_restoration(self):
        memory = t.TypedMemory()
        region = memory.allocate_output(0x1000, 128)
        self.assert_same(memory, 0x1040)
        for base, extent in ((0x1040, 128), (0x1000, 64), (0x1000, 192),
                             (-64, 128), (0x1000, 0), (0x1000, -64)):
            region.base, region.extent = base, extent
            for address in (-64, 0, 0x1000, 0x1040, 0x1080):
                self.assert_same(memory, address)
        region.base, region.extent = 0x1000, 128
        self.assertIs(self.assert_same(memory, 0x1040)[1], region)

    def test_unrelated_region_can_move_or_grow_over_warmed_target(self):
        for field, value in (('base', 0x1000), ('extent', 0x2000)):
            memory = t.TypedMemory()
            target = memory.allocate_output(0x1000, 128)
            other = memory.allocate_output(0, 128)
            self.assertIs(self.assert_same(memory, 0x1000)[1], target)
            setattr(other, field, value)
            self.assertEqual(self.assert_same(memory, 0x1000)[0], 'error')

    def test_partial_overlap_is_not_blanket_rejected(self):
        memory = t.TypedMemory()
        target = memory.allocate_output(0x1000, 256)
        partial = memory.allocate_output(0x2000, 64)
        partial.base = 0x1040
        self.assertIs(self.assert_same(memory, 0x1000, 256)[1], target)
        self.assertEqual(self.assert_same(memory, 0x1040, 64)[0], 'error')

    def test_alignment_error_precedes_alias_or_malformed_regions(self):
        memory = t.TypedMemory()
        region = memory.allocate_output(0x1000, 64)
        memory.regions[0x2000] = replace(region)
        memory.regions[0x3000] = object()
        self.assertEqual(self.assert_same(memory, 0x1001),
                         ('error', ValueError, 'typed Dense: physical access alignment'))

    def test_full_scan_has_no_early_exit_after_one_or_multiple_matches(self):
        for count in (1, 2, 3):
            memory = t.TypedMemory()
            region = memory.allocate_output(0x1000, 64)
            for i in range(count - 1):
                memory.regions[0x2000 + 64 * i] = replace(region)
            memory.regions[0x3000] = object()
            result = self.assert_same(memory, 0x1000)
            self.assertEqual(result[1], AttributeError)

    def test_later_extent_is_not_read_when_lower_bound_fails(self):
        class Future:
            base = 0x2000
            @property
            def extent(self):
                raise RuntimeError('extent should not be accessed')

        memory = t.TypedMemory()
        region = memory.allocate_output(0x1000, 64)
        memory.regions[0x2000] = Future()
        self.assertIs(self.assert_same(memory, 0x1000)[1], region)

    def test_failed_resolve_is_readonly(self):
        memory = t.TypedMemory()
        memory.allocate_output(0x1000, 128)
        for address, size in ((1, 64), (0, 64), (0x1040, 128)):
            before = snapshot(memory)
            self.assertEqual(self.assert_same(memory, address, size)[0], 'error')
            self.assertEqual(snapshot(memory), before)

    def test_read_publication_failure_precedes_guard_failure(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            memory = kind()
            region = memory.allocate_output(0x1000, 64)
            region.storage[0] ^= 1
            self.reject_without_change(memory, 'read before producer terminal',
                                       lambda: memory.read64(0x1000))
            region.published = True
            self.reject_without_change(memory, 'physical region guard changed',
                                       lambda: memory.read64(0x1000))

    def test_descriptor_error_precedence_and_no_mutation(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            memory = kind()
            region = memory.allocate_output(0x1000, 128)
            self.reject_without_change(memory, 'overlapping or invalid write descriptor',
                                       lambda: memory.begin_write(t.down.WriteCommand(960, 17, 7)))
            self.reject_without_change(memory, 'write crosses original 1KiB boundary',
                                       lambda: memory.begin_write(t.down.WriteCommand(960, 2, 7)))
            self.reject_without_change(memory, 'physical access alignment',
                                       lambda: memory.begin_write(t.down.WriteCommand(0x1001, 1, 7)))
            region.written.add(0)
            for attribute in ('readonly', 'published'):
                setattr(region, attribute, True)
                self.reject_without_change(memory, 'write to readonly/published allocation',
                                           lambda: memory.begin_write(t.down.WriteCommand(0x1000, 1, 7)))
                setattr(region, attribute, False)
            self.reject_without_change(memory, 'duplicate physical write',
                                       lambda: memory.begin_write(t.down.WriteCommand(0x1000, 1, 7)))
            region.written.clear()
            memory.begin_write(t.down.WriteCommand(0x1000, 1, 7))
            self.reject_without_change(memory, 'overlapping or invalid write descriptor',
                                       lambda: memory.begin_write(t.down.WriteCommand(960, 2, 8)))

    def test_ack_failure_and_publication_fences(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            memory = kind()
            region = memory.allocate_output(0x1000, 128)
            memory.begin_write(t.down.WriteCommand(0x1000, 2, 7))
            memory.write_data((1,) * 32, False)
            self.reject_without_change(memory, 'ACK before final data beat',
                                       lambda: memory.acknowledge(t.down.WriteAck(7, False, 128)))
            memory.write_data((2,) * 32, True)
            self.reject_without_change(memory, 'write ACK identity/explicit byte count',
                                       lambda: memory.acknowledge(t.down.WriteAck(7, False, 64)))
            self.reject_without_change(memory, 'publication before successful owner terminal',
                                       lambda: memory.publish(0x1000, (7, None, 128)))
            memory.acknowledge(t.down.WriteAck(7, True, 128))
            self.assertEqual(region.acknowledged, set())
            self.reject_without_change(memory, 'incomplete actual data/ACK coverage',
                                       lambda: memory.publish(0x1000, (7, None, 128)))
            self.reject_without_change(memory, 'duplicate physical write',
                                       lambda: memory.begin_write(t.down.WriteCommand(0x1000, 1, 7)))

    def test_successful_ack_does_not_publish_until_explicit_terminal_fence(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            memory = kind()
            region = memory.allocate_output(0x1000, 64)
            memory.begin_write(t.down.WriteCommand(0x1000, 1, 7))
            memory.write_data((0,) * 32, True)
            memory.acknowledge(t.down.WriteAck(7, False, 64))
            for _ in range(3):
                self.assertFalse(region.published)
                self.reject_without_change(memory, 'read before producer terminal',
                                           lambda: memory.read64(0x1000))
            memory.publish(0x1000, (7, None, 64))
            self.assertEqual(memory.read64(0x1000), bytes(64))

    def test_publish_many_is_atomic_for_incomplete_coverage_and_corrupt_guard(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            for defect in ('ack', 'guard'):
                memory = kind()
                first = memory.allocate_output(0x1000, 64)
                second = memory.allocate_output(0x2000, 64)
                for region in (first, second):
                    memory.begin_write(t.down.WriteCommand(region.base, 1, 7))
                    memory.write_data((0,) * 32, True)
                    memory.acknowledge(t.down.WriteAck(7, False, 64))
                if defect == 'ack':
                    second.acknowledged.clear()
                    message = 'incomplete actual multi-span data/ACK coverage'
                else:
                    second.storage[0] ^= 1
                    message = 'physical region guard changed'
                self.reject_without_change(memory, message,
                    lambda: memory.publish_many((0x1000, 0x2000), (7, None, 128)))
                self.assertFalse(first.published or second.published)

    def test_add_alias_error_precedes_raw_validation_and_leaves_map_unchanged(self):
        for kind in (LegacyTypedMemory, t.TypedMemory):
            memory = kind()
            memory.allocate_output(0x1000, 128)
            self.reject_without_change(memory, 'physical allocation alias',
                                       lambda: memory._add(0x1040, 64, b'bad'))
            self.reject_without_change(memory, 'aligned nonempty physical span',
                                       lambda: memory._add(0x1001, 64, b'bad'))


if __name__ == '__main__':
    unittest.main()
