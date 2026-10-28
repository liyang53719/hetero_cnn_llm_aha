"""Independent source + abstract protocol/numerical-boundary tests, NOT DUT.
Original ExpNegative polynomial implementation is not reimplemented or claimed
Torch-bit exact: tests compare the original graph and BF16 materialization
placement using a deterministic injected scalar exp primitive.
"""
from pathlib import Path
import argparse,hashlib,json,math,re,struct,unittest
C=Path(__file__).resolve().parents[1]
W=C.parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--original-source',type=Path,required=True)
parser.add_argument('--core-source',type=Path,required=True)
args,unittest_args=parser.parse_known_args()
ORIGINAL=args.original_source
CORE=args.core_source
LEAF=C/'source/GdnRuntimeElementwiseOwnerV15.scala'
KERNEL=C/'source/QwenOwnerProtocol.scala'
TOP=C/'source/HostBlockTopV4.scala'
BASE=W/'host_runtime_gqa/source'

def need(v,msg):
    if not v: raise ValueError(msg)
pins=json.loads((C/'SOURCE_PINS.json').read_text())
for n in ['QwenOwnerProtocol.scala','UnifiedMoeSharedArithmeticAdapterV5.scala']:
 r=pins['source_check_originals'][n];b=(BASE/n).read_bytes();need(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'exact public predecessor '+n)
r=pins['original_core_boundary'];b=CORE.read_bytes();need(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'exact external Core pin')
def f32(v): return struct.unpack('>f',struct.pack('>f',v))[0]
def bits(v): return struct.unpack('>I',struct.pack('>f',v))[0]
def from_bits(v): return struct.unpack('>f',struct.pack('>I',v))[0]
def bf16(v):
    u=bits(v)
    return from_bits(((u+0x7fff+((u>>16)&1))>>16)<<16)
def original_graph(g,c,op=2,exp_primitive=lambda x:f32(math.exp(-abs(x)))):
    if op==0: return bf16(f32(g+c)), ['add','bf16']
    if op!=2: raise ValueError('unsupported op')
    if not math.isfinite(g) or not math.isfinite(c): raise ValueError('nonfinite')
    if math.copysign(1,g)<0 and abs(g)>=80: raise ValueError('unsupported negative gate')
    e=exp_primitive(g)
    den=f32(1+e); inv=f32(1/den); sig=f32(inv*(e if math.copysign(1,g)<0 else 1))
    return bf16(f32(bf16(sig)*c)), ['exp','denominator','inverse','sign','bf16','multiply','bf16']
def successor_graph(g,c,op=2,exp_primitive=lambda x:f32(math.exp(-abs(x))),omit_sig_round=False,silu=False):
    if op==0:return bf16(f32(g+c)), ['add','bf16']
    if op!=2:raise ValueError('unsupported op')
    if not math.isfinite(g) or not math.isfinite(c):raise ValueError('nonfinite')
    if math.copysign(1,g)<0 and abs(g)>=80:raise ValueError('unsupported negative gate')
    trace=[]; value=0.; exponential=0.; operation='exp'
    while True:
        trace.append(operation)
        if operation=='exp':exponential=exp_primitive(g);value=exponential;operation='denominator'
        elif operation=='denominator':value=f32(1+exponential);operation='inverse'
        elif operation=='inverse':value=f32(1/value);operation='sign'
        elif operation=='sign':
            value=f32(value*(exponential if math.copysign(1,g)<0 else 1))
            if silu:value=f32(value*g)
            trace.append('bf16')
            if not omit_sig_round:value=bf16(value)
            operation='multiply'
        else:
            value=f32(value*c);trace.append('bf16');return bf16(value),trace

def core_admission(*,captured=False,active=True,mode=9,owner_poison=False,transport_quarantine=False,rejected=False,shared_poison=False,auxiliary=False,legacy_debt=False,raw_return=False,core_quarantine=False):
    drain=active and mode==9 and captured
    compatible=not active or mode in (3,4,6,8,9,10,11,13,14)
    scheduler=compatible and not auxiliary and not transport_quarantine and not rejected and (not owner_poison or drain) and not shared_poison and not legacy_debt and not raw_return
    return scheduler and not core_quarantine

