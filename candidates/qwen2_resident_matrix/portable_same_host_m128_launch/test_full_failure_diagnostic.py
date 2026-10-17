"""Stdlib-only synthetic metadata/ownership/privacy regressions; no numerical work."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
D=load('full_failure_tested',HERE/'full_failure_diagnostic.py');R=load('parent_failure_tested',HERE/'run.py');L=R.load_launcher(ROOT)

class Progress(unittest.TestCase):
    def fixture(self):
        return dict(status='FAILED',rows=128,source_sha256={'a.py':'a'*64},snapshot_sha256='b'*64,
            old_pass_inherited=False,rtl_executed=False,scala_executed=False,host_wall_seconds=899.5,
            prefix_host_wall_seconds=200,prefix_execution=[{'pc':i,'secret':'NEVER_EXPORT'} for i in range(10)],
            failed_host=dict(completions=[{'pc':i,'status':None,'address':'NEVER_EXPORT'} for i in range(14)],
                accepted={'completion_fire':14,'request_fire':12,'owner_result_fire':11,'result_fire':0,'host_model_ticks':500000,'secret':'NEVER_EXPORT'},
                launch_result=None),error='NEVER_EXPORT',failed_memory={'secret':'NEVER_EXPORT'})
    def project(self,v):return D.progress(D.encoded(v),{'a.py':'a'*64},'b'*64)
    def test_fixed_projection_discards_payload_messages_addresses(self):
        v=self.project(self.fixture());self.assertEqual(v['completed_public_pcs'],list(range(14)))
        self.assertTrue(v['reported_prefix_complete']);self.assertEqual(v['numeric_elapsed_seconds'],899.5)
        self.assertNotIn('NEVER_EXPORT',D.encoded(v).decode());self.assertNotIn('error',v)
    def test_all_explicit_statuses(self):
        for status in D.STATUSES:
            v=self.fixture();v['status']=status;self.assertEqual(self.project(v)['reported_status'],status)
    def test_status_payload_rejected(self):
        for value in ('secret',None,True,{},[]):
            v=self.fixture();v['status']=value
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):self.project(v)
    def test_source_snapshot_rows_flags_typed(self):
        for key,bad in (('source_sha256',{}),('snapshot_sha256','c'*64),('rows',True),('rows',128.0),('rows',16),('old_pass_inherited',0),('rtl_executed',0),('scala_executed',1)):
            v=self.fixture();v[key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.project(v)
    def test_prefix_must_be_exact_complete_ten(self):
        for changed in ('short','reorder','bool','extra'):
            v=self.fixture();p=v['prefix_execution']
            if changed=='short':p.pop()
            elif changed=='reorder':p[0]['pc']=1
            elif changed=='bool':p[0]['pc']=False
            else:p.append({'pc':10})
            with self.subTest(changed=changed),self.assertRaises(ValueError):self.project(v)
    def test_missing_prefix_is_unknown_not_false_or_zero(self):
        v=self.fixture();del v['prefix_execution'];self.assertIsNone(self.project(v)['reported_prefix_complete'])
    def test_completions_are_bounded_contiguous_typed(self):
        for bad in ([{'pc':True,'status':None}],[{'pc':1,'status':None}], [{'pc':i,'status':None} for i in range(22)]):
            v=self.fixture();v['failed_host']['completions']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.project(v)
    def test_missing_host_is_unknown(self):
        v=self.fixture();del v['failed_host'];self.assertIsNone(self.project(v)['completed_public_pcs'])
    def test_present_null_host_and_missing_status_fail_closed(self):
        v=self.fixture();v['execution']={'host':v['failed_host']};v['failed_host']=None
        with self.assertRaises(ValueError):self.project(v)
        v=self.fixture();del v['failed_host']['completions'][0]['status']
        with self.assertRaises(ValueError):self.project(v)
    def test_execution_host_fallback(self):
        v=self.fixture();v['execution']={'host':v.pop('failed_host')};self.assertEqual(len(self.project(v)['completed_public_pcs']),14)
    def test_counter_types_and_limits(self):
        for key,maximum in D.COUNTERS.items():
            for bad in (True,-1,maximum+1,1.0,'1'):
                v=self.fixture();v['failed_host']['accepted'][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.project(v)
    def test_launch_limits(self):
        v=self.fixture();v['failed_host']['launch_result']={'completed':21,'jobs':17,'status':None,'payload':'NEVER_EXPORT'}
        self.assertEqual(self.project(v)['reported_launch_jobs'],17)
        for key,bad in (('completed',22),('completed',True),('jobs',18),('jobs',False)):
            w=copy.deepcopy(v);w['failed_host']['launch_result'][key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):self.project(w)
    def test_reset_and_validated_dispatch_keys_only(self):
        v=self.fixture();v['failed_host'].update(reset_required=True,validated_policy_jobs={'0':{'address':'NEVER_EXPORT'},'12':{},'20':{}})
        out=self.project(v);self.assertTrue(out['reset_required']);self.assertEqual(out['validated_dispatch_pcs'],[0,12,20])
        self.assertNotIn('NEVER_EXPORT',D.encoded(out).decode())
        for value in ({'10':{}},{'11':{}},{'21':{}},{'00':{}},{'secret':{}},[]):
            w=copy.deepcopy(v);w['failed_host']['validated_policy_jobs']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.project(w)
        v['failed_host']['reset_required']=1
        with self.assertRaises(ValueError):self.project(v)
    def test_launch_status_closed_allowlist(self):
        for status in D.CONTROL_STATUSES:
            v=self.fixture();v['failed_host']['launch_result']={'completed':14,'jobs':12,'status':status}
            self.assertEqual(self.project(v)['reported_launch_status'],status)
        v['failed_host']['launch_result']['status']='NEVER_EXPORT'
        with self.assertRaises(ValueError):self.project(v)
    def test_elapsed_typed_finite_bounded(self):
        for bad in (True,-1,4921,'1',float('inf'),float('nan')):
            v=self.fixture();v['host_wall_seconds']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):self.project(v)
    def test_json_duplicate_nonfinite_depth_size(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'['*45+b'0'+b']'*45,b' '*(D.MAX_SUMMARY+1)):
            with self.subTest(raw=raw[:60]),self.assertRaises(ValueError):D.strict(raw)
    def test_read_rejects_alias_link_directory_oversize(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'file';p.write_bytes(b'1234')
            self.assertEqual(D.bounded_file(p,4),b'1234')
            with self.assertRaises(ValueError):D.bounded_file(p,3)
            link=p.with_name('link');link.symlink_to(p)
            with self.assertRaises(ValueError):D.bounded_file(link,4)
            link.unlink();os.link(p,link)
            with self.assertRaises(ValueError):D.bounded_file(p,4)
            with self.assertRaises(ValueError):D.bounded_file(Path(td),10000)

    def test_all_4920_second_elapsed_bounds_and_missing_values(self):
        keys=(('host_wall_seconds','numeric_elapsed_seconds'),('prefix_host_wall_seconds','prefix_elapsed_seconds'),
              ('whole_terminal_host_wall_seconds','terminal_elapsed_seconds'))
        for source,target in keys:
            v=self.fixture();v[source]=4920
            self.assertEqual(self.project(v)[target],4920)
            for bad in (True,-1,4920.01,4921,'4920'):
                v[source]=bad
                with self.subTest(source=source,bad=bad),self.assertRaises(ValueError):self.project(v)
            del v[source];self.assertIsNone(self.project(v)[target])
    def test_complete_control_bounds_and_projection_contains_no_values(self):
        v=self.fixture();host=v['failed_host']
        host['completions']=[{'pc':i,'status':None,'values':['PRIVATE_VALUES',i]} for i in range(21)]
        host['validated_policy_jobs']={str(pc):{'values':['PRIVATE_VALUES',pc]} for pc in D.DISPATCH_PCS}
        host['launch_result']={'completed':21,'jobs':17,'status':None,'raw_log':'PRIVATE_RAW_LOG'}
        host['accepted'].update(completion_fire=21,owner_result_fire=17,request_fire=17)
        v.update(raw_log='PRIVATE_RAW_LOG',values=['PRIVATE_VALUES'],memory_contents={'secret':'PRIVATE_MEMORY'})
        projected=self.project(v)
        self.assertEqual(projected['completed_public_pcs'],list(range(21)))
        self.assertEqual(projected['validated_dispatch_pcs'],sorted(D.DISPATCH_PCS))
        self.assertEqual(projected['reported_launch_jobs'],17)
        self.assertEqual(set(projected),{'status','reported_status','summary_sha256','snapshot_sha256',
            'reported_prefix_complete','completed_public_pcs','host_counters','reported_launch_completed',
            'reported_launch_jobs','reported_launch_status','reset_required','validated_dispatch_pcs',
            'numeric_elapsed_seconds','prefix_elapsed_seconds','terminal_elapsed_seconds'})
        raw=D.encoded(projected).decode()
        for private in ('PRIVATE_VALUES','PRIVATE_RAW_LOG','PRIVATE_MEMORY','NEVER_EXPORT','memory_contents','raw_log'):
            self.assertNotIn(private,raw)

class Observer(unittest.TestCase):
    def fixture(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);base=Path(temp.name);root=base/'root';out=base/'out'
        root.mkdir();(out/'source128').mkdir(parents=True);(out/'full_m128/actual').mkdir(parents=True);(out/'full_m128/snapshot').mkdir()
        source=out/'source128/fixture.py';source.write_text('raise ValueError("NEVER_EXPORT")\n');sources={'fixture.py':D.sha(source.read_bytes())}
        parser=root/D.PARSER;parser.parent.mkdir(parents=True);parser.write_bytes((ROOT/D.PARSER).read_bytes())
        worker=root/D.OWN/'worker.py';worker.parent.mkdir(parents=True);worker.write_text('# fixed synthetic worker\n')
        pins={'inputs':{D.PARSER:D.sha(parser.read_bytes()),D.OWN+'worker.py':D.sha(worker.read_bytes())}}
        snapshot=out/'full_m128/snapshot/SNAPSHOT.json';snapshot.write_bytes(b'{"private":"NEVER_EXPORT"}\n')
        value=Progress().fixture();value['source_sha256']=sources;value['snapshot_sha256']=D.sha(snapshot.read_bytes())
        (out/'full_m128/actual/summary.json').write_bytes(D.encoded(value))
        (out/'full_m128.log').write_text('Traceback (most recent call last):\n  File "'+str(source)+'", line 1, in runtime\n    raise ValueError("NEVER_EXPORT")\nValueError: NEVER_EXPORT\n')
        context=dict(parent_pid=os.getpid(),out=str(out),origin=str(root),source_manifest_sha256=D.sha(D.encoded(sources)),outer_deadline=time.monotonic()+2430)
        raw=D.encoded(context);(out/'M128_RUN_CONTEXT.json').write_bytes(raw)
        event=dict(phase='full_m128',pid=123,observed_exit_code=1,final_exit_code=1,owned_group_cleanup_complete=True,status='FAILED')
        return root,out,pins,sources,context,D.sha(raw),[event]
    def call(self,f,deadline=None):
        root,out,pins,sources,context,context_sha,journal=f
        return D.observe(L,pins,root,out,journal,sources=sources,run_context=context,run_context_sha256=context_sha,deadline=time.monotonic()+2 if deadline is None else deadline)
    def test_exact_owned_log_metadata_and_context(self):
        f=self.fixture();v=self.call(f);self.assertEqual(v['reason'],'BOUNDED_FAILURE_OBSERVATIONS')
        self.assertEqual(v['traceback']['exception_class'],'ValueError');self.assertEqual(v['progress']['completed_public_pcs'],list(range(14)))
        self.assertFalse(v['acceptance']);self.assertFalse(v['origin_authenticated']);self.assertNotIn('NEVER_EXPORT',D.encoded(v).decode())
        self.assertNotIn(str(f[1]),D.encoded(v).decode())
    def test_real_owned_stdlib_failure_yields_pinned_frame_after_cleanup(self):
        f=list(self.fixture());root,out,pins,sources,context,context_sha,_=f
        (out/'full_m128.log').unlink();journal=[];f[-1]=journal
        control=L.helper(ROOT,L.load_contract(ROOT));start=time.monotonic()
        try:
            with self.assertRaises(ValueError):
                R.load_m16(ROOT).owned_phase(L,control,[sys.executable,'-I','-B',out/'source128/fixture.py'],cwd=out,
                    env={'PATH':'/usr/bin:/bin'},log=out/'full_m128.log',work_deadline=start+2,
                    cleanup_deadline=start+3,journal=journal,phase='full_m128')
            self.assertTrue(journal[0]['owned_group_cleanup_complete']);self.assertEqual(journal[0]['observed_exit_code'],1)
            v=self.call(f);self.assertEqual(v['traceback']['exception_class'],'ValueError')
            self.assertEqual(v['traceback']['frames'],[{'path':'fixture.py','sha256':sources['fixture.py'],'line':1}])
            self.assertNotIn('NEVER_EXPORT',D.encoded(v).decode())
        finally:control.protect_cleanup()
    def test_ownership_rejects_before_read(self):
        for key,bad in (('pid',True),('observed_exit_code',0),('observed_exit_code',True),('final_exit_code',2),('owned_group_cleanup_complete',False),('status','TIMEOUT')):
            f=self.fixture();f[-1][0][key]=bad
            with self.subTest(key=key,bad=bad),mock.patch.object(D,'bounded_file',side_effect=AssertionError('must not read')):
                self.assertEqual(self.call(f)['reason'],'OWNERSHIP_NOT_ESTABLISHED')
    def test_duplicate_child_rejected(self):
        f=self.fixture();f[-1].append(dict(f[-1][0]));self.assertEqual(self.call(f)['reason'],'OWNERSHIP_NOT_ESTABLISHED')
    def test_expired_local_budget_no_read(self):
        with mock.patch.object(D,'bounded_file',side_effect=AssertionError('must not read')):
            self.assertEqual(self.call(self.fixture(),time.monotonic()-1)['reason'],'DIAGNOSTIC_BUDGET')
    def test_context_drift_no_observation(self):
        f=self.fixture();(f[1]/'M128_RUN_CONTEXT.json').write_bytes(b'{}\n');v=self.call(f)
        self.assertEqual(v['reason'],'SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE');self.assertIsNone(v['traceback'])
    def test_source_drift_no_observation(self):
        f=self.fixture();(f[1]/'source128/fixture.py').write_text('raise RuntimeError()\n');self.assertEqual(self.call(f)['reason'],'SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE')
    def test_missing_metadata_retains_trace(self):
        f=self.fixture();(f[1]/'full_m128/actual/summary.json').unlink();v=self.call(f)
        self.assertEqual(v['traceback']['status'],'OBSERVED');self.assertEqual(v['progress']['status'],'UNAVAILABLE')
    def test_missing_trace_retains_progress(self):
        f=self.fixture();(f[1]/'full_m128.log').unlink();v=self.call(f)
        self.assertEqual(v['traceback']['status'],'UNAVAILABLE');self.assertEqual(v['progress']['status'],'OBSERVED')
    def test_poisoned_parser_is_unavailable(self):
        f=self.fixture();p=f[0]/D.PARSER;p.write_text('raise RuntimeError("NEVER_EXPORT")\n');v=self.call(f)
        self.assertEqual(v['reason'],'SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE');self.assertNotIn('NEVER_EXPORT',D.encoded(v).decode())
    def test_local_budget_expiry_returns_unavailable(self):
        f=self.fixture()
        with mock.patch.object(D.time,'monotonic',side_effect=[0,0,0,0,2]):
            v=self.call(f,deadline=2)
        self.assertEqual(v['reason'],'SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE');self.assertFalse(v['acceptance'])
    def test_global_timeout_is_not_swallowed_or_rearmed(self):
        f=self.fixture()
        with mock.patch.object(D,'bounded_file',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):self.call(f)
    def test_m16_phase_cannot_authorize_m128_observation(self):
        f=self.fixture();f[-1][0]['phase']='full_m16'
        with mock.patch.object(D,'bounded_file',side_effect=AssertionError('must not read')):
            self.assertEqual(self.call(f)['reason'],'OWNERSHIP_NOT_ESTABLISHED')
    def test_summary_or_snapshot_over_four_mib_is_unavailable(self):
        for name in ('full_m128/actual/summary.json','full_m128/snapshot/SNAPSHOT.json'):
            f=self.fixture()
            with (f[1]/name).open('wb') as stream:stream.truncate(D.MAX_SUMMARY+1)
            with self.subTest(name=name):
                v=self.call(f);self.assertEqual(v['traceback']['status'],'OBSERVED')
                self.assertEqual(v['progress'],{'status':'UNAVAILABLE','reason':'METADATA_UNAVAILABLE'})
                self.assertFalse(v['acceptance'])
    def test_log_bound_stays_64_kib_and_raw_log_never_exported(self):
        f=self.fixture();p=f[1]/'full_m128.log'
        raw=p.read_bytes();p.write_bytes(b'PRIVATE_RAW_LOG tensor=[1,2,3] address=0xfeed\n'+raw)
        v=self.call(f);self.assertEqual(v['traceback']['exception_class'],'ValueError')
        self.assertNotIn('PRIVATE_RAW_LOG',D.encoded(v).decode());self.assertNotIn('0xfeed',D.encoded(v).decode())
        p.write_bytes(b'x'*65536);self.assertEqual(len(L.diagnostic_log(p)),65536)
        p.write_bytes(b'x'*65537);v=self.call(f)
        self.assertEqual(v['traceback'],{'status':'UNAVAILABLE','reason':'LOG_OR_PARSER_UNAVAILABLE'})
        self.assertEqual(v['progress']['status'],'OBSERVED')
    def test_parent_and_context_source_binding_fail_closed(self):
        for key,bad in (('parent_pid',os.getpid()+1),('out','/different'),('origin','/different'),
                        ('source_manifest_sha256','f'*64)):
            f=list(self.fixture());f[4][key]=bad;raw=D.encoded(f[4]);f[5]=D.sha(raw)
            (f[1]/'M128_RUN_CONTEXT.json').write_bytes(raw)
            with self.subTest(key=key):
                v=self.call(f);self.assertEqual(v['reason'],'SOURCE_CONTEXT_OR_BUDGET_UNAVAILABLE')
                self.assertIsNone(v['traceback']);self.assertIsNone(v['progress'])
    def test_parent_diagnostic_timeout_propagates(self):
        with mock.patch.object(R,'cold_load',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                R.full_failure_observation(L,{'inputs':{D.OWN+'full_failure_diagnostic.py':'a'*64}},ROOT,Path('/unused'),[],
                    sources={},run_context={'outer_deadline':time.monotonic()+10},run_context_sha256='a'*64,
                    receipt_stop=time.monotonic()+10)
    def test_receipt_reserve_skips_before_loader(self):
        with mock.patch.object(R,'cold_load',side_effect=AssertionError('no loader')):
            v=R.full_failure_observation(L,{},ROOT,Path('/unused'),[],sources={},run_context={'outer_deadline':time.monotonic()+1},run_context_sha256='a'*64,receipt_stop=time.monotonic()+3)
            self.assertEqual(v['reason'],'RECEIPT_RESERVE')
    def test_parent_parser_error_is_best_effort(self):
        with mock.patch.object(R,'cold_load',side_effect=RuntimeError('NEVER_EXPORT')):
            v=R.full_failure_observation(L,{'inputs':{D.OWN+'full_failure_diagnostic.py':'a'*64}},ROOT,Path('/unused'),[],sources={},run_context={'outer_deadline':time.monotonic()+10},run_context_sha256='a'*64,receipt_stop=time.monotonic()+10)
            self.assertEqual(v['reason'],'DIAGNOSTIC_UNAVAILABLE');self.assertFalse(v['acceptance']);self.assertNotIn('NEVER_EXPORT',D.encoded(v).decode())
    def test_standalone_imports_no_numerical_or_unittest(self):
        code='import sys;from pathlib import Path;p=Path(sys.argv[1]);exec(compile(p.read_bytes(),str(p),"exec"),{"__name__":"cold","__file__":str(p)});assert not set(("unittest","numpy","torch","ctypes","transformers"))&sys.modules.keys()'
        r=subprocess.run([sys.executable,'-I','-B','-c',code,str(HERE/'full_failure_diagnostic.py')],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)


class SourceAdaptation(unittest.TestCase):
    BASE='candidates/qwen2_resident_matrix/portable_same_host_m16_launch/'
    OBSERVER_SHA='85b8573d8e3e9f3357876414f6e6aabad5d1c6006c25bf25fa111a5686f328e2'
    TEST_SHA='b35ebd92542b857622c134c9775f1adaa0f1a0c6c700af2fb494c953d5783698'
    # Exactly these ten substitutions are permitted in the reviewed observer.
    ADAPTATIONS=(("PROFILE='qwen2-full-m16-failure-observation-v1'", "PROFILE='qwen2-full-m128-failure-observation-v1'"), ("OWN='candidates/qwen2_resident_matrix/portable_same_host_m16_launch/'", "OWN='candidates/qwen2_resident_matrix/portable_same_host_m128_launch/'"), ("v['rows']==16", "v['rows']==128"), ('0<=value<=1950', '0<=value<=4920'), ("e.get('phase')=='full_m16'", "e.get('phase')=='full_m128'"), ("Path(out)/'RUN_CONTEXT.json'", "Path(out)/'M128_RUN_CONTEXT.json'"), ("Path(out)/'source'/name", "Path(out)/'source128'/name"), ("Path(out)/'full_m16.log'", "Path(out)/'full_m128.log'"), ("Path(out)/'full_m16/actual/summary.json'", "Path(out)/'full_m128/actual/summary.json'"), ("Path(out)/'full_m16/snapshot/SNAPSHOT.json'", "Path(out)/'full_m128/snapshot/SNAPSHOT.json'"))
    def reviewed(self):
        raw=(ROOT/self.BASE/'full_failure_diagnostic.py').read_bytes()
        self.assertEqual(D.sha(raw),self.OBSERVER_SHA)
        self.assertEqual(D.sha((ROOT/self.BASE/'test_full_failure_diagnostic.py').read_bytes()),self.TEST_SHA)
        return raw.decode()
    def expected(self):
        source=self.reviewed()
        for old,new in self.ADAPTATIONS:
            self.assertEqual(source.count(old),1,old)
            source=source.replace(old,new)
        return source
    def test_exact_source_only_declared_adaptations(self):
        self.assertEqual((HERE/'full_failure_diagnostic.py').read_text(),self.expected())
    def test_ast_only_declared_constant_adaptations(self):
        baseline=ast.parse(self.reviewed());current=ast.parse((HERE/'full_failure_diagnostic.py').read_text())
        expected=ast.parse(self.expected())
        self.assertEqual(ast.dump(current,include_attributes=False),ast.dump(expected,include_attributes=False))
        old_nodes=list(ast.walk(baseline));new_nodes=list(ast.walk(current))
        self.assertEqual(len(old_nodes),len(new_nodes));changed=[]
        for old,new in zip(old_nodes,new_nodes):
            self.assertIs(type(old),type(new))
            if isinstance(old,ast.Constant) and old.value!=new.value:changed.append((old.value,new.value))
        self.assertCountEqual(changed,[
            ('qwen2-full-m16-failure-observation-v1','qwen2-full-m128-failure-observation-v1'),
            ('candidates/qwen2_resident_matrix/portable_same_host_m16_launch/',
             'candidates/qwen2_resident_matrix/portable_same_host_m128_launch/'),
            (16,128),(1950,4920),('full_m16','full_m128'),('RUN_CONTEXT.json','M128_RUN_CONTEXT.json'),
            ('source','source128'),('full_m16.log','full_m128.log'),
            ('full_m16/actual/summary.json','full_m128/actual/summary.json'),
            ('full_m16/snapshot/SNAPSHOT.json','full_m128/snapshot/SNAPSHOT.json')])
    def test_same_report_statuses_and_control_bounds(self):
        old=load('reviewed_m16_failure_observer',ROOT/self.BASE/'full_failure_diagnostic.py')
        for name in ('STATUSES','COUNTERS','CONTROL_STATUSES','DISPATCH_PCS','MAX_SUMMARY','MAX_OUTPUT','PARSER'):
            self.assertEqual(getattr(D,name),getattr(old,name),name)
        self.assertEqual(D.MAX_SUMMARY,4*1024*1024)
        self.assertEqual(len(D.DISPATCH_PCS),19)
        self.assertEqual(D.COUNTERS['completion_fire'],21)
        self.assertEqual(D.COUNTERS['owner_result_fire'],17)
        self.assertEqual(D.COUNTERS['request_fire'],17)

if __name__=='__main__':unittest.main()
