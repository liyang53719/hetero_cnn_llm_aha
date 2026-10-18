"""Tiny synthetic byte and supervisor mocks only; no network, child, native execution or OS limits."""
import argparse,ast,contextlib,hashlib,io,json,os,signal,socket,stat,sys,tempfile,types,unittest,warnings,zipfile
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(add_help=False)
p.add_argument('--repo',type=Path,required=True);p.add_argument('--acquisition-source',type=Path,required=True)
a,extra=p.parse_known_args()
SOURCE_PINS = {'run_acquisition_gate.py': {'bytes': 14006, 'sha256': '09938994ab8537cefa8e4ae5a5a660cffaa07079c40b10b508af832236fc6383'}, 'acquire_firtool_member.py': {'bytes': 6038, 'sha256': 'c677bd0129be21cfc26e4e3adfd550861b9ee75f7066547874ca0fd44cf719b2'}}


def load(name):
    raw=(HERE/name).read_bytes();pin=SOURCE_PINS[name]
    if len(raw)!=pin['bytes'] or hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('fixed cold source')
    m=types.ModuleType(name);m.__file__=str(HERE/name)
    exec(compile(raw,m.__file__,'exec',dont_inherit=True),m.__dict__);return m


gate=load('run_acquisition_gate.py');member=load('acquire_firtool_member.py')
plan,frozen,projected,identities=gate.preflight(a.repo,a.acquisition_source)
runner=types.SimpleNamespace(**gate.supervisor(projected))
raw=(a.repo/'development_snapshots/canonical_runtime_ram_source_20261018/test_runner_cold.py').read_bytes()
if len(raw)!=18004 or hashlib.sha256(raw).hexdigest()!='fc88db7e72d64fca1603de193940e7b95e9030f90dc3eb0e574cec9d5b40ff46':raise ValueError('published mock changed')
classes=[n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='FakeOS']
if len(classes)!=1:raise ValueError('fixed FakeOS projection')
ns={'contextlib':contextlib,'types':types,'runner':runner,'signal':signal,'mock':mock}
exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),'published_FakeOS','exec',dont_inherit=True),ns)
FakeOS=ns['FakeOS'];DATA=b'tiny synthetic bytes; never execute'


def zbytes(entries=None):
    b=io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        with zipfile.ZipFile(b,'w') as z:
            for name,data,mode in entries or [(member.MEMBER,DATA,stat.S_IFREG|0o755)]:
                i=zipfile.ZipInfo(name);i.create_system=3;i.external_attr=mode<<16;z.writestr(i,data)
    return b.getvalue()


def synthetic_receipt():
    selected=json.loads(frozen['plans/firtool.json']);pin=selected['artifacts'][0]
    return {'status':'VERIFIED_OPAQUE_BYTES_ONLY','group':'firtool','artifacts':[{'relative_destination':pin['relative_destination'],
      'sha256':pin['sha256'],'origin_url':pin['url'],'transport':selected['transport'],'size_bytes':123}],
      'received_bytes':123,'extracted':False,'installed':False,'executed':False,'host_compilation_or_rtl_evidence':False}


