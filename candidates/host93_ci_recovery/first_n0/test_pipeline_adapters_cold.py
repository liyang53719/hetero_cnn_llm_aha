"""Pinned, same-buffer, pure-Python adapter integration; never executes phases."""
import argparse, ast, contextlib, copy, hashlib, io, json, os, stat, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock

PINS = {'pipeline.py': (31285, 'fa1f359f3e7145cabdeed32898799ac5f72c8fa5fcccd29a0dd21c8970385e12'), 'stage_entry.py': (5627, 'a3fad553a94bb07b210b32b947cbeaf15dc2fa6b4c314317d99132d6458bedd5')}
DEFAULT = str(Path(__file__).resolve().parent)
ap = argparse.ArgumentParser(allow_abbrev=False); ap.add_argument('--source', type=Path, default=Path(DEFAULT)); args, rest = ap.parse_known_args()
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Tests require -I -S -B')
def checked(path, pin):
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('source path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        a = os.fstat(f.fileno())
        if not stat.S_ISREG(a.st_mode) or a.st_size != pin[0]: raise ValueError('source size/type')
        raw = f.read(pin[0] + 1); z = os.fstat(f.fileno())
    sig = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if sig(a) != sig(z) or sig(z) != sig(path.stat(follow_symlinks=False)): raise ValueError('source changed')
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin: raise ValueError('source hash')
    return raw

def source(name):
    raw = checked(args.source/name, PINS[name]); m = types.ModuleType('_tested_'+name[:-3]); m.__file__ = str(args.source/name); sys.modules[m.__name__] = m
    exec(compile(raw, m.__file__, 'exec', dont_inherit=True), m.__dict__); return m
def cold_audit(event, values):
    if event.startswith(('socket.', 'subprocess.', 'ctypes.dlopen')) or event in ('os.system','os.fork','os.posix_spawn','os.exec'):
        raise RuntimeError('cold test forbidden external execution')
sys.addaudithook(cold_audit)
A=source('pipeline.py'); E=source('stage_entry.py')
SECRET='PRIVATE_SECRET_ARBITRARY_TEXT'
def encode(x): return json.dumps(x).encode()
def natural(name, code):
    return dict(name=name,exit_code=code,waitid_code=1,waitid_status=code,receipt_timed_out=False,cleanup_confirmed=True,kill_attempted=True,kill_result='GROUP_ALREADY_ABSENT',final_reap_signal=None)

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir();self.work=self.root/'out';self.now=100.;self.obs=A.empty_observation();self.completed=[];self.calls=[];self.events=[];self.stages=[]
        self.runtime=types.SimpleNamespace(source_preflight=mock.Mock(),require_current_python=mock.Mock(),install_argv=mock.Mock(return_value=['FIXED_INSTALL']),observe_installed_tree=mock.Mock())
        self.actual=b'\0'*786432;self.raw=b'{"fixed_counts":true}';self.counts={'fixed_counts':True};self.apin={'bytes':len(self.actual),'sha256':A.sha(self.actual)}
        self.comparator=types.SimpleNamespace(capture_gate=mock.Mock(return_value=self.counts), ORIGINAL_SCRIPT={'sha256':'1'*64}, ORIGINAL_CONTRACT={'sha256':'2'*64})
        metrics=dict(shape=[1,128,1536],elements=196608,finite=True,actual_f32_sha256=self.apin['sha256'],reference_f32_sha256=A.F32['sha256'],max_abs=.001,mean_abs=.001,relative_l2=.001,cosine=.999,normalized_max_abs=.001,different_elements=100,bit_exact=False)
        self.report=dict(schema=1,scope='FIRST_N0_M128_ONLY',stage='COMPLETE',code=None,full_block_pass=False,reference_hash_accepted=True,capture_basic_counts_accepted=True,shape=[1,128,1536],elements=196608,actual_bytes=786432,reference_bytes=786432,source_sha256='1'*64,contract_sha256='2'*64,capture_sha256=A.sha(self.raw),actual_sha256=self.apin['sha256'],reference_sha256=A.F32['sha256'],metrics=metrics,limits={'max_abs':.03125,'mean_abs':.005},numeric_pass=True,status='N0_LIMITED_TOLERANCE_PASS',bit_exact=False,hash_exact=False)
        self.comparator.REPORT_KEYS=set(self.report);self.comparator.METRIC_KEYS=set(metrics)
        self.front={'inputs':self.root/'inputs','runtime':self.root/'runtime','reference':self.root/'reference'/'n0.f32le'};self.execution={'compiled_executable':dict(path=str(self.root/'elf'),bytes=10,sha256='3'*64)}
        self.pins={p:{'bytes':23,'sha256':'4'*64} for p in (A.PREFIX+'stage_entry.py',A.PREFIX+'prepare_inputs.py',A.REFERENCE+'n0_reference.py',A.COMPARISON+'n0_compare.py')}
        self.input_receipt=dict(status='CANONICAL16_PREPARED_ONLY',input_bytes=94920448,inputs=[{}]*16,weights_loaded_into_rtl=False)
        self.ref_receipt=dict(status='PASS_FROZEN_N0_EXACT',reference_accepted=True,stage='COMPLETE',code=None,output=dict(native=A.BF16,fp32le=A.F32,native_exact=True,fp32le_exact=True,accepted=True))
        self.patch('time.monotonic',side_effect=lambda:self.now);self.load=self.patch('load',side_effect=lambda r,p,n:self.runtime if n.endswith('runtime_wheel_gate.py') else self.comparator);self.reader=self.patch('read',side_effect=self.read);self.ident=self.patch('verify_file',return_value=self.apin);self.inputs=self.patch('canonical_inputs',return_value=[]);self.rss=self.patch('rss_observation',return_value=dict(sampled_leader_max_kib=1,limit_kib=1572864,os_hard_limit=False,includes_descendants=False))
    def patch(self,name,**kw):
        p=mock.patch.object(A,name,**kw) if '.' not in name else mock.patch.object(A.time,name.split('.')[-1],**kw)
        m=p.start();self.addCleanup(p.stop);return m
    def read(self,path,cap,expected=None):
        self.events.append(('read',str(path)))
        if path.name=='INPUTS_READY.json':return encode(self.input_receipt)
        if path.name=='RECEIPT.json':return encode(self.ref_receipt if path.parent.name=='reference' else self.report)
        if path.name=='counts.json':return self.raw
        if path.name=='actual_n0.f32le':return self.actual
        if path.name=='n0.f32le':return b'fixed reference'
        raise RuntimeError(SECRET)
    def phase(self,*a):
        self.calls.append(a);self.events.append(('phase',a[0]));self.stages.append(natural(a[0],0));return {'evidence_root':str(self.root/'evidence')}
    def frontdoor(self,stop=10000,phase=None):return A.run_frontdoor(self.repo,self.work,self.pins,phase or self.phase,stop,self.obs,self.completed)
    def numeric(self,stop=10000,phase=None):return A.run_numeric(self.repo,self.work,self.pins,phase or self.phase,stop,self.front,self.execution,self.obs,self.completed,self.stages)
    def rejected(self,fn,boundary,code):
        with self.assertRaises(A.Rejected) as c:fn()
        self.assertEqual((c.exception.safe_contract_boundary,c.exception.safe_contract_code),(boundary,code));self.assertNotIn(SECRET,str(c.exception))

class Frontdoor(Fixture):
    def test_success_order_budgets(self):
        out=self.frontdoor();self.assertEqual([c[0] for c in self.calls],list(A.FRONT_STAGES));self.assertEqual(self.completed,list(A.FRONT_COMPONENTS));self.assertTrue(self.obs['reference_ready']);self.assertEqual(out['reference'],self.work/'reference'/'n0.f32le')
        expected=[(180,165,120,512*A.MIB,256*A.MIB),(120,100,90,2*A.GIB,A.GIB),(900,880,300,512*A.MIB,128*A.MIB),(120,100,60,256*A.MIB,128*A.MIB),(120,100,90,8*A.GIB,4*A.MIB)]
        for call,exp in zip(self.calls,expected):
            self.assertEqual(tuple(call[4][k] for k in ('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes')),exp);self.assertEqual(call[4]['log_bytes'],65536);self.assertEqual(call[4]['sample_rows'],exp[0]+16)
        for i in (0,2,3,4):self.assertEqual(self.calls[i][1][1:5],['-I','-S','-B','-c']);self.assertEqual(self.calls[i][1][5],A.BOOTSTRAP)
        for i,key,val in ((0,'--deadline',280),(2,'--deadline',1000),(3,'--shared-stop',220),(4,'--shared-stop',220)):
            cmd=self.calls[i][1];self.assertEqual(float(cmd[cmd.index(key)+1]),val)
        self.runtime.install_argv.assert_called_once_with(self.repo/A.REFERENCE,self.work/'wheels',self.work/'runtime');self.runtime.observe_installed_tree.assert_called_once_with(self.work/'runtime',self.work/'wheels')
        self.assertEqual(self.calls[4][3]['OMP_NUM_THREADS'],'4');self.assertNotIn('OMP_NUM_THREADS',self.calls[3][3])
    def test_shared_deadline_caps_every_phase(self):
        self.frontdoor(200)
        for c in self.calls:self.assertLessEqual(c[4]['total_seconds'],85);self.assertLessEqual(c[4]['work_seconds'],70)
        for c in self.calls:
            for flag in ('--deadline','--shared-stop'):
                if flag in c[1]:self.assertLessEqual(float(c[1][c[1].index(flag)+1]),185)
    def test_front_total_1440_and_wheel_300(self):
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='n0_wheels_acquire':self.now=280
            if a[0]=='n0_runtime_install':self.now=399
            if a[0]=='n0_raw_acquire':self.now=1299
            if a[0]=='n0_inputs_prepare':self.now=1419
            return r
        self.frontdoor(10000,phase);self.assertEqual(self.calls[1][4]['total_seconds'],120);self.assertEqual(self.calls[-1][4]['total_seconds'],120)
        self.assertEqual(float(self.calls[-1][1][self.calls[-1][1].index('--shared-stop')+1]),1539)
    def test_front_1440_cap_reaches_reference(self):
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='n0_wheels_acquire':self.now=280
            if a[0]=='n0_runtime_install':self.now=390
            if a[0]=='n0_raw_acquire':self.now=1290
            if a[0]=='n0_inputs_prepare':self.now=1400
            return r
        self.frontdoor(10000,phase);cmd=self.calls[-1][1];self.assertEqual(float(cmd[cmd.index('--shared-stop')+1]),1520)
        # Reuse a fresh output and drive reference scheduling against the actual 1440 wall.
        self.work=self.root/'out2';self.now=100;self.calls=[];self.completed=[];self.obs=A.empty_observation()
        def delayed(*a):
            r=self.phase(*a)
            if a[0]=='n0_inputs_prepare':self.now=1500
            return r
        self.frontdoor(10000,delayed);self.assertEqual(self.calls[-1][4]['total_seconds'],40);self.assertEqual(self.calls[-1][4]['work_seconds'],25);cmd=self.calls[-1][1];self.assertEqual(float(cmd[cmd.index('--shared-stop')+1]),1540)
    def test_front_deadline_failure_fixed(self):self.rejected(lambda:self.frontdoor(120),'N0_DEADLINE','N0_DEADLINE');self.assertEqual(self.calls,[])
    def test_inputs_rejection_stops_reference(self):
        self.input_receipt['weights_loaded_into_rtl']=True;self.rejected(self.frontdoor,'N0_INPUT_RECEIPT','N0_INPUTS');self.assertEqual([c[0] for c in self.calls],list(A.FRONT_STAGES[:4]));self.assertEqual(self.completed,['n0_runtime'])
    def test_receipt_exception_redacted(self):
        self.reader.side_effect=RuntimeError(SECRET);self.rejected(self.frontdoor,'N0_INPUT_RECEIPT','N0_INPUTS')
    def test_reference_postflight_rejection(self):
        self.ref_receipt['reference_accepted']=False;self.rejected(self.frontdoor,'N0_REFERENCE_RECEIPT','N0_REFERENCE');self.assertEqual(self.completed,['n0_runtime','n0_inputs'])
    def test_runtime_prepare_failure(self):
        self.runtime.source_preflight.side_effect=RuntimeError(SECRET);self.rejected(self.frontdoor,'N0_RUNTIME_PREPARE','N0_RUNTIME');self.assertEqual(self.calls,[])
    def test_runtime_tree_failure(self):
        self.runtime.observe_installed_tree.side_effect=RuntimeError(SECRET);self.rejected(self.frontdoor,'N0_RUNTIME_TREE','N0_RUNTIME');self.assertEqual(len(self.calls),2)
    def test_native_failure_identity(self):
        error=RuntimeError(SECRET)
        with self.assertRaises(RuntimeError) as c:self.frontdoor(phase=mock.Mock(side_effect=error))
        self.assertIs(c.exception,error);self.assertEqual(self.completed,[])

class ReferenceCapability(Fixture):
    def setUp(self):
        super().setUp()
        self.reference=types.SimpleNamespace(CODES={'DISPATCH','RESOURCE','HASH_MISMATCH'})
        self.load.side_effect=lambda r,p,n:self.reference if n.endswith('n0_reference.py') else self.runtime if n.endswith('runtime_wheel_gate.py') else self.comparator
        self.failed=dict(schema=1,scope='FROZEN_M128_N0_REFERENCE_ONLY',status='NOT_COMPLETED',reference_accepted=False,rtl_executed=False,fullblock_executed=False,code='DISPATCH',stage='RUNTIME_IMPORT',observed_runtime={'capability':'AVX2','private_extra':SECRET})
    def project(self):
        self.ref_receipt=self.failed
        return A.failed_reference_capability(self.repo,self.pins,self.work/'reference'/'RECEIPT.json')
    def test_known_enums(self):
        for value in ('DEFAULT','AVX2','AVX512'):
            self.failed['observed_runtime']['capability']=value
            self.assertEqual(self.project(),dict(state='AVAILABLE',expected='AVX512',observed=value))
    def test_arbitrary_values_are_other_not_free_text(self):
        for value in (SECRET,None,False,123,{},['AVX512']):
            self.failed['observed_runtime']['capability']=value;result=self.project()
            self.assertEqual(result['observed'],'OTHER');self.assertNotIn(SECRET,json.dumps(result))
    def test_missing_observation_is_unknown(self):
        for value in (None,{}):
            self.failed['observed_runtime']=value;self.assertEqual(self.project(),dict(state='AVAILABLE',expected='AVX512',observed='UNKNOWN'))
    def test_receipt_read_failure(self):
        self.reader.side_effect=OSError(SECRET);self.assertEqual(self.project(),dict(state='READ_ERROR',expected='AVX512',observed='UNKNOWN'))
    def test_bad_json_and_shape(self):
        for raw in (b'{',b'[]',b'{"schema":1,"schema":1}',b'{"schema":NaN}'):
            self.reader.side_effect=None;self.reader.return_value=raw;self.assertEqual(self.project()['state'],'SANITIZER_ERROR')
    def test_wrong_failed_receipt_contract(self):
        for key,value in [('schema',True),('scope',SECRET),('status','PASS_FROZEN_N0_EXACT'),('reference_accepted',True),('rtl_executed',True),('fullblock_executed',True),('code',SECRET),('stage',SECRET),('observed_runtime',SECRET)]:
            original=copy.deepcopy(self.failed);self.failed[key]=value
            self.assertEqual(self.project()['state'],'SANITIZER_ERROR');self.failed=original
    def test_exact_read_cap(self):
        self.project();self.reader.assert_called_once_with(self.work/'reference'/'RECEIPT.json',65536)
    def test_source_loading_error_is_sanitizer_error(self):
        self.load.side_effect=ValueError(SECRET);self.assertEqual(self.project()['state'],'SANITIZER_ERROR')
    def test_success_does_not_collect_failed_receipt(self):
        with mock.patch.object(A,'failed_reference_capability') as collector:self.frontdoor();collector.assert_not_called()
        self.assertEqual(self.obs['reference_capability'],A.empty_reference_capability())
    def test_first_phase_failure_does_not_collect(self):
        with mock.patch.object(A,'failed_reference_capability') as collector,self.assertRaises(RuntimeError):self.frontdoor(phase=mock.Mock(side_effect=RuntimeError(SECRET)))
        collector.assert_not_called();self.assertEqual(self.obs['reference_capability'],A.empty_reference_capability())

class BoundedReferenceRead(unittest.TestCase):
    def test_real_reader_rejects_oversize_missing_and_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);large=root/'large';large.write_bytes(b'x'*65537);link=root/'link';link.symlink_to(large)
            for path in (large,link,root/'missing'):
                with self.subTest(path=path.name):self.assertEqual(A.failed_reference_capability(root,{},path)['state'],'READ_ERROR')

