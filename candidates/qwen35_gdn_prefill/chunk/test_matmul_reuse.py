"""Cold scheduling/storage gates; integer fixture is not floating point validation."""
import struct,unittest
from .model import Matrix
from .matmul_reuse import Scratch1024,matmul4
from .replay_matmul_reuse import LocalOwner,execute

class IntegerFixtureVector:
    def __init__(self):self.client=None
    def acquire(self,client):
        if self.client is not None:raise ValueError('busy')
        self.client=client
    def release(self,client):
        if self.client is not client:raise ValueError('owner')
        self.client=None
    def mul_add(self,client,a,b,total):
        if self.client is not client:raise ValueError('owner')
        return [(x+y*z)&0xffff for x,y,z in zip(total,a,b)]
    def op(self,client,op,a,b):return [(x*y)&0xffff for x,y in zip(a,b)]

def fixture(rows=4):
    a=Matrix(0x1000,rows,32);b=Matrix(0x2000,32,32);d=Matrix(0x4000,rows,32)
    values=lambda n:struct.pack('<'+'I'*n,*[(i%11)+1 for i in range(n)])
    return a,b,d,{'a':(a.base,values(rows*32)),'b':(b.base,values(32*32))}

class ReuseTests(unittest.TestCase):
    def test_same_order_and_exact_transport_with_tail(self):
        for rows in (1,4,5,8):
            a,b,d,inputs=fixture(rows)
            old=execute(IntegerFixtureVector(),a,b,d,inputs)
            new=execute(IntegerFixtureVector(),a,b,d,inputs,reuse=True)
            self.assertEqual(old[0],new[0]);self.assertEqual(old[2],new[2])
            self.assertEqual(old[1]['a_read_bytes'],new[1]['a_read_bytes'])
            self.assertEqual(new[1]['b_read_bytes'],((rows+3)//4)*2*32*64)
            self.assertEqual(new[1]['write_bytes'],new[1]['write_ack_bytes'])
            self.assertLessEqual(new[3],1024)
    def test_lease_and_range_checks(self):
        s=Scratch1024();a=object();b=object();s.acquire(a)
        with self.assertRaises(ValueError):s.acquire(b)
        with self.assertRaises(ValueError):s.put(a,255,[1,2])
        with self.assertRaises(ValueError):s.put(b,0,[1])
        with self.assertRaises(ValueError):s.get(a,256,1)
        s.put(a,192,[0]*64);self.assertEqual(s.high_water_words,256);s.release(a)
    def test_exception_releases_local_lease_without_claiming_transport_recovery(self):
        a,b,d,inputs=fixture();v=IntegerFixtureVector();o=LocalOwner(v);s=Scratch1024();v.acquire(o)
        g=matmul4(o,a,b,d,scratch=s);next(g);self.assertIs(s.client,o)
        with self.assertRaisesRegex(RuntimeError,'injected read failure'):g.throw(RuntimeError('injected read failure'))
        self.assertIsNone(s.client);v.release(o)
    def test_suspended_write_holds_scratch_until_ack_advance(self):
        a,b,d,inputs=fixture();v=IntegerFixtureVector();o=LocalOwner(v);s=Scratch1024();v.acquire(o)
        g=matmul4(o,a,b,d,scratch=s);reply=None
        while True:
            address,data=g.send(reply)
            if data is not None:break
            _,(base,raw)=next((n,x) for n,x in inputs.items() if x[0]<=address<x[0]+len(x[1]))
            reply=raw[address-base:address-base+64]
        self.assertIs(s.client,o)
        with self.assertRaises(ValueError):s.acquire(object())
        # Closing only abandons the local arithmetic generator. A production
        # transport must separately drain this accepted write before reuse.
        g.close();self.assertIsNone(s.client);v.release(o)
if __name__=='__main__':unittest.main()
