"""Small function-level cold tests; the production run/main are never invoked."""
import argparse
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / 'public' / 'run_owner_micro.py'
REPO = HERE.parents[2] / 'hetero_ci_recovery_20261019T0039'
PIN = (25935, '9eaf9a3029e905e1eaaaf1cdd7d72778b5a7556a96435513c95ef92be5372144')
SUPERVISOR_PIN = (16348, '653de8cdfbdbb5ffe9b3725467ee0f44c98da353e1d680fec4f282d2b73d00d1')
ENTRY_PIN = (2050, 'd094bedceb61d37e97154289a7efd55d6e55904546751c982439dd86e2bd38bc')
PARSER = argparse.ArgumentParser(allow_abbrev=False)
PARSER.add_argument('--source', type=Path, default=SOURCE)
PARSER.add_argument('--entry', type=Path)
PARSER.add_argument('--repo', type=Path, default=REPO)
PARSER.add_argument('--mode', choices=('normal', 'optimized', 'relocated', 'relocated_optimized'), default='normal')
ARGS = PARSER.parse_args()
SOURCE = ARGS.source.resolve(strict=True)
ENTRY_SOURCE = (ARGS.entry or SOURCE.parent / 'launch.py').resolve(strict=True)
REPO = ARGS.repo.resolve(strict=True)


def audit(event, args):
    if event.startswith(('subprocess.', 'socket.')) or event in (
        'os.system', 'os.fork', 'os.forkpty', 'os.exec', 'os.posix_spawn',
        'ctypes.dlopen', 'urllib.Request'):
        raise RuntimeError('COLD_NATIVE_NETWORK_FORBIDDEN')
    if event == 'import' and str(args[0]).split('.')[0] in ('numpy', 'scipy', 'torch', 'ctypes'):
        raise RuntimeError('COLD_NUMERICAL_IMPORT_FORBIDDEN')


sys.addaudithook(audit)


def pin(raw):
    return len(raw), hashlib.sha256(raw).hexdigest()


def load():
    if PIN is None:
        raise RuntimeError('COLD_SOURCE_FREEZE_REQUIRED')
    raw = SOURCE.read_bytes()
    if pin(raw) != PIN:
        raise RuntimeError('COLD_SOURCE_IDENTITY')
    module = types.ModuleType('fixed_owner_caller')
    module.__file__ = str(SOURCE)
    exec(compile(raw, str(SOURCE), 'exec', dont_inherit=True), module.__dict__)
    return module


R = load()


