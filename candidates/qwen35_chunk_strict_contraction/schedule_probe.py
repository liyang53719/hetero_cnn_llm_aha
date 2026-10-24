"""Test-only synchronous access/identity oracle, not a hardware scheduler.

The expected addresses below are derived independently from row-major geometry,
not from Matrix.address or a trace emitted by the contraction itself. The probe
watches actual memory callbacks and the actual lists supplied to observe.
"""
import numpy as np


class ScheduleProbe:
    def __init__(self, case, owner, memory, matrices, a_words, kt_words):
        self.case, self.owner, self.memory = case, owner, memory
        self.banks, self.panels = tuple(owner._banks), tuple(owner._panels)
        self.a_words, self.kt_words = a_words, kt_words
        a, kt, pair, destination = matrices
        self.expected = []
        for start in range(0, 128, 16):
            self.expected.extend(('read', a.base + 4*(r*128+start)) for r in range(64))
            self.expected.extend(('read', kt.base + 4*(k*64+c))
                                 for k in range(start, start+16) for c in range(0, 64, 16))
            self.expected.extend((stage, k) for k in range(start, start+16)
                                 for stage in ('mul', 'add'))
        for row in range(64):
            for col in range(0, 64, 16):
                offset = row*64+col
                self.expected.extend((('read', pair.base+4*offset), ('pair', offset),
                                      ('write', destination.base+4*offset)))
        self.position = self.reads = self.writes = 0

    def _step(self, event):
        self.case.assertTrue(self.owner._busy)
        for actual, original in zip(self.owner._banks+self.owner._panels,
                                    self.banks+self.panels):
            self.case.assertIs(actual, original)
        self.case.assertEqual(tuple(map(len, self.owner._banks)), (4096, 4096))
        self.case.assertEqual(tuple(map(len, self.owner._panels)), (1024, 1024))
        self.case.assertLess(self.position, len(self.expected))
        self.case.assertEqual(event, self.expected[self.position], 'synchronous schedule mismatch')
        self.position += 1

    def read(self, address):
        self._step(('read', address))
        self.case.assertEqual(self.owner.counts['read_beats'], self.reads)
        if self.reads == 0:
            self.case.assertTrue(all(word == 0 for word in self.banks[0]))
        result = self.memory.read(address)
        self.reads += 1
        return result

    def write(self, address, values):
        self._step(('write', address))
        self.case.assertEqual(self.owner.counts['write_beats'], self.writes)
        self.memory.write(address, values)
        self.writes += 1

    def observe(self, stage, k, values, flags):
        self._step((stage, k))
        if stage in ('mul', 'add'):
            # Both passes overwrite the same product bank. The other bank is
            # the previous accumulator until the complete Add plane passes.
            self.case.assertIs(values, self.banks[1-k % 2])
            if stage == 'mul' and k % 16 == 0:
                np.testing.assert_array_equal(np.asarray(self.panels[0], np.uint32),
                                              self.a_words[:, k:k+16].reshape(-1))
                np.testing.assert_array_equal(np.asarray(self.panels[1], np.uint32),
                                              self.kt_words[k:k+16, :].reshape(-1))

    def finish(self):
        self.case.assertEqual(self.position, len(self.expected))
        self.case.assertEqual((self.reads, self.writes), (1280, 256))
        self.case.assertFalse(self.owner._busy)
