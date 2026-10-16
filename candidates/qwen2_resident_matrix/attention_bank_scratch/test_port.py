"""Bounded bank-port checks using the existing physical Banks allocation."""
import unittest
from unittest.mock import call, patch

from candidates.qwen2_resident_matrix.transposed_down.model import Banks
from candidates.qwen2_resident_matrix.raw_kv.model import location as original_location
from candidates.qwen2_resident_matrix.attention_bank_scratch.port import (
    Key, RawKvPort, Request, location, valid_key,
)


class ScratchPortTests(unittest.TestCase):
    def setUp(self):
        self.banks = Banks(1376)
        self.p = RawKvPort(self.banks, enabled=True, scratch_enabled=True)
        self.read = self.enterContext(patch.object(self.banks, 'read', wraps=self.banks.read))
        self.write = self.enterContext(patch.object(self.banks, 'write', wraps=self.banks.write))
        self.assertTrue(self.edge(acquire=7)['acquired'])

    def edge(self, **kwargs):
        """Count calls as well as bank maps, including under python -O."""
        self.read.reset_mock(); self.write.reset_mock()
        out = self.p.tick(**kwargs)
        if out['accepted']:
            req = kwargs['request']
            lo, hi, word = location(req.key.line, scratch_enabled=self.p.scratch_enabled)
            self.assertNotEqual(lo, hi)
            if req.key.write:
                self.assertEqual(self.write.call_args_list, [
                    call(lo, word, req.data & ((1 << 256) - 1)),
                    call(hi, word, req.data >> 256),
                ])
                self.assertEqual(self.read.call_count, 0)
                self.assertEqual(self.banks.writes, {lo: word, hi: word})
                self.assertEqual(self.banks.reads, {})
            else:
                self.assertEqual(self.read.call_args_list, [call(lo, word), call(hi, word)])
                self.assertEqual(self.write.call_count, 0)
                self.assertEqual(self.banks.reads, {lo: word, hi: word})
                self.assertEqual(self.banks.writes, {})
        else:
            self.assertEqual((self.read.call_count, self.write.call_count), (0, 0))
            self.assertEqual((self.banks.reads, self.banks.writes), ({}, {}))
        return out

    def transact(self, line, write, data=0, tag=1):
        key = Key(7, tag, line, write)
        out = self.edge(request=Request(key, data), ack=key)
        self.assertTrue(out['accepted']); self.assertFalse(out['acked'])
        self.assertIsNone(out['response']); self.assertIsNone(self.p.response)
        out = self.edge(ack=key)
        self.assertFalse(out['acked']); self.assertIsNone(out['response'])
        response = self.p.response
        self.assertEqual(response.key, key)
        out = self.edge(ack=key)
        self.assertTrue(out['acked']); self.assertEqual(out['response'], response)
        self.assertTrue(self.p.drained)
        return response.data

    def test_all_96_scratch_lines_preserve_raw_bits_and_one_allocation(self):
        words = self.banks.words
        rows = tuple(words)
        # FP32 +/-Inf, NaN payload and negative zero remain uninterpreted bits.
        raw = int.from_bytes(bytes.fromhex('0000807f000080ff0100c07f00000080') * 4, 'little')
        cells = set()
        for line in range(4096, 4192):
            lo, hi, word = location(line, scratch_enabled=True)
            self.assertTrue(512 <= word <= 523)
            self.assertTrue(cells.isdisjoint({(lo, word), (hi, word)}))
            cells.update(((lo, word), (hi, word)))
            self.assertEqual(self.transact(line, True, raw ^ line, line), 0)
        for line in range(4096, 4192):
            self.assertEqual(self.transact(line, False, tag=line), raw ^ line)
        self.assertEqual(len(cells), 192)
        self.assertIs(self.p.banks, self.banks); self.assertIs(self.banks.words, words)
        for before, after in zip(rows, self.banks.words):
            self.assertIs(before, after)
            self.assertTrue(all(value == 0 for value in after[:512] + after[524:]))

    def test_boundaries_and_default_address_profile(self):
        for line, expected in ((4095, (14, 15, 511)), (4096, (0, 1, 512)),
                               (4191, (14, 15, 523))):
            self.assertEqual(location(line, scratch_enabled=True), expected)
            self.assertTrue(valid_key(Key(7, 1, line, False), scratch_enabled=True))
            self.transact(line, True, (1 << 511) | line)
            self.assertEqual(self.transact(line, False), (1 << 511) | line)
        for line in (4192, -1, 8192, True, 4096.0):
            with self.assertRaises(ValueError): location(line, scratch_enabled=True)
            key = Key(7, 1, line, False)
            self.assertFalse(valid_key(key, scratch_enabled=True))
            self.assertFalse(self.edge(request=Request(key))['accepted'])
        for line in range(4096):
            self.assertEqual(location(line), original_location(line))
        for line in (4096, 4191, 4192):
            with self.assertRaises(ValueError): location(line)
            self.assertFalse(valid_key(Key(7, 1, line, False)))
        self.p = RawKvPort(self.banks, enabled=True)
        self.assertTrue(self.edge(acquire=7)['acquired'])
        self.transact(4095, True, 123)
        for line in (4096, 4191, 4192):
            self.assertFalse(self.edge(request=Request(Key(7, 1, line, False)))['accepted'])

    def test_port_defaults_off_even_when_scratch_profile_selected(self):
        for kwargs in ({}, {'scratch_enabled': True}):
            self.p = RawKvPort(self.banks, **kwargs)
            for offer in ({'acquire': 7}, {'request': Request(Key(7, 1, 4095, True), 99)},
                          {'request': Request(Key(7, 2, 4096, True), 99)}):
                out = self.edge(**offer)
                self.assertFalse(out['accepted'] or out['acquired'])
                self.assertTrue(out['dense_allowed'] and out['tile_allowed'] and out['clear_allowed'])
                self.assertTrue(self.p.drained); self.assertIsNone(self.p.owner)
        self.assertTrue(all(value == 0 for row in self.banks.words for value in row))

    def test_held_response_rejects_malformed_ack_and_early_release(self):
        self.transact(4096, True, (1 << 511) | 0x1234)
        key = Key(7, 1, 4096, False)
        self.assertTrue(self.edge(request=Request(key))['accepted'])
        self.assertFalse(self.edge(release=7, ack=key)['released'])
        held = self.p.response
        self.assertEqual(held.data, (1 << 511) | 0x1234)
        malformed = [Key(7.0, 1, 4096, False), Key(7, True, 4096, False),
                     Key(7, 1.0, 4096, False), Key(7, 1, 4096.0, False),
                     Key(7, 1, 4096, 0), Key(7, 1, 4096, 0.0),
                     Key(True, 1, 4096, False), Key(7, 1, True, False),
                     Key(8, 1, 4096, False), Key(7, 2, 4096, False),
                     Key(7, 1, 4191, False), Key(7, 1, 4096, True), None]
        for ack in malformed:
            out = self.edge(ack=ack, release=7, request=Request(Key(7, 2, 4191, False)),
                            dense=True, tile=True, clear=True)
            self.assertFalse(out['acked'] or out['released'] or out['accepted'])
            self.assertFalse(out['dense_allowed'] or out['tile_allowed'] or out['clear_allowed'])
            self.assertIs(self.p.response, held); self.assertEqual(out['response'], held)
        out = self.edge(ack=key, release=7)
        self.assertTrue(out['acked']); self.assertFalse(out['released'])
        self.assertTrue(self.edge(release=7)['released'])

    def test_abort_and_ack_drain_without_publishing_fill(self):
        key = Key(7, 1, 4191, True)
        valid = set()
        self.assertTrue(self.edge(request=Request(key, 99))['accepted'])
        self.edge(); self.assertFalse(valid)
        out = self.edge(ack=key, abort=True, release=7)
        if out['acked'] and not self.p.poison:
            valid.add(key.line)
        self.assertTrue(out['acked']); self.assertTrue(self.p.poison)
        self.assertFalse(valid); self.assertFalse(out['released'])
        self.assertTrue(self.p.drained)
        self.assertTrue(self.edge(release=7)['released'])
        self.assertFalse(self.edge(acquire=8)['acquired'])


if __name__ == '__main__':
    unittest.main()
