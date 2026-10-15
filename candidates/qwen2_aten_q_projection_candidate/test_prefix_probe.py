import hashlib
import unittest
from unittest.mock import patch
from . import prefix_probe as p

class PrefixCold(unittest.TestCase):
    def test_default_no_reads(self):
        with patch('pathlib.Path.open',side_effect=AssertionError('read')):
            self.assertEqual(p.run(),{'status':'NOT_EXECUTED'})
    def record(self):return dict(name='qr',owner_terminal=True,finite=True,bytes=4,ack_bytes=4,sha256=hashlib.sha256(b'abcd').hexdigest())
    def test_completed_record(self):
        r=self.record();self.assertEqual(p.completed_record([r],'qr',b'abcd'),r)
    def test_reject_receipt_variations(self):
        for field,value in [('owner_terminal',False),('finite',False),('ack_bytes',0),('bytes',8),('sha256','0'*64)]:
            r=self.record();r[field]=value
            with self.assertRaises(ValueError):p.completed_record([r],'qr',b'abcd')
        with self.assertRaises(ValueError):p.completed_record([self.record()]*2,'qr',b'abcd')
        with self.assertRaises(ValueError):p.completed_record([],'qr',b'abcd')

if __name__=='__main__':unittest.main()
