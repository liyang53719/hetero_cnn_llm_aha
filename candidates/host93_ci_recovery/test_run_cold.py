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
SIZE=77219
SHA='853d7d53c2b85376b643a90ae1421d9d9766c5ad6d415e8e5ddf1570ab0aa79c'
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
TPIN=PINS['candidates/host93_ci_recovery/toolchain/ci_toolchain.py']
TOOLCHAIN=G.load(HERE/'toolchain/ci_toolchain.py',TPIN['bytes'],TPIN['sha256'],'cold_toolchain_contracts')
DPIN=PINS.get('candidates/host93_ci_recovery/emission/chirrtl_diagnostic.py')
DIAGNOSTIC=G.load(HERE/'emission/chirrtl_diagnostic.py',DPIN['bytes'],DPIN['sha256'],'cold_chirrtl_contracts') if DPIN else None
GPIN=PINS.get('candidates/host93_ci_recovery/execution/generation_diagnostics.py')
CENSUS=G.load(HERE/'execution/generation_diagnostics.py',GPIN['bytes'],GPIN['sha256'],'cold_generation_diagnostics') if GPIN else None

FPIN=PINS['candidates/host93_ci_recovery/fifo_preflight/fifo_preflight.py']
PREFLIGHT=G.load(HERE/'fifo_preflight/fifo_preflight.py',FPIN['bytes'],FPIN['sha256'],'cold_fixed_fifo_preflight')
EPIN=PINS['candidates/host93_ci_recovery/execution/host_execution.py']
EXECUTION=G.load(HERE/'execution/host_execution.py',EPIN['bytes'],EPIN['sha256'],'cold_fixed_cluster_execution')

NPIN=PINS['candidates/host93_ci_recovery/first_n0/pipeline.py']
PIPELINE=G.load(HERE/'first_n0/pipeline.py',NPIN['bytes'],NPIN['sha256'],'cold_n0_pipeline')
NROOT=Path(G.os.environ.get('N0_TEST_SOURCE_ROOT',str(HERE.parent/'host93_first_n0_sources')))
if not NROOT.is_absolute():raise ValueError('absolute explicit N0 test source root')
NPIN=PINS['candidates/host93_first_n0_sources/comparison/n0_compare.py']
COMPARATOR=G.load(NROOT/'comparison/n0_compare.py',NPIN['bytes'],NPIN['sha256'],'cold_n0_comparator')

def n0_counts():
    c={key:0 for key in COMPARATOR.COUNT_KEYS}
    c.update(scope='FIRST_N0_M128_ONLY',status='ACK0_ACTUAL_CAPTURED',phase='OUTPUT',code='ACK0_COMPLETE',numeric_comparison='NOT_RUN',full_block_pass=False,root256_handles='UNKNOWN',cycle_budget=8000000,reduction_only_source_floor=2428928,unproven_overhead_allowance=5571072,cycles=3000000,launches=1,jobs=1,owner_dones=1,completion_acks=1,committed_bytes=786432,successful_b=12288,writeback_bytes=786432,post_pc=1,post_issued_jobs=1,further_eval_calls=0,actual_values=196608,actual_bytes=786432)
    c.update({key:[0]*size for key,size in COMPARATOR.ARRAY_SIZES.items()});c['axi']={key:0 for key in COMPARATOR.AXI_KEYS};c['axi'].update(bs=12288,strobed_bytes=786432);return c

def n0_comparison(passed=True,exact=False):
    r=COMPARATOR.new_report();r.update(status='N0_LIMITED_TOLERANCE_PASS' if passed else 'N0_LIMITED_TOLERANCE_FAIL',code=None,stage='COMPLETE',numeric_pass=passed,bit_exact=exact,hash_exact=exact,reference_hash_accepted=True,capture_basic_counts_accepted=True,actual_bytes=786432,reference_bytes=786432,actual_sha256=PIPELINE.F32['sha256'] if exact else 'a'*64,reference_sha256=PIPELINE.F32['sha256'],capture_sha256='b'*64,limits={'max_abs':.03125,'mean_abs':.005})
    r['metrics']={'shape':[1,128,1536],'elements':196608,'max_abs':0.0 if exact else .03 if passed else .04,'mean_abs':0.0 if exact else .004,'relative_l2':0.0,'cosine':1.0,'normalized_max_abs':.03,'different_elements':0 if exact else 5,'bit_exact':exact,'actual_f32_sha256':r['actual_sha256'],'reference_f32_sha256':r['reference_sha256'],'finite':True};return r

RSS={'sampled_leader_max_kib':1000,'limit_kib':1572864,'os_hard_limit':False,'includes_descendants':False}

# Safe JSON schema fixture only; no generated private bytes are reconstructed.
CLUSTER_REPORT = {'by_rule': {},
 'caps': {'example_cap': False, 'partial': False, 'record_cap': False, 'report_byte_cap': False},
 'counts': {'error_headers': 0,
            'example_paths': 0,
            'fatal_summary_headers': 0,
            'unparsed_headers': 0,
            'warning_headers': 0},
 'fatal_summaries': {'error_total': None,
                     'header_count_comparison': 'NOT_AVAILABLE',
                     'process_attribution': 'NOT_AVAILABLE',
                     'warning_total': None},
 'log_identity': {'bytes': 1874,
                  'sha256': '46e43993bb5e0fe0d995e5eb23a31eb5ad7a125dfa69e26502b5584ddd96eaa1'},
 'omission': {'examples': 0, 'records': 0},
 'records': [],
 'scan_complete': True,
 'schema_version': 1,
 'source_derivations': [{'base_identity': {'bytes': 4411,
                                           'sha256': '68de1c713e40d97950591111dccd37a7546025f7fe6750fa3092826422557352'},
                         'derived_identity': {'bytes': 4662,
                                              'sha256': 'cf5607bf61d0e1ca95d523689ba5170fe937dcfb2f94c001661b4a897bf9e5f6'},
                         'source_id': 'idma/deps/common_cells/src/cc_passthrough_stream_fifo.sv'}],
 'state': 'AVAILABLE',
 'wrapper': {'always_comb_count': 2,
             'always_comb_lines': [123, 184],
             'args_identity': {'bytes': 32810,
                               'sha256': '6ae0d4333db213f9dcb7d9bc2ba3eb1caf3f00817cb0a2c9f99d0bda07ba268a'},
             'candidate_count': 1,
             'cluster_structure': {'expected_structure_observed': False,
                                   'handle_declaration_count': None,
                                   'instance_handle_count': None,
                                   'library_target_count': 1,
                                   'makegraph_identity': {'bytes': 34706,
                                                          'sha256': '45f18f4c1347ef461ed305d85cab9dc4059a5f283ec1e44ed7a03421f4370ad9'},
                                   'makegraph_state': 'AVAILABLE',
                                   'matching_library_target_count': 1,
                                   'root_header_identity': {'bytes': 5296945,
                                                            'sha256': '82307c51e8722e51062eaf38200355143d5e86cdaa50fdd4f0c9d24e0c458ef6'},
                                   'root_header_read': {'final_code': 'OK',
                                                        'final_observed_size': 5296945,
                                                        'first_code': 'SIZE_LIMIT',
                                                        'first_observed_size': 5296945,
                                                        'retry_outcome': 'SUCCEEDED'},
                                   'root_header_state': 'UNRECOGNIZED_SYNTAX'},
             'combo_input_count': 18,
             'combo_output_count': 2,
             'combo_update_call_count': 1,
             'combo_update_import_count': 1,
             'dependency_conclusion': 'NOT_ESTABLISHED',
             'dpi_import_count': 6,
             'handshakes': [],
             'hierarchical_child': 1,
             'module': 'bf16_context_lane_cluster16_rev8b_b_candidate',
             'specialization': 'UNKNOWN',
             'state': 'AVAILABLE',
             'syntax_state': 'FINITE_PARSE_AVAILABLE',
             'top_args_identity': {'bytes': 32736,
                                   'sha256': '2f1d903e8b6274a4917b06f1153c4227cfa9a6182ebf6ae695bd2bf8dba8ed7f'},
             'top_references_wrapper': True,
             'wrapper_identity': {'bytes': 7959,
                                  'sha256': 'acbd12f080c1f92bf5f1d26549c4e9e0654bd0b535a2a3e81b5c3fbedf612590'}}}