class Cold(unittest.TestCase):
    def setUp(self):
        self.deny=mock.patch.object(socket,'socket',side_effect=AssertionError('network forbidden'));self.deny.start()
    def tearDown(self):self.deny.stop()
    def reject_zip(self,entries):
        raw=zbytes(entries)
        with self.assertRaises((ValueError,zipfile.BadZipFile)):member.member_bytes(raw,member.sha(raw),member.sha(DATA))
    def test_01_fixed_source_plan_and_shared180(self):
        self.assertEqual(set(frozen),{'acquire.py','plans/firtool.json','acquire_firtool_member.py'})
        self.assertEqual(plan['groups'],{'firtool':{'byte_cap':67108864,'cleanup_seconds':5,'cpu_seconds':170,'postflight_reserve_seconds':5,'total_wall_seconds':180,'work_deadline_offset_seconds':170}})
        self.assertEqual(tuple(identities),gate.FUNCTIONS)
        for token in ['env=None)','os.WNOWAIT','signal.setitimer(signal.ITIMER_REAL, 0)','os.sched_setaffinity(0, {min(allowed)})']:self.assertIn(token,projected.decode())
    def test_02_tiny_zip_same_buffer_success(self):
        raw=zbytes();self.assertEqual(member.member_bytes(raw,member.sha(raw),member.sha(DATA)),DATA)
    def test_03_archive_and_member_hash_mismatch(self):
        raw=zbytes()
        for ah,bh in [('0'*64,member.sha(DATA)),(member.sha(raw),'0'*64)]:
            with self.assertRaisesRegex(ValueError,'SHA'):member.member_bytes(raw,ah,bh)
    def test_04_duplicate_member(self):self.reject_zip([(member.MEMBER,DATA,0),(member.MEMBER,DATA,0)])
    def test_05_escape_names(self):
        for name in ['../escape','/escape','a/../escape','a//b','a/./b','C:/escape','a\\escape']:
            with self.subTest(name=name):self.reject_zip([(member.MEMBER,DATA,0),(name,b'x',0)])
    def test_06_symlink_and_special_entries(self):
        for mode in [stat.S_IFLNK|0o777,stat.S_IFIFO|0o600,stat.S_IFSOCK|0o600]:self.reject_zip([(member.MEMBER,DATA,mode)])
    def test_07_missing_member_or_directory(self):
        self.reject_zip([('wrong',DATA,0)]);self.reject_zip([(member.MEMBER,DATA,stat.S_IFDIR|0o755)])
    def test_08_bounded_member_and_archive_and_entries(self):
        raw=zbytes()
        with mock.patch.object(member,'MEMBER_CAP',len(DATA)-1):
            with self.assertRaisesRegex(ValueError,'size cap'):member.member_bytes(raw,member.sha(raw),member.sha(DATA))
        with mock.patch.object(member,'ARCHIVE_CAP',len(raw)):
            with self.assertRaisesRegex(ValueError,'archive byte cap'):member.member_bytes(raw,member.sha(raw),member.sha(DATA))
        with mock.patch.object(member,'ENTRY_CAP',0):
            with self.assertRaisesRegex(ValueError,'count cap'):member.member_bytes(raw,member.sha(raw),member.sha(DATA))
    def test_09_member_fixed_output0600_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            target=Path(t)/'firtool';member.write_member(target,DATA)
            self.assertEqual(target.read_bytes(),DATA);self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
            with self.assertRaises(ValueError):member.write_member(target,DATA)
    def test_10_symlink_input_and_output_refused(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'real').write_bytes(DATA);(root/'link').symlink_to(root/'real')
            with self.assertRaises(ValueError):member.regular_bytes(root/'link',100)
            with self.assertRaises(ValueError):member.write_member(root/'link',DATA)
    def test_11_same_raw_acquirer_loading(self):
        acq=member.load_acquirer(a.acquisition_source)
        self.assertEqual(acq.GROUP_HASHES['firtool'],member.PLAN_SHA)
        self.assertEqual(acq.load_plan('firtool')['artifacts'][0]['sha256'],member.ARCHIVE_SHA)
    def test_12_default_does_not_spawn_or_arm(self):
        argv=['gate','--repo',str(a.repo),'--acquisition-source',str(a.acquisition_source),'--group','firtool']
        with mock.patch.object(sys,'argv',argv),mock.patch.object(gate.subprocess,'Popen',side_effect=AssertionError('spawn')),mock.patch.object(gate.signal,'setitimer',side_effect=AssertionError('timer')),contextlib.redirect_stdout(io.StringIO()) as out:gate.main()
        self.assertFalse(json.loads(out.getvalue())['child_started'])
    def test_13_original_success_and_failures_kill_before_reap(self):
        for mode,error in [('pass',None),('timeout',runner.subprocess.TimeoutExpired),('interrupt',KeyboardInterrupt),('other_exception',RuntimeError),('reap_unknown',runner.subprocess.TimeoutExpired),('spawn_fail',OSError),('compiler_fail',ValueError)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                out=Path(t);fake=FakeOS(mode)
                with fake.patches(),mock.patch.object(runner.signal,'setitimer'):
                    if error:
                        with self.assertRaises(error):runner.bounded('acquire',['mock-python'],out,out,10,10)
                    else:runner.bounded('acquire',['mock-python'],out,out,10,10)
                r=json.loads((out/'acquire.json').read_text())
                self.assertEqual(r['status'],'FAIL' if error else 'PASS')
                if mode!='spawn_fail':self.assertEqual(fake.calls.count((424242,signal.SIGKILL)),1)
    def test_14_child_resource_limits_mock_only(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t);fake=FakeOS('pass');seen=[]
            def spawn(command,**kwargs):
                self.assertIsNone(kwargs['env'])
                with mock.patch.object(runner.resource,'setrlimit') as limits,mock.patch.object(runner.os,'sched_getaffinity',return_value={7,9}),mock.patch.object(runner.os,'sched_setaffinity') as affinity:
                    kwargs['preexec_fn']();seen.extend(limits.call_args_list);affinity.assert_called_once_with(0,{7})
                return fake.spawn(command,**kwargs)
            with fake.patches(),mock.patch.object(runner.subprocess,'Popen',side_effect=spawn),mock.patch.object(runner.signal,'setitimer'):runner.bounded('acquire',['mock'],out,out,170,170)
            for kind,value in [(runner.resource.RLIMIT_AS,536870912),(runner.resource.RLIMIT_FSIZE,67108864),(runner.resource.RLIMIT_CPU,170)]:self.assertIn(mock.call(kind,(value,value)),seen)
    def test_15_existing_or_blocked_alarm_refused(self):
        for blocked,timer in [({signal.SIGALRM},(0.,0.)),(set(),(4.,0.))]:
            with mock.patch.object(gate.signal,'pthread_sigmask',return_value=blocked),mock.patch.object(gate.signal,'getitimer',return_value=timer),mock.patch.object(gate.signal,'setitimer') as setter:
                with self.assertRaises(ValueError):gate.alarm_available()
                setter.assert_not_called()
    def test_16_receipt_wrong_identity_or_scope(self):
        receipt=synthetic_receipt();selected=json.loads(frozen['plans/firtool.json']);gate.receipt_matches(receipt,selected)
        for k in ['extracted','installed','executed','host_compilation_or_rtl_evidence']:
            with self.assertRaises(ValueError):gate.receipt_matches(dict(receipt,**{k:True}),selected)
    def outer(self,commit_mode=None,child_failure=False):
        now=[5.];seen=[]
        def fake_bounded(label,command,directory,output,wall,cpu):
            seen.append((wall,cpu,command));root=output/'artifacts';root.mkdir();(root/'ACQUISITION.json').write_text(json.dumps(synthetic_receipt()))
            if child_failure:now[0]=181.;raise TimeoutError('synthetic late cleanup')
            return {'cleanup_confirmed':True},b''
        def fake_save(path,value):
            runner.save(path,value)
            if commit_mode and path.name=='RESULT.json' and value['status']=='EVIDENCE_PENDING_OUTER_EXIT0':
                now[0]=181.
                if commit_mode=='interrupt':raise TimeoutError('synthetic late receipt interruption')
        with tempfile.TemporaryDirectory() as t,mock.patch.object(gate.signal,'pthread_sigmask',return_value=set()),mock.patch.object(gate.signal,'getitimer',return_value=(0.,0.)),mock.patch.object(gate.signal,'signal'),mock.patch.object(gate.signal,'setitimer') as timer,mock.patch.object(gate.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(gate,'supervisor',return_value={'bounded':fake_bounded,'save':fake_save}),mock.patch.object(gate,'member_receipt_matches',return_value={'scope':'MOCK_ONLY'}):
            out=Path(t)/'attempt'
            if commit_mode or child_failure:
                with self.assertRaises((ValueError,TimeoutError)):gate.execute('firtool',a.repo,a.acquisition_source,out,0)
                if commit_mode:
                    saved=json.loads((out/'RESULT.json').read_text());self.assertFalse(saved['terminal_success']);self.assertEqual(saved['status'],'EVIDENCE_PENDING_OUTER_EXIT0')
                else:self.assertFalse((out/'RESULT.json').exists())
            else:
                result=gate.execute('firtool',a.repo,a.acquisition_source,out,0)
                self.assertFalse(result['terminal_success']);self.assertFalse(result['binary_executed']);self.assertEqual(seen[0][:2],(165,170))
                self.assertEqual(timer.call_args_list,[mock.call(signal.ITIMER_REAL,165),mock.call(signal.ITIMER_REAL,175),mock.call(signal.ITIMER_REAL,0)])
                self.assertIn('acquire_firtool_member.py',seen[0][2][4])
    def test_17_outer_shared_deadline_and_command(self):self.outer()
    def test_18_late_cleanup_cannot_publish(self):self.outer(child_failure=True)
    def test_19_late_final_save_cannot_return_success(self):self.outer('late')
    def test_20_interrupt_after_commit_is_nonterminal(self):self.outer('interrupt')
    def test_21_member_failure_never_executes_binary(self):
        with tempfile.TemporaryDirectory() as t,mock.patch.object(member,'load_acquirer') as load:
            acq=load.return_value;root=Path(t)/'artifacts';root.mkdir();acq.checked_output_root.return_value=root;acq.acquire.return_value={'received_bytes':3};(root/member.ARCHIVE_NAME).write_bytes(b'bad')
            with self.assertRaises(ValueError):member.run(Path(t),Path(t),root)
            self.assertFalse((root/'firtool').exists());self.assertFalse((root/'MEMBER.json').exists())
    def test_23_member_postflight_actual_bytes_and_negative_cases(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);archive=b'opaque synthetic';(root/member.ARCHIVE_NAME).write_bytes(archive)
            receipt={'received_bytes':len(archive)};ar=json.dumps(receipt).encode();(root/'ACQUISITION.json').write_bytes(ar)
            member.write_member(root/'firtool',DATA)
            m={'status':'MEMBER_BYTES_PREPARED_PENDING_OUTER_EXIT0','terminal_success':False,'member_name':member.MEMBER,
              'extracted_member_count':1,'binary_relative_destination':'firtool','archive_relative_destination':member.ARCHIVE_NAME,
              'archive_sha256':member.sha(archive),'binary_sha256':member.sha(DATA),'archive_bytes':len(archive),'received_bytes':len(archive),
              'archive_receipt_sha256':member.sha(ar),'binary_bytes':len(DATA),'binary_mode_octal':'0600',
              'binary_executed':False,'installed':False,'rtl_generated':False,'host_executed':False}
            synthetic_plan={'member_policy':dict(plan['member_policy'],archive_sha256=member.sha(archive),binary_sha256=member.sha(DATA))}
            def save(): (root/'MEMBER.json').write_text(json.dumps(m))
            save();self.assertEqual(gate.member_receipt_matches(root,synthetic_plan,receipt),m)
            m['binary_executed']=True;save()
            with self.assertRaises(ValueError):gate.member_receipt_matches(root,synthetic_plan,receipt)
            m['binary_executed']=False;save();(root/'firtool').write_bytes(b'changed')
            with self.assertRaises(ValueError):gate.member_receipt_matches(root,synthetic_plan,receipt)
            (root/'firtool').write_bytes(DATA);(root/'unknown').write_bytes(b'')
            with self.assertRaises(ValueError):gate.member_receipt_matches(root,synthetic_plan,receipt)
    def test_24_complete_tiny_mock_pipeline(self):
        raw=zbytes();a_sha=member.sha(raw);b_sha=member.sha(DATA);original=member.member_bytes
        with tempfile.TemporaryDirectory() as t,mock.patch.object(member,'load_acquirer') as load,mock.patch.object(member,'ARCHIVE_SHA',a_sha),mock.patch.object(member,'BINARY_SHA',b_sha),mock.patch.object(member,'member_bytes',side_effect=lambda b:original(b,a_sha,b_sha)):
            root=Path(t)/'artifacts';acq=load.return_value;acq.checked_output_root.return_value=root
            def acquire(_plan,dest):
                dest.mkdir();(dest/member.ARCHIVE_NAME).write_bytes(raw)
                receipt={'received_bytes':len(raw)};(dest/'ACQUISITION.json').write_text(json.dumps(receipt));return receipt
            def save(dest,value):dest.write_text(json.dumps(value));return None
            acq.acquire.side_effect=acquire;acq.write_json.side_effect=save
            result=member.run(Path(t),Path(t),root)
            self.assertEqual((root/'firtool').read_bytes(),DATA);self.assertFalse(result['binary_executed']);self.assertFalse(result['terminal_success'])
            self.assertEqual({x.name for x in root.iterdir()},{member.ARCHIVE_NAME,'ACQUISITION.json','MEMBER.json','firtool'})

    def test_22_crc_corruption_refused(self):
        raw=bytearray(zbytes());pos=raw.index(DATA);raw[pos]^=1;raw=bytes(raw)
        with self.assertRaises(zipfile.BadZipFile):member.member_bytes(raw,member.sha(raw),member.sha(DATA))


if __name__=='__main__':
    if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('use -I -S -B')
    unittest.main(argv=[sys.argv[0]]+extra,verbosity=2)
