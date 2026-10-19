import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B before source load')
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).absolute().parent
SIZE=43611
SHA='23fcbb7789bc4489d83c99f4a760a60d6add8340e54b32386cf68812c333a8f9'
RAW=(HERE/'run.py').read_bytes()

def load(raw):
    if len(raw)!=SIZE or hashlib.sha256(raw).hexdigest()!=SHA:
        raise ValueError('source rejected before compile')
    g=types.ModuleType('verified_run_cold');g.__file__=str(HERE/'run.py')
    exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
    return g
G=load(RAW)
PINS=G.decode(G.exact(HERE/'RUN_PINS.json',G.PINS_SIZE,G.PINS_SHA))['files']
CPIN=PINS['candidates/host93_ci_recovery/safe_build_diagnostics.py']
CONTEXT=G.load(HERE/'safe_build_diagnostics.py',CPIN['bytes'],CPIN['sha256'],'cold_context_same_buffer')


def defaults():
    return dict(zip(G.OBSERVATION_KEYS,(None,None,None,None,None,None,None,'UNKNOWN','UNKNOWN','UNKNOWN','UNKNOWN',None,None,None)))


def clean_observation():
    return {**defaults(), 'exit_code':0,'cleanup_confirmed':True,'receipt_timed_out':False,
            'waitid_code':1,'waitid_status':0,'kill_attempted':True,'kill_result':'SIGNAL_SENT_BEFORE_REAP',
            'native_record_status':'PASS','failure_code':'NONE','failure_boundary':'NONE',
            'child_user_cpu_seconds':0.05,'child_system_cpu_seconds':0.01,'child_maxrss_kib_cumulative':1234}


def fixture(ready=False, mode='host-reset-launch'):
    build=mode=='build-diagnostic'
    stages=[{'name':n,'status':'EXIT0_CLEANED','seconds':0.1,'diagnostics':G.empty_diagnostics(),
             **clean_observation()} for n in (G.BUILD_STAGES if build else G.STAGES)] if ready else []
    generated={'derived_backend':{'bytes':1,'sha256':'1'*64}} if ready else {}
    if ready and not build:
        generated.update({'host_elf':{'bytes':1,'sha256':'1'*64},'host93_fir':{'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'},'host93_sv':{'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'}})
    return {'summary.json':{'schema':'host93-ci-summary-v2','mode':mode,'status':'READY_REQUIRES_ACTIONS_EXIT0' if ready else 'INCOMPLETE',
             'failure_category':'NONE' if ready else 'INPUT_OR_CONTRACT','completed_components':(['toolchain_build'] if build else list(G.COMPONENTS)) if ready else [],
             'scope':{x:ready and (x=='toolchain_build' if build else x not in ('n0_numeric','weights_loaded')) for x in G.SCOPES},'seconds':1.0},
            'source_hashes.json':{'schema':'host93-ci-source-hashes-v2','project_sources':[{'path':n,**p} for n,p in sorted(PINS.items())] if ready else [],
              'fixed_inputs':{} if build else {'idma_archive':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}},'generated':generated},
            'stage_exits.json':{'schema':'host93-ci-stage-exits-v3','stages':stages}}