def generation_fixture_report(cluster=False):
    if cluster:return copy.deepcopy(CLUSTER_REPORT)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td);log=root/'native.log';log.write_bytes(b'')
        return CENSUS.collect(log,root,[{'path':'/private/fixture.sv','id':'host/fixture.sv','bytes':0,'sha256':'a'*64}],CONTEXT)


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
             **clean_observation()} for n in G.mode_stages(mode)] if ready else []
    generated={'derived_backend':{'bytes':1,'sha256':'1'*64}} if ready else {}
    if ready and not build:
        generated.update({'host_elf':{'bytes':1,'sha256':'1'*64},'host93_fir':{'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'},'host93_sv':{'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'}})
    if ready and mode in G.FRONTLOAD_MODES:generated['diagnostic_fir']=dict(G.HISTORICAL_FIR)
    if ready and mode=='host-generation-diagnostic':generated.pop('host_elf',None)
    observation={'state':'AVAILABLE','utf8_bytes':G.HISTORICAL_FIR['bytes'],'line_count':293837,'module_count':682,'extmodule_count':17,'source_info_count':254482,'source_info_utf8_bytes':1000000,'project_source_info_count':249537,'library_source_info_count':4945,'other_source_info_count':0,'historical_fir_equal':True} if ready and mode in G.FRONTLOAD_MODES else G.empty_chirrtl_observation()
    return {'summary.json':{'schema':'host93-ci-summary-v6','mode':mode,'status':G.success_status(mode) if ready else 'INCOMPLETE',
             'failure_category':'NONE' if ready else 'INPUT_OR_CONTRACT','contract_failure':{'boundary':'NONE' if ready else 'UNREPORTED','code':'NONE' if ready else 'UNMAPPED_CONTRACT'},'completed_components':list(G.mode_components(mode)) if ready else [],
             'scope':{x:ready and (x=='toolchain_build' if build else x in G.SCOPES[:3] if mode=='host-generation-diagnostic' else x not in ('n0_numeric','weights_loaded')) for x in G.SCOPES},'seconds':1.0,'chirrtl_observation':observation,'generation_diagnostics':generation_fixture_report(mode=='host-cluster-reset-launch') if ready and mode in G.CLUSTER_MODES else None,'fifo_observation':{'state':'AVAILABLE','cases':4,'comparisons':5180,'tools':copy.deepcopy(G.FIFO_TOOLS)} if ready and mode in G.CLUSTER_MODES else G.empty_fifo_observation()},
            'source_hashes.json':{'schema':'host93-ci-source-hashes-v3','project_sources':[{'path':n,**p} for n,p in sorted(PINS.items())] if ready else [],
              'fixed_inputs':{} if build else {'idma_archive':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}},'generated':generated},
            'stage_exits.json':{'schema':'host93-ci-stage-exits-v6','stages':stages}}


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
    def test_phase_all_names_have_bounds(self):self.assertEqual(set(G.STAGES)|set(G.FRONTLOAD_STAGES)|set(G.FIFO_STAGES)|set(G.N0_FRONT_STAGES)|{'host93_first_n0','host93_n0_compare'},set(G.PHASE_CAPS))
    def test_header_phase_order_and_counts(self):
        self.assertEqual(len(G.STAGES),34);self.assertEqual(len(G.BUILD_STAGES),16)
        self.assertEqual(G.STAGES[11:16],('flex_header_acquire','flex_header_compile','fresh_autoconf','fresh_configure','fresh_make'))
    def test_header_fixed_small_bounds(self):
        self.assertEqual(G.PHASE_CAPS['flex_header_acquire'],(120,90,40,512*G.MIB,4*G.MIB,65536))
        self.assertEqual(G.PHASE_CAPS['flex_header_compile'],(30,10,10,512*G.MIB,4*G.MIB,65536))
    def test_header_phase_failure_stops_both_modes(self):
        for mode in (m for m in G.MODES if m!=G.N0_MODE):
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

    def mock_whole_job(self, fail_name=None, mode="host-reset-launch", nonzero=False, context=None, contract_postflight=False, diagnostic_match=True, fifo_contract=None, phase_deadline=False):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);repo=base/'repo';repo.mkdir();out=base/'out';archive=base/'idma.zip'
            fixed={'bytes':1,'sha256':'1'*64,'path':str(base/'observed')}
            def cfg(name):
                x=dict(zip(('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes'),G.PHASE_CAPS[name]));x['sample_rows']=x['total_seconds']+2;return x
            def group(names,result):
                def run(repo,work,call,*args,**kwargs):
                    selected=names[:16] if kwargs.get("stop_after_build") else names[:1] if kwargs.get('stop_after_generation') else names[:2] if kwargs.get('first_n0') else names
                    for name in selected:
                        try:
                            call(name,['/fixed/fixture'],base,{},cfg(name))
                        finally:
                            if (kwargs.get('stop_after_generation') or kwargs.get('cluster_boundary')) and name=='host93_cpp_generate':kwargs['diagnostic_callback'](work,[{'path':'/private/fixture.sv','id':'host/fixture.sv','bytes':0,'sha256':'a'*64}])
                        if contract_postflight and name == 'fresh_configure':
                            error=ValueError('private fixture text must not publish')
                            error.safe_contract_boundary='BUILD_CONFIGURE_CPPFLAGS_AFTER'
                            error.safe_contract_code='CPPFLAGS_VALUE'
                            raise error
                    return {'status':'COMPILED_FIRST_N0_FIXTURE_ONLY','compiled_executable':fixed} if kwargs.get('first_n0') else {'diagnostic_only':True} if kwargs.get('stop_after_generation') else result
                return types.SimpleNamespace(run=run)
            tools=group(G.STAGES[:20],{'backend':fixed})
            emission=group(G.STAGES[20:28],{'fir':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_fir']},'sv':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_sv']}})
            execution=group(G.STAGES[-3:],{'elf':fixed})
            diagnostic_pin=G.HISTORICAL_FIR if diagnostic_match else {'bytes':100,'sha256':'1'*64}
            diagnostic_observation={'utf8_bytes':diagnostic_pin['bytes'],'line_count':10,'module_count':5,'extmodule_count':0,'source_info_count':8,'source_info_utf8_bytes':50,'project_source_info_count':6,'library_source_info_count':2,'other_source_info_count':0,'historical_fir_equal':diagnostic_match}
            diagnostic=group(G.CHIRRTL_STAGES,{'fir':{'path':fixed['path'],**diagnostic_pin},'observation':diagnostic_observation,'resume_context':{'fixed':'same-root-fixture'},'structural_assertions_passed':True})
            def resume(repo,work,call,base,context):
                self.assertEqual(context,{'fixed':'same-root-fixture'})
                return group(G.STAGES[26:28],{'fir':{'path':fixed['path'],**G.HISTORICAL_FIR},'sv':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_sv']}}).run(repo,work,call)
            diagnostic.resume_sv=resume
            diagnostic.parse_observation=DIAGNOSTIC.parse_observation if DIAGNOSTIC else None
            preflight=group(G.FIFO_STAGES,{'cases':4,'comparisons':5180,'tools':copy.deepcopy(G.FIFO_TOOLS)})
            if fifo_contract:
                boundary,count=fifo_contract
                def fail_fifo(repo,work,call,*args):
                    for name in G.FIFO_STAGES[:count]:call(name,['/fixed/fixture'],base,{},cfg(name))
                    error=ValueError('private finite preflight fixture')
                    error.safe_contract_boundary=boundary;error.safe_contract_code=G.FIFO_CONTRACTS[boundary]
                    raise error
                preflight=types.SimpleNamespace(run=fail_fifo)
            execution.validate_cluster_census=EXECUTION.validate_cluster_census
            census=types.SimpleNamespace(collect=lambda *a:generation_fixture_report(True),validate_report=CENSUS.validate_report,empty_report=CENSUS.empty_report) if mode in ('host-cluster-reset-launch',G.N0_MODE) else CENSUS
            modules={'verified_fifo_preflight':preflight,'verified_ci_chirrtl_diagnostic':diagnostic,'verified_ci_toolchain':tools,'verified_ci_host_emission':emission,'verified_ci_host_execution':execution,'verified_safe_build_diagnostics':CONTEXT,'verified_ci_generation_diagnostics':census}
            if mode==G.N0_MODE:
                def front(repo,work,pins,call,stop,observation,completed):
                    for i,name in enumerate(G.N0_FRONT_STAGES,1):
                        if phase_deadline:
                            with mock.patch.object(G.time,'monotonic',return_value=stop-14):call(name,['/fixed/fixture'],base,{},cfg(name))
                        else:call(name,['/fixed/fixture'],base,{},cfg(name))
                        if i==2:observation.update(state='COLLECTING',runtime_ready=True);completed.append('n0_runtime')
                        if i==4:observation['inputs_ready']=True;completed.append('n0_inputs')
                        if i==5:observation.update(reference_ready=True,reference_rss=copy.deepcopy(RSS));completed.append('n0_reference')
                    return {'private':'mock'}
                def numeric(repo,work,pins,call,stop,front,result,observation,completed,stages):
                    observation['capture_state']='READ_ERROR'
                    try:call('host93_first_n0',['/fixed/fixture'],base,{},cfg('host93_first_n0'))
                    except BaseException:observation['capture_state']='NATIVE_FAILED';raise
                    observation.update(capture_state='AVAILABLE',capture=n0_counts());completed.append('n0_capture')
                    observation['comparison_state']='READ_ERROR'
                    call('host93_n0_compare',['/fixed/fixture'],base,{},cfg('host93_n0_compare'))
                    observation.update(comparison_state='AVAILABLE',comparison=n0_comparison(),comparison_rss=copy.deepcopy(RSS),state='COMPLETE');completed.append('n0_comparison');return True
                modules['verified_n0_pipeline']=types.SimpleNamespace(run_frontdoor=front,run_numeric=numeric,empty_observation=PIPELINE.empty_observation,PRIVATE_STAGES=PIPELINE.PRIVATE_STAGES,private_diagnostics=lambda *args:G.empty_diagnostics('READ_ERROR'),need=PIPELINE.need)
            def native(*args,**kwargs):
                name=args[2]
                if name=='idma319_extract':
                    self.assertEqual('--fifo-valid-split' in args[3],mode in G.CLUSTER_MODES)
                if name=='host93_configuration':
                    self.assertEqual('--cluster-boundary' in args[3],mode in G.CLUSTER_MODES)
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
                if mode in G.CLUSTER_MODES and name=='host93_cpp_generate':
                    args[5].mkdir(parents=True,exist_ok=True);(args[5]/'native.log').write_bytes(b'')
                return {'exit_code':0,'cleanup_confirmed':True},b'private synthetic',{'child_user_cpu_seconds':0.1,'child_system_cpu_seconds':0.01}
            support=types.SimpleNamespace(deadline_ready=lambda:None,fixed_support=lambda repo:(None,None,None),run_phase=native,diagnostic_defaults=defaults)
            prefix='candidates/host93_ci_recovery/'
            buffers={prefix+'emission/EmitCanonicalHost93Diagnostic.scala':b'synthetic fixed emitter',prefix+'idma319/ENTRY.json':b'{"bootstrap":"pinned synthetic"}',prefix+'configuration/ENTRY.json':b'{"argv_prefix":["python3","-I","-S","-B","-c","pinned synthetic"]}'}
            with mock.patch.dict(G.os.environ,{'GITHUB_ACTIONS':'true'},clear=True), \
                 mock.patch.object(G,'load',return_value=support), \
                 mock.patch.object(G,'project_pin_map',return_value=(PINS,buffers)), \
                 mock.patch.object(G,'generation_schema_module',return_value=CENSUS), \
                 mock.patch.object(G,'execution_schema_module',return_value=EXECUTION), \
                 mock.patch.object(G,'n0_schema_module',return_value=PIPELINE), \
                 mock.patch.object(G,'n0_comparison_module',return_value=COMPARATOR), \
                 mock.patch.object(G,'module_from',side_effect=lambda repo,pins,relative,name:modules[name]), \
                 mock.patch.object(G,'exact',return_value=b''), \
                 mock.patch.object(G,'memory_disk_gate'), \
                 mock.patch.object(G.signal,'signal'), mock.patch.object(G.signal,'setitimer'), \
                 mock.patch('builtins.print'):
                code=G.execute(repo,out,None if mode=='build-diagnostic' else archive,G.time.monotonic()+1000.,mode)
            with mock.patch.object(G,'n0_schema_module',return_value=PIPELINE),mock.patch.object(G,'n0_comparison_module',return_value=COMPARATOR):
                self.assertEqual(G.verify_evidence(out),0)
            summary=G.decode((out/'evidence/summary.json').read_bytes())
            stages=G.decode((out/'evidence/stage_exits.json').read_bytes())['stages']
            return code,summary,stages
    def test_postconfigure_safe_contract_retains_native_success(self):
        code,summary,stages=self.mock_whole_job(contract_postflight=True)
        self.assertEqual(code,1);self.assertEqual(len(stages),15)
        self.assertTrue(all(row['status']=='EXIT0_CLEANED' and row['exit_code']==0 for row in stages))
        self.assertEqual(summary['contract_failure'],{'boundary':'BUILD_CONFIGURE_CPPFLAGS_AFTER','code':'CPPFLAGS_VALUE'})
        self.assertNotIn('private fixture',json.dumps(summary))
    def test_contract_enum_matches_pinned_toolchain(self):
        self.assertTrue(set(TOOLCHAIN.CONTRACT_CODES)<=set(G.CONTRACT_CODES))
        self.assertEqual(set(G.CONTRACT_CODES)-set(TOOLCHAIN.CONTRACT_CODES)-set(G.FIFO_CONTRACTS.values())-set(G.FIFO_REQUIRE_CODES)-set(G.CLUSTER_CONTRACT_CODES),{'CHIRRTL_FIR_IDENTITY_MISMATCH','DIAGNOSTIC_CONTRACT','DIAGNOSTIC_EMITTER','DIAGNOSTIC_DERIVATION','DIAGNOSTIC_STATS','DIAGNOSTIC_FIR_OUTPUT','DIAGNOSTIC_RESUME_IDENTITY'})
        self.assertEqual(set(G.CONTRACT_BOUNDARIES)-set(TOOLCHAIN.CONTRACT_BOUNDARIES)-set(G.FIFO_CONTRACTS)-{'CLUSTER_GENERATION_WITNESS'},{'CHIRRTL_DIAGNOSTIC'})
    def test_unknown_contract_message_not_public(self):
        self.assertEqual(G.contract_failure_observation(ValueError('/private/path password=fixture')),
                         {'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})
    def test_forged_contract_labels_cannot_publish_text(self):
        error=ValueError('fixture');error.safe_contract_boundary='/private';error.safe_contract_code='token=secret'
        self.assertEqual(G.contract_failure_observation(error),{'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})
    def test_contract_schema_rejects_free_text(self):
        for field in ('boundary','code'):
            x=fixture();x['summary.json']['contract_failure'][field]='private arbitrary text'
            with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_success_contract_detail_must_be_none(self):
        x=fixture(True);x['summary.json']['contract_failure']={'boundary':'BUILD_CONFIGURE_CPPFLAGS_AFTER','code':'CPPFLAGS_VALUE'}
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_failed_contract_detail_cannot_be_none(self):
        x=fixture();x['summary.json']['contract_failure']={'boundary':'NONE','code':'NONE'}
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_contract_extra_detail_key_rejected(self):
        x=fixture();x['summary.json']['contract_failure']['message']='private arbitrary text'
        with self.assertRaises(ValueError):G.validate_evidence(x)
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


    def test_diagnostic_shared_contract_matches_pinned_component(self):
        self.assertIsNotNone(DIAGNOSTIC)
        self.assertEqual(G.CHIRRTL_NUMERIC,DIAGNOSTIC.METRICS)
        self.assertTrue(set(DIAGNOSTIC.SAFE_CONTRACT_CODES)<=set(G.CONTRACT_CODES))
        self.assertEqual(G.HISTORICAL_FIR,DIAGNOSTIC.HISTORICAL_FIR_PIN)
        G.phase_limits('host93_chirrtl_diagnostic',DIAGNOSTIC.DIAGNOSTIC_LIMITS)
    def test_frontload_path_count_partition_rejected(self):
        x=fixture(True,'host-chirrtl-diagnostic');x['summary.json']['chirrtl_observation']['other_source_info_count']=1
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def diagnostic_completed_fixture(self):
        x=fixture(True,'host-chirrtl-diagnostic')
        x['summary.json'].update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',
            contract_failure={'boundary':'CHIRRTL_DIAGNOSTIC','code':'CHIRRTL_FIR_IDENTITY_MISMATCH'},
            completed_components=['chirrtl_diagnostic'],scope={key:False for key in G.SCOPES})
        x['source_hashes.json']['generated']={'diagnostic_fir':dict(G.HISTORICAL_FIR)}
        x['stage_exits.json']['stages']=x['stage_exits.json']['stages'][:6]
        return x
    def test_available_diagnostic_requires_all_six_native_rows(self):
        for count in range(6):
            x=self.diagnostic_completed_fixture();x['stage_exits.json']['stages']=x['stage_exits.json']['stages'][:count]
            with self.subTest(count=count),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_available_diagnostic_rejects_failed_sixth_stage(self):
        x=self.diagnostic_completed_fixture();row=x['stage_exits.json']['stages'][-1]
        row.update(status='FAILED',**defaults());row['diagnostics']=G.empty_diagnostics('READ_ERROR')
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_all_modes_reject_rows_after_first_failure(self):
        for mode in (m for m in G.MODES if m!=G.N0_MODE):
            x=fixture(True,mode);x['summary.json'].update(status='INCOMPLETE',failure_category='UNEXPECTED')
            row=x['stage_exits.json']['stages'][0]
            row.update(status='FAILED',**defaults());row['diagnostics']=G.empty_diagnostics('READ_ERROR')
            with self.subTest(mode=mode),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_available_diagnostic_six_clean_rows_accept(self):
        self.assertTrue(G.validate_evidence(self.diagnostic_completed_fixture()))

    def test_frontload_full_continuation_once_after_exact_fir(self):
        code,summary,stages=self.mock_whole_job(mode='host-chirrtl-diagnostic')
        self.assertEqual(code,0);self.assertEqual([x['name'] for x in stages],list(G.FRONTLOAD_STAGES))
        self.assertEqual(len(stages),34);self.assertEqual(len({x['name'] for x in stages}),34)
        self.assertEqual(summary['completed_components'],['chirrtl_diagnostic']+list(G.COMPONENTS))
        self.assertTrue(summary['chirrtl_observation']['historical_fir_equal'])
        self.assertEqual(summary['chirrtl_observation']['state'],'AVAILABLE')
        self.assertTrue(summary['scope']['reset_launch']);self.assertFalse(summary['scope']['n0_numeric'])
    def test_frontload_mismatch_stops_before_expensive_toolchain(self):
        code,summary,stages=self.mock_whole_job(mode='host-chirrtl-diagnostic',diagnostic_match=False)
        self.assertEqual(code,1);self.assertEqual([x['name'] for x in stages],list(G.CHIRRTL_STAGES))
        self.assertTrue(all(x['status']=='EXIT0_CLEANED' for x in stages))
        self.assertEqual(summary['completed_components'],['chirrtl_diagnostic'])
        self.assertFalse(any(summary['scope'].values()))
        self.assertEqual(summary['chirrtl_observation']['state'],'AVAILABLE')
        self.assertFalse(summary['chirrtl_observation']['historical_fir_equal'])
        self.assertEqual(summary['contract_failure'],{'boundary':'CHIRRTL_DIAGNOSTIC','code':'CHIRRTL_FIR_IDENTITY_MISMATCH'})
    def test_frontload_diagnostic_failure_retains_context_and_no_toolchain(self):
        code,summary,stages=self.mock_whole_job('host93_chirrtl_diagnostic','host-chirrtl-diagnostic',True,b'utf8_bytes=57389476\n')
        self.assertEqual(code,1);self.assertEqual(len(stages),6)
        self.assertEqual(summary['chirrtl_observation'],G.empty_chirrtl_observation())
        self.assertFalse(any(summary['scope'].values()))
        self.assertEqual(stages[-1]['diagnostics']['merged_log_tail'],'utf8_bytes=57389476')
    def test_frontload_overcap_numeric_report_survives_failed_child(self):
        values={'utf8_bytes':96*G.MIB+1,'line_count':293837,'module_count':682,'extmodule_count':17,'source_info_count':254482,'source_info_utf8_bytes':1000000,'project_source_info_count':249537,'library_source_info_count':4945,'other_source_info_count':0}
        log=DIAGNOSTIC.MARKER+b' '.join(k.encode()+b'='+str(values[k]).encode() for k in G.CHIRRTL_NUMERIC)+b'\nException: cap\n'
        code,summary,stages=self.mock_whole_job('host93_chirrtl_diagnostic','host-chirrtl-diagnostic',True,log)
        self.assertEqual(code,1);self.assertEqual(len(stages),6);self.assertFalse(any(summary['scope'].values()))
        self.assertEqual(summary['chirrtl_observation'],{'state':'REPORTED',**values,'historical_fir_equal':None})
        self.assertEqual(stages[-1]['diagnostics']['context_state'],'AVAILABLE')
    def test_frontload_reported_cannot_claim_historical_identity(self):
        x=fixture(True,'host-chirrtl-diagnostic');x['summary.json']['chirrtl_observation']['state']='REPORTED'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_resume_failure_keeps_tool_and_fir_observation(self):
        code,summary,stages=self.mock_whole_job('host93_sv','host-chirrtl-diagnostic',True,b'firtool failure\n')
        self.assertEqual(code,1);self.assertEqual(len(stages),28)
        self.assertTrue(summary['scope']['toolchain_build']);self.assertTrue(summary['scope']['toolchain_tiny'])
        self.assertFalse(summary['scope']['fresh_host_sv'])
        self.assertTrue(summary['chirrtl_observation']['historical_fir_equal'])
    def test_frontload_caps_only_new_fsize_differs(self):
        self.assertEqual(G.PHASE_CAPS['host93_chirrtl_diagnostic'],(90,60,60,4*G.GIB,96*G.MIB,2*G.MIB))
        self.assertEqual(G.PHASE_CAPS['host93_chirrtl'],(90,60,60,4*G.GIB,48*G.MIB,2*G.MIB))
        self.assertEqual(G.FRONTLOAD_STAGES,G.CHIRRTL_STAGES+G.STAGES[:20]+G.STAGES[26:])
    def test_frontload_ready_fixture(self):self.assertTrue(G.validate_evidence(fixture(True,'host-chirrtl-diagnostic')))
    def test_frontload_observation_forbidden_in_old_modes(self):
        for mode in ('host-reset-launch','build-diagnostic'):
            x=fixture(True,mode);x['summary.json']['chirrtl_observation']=fixture(True,'host-chirrtl-diagnostic')['summary.json']['chirrtl_observation']
            with self.subTest(mode=mode),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_rejects_unknown_or_unbounded_numeric_fields(self):
        for key in G.CHIRRTL_NUMERIC:
            for bad in ('private',True,-1,96*G.MIB+1,None):
                x=fixture(True,'host-chirrtl-diagnostic');x['summary.json']['chirrtl_observation'][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_rejects_false_identity_comparison(self):
        for key,bad in (('bytes',42417257),('sha256','1'*64)):
            x=fixture(True,'host-chirrtl-diagnostic');x['source_hashes.json']['generated']['diagnostic_fir'][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_rejects_stage_reordering(self):
        x=fixture(True,'host-chirrtl-diagnostic');rows=x['stage_exits.json']['stages'];rows[0],rows[6]=rows[6],rows[0]
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_does_not_qualify_changed_fir(self):
        x=fixture(True,'host-chirrtl-diagnostic');x['source_hashes.json']['generated']['diagnostic_fir']['sha256']='1'*64
        x['summary.json']['chirrtl_observation']['historical_fir_equal']=False
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_frontload_empty_observation_has_no_numeric_claim(self):
        x=fixture();x['summary.json']['chirrtl_observation']['utf8_bytes']=1
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_old_three_schemas_not_reinterpreted(self):
        for name,schema in (('summary.json','host93-ci-summary-v3'),('source_hashes.json','host93-ci-source-hashes-v2'),('stage_exits.json','host93-ci-stage-exits-v4')):
            x=fixture();x[name]['schema']=schema
            with self.subTest(name=name),self.assertRaises(ValueError):G.validate_evidence(x)

    def test_generation_only_fixture_accepted_no_runtime(self):
        x=fixture(True,'host-generation-diagnostic');self.assertTrue(G.validate_evidence(x))
        self.assertEqual(x['summary.json']['status'],'DIAGNOSTIC_ONLY_REQUIRES_ACTIONS_EXIT0')
        self.assertFalse(any(x['summary.json']['scope'][k] for k in ('cpp_generated','cpp_compiled','reset_launch')))
    def test_generation_only_mock_runs35_and_stops(self):
        code,summary,stages=self.mock_whole_job(mode='host-generation-diagnostic')
        self.assertEqual(code,0);self.assertEqual([x['name'] for x in stages],list(G.FIFO_STAGES+G.FRONTLOAD_STAGES[:-2]))
        self.assertEqual(summary['completed_components'],list(G.mode_components('host-generation-diagnostic')))
        self.assertEqual(summary['generation_diagnostics']['state'],'AVAILABLE')
        self.assertFalse(summary['scope']['cpp_generated']);self.assertFalse(summary['scope']['cpp_compiled'])
        self.assertFalse(summary['scope']['reset_launch'])
    def test_generation_failure_collects_and_preserves_nonzero(self):
        code,summary,stages=self.mock_whole_job('host93_cpp_generate','host-generation-diagnostic',True,b'%Warning-UNOPTFLAT: /private/x.sv:3:2: circular\n%Error: Exiting due to 1 warning(s)\n')
        self.assertEqual(code,1);self.assertEqual(len(stages),35);self.assertEqual(stages[-1]['exit_code'],2)
        self.assertEqual(summary['generation_diagnostics']['state'],'AVAILABLE')
        self.assertNotIn('/private/',str(summary['generation_diagnostics']))
        self.assertFalse(summary['scope']['cpp_compiled']);self.assertFalse(summary['scope']['reset_launch'])
    def test_generation_missing_log_is_explicit_read_error(self):
        code,summary,stages=self.mock_whole_job('host93_cpp_generate','host-generation-diagnostic',True)
        self.assertEqual(code,1);self.assertEqual(summary['generation_diagnostics']['state'],'READ_ERROR')
    def test_generation_early_failure_has_no_census_claim(self):
        code,summary,stages=self.mock_whole_job('host93_class','host-generation-diagnostic',True)
        self.assertEqual(code,1);self.assertIsNone(summary['generation_diagnostics'])
    def test_generation_schema_refuses_host_qualification(self):
        for key in ('cpp_generated','cpp_compiled','reset_launch'):
            x=fixture(True,'host-generation-diagnostic');x['summary.json']['scope'][key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_schema_refuses_compile_or_runtime_rows(self):
        for name in ('host93_cpp_compile','host93_reset_launch'):
            x=fixture(True,'host-generation-diagnostic');row=copy.deepcopy(x['stage_exits.json']['stages'][-1]);row['name']=name;x['stage_exits.json']['stages'].append(row)
            with self.subTest(name=name),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_schema_requires_attempted_census(self):
        for value in (None,CENSUS.empty_report()):
            x=fixture(True,'host-generation-diagnostic');x['summary.json']['generation_diagnostics']=value
            with self.subTest(value=value),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_census_forbidden_before_generation(self):
        x=fixture(False,'host-generation-diagnostic');x['summary.json']['generation_diagnostics']=generation_fixture_report()
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_census_forbidden_in_other_modes(self):
        for mode in ('host-reset-launch','build-diagnostic','host-chirrtl-diagnostic'):
            x=fixture(True,mode);x['summary.json']['generation_diagnostics']=generation_fixture_report()
            with self.subTest(mode=mode),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_completed_component_requires_all_clean_stages(self):
        for action in ('missing','failed','report'):
            x=fixture(True,'host-generation-diagnostic');x['summary.json']['status']='INCOMPLETE';x['summary.json']['failure_category']='SYSTEM'
            if action=='missing': x['stage_exits.json']['stages'].pop()
            elif action=='failed':
                row=x['stage_exits.json']['stages'][-1];row.update(status='FAILED',exit_code=2,native_record_status='FAIL',failure_code='CHILD_EXIT_NONZERO',failure_boundary='NATIVE_SUPERVISION');row['diagnostics']['context_state']='READ_ERROR'
            else:x['summary.json']['generation_diagnostics']=CENSUS.empty_report('READ_ERROR')
            with self.subTest(action=action),self.assertRaises(ValueError):G.validate_evidence(x)

    def test_generation_status_cannot_be_full_ready(self):
        x=fixture(True,'host-generation-diagnostic');x['summary.json']['status']='READY_REQUIRES_ACTIONS_EXIT0'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_diagnostic_status_forbidden_in_full_mode(self):
        x=fixture(True);x['summary.json']['status']='DIAGNOSTIC_ONLY_REQUIRES_ACTIONS_EXIT0'
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_scope_needs_historical_fir_gate(self):
        code,summary,stages=self.mock_whole_job(mode='host-generation-diagnostic',diagnostic_match=False)
        self.assertEqual(code,1);self.assertEqual(len(stages),9);self.assertIsNone(summary['generation_diagnostics'])

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
        row=x['stage_exits.json']['stages'][-1];row.update(status='FAILED',**defaults());row['diagnostics']=G.empty_diagnostics('READ_ERROR')
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
    def test_successful_stage_context_rejected_for_every_stage(self):
        for index,name in enumerate(G.STAGES):
            x=fixture(True);row=x['stage_exits.json']['stages'][index]
            row['diagnostics'].update(context_state='AVAILABLE',merged_log_tail='context')
            with self.subTest(name=name),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_failed_stage_uncollected_context_rejected_for_every_stage(self):
        for index,name in enumerate(G.STAGES):
            x=fixture(True);row=x['stage_exits.json']['stages'][index]
            x['summary.json'].update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',
                contract_failure={'boundary':'UNREPORTED','code':'UNMAPPED_CONTRACT'})
            row.update(status='FAILED',exit_code=1,native_record_status='FAIL',
                failure_code='CHILD_EXIT_NONZERO',failure_boundary='NATIVE_SUPERVISION')
            with self.subTest(name=name),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_all_native_failures_collect_context_in_both_modes(self):
        for mode,names in (('host-reset-launch',G.STAGES),('build-diagnostic',G.BUILD_STAGES),('host-chirrtl-diagnostic',G.FRONTLOAD_STAGES),('host-generation-diagnostic',G.FIFO_STAGES+G.FRONTLOAD_STAGES[:-2]),('host-cluster-reset-launch',G.FIFO_STAGES+G.FRONTLOAD_STAGES)):
            for name in names:
                with self.subTest(mode=mode,name=name),mock.patch.object(G,'collect_build_diagnostics',wraps=G.collect_build_diagnostics) as collector:
                    code,summary,stages=self.mock_whole_job(name,mode,True,b'fixed native failure context\n')
                    self.assertEqual(code,1);self.assertEqual(stages[-1]['name'],name)
                    self.assertEqual([row['name'] for row in stages],list(names[:names.index(name)+1]))
                    self.assertEqual(stages[-1]['diagnostics']['context_state'],'AVAILABLE')
                    self.assertEqual(stages[-1]['diagnostics']['merged_log_tail'],'fixed native failure context')
                    self.assertEqual(stages[-1]['failure_code'],'CHILD_EXIT_NONZERO')
                    self.assertFalse(stages[-1]['receipt_timed_out'])
                    self.assertTrue(stages[-1]['cleanup_confirmed'])
                    self.assertTrue(all(row['diagnostics']==G.empty_diagnostics() for row in stages[:-1]))
                    collector.assert_called_once()
                    self.assertEqual(collector.call_args.args[2].parts[-3:],('phases',name,'native.log'))
    def test_all_native_failures_without_log_are_read_error(self):
        for name in G.STAGES:
            with self.subTest(name=name):
                code,summary,stages=self.mock_whole_job(name,nonzero=True)
                self.assertEqual(stages[-1]['diagnostics'],G.empty_diagnostics('READ_ERROR'))
                self.assertEqual(code,1)
    def test_chirrtl_stack_context_and_source_location_preserved(self):
        log=(b'CANONICAL_HOST93_CHIRRTL_BEGIN source=public\n'
             b'Exception in thread "main" java.lang.IllegalArgumentException: requirement failed\n'
             b'\tat demo.Emit.main(EmitCanonicalHost93.scala:17)\n'
             b'Caused by: java.lang.RuntimeException: fixed fixture failure\n')
        code,summary,stages=self.mock_whole_job('host93_chirrtl',nonzero=True,context=log)
        tail=stages[-1]['diagnostics']['merged_log_tail']
        self.assertIn('requirement failed',tail);self.assertIn('EmitCanonicalHost93.scala:17',tail)
        self.assertIn('\\tat demo.Emit.main',tail);self.assertIn('Caused by:',tail)
        self.assertEqual(stages[-1]['diagnostics']['observations'],[])
        self.assertTrue(summary['scope']['toolchain_build']);self.assertTrue(summary['scope']['toolchain_tiny'])
        self.assertFalse(summary['scope']['fresh_host_sv']);self.assertFalse(summary['scope']['weights_loaded'])
        self.assertEqual(stages[-1]['failure_boundary'],'NATIVE_SUPERVISION')
    def test_acquisition_context_redacts_transport_text(self):
        log=(b'fetch failed https://user:tiny-secret@example.invalid/private\n'
             b'Authorization: Bearer fixture-auth\n'
             b'CMAKE_PRIVATE_AUTHENTICATION_SERVICE_PASSWORD="tiny-secret"\n'
             b'failed opening /private/cache/input.scala\n'
             b'ordinary acquisition error remains\n')
        with mock.patch.dict(G.os.environ,{'HTTPS_PROXY':'must-not-read-this-value'},clear=True):
            code,summary,stages=self.mock_whole_job('host93_acquire_jar87',nonzero=True,context=log)
        tail=stages[-1]['diagnostics']['merged_log_tail']
        for secret in ('tiny-secret','fixture-auth','example.invalid','/private','must-not-read-this-value'):
            self.assertNotIn(secret,tail)
        self.assertIn('[URL]',tail);self.assertIn('[AUTH_HEADER]',tail);self.assertIn('[PATH]',tail)
        self.assertIn('ordinary acquisition error remains',tail)
    def test_chirrtl_tail_controls_and_large_input_keep_existing_caps(self):
        log=b'old context\n'*(G.MIB//10)+b'\n'+b'\n'.join([b'x'*700 for _ in range(90)])+b'\nlast line\tvisible\x1b\n'
        code,summary,stages=self.mock_whole_job('host93_chirrtl',nonzero=True,context=log)
        d=stages[-1]['diagnostics'];G.validate_diagnostics(d)
        self.assertTrue(d['truncated']);self.assertEqual(d['context_state'],'AVAILABLE')
        self.assertLessEqual(len(d['merged_log_tail'].split('\n')),80)
        self.assertTrue(d['merged_log_tail'].endswith('last line\\tvisible\\x1b'))
        self.assertNotIn('old context',d['merged_log_tail'])
        self.assertLessEqual(len(CONTEXT.canonical_json(d)),16384)
    def test_success_never_calls_context_collector(self):
        with mock.patch.object(G,'collect_build_diagnostics') as collector:
            code,summary,stages=self.mock_whole_job()
        self.assertEqual(code,0);collector.assert_not_called()
    def test_postflight_contract_does_not_relabel_success_as_native_failure(self):
        with mock.patch.object(G,'collect_build_diagnostics') as collector:
            code,summary,stages=self.mock_whole_job(contract_postflight=True)
        self.assertEqual(code,1);collector.assert_not_called()
        self.assertTrue(all(row['diagnostics']==G.empty_diagnostics() for row in stages))
    def test_chirrtl_sanitizer_error_is_explicit_and_not_private_text(self):
        with mock.patch.object(CONTEXT,'sanitize_build_context',side_effect=ValueError('private-token-fixture')):
            code,summary,stages=self.mock_whole_job('host93_chirrtl',nonzero=True,context=b'fixture')
        self.assertEqual(stages[-1]['diagnostics'],G.empty_diagnostics('SANITIZER_ERROR'))
        self.assertNotIn('private-token-fixture',json.dumps(summary)+json.dumps(stages))
    def test_native_timeout_collects_context_without_changing_classification(self):
        code,summary,stages=self.mock_whole_job('host93_cpp_compile',context=b'last compile line\n')
        self.assertEqual(summary['failure_category'],'TIMEOUT')
        self.assertEqual(stages[-1]['failure_code'],'SUPERVISOR_TIMEOUT_CLASSIFICATION')
        self.assertTrue(stages[-1]['receipt_timed_out'])
        self.assertEqual(stages[-1]['diagnostics']['merged_log_tail'],'last compile line')
    def test_v3_stage_evidence_requires_original_validator(self):
        x=fixture(True);x['stage_exits.json']['schema']='host93-ci-stage-exits-v3'
        with self.assertRaises(ValueError):G.validate_evidence(x)
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

    def test_fifo_three_stage_prefix_and_original_modes(self):
        self.assertEqual(G.mode_stages('host-generation-diagnostic'),G.FIFO_STAGES+G.FRONTLOAD_STAGES[:-2])
        for mode in ('host-reset-launch','host-chirrtl-diagnostic','build-diagnostic'):
            self.assertTrue(set(G.FIFO_STAGES).isdisjoint(G.mode_stages(mode)))
    def test_fifo_native_failure_stops_before_host_or_tools(self):
        for name in G.FIFO_STAGES:
            code,summary,rows=self.mock_whole_job(name,'host-generation-diagnostic',True,b'finite FIFO failure\n')
            self.assertEqual(code,1);self.assertEqual(rows[-1]['name'],name)
            self.assertEqual(summary['fifo_observation'],G.empty_fifo_observation())
            self.assertEqual(summary['completed_components'],[])
            self.assertFalse(any(summary['scope'].values()))
    def test_fifo_claim_requires_native_rows_and_tools(self):
        for kind in ('no_rows','missing_tool','wrong_hash','case_bool','bad_count','failed_row','signal','no_kill'):
            x=fixture(True,'host-generation-diagnostic');f=x['summary.json']['fifo_observation'];rows=x['stage_exits.json']['stages']
            if kind=='no_rows':rows.clear()
            elif kind=='missing_tool':f['tools'].pop('vvp')
            elif kind=='wrong_hash':f['tools']['icarus']['sha256']='0'*64
            elif kind=='case_bool':f['cases']=True
            elif kind=='bad_count':f['comparisons']=5120
            elif kind=='failed_row':rows[1]['status']='FAILED'
            elif kind=='signal':rows[1].update(waitid_code=2,waitid_status=9)
            else:rows[1].update(kill_attempted=False,kill_result='NOT_REQUESTED')
            with self.subTest(kind=kind),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_fifo_forbidden_in_other_modes(self):
        for mode in ('host-reset-launch','host-chirrtl-diagnostic','build-diagnostic'):
            x=fixture(True,mode);x['summary.json']['fifo_observation']=fixture(True,'host-generation-diagnostic')['summary.json']['fifo_observation']
            with self.subTest(mode=mode),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_fifo_no_qualification_no_host_continuation(self):
        x=fixture(True,'host-generation-diagnostic');x['summary.json']['completed_components']=[]
        x['summary.json']['fifo_observation']=G.empty_fifo_observation()
        with self.assertRaises(ValueError):G.validate_evidence(x)
    def test_generation_historical_mismatch_retains_fifo_only(self):
        code,summary,rows=self.mock_whole_job(mode='host-generation-diagnostic',diagnostic_match=False)
        self.assertEqual(code,1);self.assertEqual(len(rows),9)
        self.assertEqual(summary['completed_components'],['fifo_preflight','chirrtl_diagnostic'])
        self.assertEqual(summary['fifo_observation']['comparisons'],5180)
        self.assertFalse(any(summary['scope'].values()))
    def test_generation_reported_failure_retains_fifo(self):
        values={'utf8_bytes':96*G.MIB+1,'line_count':293837,'module_count':682,'extmodule_count':17,'source_info_count':254482,'source_info_utf8_bytes':1000000,'project_source_info_count':249537,'library_source_info_count':4945,'other_source_info_count':0}
        log=DIAGNOSTIC.MARKER+b' '.join(k.encode()+b'='+str(values[k]).encode() for k in G.CHIRRTL_NUMERIC)+b'\nException: cap\n'
        code,summary,rows=self.mock_whole_job('host93_chirrtl_diagnostic','host-generation-diagnostic',True,log)
        self.assertEqual(code,1);self.assertEqual(len(rows),9)
        self.assertEqual(summary['completed_components'],['fifo_preflight'])
        self.assertEqual(summary['chirrtl_observation']['state'],'REPORTED')

    def test_fifo_parent_labels_bound_to_clean_prefix(self):
        for boundary,counts in G.FIFO_CONTRACT_COUNTS.items():
            for count in counts:
                code,summary,rows=self.mock_whole_job(mode='host-generation-diagnostic',fifo_contract=(boundary,count))
                self.assertEqual(code,1);self.assertEqual(len(rows),count)
                self.assertTrue(all(row['status']=='EXIT0_CLEANED' for row in rows))
                self.assertEqual(summary['contract_failure'],{'boundary':boundary,'code':G.FIFO_CONTRACTS[boundary]})
                self.assertEqual(summary['fifo_observation'],G.empty_fifo_observation())
                self.assertNotIn('private finite',str(summary))
    def test_fifo_parent_labels_reject_wrong_native_progress(self):
        for boundary,count in (('ICARUS_RECEIPT_READ',0),('FIFO_COMPILED_MODULES',1),('FIFO_RUN_OBSERVATION',2)):
            x=fixture(False,'host-generation-diagnostic')
            x['source_hashes.json']['project_sources']=[{'path':n,**p} for n,p in sorted(PINS.items())]
            x['stage_exits.json']['stages']=fixture(True,'host-generation-diagnostic')['stage_exits.json']['stages'][:count]
            x['summary.json']['contract_failure']={'boundary':boundary,'code':G.FIFO_CONTRACTS[boundary]}
            with self.subTest(boundary=boundary),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_fifo_parent_labels_reject_failed_native_or_wrong_code(self):
        for kind in ('failed','code','completed'):
            x=fixture(False,'host-generation-diagnostic')
            x['source_hashes.json']['project_sources']=[{'path':n,**p} for n,p in sorted(PINS.items())]
            x['stage_exits.json']['stages']=fixture(True,'host-generation-diagnostic')['stage_exits.json']['stages'][:1]
            x['summary.json']['contract_failure']={'boundary':'ICARUS_RECEIPT_READ','code':'RECEIPT_READ'}
            if kind=='failed':
                x['stage_exits.json']['stages'][0].update(status='FAILED',exit_code=1,waitid_status=1,native_record_status='FAIL',failure_code='CHILD_EXIT_NONZERO',failure_boundary='NATIVE_SUPERVISION',diagnostics=G.empty_diagnostics('READ_ERROR'))
            elif kind=='code':x['summary.json']['contract_failure']['code']='DIAGNOSTIC_EMITTER'
            else:x['summary.json']['completed_components']=['fifo_preflight']
            with self.subTest(kind=kind),self.assertRaises(ValueError):G.validate_evidence(x)

    def test_fifo_adapter_labels_match_fixed_source(self):
        self.assertEqual(G.FIFO_CONTRACTS,PREFLIGHT.PARENT_CONTRACTS)
        self.assertEqual(G.FIFO_CONTRACT_COUNTS,PREFLIGHT.CONTRACT_COMPLETED_COUNTS)
        self.assertEqual(set(G.FIFO_REQUIRE_CODES),set(PREFLIGHT.REQUIRE_CODES.values()))
        for name,pin in PREFLIGHT.REQUIRED_SOURCES.items():self.assertEqual(PINS[name],pin)

    def test_cluster_mode37_same_job_no_duplicate_stage(self):
        code,summary,rows=self.mock_whole_job(mode='host-cluster-reset-launch')
        self.assertEqual(code,0);self.assertEqual(len(rows),37);self.assertEqual(len(set(x['name'] for x in rows)),37)
        self.assertEqual([x['name'] for x in rows],list(G.FIFO_STAGES+G.FRONTLOAD_STAGES))
        self.assertEqual(summary['completed_components'],['fifo_preflight','chirrtl_diagnostic']+list(G.COMPONENTS))
        self.assertTrue(all(summary['scope'][x] for x in G.SCOPES[:6]))
        self.assertFalse(summary['scope']['n0_numeric']);self.assertFalse(summary['scope']['weights_loaded'])
        self.assertEqual(summary['generation_diagnostics']['wrapper']['cluster_structure']['root_header_state'],'UNRECOGNIZED_SYNTAX')
    def test_cluster_ready_fixture_and_unknown_handles_remain_unknown(self):
        x=fixture(True,'host-cluster-reset-launch');self.assertTrue(G.validate_evidence(x))
        self.assertIsNone(x['summary.json']['generation_diagnostics']['wrapper']['cluster_structure']['instance_handle_count'])
    def test_cluster_compile_or_runtime_failure_stops_and_keeps_census(self):
        for name in ('host93_cpp_compile','host93_reset_launch'):
            code,summary,rows=self.mock_whole_job(name,'host-cluster-reset-launch',True,b'fixed native failure\n')
            self.assertEqual(code,1);self.assertEqual(rows[-1]['name'],name)
            self.assertEqual(rows[-1]['status'],'FAILED');self.assertFalse(summary['scope']['reset_launch'])
            self.assertEqual(summary['generation_diagnostics']['state'],'AVAILABLE')
    def test_cluster_bad_census_cannot_qualify_compile(self):
        for kind in ('missing','old_wrapper','unknown_make','missing_combo','partial','wrong_inputs'):
            x=fixture(True,'host-cluster-reset-launch');r=x['summary.json']['generation_diagnostics']
            if kind=='missing':x['summary.json']['generation_diagnostics']=None
            elif kind=='old_wrapper':r['wrapper']['module']='qwen2_matrix_command_endpoint'
            elif kind=='unknown_make':r['wrapper']['cluster_structure']['makegraph_state']='MISSING'
            elif kind=='missing_combo':r['wrapper']['combo_update_call_count']=0
            elif kind=='partial':r['caps']['partial']=True
            else:r['wrapper']['combo_input_count']=17
            with self.subTest(kind=kind),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_cluster_codegen_prefix_cannot_be_skipped_or_failed(self):
        for kind in ('remove','swap','failed'):
            x=fixture(True,'host-cluster-reset-launch');rows=x['stage_exits.json']['stages']
            if kind=='remove':del rows[34]
            elif kind=='swap':rows[34],rows[35]=rows[35],rows[34]
            else:rows[34]['status']='FAILED'
            with self.subTest(kind=kind),self.assertRaises(ValueError):G.validate_evidence(x)
    def test_cluster_contract_label_exact_progress(self):
        for count in (35,36,37):
            x=fixture(True,'host-cluster-reset-launch');x['stage_exits.json']['stages']=x['stage_exits.json']['stages'][:count]
            s=x['summary.json'];s.update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',contract_failure={'boundary':'CLUSTER_GENERATION_WITNESS','code':'CLUSTER_INITIALIZER'})
            s['completed_components'].pop();s['scope'].update(cpp_generated=False,cpp_compiled=False,reset_launch=False)
            x['source_hashes.json']['generated'].pop('host_elf')
            self.assertTrue(G.validate_evidence(x))
        x['stage_exits.json']['stages']=x['stage_exits.json']['stages'][:34]
        with self.assertRaises(ValueError):G.validate_evidence(x)


def n0_fixture(passed=True,exact=False):
    x=fixture(True,'host-cluster-reset-launch');s=x['summary.json'];s.update(schema='host93-ci-summary-v7',mode=G.N0_MODE,status=G.success_status(G.N0_MODE) if passed else 'N0_LIMITED_TOLERANCE_FAIL',failure_category='NONE' if passed else 'NUMERIC_MISMATCH',completed_components=list(G.mode_components(G.N0_MODE)))
    s['scope'].update(reset_launch=False,n0_numeric=passed,weights_loaded=True)
    s['n0_observation']=PIPELINE.empty_observation();s['n0_observation'].update(state='COMPLETE',runtime_ready=True,inputs_ready=True,reference_ready=True,reference_rss=copy.deepcopy(RSS),capture_state='AVAILABLE',capture=n0_counts(),comparison_state='AVAILABLE',comparison=n0_comparison(passed,exact),comparison_rss=copy.deepcopy(RSS))
    x['stage_exits.json']['stages']=[{'name':n,'status':'EXIT0_CLEANED','seconds':.1,'diagnostics':G.empty_diagnostics(),**clean_observation()} for n in G.mode_stages(G.N0_MODE)]
    if not passed:x['stage_exits.json']['stages'][-1].update(status='FAILED',exit_code=1,waitid_status=1,native_record_status='FAIL',failure_boundary='NATIVE_SUPERVISION',failure_code='CHILD_EXIT_NONZERO',diagnostics=G.empty_diagnostics('READ_ERROR'))
    return x

class N0Cold(unittest.TestCase):
    def validate(self,x):
        with mock.patch.object(G,'n0_schema_module',return_value=PIPELINE),mock.patch.object(G,'n0_comparison_module',return_value=COMPARATOR):return G.validate_evidence(x)
    def cycle_fixture(self):
        x=n0_fixture();s=x['summary.json'];s.update(status='INCOMPLETE',failure_category='UNEXPECTED',completed_components=list(G.mode_components(G.N0_MODE)[:-2]));s['scope'].update(n0_numeric=False,weights_loaded=False)
        c=n0_counts();c.update(status='INCOMPLETE_CYCLE_BUDGET',phase='RTL_N0',code='CYCLE_BUDGET',cycles=8000000,completion_acks=0,actual_values=0,actual_bytes=0);c['axi'].update(ar_stall=500,aw_stall=400,w_stall=300,r_stall=200,b_stall=100)
        s['n0_observation'].update(state='COLLECTING',capture_state='REPORTED',capture=c,comparison_state='NOT_COLLECTED',comparison=None,comparison_rss=None)
        del x['stage_exits.json']['stages'][-1];x['stage_exits.json']['stages'][-1].update(status='FAILED',exit_code=2,waitid_status=2,native_record_status='FAIL',failure_boundary='NATIVE_SUPERVISION',failure_code='CHILD_EXIT_NONZERO',diagnostics=G.empty_diagnostics('READ_ERROR'))
        return x
    def test_cycle_budget_retains_counts_without_numeric_qualification(self):self.assertTrue(self.validate(self.cycle_fixture()))
    def test_cycle_budget_cannot_hide_timeout_or_signal(self):
        for field,value in [('receipt_timed_out',True),('waitid_code',2),('cleanup_confirmed',False)]:
            x=self.cycle_fixture();x['stage_exits.json']['stages'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(x)
    def test_cycle_budget_rejects_bad_or_private_counts(self):
        for field,value in [('cycles',7999999),('completion_acks',1),('actual_values',196608),('private_path','/secret')]:
            x=self.cycle_fixture();x['summary.json']['n0_observation']['capture'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(x)
    def test_cycle_stall_bound(self):
        x=self.cycle_fixture();x['summary.json']['n0_observation']['capture']['axi']['b_stall']=8000001
        with self.assertRaises(ValueError):self.validate(x)
    def reference_after_compare_failure(self):
        x=n0_fixture(False);s=x['summary.json'];s.update(status='INCOMPLETE',failure_category='INPUT_OR_CONTRACT',contract_failure={'boundary':'N0_REFERENCE_RECEIPT','code':'N0_REFERENCE'});s['completed_components'].remove('n0_comparison');s['n0_observation'].update(state='COLLECTING',comparison_state='READ_ERROR',comparison=None,comparison_rss=None);return x
    def test_reference_postread_after_natural_compare_failure(self):self.assertTrue(self.validate(self.reference_after_compare_failure()))
    def test_reference_postread_exception_is_narrow(self):
        for kind in ('timeout','signal','cleanup','unrelated_boundary','wrong_count'):
            x=self.reference_after_compare_failure();row=x['stage_exits.json']['stages'][-1]
            if kind=='timeout':row['receipt_timed_out']=True
            elif kind=='signal':row['waitid_code']=2
            elif kind=='cleanup':row['cleanup_confirmed']=False
            elif kind=='unrelated_boundary':x['summary.json']['contract_failure']={'boundary':'N0_CAPTURE_RECEIPT','code':'N0_CAPTURE'}
            else:x['stage_exits.json']['stages'].pop()
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.validate(x)
    def test_new_mode_shared_deadline_fixed_label(self):
        code,summary,rows=Cold().mock_whole_job(mode=G.N0_MODE,phase_deadline=True)
        self.assertEqual(code,1);self.assertEqual(rows,[]);self.assertEqual(summary['contract_failure'],{'boundary':'N0_DEADLINE','code':'N0_DEADLINE'})
    def test_new_order43(self):
        self.assertEqual(len(G.mode_stages(G.N0_MODE)),43);self.assertEqual(G.mode_stages(G.N0_MODE)[:5],G.N0_FRONT_STAGES);self.assertEqual(G.mode_stages(G.N0_MODE)[-3:],('host93_cpp_compile','host93_first_n0','host93_n0_compare'));self.assertNotIn('host93_reset_launch',G.mode_stages(G.N0_MODE))
    def test_complete_tolerance_and_exact_separate(self):
        for exact in (False,True):self.assertTrue(self.validate(n0_fixture(True,exact)))
    def test_complete_numeric_fail(self):self.assertTrue(self.validate(n0_fixture(False)))
    def test_new_whole_mock_success(self):
        code,summary,rows=Cold().mock_whole_job(mode=G.N0_MODE);self.assertEqual(code,0);self.assertEqual(len(rows),43);self.assertTrue(summary['scope']['n0_numeric']);self.assertFalse(summary['scope']['reset_launch'])
    def test_first_failure_all43(self):
        for phase in G.mode_stages(G.N0_MODE):
            with self.subTest(phase=phase):
                code,s,rows=Cold().mock_whole_job(phase,G.N0_MODE,True,b'private tensor values must never escape');self.assertEqual(code,1);self.assertEqual(rows[-1]['name'],phase);self.assertFalse(s['scope']['n0_numeric'])
                if phase in PIPELINE.PRIVATE_STAGES:self.assertNotIn('private tensor',json.dumps(s)+json.dumps(rows))
    def test_prefix_missing_each_front_or_capture(self):
        for i in (*range(5),40,41,42):
            x=n0_fixture();del x['stage_exits.json']['stages'][i]
            with self.subTest(i=i),self.assertRaises(ValueError):self.validate(x)
    def test_capture_tuple_cannot_claim_signal(self):
        for field,value in [('waitid_status',9),('waitid_code',2),('receipt_timed_out',True),('cleanup_confirmed',False),('kill_attempted',False)]:
            x=n0_fixture();x['stage_exits.json']['stages'][41][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(x)
    def test_capture_protocol_fields(self):
        for field,value in [('successful_b',12287),('actual_values',196607),('writeback_bytes',0),('completion_acks',0),('phase','RTL_N0'),('code','CYCLE_BUDGET'),('root256_handles',256)]:
            x=n0_fixture();x['summary.json']['n0_observation']['capture'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(x)
    def test_compare_bad_denominator_or_unapproved_metric(self):
        for field,value in [('elements',1),('max_abs',float('nan')),('finite',False),('first_difference_flat',0)]:
            x=n0_fixture();x['summary.json']['n0_observation']['comparison']['metrics'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(x)
    def test_compare_tolerance_not_exact_required(self):
        x=n0_fixture();self.assertFalse(x['summary.json']['n0_observation']['comparison']['bit_exact']);self.assertTrue(self.validate(x))
    def test_compare_larger_threshold_rejected(self):
        x=n0_fixture();x['summary.json']['n0_observation']['comparison']['limits']['max_abs']=1.
        with self.assertRaises(ValueError):self.validate(x)
    def test_unknown_fields_and_paths_rejected(self):
        for target in ('observation','capture','comparison'):
            x=n0_fixture();o=x['summary.json']['n0_observation'];(o if target=='observation' else o[target])['private_path']='/secret'
            with self.subTest(target=target),self.assertRaises(ValueError):self.validate(x)
    def test_compare_failure_cannot_hide_timeout(self):
        x=n0_fixture(False);x['stage_exits.json']['stages'][-1].update(receipt_timed_out=True)
        with self.assertRaises(ValueError):self.validate(x)
    def test_resources_exact(self):
        self.assertEqual(G.PHASE_CAPS['host93_first_n0'][:4],(3540,3510,3540,6*G.GIB));self.assertEqual(G.PHASE_CAPS['host93_n0_compare'][:4],(30,15,25,8*G.GIB));self.assertEqual(PIPELINE.empty_observation()['cycle_cap'],8000000)
    def test_bad_private_diagnostic_not_generic_sanitizer(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'log';p.write_bytes(b'private payload [1,2,3] password=secret')
            with mock.patch.object(PIPELINE,'fixed_markers',return_value={'NOT_COMPLETED:RESOURCE'}):
                value=PIPELINE.private_diagnostics(Path(t),{},'n0_reference',p)
            self.assertEqual(value['merged_log_tail'],'PRIVATE_PHASE_FAILED:NO_FIXED_STATUS_MARKER');self.assertNotIn('payload',json.dumps(value))
    def test_private_marker_only(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'log';p.write_bytes(b'secret\nNOT_COMPLETED:RESOURCE\nNOT_COMPLETED:invented-secret\n')
            with mock.patch.object(PIPELINE,'fixed_markers',return_value={'NOT_COMPLETED:RESOURCE'}):value=PIPELINE.private_diagnostics(Path(t),{},'n0_reference',p)
            self.assertEqual(value['merged_log_tail'],'NOT_COMPLETED:RESOURCE')
    def test_private_read_failure_explicit(self):
        with tempfile.TemporaryDirectory() as t:self.assertEqual(PIPELINE.private_diagnostics(Path(t),{},'n0_reference',Path(t)/'missing')['context_state'],'READ_ERROR')
    def test_deadline_never_restarts(self):
        bound=PIPELINE.limits(120,100,90,8*G.GIB,4*G.MIB)
        with mock.patch.object(PIPELINE.time,'monotonic',return_value=100):
            actual=PIPELINE.cap_deadline(bound,130);self.assertEqual(actual['total_seconds'],30);self.assertEqual(actual['work_seconds'],15)
            with self.assertRaises(ValueError):PIPELINE.cap_deadline(bound,116)

if __name__=='__main__':unittest.main(verbosity=2)
