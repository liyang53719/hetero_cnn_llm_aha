"""Tiny and mocked SV gate tests only. Never execute firtool, Java or another child."""
import argparse,ast,contextlib,copy,hashlib,io,json,os,signal,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--repo',type=Path,required=True);args,remaining=parser.parse_known_args()
raw=(HERE/'run_sv_gate.py').read_bytes()
if len(raw)!=18507 or hashlib.sha256(raw).hexdigest()!='0c6bfa402588dcdad6c492a8fa2f295f2f63670f305a738e92e621ee7cbfe3f1':raise ValueError('gate source drift')
g=types.ModuleType('fixed_sv_gate');g.__file__=str(HERE/'run_sv_gate.py');exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
plan=g.load_plan();cal=g.load_gate(args.repo);base=cal.configuration(args.repo)[4];projected=g.native_projection(base)


def pinned(path):
    raw=path.read_bytes();return {'bytes':len(raw),'sha256':g.digest(raw)}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True)+'\n');return pinned(path)


class SVCold(unittest.TestCase):
    def test_01_pending_actual_rejected_before_output(self):
        pending=copy.deepcopy(plan);pending['firtool']['actual_review_state']='PENDING'
        with tempfile.TemporaryDirectory() as t,mock.patch.object(g,'load_plan',return_value=pending),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.signal,'signal'),mock.patch.object(cal.subprocess,'Popen',side_effect=AssertionError('no spawn')):
            output=Path(t)/'never_created'
            a=types.SimpleNamespace(repo=args.repo,output=output)
            with self.assertRaisesRegex(ValueError,'PENDING'):g.execute(a,g.time.monotonic())
            self.assertFalse(output.exists())

    def test_02_closed_binding_requires_every_actual_pin(self):
        p=copy.deepcopy(plan);tool=p['firtool'];tool.update(actual_review_state='CLOSED_FIXED_FIRTOOL_MEMBER_ONLY',bytes=1,attempt_path='/new',review_path='/new_review',review_summary_claims={'verdict':'PASS_TEST_ONLY','outer_exit':0,'binary_executed':False})
        for pin in list(tool['attempt_files'].values())+list(tool['review_files'].values()):pin.update(bytes=1,sha256='0'*64)
        g.validate_binding(p)
        for field in ('bytes','attempt_path','review_path'):
            q=copy.deepcopy(p);q['firtool'][field]='PENDING'
            with self.assertRaises(ValueError):g.validate_binding(q)
        q=copy.deepcopy(p);q['firtool']['review_files']['MANIFEST.json']['sha256']='PENDING'
        with self.assertRaises(ValueError):g.validate_binding(q)

    def test_03_same_five_functions_lifecycle_projection(self):
        self.assertEqual(g.digest(base),g.PROJECTION_SHA)
        old=b'(48 * 1024 * 1024, 48 * 1024 * 1024)';new=b'(128 * 1024 * 1024, 128 * 1024 * 1024)'
        self.assertEqual(projected.replace(new,old,1),base)
        self.assertEqual([n.name for n in ast.parse(projected).body],list(cal.FUNCTIONS))
        self.assertIn(b'os.WNOWAIT',projected);self.assertIn(b'signal.setitimer(signal.ITIMER_REAL, 0)',projected)
        self.assertIn(b'cleanup_budget_seconds=5',projected);self.assertIn(b'sample_leader(child)',projected)
        ns=g.native_supervisor(cal,projected,Path('/never_used'));self.assertEqual(ns['AS_LIMIT'],2147483648)

    def test_04_exact_single_sv_argv(self):
        argv=g.command(Path('/fresh/tool/firtool'),Path('/fresh/inputs/HostBlockCollection.fir'),Path('/fresh/rtl'))
        self.assertEqual(argv,['/fresh/tool/firtool','-format=fir','/fresh/inputs/HostBlockCollection.fir','-o','/fresh/rtl/HostBlockCollection.sv','-warn-on-unprocessed-annotations','-output-annotation-file','/fresh/rtl/circt.anno.json','--preserve-values=all','-disable-all-randomization','--verbose-pass-executions'])

    def test_05_source_preflight_reads_no_actual_or_spawns(self):
        with mock.patch.object(sys,'argv',['gate','--repo',str(args.repo)]),mock.patch.object(cal.subprocess,'Popen',side_effect=AssertionError('no spawn')),mock.patch.object(g,'fixed',wraps=g.fixed) as reads,contextlib.redirect_stdout(io.StringIO()) as out:
            g.main();result=json.loads(out.getvalue());self.assertEqual(result['status'],'SV_SOURCE_PREFLIGHT_ONLY');self.assertFalse(result['firtool_started'])
            self.assertTrue(all('run_class_gate.py' in str(c.args[0]) for c in reads.call_args_list))

    def test_06_blocked_or_inherited_alarm_refuses_before_plan(self):
        for blocked,timer in (({signal.SIGALRM},(0.,0.)),(set(),(1.,0.))):
            with mock.patch.object(g.signal,'pthread_sigmask',return_value=blocked),mock.patch.object(g.signal,'getitimer',return_value=timer),mock.patch.object(g,'load_plan') as load:
                with self.assertRaises(ValueError):g.execute(types.SimpleNamespace(),0)
                load.assert_not_called()

    def test_07_fixed_same_buffer_and_streaming_copy(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'src';p.write_bytes(b'fixture');self.assertEqual(g.fixed(p,7,g.digest(b'fixture')),b'fixture')
            cal.verified_file(p,g.digest(b'fixture'),7,p.parent/'copy',7);self.assertEqual(g.file_identity(p),g.file_identity(p.parent/'copy'))
            with self.assertRaises(ValueError):g.fixed(p,7,'0'*64)

    def test_08_finite_inventory_unknown_directory(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'x').write_bytes(b'x');g.inventory(root,{'x'});(root/'extra').mkdir()
            with self.assertRaises(ValueError):g.inventory(root,{'x'})

    def test_09_finite_inventory_symlink_and_special_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'x').write_bytes(b'x');(root/'link').symlink_to('x')
            with self.assertRaises(ValueError):g.inventory(root,{'x','link'})
            (root/'link').unlink();os.mkfifo(root/'fifo')
            with self.assertRaises(ValueError):g.inventory(root,{'x','fifo'})

    def test_10_finite_inventory_file_count(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);names={str(i) for i in range(33)}
            for name in names:(root/name).write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'file cap'):g.inventory(root,names)

    def full_mock(self,mode='ok'):
        # Real tiny file copy/hash/inventory and receipt closure; only process/timer/
        # usage observations and production-size plan binding are mocked.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);origin=root/'origin';origin.mkdir();fir=origin/'HostBlockCollection.fir';fir.write_bytes(b'tiny same FIR fixture')
            attempt=root/'acquisition';binary=attempt/'artifacts/firtool';binary.parent.mkdir(parents=True);binary.write_bytes(b'tiny non-executed binary fixture');binary.chmod(0o600)
            review=root/'tool_review';structure=root/'structure_review';output=root/'attempt'
            p=copy.deepcopy(plan);p['fir']={'origin_path':str(fir),**pinned(fir)};p['structure_review']['path']=str(structure)
            tool=p['firtool'];tool.update(actual_review_state='CLOSED_FIXED_FIRTOOL_MEMBER_ONLY',attempt_path=str(attempt),review_path=str(review),**pinned(binary))
            acq_pin=write(attempt/'artifacts/ACQUISITION.json',{'status':'VERIFIED_OPAQUE_BYTES_ONLY'})
            member={'status':'MEMBER_BYTES_PREPARED_PENDING_OUTER_EXIT0','terminal_success':False,'member_name':tool['member_name'],'extracted_member_count':1,'binary_relative_destination':'firtool','binary_sha256':tool['sha256'],'binary_bytes':tool['bytes'],'binary_mode_octal':'0600','archive_sha256':tool['archive_sha256'],'archive_receipt_sha256':acq_pin['sha256'],'binary_executed':False,'installed':False}
            tool['attempt_files']={'artifacts/ACQUISITION.json':acq_pin,'artifacts/MEMBER.json':write(attempt/'artifacts/MEMBER.json',member),'RESULT.json':write(attempt/'RESULT.json',{'member':member,'terminal_success':False,'child_cleanup_confirmed':True,'binary_executed':False,'installed':False})}
            tool['review_summary_claims']={'verdict':'PASS_TINY_MOCK_ONLY','outer_exit':0,'binary_executed':False}
            summary_pin=write(review/'SUMMARY.json',tool['review_summary_claims']);tool['review_files']={'SUMMARY.json':summary_pin,'MANIFEST.json':write(review/'MANIFEST.json',{'files':{'SUMMARY.json':summary_pin}})}
            s={'verdict':'PASS_ACTUAL_SAME_FIR_CHIRRTL_STATIC_STRUCTURE_ONLY','accepted_by_combining_saved_outer0_time_and_independent_review':True,'outer_exit':0,'runtime_or_functional_qualification':False,'structure':{'host_port_count':83,'metadata_direct_request_response_routes':8}}
            summary_pin=write(structure/'SUMMARY.json',s);p['structure_review']['files']={'SUMMARY.json':summary_pin,'MANIFEST.json':write(structure/'MANIFEST.json',{'files':{'SUMMARY.json':summary_pin}}),'FIR_CURRENT_IDENTITY.json':write(structure/'FIR_CURRENT_IDENTITY.json',{'identity':pinned(fir)})}
            now=[0.0];seen=[];before={'user_cpu_seconds':0,'system_cpu_seconds':0,'maxrss_kib':0};after={'user_cpu_seconds':1,'system_cpu_seconds':.1,'maxrss_kib':1234}
            def save(path,value):
                write(path,value)
                if path.name=='RESULT.json' and mode in ('late_commit','interrupt_commit'):
                    now[0]=181
                    if mode=='interrupt_commit':raise TimeoutError('after final evidence save')
            def bounded(label,argv,cwd,out,wall,cpu):
                seen.append((label,wall,cpu));self.assertEqual(Path(argv[0]),out/'tool/firtool');self.assertEqual(Path(argv[2]),out/'inputs/HostBlockCollection.fir')
                self.assertEqual(binary.stat().st_mode&0o7777,0o600);self.assertEqual(Path(argv[0]).stat().st_mode&0o7777,0o700)
                record={'cleanup_confirmed':True,'timed_out':mode=='timeout'};save(out/'firtool.json',record);(out/'leader_samples.jsonl').write_bytes(b'{}\n')
                log=b'x'*(2*1024*1024+1) if mode=='large_log' else b'tiny mock log\n';(out/'firtool.log').write_bytes(log)
                if mode=='timeout':raise TimeoutError('SV firtool_work150s deadline')
                if mode!='missing_sv':(out/'rtl/HostBlockCollection.sv').write_bytes(b'module mock; endmodule\n')
                if mode!='no_annotation':(out/'rtl/circt.anno.json').write_bytes(b'[]\n')
                if mode=='extra':(out/'rtl/unknown.tmp').write_bytes(b'x')
                if mode=='extra_root':(out/'unknown').write_bytes(b'x')
                if mode=='source_drift':fir.write_bytes(b'changed original FIR')
                if mode=='binary_mode_drift':binary.chmod(0o700)
                return record,log
            a=types.SimpleNamespace(repo=args.repo,fir=fir,firtool_attempt=attempt,firtool_review=review,structure_review=structure,output=output)
            with mock.patch.object(g,'load_plan',return_value=p),mock.patch.object(g,'validate_binding'),mock.patch.object(g,'load_gate',return_value=cal),mock.patch.object(cal,'usage',side_effect=[before,after]),mock.patch.object(g,'native_supervisor',return_value={'save':save,'bounded':bounded}),mock.patch.object(g.signal,'pthread_sigmask',return_value=set()),mock.patch.object(g.signal,'getitimer',return_value=(0.0,0.0)),mock.patch.object(g.signal,'signal'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(cal.subprocess,'Popen',side_effect=AssertionError('no native spawn')):
                if mode in ('ok','no_annotation'):
                    result=g.execute(a,0);self.assertEqual(seen,[('firtool',150,150)]);self.assertFalse(result['terminal_success']);self.assertFalse(result['host_executed']);self.assertFalse(result['numerical_qualification'])
                    self.assertEqual(result['status'],'SV_EVIDENCE_PENDING_OUTER_EXIT0');self.assertTrue(result['sv_static_structure_qualification'].startswith('INCOMPLETE'))
                    inv=json.loads((output/'OUTPUT_INVENTORY.json').read_bytes());self.assertEqual(len(inv),9 if mode=='ok' else 8);self.assertEqual(result['final_exact_path_count'],len(inv)+2)
                    self.assertEqual(result['sv'],pinned(output/'rtl/HostBlockCollection.sv'));self.assertEqual(result['output_inventory_sha256'],pinned(output/'OUTPUT_INVENTORY.json')['sha256'])
                    self.assertEqual(result['annotation'] is None,mode=='no_annotation')
                else:
                    with self.assertRaises((TimeoutError,ValueError)):g.execute(a,0)
                    if mode in ('late_commit','interrupt_commit'):
                        result=json.loads((output/'RESULT.json').read_bytes());self.assertFalse(result['terminal_success']);self.assertEqual(result['status'],'SV_EVIDENCE_PENDING_OUTER_EXIT0')
                    else:self.assertFalse((output/'RESULT.json').exists());self.assertTrue((output/'FAILURE.json').exists())
                    usage=json.loads((output/'CHILD_USAGE.json').read_bytes());self.assertEqual(usage['after']['maxrss_kib'],1234)
                    if mode=='timeout':self.assertEqual(usage['failure_type'],'TimeoutError')
                    elif mode!='missing_sv':self.assertTrue((output/'rtl/HostBlockCollection.sv').exists())

    def test_11_mock_complete_inventory_no_structure_pass(self):self.full_mock()
    def test_12_mock_optional_annotation_absent(self):self.full_mock('no_annotation')
    def test_13_mock_timeout_retains_rusage(self):self.full_mock('timeout')
    def test_14_mock_unknown_rtl_retains_artifacts(self):self.full_mock('extra')
    def test_15_mock_unknown_root_retains_artifacts(self):self.full_mock('extra_root')
    def test_16_mock_missing_sv_refuses(self):self.full_mock('missing_sv')
    def test_17_mock_original_fir_drift_refuses(self):self.full_mock('source_drift')
    def test_18_mock_original_binary_mode_change_refuses(self):self.full_mock('binary_mode_drift')
    def test_19_mock_postflight_log_soft_cap(self):self.full_mock('large_log')
    def test_20_late_final_commit_non_success(self):self.full_mock('late_commit')
    def test_21_interrupted_final_commit_non_success(self):self.full_mock('interrupt_commit')

    def test_22_exact_budget_and_flags_no_heavy_checker(self):
        self.assertEqual(plan['budgets'],{'entry_total_seconds':180,'work_max_seconds':150,'preflight_seconds':10,'work_latest_offset_seconds':160,'cleanup_seconds':5,'postflight_deadline_offset_seconds':180,'cpu_count':1,'address_space_bytes':2147483648,'per_file_hard_cap_bytes':134217728,'tree_acceptance_soft_cap_bytes':268435456,'log_acceptance_soft_cap_bytes':2097152,'annotation_acceptance_soft_cap_bytes':33554432,'inventory_file_count_cap':32,'inventory_entry_count_cap':64})
        self.assertNotIn(b'importlib',raw);self.assertNotIn(b'owned_compile',raw);self.assertNotIn(b'load_checker',raw)
        self.assertEqual(plan['output_shape']['maximum_annotation_files'],1)

    def test_23_nonzero_inherited_child_usage_rejected_before_output(self):
        # The precise check is kept in the same orchestration location as CHIRRTL.
        self.assertIn(b"before['user_cpu_seconds']==0 and before['system_cpu_seconds']==0 and before['maxrss_kib']==0",raw)
        self.assertLess(raw.index(b'before=g.usage()'),raw.index(b'output.mkdir(mode=0o700)'))

if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use python -I -S -B')
    unittest.main(argv=[sys.argv[0]]+remaining,verbosity=2)
