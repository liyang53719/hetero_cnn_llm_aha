"""Pinned cache/sequence microtests: synthetic metadata and mocks, no native action."""
import argparse,builtins,copy,hashlib,json,os,resource,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
PINS={'cache_gate.py':(5313,'bc4dc052931317d4e3c0f99bd6beb42d85073a78c2d3efcecd19e8f539756871'),
      'supervision.py':(4363,'10a14b6eafe7cb977790ceea59fb5b4821f9f010df01a7448d4bce1928c3225a'),
      'run_owner_cache.py':(28124,'10d9c44a669315e4a66e8de47135bbe622454e13321e1a12e1eabb93e2114871')}
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--source-dir',required=True,type=Path)
p.add_argument('--mode',required=True,choices=('normal','optimized','relocated'));ARGS=p.parse_args()
def audit(event,args):
    if event.startswith(('subprocess.','socket.')) or event in ('os.system','os.fork','os.forkpty','os.exec','os.posix_spawn','ctypes.dlopen','urllib.Request'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
sys.addaudithook(audit)
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise RuntimeError('COLD_ISOLATION')
resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_CPU,(30,30))
resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2));os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def pin(raw):return len(raw),hashlib.sha256(raw).hexdigest()
def load(name,directory=ARGS.source_dir):
    path=directory/name;raw=path.read_bytes()
    if pin(raw)!=PINS[name]:raise ValueError('COLD_FIXED_SOURCE_IDENTITY')
    m=types.ModuleType('cold_'+name.replace('.','_'));m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__);return m
C=load('cache_gate.py');S=load('supervision.py');R=load('run_owner_cache.py')
def record():return {'exit_code':0,'status':'PASS','cleanup_confirmed':True,'timed_out':False,'reaped':True,
    'parent_exception':None,'group_state':'absent','exit_observed_while_unreaped':{'code':1,'status':0},'argv':['fixed','generation']}
def usage():return {'maxrss_kib_cumulative_parent_children':4096}
def inventory_value():
    rows=[{'path':n,'type':'directory','mode':0o700} for n in ('obj','fixtures','phases','phases/generate','home','tmp','obj/child','extra')]
    for i in range(516):rows.append({'path':f'obj/source{i}.cpp','type':'file','mode':0o600,'bytes':532750 if i==0 else 155000,'sha256':'0'*64})
    for i in range(7):rows.append({'path':f'fixtures/f{i}.hpp','type':'file','mode':0o600,'bytes':1000,'sha256':'0'*64})
    for i in range(5):rows.append({'path':f'extra/e{i}.json','type':'file','mode':0o600,'bytes':61138,'sha256':'0'*64})
    return {'root':'/mock/prior','entries':rows}

class Loader(unittest.TestCase):
    def test_three_pins_and_same_buffer_loading(self):
        for name,wanted in PINS.items():self.assertEqual(pin((ARGS.source_dir/name).read_bytes()),wanted)
        raw=(ARGS.source_dir/'cache_gate.py').read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path=Path(folder)/'cache_gate.py';path.write_bytes(raw);compiler=builtins.compile;seen=[]
            def call(buf,*args,**kwargs):seen.append(buf);path.write_bytes(b'changed');return compiler(buf,*args,**kwargs)
            with mock.patch.object(builtins,'compile',side_effect=call):loaded=load('cache_gate.py',Path(folder))
            self.assertEqual(seen,[raw]);self.assertEqual(loaded.OLD_TARGETS,C.OLD_TARGETS)
    def test_bad_source_pin_before_compile(self):
        raw=(ARGS.source_dir/'cache_gate.py').read_bytes()
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            for bad in (raw[:-1],raw+b'\n',bytes([raw[0]^1])+raw[1:]):
                (Path(folder)/'cache_gate.py').write_bytes(bad)
                with mock.patch.object(builtins,'compile',side_effect=AssertionError('bad compile')) as compiler:
                    with self.assertRaisesRegex(ValueError,'COLD_FIXED_SOURCE_IDENTITY'):load('cache_gate.py',Path(folder))
                    compiler.assert_not_called()