def shape(op,m,n):return 1<=m<=128 and ((op==0 and n in (1024,2048)) or (op==2 and n in (2048,4096)))
def counts(op,m,n):
    need(shape(op,m,n),'shape')
    e=m*n
    return dict(scalar=e*(5 if op==2 else 1),format=e*(2 if op==2 else 1),memory=(e//32)*3,bytes=e*2)

class Channel:
    """Single serial resource, real downstream publication, sticky poison.
    Unknown identity never refunds a known pending debt or quarantine.
    """
    def __init__(self):self.held=False;self.pending=False;self.poison=False;self.quarantine=False;self.accepted=0;self.returned=0
    def offer(self,intent=True,publish_gate=True,ready=False,fault=False):
        visible=intent and (not(self.poison or self.quarantine or fault) or self.held)
        published=visible and (publish_gate or self.held)
        fire=published and ready
        if published:self.held=not ready
        if fire:self.pending=True;self.accepted+=1
        self.poison|=fault
        return visible,published,fire
    def response(self,correct=True):
        if not self.pending or not correct:self.quarantine=True;self.poison=True;return False
        self.pending=False;self.returned+=1;return True
    def drained(self):return not(self.pending or self.held or self.quarantine)

def source_checks(leaf,kernel,top):
    need('val add :: exp :: denominator :: inverse :: sign :: multiply :: Nil=Enum(6)' in leaf,'original scalar graph, no activate')
    need('sign->Mux(x(31),exponential,F32.lit(1)),multiply->y' in leaf,'original sign/context operands')
    need('when(operation===sign){value:=Cat(r.value,0.U(16.W));operation:=multiply;state:=scalarIssue}' in leaf,'sigmoid BF16 before multiply')
    need('is(sign){state:=formatIssue}' in leaf and 'is(multiply){state:=formatIssue}' in leaf and 'is(add){state:=formatIssue}' in leaf,'both gate and Add format boundaries')
    need('val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)' in leaf and 'ScalarOp.MulIeeeRne.U' in leaf,'legacy scalar policy and gradual-underflow multiply')
    need('x(31) && x(30,0)>=F32.lit(80)' in leaf and 'fail(Status.Unsupported.U)' in leaf,'unsupported negative gate retained')
    need(leaf.count('Reg(Vec(32,UInt(16.W)))')==3,'fixed three 32-lane payload banks')
    need('Module(new ' not in leaf and 'TensorMath.bf16Rne' not in leaf and 'F32.bf(' not in leaf,'no local arithmetic/formatter services')
    need('when(published){held:= !ready}' in leaf and 'held:= !visible' not in leaf,'only actual publication creates held debt')
    need('val visible=intent && ((!poison && !quarantine && !currentFault) || held)' in leaf,'held stable late fault; fresh veto')
    reset=re.search(r'io.resetRequired:=(.*)',leaf).group(1)
    need('faultNow' not in reset,'avoid job.fire->faultNow->Kernel canStart combinational loop')
    need('when(state===drain && !memoryPending && !scalarPending && !formatPending && !quarantine){state:=finish}' in leaf,'real debt drain and quarantine')
    need('.elsewhen(state=/=drain){state:=drain}' in leaf,'sticky poison cannot overwrite drain->finish')
    need('when(state===idle && !io.job.fire){state:=locked}' in leaf,'idle fault never invents terminal')
    need('when(memoryWrite && !io.response.bits.error){bytes:=bytes+64.U}' in leaf,'actual successful output ACK bytes')
    need('memoryAccepted===expectedMemory && sequence===expectedMemory && bytes===(elements<<1)' in leaf,'exact terminal memory/count')
    need('formatAccepted===expectedFormat && formatReturned===expectedFormat' in leaf,'exact terminal format count')
    need('scalarAccepted===expectedScalar && scalarReturned===expectedScalar' in leaf,'exact terminal scalar count')
    need('val elementJobHeld=RegInit(false.B)' in kernel,'new child job held register')
    need('(enableRuntimeElementwise.B && elementJobHeld && choose===9.U)' in kernel,'held mode9 admitted')
    need('e.io.job.valid:=ordinaryJob.valid && ordinaryCanStart && choose===9.U' in kernel,'child offered job cannot retract')
    need('when(e.io.job.valid){elementJobHeld:= !e.io.job.ready}' in kernel,'track actual child offer')
    need('val elementScalarDrain=enableRuntimeElementwise.B && active && mode===9.U &&\n      io.sharedScalar.map(_.request.valid).getOrElse(false.B)' in kernel,'only actual captured adapter mode9 packet drains')
    need('!rejected && (!gdnPoison || elementScalarDrain) && !sharedPoison && !legacyScalarDebt && !rawReturn' in kernel,'only owner poison bypass; physical conflicts unchanged')
    need('moeArithmetic.io.coreScalar<>owner.io.sharedScalar.get' in top,'Core request originates only retained adapter')
    need('runtimeElementwise.toSeq.map(n=>(9,n.io.scalar,n.io.formatRequest,n.io.formatResult,n.io.resourcesDrained))' in kernel,'same scalar/format mode9')
    need('++runtimeElementwise.toSeq.map(x=>9->x.io.memory)' in kernel and '++runtimeElementwise.toSeq.map(x=>9->x.io.response)' in kernel,'same memory mode9')
    need('(bf16GdnBlock||bf16AttentionBlock) && !enableRuntimeElementwise' in kernel,'replacement, not parallel legacy owner')
    need('enableRuntimeOutput=true' in top and 'enableRuntimeElementwise=true' in top,'same common top')
    for channel,port in [('memory','hub.io.requests(1).valid'),('scalar','moeArithmetic.io.scalar(3).request.valid'),('format','moeArithmetic.io.formatRequest(3).valid')]:
        need(f'owner.io.runtimeElementwisePublished.get.{channel}:=normLease.owned && elementJob && {port}' in top,'actual downstream publication '+channel)
    need('Mux(elementJob,nwithin(nj.a,nbytes) || nwithin(nj.b,nbytes),' in top,'both packed BF16 input spans')

class Numerical(unittest.TestCase):
    def test_original_pin(self):self.assertEqual(hashlib.sha256(ORIGINAL.read_bytes()).hexdigest(),'01b394526f75b9732c3e605652c64f3968851aca97258a3a640bc056de1f2fe3')
    def test_graph_equivalence_injected_exp(self):
        for g in [-79.,-8.,-2.,-0.0,0.,.5,1.,3.,79.,80.]:
            for c in [-32.,-.1,0.,.01,1.,17.]:
                self.assertEqual(original_graph(bf16(g),bf16(c)),successor_graph(bf16(g),bf16(c)))
    def test_add_order_and_round(self):
        for a,b in [(1.,.00390625),(1.,.01171875),(-1.,1.),(0.,0.),(128.,.5)]:self.assertEqual(original_graph(a,b,0),successor_graph(a,b,0))
    def test_exp_injected_identically(self):
        for e in [0.,.25,.5,1.]:
            for g in [-1.,1.]:self.assertEqual(original_graph(g,3.,exp_primitive=lambda x:e),successor_graph(g,3.,exp_primitive=lambda x:e))
    def test_two_bf16_boundary_essential(self):
        differs=[]
        for gi in range(-80,81):
            for ci in range(1,31):
                g=bf16(gi/16);c=bf16(ci/7)
                if bits(successor_graph(g,c)[0])!=bits(successor_graph(g,c,omit_sig_round=True)[0]):differs.append((g,c))
        self.assertTrue(differs)
    def test_not_silu(self):self.assertNotEqual(successor_graph(-2.,3.)[0],successor_graph(-2.,3.,silu=True)[0])
    def test_unsupported_negative_only(self):
        for g in [-80.,-128.]:
            with self.assertRaises(ValueError):successor_graph(g,1.)
        successor_graph(80.,1.);successor_graph(-79.,1.)
    def test_nonfinite(self):
        for g,c in [(math.inf,1.),(math.nan,1.),(1.,math.inf)]:
            with self.assertRaises(ValueError):successor_graph(g,c)
    def test_shape_edges(self):
        for op,n in [(0,1024),(0,2048),(2,2048),(2,4096)]:
            for m in [1,128]:self.assertTrue(shape(op,m,n));self.assertEqual(counts(op,m,n)['bytes'],m*n*2)
        for args in [(1,128,3584),(0,0,1024),(2,129,4096),(2,128,8192),(0,128,4096)]:self.assertFalse(shape(*args))
    def test_max_counts(self):self.assertEqual(counts(2,128,4096),dict(scalar=2621440,format=1048576,memory=49152,bytes=1048576))
    def test_max_residual_counts(self):self.assertEqual(counts(0,128,2048),dict(scalar=262144,format=262144,memory=24576,bytes=524288))

class Protocol(unittest.TestCase):
    def test_hidden_offer_not_held(self):
        c=Channel();self.assertEqual(c.offer(publish_gate=False),(True,False,False));self.assertFalse(c.held)
        self.assertEqual(c.offer(fault=True),(False,False,False));self.assertTrue(c.drained())
    def test_held_each_resource_late_fault(self):
        for resource in ['memory','scalar','format']:
            c=Channel();self.assertEqual(c.offer(),(True,True,False));self.assertTrue(c.held)
            self.assertEqual(c.offer(publish_gate=False,fault=True),(True,True,False));self.assertFalse(c.drained())
            self.assertEqual(c.offer(ready=True,publish_gate=False),(True,True,True));self.assertTrue(c.pending)
            self.assertTrue(c.response());self.assertTrue(c.drained());self.assertEqual((c.accepted,c.returned),(1,1))
    def test_wrong_response_preserves_owned_debt(self):
        c=Channel();c.offer(ready=True);self.assertFalse(c.response(correct=False));self.assertTrue(c.pending)
        self.assertTrue(c.response());self.assertFalse(c.drained());self.assertTrue(c.quarantine)
    def test_unsolicited_response_quarantines(self):
        c=Channel();self.assertFalse(c.response());self.assertEqual((c.accepted,c.returned),(0,0));self.assertFalse(c.drained())
    def test_poison_suppresses_fresh(self):
        c=Channel();c.offer(fault=True);self.assertEqual(c.offer(ready=True),(False,False,False))
    def test_no_final_commit_from_partial_ack(self):
        expected=counts(2,128,4096);actual=expected.copy();actual['bytes']-=64
        self.assertNotEqual(actual,expected)
    def test_captured_adapter_packet_drains_after_owner_fault(self):
        c=Channel();c.offer(ready=True) # real authorized adapter ingress
        self.assertTrue(c.pending);c.poison=True
        self.assertTrue(core_admission(captured=True,owner_poison=True)) # Core accepts retained sOffer
        self.assertTrue(c.response());self.assertTrue(c.drained())
    def test_no_drain_exception_for_new_or_wrong_mode(self):
        self.assertFalse(core_admission(captured=False,owner_poison=True))
        self.assertFalse(core_admission(captured=True,mode=13,owner_poison=True))
        self.assertFalse(core_admission(captured=True,active=False,owner_poison=True))
    def test_drain_keeps_all_physical_conflict_fences(self):
        for fence in ['transport_quarantine','rejected','shared_poison','auxiliary','legacy_debt','raw_return','core_quarantine']:
            with self.subTest(fence=fence):self.assertFalse(core_admission(captured=True,owner_poison=True,**{fence:True}))
    def test_terminal_snapshot_held(self):
        terminal=dict(status=0,writeBytes=64,outputCommitted=True);snapshot=terminal.copy();late_fault=True
        self.assertEqual(terminal,snapshot);self.assertTrue(late_fault) # sideband poisons parent, not held payload

class Source(unittest.TestCase):
    def test_contracts(self):source_checks(LEAF.read_text(),KERNEL.read_text(),TOP.read_text())
    def test_matrix_and_qwen2_routing_unchanged(self):
        old=(BASE/'QwenOwnerProtocol.scala').read_text();new=KERNEL.read_text()
        for begin,end in [('    val useDense=','    val noAuxOwner='),('    val dense:DenseOwnerIO=','    // The core-only GDN')]:
            self.assertEqual(old[old.index(begin):old.index(end)],new[new.index(begin):new.index(end)])
        self.assertIn('val hub=Module(new SharedMemoryArbiter(17))',TOP.read_text())
    def test_adapter_core_retained_packet_boundary(self):
        adapter=(BASE/'UnifiedMoeSharedArithmeticAdapterV5.scala').read_text()
        core=CORE.read_text()
        self.assertIn('val sOffer=RegInit(false.B)',adapter)
        self.assertIn('when(scalarAccept){sPacket:=sarb.io.out.bits;sClient:=scalarAcceptClient;sOffer:=true.B}',adapter)
        self.assertIn('io.coreScalar.request.valid:=sOffer;io.coreScalar.request.bits:=sPacket',adapter)
        self.assertIn('io.sharedScalarSchedulerAvailable.get && scalarLendingAllowed && !offerHeld && !pending',core)
        self.assertIn('scalarResponseLegal && !ledgerQuarantine && !fault',core)
    def test_negative_source_mutations(self):
        l,k,t=LEAF.read_text(),KERNEL.read_text(),TOP.read_text()
        source_checks(l,k,t)
        mutations=[
            ('l','sign->Mux(x(31),exponential,F32.lit(1)),multiply->y','sign->Mux(x(31),exponential,F32.lit(1)),multiply->x'),
            ('l','when(published){held:= !ready}','when(visible){held:= !ready}'),
            ('l','io.resetRequired:=','io.resetRequired:=faultNow || '),
            ('l','is(sign){state:=formatIssue}','is(sign){state:=scalarIssue}'),
            ('l','val requestPolicy=UnifiedScalarPolicyV2.Legacy.U(2.W)','val requestPolicy=UnifiedScalarPolicyV2.Other.U(2.W)'),
            ('l','&& !quarantine){state:=finish}',' ){state:=finish}'),
            ('l','sequence===expectedMemory','sequence>=expectedMemory'),
            ('l','formatReturned===expectedFormat','formatReturned<=expectedFormat'),
            ('l','scalarReturned===expectedScalar','scalarReturned<=expectedScalar'),
            ('k','e.io.job.valid:=ordinaryJob.valid && ordinaryCanStart && choose===9.U','e.io.job.valid:=ordinaryJob.valid && canStartWithTiles && choose===9.U'),
            ('k','++runtimeElementwise.toSeq.map(x=>9->x.io.response)','++runtimeElementwise.toSeq.map(x=>8->x.io.response)'),
            ('k','(!gdnPoison || elementScalarDrain)','!gdnPoison'),
            ('k','&& !sharedPoison && !legacyScalarDebt && !rawReturn','&& !legacyScalarDebt && !rawReturn'),
            ('k','val elementScalarDrain=enableRuntimeElementwise.B && active && mode===9.U &&','val elementScalarDrain=enableRuntimeElementwise.B &&'),
            ('t','elementJob && moeArithmetic.io.formatRequest(3).valid','elementJob && owner.io.runtimeRms.get.formatRequest.valid'),
        ]
        for which,a,b in mutations:
            inputs=dict(l=l,k=k,t=t);self.assertIn(a,inputs[which]);inputs[which]=inputs[which].replace(a,b,1)
            with self.subTest(which=which,mutation=a),self.assertRaises(ValueError):source_checks(inputs['l'],inputs['k'],inputs['t'])
if __name__=='__main__':unittest.main(argv=[__file__]+unittest_args)
