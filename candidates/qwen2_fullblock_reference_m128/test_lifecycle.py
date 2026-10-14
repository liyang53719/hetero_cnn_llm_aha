#!/usr/bin/env python3
"""Cold lifecycle tests: only stdlib fake workers, never Torch, arrays or model calls."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock
sys.dont_write_bytecode = True
import recipe as R
import lifecycle as L
import guard as G
import capture as C

SCRATCH = R.ROOT/L.WORK/'cold_tests'


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True,exist_ok=True)
        cls.pins = R.load_pins()

    def temp(self):
        return tempfile.TemporaryDirectory(dir=SCRATCH)

    def fake(self,code,**kwargs):
        with self.temp() as tmp:
            out = Path(tmp)/'bootstrap';out.mkdir()
            result = G.supervise([sys.executable,'-B','-c',code],os.environ.copy(),out,**kwargs)
            files = {p.name:p.read_bytes() for p in out.iterdir()}
            return result,files

    def test_01_direct_capture_has_no_capability(self):
        with self.assertRaises(C.CaptureDisabled):
            C.capture(R.ROOT,self.pins,None,recipe=R)

    def test_02_missing_pipe_is_rejected_before_payload(self):
        for fd in (None,False,0,-1,'3'):
            with self.assertRaises(R.Rejected):
                L.claim_capability(R,self.pins,Path('/nonexistent'),'bootstrap',fd)

    def test_03_file_is_not_pipe(self):
        with self.temp() as tmp:
            p = Path(tmp)/'fake';p.write_text('{}')
            with p.open('rb') as f:
                with self.assertRaises(R.Rejected):
                    L.claim_capability(R,self.pins,Path(tmp),'bootstrap',f.fileno())

    def test_04_flags_do_not_unlock_recipe(self):
        result = subprocess.run([sys.executable,'-B',str(R.HERE/'recipe.py'),'--execute','--action','bootstrap'],
                                capture_output=True,text=True)
        self.assertEqual(result.returncode,2)

    def test_05_guard_needs_explicit_go(self):
        for args in (['--mode','bootstrap'],['--mode','frozen','--run-id','not_run']):
            p = subprocess.run([sys.executable,'-B',str(R.HERE/'guard.py'),*args],capture_output=True,text=True)
            self.assertEqual(p.returncode,2)
            self.assertIn('single go',p.stderr)

    def test_06_run_identity_is_canonical(self):
        for value in ('../x','x/y','/tmp/x','x.' ,''):
            with self.assertRaises(R.Rejected):
                L.run_path(R,value,'bootstrap')
        self.assertNotEqual(L.run_path(R,'fresh01','bootstrap'),L.run_path(R,'fresh01','frozen'))

    def test_07_frozen_cannot_accept_caller_hash(self):
        pins = copy.deepcopy(self.pins)
        pins['reference_freeze'].update(status='FROZEN_FROM_INDEPENDENT_REVIEW',independent_review_sha256='1'*64)
        for spec in pins['references'].values():
            spec.update(sha256='1'*64,native_sha256='1'*64,token_major_sha256='1'*64)
        with self.assertRaises(R.Rejected):
            R.require_frozen_references(pins)
        if R.FROZEN_CONTRACT_SHA256 is not None:
            self.assertEqual(R.FROZEN_CONTRACT_SHA256,L.identity(R.HERE/'FROZEN_CONTRACT.json')['sha256'])

    def test_08_unobserved_values_are_not_freeze(self):
        with self.assertRaises(R.Rejected):
            R.validate_observations(self.pins['references'],self.pins)

    def test_09_output_inventory_extra_missing(self):
        for outputs in ({},{**self.pins['references'],'extra':{}}):
            with self.assertRaises(R.Rejected):
                R.validate_observations(outputs,self.pins)

    def test_10_stdlib_success_child_is_bounded(self):
        r,files = self.fake("print('cold-only')")
        self.assertEqual(r['returncode'],0)
        self.assertIsNone(r['limit_reason'])
        self.assertEqual(files['stdout.log'],b'cold-only\n')
        self.assertFalse(r['rss_is_os_hard_cap'])
        self.assertTrue(r['independent_watchdog_enabled'])
        self.assertNotIn('SEAL.json',files)

    def test_11_wall_kills_process_group(self):
        r,files = self.fake('import time;time.sleep(10)',wall=0.15)
        self.assertEqual(r['limit_reason'],'wall-limit')
        self.assertLess(r['wall_seconds'],4)
        self.assertNotEqual(r['returncode'],0)
        self.assertNotIn('SEAL.json',files)

    def test_12_rss_sampling_kills_worker(self):
        r,_ = self.fake('import time;x=bytearray(96*1024*1024);time.sleep(10)',rss=64*(1<<20))
        self.assertEqual(r['limit_reason'],'sampled-process-tree-rss-limit')
        self.assertGreater(r['peak_sampled_process_tree_rss_bytes'],64*(1<<20))

    def test_13_log_prefix_is_bounded_full_hash_is_retained(self):
        r,files = self.fake("import os;os.write(1,b'a'*200000);os.write(2,b'b'*100000)")
        for key,character,count in [('stdout',b'a',200000),('stderr',b'b',100000)]:
            self.assertEqual(len(files[key+'.log']),L.LOG_RETAIN_BYTES)
            self.assertEqual(r['logs'][key]['total_bytes'],count)
            self.assertEqual(r['logs'][key]['sha256_all_observed_bytes'],hashlib.sha256(character*count).hexdigest())
            self.assertTrue(r['logs'][key]['truncated'])

    def test_14_worker_failure_keeps_real_error(self):
        r,files = self.fake("import sys;print('specific-child-failure',file=sys.stderr);sys.exit(7)")
        self.assertEqual(r['returncode'],7)
        self.assertIsNone(r['limit_reason'])
        self.assertIn(b'specific-child-failure',files['stderr.log'])

    def test_15_fork_setsid_descendant_cleanup(self):
        code = '''import os,time
pid=os.fork()
if pid==0:
 os.setsid()
 print('descendant',os.getpid(),flush=True)
 time.sleep(10)
else:
 time.sleep(10)
'''
        r,files = self.fake(code,wall=0.25)
        self.assertEqual(r['limit_reason'],'wall-limit')
        self.assertGreaterEqual(len(r['tracked_process_starts']),2)
        child_pid = int(files['stdout.log'].split()[1])
        info = G.processes().get(child_pid)
        self.assertIsNone(info)
        self.assertEqual(r['descendant_cleanup']['remaining_descendants'],{})

    def test_16_disk_cap_failure_unsealed(self):
        with self.temp() as tmp:
            out = Path(tmp)/'bootstrap';out.mkdir()
            code = "import pathlib,time;pathlib.Path(%r).write_bytes(b'x'*10000);time.sleep(10)" % str(out/'partial.bin')
            r = G.supervise([sys.executable,'-B','-c',code],os.environ.copy(),out,run_cap=5000)
            self.assertEqual(r['limit_reason'],'disk-cap')
            self.assertTrue((out/'partial.bin').exists())
            self.assertFalse((out/'SEAL.json').exists())

    def test_17_progress_is_true_last_stage(self):
        with self.temp() as tmp:
            out=Path(tmp)
            L.progress(R,out,'raw13-load');L.progress(R,out,'official-tail-execution')
            self.assertEqual(L.last_stage(R,out),'official-tail-execution')

    def test_18_boundary_failure_keeps_partial_identity(self):
        with self.temp() as tmp:
            out=Path(tmp)/'bootstrap'
            with mock.patch.object(R,'source_check'), mock.patch.object(L,'run_path',return_value=out), \
                 mock.patch.object(L,'validate_go',return_value={'receipt':{},'content':{}}), \
                 mock.patch.object(L,'snapshot',side_effect=R.Rejected('raw-drift-before-import')):
                with self.assertRaises(R.Rejected):
                    G.run('bootstrap','test_only','not-used')
            failure=R.parse((out/'FAILURE.json').read_bytes())
            self.assertEqual(failure['stage'],'wrapper-boundary-before')
            self.assertIn('raw-drift-before-import',failure['error'])
            self.assertIn('GO.json',failure['partial_files'])
            self.assertFalse(failure['completion_seal_written'])
            self.assertFalse((out/'SEAL.json').exists())

    def test_19_no_existing_run_overwrite(self):
        with self.temp() as tmp:
            out=Path(tmp)/'bootstrap';out.mkdir();(out/'sentinel').write_text('original')
            with mock.patch.object(R,'source_check'),mock.patch.object(L,'run_path',return_value=out):
                with self.assertRaisesRegex(R.Rejected,'never overwritten'):
                    G.run('bootstrap','test_only','not-used')
            self.assertEqual((out/'sentinel').read_text(),'original')

    def test_20_stream_hash_is_byte_equivalent(self):
        with self.temp() as tmp:
            p=Path(tmp)/'bytes';data=bytes(range(256))*17000;p.write_bytes(data)
            self.assertEqual(L.identity(p),{'bytes':len(data),'sha256':R.sha(data)})

    def test_21_no_model_inputs_or_numeric_imports_in_cold_process(self):
        self.assertFalse(set(('torch','numpy','transformers'))&set(sys.modules))
        self.assertEqual(self.pins['budget']['bootstrap_plus_frozen_payload_bytes'],65208320)

    def test_22_future_body_keeps_exact_official_call_slices(self):
        tree=ast.parse((R.HERE/'capture.py').read_text())
        slices=[]
        for node in sorted((n for n in ast.walk(tree) if isinstance(n,ast.Call)),key=lambda n:(n.lineno,n.col_offset)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='execute' and node.args:
                arg=node.args[0]
                if isinstance(arg,ast.Subscript) and isinstance(arg.value,ast.Name) and arg.value.id=='nodes':
                    slices.append((0 if arg.slice.lower is None else arg.slice.lower.value,arg.slice.upper.value))
        self.assertEqual(slices,[(0,4),(15,16),(27,28),(4,7),(28,29),(29,31),(31,32),
            (7,10),(10,13),(13,15),(16,18),(18,20),(20,21),(21,22),(22,23),(23,25),(25,27),
            (32,33),(33,34),(34,35),(35,36),(36,37),(37,38)])

    def test_23_no_early_return_in_capture_body(self):
        tree=ast.parse((R.HERE/'capture.py').read_text())
        body=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capture').body
        self.assertEqual([i for i,n in enumerate(body) if isinstance(n,ast.Return)],[len(body)-1])

    def test_24_pinned_prior18_metadata_comparison_remains_whole(self):
        source=(R.HERE/'capture.py').read_text()
        self.assertIn("R.same(actual,pins['prior18_expectations'][name])",source)
        self.assertIn("hook_order == ['gate','silu','up','act','down']",source)
        self.assertIn("float(torch.max(torch.abs(outputs['softmax_fp32'].sum(dim=-1)-1))) <= 2e-5",source)

    def test_25_watcher_setup_failure_cleans_started_worker(self):
        real=G.subprocess.Popen
        children=[]
        def fail_second(*args,**kwargs):
            if children:
                raise OSError('injected watcher startup failure')
            child=real(*args,**kwargs);children.append(child);return child
        with self.temp() as tmp, mock.patch.object(G.subprocess,'Popen',side_effect=fail_second):
            out=Path(tmp)/'bootstrap';out.mkdir()
            with self.assertRaisesRegex(OSError,'injected watcher'):
                G.supervise([sys.executable,'-B','-c','import time;time.sleep(10)'],os.environ.copy(),out)
        self.assertIsNotNone(children[0].poll())

    def test_26_log_setup_failure_cleans_started_worker(self):
        real_open=Path.open;real_popen=G.subprocess.Popen;children=[]
        def capture_child(*args,**kwargs):
            child=real_popen(*args,**kwargs);children.append(child);return child
        def fail_log(path,*args,**kwargs):
            if path.name=='stderr.log':
                raise OSError('injected log startup failure')
            return real_open(path,*args,**kwargs)
        with self.temp() as tmp, mock.patch.object(G.subprocess,'Popen',side_effect=capture_child), \
             mock.patch.object(Path,'open',fail_log):
            out=Path(tmp)/'bootstrap';out.mkdir()
            with self.assertRaisesRegex(OSError,'injected log'):
                G.supervise([sys.executable,'-B','-c','import time;time.sleep(10)'],os.environ.copy(),out)
        self.assertTrue(all(child.poll() is not None for child in children))

    def test_27_overall_watchdog_covers_preflight_worker_and_postflight(self):
        for stage,spawn_child in [('wrapper-boundary-before',False),('official-tail-execution',True),
                                  ('wrapper-boundary-after',False)]:
            with self.subTest(stage=stage),self.temp() as tmp:
                out=Path(tmp)/'bootstrap'
                code = """import sys,time,subprocess,json,os