class Numeric(Fixture):
    def test_success_real_validator_and_order(self):
        self.assertTrue(self.numeric());self.assertEqual([c[0] for c in self.calls],list(A.FINAL_STAGES));self.assertEqual(self.completed,['n0_capture','n0_comparison']);self.assertEqual(self.obs['state'],'COMPLETE');self.assertEqual(self.inputs.call_count,2);self.assertEqual(self.ident.call_count,3)
        self.assertEqual(self.calls[0][1],[str(self.root/'elf'),str(self.front['inputs']),str(self.work/'capture')]);self.assertEqual(self.calls[0][4],A.limits(3540,3510,3540,6*A.GIB,4*A.MIB));self.assertEqual(self.calls[1][4],A.limits(30,15,25,8*A.GIB,4*A.MIB));self.assertEqual(self.calls[1][1][1:5],['-I','-S','-B','-c'])
    def test_shared_stop_reserved_cleanup(self):
        self.numeric(500);self.assertEqual(self.calls[0][4]['total_seconds'],340);self.assertEqual(self.calls[0][4]['work_seconds'],325);self.assertEqual(self.calls[1][4]['total_seconds'],30)
    def test_numeric_window_includes_compare(self):
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='host93_first_n0':self.now=3680
            return r
        self.numeric(10000,phase);self.assertEqual(self.calls[-1][4]['total_seconds'],20);self.assertEqual(self.calls[-1][4]['work_seconds'],5);cmd=self.calls[-1][1];self.assertEqual(float(cmd[cmd.index('--shared-stop')+1]),3700)
    def test_capture_failure_preserved(self):
        error=TimeoutError(SECRET)
        with self.assertRaises(TimeoutError) as c:self.numeric(phase=mock.Mock(side_effect=error))
        self.assertIs(c.exception,error);self.assertEqual(self.obs['capture_state'],'NATIVE_FAILED');self.assertEqual(self.completed,[])
    def test_native_cycle_report_still_preserves_error(self):
        error=RuntimeError(SECRET);partial={'fixed_cycle_receipt':True}
        def phase(*a):
            self.phase(*a);self.stages[-1]=natural(a[0],2);raise error
        with mock.patch.object(A,'cycle_budget_counts',return_value=partial) as gate,self.assertRaises(RuntimeError) as c:self.numeric(phase=phase)
        self.assertIs(c.exception,error);self.assertEqual(self.obs['capture_state'],'REPORTED');self.assertEqual(self.obs['capture'],partial);self.assertEqual(self.completed,[]);self.assertEqual(self.obs['comparison_state'],'NOT_COLLECTED');gate.assert_called_once_with(self.raw,self.comparator)
    def test_invalid_cycle_counts_do_not_replace_native_error(self):
        error=RuntimeError(SECRET)
        def phase(*a):
            self.phase(*a);self.stages[-1]=natural(a[0],2);raise error
        with mock.patch.object(A,'cycle_budget_counts',side_effect=ValueError('bad counts')),self.assertRaises(RuntimeError) as c:self.numeric(phase=phase)
        self.assertIs(c.exception,error);self.assertEqual(self.obs['capture_state'],'NATIVE_FAILED');self.assertIsNone(self.obs['capture'])
    def test_compare_failure_survives_unparseable_receipt(self):
        error=TimeoutError(SECRET)
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='host93_n0_compare':self.reader.side_effect=ValueError('bad receipt');raise error
            return r
        with self.assertRaises(TimeoutError) as c:self.numeric(phase=phase)
        self.assertIs(c.exception,error);self.assertEqual(self.completed,['n0_capture'])
    def test_capture_gate_rejected(self):
        self.comparator.capture_gate.side_effect=RuntimeError(SECRET);self.rejected(self.numeric,'N0_CAPTURE_RECEIPT','N0_CAPTURE');self.assertEqual(len(self.calls),1)
    def test_capture_size_rejected(self):
        self.actual=b'bad';self.rejected(self.numeric,'N0_CAPTURE_RECEIPT','N0_CAPTURE');self.assertEqual(len(self.calls),1)
    def test_elf_preflight_rejected(self):
        self.ident.side_effect=RuntimeError(SECRET);self.rejected(self.numeric,'N0_CAPTURE_ELF','N0_CAPTURE');self.assertEqual(self.calls,[])
    def test_input_postflight_rejected(self):
        self.inputs.side_effect=[[],RuntimeError(SECRET)];self.rejected(self.numeric,'N0_CAPTURE_INPUTS','N0_INPUTS');self.assertEqual(len(self.calls),1)
    def test_compare_report_rejected(self):
        self.report['full_block_pass']=True;self.rejected(self.numeric,'N0_COMPARE_RECEIPT','N0_COMPARISON');self.assertEqual(self.completed,['n0_capture'])
    def test_compare_failure_authoritative(self):
        error=RuntimeError(SECRET);self.report['full_block_pass']=True
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='host93_n0_compare':raise error
            return r
        with self.assertRaises(RuntimeError) as c:self.numeric(phase=phase)
        self.assertIs(c.exception,error);self.assertEqual(error.safe_contract_code,'N0_COMPARISON');self.assertEqual(self.completed,['n0_capture'])
    def test_numeric_tolerance_fail_is_valid_result(self):
        self.report.update(status='N0_LIMITED_TOLERANCE_FAIL',numeric_pass=False);self.report['metrics']['max_abs']=.1;error=RuntimeError(SECRET)
        def phase(*a):
            r=self.phase(*a)
            if a[0]=='host93_n0_compare':self.stages[-1]=natural(a[0],1);raise error
            return r
        self.assertFalse(self.numeric(phase=phase));self.assertEqual(self.obs['comparison_state'],'AVAILABLE');self.assertEqual(self.completed,['n0_capture','n0_comparison'])
    def test_nonnatural_compare_rejected(self):
        def phase(*a):
            r=self.phase(*a);self.stages[-1]['cleanup_confirmed']=False;return r
        self.rejected(lambda:self.numeric(phase=phase),'N0_COMPARE_RECEIPT','N0_COMPARISON')
    def test_no_phase_order_substitution(self):
        def phase(*a):
            r=self.phase(*a);self.stages[-1]['name']='wrong';return r
        self.rejected(lambda:self.numeric(phase=phase),'N0_COMPARE_RECEIPT','N0_COMPARISON')

