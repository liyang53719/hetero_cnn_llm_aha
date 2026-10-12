"""Real full-beat ACK coverage and atomic dual-output visibility."""
from types import SimpleNamespace as N
import unittest
from ...qwen35_gdn_prefill.typed_dense import TypedMemory

class AtomicPublicationTests(unittest.TestCase):
    def fixture(self):
        m=TypedMemory();m.add_readonly(0x1000,bytes(64))
        for b in (0x2000,0x3000):m.allocate_output(b,64)
        return m

    def write(self,m,b,*,error=False,ack=True):
        m.begin_write(N(address=b,beats=1,tag=b))
        m.write_data(tuple(range(32)),True)
        if ack:m.acknowledge(N(tag=b,nbytes=64,error=error))

    def test_both_publish_only_after_all_real_acks(self):
        m=self.fixture();self.write(m,0x2000);self.write(m,0x3000,ack=False)
        with self.assertRaises(ValueError):m.publish_many((0x2000,0x3000),(7,None,128))
        self.assertFalse(any(m.regions[b].published for b in (0x2000,0x3000)))
        m.acknowledge(N(tag=0x3000,nbytes=64,error=False))
        m.publish_many((0x2000,0x3000),(7,None,128))
        self.assertEqual(m.read64(0x2000),m.read64(0x3000))
        self.assertEqual(m.read64(0x1000),bytes(64))

    def test_second_ack_error_or_guard_failure_preserves_both_unpublished(self):
        for mode in ('ack','guard'):
            with self.subTest(mode=mode):
                m=self.fixture();self.write(m,0x2000);self.write(m,0x3000,error=mode=='ack')
                if mode=='guard':m.regions[0x3000].storage[-1]^=1
                with self.assertRaises(ValueError):m.publish_many((0x2000,0x3000),(7,None,128))
                for b in (0x2000,0x3000):
                    self.assertFalse(m.regions[b].published)
                    with self.assertRaises(ValueError):m.read64(b)

    def test_terminal_span_and_byte_contract_rejects_without_partial_publish(self):
        m=self.fixture();self.write(m,0x2000);self.write(m,0x3000)
        cases=[((),(7,None,0)),((0x2000,0x2000),(7,None,128)),
            ((0x2000,0x4000),(7,None,128)),((0x2000,0x1000),(7,None,128)),
            ((0x2000,0x3000),(7,'Fault',128)),((0x2000,0x3000),(7,None,64)),
            ((0x2000,0x3000),(7,None,True))]
        for bases,result in cases:
            with self.subTest(bases=bases,result=result):
                with self.assertRaises(ValueError):m.publish_many(bases,result)
                self.assertFalse(m.regions[0x2000].published or m.regions[0x3000].published)
        m.publish(0x2000,(7,None,64))
        with self.assertRaises(ValueError):m.publish_many((0x2000,0x3000),(7,None,128))
        self.assertTrue(m.regions[0x2000].published);self.assertFalse(m.regions[0x3000].published)

if __name__=='__main__':unittest.main()