from pathlib import Path
sys.path.insert(0,%r)
import guard as G
G.L.WALL_SECONDS=0.15
out=Path(%r)
G.L.run_path=lambda *args:out
def body(mode,run_id,go,start,deadline,watcher_pid):
 out.mkdir()
 G.L.progress(G.R,out,%r)
 child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(20)'],start_new_session=True) if %r else None
 G.L.write_new(G.R,out/'COLD_RUNTIME.json',{'watcher_pid':watcher_pid,'child_pid':None if child is None else child.pid})
 time.sleep(20)
G.run_body=body
G.run('bootstrap','cold_only','no_actual_go')
""" % (str(R.HERE),str(out),stage,spawn_child)
                subject=subprocess.Popen([sys.executable,'-B','-c',code],start_new_session=True,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    subject.wait(timeout=6)
                    self.assertNotEqual(subject.returncode,0)
                    deadline=time.monotonic()+3
                    while not (out/'FAILURE.json').exists() and time.monotonic()<deadline:
                        time.sleep(0.02)
                    failure=R.parse((out/'FAILURE.json').read_bytes())
                    self.assertEqual(failure['stage'],stage)
                    self.assertEqual(failure['reason'],'overall-122s-watchdog')
                    self.assertFalse((out/'SEAL.json').exists())
                    recorded=R.parse((out/'COLD_RUNTIME.json').read_bytes())
                    for pid in recorded.values():
                        if pid is None: continue
                        until=time.monotonic()+2
                        while time.monotonic()<until:
                            try: os.waitpid(pid,os.WNOHANG)
                            except ChildProcessError: pass
                            info=G.processes().get(pid)
                            if info is None: break
                            time.sleep(0.02)
                        self.assertIsNone(G.processes().get(pid))
                finally:
                    if subject.poll() is None:
                        os.killpg(subject.pid,9);subject.wait(timeout=2)

    def test_28_one_go_binds_review_mode_tools_and_exact_source(self):
        with self.temp() as tmp,mock.patch.object(L,'WORK',str(SCRATCH.relative_to(R.ROOT))):
            out=Path(tmp)
            source=R.source_manifest()
            review={'status':'APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP','mode':'bootstrap','source_manifest':source,
                    'numeric_executed':False,'reviewer':'independent-cold-fixture',
                    'tool_identity':{'python_executable':self.pins['runtime_native_files']['python'],
                    'implementation':'cpython','python_major_minor':[3,12],'source_manifest':source}}
            L.write_new(R,out/'REVIEW.json',review)
            review_spec={'path':str((out/'REVIEW.json').relative_to(R.ROOT)),**L.identity(out/'REVIEW.json')}
            go={'schema':1,'action':'single-bootstrap','run_id':'cold_fixture','source_manifest':source,
                'source_review':review_spec,'issued_by':'parent-cold-fixture','maximum_invocations':1,
                'no_retry':True,'exclusive_numeric_slot':True}
            L.write_new(R,out/'GO.json',go)
            relative=str((out/'GO.json').relative_to(R.ROOT))
            self.assertEqual(L.validate_go(R,self.pins,relative,'cold_fixture','bootstrap')['content'],go)
            for update in ({'run_id':'other'},{'maximum_invocations':2},{'exclusive_numeric_slot':False},
                           {'source_manifest':{'bytes':1,'sha256':'1'*64}},{'issued_by':review['reviewer']}):
                bad={**go,**update};(out/'GO.json').write_bytes(R.encoded(bad))
                with self.assertRaises(R.Rejected):
                    L.validate_go(R,self.pins,relative,'cold_fixture','bootstrap')

    def test_29_parent_script_slot_and_full_bindings(self):
        cap={'mode':'bootstrap','run_id':'cold_fixture'}
        go={'receipt':{'path':'work/cold-go.json'}}
        exe=self.pins['runtime_native_files']['python']['path']
        tail=['--mode','bootstrap','--run-id','cold_fixture','--go','work/cold-go.json']
        for script in (str(R.HERE/'guard.py'),R.PACKAGE+'/guard.py'):
            L.verify_parent_entry(R,self.pins,[exe,'-B',script,*tail],str(R.ROOT),exe,cap,go)
        invalid=[[exe,'-B','-c',*tail],[exe,'-B','-m',*tail],
                 [exe,'-B',str(R.HERE/'recipe.py'),*tail],
                 [exe,'-B',str(R.HERE/'guard.py'),'--mode','frozen',*tail[2:]],
                 [exe,'-B',str(R.HERE/'guard.py'),*tail[:-1],'different-go.json']]
        for args in invalid:
            with self.assertRaises((R.Rejected,OSError)):
                L.verify_parent_entry(R,self.pins,args,str(R.ROOT),exe,cap,go)
        with self.assertRaises(R.Rejected):
            L.verify_parent_entry(R,self.pins,[exe,'-B',str(R.HERE/'guard.py'),*tail],'/tmp',exe,cap,go)
        with self.assertRaises(R.Rejected):
            L.verify_parent_entry(R,self.pins,[exe,'-B',str(R.HERE/'guard.py'),*tail],str(R.ROOT),'/bin/false',cap,go)

    def test_30_real_relative_and_absolute_guard_cli_cold_handshakes(self):
        # Test-only sitecustomize replaces raw snapshots and the sole numerical
        # Popen with a stdlib capability probe. Unknown child commands fail closed.
        # The real parent argv, cwd, executable, inherited pipe and CLI are tested.
        for index,script in enumerate((R.PACKAGE+'/guard.py',str(R.HERE/'guard.py'))):
            with self.subTest(script=script),self.temp() as tmp:
                base=Path(tmp);fixture_work=str(base.relative_to(R.ROOT));run_id='cold_entry_'+str(index)
                source=R.source_manifest()
                review={'status':'APPROVED_SOURCE_FOR_SINGLE_BOOTSTRAP','mode':'bootstrap','source_manifest':source,
                    'numeric_executed':False,'reviewer':'independent-cold-fixture','tool_identity':{
                    'python_executable':self.pins['runtime_native_files']['python'],'implementation':'cpython',
                    'python_major_minor':[3,12],'source_manifest':source}}
                L.write_new(R,base/'REVIEW.json',review)
                go={'schema':1,'action':'single-bootstrap','run_id':run_id,'source_manifest':source,
                    'source_review':{'path':fixture_work+'/REVIEW.json',**L.identity(base/'REVIEW.json')},
                    'issued_by':'parent-cold-fixture','maximum_invocations':1,'no_retry':True,'exclusive_numeric_slot':True}
                L.write_new(R,base/'GO.json',go)
                helper=base/'cold_worker.py'
                helper.write_text("""import sys,json
