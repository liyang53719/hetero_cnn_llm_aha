"""Finite four-phase coordinator tests; child calls and numerical imports are mocked."""
import argparse,contextlib,copy,hashlib,io,json,os,stat,sys,tempfile,time,types,unittest
from pathlib import Path
from unittest import mock
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--repo',type=Path,required=True);args,rest=ap.parse_known_args()
RUN_PIN=(19370,'2ac4c215a6d321df2eeb48384f974b041c1e762027a4b47c37a6527468d6e279')
def checked(p,pin):
    if not p.is_absolute() or '..' in p.parts or any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('path')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        before=os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size!=pin[0]:raise ValueError('size')
        raw=f.read(pin[0]+1);after=os.fstat(f.fileno())
    sig=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
    if sig(before)!=sig(after) or sig(before)!=sig(p.stat(follow_symlinks=False)) or (len(raw),hashlib.sha256(raw).hexdigest())!=pin:raise ValueError('pin')
    return raw
def module(p,pin):
    raw=checked(p,pin);m=types.ModuleType('_cold_'+p.stem);m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(raw,str(p),'exec',dont_inherit=True),m.__dict__);return m
def audit(event,values):
    if event.startswith(('socket.','subprocess.','ctypes.dlopen')) or event in ('os.system','os.fork','os.posix_spawn','os.exec'):raise RuntimeError('cold external activity forbidden')
sys.addaudithook(audit)
N=module(args.source/'run.py',RUN_PIN);PINS=N.source_map(args.repo);A,P,S,C=N.modules(args.repo,PINS)

REFPINS=C.load_pins(args.repo/N.REFERENCE/'PINS.json')
ENTRY=N.load(args.repo,PINS,N.PREFIX+'stage_entry.py')
def private_receipt(kind='match'):
    r={'schema':1,'status':'PASS_FROZEN_N0_EXACT','code':None,'stage':'COMPLETE','scope':'FROZEN_M128_N0_REFERENCE_ONLY','rtl_executed':False,'fullblock_executed':False,'reference_accepted':True,'python_profile':'historical','source_identities':REFPINS['sources'],'input_identities':REFPINS['raw2'],'runtime_requirements':REFPINS['runtime_requirements'],'observed_runtime':{'capability':'AVX512'}}
    native={k:{a:v[a] for a in ('bytes','sha256')} for k,v in REFPINS['runtime_native_files'].items() if k!='python'};native['python']={k:REFPINS['python_profiles']['historical'][k] for k in ('bytes','sha256')};r.update(runtime_before=native,runtime_after=copy.deepcopy(native))
    r['output']={'native':{'bytes':C.BF16_BYTES,'sha256':C.BF16_SHA256},'fp32le':{'bytes':C.F32_BYTES,'sha256':C.F32_SHA256},'native_exact':True,'fp32le_exact':True,'accepted':True}
    if kind=='mismatch':r.update(status='REFERENCE_MISMATCH',code='HASH_MISMATCH',stage='POSTFLIGHT',reference_accepted=False);r['output'].update(native_exact=False,accepted=False)
    elif kind=='gate':r.update(status='NOT_COMPLETED',code='DISPATCH',stage='RUNTIME_IMPORT',reference_accepted=False);r['observed_runtime']['capability']='AVX2';r.pop('output');r.pop('runtime_after')
    return r
def observation(kind='match'):return N.project_receipt(private_receipt(kind),REFPINS,C)
RAW2={'schema':1,'status':'LOCAL_RAW2_IDENTITY_ONLY','origin':'EXISTING_PINNED_RAW2_READ_ONLY','inputs':{k:{a:v[a] for a in ('bytes','sha256')} for k,v in REFPINS['raw2'].items()},'network_acquired_here':False,'reference_executed':False,'dut_executed':False}

def diag(code):
    d=S.diagnostic_defaults();d.update(exit_code=code,final_reap_signal=None,receipt_timed_out=False,cleanup_confirmed=True,waitid_code=1,waitid_status=code,kill_attempted=True,kill_result='SIGNAL_SENT_BEFORE_REAP',native_record_status='PASS' if code==0 else 'FAIL',failure_code='NONE' if code==0 else 'CHILD_EXIT_NONZERO',failure_boundary='NONE' if code==0 else 'NATIVE_SUPERVISION',child_user_cpu_seconds=.1,child_system_cpu_seconds=.1,child_maxrss_kib_cumulative=1000);return d