class Loading(unittest.TestCase):
    def test_source_has_no_automatic_run_and_no_assert_guards(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(pin(raw), PIN)
        tree = ast.parse(raw)
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(tree)))
        for n in tree.body:
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
                self.fail('Unexpected top-level action')

    def test_read_exact_verified_buffer(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(R.read(SOURCE, PIN), raw)

    def test_module_uses_same_verified_buffer_when_file_changes(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'module.py'; raw = b'VALUE = 73\n'; path.write_bytes(raw)
            compiler = builtins.compile; seen = []
            def compile_buffer(buf, *args, **kwargs):
                seen.append(buf); path.write_bytes(b'VALUE = 99\n')
                return compiler(buf, *args, **kwargs)
            with mock.patch.object(builtins, 'compile', side_effect=compile_buffer):
                loaded = R.module(path, pin(raw), 'same_checked_buffer')
            self.assertEqual(loaded.VALUE, 73)
            self.assertEqual(seen, [raw])

    def test_size_hash_and_missing_pin_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'module.py'; raw = b'VALUE = 73\n'
            for changed, wanted in ((raw[:-1], pin(raw)), (raw+b'\n', pin(raw)),
                                    (b'VALUE = 74\n', pin(raw)), (raw, None), (raw, [len(raw), pin(raw)[1]])):
                with self.subTest(changed=changed, wanted=wanted):
                    path.write_bytes(changed)
                    with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled invalid source')) as compiler:
                        with self.assertRaises(ValueError):
                            R.module(path, wanted, 'invalid')
                        compiler.assert_not_called()

    def test_symlink_rejected_before_compile(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'module.py'; raw=b'VALUE = 73\n'; path.write_bytes(raw)
            alias=Path(folder)/'alias.py'; alias.symlink_to(path)
            with mock.patch.object(builtins, 'compile', side_effect=AssertionError('compiled symlink')) as compiler:
                with self.assertRaisesRegex(ValueError, 'SOURCE_CANONICAL'):
                    R.module(alias, pin(raw), 'invalid')
                compiler.assert_not_called()

    def test_original_supervisor_loaded_exactly_without_projection_or_native(self):
        path=REPO/'candidates/host93_ci_recovery/ci_support_v3.py'
        before=path.read_bytes(); self.assertEqual(pin(before), SUPERVISOR_PIN)
        compiler=builtins.compile; seen=[]
        def compile_buffer(buf,*args,**kwargs):
            seen.append(buf); return compiler(buf,*args,**kwargs)
        with mock.patch.object(builtins,'compile',side_effect=compile_buffer):
            supervisor=R.module(path,SUPERVISOR_PIN,'cold_original_supervisor')
        self.assertEqual(seen,[before])
        self.assertEqual(supervisor.SHARED_SECONDS,6600)
        self.assertTrue(callable(supervisor.run_phase))
        self.assertEqual(path.read_bytes(),before)

    def test_parent_calls_original_supervisor_through_module_not_projected(self):
        tree=ast.parse(SOURCE.read_bytes())
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        assignment=next(n for n in ast.walk(run) if isinstance(n,ast.Assign) and
                        any(isinstance(t,ast.Name) and t.id=='supervisor' for t in n.targets))
        self.assertIsInstance(assignment.value,ast.Call)
        self.assertEqual(assignment.value.func.id,'module')
        self.assertIn('candidates/host93_ci_recovery/ci_support_v3.py',ast.unparse(assignment.value))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='projected'
                             for n in ast.walk(run)))


class Projections(unittest.TestCase):
    def test_exact_counts_inverse_and_identities(self):
        raw=b'old_a old_a old_b\n'; replacements=((b'old_a',b'new_a',2),(b'old_b',b'new_b',1))
        derived,proof=R.projected(raw,replacements)
        self.assertEqual(derived,b'new_a new_a new_b\n')
        self.assertEqual(proof,{'original':R.pin(raw),'derived':R.pin(derived),'inverse_exact':True,
                              'substitutions':[{'old':'old_a','new':'new_a','count':2},
                                               {'old':'old_b','new':'new_b','count':1}]})

    def test_missing_duplicate_and_existing_new_anchor_rejected(self):
        for raw in (b'not_here',b'old old',b'old new'):
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,'EXACT_PROJECTION_ANCHOR'):
                R.projected(raw,((b'old',b'new',1),))

    def test_overlapping_projection_cannot_pass_inverse(self):
        with self.assertRaisesRegex(ValueError,'EXACT_PROJECTION_INVERSE'):
            R.projected(b'aba',((b'b',b'aa',1),))

    def test_real_owner_adapters_use_seven_fixed_replacements_preserving_schema(self):
        executor=R.module(REPO/R.EXECUTOR,R.EXECUTOR_PIN,'cold_fixed_executor')
        census_original=R.module(REPO/R.CENSUS,R.CENSUS_PIN,'cold_fixed_census')
        raw_census=(REPO/R.CENSUS).read_bytes(); raw_executor=(REPO/R.EXECUTOR).read_bytes()
        census,witness,proof=R.owner_adapters(REPO,executor)
        self.assertEqual(census.empty_report(),census_original.empty_report())
        self.assertTrue(callable(witness))
        self.assertEqual(proof['census']['substitutions'],[
            {'old':'HostBlockTop__DOT__owner__DOT__matrix','new':'QwenOwnerKernel__DOT__matrix','count':1},
            {'old':'VHostBlockTop','new':'VQwenOwnerKernel','count':5},
            {'old':'VERILATED_VHOSTBLOCKTOP','new':'VERILATED_VQWENOWNERKERNEL','count':1}])
        self.assertEqual(proof['witness']['substitutions'],[
            {'old':'VHostBlockTop','new':'VQwenOwnerKernel','count':8},
            {'old':'len(ports) == 83','new':'len(ports) == 196','count':1},
            {'old':"'host_ports': 83",'new':"'owner_ports': 196",'count':1},
            {'old':'FINITE_CLUSTER_RESET_LAUNCH_WITNESS','new':'FINITE_CLUSTER_OWNER_MICRO_SOURCE_WITNESS','count':1}])
        self.assertTrue(proof['census']['inverse_exact']);self.assertTrue(proof['witness']['inverse_exact'])
        self.assertEqual(proof['census']['original'],R.pin(raw_census))
        self.assertEqual((REPO/R.CENSUS).read_bytes(),raw_census)
        self.assertEqual((REPO/R.EXECUTOR).read_bytes(),raw_executor)
        self.assertEqual(census.MAX_REPORT_BYTES,census_original.MAX_REPORT_BYTES)
        self.assertEqual(census.MAX_LOG_BYTES,census_original.MAX_LOG_BYTES)