from pathlib import Path
sys.path.insert(0,%r)
import recipe as R,lifecycle as L
L.WORK=%r
try:
 L.claim_capability(R,R.load_pins(),Path(sys.argv[3]),sys.argv[2],int(sys.argv[1]))
 print(json.dumps({'status':'COLD_CAPABILITY_ACCEPTED','numeric_imported':any(n in sys.modules for n in ('torch','numpy','transformers'))}),flush=True)
except BaseException as error:
 print(json.dumps({'status':'COLD_CAPABILITY_REJECTED','error':str(error)}),flush=True)
raise SystemExit(99)
""" % (str(R.HERE),fixture_work))
                (base/'sitecustomize.py').write_text("""import sys,subprocess
from pathlib import Path
sys.path.insert(0,%r)
import recipe as R,lifecycle as L
L.WORK=%r
L.snapshot=lambda *args:{'source_manifest':R.source_manifest()}
original=subprocess.Popen
def cold_popen(command,*args,**kwargs):
 if len(command)>3 and command[2]==str(R.HERE/'guard.py'):
  if command[3]=='--worker':
   command=[command[0],'-B',%r,*command[4:]]
  elif command[3] not in ('--supervisor-watchdog','--watchdog'):
   raise RuntimeError('cold fixture refuses unknown child')
 else:
  raise RuntimeError('cold fixture refuses all other children')
 return original(command,*args,**kwargs)