RSS={'sampled_leader_max_kib':1000,'limit_kib':1572864,'os_hard_limit':False,'includes_descendants':False}

class Execute(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='dispatch-cold-',dir='/tmp');self.addCleanup(t.cleanup);self.out=Path(t.name)/'out';self.calls=[];self.kind='match';self.fail_at=None;self.native_error=ValueError('PRIVATE_SECRET_MUST_NOT_ESCAPE');self.receipt_mode='valid'
        self.runtime=types.SimpleNamespace(source_preflight=mock.Mock(),require_current_python=mock.Mock(),install_argv=mock.Mock(return_value=['/fixed/offline-pip']),observe_installed_tree=mock.Mock())
        self.raw2=types.SimpleNamespace(raw2_receipt=mock.Mock(return_value=copy.deepcopy(RAW2)),SAFE_MARKERS=ENTRY.SAFE_MARKERS)
        self.support=types.SimpleNamespace(deadline_ready=mock.Mock(),fixed_support=mock.Mock(return_value=(None,None,{})),interrupted=S.interrupted,diagnostic_defaults=S.diagnostic_defaults,run_phase=self.phase)
        self.patch(N,'source_map',return_value=PINS);self.patch(N,'modules',return_value=(A,P,self.support,C))
        self.patch(N,'load',side_effect=lambda repo,pins,name:self.runtime if name==N.RUNTIME else self.raw2 if name==N.PREFIX+'stage_entry.py' else NATIVE_LOAD(repo,pins,name))
        self.patch(N.signal,'signal',return_value=S.interrupted);self.patch(N.signal,'setitimer');self.patch(P,'rss_observation',return_value=dict(RSS))
        self.original_read=N.read
        self.patch(N,'read',side_effect=lambda p,*a,**kw:b'mocked exact FP32 file' if Path(p).name=='n0.f32le' else self.original_read(p,*a,**kw))
    def patch(self,obj,name,**kw):
        p=mock.patch.object(obj,name,**kw);m=p.start();self.addCleanup(p.stop);return m
    def phase(self,base,plan,name,argv,cwd,evidence,env,bound,stop,owner,diagnostics):
        self.calls.append((name,argv,env,bound,stop));evidence.mkdir();(evidence/'native.log').write_text('PRIVATE_SECRET_MUST_NOT_ESCAPE\n')
        index=N.STAGES.index(name);code=1 if index==self.fail_at or index==3 and self.kind!='match' else 0
        diagnostics.update(diag(code))
        if index==2:
            (self.out/'raw2').mkdir();(self.out/'raw2'/'RECEIPT.json').write_text(json.dumps(RAW2))
        if index==3 and self.receipt_mode!='missing':
            (self.out/'reference').mkdir()
            raw=json.dumps(private_receipt(self.kind)) if self.receipt_mode=='valid' else '{'
            (self.out/'reference'/'RECEIPT.json').write_text(raw)
        if code:raise self.native_error
        return {'exit_code':0,'cleanup_confirmed':True},b'',{}
    def run_job(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):result=N.execute(args.repo,self.out,time.monotonic()+590.,Path('/synthetic/embedding'),Path('/synthetic/gamma'))
        objects={n:N.decode((self.out/'evidence'/n).read_bytes()) for n in N.EVIDENCE};self.assertNotIn('PRIVATE_SECRET',json.dumps(objects));return result,objects
    def test_match_four_stages_candidate_only(self):
        r,o=self.run_job();self.assertEqual(r,0);self.assertEqual(o['summary.json']['status'],'LOCAL_REFERENCE_EXACT_ONLY');self.assertEqual([x[0] for x in self.calls],list(N.STAGES));self.assertTrue(o['summary.json']['scope']['local_reference_qualified']);self.assertFalse(o['summary.json']['scope']['baseline_adopted'])
        self.assertEqual([x[3]['total_seconds'] for x in self.calls],[180,120,30,120]);self.assertEqual([x[3]['as_bytes'] for x in self.calls],[512*N.MIB,2*N.GIB,256*N.MIB,8*N.GIB]);self.assertEqual(self.calls[-1][2]['OMP_NUM_THREADS'],'4');self.assertEqual(self.calls[-1][2]['OPENBLAS_NUM_THREADS'],'1')
        self.assertNotIn('ATEN_CPU_CAPABILITY',self.calls[-1][2]);self.assertNotIn('GH_TOKEN',self.calls[-1][2]);self.assertEqual(self.runtime.install_argv.call_count,1);self.assertEqual(self.raw2.raw2_receipt.call_count,2)
    def test_mismatch_native_one_preserved(self):
        self.kind='mismatch';r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['status'],'INCOMPLETE');self.assertEqual(o['stage_exits.json']['stages'][-1]['exit_code'],1)
    def test_unknown_capability_gate_stops_candidate(self):
        self.kind='gate';r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['status'],'INCOMPLETE');self.assertEqual(o['summary.json']['reference']['observed_capability'],'AVX2')
    def test_each_earlier_native_first_failure_stops(self):
        for index in range(3):
            with self.subTest(index=index):
                self.out=self.out.with_name('out'+str(index));self.fail_at=index;self.calls=[];r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(len(self.calls),index+1);self.assertEqual(o['summary.json']['observation_state'],'NOT_COLLECTED')
    def test_runtime_tree_parent_failure_label(self):
        self.runtime.observe_installed_tree.side_effect=ValueError('PRIVATE_SECRET');r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['contract_failure']['boundary'],'RUNTIME_TREE');self.assertEqual(len(self.calls),2)
    def test_raw2_receipt_parent_failure_label(self):
        self.raw2.raw2_receipt.side_effect=ValueError('PRIVATE_SECRET');r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['contract_failure']['boundary'],'RAW2_RECEIPT');self.assertEqual(len(self.calls),3)
    def test_missing_candidate_receipt(self):
        self.receipt_mode='missing';r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['observation_state'],'READ_ERROR');self.assertEqual(o['summary.json']['contract_failure']['boundary'],'REFERENCE_RECEIPT')
    def test_malformed_candidate_receipt(self):
        self.receipt_mode='malformed';r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['observation_state'],'SANITIZER_ERROR')
    def test_child_failure_missing_receipt_preserves_exception_type(self):
        self.kind='mismatch';self.receipt_mode='missing';r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['contract_failure']['exception_type'],'ValueError')
    def test_candidate_budget_failure_before_row_preserves_three_json(self):
        original=P.cap_deadline;count=[0]
        def cap(*a):
            count[0]+=1
            if count[0]==4:raise TimeoutError('PRIVATE_SECRET')
            return original(*a)
        self.patch(P,'cap_deadline',side_effect=cap);r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(len(self.calls),3);self.assertEqual(o['summary.json']['observation_state'],'NOT_COLLECTED');self.assertEqual(o['summary.json']['contract_failure']['boundary'],'PHASE_BUDGET')
    def test_rss_rejection_not_candidate_qualification(self):
        P.rss_observation.side_effect=ValueError('PRIVATE_SECRET');r,o=self.run_job();self.assertEqual(r,1);self.assertEqual(o['summary.json']['status'],'INCOMPLETE');self.assertEqual(o['summary.json']['contract_failure']['boundary'],'REFERENCE_RSS')