class Commands(unittest.TestCase):
    def setUp(self):
        self.work=Path('/fixed/fresh');self.configuration=Path('/fixed/config')
        self.n0=Path('/fixed/n0');self.wq=Path('/fixed/wq')
        self.toolchain={'backend':{'path':'/fixed/qualified/backend'}}
        self.closure={'defines':['TARGET_ASIC','TARGET_RTL','TARGET_SYNTHESIS','TARGET_VERILATOR'],
                      'includes':['/fixed/includes'],'sources':['/fixed/source.sv']}
        self.executor=R.module(REPO/R.EXECUTOR,R.EXECUTOR_PIN,'cold_command_executor')
        self.old=self.executor.commands(self.work,self.toolchain['backend'],self.closure,self.configuration)
        self.fake=types.SimpleNamespace(commands=mock.Mock(side_effect=lambda *args:self.old))

    def go(self):
        return R.commands(self.fake,self.work,self.toolchain,self.closure,self.configuration,self.n0,self.wq)

    def test_exact_old_command_projection_and_no_old_mutation(self):
        before=copy.deepcopy(self.old); actual=self.go()
        expected=copy.deepcopy(self.old['host93_cpp_generate'])
        for old,new in ((str(self.work/'fixtures/short_launch.cpp'),str(self.work/'fixtures/owner_micro.cpp')),
                        ('HostBlockTop','QwenOwnerKernel'),('VHostBlockTop','VQwenOwnerKernel')):
            expected[expected.index(old)]=new
        anchor=str(self.configuration/'precision_warnings.vlt')
        expected.insert(expected.index(anchor)+1,str(self.work/'fixtures/owner_readonly.vlt'))
        self.assertEqual(actual['generate'],expected)
        build=copy.deepcopy(self.old['host93_cpp_compile']);build[build.index('VHostBlockTop.mk')]='VQwenOwnerKernel.mk';build[-1]='VQwenOwnerKernel'
        self.assertEqual(actual['build'],build)
        self.assertEqual(actual['run'],[str(self.work/'obj/VQwenOwnerKernel'),str(self.n0),str(self.wq)])
        self.assertEqual(self.old,before)
        self.fake.commands.assert_called_once_with(self.work,self.toolchain['backend'],self.closure,self.configuration)

    def test_duplicate_missing_and_wrong_top_exe_prefix_rejected(self):
        original=copy.deepcopy(self.old)
        for flag in ('--exe','--top-module','--prefix'):
            for mode in ('duplicate','missing','wrong'):
                with self.subTest(flag=flag,mode=mode):
                    self.old=copy.deepcopy(original);argv=self.old['host93_cpp_generate'];i=argv.index(flag)
                    if mode=='duplicate':argv.extend([flag,argv[i+1]])
                    elif mode=='missing':del argv[i:i+2]
                    else:argv[i+1]='different'
                    with self.assertRaisesRegex(ValueError,'FIXED_GENERATE_MAPPING'):self.go()

    def test_precision_anchor_missing_or_duplicate_rejected(self):
        original=copy.deepcopy(self.old);anchor=str(self.configuration/'precision_warnings.vlt')
        for mode in ('missing','duplicate'):
            self.old=copy.deepcopy(original);argv=self.old['host93_cpp_generate']
            if mode=='missing':argv.remove(anchor)
            else:argv.append(anchor)
            with self.assertRaisesRegex(ValueError,'FIXED_CONFIG_ORDER'):self.go()

    def test_build_mk_and_target_mapping_reject_drift(self):
        original=copy.deepcopy(self.old)
        for mode in ('missing','duplicate','wrong_target'):
            self.old=copy.deepcopy(original);build=self.old['host93_cpp_compile']
            if mode=='missing':build.remove('VHostBlockTop.mk')
            elif mode=='duplicate':build.insert(0,'VHostBlockTop.mk')
            else:build[-1]='different'
            with self.assertRaisesRegex(ValueError,'FIXED_BUILD_MAPPING'):self.go()


