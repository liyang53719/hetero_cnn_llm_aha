"""Bounded synthetic full-chunk numerical checks; no weights or full block."""
import unittest
import numpy as np
from candidates.qwen35_chunk_strict_contraction.model import Contraction, Matrix, ArithmeticFault
from candidates.qwen35_chunk_strict_contraction.schedule_probe import ScheduleProbe
from candidates.qwen35_strict_fp32_lane import fraction_reference as exact


def words(a):
    return np.asarray(a, dtype=np.float32).view(np.uint32)


class Memory:
    def __init__(self):
        self.regions = {}
        self.writes = []
        self.reads = []

    def allocate(self, base, data):
        data = np.asarray(data, dtype=np.uint32).copy()
        self.regions[base] = data.reshape(-1)
        return Matrix(base, *data.shape)

    def find(self, addr):
        for base, data in self.regions.items():
            if base <= addr and addr+64 <= base+data.nbytes:
                return data, (addr-base)//4
        raise ValueError('unmapped beat')

    def read(self, addr):
        self.reads.append(addr)
        data, offset = self.find(addr)
        return data[offset:offset+16].tolist()

    def write(self, addr, values):
        self.writes.append(addr)
        data, offset = self.find(addr)
        data[offset:offset+16] = values


class Tests(unittest.TestCase):
    def test_m128_two_real_chunks_ut_qk_all_intermediates(self):
        """Two distinct chunks, both phases, one head: 2,097,152 strict MACs."""
        memory = Memory()
        rng = np.random.default_rng(20261022)
        records, observed = [], 0
        outputs = []
        owner = Contraction(memory.read, memory.write)
        workspace = owner._banks + owner._panels
        for chunk in range(2):
            # Non-BF16 lower mantissa bits, mixed signs and cross-token coupling.
            q = rng.uniform(-.3,.3,(64,128)).astype(np.float32)
            kb = rng.uniform(-.2,.2,(64,128)).astype(np.float32)
            kt = rng.uniform(-.3,.3,(128,64)).astype(np.float32)
            pair = np.tril(rng.uniform(.3,1,(64,64)).astype(np.float32))
            np.fill_diagonal(pair, np.float32(1))
            self.assertTrue(np.all(np.diag(pair) == 1))
            self.assertTrue(np.all(pair[np.triu_indices(64,1)] == 0))
            base = 0x100000 + chunk*0x100000
            kt_m = memory.allocate(base+0x10000,words(kt))
            pair_m = memory.allocate(base+0x20000,words(pair))
            for phase, a in ((5,kb),(6,q)):
                a_m = memory.allocate(base+(phase-5)*0x30000,words(a))
                dst = memory.allocate(base+0x60000+(phase-5)*0x10000,np.zeros((64,64),np.uint32))
                # Independent host IEEE float32 ufuncs, separate operations,
                # no matmul/BLAS/FMA or reduction tree. Check every K plane.
                expected_acc = np.zeros((64,64),np.float32)
                expected_product = None
                seen = []
                probes = ((0,0),(31,7),(63,62))
                rational_acc = {cell: 0 for cell in probes}
                rational_product = {}
                aw, bw, pw = words(a), words(kt), words(pair)
                probe = ScheduleProbe(self, owner, memory, (a_m, kt_m, pair_m, dst), aw, bw)
                def observe(stage,k,values,flags):
                    nonlocal expected_acc,expected_product,observed
                    probe.observe(stage,k,values,flags)
                    seen.append((stage,k))
                    if stage == 'mul':
                        # The active accumulator may not be overwritten by Mul.
                        np.testing.assert_array_equal(np.asarray(owner._banks[k % 2],np.uint32),
                                                      words(expected_acc).reshape(-1))
                        expected_product = np.multiply(a[:,k,None],kt[k,None,:],dtype=np.float32)
                        expected = expected_product
                    elif stage == 'add':
                        expected_acc = np.add(expected_product,expected_acc,dtype=np.float32)
                        expected = expected_acc
                    else:
                        r,c = divmod(k,64)
                        expected = np.multiply(expected_acc[r,c:c+16],pair[r,c:c+16],dtype=np.float32)
                    np.testing.assert_array_equal(np.array(values,np.uint32),words(expected).reshape(-1))
                    self.assertTrue(all(f in (0,1) for f in flags))
                    observed += len(values)
                    # Compare every selected product/accumulator AND its flags
                    # before masking; a final zero cannot hide an error here.
                    if stage in ('mul','add'):
                        for r,c in probes:
                            if stage == 'mul':
                                expected_word, expected_flags = exact.mul(int(aw[r,k]),int(bw[k,c]))
                                rational_product[r,c] = expected_word
                            else:
                                expected_word, expected_flags = exact.add(rational_product[r,c],rational_acc[r,c])
                                rational_acc[r,c] = expected_word
                            self.assertEqual((values[r*64+c],flags[r*64+c]),(expected_word,expected_flags))
                    else:
                        r, start = divmod(k,64)
                        for rr,c in probes:
                            if rr == r and start <= c < start+16:
                                self.assertGreater(float(pair[r,c]),0)
                                expected_pair = exact.mul(rational_acc[r,c],int(pw[r,c]))
                                self.assertEqual((values[c-start],flags[c-start]),expected_pair)
                owner.read16, owner.write16, owner.observe = probe.read, probe.write, observe
                records.append(owner.run(a_m,kt_m,pair_m,dst,phase=phase))
                probe.finish()
                for actual, original in zip(owner._banks + owner._panels, workspace):
                    self.assertIs(actual, original)
                self.assertEqual(seen[:256],[(stage,k) for k in range(128) for stage in ('mul','add')])
                result = memory.regions[dst.base].reshape(64,64)
                np.testing.assert_array_equal(result,words(np.multiply(expected_acc,pair,dtype=np.float32)))
                self.assertEqual(records[-1]['read_beats'],1280)
                self.assertEqual(records[-1]['write_beats'],256)
                self.assertEqual(records[-1]['matrix_lane_passes'],1048576)
                self.assertEqual(records[-1]['vector_lane_ops'],4096)
                outputs.append(result.copy())
        self.assertEqual(observed,4210688)
        self.assertFalse(np.array_equal(outputs[0],outputs[2]))
        self.assertEqual(len(memory.writes),1024)
        self.assertEqual(len(set(memory.writes)),1024)
        print('M128 boundary: two genuine chunk64 inputs, one head, phases 5/6; '
              '4194304 Matrix lane passes + 16384 Vector lane operations; '
              '4210688 intermediate/output words checked; NOT full block or RTL.')

    def test_recursive_callbacks_cannot_reown_workspace(self):
        memory, matrices, owner = self.fixture(np.zeros((64,128),np.uint32),
                                              np.zeros((128,64),np.uint32))
        attempted = set()
        def try_reenter(kind):
            if kind not in attempted:
                attempted.add(kind)
                counts = dict(owner.counts)
                with self.assertRaisesRegex(RuntimeError, 'workspace already owned'):
                    owner.run(*matrices, phase=5)
                self.assertEqual(owner.counts, counts)
                self.assertTrue(owner._busy)
        def read(address):
            try_reenter('read')
            return memory.read(address)
        def observe(*args):
            try_reenter('observe')
        def write(address, values):
            try_reenter('write')
            memory.write(address, values)
        owner.read16, owner.write16, owner.observe = read, write, observe
        result = owner.run(*matrices, phase=6)
        self.assertEqual(attempted, {'read', 'observe', 'write'})
        self.assertEqual((result['read_beats'], result['write_beats']), (1280, 256))
        self.assertFalse(owner._busy)

    def test_partial_panel_read_failure_and_clean_workspace_reuse(self):
        for bad in ([0]*15, [0x7fc00000]+[0]*15):
            with self.subTest(bad_length=len(bad)):
                a = words(np.ones((64,128),np.float32))
                kt = words(np.ones((128,64),np.float32)); kt[16:32] = 0x40000000
                seen = []
                memory, matrices, owner = self.fixture(a, kt,
                    observe=lambda stage,k,*_: seen.append((stage,k)))
                workspace = owner._banks + owner._panels
                # Fail the third KT beat in panel 1, after panel 0 was consumed.
                fail_at = matrices[1].base + 4*(16*64+32)
                def read(address):
                    return bad if address == fail_at else memory.read(address)
                owner.read16 = read
                with self.assertRaisesRegex(ValueError, 'finite FP32 read beat'):
                    owner.run(*matrices, phase=5)
                self.assertEqual(seen, [(stage,k) for k in range(16) for stage in ('mul','add')])
                self.assertEqual(owner.counts['read_beats'], 194)
                self.assertEqual(owner.counts['matrix_lane_passes'], 16*8192)
                self.assertEqual(owner.counts['write_beats'], 0)
                self.assertEqual(memory.writes, [])
                self.assertTrue(all(word == 0x41800000 for word in owner._banks[0]))
                self.assertEqual(owner._panels[1][:32], [0x40000000]*32)
                self.assertEqual(owner._panels[1][32:48], [0x3f800000]*16)
                self.assertFalse(owner._busy)
                # Real second run through the same storage. Previous partial
                # panels and nonzero accumulation must not leak into new work.
                memory.regions[matrices[0].base][:] = 0
                owner.read16, owner.observe = memory.read, None
                result = owner.run(*matrices, phase=6)
                self.assertEqual((result['read_beats'], result['write_beats']), (1280,256))
                self.assertTrue(np.all(memory.regions[matrices[-1].base] == 0))
                for actual, original in zip(owner._banks + owner._panels, workspace):
                    self.assertIs(actual, original)

    def test_schedule_oracle_rejects_wrong_address_and_bank_identity(self):
        a = np.zeros((64,128),np.uint32); kt = np.zeros((128,64),np.uint32)
        for mutant in ('address', 'bank'):
            with self.subTest(mutant=mutant):
                memory, matrices, owner = self.fixture(a, kt)
                probe = ScheduleProbe(self, owner, memory, matrices, a, kt)
                owner.read16, owner.write16, owner.observe = probe.read, probe.write, probe.observe
                if mutant == 'address':
                    original = owner._read
                    owner._read = lambda address: original(address+64)
                    reason = 'synchronous schedule mismatch'
                else:
                    # A copied plane has identical numbers but is not the
                    # allocated product bank. The identity oracle must reject it.
                    owner.observe = lambda stage,k,values,flags: probe.observe(stage,k,list(values),flags)
                    reason = 'is not'
                with self.assertRaisesRegex(AssertionError, reason):
                    owner.run(*matrices, phase=5)
                self.assertEqual(memory.writes, [])
                self.assertFalse(owner._busy)

    def fixture(self, a, kt, pair=None, observe=None, write=None):
        memory=Memory()
        if pair is None:
            pair=words(np.tril(np.ones((64,64),np.float32)))
        matrices=[memory.allocate(base,data) for base,data in (
            (0x10000,a),(0x20000,kt),(0x30000,pair),
            (0x40000,np.full((64,64),0xdeadbeef,np.uint32)))]
        owner=Contraction(memory.read,write or memory.write,observe)
        return memory,matrices,owner

    def test_actual_contraction_rounding_order_and_exact_flags(self):
        a=np.zeros((64,128),np.uint32)
        kt=np.zeros((128,64),np.uint32)
        # FMA discriminator: first accumulate -1, then rounded product ~= 1.
        a[0,:2]=[0xbf800000,0x3f800001]
        kt[:2,0]=[0x3f800000,0x3f7ffffe]
        # Reverse-K discriminator: large, -large, 1.
        a[1,:3]=[0x4c000000,0xcc000000,0x3f800000]
        kt[:3,1]=0x3f800000
        # Factor-inside-reduction discriminator, at a strictly lower cell.
        a[3,:2]=[0x3f800001,0xbf800000]
        kt[:2,2]=0x3f800000
        pair=words(np.tril(np.ones((64,64),np.float32)))
        pair[3,2]=0x3f000001
        # Exact subnormal and signed-zero products must survive admission.
        a[4,0]=1; kt[0,3]=0x3f800000
        a[5,0]=0x80000000; kt[0,4]=0x3f800000
        cells=((0,0),(1,1),(3,2),(4,3),(5,4))
        acc={cell:0 for cell in cells}; product={}; captured={}; observed_flags=set()
        def observe(stage,k,values,flags):
            if stage in ('mul','add'):
                for r,c in cells:
                    if stage=='mul':
                        expected=exact.mul(int(a[r,k]),int(kt[k,c])); product[r,c]=expected[0]
                    else:
                        expected=exact.add(product[r,c],acc[r,c]); acc[r,c]=expected[0]
                    self.assertEqual((values[r*64+c],flags[r*64+c]),expected)
                    observed_flags.add(expected[1])
                    captured[stage,k,r,c]=values[r*64+c]
        memory,matrices,owner=self.fixture(a,kt,pair,observe)
        owner.run(*matrices,phase=6)
        result=memory.regions[matrices[-1].base].reshape(64,64)
        for r,c in cells:
            self.assertEqual(int(result[r,c]),exact.mul(acc[r,c],int(pair[r,c]))[0])
        self.assertEqual(captured['mul',0,5,4],0x80000000)
        self.assertEqual(captured['add',0,5,4],0)
        self.assertEqual(int(result[4,3]),1)
        self.assertEqual(observed_flags,{0,1})
        fused=exact.fma(int(a[0,1]),int(kt[1,0]),0xbf800000)[0]
        self.assertNotEqual(int(result[0,0]),fused)
        reverse=0
        for k in range(127,-1,-1):
            reverse=exact.add(exact.mul(int(a[1,k]),int(kt[k,1]))[0],reverse)[0]
        self.assertNotEqual(int(result[1,1]),reverse)
        inside=0
        for k in range(128):
            p=exact.mul(int(a[3,k]),int(kt[k,2]))[0]
            inside=exact.add(exact.mul(p,int(pair[3,2]))[0],inside)[0]
        self.assertNotEqual(int(result[3,2]),inside)

    def test_add_fatal_preserves_no_writes(self):
        a=np.zeros((64,128),np.uint32); a[0,:2]=0x7f7fffff
        kt=np.zeros((128,64),np.uint32); kt[:2,0]=0x3f800000
        stages=[]
        memory,matrices,owner=self.fixture(a,kt,observe=lambda stage,k,*_:stages.append((stage,k)))
        with self.assertRaises(ArithmeticFault) as caught:
            owner.run(*matrices,phase=5)
        fault=caught.exception
        self.assertEqual((fault.stage,fault.k,fault.lane,fault.word,fault.flags),('add',1,0,0x7f800000,5))
        self.assertEqual(stages,[('mul',0),('add',0),('mul',1),('add',1)])
        self.assertEqual(memory.writes,[])
        self.assertEqual(owner.counts['matrix_lane_passes'],16384)

    def test_pair_underflow_fatal_and_partial_write_boundary(self):
        a=np.zeros((64,128),np.uint32); a[0,0]=1
        kt=np.zeros((128,64),np.uint32); kt[0,:]=0x3f800000
        pair=words(np.ones((64,64),np.float32)); pair[0,16]=0x3f000000
        # Deliberately malformed/noncausal phase-boundary input tests the
        # generic post-reduction fault path, not upstream pair generation.
        memory,matrices,owner=self.fixture(a,kt,pair)
        with self.assertRaises(ArithmeticFault) as caught:
            owner.run(*matrices,phase=5)
        fault=caught.exception
        self.assertEqual((fault.stage,fault.k,fault.lane,fault.word,fault.flags),('pair',16,0,0,3))
        self.assertEqual(memory.writes,[matrices[-1].base])
        self.assertEqual(owner.counts['write_beats'],1)
        self.assertTrue(np.all(memory.regions[matrices[-1].base][16:]==0xdeadbeef))

    def test_write_failure_does_not_count_completion(self):
        a=np.zeros((64,128),np.uint32)
        kt=np.zeros((128,64),np.uint32)
        memory,matrices,owner=self.fixture(a,kt)
        attempts=[]
        def fail_second(address,values):
            attempts.append(address)
            if len(attempts)==2:
                raise OSError('injected modeled write failure before mutation')
            memory.write(address,values)
        owner.write16=fail_second
        with self.assertRaisesRegex(OSError,'modeled write failure'):
            owner.run(*matrices,phase=6)
        self.assertEqual(len(attempts),2)
        self.assertEqual(owner.counts['write_beats'],1)
        self.assertEqual(len(memory.writes),1)
        self.assertTrue(np.all(memory.regions[matrices[-1].base][16:]==0xdeadbeef))

    def test_mul_fatal_never_adds_or_writes(self):
        memory=Memory()
        a=np.zeros((64,128),np.uint32); a[0,0]=0x7f7fffff
        kt=np.zeros((128,64),np.uint32); kt[0,0]=0x40000000
        matrices=[memory.allocate(base,data) for base,data in (
            (0x10000,a),(0x20000,kt),(0x30000,words(np.ones((64,64)))),
            (0x40000,np.zeros((64,64),np.uint32)))]
        stages=[]
        owner=Contraction(memory.read,memory.write,lambda stage,*args: stages.append(stage))
        with self.assertRaises(ArithmeticFault) as raised:
            owner.run(*matrices,phase=5)
        self.assertEqual((raised.exception.stage,raised.exception.k,raised.exception.lane,
                          raised.exception.word,raised.exception.flags),('mul',0,0,0x7f800000,5))
        self.assertEqual(stages,['mul'])
        self.assertEqual(memory.writes,[])
        self.assertEqual(owner.counts['matrix_lane_passes'],4096)

    def test_reject_m1_and_overlap(self):
        owner=Contraction(lambda _:[],lambda *_:None)
        with self.assertRaises(ValueError):
            owner.run(Matrix(0,1,128),Matrix(0x10000,128,64),Matrix(0x20000,64,64),Matrix(0x30000,64,64),phase=5)
        with self.assertRaises(ValueError):
            owner.run(Matrix(0,64,128),Matrix(0,128,64),Matrix(0x20000,64,64),Matrix(0x30000,64,64),phase=6)

if __name__=='__main__':
    unittest.main()