class Cold(unittest.TestCase):
    def test_ascii_runner_paths_accepted(self):
        for path in ('/home/runner/work/repo/repo', '/home/runner/work/_temp/host93-ci-private', '/tmp/host93-idma.zip'):
            self.assertEqual(G.plain_path(path),Path(path))
    def test_make_metacharacters_rejected_before_filesystem(self):
        for character in ('\t','$','`',';',' ','\n','é','&'):
            with self.subTest(character=character),mock.patch.object(G.Path,'is_symlink') as fs:
                with self.assertRaises(ValueError):G.plain_path('/tmp/repo'+character+'bad')
                fs.assert_not_called()
    def test_each_execution_path_rejected_before_support(self):
        for position in range(3):
            values=[Path('/tmp/repo'),Path('/tmp/out'),Path('/tmp/idma.zip')]
            values[position]=Path(str(values[position])+';bad')
            with self.subTest(position=position),mock.patch.dict(G.os.environ,{'GITHUB_ACTIONS':'true'},clear=True),mock.patch.object(G,'load') as load:
                with self.assertRaises(ValueError):G.execute(*values,G.time.monotonic()+60.0)
                load.assert_not_called()
    def test_fixed_short_beforecompile(self):
        with mock.patch('builtins.compile') as c:
            with self.assertRaises(ValueError):load(RAW[:-1])
            c.assert_not_called()
    def test_fixed_same_size_beforecompile(self):
        with mock.patch('builtins.compile') as c:
            with self.assertRaises(ValueError):load(bytes([RAW[0]^1])+RAW[1:])
            c.assert_not_called()
    def test_valid_incomplete(self):self.assertTrue(G.validate_evidence(fixture()))
    def test_valid_ready_nonterminal(self):self.assertTrue(G.validate_evidence(fixture(True)))
    def test_extra_summary_key(self):
        x=fixture();x['summary.json']['environment']='secret'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_source_absolute_path(self):
        x=fixture();x['source_hashes.json']['project_sources']=[{'path':'/private/key','bytes':1,'sha256':'0'*64}]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_source_parent_escape(self):
        x=fixture();x['source_hashes.json']['project_sources']=[{'path':'candidates/host93_ci_recovery/../secret','bytes':1,'sha256':'0'*64}]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_source_unknown_kind(self):
        x=fixture();x['source_hashes.json']['generated']['environment']={'bytes':1,'sha256':'0'*64}
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_archive_hash_exact(self):
        x=fixture();x['source_hashes.json']['fixed_inputs']['idma_archive']['sha256']='0'*64
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_weights_claim_rejected(self):
        x=fixture();x['summary.json']['scope']['weights_loaded']=True
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_numeric_claim_rejected(self):
        x=fixture();x['summary.json']['scope']['n0_numeric']=True
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_missing_stage(self):
        x=fixture(True);x['stage_exits.json']['stages'].pop()
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_failed_stage(self):
        x=fixture(True);x['stage_exits.json']['stages'][-1]['status']='FAILED'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_not_cleaned(self):
        x=fixture(True);x['stage_exits.json']['stages'][-1]['cleanup_confirmed']=False
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_nonzero_exit(self):
        x=fixture(True);x['stage_exits.json']['stages'][-1]['exit_code']=1
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_duplicate_stage(self):
        x=fixture(True);x['stage_exits.json']['stages'][-1]=x['stage_exits.json']['stages'][0]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_unknown_stage_name(self):
        x=fixture(True);x['stage_exits.json']['stages'][-1]['name']='arbitrary command'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_incomplete_cannot_claim_none(self):
        x=fixture();x['summary.json']['failure_category']='NONE'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_nan_and_bool_seconds(self):
        for val in (float('nan'),True,-1):
            x=fixture();x['summary.json']['seconds']=val
            with self.subTest(val=val),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_summary_wall(self):
        x=fixture();x['summary.json']['seconds']=6601
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_phase_all_names_have_bounds(self):self.assertEqual(set(G.STAGES),set(G.PHASE_CAPS))
    def test_header_phase_order_and_counts(self):
        self.assertEqual(len(G.STAGES),34);self.assertEqual(len(G.BUILD_STAGES),16)
        self.assertEqual(G.STAGES[11:16],('flex_header_acquire','flex_header_compile','fresh_autoconf','fresh_configure','fresh_make'))
    def test_header_fixed_small_bounds(self):
        self.assertEqual(G.PHASE_CAPS['flex_header_acquire'],(120,90,40,512*G.MIB,4*G.MIB,65536))
        self.assertEqual(G.PHASE_CAPS['flex_header_compile'],(30,10,10,512*G.MIB,4*G.MIB,65536))
    def test_header_phase_failure_stops_both_modes(self):
        for mode in G.MODES:
            for name in ('flex_header_acquire','flex_header_compile'):
                with self.subTest(mode=mode,name=name):
                    code,summary,stages=self.mock_whole_job(name,mode,True)
                    self.assertEqual(code,1);self.assertEqual(stages[-1]['name'],name)
                    self.assertFalse(summary['scope']['toolchain_build'])
                    self.assertFalse(summary['scope']['reset_launch'])
                    self.assertNotIn('fresh_make',[row['name'] for row in stages])
    def test_old_phase_sequence_cannot_claim_ready(self):
        x=fixture(True)
        x['stage_exits.json']['stages']=[row for row in x['stage_exits.json']['stages'] if not row['name'].startswith('flex_header_')]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_phase_bounds_exact(self):
        for name,caps in G.PHASE_CAPS.items():
            values=dict(zip(('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes'),caps));values['sample_rows']=caps[0]+2
            G.phase_limits(name,values)
    def test_phase_larger_as_rejected(self):
        d=G.limits(600,540,540,7*G.GIB,128*G.MIB,4*G.MIB)
        with self.assertRaises(ValueError):G.phase_limits('host93_cpp_generate',d)
    def test_phase_larger_work_rejected(self):
        d=G.limits(600,541,540,6*G.GIB,128*G.MIB,4*G.MIB)
        with self.assertRaises(ValueError):G.phase_limits('host93_cpp_generate',d)
    def test_sample_cap_rejected(self):
        d=G.limits(600,540,540,6*G.GIB,128*G.MIB,4*G.MIB);d['sample_rows']=100000
        with self.assertRaises(ValueError):G.phase_limits('host93_cpp_generate',d)
    def test_resource_unknown_key(self):
        d=G.limits(600,540,540,6*G.GIB,128*G.MIB,4*G.MIB);d['unlimited']=True
        with self.assertRaises(ValueError):G.phase_limits('host93_cpp_generate',d)
    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):G.decode(b'{"a":1,"a":2}')
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):G.decode(b'{"a":NaN}')
    def test_evidence_roundtrip_no_native(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'evidence').mkdir()
            for n,v in fixture().items():G.write_json(out/'evidence'/n,v)
            with mock.patch.object(G,'execute',side_effect=RuntimeError('must not execute')) as native:
                self.assertEqual(G.main(['--verify-evidence','--out',str(out)]),0)
                native.assert_not_called()
    def test_evidence_extra_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'evidence').mkdir()
            for n,v in fixture().items():G.write_json(out/'evidence'/n,v)
            (out/'evidence'/'raw.log').write_text('must not upload')
            with self.assertRaises(ValueError):G.verify_evidence(out)
    def test_evidence_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);(out/'real').mkdir();(out/'evidence').symlink_to(out/'real',target_is_directory=True)
            with self.assertRaises(ValueError):G.verify_evidence(out)
    def test_memory_proc_zero_stat_is_irrelevant(self):
        with mock.patch('builtins.open',mock.mock_open(read_data=b'MemAvailable: 8388608 kB\n')) as read, \
             mock.patch.object(G.shutil,'disk_usage',return_value=types.SimpleNamespace(free=4*G.GIB)):
            G.memory_disk_gate('/tmp',8*G.GIB,3*G.GIB)
            read.assert_called_once_with('/proc/meminfo','rb')
    def test_memory_insufficient_rejected(self):
        with mock.patch('builtins.open',mock.mock_open(read_data=b'MemAvailable: 1 kB\n')):
            with self.assertRaises(ValueError):G.memory_disk_gate('/tmp',8*G.GIB,3*G.GIB)
    def test_memory_unknown_format_rejected(self):
        with mock.patch('builtins.open',mock.mock_open(read_data=b'WrongMemory: 9999999 kB\n')):
            with self.assertRaises(ValueError):G.memory_disk_gate('/tmp',8*G.GIB,3*G.GIB)
    def test_memory_oversize_rejected(self):
        with mock.patch('builtins.open',mock.mock_open(read_data=b'x'*65537)):
            with self.assertRaises(ValueError):G.memory_disk_gate('/tmp',8*G.GIB,3*G.GIB)
    def test_disk_insufficient_rejected(self):
        with mock.patch('builtins.open',mock.mock_open(read_data=b'MemAvailable: 8388608 kB\n')), \
             mock.patch.object(G.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1)):
            with self.assertRaises(ValueError):G.memory_disk_gate('/tmp',8*G.GIB,3*G.GIB)
    def test_missing_job_environment_before_module(self):
        with mock.patch.dict(G.os.environ,{},clear=True),mock.patch.object(G,'load') as load:
            with self.assertRaises(ValueError):G.execute(Path('/tmp/repo'),Path('/tmp/out'),Path('/tmp/a.zip'),1.0)
            load.assert_not_called()
    def test_nonfinite_job_deadline_before_module(self):
        with mock.patch.dict(G.os.environ,{'GITHUB_ACTIONS':'true'},clear=True),mock.patch.object(G,'load') as load:
            with self.assertRaises(ValueError):G.execute(Path('/tmp/repo'),Path('/tmp/out'),Path('/tmp/a.zip'),float('inf'))
            load.assert_not_called()
    def test_pending_source_pin_before_compile(self):
        with mock.patch('builtins.compile') as comp:
            with self.assertRaises(ValueError):G.exact(Path('/tmp/not-read'),0,'PENDING')
            comp.assert_not_called()

    def mock_whole_job(self, fail_name=None, mode="host-reset-launch", nonzero=False, context=None):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);repo=base/'repo';repo.mkdir();out=base/'out';archive=base/'idma.zip'
            fixed={'bytes':1,'sha256':'1'*64,'path':str(base/'observed')}
            def cfg(name):
                x=dict(zip(('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes'),G.PHASE_CAPS[name]));x['sample_rows']=x['total_seconds']+2;return x
            def group(names,result):
                def run(repo,work,call,*args,**kwargs):
                    selected=names[:16] if kwargs.get("stop_after_build") else names
                    for name in selected:call(name,['/fixed/fixture'],base,{},cfg(name))
                    return result
                return types.SimpleNamespace(run=run)
            tools=group(G.STAGES[:20],{'backend':fixed})
            emission=group(G.STAGES[20:28],{'fir':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_fir']},'sv':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_sv']}})
            execution=group(G.STAGES[-3:],{'elf':fixed})
            modules={'verified_ci_toolchain':tools,'verified_ci_host_emission':emission,'verified_ci_host_execution':execution,'verified_safe_build_diagnostics':CONTEXT}
            def native(*args,**kwargs):
                name=args[2]
                kwargs['diagnostics'].update(clean_observation())
                if name==fail_name:
                    if context is not None:
                        args[5].mkdir(parents=True)
                        (args[5]/'native.log').write_bytes(context)
                    kwargs['diagnostics'].update(exit_code=2 if nonzero else -9, final_reap_signal=None if nonzero else 9,
                        receipt_timed_out=not nonzero,waitid_status=2 if nonzero else None,waitid_code=1 if nonzero else None,
                        native_record_status='FAIL',failure_code='CHILD_EXIT_NONZERO' if nonzero else 'SUPERVISOR_TIMEOUT_CLASSIFICATION',
                        failure_boundary='NATIVE_SUPERVISION')
                    raise ValueError('synthetic child exit') if nonzero else TimeoutError('synthetic boundary')
                return {'exit_code':0,'cleanup_confirmed':True},b'private synthetic',{'child_user_cpu_seconds':0.1,'child_system_cpu_seconds':0.01}
            support=types.SimpleNamespace(deadline_ready=lambda:None,fixed_support=lambda repo:(None,None,None),run_phase=native,diagnostic_defaults=defaults)
            prefix='candidates/host93_ci_recovery/'
            buffers={prefix+'idma319/ENTRY.json':b'{"bootstrap":"pinned synthetic"}',prefix+'configuration/ENTRY.json':b'{"argv_prefix":["python3","-I","-S","-B","-c","pinned synthetic"]}'}
            with mock.patch.dict(G.os.environ,{'GITHUB_ACTIONS':'true'},clear=True), \
                 mock.patch.object(G,'load',return_value=support), \
                 mock.patch.object(G,'project_pin_map',return_value=(PINS,buffers)), \
                 mock.patch.object(G,'module_from',side_effect=lambda repo,pins,relative,name:modules[name]), \
                 mock.patch.object(G,'exact',return_value=b''), \
                 mock.patch.object(G,'memory_disk_gate'), \
                 mock.patch.object(G.signal,'signal'), mock.patch.object(G.signal,'setitimer'), \
                 mock.patch('builtins.print'):
                code=G.execute(repo,out,None if mode=='build-diagnostic' else archive,G.time.monotonic()+1000.,mode)
            self.assertEqual(G.verify_evidence(out),0)
            summary=G.decode((out/'evidence/summary.json').read_bytes())
            stages=G.decode((out/'evidence/stage_exits.json').read_bytes())['stages']
            return code,summary,stages
    def test_whole_job_mock_all_finite_stages(self):
        code,summary,stages=self.mock_whole_job()
        self.assertEqual(code,0)
        self.assertEqual(summary['status'],'READY_REQUIRES_ACTIONS_EXIT0')
        self.assertEqual([x['name'] for x in stages],list(G.STAGES))
    def test_whole_job_mock_timeout_not_hidden_by_evidence(self):
        code,summary,stages=self.mock_whole_job('host93_cpp_compile')
        self.assertEqual(code,1)
        self.assertEqual(summary['status'],'INCOMPLETE')
        self.assertEqual(summary['failure_category'],'TIMEOUT')
        self.assertFalse(summary['scope']['reset_launch'])
        self.assertEqual(stages[-1]['name'],'host93_cpp_compile')
        self.assertEqual(stages[-1]['status'],'FAILED')
        self.assertEqual(stages[-1]['exit_code'],-9)
        self.assertTrue(stages[-1]['receipt_timed_out'])
        self.assertIsNone(stages[-1]['waitid_code'])
        self.assertTrue(stages[-1]['kill_attempted'])

    def test_ready_missing_project_identities(self):
        x=fixture(True);x['source_hashes.json']['project_sources']=[]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_project_identity_wrong_hash(self):
        x=fixture(True);x['source_hashes.json']['project_sources'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_missing_generated_identity(self):
        x=fixture(True);del x['source_hashes.json']['generated']['host_elf']
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_ready_wrong_deterministic_sv(self):
        x=fixture(True);x['source_hashes.json']['generated']['host93_sv']['sha256']='0'*64
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_empty_generated_identity(self):
        x=fixture(True);x['source_hashes.json']['generated']['derived_backend']['bytes']=0
        with self.assertRaises(ValueError):G.validate_evidence(x)


    def test_build_mode_ready(self):
        self.assertTrue(G.validate_evidence(fixture(True,'build-diagnostic')))
    def test_build_mode_only16_mock(self):
        code,summary,stages=self.mock_whole_job(mode='build-diagnostic')
        self.assertEqual(code,0);self.assertEqual([x['name'] for x in stages],list(G.BUILD_STAGES))
        self.assertEqual(summary['completed_components'],['toolchain_build'])
        self.assertFalse(summary['scope']['toolchain_tiny'])
    def test_build_nonzero_real_observation_survives(self):
        code,summary,stages=self.mock_whole_job('fresh_make','build-diagnostic',True)
        self.assertEqual(code,1);row=stages[-1]
        self.assertEqual(row['exit_code'],2);self.assertTrue(row['cleanup_confirmed'])
        self.assertEqual(row['failure_code'],'CHILD_EXIT_NONZERO')
        self.assertEqual(row['waitid_status'],2);self.assertIsNone(row['final_reap_signal'])
        self.assertEqual(row['child_user_cpu_seconds'],.05)
        self.assertFalse(summary['scope']['toolchain_build'])
    def test_build_scope_tiny_forbidden(self):
        x=fixture(True,'build-diagnostic');x['summary.json']['scope']['toolchain_tiny']=True
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_build_archive_forbidden_before_output(self):
        with mock.patch.dict(G.os.environ,{'GITHUB_ACTIONS':'true'},clear=True),mock.patch.object(G,'load') as load:
            with self.assertRaises(ValueError):G.execute(Path('/tmp/repo'),Path('/tmp/out'),Path('/tmp/a.zip'),G.time.monotonic()+60.,'build-diagnostic')
            load.assert_not_called()
    def test_build_stage_extra_backend_forbidden(self):
        x=fixture(True,'build-diagnostic');x['stage_exits.json']['stages'][-1]['name']='derived_tiny_version'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_unknown_cleanup_remains_null(self):
        x=fixture(True,'build-diagnostic');x['summary.json'].update(status='INCOMPLETE',failure_category='UNEXPECTED')
        row=x['stage_exits.json']['stages'][-1];row.update(status='FAILED',**defaults())
        self.assertTrue(G.validate_evidence(x));self.assertIsNone(row['cleanup_confirmed'])
    def test_final_signal_mismatch_rejected(self):
        x=fixture(True);x['stage_exits.json']['stages'][0]['final_reap_signal']=9
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_success_unknown_observation_rejected(self):
        x=fixture(True);x['stage_exits.json']['stages'][0]['native_record_status']='UNKNOWN'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_malicious_diagnostic_tail_rejected(self):
        for text in ('/private/token','https://example.com?secret','arbitrary compiler text'):
            x=fixture(True);x['stage_exits.json']['stages'][0]['diagnostics']['merged_log_tail']=text
            with self.subTest(text=text),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_fixed_diagnostic_accepted(self):
        msg=G.DIAGNOSTIC_MESSAGES['syntax_error_reported']
        row={'path':'src/V3Error.cpp','line':4,'column':2,'category':'syntax_error_reported','message':msg}
        d={'observations':[row],'merged_log_tail':'src/V3Error.cpp:4:2: syntax_error_reported: '+msg,'truncated':True,'context_state':'AVAILABLE'}
        G.validate_diagnostics(d)
        for value in ('/private/V3Error.cpp','src/not_in_fixed_tree.cpp'):
            d['observations'][0]['path']=value
            with self.assertRaises(ValueError):G.validate_diagnostics(d)
    def test_context_available_without_category(self):
        code,summary,stages=self.mock_whole_job('fresh_make','build-diagnostic',True,
            b'V3Ast__gen.cpp:41: error: no matching function for call\n  41 | f(1);\nmake: *** [all] Error 2\n')
        row=stages[-1]
        self.assertEqual(code,1);self.assertEqual(row['exit_code'],2)
        self.assertEqual(row['diagnostics']['context_state'],'AVAILABLE')
        self.assertEqual(row['diagnostics']['observations'],[])
        self.assertIn('no matching function',row['diagnostics']['merged_log_tail'])
        self.assertFalse(summary['scope']['toolchain_build'])
        self.assertTrue(all(x['diagnostics']['context_state']=='NOT_COLLECTED' for x in stages[:-1]))
    def test_failed_make_missing_log_state(self):
        code,summary,stages=self.mock_whole_job('fresh_make','build-diagnostic',True)
        self.assertEqual(stages[-1]['diagnostics'],G.empty_diagnostics('READ_ERROR'))
        self.assertEqual(code,1)
    def test_failed_make_empty_log_available(self):
        code,summary,stages=self.mock_whole_job('fresh_make','build-diagnostic',True,b'')
        self.assertEqual(stages[-1]['diagnostics']['context_state'],'AVAILABLE')
        self.assertEqual(stages[-1]['diagnostics']['merged_log_tail'],'')
        self.assertEqual(code,1)
    def test_collector_read_error_does_not_load_sanitizer(self):
        with mock.patch.object(G,'compiler_log_tail',side_effect=OSError('PRIVATE read failure')),mock.patch.object(G,'module_from') as module:
            self.assertEqual(G.collect_build_diagnostics(None,None,None,None),G.empty_diagnostics('READ_ERROR'))
            module.assert_not_called()
    def test_collector_source_failure_is_sanitizer_error(self):
        with mock.patch.object(G,'compiler_log_tail',return_value=(b'context',False)),mock.patch.object(G,'module_from',side_effect=ValueError('PRIVATE pin failure')):
            self.assertEqual(G.collect_build_diagnostics(None,None,None,None),G.empty_diagnostics('SANITIZER_ERROR'))
    def test_collector_sanitizer_exceptions_are_explicit(self):
        for exc in (ValueError('PRIVATE'),TimeoutError('PRIVATE'),KeyboardInterrupt()):
            module=types.SimpleNamespace(sanitize_build_context=mock.Mock(side_effect=exc))
            with self.subTest(exc=type(exc)),mock.patch.object(G,'compiler_log_tail',return_value=(b'context',False)),mock.patch.object(G,'module_from',return_value=module):
                self.assertEqual(G.collect_build_diagnostics(None,None,None,None),G.empty_diagnostics('SANITIZER_ERROR'))
    def test_collector_malformed_output_rejected(self):
        invalid=G.empty_diagnostics();invalid['context_state']='AVAILABLE';invalid['merged_log_tail']='x'*513
        module=types.SimpleNamespace(sanitize_build_context=mock.Mock(return_value=invalid))
        with mock.patch.object(G,'compiler_log_tail',return_value=(b'context',False)),mock.patch.object(G,'module_from',return_value=module):
            self.assertEqual(G.collect_build_diagnostics(None,None,None,None),G.empty_diagnostics('SANITIZER_ERROR'))
    def test_collector_read_truncation_propagates(self):
        with mock.patch.object(G,'compiler_log_tail',return_value=(b'make: failed',True)),mock.patch.object(G,'module_from',return_value=CONTEXT):
            result=G.collect_build_diagnostics(None,None,None,'/fixed/build')
            self.assertEqual(result['context_state'],'AVAILABLE');self.assertTrue(result['truncated'])
    def test_context_unknown_state_rejected(self):
        for state in ('FAILED','',None,1,True):
            d=G.empty_diagnostics();d['context_state']=state
            with self.subTest(state=state),self.assertRaises(ValueError):G.validate_diagnostics(d)
    def test_context_nonavailable_evidence_rejected(self):
        for state in ('NOT_COLLECTED','READ_ERROR','SANITIZER_ERROR'):
            for change in ({'merged_log_tail':'ordinary context'},{'truncated':True}):
                d=G.empty_diagnostics(state);d.update(change)
                with self.subTest(state=state,change=change),self.assertRaises(ValueError):G.validate_diagnostics(d)
    def test_context_caps_and_controls_rejected(self):
        for tail in ('x'*513,'\n'.join(['x']*81),'\n'.join(['x'*500]*40),'tab\t','carriage\r','escape\x1b','unicode \u202e'):
            d=G.empty_diagnostics();d.update(context_state='AVAILABLE',merged_log_tail=tail)
            with self.subTest(tail=tail[:20]),self.assertRaises(ValueError):G.validate_diagnostics(d)
    def test_context_max_line_and_visible_escape_accepted(self):
        for tail in ('word '*100, 'visible \\t and \\x1b', '\n'.join(['x']*80)):
            d=G.empty_diagnostics();d.update(context_state='AVAILABLE',merged_log_tail=tail)
            G.validate_diagnostics(d)
    def test_context_only_failed_make(self):
        for index,status in ((0,'FAILED'),(-1,'EXIT0_CLEANED')):
            x=fixture(True,'build-diagnostic');row=x['stage_exits.json']['stages'][index]
            row['status']=status;row['diagnostics'].update(context_state='AVAILABLE',merged_log_tail='context')
            with self.subTest(index=index,status=status),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_stage_old_schema_rejected(self):
        x=fixture(True);x['stage_exits.json']['schema']='host93-ci-stage-exits-v2'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_context_missing_state_rejected(self):
        d=G.empty_diagnostics();del d['context_state']
        with self.assertRaises(ValueError):G.validate_diagnostics(d)

    def test_diagnostic_extra_keys_rejected(self):
        d=G.empty_diagnostics();d['raw']='private'
        with self.assertRaises(ValueError):G.validate_diagnostics(d)
    def test_log_tail_fixed_partial_line_removed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'native.log';p.write_bytes(b'x'*(G.MIB+10)+b'\n../V3Error.cpp:1: error: expected token\n')
            raw,truncated=G.compiler_log_tail(p)
            self.assertTrue(truncated);self.assertEqual(raw,b'../V3Error.cpp:1: error: expected token\n')
    def test_log_tail_small_exact(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'native.log';p.write_bytes(b'fixture\n')
            self.assertEqual(G.compiler_log_tail(p),(b'fixture\n',False))


if __name__=='__main__':unittest.main(verbosity=2)