class Observations(unittest.TestCase):
    def setUp(self):
        self.rows=[{'member':'QwenOwnerKernel__DOT__obs_'+str(i),'width':(1,8,9,16,17,32,33,64)[i%8]} for i in range(95)]
        lines=[]
        for row in self.rows:
            w=row['width'];kind='CData' if w<=8 else 'SData' if w<=16 else 'IData' if w<=32 else 'QData'
            lines.append(f"{kind}/*{w-1}:0*/ {row['member']};")
        self.header='\n'.join(lines)

    def test_exact_ninety_five_unique_names_and_widths(self):
        actual=R.observation_declarations(self.header,self.rows)
        self.assertEqual(len(actual),95)
        for row in self.rows:self.assertEqual(actual[row['member']]['width'],row['width'])

    def test_missing_extra_and_nonlist_observations_rejected(self):
        for rows in (self.rows[:-1],self.rows+[self.rows[0]],tuple(self.rows)):
            with self.assertRaisesRegex(ValueError,'EXACT_OBSERVATION_COUNT'):R.observation_declarations(self.header,rows)

    def test_wrong_width_type_range_and_prefix_rejected(self):
        for key,value in (('width',True),('width',0),('width',65),('width',1.0),('member','HostBlockTop__DOT__x')):
            with self.subTest(key=key,value=value):
                rows=copy.deepcopy(self.rows);rows[0][key]=value
                with self.assertRaisesRegex(ValueError,'FIXED_SCALAR_OBSERVATION'):R.observation_declarations(self.header,rows)

    def test_duplicate_requested_name_missing_header_or_wrong_width_rejected(self):
        for rows,header in (([self.rows[0]]*95,self.header),(self.rows,'\n'.join(self.header.splitlines()[1:])),
                            (self.rows,self.header.replace('CData/*0:0*/','CData/*1:0*/',1)),
                            (self.rows,self.header.replace('CData/*0:0*/','SData/*0:0*/',1)),
                            (self.rows,self.header.replace('CData/*0:0*/','CData/*0:1*/',1))):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_DECLARATION_MISMATCH'):R.observation_declarations(header,rows)

    def test_duplicate_root_declaration_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNIQUE_ROOT_DECLARATION'):
            R.observation_declarations(self.header+'\n'+self.header.splitlines()[0],self.rows)