class ReceiptLabels(Fixture):
    def check_label(self,kind,failed):
        native=ValueError('fixed native failure');original=self.read
        def reading(path,*args):
            if path.name=='RECEIPT.json' and path.parent.name=='comparison':
                if kind=='missing':raise FileNotFoundError(SECRET)
                return b'{'
            return original(path,*args)
        self.reader.side_effect=reading
        def phase(*args):
            result=self.phase(*args)
            if args[0]=='host93_n0_compare' and failed:self.stages[-1]=natural(args[0],1);raise native
            return result
        with self.assertRaises(ValueError) as caught:self.numeric(phase=phase)
        if failed:self.assertIs(caught.exception,native)
        else:self.assertIsInstance(caught.exception,A.Rejected)
        self.assertEqual(caught.exception.safe_contract_boundary,'N0_COMPARE_RECEIPT');self.assertEqual(caught.exception.safe_contract_code,'N0_COMPARISON');self.assertEqual(self.obs['comparison_state'],'READ_ERROR');self.assertEqual(self.completed,['n0_capture'])
    def test_failed_missing_receipt_fixed_label(self):self.check_label('missing',True)
    def test_failed_malformed_receipt_fixed_label(self):self.check_label('malformed',True)
    def test_success_missing_receipt_fixed_label(self):self.check_label('missing',False)
    def test_success_malformed_receipt_fixed_label(self):self.check_label('malformed',False)
    def test_failed_compare_reference_postread_retains_error_and_label(self):
        self.report.update(status='N0_LIMITED_TOLERANCE_FAIL',numeric_pass=False);self.report['metrics']['max_abs']=.1;native=ValueError('fixed native failure');original=self.read
        def reading(path,*args):
            if path.name=='n0.f32le':raise ValueError(SECRET)
            return original(path,*args)
        self.reader.side_effect=reading
        def phase(*args):
            result=self.phase(*args)
            if args[0]=='host93_n0_compare':self.stages[-1]=natural(args[0],1);raise native
            return result
        with self.assertRaises(ValueError) as caught:self.numeric(phase=phase)
        self.assertIs(caught.exception,native);self.assertEqual(native.safe_contract_boundary,'N0_REFERENCE_RECEIPT');self.assertEqual(native.safe_contract_code,'N0_REFERENCE');self.assertEqual(self.completed,['n0_capture'])

