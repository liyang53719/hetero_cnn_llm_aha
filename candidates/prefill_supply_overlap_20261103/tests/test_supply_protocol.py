"""Small pure protocol/arithmetic model tests. NOT Chisel, RTL, or model PASS."""
import hashlib, itertools, pathlib, random, struct, unittest
D=pathlib.Path(__file__).resolve().parents[1]

def spans(address, beats):
    while beats:
        n=min(beats,16-(address//64)%16)
        yield address,n
        address+=64*n;beats-=n

def a_spans(base,m,k,bf16,chunk_base=0,chunk_depth=None):
    depth=chunk_depth or k; width=2 if bf16 else 4
    for row in range(m):
        yield from spans(base+(row*k+chunk_base)*width,depth*width//64)

def b_spans(base,n,begin,end,ng,contexts,bf16):
    width=2 if bf16 else 4
    for k in range(begin,end):
        yield from spans(base+(k*n+ng)*width,contexts*32*width//64)

def expand(ds):
    for address,n in ds:
        for i in range(n):yield address+i*64

class Receiver:
    def __init__(self,n,tag=9):
        assert 1<=n<=16
        self.n=n;self.tag=tag;self.received=0;self.poison=False;self.committed=False;self.staged=[]
    def beat(self,value,last,tag=9,error=False,finite=True,ready=True):
        if not ready:return
        assert self.received<self.n
        terminal=self.received+1==self.n
        bad=last!=terminal or tag!=self.tag or error or not finite
        if not bad and not self.poison:self.staged.append(value)
        self.poison|=bad;self.received+=1
        if terminal:self.committed=not self.poison
    @property
    def outstanding(self):return self.received<self.n

class WriteSlot:
    """One posted-write credit, older read completion, strict no-bypass order."""
    def __init__(self,read=False):self.read=read;self.pending=None;self.write_active=False;self.poison=False;self.events=[]
    def ready(self,ordinary=False,write=False,read=False):
        blocked=self.pending is not None or self.write_active
        return (not self.read and not blocked,
                not blocked and not ordinary,
                not self.read and not blocked and not ordinary and not write)
    def accept_write(self,n,tag):
        assert self.pending is None and not self.write_active
        self.pending=dict(n=n,tag=tag,data=[],bad=False);self.events.append(('accepted',tag))
    def data(self,value,last):
        p=self.pending;assert p is not None and len(p['data'])<p['n']
        p['bad']|=(last!=(len(p['data'])+1==p['n']));p['data'].append(value)
        self.events.append(('data',self.read))
    def read_done(self,error=False):self.read=False;self.poison|=error
    def dispatch(self):
        p=self.pending
        if p is None or len(p['data'])!=p['n'] or self.read:return None
        self.poison|=p['bad'];self.write_active=not self.poison
        return ('error' if self.poison else 'issue',p['tag'])
    def ack(self,tag):
        assert self.pending and self.pending['tag']==tag
        self.events.append(('ack',tag));self.pending=None;self.write_active=False

class Snapshot:
    def __init__(self):self.value=None
    def commit(self,base,m,k,bf16,whole=True):
        self.value=(base,m,k,k*(2 if bf16 else 4),bf16) if whole else None
    def matches(self,base,m,k,bf16,split=2560,tiles=False,write=None,flush=False):
        if self.value is None:return False
        b,rows,depth,stride,native=self.value
        end=b+rows*stride
        hitwrite=write is not None and write[0]<end and b<write[0]+write[1]
        return not flush and not hitwrite and self.value==(base,m,k,k*(2 if bf16 else 4),bf16) and k<=split and (not tiles or k<=1536)
    def mutation(self,write=None,tile=False,clear=False,flush=False):
        if self.value is None:return
        b,m,k,stride,_=self.value
        if clear or flush or (tile and k>1536) or (write and write[0]<b+m*stride and b<write[0]+write[1]):self.value=None

class Prefetch:
    def __init__(self,n=256,k=1536):self.n=n;self.k=k;self.ng=0;self.contexts=min(5,n//32);self.pref=None;self.half=None
    def start(self,all_read,response_pending=False,window=False,restoring=False,saving=False):
        if not all_read or response_pending or window or restoring or saving or self.ng+self.contexts*32>=self.n:return False
        target=self.ng+self.contexts*32
        self.pref=(target,min(5,(self.n-target)//32),min(128,self.k));return True
    def commit(self,ok=True):self.half=self.pref if ok else None
    def setup(self,written,read_outstanding=False):
        if written!=self.contexts or read_outstanding:return False
        assert self.pref is not None and self.half==self.pref
        self.ng,self.contexts,end=self.half;self.pref=None
        return end

class Mapping(unittest.TestCase):
    def check_legal(self,desc):
        for a,n in desc:
            self.assertEqual(a%64,0);self.assertTrue(1<=n<=16)
            self.assertLessEqual(a%1024+64*n,1024);self.assertLessEqual(a%4096+64*n,4096)
    def test_activation_shapes_types_and_chunks(self):
        for k in (32,128,1024,1536,2048,2560,8960):
            for bf in (False,True):
                for off in (0,64,960,4032):
                    for chunk in range(0,k,2560):
                        depth=min(k-chunk,2560);base=0x100000+off;width=2 if bf else 4
                        ds=list(a_spans(base,3,k,bf,chunk,depth));self.check_legal(ds)
                        expected=(base+(row*k+chunk)*width+i*64 for row in range(3) for i in range(depth*width//64))
                        self.assertEqual(list(expand(ds)),list(expected))
    def test_weight_context_tail_and_dtype(self):
        for n in (32,96,160,256,1536,2048,6144):
            for ng in range(0,n,160):
                ctx=min(5,(n-ng)//32)
                for bf in (False,True):
                    width=2 if bf else 4
                    for off in (0,64,960,4032):
                        base=0x400000+off;ds=list(b_spans(base,n,127,131,ng,ctx,bf));self.check_legal(ds)
                        expected=(base+(k*n+ng)*width+i*64 for k in range(127,131) for i in range(ctx*32*width//64))
                        self.assertEqual(list(expand(ds)),list(expected))
    def test_prefix_permutation_never_coalesced(self):
        addresses=[(((i>>1)&15)*16+((i>>5)&7)*2+(i&1))*64 for i in range(256)]
        self.assertEqual(len(set(addresses)),256)
        self.assertTrue(any(b!=a+64 for a,b in zip(addresses,addresses[1:])))
        source=(D/'source/TransposedDenseOwner.scala').read_text().split('/** Selected chunk-major extension;')[1]
        self.assertIn('Mux(readingPrefix,1.U,bRemaining)',source)
    def test_real_q_burst_count(self):
        # Actual frozen P0 bases: n0 mod1KiB=0, wq mod1KiB=64.
        a=list(a_spans(0x10b3d5400,128,1536,False));bcount=0;beats=0
        for ng in range(0,1536,160):
            ds=list(b_spans(0x100010040,1536,0,1536,ng,min(5,(1536-ng)//32),True))
            bcount+=len(ds);beats+=sum(n for _,n in ds)
        self.assertEqual((len(a),bcount,sum(n for _,n in a),beats),(768,18432,12288,73728))

class Transactions(unittest.TestCase):
    def test_good_with_backpressure_and_committed_last(self):
        for n in range(1,17):
            r=Receiver(n)
            for i in range(n):
                r.beat(i,i+1==n,ready=False);self.assertEqual(r.received,i)
                r.beat(i,i+1==n);self.assertEqual(r.committed,i+1==n)
            self.assertFalse(r.outstanding);self.assertEqual(r.staged,list(range(n)))
    def test_bad_tag_early_late_last_and_error_drain_by_expected_count(self):
        for n in (1,2,5,10,16):
            for fault in ('tag','early','late','error','nonfinite'):
                r=Receiver(n)
                for i in range(n):
                    badindex=0 if fault!='late' else n-1
                    last=i+1==n
                    if i==badindex and fault in ('early','late'):last=not last
                    r.beat(i,last,tag=7 if fault=='tag' and i==badindex else 9,error=fault=='error' and i==badindex,finite=not(fault=='nonfinite' and i==badindex))
                    self.assertEqual(r.outstanding,i+1<n)
                self.assertTrue(r.poison);self.assertFalse(r.committed)
    def test_write_credit_overlap_and_no_early_ack(self):
        s=WriteSlot(read=True);s.accept_write(2,99);s.data(7,False);s.data(8,True)
        self.assertIsNone(s.dispatch());self.assertTrue(all(e[1] for e in s.events if e[0]=='data'))
        self.assertEqual(s.ready(ordinary=True,read=True),(False,False,False))
        s.read_done();self.assertEqual(s.dispatch(),('issue',99));self.assertIsNotNone(s.pending)
        s.ack(99);self.assertIsNone(s.pending)
    def test_simultaneous_held_offers_have_one_priority_winner(self):
        for ordinary,write,read in itertools.product((False,True),repeat=3):
            s=WriteSlot();ready=s.ready(ordinary,write,read)
            fires=[ordinary and ready[0],write and ready[1],read and ready[2]]
            self.assertEqual(sum(fires),int(ordinary or write or read))
    def test_queued_store_poison_drains_own_tag_without_issue(self):
        for read_error in (False,True):
            s=WriteSlot(read=True);s.accept_write(3,82)
            for i in range(3):s.data(i,True if i==0 else i==2)
            self.assertIsNone(s.dispatch());s.read_done(read_error)
            self.assertEqual(s.dispatch(),('error',82));self.assertFalse(s.write_active);s.ack(82)
    def test_one_posted_write_credit_only(self):
        s=WriteSlot();s.accept_write(1,1)
        with self.assertRaises(AssertionError):s.accept_write(1,2)
        s.data(5,True);self.assertEqual(s.dispatch(),('issue',1))
        with self.assertRaises(AssertionError):s.ack(2)

class ResidencyAndSchedule(unittest.TestCase):
    def test_profile_snapshot_metadata_and_fp32_storage(self):
        for profile,k,bf in ((0,1536,False),(1,1024,True),(2,1024,True),(3,2048,True),(4,2048,True)):
            x=Snapshot();x.commit(0x100000,128,k,bf)
            self.assertTrue(x.matches(0x100000,128,k,bf))
            self.assertFalse(x.matches(0x100000,128,k,not bf))
            self.assertFalse(x.matches(0x100000,127,k,bf))
            self.assertFalse(x.matches(0x100040,128,k,bf))
            self.assertFalse(x.matches(0x100000,128,k,bf,flush=True))
    def test_snoop_endpoint_alias_and_same_cycle_reuse_veto(self):
        x=Snapshot();x.commit(1024,128,1536,False);end=1024+128*1536*4
        for a,n,hit in ((960,64,False),(960,128,True),(1024,64,True),(end-64,64,True),(end,64,False)):
            self.assertEqual(x.matches(1024,128,1536,False,write=(a,n)),not hit)
    def test_p0_window_identity_is_reminted_not_reused(self):
        x=Snapshot();x.commit(0x100000,128,1536,False)
        old_identity=11;new_identity=24
        x.mutation(tile=True);self.assertTrue(x.matches(0x100000,128,1536,False,tiles=True))
        # Physical snapshot may hit; explicit old identity lease still cannot.
        self.assertNotEqual(old_identity,new_identity)
        x.mutation(write=(0x100000,64));self.assertFalse(x.matches(0x100000,128,1536,False))
    def test_tile_1536_boundary_and_h2048_overlap(self):
        for k,preserved in ((1536,True),(2048,False),(2560,False)):
            x=Snapshot();x.commit(1024,128,k,True);x.mutation(tile=True)
            self.assertEqual(x.value is not None,preserved)
    def test_partial_k_never_full_snapshot(self):
        x=Snapshot();x.commit(0,128,8960,False,whole=False);self.assertFalse(x.matches(0,128,8960,False))
    def test_next_n_prefetch_requires_last_sram_return(self):
        for all_read,pending in itertools.product((False,True),repeat=2):
            p=Prefetch();self.assertEqual(p.start(all_read,pending),all_read and not pending)
    def test_prefetch_old_writeback_and_tail_context_identity(self):
        p=Prefetch();self.assertTrue(p.start(True));self.assertEqual(p.pref,(160,3,128))
        self.assertEqual((p.ng,p.contexts),(0,5));p.commit()
        self.assertFalse(p.setup(4));self.assertFalse(p.setup(5,read_outstanding=True))
        self.assertEqual(p.setup(5),128);self.assertEqual((p.ng,p.contexts),(160,3))
        self.assertFalse(p.start(True))
    def test_window_prefix_and_failed_preload_cannot_reuse(self):
        for field in ('window','restoring','saving'):
            p=Prefetch();self.assertFalse(p.start(True,**{field:True}))
        p=Prefetch(k=32);self.assertTrue(p.start(True));p.commit(False)
        with self.assertRaises(AssertionError):p.setup(5)
    def test_actual_overlap_window_exists_in_pure_schedule(self):
        p=Prefetch();self.assertTrue(p.start(True));s=WriteSlot(read=True)
        s.accept_write(2,1);s.data(1,False);s.data(2,True)
        self.assertTrue(p.pref is not None and s.read and s.pending is not None)
        s.read_done();p.commit();s.dispatch();self.assertFalse(p.setup(0));s.ack(1)

# Exact BF16 operand conversion / ordered payload replay only.
# The original retained FMA and accumulator arithmetic are NOT modeled here.
def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]
def val(u):return struct.unpack('<f',struct.pack('<I',u))[0]
def f32(f):return val(bits(f))
def bf16(u):return (u+0x7fff+((u>>16)&1))>>16
class Arithmetic(unittest.TestCase):
    def test_operand_conversion_and_order_preserved_by_burst_partition(self):
        rng=random.Random(5719)
        for native in (False,True):
            for k in (16,32,128):
                original=[bits(f32(rng.uniform(-3,3))) for _ in range(k)]
                converted=[(u>>16) if native else bf16(u) for u in original]
                for burst in (1,2,5,10,16):
                    order=list(itertools.chain.from_iterable(range(i,min(k,i+burst)) for i in range(0,k,burst)))
                    self.assertEqual(order,list(range(k)))
                    self.assertEqual([converted[i]for i in order],converted)
                    self.assertEqual([original[i]for i in order],original)
    def test_bf16_ties_and_unchanged_fp32_source_bits(self):
        for u,want in ((0x3f808000,0x3f80),(0x3f818000,0x3f82),(0xbf808000,0xbf80),(0x7f7f8000,0x7f80)):
            before=u;self.assertEqual(bf16(u),want);self.assertEqual(u,before)

class CoherentExplicitReuse(unittest.TestCase):
    def test_matching_physical_snapshot_does_not_authorize_old_window_identity(self):
        physical=Snapshot();physical.commit(0x100000,128,1536,False)
        logical_identity=17
        self.assertTrue(physical.matches(0x100000,128,1536,False))
        self.assertFalse(logical_identity==18)
    def test_accepted_alias_write_and_launch_flush_revoke_explicit_lease(self):
        for flush,write in ((True,None),(False,(0x100000,64))):
            logical=Snapshot();logical.commit(0x100000,128,1536,False)
            self.assertFalse(logical.matches(0x100000,128,1536,False,write=write,flush=flush))
            logical.mutation(write=write,flush=flush);self.assertIsNone(logical.value)
    def test_real_owner_vetoes_explicit_reuse_and_revokes_logical_lease(self):
        s=(D/'source/TransposedDenseOwner.scala').read_text()
        self.assertIn('val reuseOK=aLeaseValid.get && !w.invalidateLease && !windowCoherenceInvalid',s)
        self.assertIn('when(w.invalidateLease || windowCoherenceInvalid || io.job.fire',s)
        self.assertIn('val tileMutation=banks.io.tiles.map',s)

class SourceIntegration(unittest.TestCase):
    def test_real_selected_control_has_required_fences(self):
        s=(D/'source/TransposedDenseOwner.scala').read_text().split('/** Selected chunk-major extension;')[1]
        for fragment in ('val readCredit=Module(new DenseReadCommitCredit)','val responseBad=readCredit.io.bad || !sourceFinite','readCredit.io.returned.valid:=io.burstResponse.fire',
                         'when(prefetchNext){assert(reuseB && !burstOutstanding && loadState===loadIdle)}',
                         'halfN(loadHalf):=loadN','!banks.io.response.valid && !prefetchNext','val freshSnapshot=',
                         'aLease.get.identity:=r.identity','ordinaryAStride.get===stride','c.flush || writeHits || tilePoison'):
            self.assertIn(fragment,s)
    def test_real_adapter_no_simultaneous_offer_deadlock_and_no_early_store_ack(self):
        s=(D/'source/IdmaWeightBurst.scala').read_text()
        normal=next(l for l in s.splitlines() if 'io.request.ready :=' in l)
        self.assertNotIn('writeOffered',normal);self.assertIn('!writeBlocked',normal)
        self.assertIn('io.streamWriteResponse.get.valid:=state===reply && writeBurst',s)
        self.assertIn('stagedWrite.get && stagedFull.get && (state===idle || state===locked)',s)
        self.assertIn('!writeBlocked && !io.resetRequired',s)
    def test_internal_snoop_and_expected_debt_on_selected_path(self):
        top=(D/'source/HostBlockTopV4.scala').read_text();owner=(D/'source/QwenOwnerProtocol.scala').read_text()
        self.assertIn('enableActivationResidency=enableTransposedDown',top)
        self.assertIn('hub.io.memory.fire && hub.io.memory.bits.write',top)
        self.assertIn('owner.io.writeRequest.map(_.fire)',top)
        self.assertIn('readRemaining:=dense.burst.bits.beats',owner)
        self.assertIn('when(readRemaining===1.U){readDebt:=false.B}',owner)

if __name__=='__main__':unittest.main(verbosity=2)