class Cache(unittest.TestCase):
    def setUp(self):
        self.value=inventory_value();self.g=types.SimpleNamespace(need=S.need,clean=Path,decode=json.loads)
        self.tree=C.inventory(self.g,self.value);self.fs=types.SimpleNamespace(tree_inventory=mock.Mock(return_value=self.tree))
        self.cfg={'root':'/mock/prior','inventory':'/mock/tree','receipt':'/mock/prior/EXECUTION_RESULT.json','review':'/mock/review','review_manifest':'/mock/review_manifest'}
        self.receipt={'status':'INCOMPLETE','failure_type':'ValueError','failure_boundary':None,'failure_code':None,
                      'stages':[{'name':'generate','record':record(),'usage':usage()}]}
        self.review=b'Verdict: ACCEPT_ACTUAL_OWNER_GENERATION_NATURAL_ZERO_POSTFLIGHT_HEADER_BOUND_FAILURE_ONLY.'
        def checked(path,wanted,cap,*args,**kwargs):
            self.assertEqual(cap,C.MIB)
            if path==Path(self.cfg['inventory']):self.assertEqual(wanted,C.TREE_PIN);return json.dumps(self.value).encode()
            if path==Path(self.cfg['receipt']):self.assertEqual(wanted,C.RECEIPT_PIN);return json.dumps(self.receipt).encode()
            if path==Path(self.cfg['review']):self.assertEqual(wanted,C.REVIEW_PIN);return self.review
            if path==Path(self.cfg['review_manifest']):self.assertEqual(wanted,C.REVIEW_MANIFEST_PIN);return b'synthetic manifest'
            raise AssertionError(path)
        self.g.checked=mock.Mock(side_effect=checked)
    def go(self):return C.accept(self.g,self.fs,self.cfg,S,['fixed','generation'])
    def test_exact_shape_counts_and_successful_generation_only_receipt(self):
        tree,receipt=self.go();self.assertEqual(tree,self.tree);self.assertEqual(receipt,self.receipt)
        self.assertEqual((len(tree['entries']),tree['files'],tree['bytes']),(536,528,80670440))
        self.fs.tree_inventory.assert_called_once_with(Path('/mock/prior'),96*C.MIB,528,536,16*C.MIB)
    def test_inventory_shape_duplicate_unsafe_and_modes_fail_closed(self):
        cases=[('root_extra',None),('count',None),('path','../escape'),('path','/absolute'),('path','obj//x'),('path','obj'),('dir_mode',0o755),('file_mode',0o644),('file_type','symlink')]
        for mode,bad in cases:
            with self.subTest(mode=mode,bad=bad):
                value=inventory_value()
                if mode=='root_extra':value['extra']=1
                elif mode=='count':value['entries'].pop()
                elif mode=='path':value['entries'][8]['path']=bad
                elif mode=='dir_mode':value['entries'][0]['mode']=bad
                elif mode=='file_mode':value['entries'][8]['mode']=bad
                else:value['entries'][8]['type']=bad
                with self.assertRaises(ValueError):C.inventory(self.g,value)
    def test_inventory_total_and_row_fields_fail_closed(self):
        for mutation in ('bytes','missing','extra'):
            value=inventory_value()
            if mutation=='bytes':value['entries'][8]['bytes']+=1
            elif mutation=='missing':del value['entries'][8]['sha256']
            else:value['entries'][8]['unexpected']=True
            with self.assertRaises(ValueError):C.inventory(self.g,value)
    def test_receipt_scope_shape_actual_argv_and_natural_exit_rejected(self):
        original=copy.deepcopy(self.receipt)
        for key,value in (('status','PASS'),('failure_type','TimeoutError'),('failure_boundary','x'),('failure_code','x'),('stages',[])):
            self.receipt=copy.deepcopy(original);self.receipt[key]=value
            with self.assertRaisesRegex(ValueError,'CACHE_GENERATION_SCOPE'):self.go()
        for section,key,value,code in (('stage','name','build','CACHE_GENERATION_SCOPE'),('record','argv',['different'],'CACHE_GENERATION_SCOPE'),('record','exit_code',1,'NATURAL_EXIT_OR_CLEANUP'),('record','cleanup_confirmed',False,'NATURAL_EXIT_OR_CLEANUP'),('usage','maxrss_kib_cumulative_parent_children',6*1024**2+1,'CUMULATIVE_RSS_6G')):
            self.receipt=copy.deepcopy(original);stage=self.receipt['stages'][0]
            (stage if section=='stage' else stage[section])[key]=value
            with self.assertRaisesRegex(ValueError,code):self.go()
    def test_binding_review_and_stable_inventory_fail_closed(self):
        self.cfg['extra']='x'
        with self.assertRaisesRegex(ValueError,'CACHE_BINDING_KEYS'):self.go()
        del self.cfg['extra'];self.review=b'not accepted'
        with self.assertRaisesRegex(ValueError,'CACHE_ACTUAL_REVIEW_SCOPE'):self.go()
        self.review=b'Verdict: ACCEPT_ACTUAL_OWNER_GENERATION_NATURAL_ZERO_POSTFLIGHT_HEADER_BOUND_FAILURE_ONLY.'
        self.fs.tree_inventory.return_value={}
        with self.assertRaisesRegex(ValueError,'CACHE_ORIGINAL_TREE_DRIFT'):self.go()
    def test_source_cache_rejects_objects_archives_precompiled_and_shared_libraries(self):
        for suffix in ('.o','.a','.gch','.so'):
            self.value=inventory_value();self.value['entries'][8]['path']='obj/forbidden'+suffix
            with self.assertRaisesRegex(ValueError,'CACHE_SOURCE_ONLY_MEMBERS'):self.go()
    def test_selected_file_count_and_total_rejected(self):
        self.value['entries'][8]['path']='extra/moved.cpp'
        with self.assertRaisesRegex(ValueError,'CACHE_SOURCE_ONLY_MEMBERS'):self.go()