NATIVE_LOAD=N.load
class Validator(unittest.TestCase):
    def good(self):
        rows=[dict(name=n,status='EXIT0_CLEANED',seconds=.1,diagnostics=A.empty_diagnostics(),**diag(0)) for n in N.STAGES]
        return {'summary.json':{'schema':'n0-historical-local-summary-v1','status':'LOCAL_REFERENCE_EXACT_ONLY','seconds':2.,'contract_failure':{'boundary':'NONE','exception_type':'NONE'},'observation_state':'AVAILABLE','reference':observation(),'sampled_rss':dict(RSS),'scope':dict(local_reference_qualified=True,baseline_adopted=False,dut_executed=False,fullblock_executed=False)},'source_hashes.json':{'schema':'n0-historical-local-sources-v1','files':PINS},'stage_exits.json':{'schema':'n0-historical-local-stage-exits-v1','stages':rows}}
    def test_exact_valid(self):self.assertTrue(N.validate(self.good(),args.repo,PINS,A,C))
    def test_qualifier_mutations_rejected(self):
        variants=[]
        for k in ['baseline_adopted','dut_executed','fullblock_executed']:
            x=self.good();x['summary.json']['scope'][k]=True;variants.append(x)
        x=self.good();x['stage_exits.json']['stages']=[];variants.append(x)
        x=self.good();x['stage_exits.json']['stages'][0]['status']='FAILED';variants.append(x)
        x=self.good();x['stage_exits.json']['stages'][0]['waitid_code']=2;x['stage_exits.json']['stages'][0]['waitid_status']=9;variants.append(x)
        x=self.good();x['summary.json']['observation_state']='READ_ERROR';variants.append(x)
        x=self.good();x['summary.json']['sampled_rss']=None;variants.append(x)
        x=self.good();x['summary.json']['reference']['worker_accepted']=False;variants.append(x)
        x=self.good();x['source_hashes.json']['files']={};variants.append(x)
        for i,x in enumerate(variants):
            with self.subTest(i=i),self.assertRaises((ValueError,TypeError,KeyError)):N.validate(x,args.repo,PINS,A,C)
    def test_private_arbitrary_diagnostic_rejected(self):
        x=self.good();r=x['stage_exits.json']['stages'][-1];r.update(status='FAILED',**diag(1));r['diagnostics'].update(context_state='AVAILABLE',merged_log_tail='PRIVATE_PASSWORD=abc');x['summary.json']['scope']['local_reference_qualified']=False;x['summary.json'].update(status='INCOMPLETE',contract_failure={'boundary':'NATIVE','exception_type':'ValueError'},reference=observation('gate'))
        with self.assertRaises(ValueError):N.validate(x,args.repo,PINS,A,C)
    def test_source_only_never_execute(self):
        with mock.patch.object(N,'execute',side_effect=AssertionError('actual')),contextlib.redirect_stdout(io.StringIO()) as s:self.assertEqual(N.main(['--repo',str(args.repo)]),0)
        self.assertIn('SOURCE_ONLY',s.getvalue())
    def test_bad_source_buffer_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad';p.write_bytes(b'x')
            with self.assertRaises(ValueError):module(p,RUN_PIN)
    def test_same_size_bad_sha_before_compile(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad';raw=bytearray(checked(args.source/'run.py',RUN_PIN));raw[0]^=1;p.write_bytes(raw)
            with mock.patch('builtins.compile',side_effect=AssertionError('must not compile')),self.assertRaises(ValueError):module(p,RUN_PIN)
    def test_correct_buffer_never_reread(self):
        raw=checked(args.source/'run.py',RUN_PIN)
        with mock.patch('__main__.checked',return_value=raw) as c,mock.patch.object(Path,'open',side_effect=AssertionError('second open')):m=module(args.source/'run.py',RUN_PIN)
        self.assertEqual(c.call_count,1);self.assertEqual(m.STAGES,N.STAGES)
    def test_incomplete_parent_boundary_association(self):
        for b in ('RUNTIME_PREPARE','RUNTIME_TREE','RAW2_RECEIPT','PATH','SOURCE','PHASE_ORDER','DEADLINE','PHASE_BUDGET'):
            x=self.good();x['summary.json']['scope']['local_reference_qualified']=False;x['summary.json'].update(status='INCOMPLETE',contract_failure={'boundary':b,'exception_type':'ValueError'})
            if b in ('PHASE_ORDER','DEADLINE','PHASE_BUDGET'):x['stage_exits.json']['stages'][-1].update(status='FAILED',**diag(1))
            with self.subTest(b=b),self.assertRaises(ValueError):N.validate(x,args.repo,PINS,A,C)

class ProjectionAndEntry(unittest.TestCase):
    def test_original_reference_bytes_pinned(self):
        self.assertEqual(PINS[N.REFERENCE+'n0_reference.py'],{'bytes':13753,'sha256':'d26bd286857a6bff8217472733658cbdcb1e6590fa095e0d0589bc1be81b8fc4'})
        self.assertEqual(PINS[N.REFERENCE+'PINS.json'],{'bytes':6364,'sha256':'ecea4b9b9137c06ae3c3f37bf9710f40f12a4556d1ae2c9aa77b84a857548db8'})
    def test_arbitrary_capability_redacted(self):
        r=private_receipt('gate');r['observed_runtime']['capability']='PRIVATE_SECRET_PATH';v=N.project_receipt(r,REFPINS,C);self.assertEqual(v['observed_capability'],'OTHER');self.assertNotIn('PRIVATE_SECRET',json.dumps(v))
        r.pop('observed_runtime');self.assertEqual(N.project_receipt(r,REFPINS,C)['observed_capability'],'UNKNOWN')
    def test_pass_receipt_native_library_drift_rejected(self):
        r=private_receipt();r['runtime_after']['python']['sha256']='0'*64
        with self.assertRaises(ValueError):N.project_receipt(r,REFPINS,C)
    def test_pass_receipt_ci_profile_rejected(self):
        r=private_receipt();r['python_profile']='ci31214'
        with self.assertRaises(ValueError):N.project_receipt(r,REFPINS,C)
    def test_exact_flags_cannot_cover_bad_output_pin(self):
        for key in ('native','fp32le'):
            r=private_receipt();r['output'][key]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):N.project_receipt(r,REFPINS,C)
    def test_public_success_requires_natural_four_clean(self):
        v=Validator();x=v.good();r=x['stage_exits.json']['stages'][-1];r.update(status='FAILED',**diag(1));x['summary.json'].update(status='INCOMPLETE',contract_failure={'boundary':'REFERENCE_OUTPUT','exception_type':'ValueError'});x['summary.json']['scope']['local_reference_qualified']=False
        with self.assertRaises(ValueError):N.validate(x,args.repo,PINS,A,C)
    def test_entry_raw2_readonly_new_receipt_no_network(self):
        calls=[]
        def read_fixed(p,pin,code='SOURCE'):
            calls.append((Path(p),pin,code))
            if Path(p).name=='PINS.json':return json.dumps(REFPINS).encode()
            return b'fixed synthetic private bytes checked by mock'
        with mock.patch.object(ENTRY,'checked',side_effect=read_fixed),mock.patch.object(ENTRY,'load_runtime',side_effect=AssertionError('no network/runtime')):
            value=ENTRY.raw2_receipt(args.repo,Path('/synthetic/embedding'),Path('/synthetic/gamma'))
        self.assertEqual(value,RAW2);self.assertEqual(len(calls),3)
        self.assertEqual(calls[1][1],(786432,'3cdd8eecf1d0948c6ebf40ca947875b7b706521733fa3107e934d3815e45c014'))
        self.assertEqual(calls[2][1],(3072,'ea77d5968e396420086f0c6c45c08df4ca4228e0c8a0be5d6ec5d0d247110a0e'))
    def test_entry_raw2_cli_private_receipt_fixed(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as t:
            out=Path(t)/'raw2';output=io.StringIO()
            with mock.patch.object(ENTRY,'raw2_receipt',return_value=copy.deepcopy(RAW2)),mock.patch.object(ENTRY,'load_runtime',side_effect=AssertionError('no runtime')),contextlib.redirect_stdout(output):
                rc=ENTRY.main(['--stage','raw2','--repo',str(args.repo),'--embedding','/synthetic/embedding','--gamma','/synthetic/gamma','--out',str(out),'--deadline',str(time.monotonic()+25),'--execute'])
            self.assertEqual(rc,0);self.assertEqual(N.decode((out/'RECEIPT.json').read_bytes()),RAW2);self.assertEqual(output.getvalue(),'LOCAL_PROBE_OK:RAW2\n')
    def test_entry_invalid_raw2_suppresses_exception_text(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as t,contextlib.redirect_stdout(io.StringIO()) as output,mock.patch.object(ENTRY,'raw2_receipt',side_effect=ValueError('PRIVATE_SECRET')):
            rc=ENTRY.main(['--stage','raw2','--repo',str(args.repo),'--embedding','/synthetic/a','--gamma','/synthetic/b','--out',t+'/new','--deadline',str(time.monotonic()+25),'--execute'])
            self.assertEqual(rc,1);self.assertEqual(output.getvalue(),'LOCAL_PROBE_FAILED:RAW2:UNEXPECTED\n')
    def test_entry_source_only_no_raw_or_runtime(self):
        with mock.patch.object(ENTRY,'raw2_receipt',side_effect=AssertionError('raw')),mock.patch.object(ENTRY,'load_runtime',side_effect=AssertionError('runtime')),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(ENTRY.main([]),0)
    def test_entry_same_size_sha_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as t:
            p=Path(t)/'file';p.write_bytes(b'abcd');pin=(4,hashlib.sha256(b'abcd').hexdigest());self.assertEqual(ENTRY.checked(p,pin),b'abcd')
            p.write_bytes(b'abce')
            with self.assertRaises(ValueError):ENTRY.checked(p,pin)
            p.write_bytes(b'abcd');link=Path(t)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):ENTRY.checked(link,pin)
    def test_duplicate_and_nonfinite_receipt_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):N.decode(raw)

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])