class Toolchain(unittest.TestCase):
    def setUp(self):
        phase={'exit_code':0,'cleanup_confirmed':True}
        self.value={'status':'PASS_FRESH_DERIVED_TOOLCHAIN_AND_TINY_ONLY',
                    'source_commit':'4e194cc3ec8e27b18e17f80d7f99c15f984bbdae','source_members':473,
                    'backend':{**R.BACKEND_PIN,'path':'/fixed/backend'},
                    'patch':{'only_changed_member':'src/V3ProtectLib.cpp','replacement_count':1,
                             'fresh_build_no_reused_objects':True,
                             'derived':{'sha256':'380f292c6e82ce30cd7c0b3375ac3f2b91e5c1e872a2c733ca6d0490122cf6fb'}},
                    'build':{'compile':copy.deepcopy(phase)},
                    'tiny':{'status':'PASS_NEW_DERIVED_FOUR_STAGE_TINY',
                            'phases':{n:copy.deepcopy(phase) for n in ('generate','compile','run','version')}}}

    def test_exact_existing_backend_and_tiny_scope_accepted(self):
        self.assertIsNone(R.accept_toolchain(self.value))

    def test_revision_members_backend_patch_scope_drift_rejected(self):
        cases=[(('status',),'PASS'),(('source_commit',),'0'*40),(('source_members',),474),
               (('backend','sha256'),'0'*64),(('backend','bytes'),1),(('backend','mode'),'0o755'),
               (('patch','only_changed_member'),'src/other.cpp'),(('patch','replacement_count'),2),
               (('patch','fresh_build_no_reused_objects'),False),(('patch','derived','sha256'),'0'*64)]
        for path,bad in cases:
            with self.subTest(path=path):
                value=copy.deepcopy(self.value);slot=value
                for key in path[:-1]:slot=slot[key]
                slot[path[-1]]=bad
                with self.assertRaisesRegex(ValueError,'EXISTING_BACKEND_SCOPE'):R.accept_toolchain(value)

    def test_tiny_exact_four_phases_status_and_all_receipts_checked(self):
        for mode in ('missing','extra','status'):
            value=copy.deepcopy(self.value)
            if mode=='missing':del value['tiny']['phases']['version']
            elif mode=='extra':value['tiny']['phases']['extra']={'exit_code':0,'cleanup_confirmed':True}
            else:value['tiny']['status']='PASS'
            with self.assertRaisesRegex(ValueError,'EXISTING_TINY_SCOPE'):R.accept_toolchain(value)
        paths=[('build','compile')]+[('tiny',n) for n in ('generate','compile','run','version')]
        for section,name in paths:
            for key,bad in (('exit_code',1),('exit_code',False),('cleanup_confirmed',False)):
                with self.subTest(section=section,name=name,key=key):
                    value=copy.deepcopy(self.value)
                    target=value['build'][name] if section=='build' else value['tiny']['phases'][name]
                    target[key]=bad
                    with self.assertRaisesRegex(ValueError,'EXISTING_BACKEND_PHASE'):R.accept_toolchain(value)


class FailureFields(unittest.TestCase):
    def test_all_fixed_codes_project_only_exact_valueerror_and_timeouterror(self):
        for kind in (ValueError,TimeoutError):
            for code in R.FIXED_FAILURE_CODES:
                with self.subTest(kind=kind.__name__,code=code):
                    self.assertEqual(R.failure_fields(kind(code)),{
                        'failure_boundary':'OWNER_LOCAL_MICRO_FIXED_CONTRACT','failure_code':code})

    def test_only_known_paired_cluster_attributes_project(self):
        codes=('CLUSTER_CHILD_ARGS','CLUSTER_TOP_LINK','CLUSTER_LIBRARY_GRAPH','CLUSTER_INITIALIZER',
               'CLUSTER_ABI','CLUSTER_ARTIFACTS','CLUSTER_CENSUS')
        for code in codes:
            error=ValueError('private diagnostic must not escape')
            error.safe_contract_boundary='CLUSTER_GENERATION_WITNESS';error.safe_contract_code=code
            self.assertEqual(R.failure_fields(error),{
                'failure_boundary':'CLUSTER_GENERATION_WITNESS','failure_code':code})
        for boundary,code in (('UNKNOWN',codes[0]),('CLUSTER_GENERATION_WITNESS','UNKNOWN'),(None,codes[0])):
            error=RuntimeError('private diagnostic')
            error.safe_contract_boundary=boundary;error.safe_contract_code=code
            self.assertEqual(R.failure_fields(error),{'failure_boundary':None,'failure_code':None})

    def test_unknown_message_types_subclasses_and_extra_args_remain_null(self):
        class DerivedValueError(ValueError):pass
        for error in (ValueError('SECRET'*1000),RuntimeError('INCOMPLETE_PHASE_WINDOW'),
                      DerivedValueError('INCOMPLETE_PHASE_WINDOW'),ValueError('INCOMPLETE_PHASE_WINDOW','extra'),
                      ValueError(123),OSError('INCOMPLETE_PHASE_WINDOW'),KeyboardInterrupt('SECRET')):
            actual=R.failure_fields(error)
            self.assertEqual(actual,{'failure_boundary':None,'failure_code':None})
            self.assertNotIn('SECRET',json.dumps(actual))