class BuildAndCopy(unittest.TestCase):
    def setUp(self):
        self.g=types.SimpleNamespace(need=S.need);self.work=Path('/mock/fresh')
        self.command=['/usr/bin/make','-C','/mock/fresh/obj','-f','VQwenOwnerKernel.mk','-j1','OPT_FAST=-O0','VQwenOwnerKernel']
    def test_exact_three_old_targets_no_regeneration_and_original_unmodified(self):
        before=list(self.command);actual=C.build_command(self.g,self.command,self.work)
        extra=[v for n in C.OLD_TARGETS for v in ('-o',n)]
        self.assertEqual(actual,before[:-1]+extra+[C.NO_GENERATION,'VM_HIER_RUN_DIR=/mock/fresh',before[-1]])
        self.assertEqual(actual.count('-o'),3);self.assertEqual(self.command,before)
        self.assertEqual(C.NO_GENERATION,"VM_HIER_VERILATOR=/bin/sh -c 'exit 97'")
    def test_build_guard_malformed_argv_fail_closed(self):
        mutations=[]
        for key,bad in ((0,'make'),(-1,'other')):
            v=list(self.command);v[key]=bad;mutations.append(v)
        for token in ('-f','-j1'):
            v=list(self.command);v.remove(token);mutations.append(v)
            v=list(self.command);v.insert(1,token);mutations.append(v)
        for token in ('hier_build','hier_verilation','hier_launch_verilator'):
            v=list(self.command);v.insert(-1,token);mutations.append(v)
        v=list(self.command);v[v.index('-f')+1]='different.mk';mutations.append(v)
        for command in mutations:
            with self.assertRaisesRegex(ValueError,'CACHE_EXACT_TOP_BUILD'):C.build_command(self.g,command,self.work)
    def copy_fixture(self):
        raw=b'one checked source buffer';wanted={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mode':'0o600'}
        tree={'root':'/mock/prior','entries':{'obj/a.cpp':{'kind':'regular',**wanted},'fixtures/a.hpp':{'kind':'regular',**wanted},'obj/sub':{'kind':'directory','mode':'0o700'}}}
        self.g.checked=mock.Mock(return_value=raw);fs=types.SimpleNamespace(identity=mock.Mock(return_value=wanted),tree_inventory=mock.Mock(return_value=tree));writer=types.SimpleNamespace(write_exact=mock.Mock())
        return raw,wanted,tree,fs,writer
    def test_copy_only_objects_source_same_buffer_and_exact_readback(self):
        raw,wanted,tree,fs,writer=self.copy_fixture();actual=C.stage_objects(self.g,fs,writer,tree,self.work)
        writer.write_exact.assert_called_once();self.assertIs(writer.write_exact.call_args.args[1],raw)
        self.g.checked.assert_called_once_with(Path('/mock/prior/obj/a.cpp'),{k:wanted[k] for k in ('bytes','sha256')},16*C.MIB,fixed_leaf='a.cpp')
        fs.identity.assert_called_once_with(self.work/'obj/a.cpp',16*C.MIB);self.assertEqual(actual,{'obj/a.cpp':wanted})
    def test_copy_readback_mismatch_and_original_drift_are_rejected(self):
        raw,wanted,tree,fs,writer=self.copy_fixture();fs.identity.return_value={**wanted,'mode':'0o644'}
        with self.assertRaisesRegex(ValueError,'CACHE_COPY_READBACK'):C.stage_objects(self.g,fs,writer,tree,self.work)
        fs.identity.return_value=wanted;fs.tree_inventory.return_value={}
        with self.assertRaisesRegex(ValueError,'CACHE_ORIGINAL_TREE_DRIFT'):C.stage_objects(self.g,fs,writer,tree,self.work)
    def test_copy_reader_first_exception_prevents_write(self):
        raw,wanted,tree,fs,writer=self.copy_fixture();first=ValueError('synthetic drift');self.g.checked.side_effect=first
        with self.assertRaises(ValueError) as caught:C.stage_objects(self.g,fs,writer,tree,self.work)
        self.assertIs(caught.exception,first);writer.write_exact.assert_not_called()

class Sequence(unittest.TestCase):
    def setUp(self):
        self.result={'stages':[]};self.work=Path('/mock/fresh');self.commands={'build':['make'],'run':['binary']};self.env={'FIXED':'1'}
        self.owner={'handler':object(),'deadline':960.0};self.pre=mock.Mock();self.after=mock.Mock();self.admit=mock.Mock(return_value={});self.calls=[];self.failure=None
        def phase(*args):
            self.calls.append(args);args[10]['mock']=True
            if self.failure is not None:raise self.failure
            return record(),b'synthetic log',usage()
        self.s=types.SimpleNamespace(run_phase=phase)
        patch=mock.patch.object(S.time,'monotonic',return_value=0.0);self.clock=patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(S,'observe_log',return_value={'mock':True});self.logs=patch.start();self.addCleanup(patch.stop)
    def go(self):return S.sequence(self.s,'support','base',self.work,self.commands,self.env,960.0,self.owner,self.pre,self.after,self.result,self.admit)
    def test_two_phases_fixed_budget_owner_and_limits(self):
        self.go();self.assertEqual((S.SHARED_SECONDS,S.TAIL_SECONDS),(960,60))
        self.assertEqual([x['name'] for x in self.result['stages']],['build','run'])
        for a,name,total in zip(self.calls,('build','run'),(600,300)):
            self.assertEqual(a[2],'owner_local_'+name);self.assertIs(a[3],self.commands[name]);self.assertIs(a[6],self.env)
            self.assertEqual(a[7]['total_seconds'],total);self.assertEqual(a[7]['work_seconds'],total-15);self.assertEqual(a[7]['as_bytes'],6*1024**3)
            self.assertEqual(a[8],960.0);self.assertIs(a[9],self.owner)
        self.assertEqual(self.admit.call_count,2);self.assertEqual(self.pre.call_count,6)
    def test_no_generation_or_extra_command_allowed(self):
        self.commands['generate']=[]
        with self.assertRaisesRegex(ValueError,'EXACT_TWO_COMMANDS'):self.go()
        self.assertEqual(self.calls,[])
    def test_initial_and_second_full_windows_reject_before_native(self):
        for times in ([300.001],[0.0,300.001]):
            self.clock.side_effect=times
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'):self.go()
            self.assertEqual(self.calls,[])
    def test_run_window_rejects_after_build_and_exact_boundaries_allowed(self):
        self.clock.side_effect=[0,0,0,0,600.001]
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_PHASE_WINDOW'):self.go()
        self.assertEqual(len(self.calls),1)
        for name,edge in (('build',300.0),('run',600.0)):
            self.clock.side_effect=None;self.clock.return_value=edge;S.complete_window(960.0,name)
    def test_first_native_failure_survives_secondary_log_failure(self):
        first=RuntimeError('native first');self.failure=first;self.logs.side_effect=OSError('log second')
        with self.assertRaises(RuntimeError) as caught:self.go()
        self.assertIs(caught.exception,first);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.result['stages'][0]['secondary_failure_types'],['OSError'])
    def test_admission_and_callback_failures_stop_following_phase(self):
        first=ValueError('admission');self.admit.side_effect=first
        with self.assertRaises(ValueError) as caught:self.go()
        self.assertIs(caught.exception,first);self.assertEqual(self.calls,[])
        self.admit.side_effect=None;self.admit.return_value={};self.after.side_effect=first
        with self.assertRaises(ValueError) as caught:self.go()
        self.assertIs(caught.exception,first);self.assertEqual(len(self.calls),1)
    def test_reserved_tail_blocks_log_and_retains_first_exception(self):
        first=RuntimeError('native first');self.failure=first;self.clock.side_effect=[0,0,900.0]
        with self.assertRaises(RuntimeError) as caught:self.go()
        self.assertIs(caught.exception,first);self.logs.assert_not_called()
    def test_tail_clamps_sixty_seconds_original_stop_and_first_exception(self):
        self.clock.return_value=100.0;save=mock.Mock();timer=mock.Mock();result={}
        self.assertIsNone(S.finish(None,self.work,result,None,960,save,timer));self.assertEqual(result['report_stop'],160);timer.assert_called_once_with(60)
        first=RuntimeError('native first');save.side_effect=OSError('save second')
        self.assertIs(S.finish(None,self.work,{},first,130,save,timer),first)
        self.assertEqual(timer.call_args.args,(30,));save.reset_mock()
        self.assertIs(S.finish(None,self.work,{},first,100,save,timer),first);save.assert_not_called()

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    summary={'schema':'CACHE_GATE_TWO_PHASE_COLD_V1','mode':ARGS.mode,'python_optimize':sys.flags.optimize,
             'status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'pins':{n:{'bytes':p[0],'sha256':p[1]} for n,p in PINS.items()},'native_make_rtl_network_executed':False,'actual_cache_copied':False,'full_run_mock':False,
             'process_limits':{'as_bytes':512*1024**2,'cpu_seconds':30,'fsize_bytes':16*1024**2,'cpu_affinity_count':1}}
    (HERE/('RESULT_'+ARGS.mode+'.json')).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
