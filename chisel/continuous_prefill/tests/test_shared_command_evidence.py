"""Verifier unit fixtures only; these are NOT hardware simulation receipts."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_shared_command_gate as v

def chain(n=33,dtype=7):
    packed=32 if dtype==5 else 16;beats=(n+packed-1)//packed;size=2 if dtype==5 else 4
    lines=[f'HOST_COMMAND_CHECK pc={i} values={n} bit_diffs=0 write_ack_bytes={n*size}' for i in range(3)]
    lines.append(f'HOST_COMMAND_CHAIN_PASS commands=3 values={3*n} dtype={dtype} bit_diffs=0 metadata_reads=33 payload_reads={6*beats} write_ack_bytes={3*n*size} idma_transfers={33+9*beats} request_stalls=1 response_delay_cycles=1 host_intermediate_writes=0')
    return '\n'.join(lines)

class SharedCommandEvidenceTest(unittest.TestCase):
    def test_exact_receipt(self):
        for d in (5,7):
            for n in v.LENGTHS:
                with self.subTest(dtype=d,n=n):v.host_checks(chain(n,d),n,d)
    def test_fields_are_not_self_certifying(self):
        text=chain()
        for old,new in [('metadata_reads=33','metadata_reads=32'),('commands=3','commands=2'),('bit_diffs=0','bit_diffs=1'),('write_ack_bytes=132','write_ack_bytes=128'),('host_intermediate_writes=0','host_intermediate_writes=1'),('pc=2','pc=1'),('request_stalls=1','request_stalls=0'),('idma_transfers=60','idma_transfers=59')]:
            with self.subTest(field=old):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):v.host_checks(text.replace(old,new),33,7)
    def test_incomplete_or_duplicate_commands(self):
        t=chain()
        for malformed in ('\n'.join(t.splitlines()[1:]),t+'\n'+t.splitlines()[0],t+'\n'+t.splitlines()[-1]):
            with self.assertRaises(ValueError):v.host_checks(malformed,33,7)
    def test_suite_requires_all_shapes_and_errors(self):
        text='\n'.join(chain(n,d) for d in (5,7) for n in v.LENGTHS)
        err='HOST_COMMAND_CHAIN_ERROR_REJECT_PASS commands=0 values=0 write_ack_bytes=0'
        text+='\n'+'\n'.join([err]*8)+'\nHOST_COMMAND_IDMA_SUITE_PASS cases=30 original_idma=1 command128=1 actual_sfu=1 arithmetic_stub=0'
        v.parse_commands(text)
        for bad in (text.replace(err,'',1),text.replace('cases=30','cases=29'),text.replace('arithmetic_stub=0','arithmetic_stub=1')):
            with self.assertRaises(ValueError):v.parse_commands(bad)
    def test_exact_finite_binary_data(self):
        with tempfile.TemporaryDirectory() as name:
            a,b=Path(name)/'a',Path(name)/'b'
            raw=struct.pack('<ff',1.5,-0.25);a.write_bytes(raw);b.write_bytes(raw)
            v.exact_words(a,b,2)
            for left,right in [(raw[:-1],raw),(raw,bytes([raw[0]^1])+raw[1:]),(struct.pack('<II',0x7fc00000,0),struct.pack('<II',0x7fc00000,0))]:
                a.write_bytes(left);b.write_bytes(right)
                with self.assertRaises(ValueError):v.exact_words(a,b,2)

if __name__=='__main__':unittest.main()
