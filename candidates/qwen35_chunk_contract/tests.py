#!/usr/bin/env python3
"""Pure-stdlib source/declarative-math controls, NOT Scala/RTL execution.

ACK tests use the explicitly synthetic MockAckContract below. They do not
produce or validate a real hardware receipt, numerical output or publication.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
EXPECTED_SHAPES = [
    ('gates',64,16),('q',64,128),('k',64,128),('v',64,128),
    ('kb',64,128),('vb',64,128),('kbg',64,128),('qg',64,128),('ke',64,128),
    ('kt',128,64),('ket',128,64),('pair',64,64),('ut',64,64),('intra',64,64),
    ('solvek',64,128),('solvev',64,128),('pred',64,128),('vnew',64,128),
    ('inter',64,128),('local',64,128),('out',64,128),('state_update',128,128),
    ('decay_state',128,128),('next_state',128,128)]
EXPECTED_GEOMETRY = dict(ChunkRows=64,Heads=16,KeyDim=128,ValueDim=128,
    BeatBytes=64,PreparedRowBytes=25600,StateBytes=1048576,OutputRowBytes=4096,AddressBits=56)
BASES = (0x100000,0x800000,0xa00000,0xc00000,0x1000000)
SHAPES = PHASES = PROTOCOL = PLAN_SOURCE = BASE_SOURCE = None
PIN_COUNT = 0


def need(ok, message='contract'):
    if not ok:
        raise ValueError(message)


def check_pin(path, spec):
    need(path.is_file() and not path.is_symlink(), 'regular exact file')
    a = path.stat(); raw = path.read_bytes(); b = path.stat()
    need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns) ==
         (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns), 'read drift')
    need(len(raw) == spec['bytes'] and hashlib.sha256(raw).hexdigest() == spec['sha256'], str(path.name))
    return raw


def readonly_audit(event, args):
    if event in ('ctypes.dlopen','subprocess.Popen','os.system','os.posix_spawn') or event.startswith('socket.'):
        raise RuntimeError('controls forbid native/process/network')
    if event == 'open':
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            raise RuntimeError('controls are read-only')


def span(base, size):
    need(type(base) is int and type(size) is int and base >= 0 and size > 0)
    need(base % 64 == size % 64 == 0 and base + size <= 1 << 56)
    return base, base + size


class MathPlan:
    """Independent Python interpretation of declarative shape/order data only.

    This does NOT call compiled Scala. Formula equivalence and hardware behavior
    need a later separately admitted Scala/elaboration/RTL test.
    """
    def __init__(self, tokens, bases=BASES, *, cold=True, generation=0,
                 committed_generation=0, committed_state=None, policy=0):
        need(type(tokens) is int and tokens in (16,128))
        need(type(cold) is bool and type(generation) is int and 0 <= generation < (1 << 32)-1)
        need(type(committed_generation) is int and committed_generation == generation)
        need((cold and generation == 0 and committed_state is None) or
             (not cold and generation > 0 and committed_state == bases[1]))
        need(type(policy) is int and policy in (0,1))
        self.tokens, self.bases, self.generation = tokens, bases, generation
        self.chunks = (tokens+63)//64
        self.per_chunk = sum(r*c*4 for _,r,c in SHAPES)
        self.head_stride = 65536+self.chunks*self.per_chunk
        self.scratch = 16*self.head_stride
        self.sizes = (tokens*25600,1048576,1048576,tokens*4096,self.scratch)
        self.spans = [span(b,n) for b,n in zip(bases,self.sizes)]
        need(len(bases) == 5)
        for i,(a,z) in enumerate(self.spans):
            for b,e in self.spans[:i]:
                need(z <= b or e <= a, 'whole-span alias')
        self.steps = []
        for h in range(16):
            self.steps.append((h,0,0))
            for c in range(self.chunks):
                self.steps.extend((h,c,p+1) for p in range(len(PHASES)))
            self.steps.append((h,self.chunks-1,18))

    def initial(self,h):
        need(type(h) is int and 0 <= h < 16)
        return self.bases[4]+h*self.head_stride

    def matrix(self,h,c,name):
        need(type(c) is int and 0 <= c < self.chunks)
        base = self.initial(h)+65536+c*self.per_chunk
        for n,r,k in SHAPES:
            if n == name:
                return base,r,k
            base += r*k*4
        raise ValueError('unknown matrix')

    def previous(self,h,c):
        need(type(c) is int and 0 <= c < self.chunks)
        return self.initial(h) if c == 0 else self.matrix(h,c-1,'next_state')[0]

    def valid_rows(self,c):
        need(type(c) is int and 0 <= c < self.chunks)
        return min(64,self.tokens-c*64)

    def ack(self,step):
        need(step in self.steps)
        h,c,p = step
        if p == 0: return (65536,0,0)
        if p == 18: return (0,0,65536)
        if p == 17: return (0,self.valid_rows(c)*128*2,0)
        names = PHASES[p-1][1]
        return (sum(self.matrix(h,c,n)[1]*self.matrix(h,c,n)[2]*4 for n in names),0,0)


class MockAckContract:
    """TEST-ONLY supplied receipt validator, not an actual bus/Chisel owner.

    Exact counts are hypothetical successful accepted beats. This model cannot
    prove those beats occurred. Stage completion never advances generation.
    """
    def __init__(self,plan,tag=7):
        self.plan,self.tag,self.index,self.failed = plan,tag,0,False
        self.generation = plan.generation

    def accept(self,step,counts,*,tag=7,generation=0,drained=True,status=0):
        good = (not self.failed and self.index < len(self.plan.steps) and
                step == self.plan.steps[self.index] and type(tag) is int and tag == self.tag and
                type(generation) is int and generation == self.generation and
                type(status) is int and status == 0 and drained is True and
                type(counts) is tuple and all(type(n) is int and n >= 0 and n % 64 == 0 for n in counts) and
                counts == self.plan.ack(step))
        if not good:
            self.failed = True
            raise ValueError('mock stage receipt rejected')
        self.index += 1

    @property
    def staged(self):
        return not self.failed and self.index == len(self.plan.steps)

    def publication_eligible(self,*,history_ready=False,residual_ready=False,fence_accepted=False,drained=False):
        # No publication or generation mutation occurs, even in this model.
        return self.staged and all(x is True for x in (history_ready,residual_ready,fence_accepted,drained))


class SourceControls(unittest.TestCase):
    def test_01_shapes_match_fixed_software_ast(self):
        fn = next(x for x in ast.parse(BASE_SOURCE).body if isinstance(x,ast.FunctionDef) and x.name == '_shapes')
        vals=[]
        for elt in fn.body[0].value.elts:
            vals.append(tuple(x.value if isinstance(x,ast.Constant) else {'dk':128,'dv':128}[x.id] for x in elt.elts))
        self.assertEqual(SHAPES,EXPECTED_SHAPES)
        self.assertEqual(SHAPES,vals)

    def test_02_geometry_and_nonpublication_types(self):
        constants = dict((k,int(v)) for k,v in re.findall(r'val (\w+) = (\d+)\b',PROTOCOL))
        self.assertEqual({k:constants[k] for k in EXPECTED_GEOMETRY},EXPECTED_GEOMETRY)
        self.assertIn('Set(16, 128)',PROTOCOL)
        body = PROTOCOL.split('class GdnChunkStagingResult extends Bundle {',1)[1]
        fields = re.findall(r'val (\w+) =',body)
        self.assertEqual(fields,['tag','expectedGeneration','status','stagedComplete','stateOut','output',
            'completedHeadChunks','scratchAckBytes','stateAckBytes','outputAckBytes','drained'])
        self.assertNotRegex(PROTOCOL,r'class\s+\w+\s+extends\s+Module\b')
        self.assertNotIn('Decoupled(',PROTOCOL)
        self.assertNotRegex(PLAN_SOURCE,r'extends\s+Module\b')

    def test_03_phase_coverage_and_source_formulas(self):
        self.assertEqual(len(PHASES),17)
        self.assertEqual(sorted(n for _,ns in PHASES for n in ns),sorted(n for n,_,_ in SHAPES))
        self.assertEqual(PHASES[-1],('OutputMaterialize',[]))
        for text in ('base + bytes <= AddressLimit','spans(i).disjoint(spans(j))',
                     'committed.state.contains(bases.stateIn)','expectedGeneration < LastGeneration',
                     'matrix(head, chunk - 1, "next_state")','Step(head, chunkCount - 1, StateOutPhase)',
                     'AckBytes(scratchBytes(tokens), BigInt(tokens) * OutputRowBytes, BigInt(StateBytes))'):
            self.assertIn(text,PLAN_SOURCE)

    def test_04_sizes_and_fp32_state(self):
        for m,scratch,total in ((16,13959168,16531456),(128,26869760,32768000)):
            p=MathPlan(m)
            self.assertEqual(p.per_chunk,806912)
            self.assertEqual(p.scratch,scratch)
            self.assertEqual(sum(p.sizes),total)
            self.assertEqual(p.sizes[1:3],(16*128*128*4,)*2)
            self.assertEqual(p.sizes[3],m*16*128*2)

    def test_05_chunk64_and_padding(self):
        p=MathPlan(16);self.assertEqual((p.chunks,p.valid_rows(0)),(1,16))
        p=MathPlan(128);self.assertEqual([p.valid_rows(i) for i in range(2)],[64,64])
        self.assertEqual([(t//64,t%64) for t in (0,15,16,63,64,127)],[(0,0),(0,15),(0,16),(0,63),(1,0),(1,63)])
        for bad in (-1,0,1,64,65,129,True):
            with self.assertRaises(ValueError):MathPlan(bad)

    def test_06_exact_head_chunk_offsets(self):
        p=MathPlan(128)
        self.assertEqual(p.head_stride,1679360)
        b=p.initial(0)
        self.assertEqual(p.matrix(0,0,'gates')[0]-b,65536)
        self.assertEqual(p.matrix(0,1,'gates')[0]-b,872448)
        self.assertEqual(p.matrix(0,0,'next_state')[0]-b,806912)
        self.assertEqual(p.matrix(0,1,'next_state')[0]-b,1613824)
        self.assertEqual(p.previous(0,1),p.matrix(0,0,'next_state')[0])
        self.assertNotEqual(p.previous(0,1),p.bases[2])

    def test_07_all_matrix_extents_cover_once(self):
        for m in (16,128):
            p=MathPlan(m);cursor=p.bases[4];beats=0;matrices=0
            for h in range(16):
                self.assertEqual(p.initial(h),cursor);cursor+=65536;beats+=1024;matrices+=1
                for c in range(p.chunks):
                    for name,r,k in SHAPES:
                        b,rr,kk=p.matrix(h,c,name)
                        self.assertEqual((b,rr,kk),(cursor,r,k))
                        # Stream integer addresses; no large tensor/list allocation.
                        for a in range(b,b+r*k*4,64):
                            self.assertEqual(a,cursor);cursor+=64;beats+=1
                        matrices+=1
            self.assertEqual(cursor,p.bases[4]+p.scratch)
            self.assertEqual(beats,p.scratch//64)
            self.assertEqual(matrices,16*(1+p.chunks*24))

    def test_08_span_limits(self):
        self.assertEqual(span((1<<56)-64,64)[1],1<<56)
        for b,n in ((-64,64),(1,64),(0,0),(0,-64),(0,65),((1<<56)-64,128),(1<<56,64),(True,64)):
            with self.assertRaises(ValueError):span(b,n)
        for name,r,c in SHAPES:
            self.assertEqual(((r-1)*c+c-16)*4+64,r*c*4)
            for row,col in ((-1,0),(r,0),(0,-16),(0,c),(0,1)):
                with self.assertRaises(ValueError):
                    need(0 <= row < r and 0 <= col < c and col % 16 == 0)

    def test_09_all_pairs_alias_rejected(self):
        for i in range(5):
            for j in range(i):
                bases=list(BASES);bases[i]=bases[j]
                with self.assertRaises(ValueError):MathPlan(128,tuple(bases))
        bases=list(BASES);bases[4]=bases[0]+128*25600-64
        with self.assertRaises(ValueError):MathPlan(128,tuple(bases))
        bases=list(BASES);bases[4]=bases[0]-64 # input completely contained in scratch
        with self.assertRaises(ValueError):MathPlan(128,tuple(bases))
        p=MathPlan(128);adjacent=[];cursor=0
        for n in p.sizes:adjacent.append(cursor);cursor+=n
        MathPlan(128,tuple(adjacent)) # endpoint adjacency is not aliasing

    def test_10_cold_carried_generation(self):
        MathPlan(128,cold=False,generation=7,committed_generation=7,committed_state=BASES[1],policy=1)
        for kw in ({'generation':1,'committed_generation':1},
                   {'committed_state':BASES[1]},
                   {'cold':False},
                   {'cold':False,'generation':7,'committed_generation':7,'committed_state':BASES[1]+64},
                   {'cold':False,'generation':7,'committed_generation':6,'committed_state':BASES[1]},
                   {'generation':(1<<32)-1,'committed_generation':(1<<32)-1},
                   {'policy':2}):
            with self.assertRaises(ValueError):MathPlan(128,**kw)

    def test_11_prepared_offsets_and_last_beats(self):
        for m in (16,128):
            p=MathPlan(m)
            for t in (0,m-1):
                row=p.bases[0]+t*25600
                self.assertEqual([row+r*8192-row for r in range(3)],[0,8192,16384])
                self.assertEqual(row+24576+15*64+64,row+25600)
            self.assertEqual(p.bases[1]+((15*128+127)*128+112)*4+64,p.spans[1][1])
            self.assertEqual(p.bases[3]+(((m-1)*16+15)*128+96)*2+64,p.spans[3][1])

    def test_12_order_and_cross_chunk_dependency(self):
        p=MathPlan(128)
        self.assertEqual(len(p.steps),16*(2+2*17))
        for h in range(16):
            a=p.steps.index((h,1,1))
            self.assertEqual(p.steps[a-1],(h,0,17))
            self.assertEqual(p.steps[p.steps.index((h,1,18))-1],(h,1,17))
            if h:
                self.assertEqual(p.steps[p.steps.index((h,0,0))-1],(h-1,1,18))

    def test_13_exact_ack_totals(self):
        for m in (16,128):
            p=MathPlan(m)
            actual=tuple(sum(p.ack(s)[i] for s in p.steps) for i in range(3))
            self.assertEqual(actual,(p.scratch,m*4096,1048576))

    def test_14_mock_final_ack_and_fence(self):
        for m in (16,128):
            p=MathPlan(m);x=MockAckContract(p)
            for step in p.steps[:-1]:x.accept(step,p.ack(step))
            self.assertFalse(x.staged)
            self.assertFalse(x.publication_eligible(history_ready=True,residual_ready=True,fence_accepted=True,drained=True))
            x.accept(p.steps[-1],p.ack(p.steps[-1]));self.assertTrue(x.staged)
            self.assertFalse(x.publication_eligible())
            self.assertFalse(x.publication_eligible(history_ready=True,residual_ready=True,drained=True))
            self.assertTrue(x.publication_eligible(history_ready=True,residual_ready=True,fence_accepted=True,drained=True))
            self.assertEqual(x.generation,0)

    def test_15_mock_wrong_or_incomplete_receipt_poison(self):
        p=MathPlan(128);first=p.steps[0]
        for counts,kw in (((65472,0,0),{}),((65600,0,0),{}),((65536,0,0),{'tag':8}),
                          ((65536,0,0),{'generation':1}),((65536,0,0),{'drained':False}),
                          ((65536,0,0),{'status':1}),((65536,0,0),{'status':False})):
            x=MockAckContract(p)
            with self.assertRaises(ValueError):x.accept(first,counts,**kw)
            with self.assertRaises(ValueError):x.accept(first,p.ack(first))
            self.assertFalse(x.staged)

    def test_16_mock_no_skip_duplicate_or_cross_chunk(self):
        p=MathPlan(128)
        for wrong in (p.steps[1],(0,1,1),(1,0,0),(0,0,18)):
            with self.assertRaises(ValueError):MockAckContract(p).accept(wrong,p.ack(wrong))
        x=MockAckContract(p);s=p.steps[0];x.accept(s,p.ack(s))
        with self.assertRaises(ValueError):x.accept(s,p.ack(s))

    def test_17_state_and_output_are_distinct_obligations(self):
        p=MathPlan(128)
        self.assertEqual(p.ack((0,0,16)),(65536,0,0)) # private next_state
        self.assertEqual(p.ack((0,0,17)),(0,16384,0)) # valid BF16 output
        self.assertEqual(p.ack((0,1,18)),(0,0,65536)) # final external stateOut
        self.assertNotEqual(p.matrix(0,0,'next_state')[0],p.matrix(1,0,'next_state')[0])


def main():
    start=time.monotonic()
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,required=True)
    args=parser.parse_args()
    need(sys.version_info[:2] == (3,12), 'target CPython 3.12 required')
    resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(8,9))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    def expired(signum,frame):raise TimeoutError('nine-second internal controls limit')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,9)
    global SHAPES,PHASES,PROTOCOL,PLAN_SOURCE,BASE_SOURCE,PIN_COUNT
    sys.addaudithook(readonly_audit)
    own=json.loads((HERE/'SOURCE_MANIFEST.json').read_bytes())
    need(own['schema']=='QWEN35_CHUNK_CONTRACT_SOURCE_V1')
    for name,spec in own['files'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts)
        check_pin(HERE/name,spec);PIN_COUNT+=1
    inputs=json.loads((HERE/'INPUT_PINS.json').read_bytes())
    need(inputs['fixed_remote_commit']=='adefaa78c2d313d9927b4e87550dddc926b3c605')
    repo=args.repo.resolve(strict=True)
    cache={}
    for name,spec in inputs['files'].items():
        need(not Path(name).is_absolute() and '..' not in Path(name).parts)
        cache[name]=check_pin(repo/name,spec);PIN_COUNT+=1
    PROTOCOL=(HERE/'source/GdnChunkProtocol.scala').read_text()
    PLAN_SOURCE=(HERE/'source/GdnChunkAddressPlan.scala').read_text()
    BASE_SOURCE=cache['candidates/qwen35_gdn_prefill/chunk/model.py']
    SHAPES=[(n,int(r),int(c)) for n,r,c in re.findall(r'Shape\("(\w+)", (\d+), (\d+)\)',PLAN_SOURCE)]
    PHASES=[]
    for name,values in re.findall(r'Phase\("(\w+)", (Vector\([^\)]*\)|Vector.empty)\)',PLAN_SOURCE):
        PHASES.append((name,re.findall(r'"(\w+)"',values)))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceControls))
    # Source stamps/bytes checked again after the entire limited suite.
    for name,spec in own['files'].items():check_pin(HERE/name,spec)
    for name,spec in inputs['files'].items():check_pin(repo/name,spec)
    signal.setitimer(signal.ITIMER_REAL,0)
    print(json.dumps({'schema':'QWEN35_CHUNK_CONTRACT_CONTROLS_V1','passed':result.wasSuccessful(),
        'groups':result.testsRun,'pin_count_before_and_after':PIN_COUNT,'elapsed_seconds':time.monotonic()-start,
        'scope':'source literals plus independent integer formulas and explicitly MOCK ACK receipts',
        'scala_compiled':False,'chisel_executed':False,'rtl_generated':False,'arithmetic_tested':False,
        'candidate_imported':False,'native_loaded':False,'publication_performed':False},sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
    raise SystemExit(main())