class Entry(unittest.TestCase):
    def setUp(self):
        self.entry=R.module(ENTRY_SOURCE,ENTRY_PIN,'cold_owner_entry')

    def test_entry_pin_binds_frozen_caller_and_t0_is_early(self):
        self.assertEqual(self.entry.CALLER_PIN,PIN)
        tree=ast.parse(ENTRY_SOURCE.read_bytes())
        self.assertEqual(tree.body[1].names[0].name,'time')
        self.assertEqual(tree.body[2].targets[0].id,'STARTED')

    def test_entry_size_hash_and_symlink_fail_before_compile(self):
        raw=b'VALUE = 73\n'
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path=Path(folder)/'caller.py'
            for changed in (raw[:-1],raw+b'\n',b'VALUE = 74\n'):
                path.write_bytes(changed)
                with mock.patch.object(builtins,'compile',side_effect=AssertionError('compiled drift')) as compiler:
                    with self.assertRaises(ValueError):self.entry.checked(path,pin(raw))
                    compiler.assert_not_called()
            path.write_bytes(raw);alias=Path(folder)/'alias.py';alias.symlink_to(path)
            with self.assertRaisesRegex(ValueError,'ENTRY_CANONICAL'):self.entry.checked(alias,pin(raw))

    def test_entry_same_verified_buffer_and_original_t0_forwarded_to_stub_only(self):
        raw=SOURCE.read_bytes()
        stub=builtins.compile('def main(argv, *, started, source_pin):\n    raise StopIteration((argv, started, source_pin))\n',
                              'pure_mock_entry_sink','exec')
        args=['--private-config','/fixed/mock']
        with mock.patch.object(self.entry.time,'monotonic',return_value=100.0), \
             mock.patch.object(builtins,'compile',return_value=stub) as compiler:
            with self.assertRaises(StopIteration) as caught:self.entry.main(args,started=99.0)
        compiler.assert_called_once_with(raw,str(SOURCE),'exec',dont_inherit=True)
        self.assertEqual(caught.exception.args[0],(args,99.0,PIN))

    def test_entry_rejects_missing_isolation_flags_before_source(self):
        for missing in ('isolated','no_site','dont_write_bytecode'):
            flags={key:True for key in ('isolated','no_site','dont_write_bytecode')};flags[missing]=False
            with mock.patch.object(self.entry.sys,'flags',types.SimpleNamespace(**flags)), \
                 mock.patch.object(self.entry,'checked') as checked:
                with self.assertRaisesRegex(ValueError,'ENTRY_ISOLATION'):self.entry.main([],started=100.0)
                checked.assert_not_called()

    def test_entry_rejects_nonfloat_stale_or_future_t0_before_source(self):
        for started in (100,70.0,100.001,-1.0,True):
            with mock.patch.object(self.entry.time,'monotonic',return_value=100.0), \
                 mock.patch.object(self.entry,'checked') as checked:
                with self.assertRaisesRegex(ValueError,'ENTRY_T0'):self.entry.main([],started=started)
                checked.assert_not_called()


if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
        raise RuntimeError('COLD_ISOLATION_REQUIRED')
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    summary={'schema':1,'mode':'FUNCTION_LEVEL_PURE_MOCK_NO_RUN_MAIN_NATIVE_RTL_NETWORK',
             'test_mode':ARGS.mode,'python_optimize':sys.flags.optimize,
             'source_bytes':PIN[0],'source_sha256':PIN[1],'tests_run':result.testsRun,
             'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
             'supervisor_original_pin':{'bytes':SUPERVISOR_PIN[0],'sha256':SUPERVISOR_PIN[1]},
             'entry_pin':{'bytes':ENTRY_PIN[0],'sha256':ENTRY_PIN[1]},
             'process_limits':{'as_bytes':512*1024**2,'cpu_seconds':30,'file_bytes':16*1024**2,
                               'cpu_affinity_count':len(os.sched_getaffinity(0))},
             'status':'PASS' if result.wasSuccessful() else 'FAIL'}
    (HERE/('RESULT_'+ARGS.mode+'.json')).write_text(json.dumps(summary,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
