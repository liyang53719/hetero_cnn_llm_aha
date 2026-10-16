import unittest
from candidates.qwen2_resident_matrix.transposed_down.model import Banks
from candidates.qwen2_resident_matrix.raw_kv.model import RawKvPort, Key, Request, Obligations, location

class RawKvTests(unittest.TestCase):
    def setUp(self):
        self.banks = Banks(1376)
        self.p = RawKvPort(self.banks, enabled=True)
        self.assertTrue(self.p.tick(acquire=7)['acquired'])

    def transact(self, line, write, data=0, tag=1):
        k = Key(7, tag, line, write)
        self.assertTrue(self.p.tick(request=Request(k, data))['accepted'])
        self.assertIsNone(self.p.response)
        lo,hi,word=location(line)
        self.assertEqual(self.banks.writes if write else self.banks.reads,{lo:word,hi:word})
        self.assertEqual(self.banks.reads if write else self.banks.writes,{})
        self.p.tick()
        r = self.p.response
        self.assertEqual(r.key, k)
        self.assertTrue(self.p.tick(ack=k)['acked'])
        return r.data

    def test_all_4096_m128_lines_raw_bits_and_no_shadow(self):
        identity = id(self.banks.words)
        cells = set()
        # Includes +/-Inf, NaNs and signed zero, never interpreted as floats.
        raw = int.from_bytes(bytes.fromhex('0000807f000080ff0100c07f00000080') * 4, 'little')
        for line in range(4096):
            a,b,w = location(line)
            self.assertNotIn((a,w), cells); self.assertNotIn((b,w), cells)
            cells.update(((a,w),(b,w)))
            self.transact(line, True, raw ^ line)
            self.assertEqual(set(self.banks.writes), set())  # ACK edge has no access
        for line in range(4096):
            self.assertEqual(self.transact(line, False), raw ^ line)
        self.assertEqual(len(cells),8192)
        self.assertEqual(location(4095),(14,15,511))
        self.assertEqual(id(self.banks.words),identity)
        self.assertIs(self.p.banks,self.banks)
        self.assertTrue(all(v == 0 for bank in self.banks.words for v in bank[512:]))

    def test_hold_ack_fill_publication_abort_reset_and_release(self):
        key=Key(7,9,4095,True); valid=set()
        self.assertTrue(self.p.tick(request=Request(key,123))['accepted'])
        self.assertNotIn(4095,valid)
        self.assertFalse(self.p.tick(release=7,abort=True,soft_reset=True)['released'])
        held=self.p.response
        for _ in range(4):
            o=self.p.tick(request=Request(key,99),ack=Key(8,9,4095,True),release=7,dense=True,tile=True,clear=True)
            self.assertFalse(o['accepted']);self.assertFalse(o['acked'])
            self.assertFalse(o['released']);self.assertEqual(self.p.response,held)
            self.assertFalse(o['dense_allowed'] or o['tile_allowed'] or o['clear_allowed'])
            self.assertFalse(self.banks.reads or self.banks.writes)
        o=self.p.tick(ack=key,release=7)
        if o['acked'] and not self.p.poison:valid.add(key.line)
        self.assertNotIn(4095,valid);self.assertFalse(o['released'])
        self.assertTrue(self.p.tick(release=7)['released'])
        self.assertFalse(self.p.tick(acquire=8)['acquired'])
        self.p.tick(soft_reset=True)
        self.assertTrue(self.p.tick(acquire=8)['acquired'])

    def test_release_edge_and_simultaneous_offers(self):
        o=self.p.tick(release=7,dense=True,tile=True,clear=True)
        self.assertTrue(o['released'])
        self.assertFalse(o['dense_allowed'] or o['tile_allowed'] or o['clear_allowed'])
        self.assertTrue(self.p.tick()['dense_allowed'])
        self.assertFalse(self.p.tick(acquire=7,release=8)['acquired'])
        self.assertTrue(self.p.tick(acquire=7)['acquired'])

    def test_read_debt_survives_reset_and_early_ack(self):
        self.transact(8,True,0x123456)
        key=Key(7,2,8,False)
        self.p.tick(request=Request(key))
        self.assertFalse(self.p.tick(ack=key,soft_reset=True)['acked'])
        held=self.p.response;self.assertEqual(held.data,0x123456)
        self.assertFalse(self.p.tick(release=7)['released'])
        self.assertEqual(self.p.response,held)
        self.assertTrue(self.p.tick(ack=key)['acked'])
        self.assertTrue(self.p.tick(release=7)['released'])
        self.assertFalse(self.p.tick()['dense_allowed'])

    def test_clean_fill_publishes_only_after_ack(self):
        key=Key(7,1,0,True);valid=set()
        self.p.tick(request=Request(key,99));self.assertFalse(valid)
        self.p.tick();self.assertFalse(valid)
        if self.p.tick(ack=key)['acked'] and not self.p.poison:valid.add(0)
        self.assertEqual(valid,{0})

    def test_bad_keys_and_no_read_before_acceptance(self):
        for owner,tag,line,write,data in [(None,1,0,False,0),(0,1,0,False,0),(8,1,0,False,0),(True,1,0,False,0),
                (7,0,0,False,0),(7,-1,0,False,0),(7,1,4096,False,0),(7,1,-1,False,0),
                (7,1,False,False,0),(7,1,0,1,0),(7,1,0,True,1<<512)]:
            self.assertFalse(self.p.tick(request=Request(Key(owner,tag,line,write),data))['accepted'])
            self.assertFalse(self.banks.reads or self.banks.writes)
        for bad in (None,-1,4096,True,1.0):
            with self.assertRaises(ValueError):location(bad)
        self.assertFalse(self.p.tick(request=Request(Key(7,1,0,False)),abort=True)['accepted'])

    def test_acquire_requires_every_obligation_and_conflict_drained(self):
        self.p.tick(release=7)
        for field in Obligations.__dataclass_fields__:
            self.assertFalse(self.p.tick(acquire=7,obligations=Obligations(**{field:True}))['acquired'])
        for field in ('dense','tile','clear','abort','soft_reset'):
            self.assertFalse(self.p.tick(acquire=7,**{field:True})['acquired'])
        for bad in (0,False,-1,1<<32):
            self.assertFalse(self.p.tick(acquire=bad)['acquired'])
        self.assertTrue(self.p.tick(acquire=7)['acquired'])

    def test_single_outstanding_read_and_default_off(self):
        p=RawKvPort(self.banks)
        self.assertFalse(p.tick(acquire=7)['acquired'])
        self.assertFalse(p.tick(request=Request(Key(7,1,0,True),9))['accepted'])
        self.assertTrue(self.p.tick(request=Request(Key(7,1,0,False)))['accepted'])
        self.assertEqual(self.banks.reads,{0:0,1:0})
        self.assertFalse(self.p.tick(request=Request(Key(7,2,1,False)))['accepted'])
        held=self.p.response
        for bad in (Key(7,True,0,False),Key(7,1,0.0,False),Key(7,1,0,0),Key(7,2,0,False),Key(7,1,1,False),Key(7,1,0,True),None):
            self.assertFalse(self.p.tick(ack=bad)['acked']);self.assertEqual(self.p.response,held)
        self.assertFalse(self.p.tick(ack=held.key,request=Request(Key(7,2,1,False)))['accepted'])
        self.assertTrue(self.p.tick(request=Request(Key(7,2,1,False)))['accepted'])

if __name__=='__main__':unittest.main()