class SourceContracts(unittest.TestCase):
    def test_production_has_no_assert_gates(self):
        for name in PINS:
            self.assertFalse(any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(checked(args.source/name,PINS[name])))))
    def test_no_numeric_runtime_imported(self):
        self.assertFalse(any(n.split('.')[0] in {'numpy','torch','tensorflow','scipy','onnxruntime'} for n in sys.modules))

class StageEntry(unittest.TestCase):
    def run_entry(self,argv,runtime=None,raw=None):
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream),mock.patch.object(E,'module',return_value=runtime or raw) as loader,mock.patch.object(E.time,'monotonic',return_value=100):code=E.main(argv)
        return code,stream.getvalue(),loader
    def test_source_default_no_import(self):
        code,text,loader=self.run_entry([]);self.assertEqual((code,text),(0,'N0_ACQUISITION_SOURCE_ONLY\n'));loader.assert_not_called()
    def test_source_explicit_no_execute(self):
        code,text,loader=self.run_entry(['--stage','raw','--repo','/missing']);self.assertEqual(code,0);loader.assert_not_called()
    def test_wheels_exact_api(self):
        runtime=types.SimpleNamespace(require_current_python=mock.Mock(),acquire_wheels=mock.Mock())
        code,text,loader=self.run_entry(['--stage','wheels','--repo','/repo','--out','/out','--deadline','200','--execute'],runtime=runtime)
        self.assertEqual((code,text),(0,'N0_ACQUISITION_OK:WHEELS\n'));loader.assert_called_once_with(Path('/repo')/E.RUNTIME_PATH,E.RUNTIME_PIN);runtime.acquire_wheels.assert_called_once_with(Path('/repo')/E.REFERENCE_PATH,Path('/out'),execute=True,deadline=195.)
    def test_raw_exact_api(self):
        raw=types.SimpleNamespace(check_sources=mock.Mock(return_value=('plan','helpers','shard')),prepare_output=mock.Mock(return_value='output'),strict_opener=mock.Mock(return_value='opener'),collect_fixed=mock.Mock())
        code,text,loader=self.run_entry(['--stage','raw','--repo','/repo','--out','/out','--deadline','200','--execute'],raw=raw)
        self.assertEqual((code,text),(0,'N0_ACQUISITION_OK:RAW\n'));loader.assert_called_once_with(Path('/repo')/E.RAW_PATH,E.RAW_PIN);raw.check_sources.assert_called_once_with(Path('/repo'),Path('/repo')/Path(E.RAW_PATH).parent/'ACQUISITION_PLAN.json');raw.prepare_output.assert_called_once_with(Path('/repo'),Path('/out'));raw.strict_opener.assert_called_once_with(195.);raw.collect_fixed.assert_called_once_with('plan','helpers','shard','output','opener')
    def test_invalid_flags_are_fixed(self):
        for argv in (['--execute'],['--unknown',SECRET],['--stage','raw','--repo','/r','--out','/o','--deadline','nan','--execute']):
            with self.subTest(argv=argv):
                code,text,_=self.run_entry(argv);self.assertEqual(code,1);self.assertNotIn(SECRET,text);self.assertTrue(text.startswith('N0_ACQUISITION_FAILED:SOURCE:'))
    def test_arbitrary_exception_not_printed(self):
        class GateError(Exception):pass
        runtime=types.SimpleNamespace(require_current_python=mock.Mock(side_effect=RuntimeError(SECRET)),GateError=GateError,CODES=())
        code,text,_=self.run_entry(['--stage','wheels','--repo','/r','--out','/o','--deadline','200','--execute'],runtime=runtime);self.assertEqual(text,'N0_ACQUISITION_FAILED:WHEELS:UNEXPECTED\n')
    def test_raw_known_and_unknown_redacted(self):
        class Refused(Exception):pass
        for msg,code in [('assembled tensor SHA mismatch','RAW_RULE_004'),(SECRET,'UNMAPPED_RAW')]:
            raw=types.SimpleNamespace(check_sources=mock.Mock(side_effect=Refused(msg)),Refused=Refused)
            result,text,_=self.run_entry(['--stage','raw','--repo','/r','--out','/o','--deadline','200','--execute'],raw=raw);self.assertEqual(text,'N0_ACQUISITION_FAILED:RAW_SOURCE:'+code+'\n')
    def test_same_buffer_loader_and_bad_pin(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'tiny.py';data=b'VALUE = 37\n';path.write_bytes(data);pin=(len(data),hashlib.sha256(data).hexdigest())
            self.assertEqual(E.module(path,pin).VALUE,37)
            with self.assertRaises(E.Rejected):E.module(path,(len(data),'0'*64))
            link=Path(td)/'link.py';link.symlink_to(path)
            with self.assertRaises(E.Rejected):E.module(link,pin)
    def test_bootstrap_same_buffer_only(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'tiny.py';data=b'def main():\n return 19\n';path.write_bytes(data)
            argv=['python',str(path),str(len(data)),hashlib.sha256(data).hexdigest()]
            with mock.patch.object(sys,'argv',argv),self.assertRaises(SystemExit) as c:exec(A.BOOTSTRAP,{'__name__':'bootstrap_test'})
            self.assertEqual(c.exception.code,19)
            argv[3]='0'*64
            with mock.patch.object(sys,'argv',argv),self.assertRaises(SystemExit) as c:exec(A.BOOTSTRAP,{'__name__':'bootstrap_bad_test'})
            self.assertEqual(c.exception.code,'N0_SOURCE_REJECTED')

class Diagnostics(unittest.TestCase):
    def test_only_exact_fixed_markers_and_last_four(self):
        marker='N0_ACQUISITION_FAILED:RAW_ACQUIRE:RAW_RULE_004';raw=('\n'.join([SECRET,'prefix '+marker,marker+SECRET]+[marker]*6)).encode()
        with mock.patch.object(A,'read',return_value=raw),mock.patch.object(A,'fixed_markers',return_value={marker}):
            result=A.private_diagnostics(Path('/repo'),{},'n0_raw_acquire',Path('/log'));A.validate_private_diagnostics(Path('/repo'),{},'n0_raw_acquire',result)
        self.assertEqual(result['merged_log_tail'],'\n'.join([marker]*4));self.assertNotIn(SECRET,str(result));self.assertEqual(result['observations'],[])
    def test_no_fixed_marker_no_arbitrary_text(self):
        with mock.patch.object(A,'read',return_value=SECRET.encode()),mock.patch.object(A,'fixed_markers',return_value=set()):result=A.private_diagnostics(Path('/repo'),{},'n0_runtime_install',Path('/log'))
        self.assertEqual(result['merged_log_tail'],'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER');self.assertNotIn(SECRET,str(result))
    def test_read_failure_no_exception_text(self):
        with mock.patch.object(A,'read',side_effect=RuntimeError(SECRET)):result=A.private_diagnostics(Path('/repo'),{},'n0_raw_acquire',Path('/log'))
        self.assertEqual(result['context_state'],'READ_ERROR');self.assertEqual(result['merged_log_tail'],'');self.assertNotIn(SECRET,str(result))
    def test_host_fixed_schema(self):
        line=dict(scope='FIRST_N0_M128_ONLY',status='CONTRACT_ERROR',phase='RTL_N0',code='UNMAPPED',numeric_comparison='NOT_RUN');bad=dict(line,private=SECRET);relative='candidates/host93_first_n0_sources/bridge/metadata/DIAGNOSTIC_MAP.json';pins={relative:{'bytes':1,'sha256':'0'*64}}
        def read(path,*a):return encode({'messages':{}}) if path.name=='DIAGNOSTIC_MAP.json' else encode(bad)+b'\n'+encode(line)+b'\n'+SECRET.encode()
        with mock.patch.object(A,'read',side_effect=read):result=A.private_diagnostics(Path('/repo'),pins,'host93_first_n0',Path('/log'));A.validate_private_diagnostics(Path('/repo'),pins,'host93_first_n0',result)
        self.assertEqual(result['merged_log_tail'],'CONTRACT_ERROR:RTL_N0:UNMAPPED');self.assertNotIn(SECRET,str(result))

if __name__=='__main__':unittest.main(argv=[sys.argv[0]]+rest,verbosity=2)