subprocess.Popen=cold_popen
""" % (str(R.HERE),fixture_work,str(helper)))
                env=os.environ.copy();env['PYTHONPATH']=str(base);env['PYTHONDONTWRITEBYTECODE']='1'
                result=subprocess.run([sys.executable,'-B',script,'--mode','bootstrap','--run-id',run_id,
                    '--go',fixture_work+'/GO.json'],cwd=R.ROOT,env=env,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,2,result.stderr)
                out=base/run_id/'bootstrap'
                observed=R.parse((out/'stdout.log').read_bytes())
                self.assertEqual(observed,{'status':'COLD_CAPABILITY_ACCEPTED','numeric_imported':False})
                failure=R.parse((out/'FAILURE.json').read_bytes())
                self.assertEqual(failure['resources']['returncode'],99)
                self.assertFalse((out/'SEAL.json').exists())
                self.assertFalse((out/'OBSERVATIONS.json').exists())

    def test_31_real_python_c_disguised_parent_cannot_claim(self):
        with self.temp() as tmp:
            base=Path(tmp);fixture_work=str(base.relative_to(R.ROOT));out=base/'fake'/'bootstrap';out.mkdir(parents=True)
            helper=base/'cold_worker.py'
            helper.write_text("""import sys,json
from pathlib import Path
sys.path.insert(0,%r)
import recipe as R,lifecycle as L
L.WORK=%r
try:
 L.claim_capability(R,R.load_pins(),Path(sys.argv[2]),'bootstrap',int(sys.argv[1]))
 result={'status':'WRONGLY_ACCEPTED'}
except R.Rejected as error:
 result={'status':'REJECTED','error':str(error)}
result['numeric_imported']=any(n in sys.modules for n in ('torch','numpy','transformers'))
print(json.dumps(result))
""" % (str(R.HERE),fixture_work))
            code="""import sys,os,subprocess
from pathlib import Path
sys.path.insert(0,%r)
import recipe as R,lifecycle as L
out=Path(%r)
go={'content':{'action':'single-bootstrap','run_id':'fake','source_manifest':R.source_manifest()},'receipt':{'path':'no-go'}}
L.write_new(R,out/'GO.json',go)
r,w=os.pipe()
cap={'schema':1,'parent_pid':os.getpid(),'run_id':'fake','mode':'bootstrap','out':str(out.relative_to(R.ROOT)),'source_manifest':R.source_manifest(),'go_sha256':L.identity(out/'GO.json')['sha256']}
os.write(w,R.encoded(cap));os.close(w)
p=subprocess.run([sys.executable,'-B',%r,str(r),str(out)],pass_fds=(r,),start_new_session=True,capture_output=True,text=True)
os.close(r);print(p.stdout,end='')
""" % (str(R.HERE),str(out),str(helper))
            result=subprocess.run([sys.executable,'-B','-c',code,str(R.HERE/'guard.py'),'--mode','bootstrap',
                '--run-id','fake','--go','no-go'],cwd=R.ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            observed=R.parse(result.stdout)
            self.assertEqual(observed['status'],'REJECTED')
            self.assertIn('exact Python -B guard CLI',observed['error'])
            self.assertFalse(observed['numeric_imported'])

    def test_32_real_direct_worker_with_no_capability_is_cold(self):
        result=subprocess.run([sys.executable,'-B',str(R.HERE/'guard.py'),'--worker','0','bootstrap','/not-a-run'],
                              cwd=R.ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2)
        self.assertIn('capture requires live bounded-wrapper capability',result.stderr)

    def test_33_frozen_contract_is_exact_reviewed29_metadata_only(self):
        original=Path.open
        def no_payload(path,*args,**kwargs):
            if path.suffix in ('.bin','.f32le','.bf16le','.npy','.npz'):
                raise AssertionError('frozen metadata must not open payloads')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'open',no_payload):
            frozen=R.require_frozen_references(self.pins)
        self.assertEqual(set(frozen['outputs']),R.NAMES)
        self.assertEqual(frozen['status'],'FROZEN_FROM_INDEPENDENT_REVIEW')
        self.assertEqual(frozen['review']['sha256'],'b5baa8bdeaa2a4b1faff81fc01a454588164a8ffbc9a2c07057360d80a2f7ddb')
        self.assertFalse(set(('torch','numpy','transformers'))&set(sys.modules))

    def test_34_unpinned_or_wrong_code_digest_cannot_load_freeze(self):
        for digest in (None,'0'*64,'1'*64):
            with mock.patch.object(R,'FROZEN_CONTRACT_SHA256',digest):
                with self.assertRaises(R.Rejected):
                    R.require_frozen_references(self.pins)

    def test_35_changed_frozen_tail_cannot_learn_a_new_hash(self):
        frozen=R.require_frozen_references(self.pins)
        frozen['outputs']['y']['sha256']='1'*64
        with self.temp() as tmp:
            p=Path(tmp)/'tampered.json';p.write_bytes(R.encoded(frozen))
            original=R.safe_path
            def choose(root,relative):
                return p if relative==R.FROZEN_CONTRACT_FILE else original(root,relative)
            with mock.patch.object(R,'safe_path',choose):
                with self.assertRaisesRegex(R.Rejected,'code-pinned frozen contract drift'):
                    R.require_frozen_references(self.pins)

    def test_36_changed_contract_digest_still_cannot_forge_independent_review(self):
        frozen=R.require_frozen_references(self.pins)
        frozen['outputs']['y']['sha256']='1'*64
        with self.temp() as tmp:
            p=Path(tmp)/'tampered.json';p.write_bytes(R.encoded(frozen));original=R.safe_path
            def choose(root,relative):
                return p if relative==R.FROZEN_CONTRACT_FILE else original(root,relative)
            with mock.patch.object(R,'safe_path',choose),mock.patch.object(R,'FROZEN_CONTRACT_SHA256',L.identity(p)['sha256']):
                with self.assertRaisesRegex(R.Rejected,'independent bootstrap review'):
                    R.require_frozen_references(self.pins)


if __name__ == '__main__':
    unittest.main(verbosity=2)
