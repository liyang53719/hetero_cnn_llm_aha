"""Synthetic tiny filesystem and mocked lifecycle tests. No native build/tool execution."""
import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Use python -I -S -B test_build_gate_cold.py.')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', required=True, help='Explicit repository containing the two fixed published support sources; cold-only.')
args = parser.parse_args()
REPO = Path(args.repo)
if not REPO.is_absolute() or '..' in REPO.parts:
    raise ValueError('--repo must be an explicit absolute path without parent traversal')
sys.argv = [sys.argv[0]]
HERE = Path(__file__).absolute().parent
SOURCE = HERE / 'run_build_gate.py'
RAW = SOURCE.read_bytes()
if len(RAW) != 28551 or hashlib.sha256(RAW).hexdigest() != '8f1560c5f0a8e78a991f98c30031cbd18df220e3eb82cf2c78de4ec0438bdafb':
    raise ValueError('cold runner raw identity mismatch before compile')
g = types.ModuleType('verified_build_cold')
g.__file__ = str(SOURCE)
g.__verified_runner_pin__ = {'path': str(SOURCE), 'bytes': len(RAW), 'sha256': hashlib.sha256(RAW).hexdigest()}
exec(compile(RAW, str(SOURCE), 'exec', dont_inherit=True), g.__dict__)
PRODUCTION_PLAN = g.load_plan()


def cold_plan_for_repo(production, repo):
    # Only cold inspection resolves public support sources. No production actual
    # identity, input root, evidence root or phase command is supplied here.
    repo = g.safe_path(str(repo))
    plan = copy.deepcopy(production)
    for key in ('supervisor','observation'):
        item = plan['published_sources'][key]
        g.relative_name(item['repo_relative'])
        item['path'] = str(repo / item['repo_relative'])
        g.fixed(item)  # Complete fixed raw size/SHA, before any AST projection.
    return plan


PLAN = cold_plan_for_repo(PRODUCTION_PLAN, REPO)


def synthetic_stage_binding():
    return {'manifest':{'path':'/synthetic/MANIFEST.json','bytes':1,'sha256':'0'*64},
            'summary':{'path':'/synthetic/SUMMARY.json','bytes':1,'sha256':'0'*64},
            'summary_claims':{'verdict':'PASS_SYNTHETIC_STAGE','original_outer_exit':0}}


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': g.sha(raw)}


def write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n')
    path.chmod(0o600)
    return pin(path)


def save(path, value):
    write(path, value)


class BuildCold(unittest.TestCase):
    def test_01_pending_each_phase_no_copy_spawn_output(self):
        pending=copy.deepcopy(PLAN);pending['required_actual']['versions']=None;pending['required_actual']['tiny']=None
        with mock.patch.object(g,'load_plan',return_value=pending), \
             mock.patch.object(g, 'materialize', side_effect=RuntimeError('no copying')) as cp, \
             mock.patch.object(g.subprocess, 'Popen', side_effect=RuntimeError('no native')) as spawn, \
             mock.patch.object(g, 'fresh_directory', side_effect=RuntimeError('no output')) as mkdir:
            for phase in g.PHASES:
                with self.assertRaisesRegex(ValueError, 'PENDING'):
                    g.execute(phase, g.time.monotonic())
            cp.assert_not_called()
            spawn.assert_not_called()
            mkdir.assert_not_called()

    def test_02_pinned_plan_exact_phase_budgets(self):
        for phase in g.PHASES:
            with self.assertRaisesRegex(ValueError,'stage actual PENDING'):g.validate_bindings(PRODUCTION_PLAN,phase)
        expected = [(180,160,170,160,1024**3,64*1024**2,256*1024,200),
                    (180,160,170,160,1024**3,64*1024**2,256*1024,200),
                    (3600,3570,3580,3570,4*1024**3,1024**3,1024**2,3700)]
        for phase, values in zip(g.PHASES, expected):
            c = PLAN['phases'][phase]
            self.assertEqual(tuple(c[k] for k in ('total_seconds','work_max_seconds','work_latest_offset_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes','sample_rows')), values)
            self.assertEqual(c['preflight_seconds'],10)
            self.assertEqual(c['cleanup_seconds'],5)
        self.assertEqual(PLAN['phases']['autoconf']['argv'][0], PLAN['build_root']+'/tools/usr/bin/autoconf')
        self.assertEqual(len(PLAN['source_members']),473)
        self.assertEqual(len(PLAN['dependency_members']),68)

    def test_03_no_assert_security_guards(self):
        self.assertFalse(any(isinstance(n, ast.Assert) for n in ast.walk(ast.parse(RAW))))
        self.assertNotIn(b'importlib',RAW)
        self.assertNotIn(b'shell=True',RAW)

    def test_04_raw_projection_hash_rejects_before_ast(self):
        p = PLAN['published_sources']['supervisor']
        raw = g.fixed(p)
        with mock.patch.object(g.ast,'parse',side_effect=RuntimeError('must not parse')) as parse:
            with self.assertRaises(ValueError):g.project_functions(raw+b'x',p,g.FUNCTIONS)
            parse.assert_not_called()

    def test_05_original_function_identity_and_unique_projection(self):
        p = PLAN['published_sources']['supervisor']
        raw = g.fixed(p)
        parts = g.project_functions(raw,p,g.FUNCTIONS)
        self.assertEqual(tuple(parts),g.FUNCTIONS)
        p2 = copy.deepcopy(p);p2['functions']['bounded']['sha256']='0'*64
        with self.assertRaises(ValueError):g.project_functions(raw,p2,g.FUNCTIONS)
        with self.assertRaises(ValueError):g.replacement(b'xx',[(b'x',b'y')])
        self.assertEqual(g.replacement(b'a0b',[(b'0',b'11')]),b'a11b')

    def test_06_same_five_lifecycle_and_four_observer_functions(self):
        for phase in g.PHASES:
            sup, obs = g.projected_sources(PLAN,phase)
            self.assertEqual(tuple(n.name for n in ast.parse(sup).body),g.FUNCTIONS)
            self.assertEqual(tuple(n.name for n in ast.parse(obs).body),g.OBSERVERS)
            self.assertIn(b'os.WNOWAIT',sup)
            self.assertIn(b'signal_sent_before_reap',sup)
            self.assertIn(b'env=BUILD_ENV',sup)
            self.assertIn(b'cleanup_budget_seconds=5',sup)
            self.assertIn(b'signal.setitimer(signal.ITIMER_REAL, 0)',sup)
            self.assertIn(b'stream.flush()',obs)
            self.assertIn(b"state['next']=now+1",obs)
            self.assertIn(b'len(raw)<=2048',obs)
            cap = PLAN['phases'][phase]['sample_rows']
            self.assertIn(("state['count']<"+str(cap)).encode(),obs)
            obs_pin = PLAN['published_sources']['observation']
            original = g.project_functions(g.fixed(obs_pin),obs_pin,g.OBSERVERS)
            lines=obs.splitlines(keepends=True)
            node=next(n for n in ast.parse(obs).body if n.name=='sample_leader')
            sample=b''.join(lines[node.lineno-1:node.end_lineno])
            self.assertEqual(sample.replace(("state['count']<"+str(cap)).encode(),b"state['count']<340",1),original['sample_leader'])

    def test_07_synthetic_copy_readback_modes_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);src=r/'original';src.write_bytes(b'tiny source');src.chmod(0o600)
            dest=r/'out';dest.mkdir(mode=0o700)
            p=pin(src)
            g.copy_member(src,dest,'usr/bin/tiny',p,0o700)
            self.assertEqual((dest/'usr/bin/tiny').read_bytes(),b'tiny source')
            self.assertEqual((dest/'usr/bin/tiny').stat().st_mode&0o777,0o700)
            self.assertEqual(src.stat().st_mode&0o777,0o600)
            with self.assertRaises(FileExistsError):g.copy_member(src,dest,'usr/bin/tiny',p,0o700)
            with self.assertRaises(ValueError):g.copy_member(src,dest,'../bad',p,0o600)

    def test_08_no_follow_source_and_destination_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);src=r/'src';src.write_bytes(b'x');alias=r/'link';alias.symlink_to(src)
            with self.assertRaises(OSError):g.checked_read(alias,1,g.sha(b'x'))
            out=r/'out';out.mkdir(mode=0o700);(out/'usr').symlink_to(r)
            with self.assertRaises(OSError):g.copy_member(src,out,'usr/tiny',pin(src),0o600)
            with self.assertRaises(ValueError):g.tree_inventory(out,1024)

    def test_09_synthetic_fixed_read_truncation_hash_and_growth(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'s';p.write_bytes(b'abc')
            self.assertEqual(g.checked_read(p,3,g.sha(b'abc')),b'abc')
            with self.assertRaises(ValueError):g.checked_read(p,2,g.sha(b'ab'))
            with self.assertRaises(ValueError):g.checked_read(p,3,'0'*64)
            with mock.patch.object(g.os,'read',side_effect=[b'abcd']):
                with self.assertRaises(ValueError):g.checked_read(p,3,g.sha(b'abc'))

    def test_10_synthetic_inventory_caps_and_fifo(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'x').write_bytes(b'abc');(r/'x').chmod(0o600)
            inv=g.tree_inventory(r,3)
            self.assertEqual(inv['bytes'],3);self.assertEqual(inv['files'],1)
            with self.assertRaises(ValueError):g.tree_inventory(r,2)
            with self.assertRaises(ValueError):g.tree_inventory(r,3,file_cap=0)
            with self.assertRaises(ValueError):g.tree_inventory(r,3,entry_cap=0)
            os.mkfifo(r/'f')
            with self.assertRaises(ValueError):g.tree_inventory(r,100)

    def test_11_git_blob_hash_tiny(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x';p.write_bytes(b'abc')
            self.assertEqual(g.identity(p,3,git=True)['git_blob'],hashlib.sha1(b'blob 3\0abc').hexdigest())

    def test_12_review_manifest_and_exact_claims(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);s=write(r/'SUMMARY.json',{'outer_exit':0,'verdict':'PASS_TINY'})
            m=write(r/'MANIFEST.json',{'files':[{'path':'SUMMARY.json','bytes':s['bytes'],'sha256':s['sha256']}]})
            b={'manifest':m,'summary':s,'summary_claims':{'outer_exit':0,'verdict':'PASS_TINY'}}
            g.review_shape(b,'tiny');g.verify_review(b)
            b['summary_claims']['verdict']='PASS_DIFFERENT'
            with self.assertRaises(ValueError):g.verify_review(b)
            b['summary_claims']['outer_exit']=False
            with self.assertRaises(ValueError):g.review_shape(b,'tiny')

    def sample_fixture(self, phase, times, cap_reject=False, identity_change=False):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);ns=g.make_runner(PLAN,phase,out)
            now=[0.0];start=[123];state={}
            def proc(pid,leaf):
                if leaf=='stat':
                    fields=['0']*22;fields[0]='R';fields[11]=str(int(now[0]));fields[19]=str(start[0]);fields[21]='4'
                    return (str(pid)+' (synthetic leader) '+' '.join(fields)).encode()
                return b'VmRSS: 16 kB\nVmHWM: 32 kB\n'
            ns['proc_bytes']=proc
            with mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g.os,'sysconf',return_value=100):
                for value in times:
                    now[0]=float(value);ns['sample_leader'](types.SimpleNamespace(pid=999))
                rows=[json.loads(x) for x in (out/'leader_samples.jsonl').read_bytes().splitlines()]
                if cap_reject:
                    now[0]+=1
                    with self.assertRaisesRegex(ValueError,'row cap'):ns['sample_leader'](types.SimpleNamespace(pid=999))
                if identity_change:
                    now[0]+=1;start[0]+=1
                    with self.assertRaisesRegex(ValueError,'starttime changed'):ns['sample_leader'](types.SimpleNamespace(pid=999))
            return rows

    def test_13_make_sampling_full3600_window(self):
        rows=self.sample_fixture('optimized_backend',range(3601))
        self.assertEqual(len(rows),3601);self.assertEqual(rows[-1]['elapsed_from_first_sample_seconds'],3600)
        self.assertTrue(all(r['scope'].endswith('excludes descendant processes') for r in rows))

    def test_14_sample_caps200_and3700_are_hard(self):
        self.assertEqual(len(self.sample_fixture('autoconf',range(200),cap_reject=True)),200)
        self.assertEqual(len(self.sample_fixture('optimized_backend',range(3700),cap_reject=True)),3700)

    def test_15_sampler_no_catchup_or_identity_reset(self):
        rows=self.sample_fixture('configure',[0,.2,.999,1,20,20.5,21],identity_change=True)
        self.assertEqual([r['elapsed_from_first_sample_seconds'] for r in rows],[0,1,20,21])

    def test_16_sample_pid_parser_and_memory_unit(self):
        ns=g.make_runner(PLAN,'autoconf',Path('/never_written'))
        with self.assertRaises(ValueError):ns['proc_stat'](b'999 (x) R',999)
        fields=['0']*22;fields[0]='R';fields[19]='1'
        raw=('998 (x) '+' '.join(fields)).encode()
        with self.assertRaises(ValueError):ns['proc_stat'](raw,999)

    def test_17_mock_original_lifecycle_anchored_kill_before_reap(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);ns=g.make_runner(PLAN,'autoconf',out);events=[]
            child=types.SimpleNamespace(pid=999,returncode=None)
            def wait(timeout):events.append('reap');child.returncode=0
            child.wait=wait
            ns['sample_leader']=lambda ch:events.append('sample')
            ns['group_state']=lambda pid:'absent' if child.returncode is not None else 'present'
            event=types.SimpleNamespace(si_pid=999,si_code=1,si_status=0)
            with mock.patch.object(g.subprocess,'Popen',return_value=child),mock.patch.object(g.os,'waitid',return_value=event),mock.patch.object(g.os,'killpg',side_effect=lambda *a:events.append('kill')),mock.patch.object(g.signal,'setitimer'):
                rec,_=ns['bounded']('native',['synthetic'],out,out,1,160)
            self.assertLess(events.index('kill'),events.index('reap'));self.assertTrue(rec['cleanup_confirmed'])
            self.assertEqual(rec['exit_observed_while_unreaped']['pid'],999)

    def test_18_mock_echild_never_signals_unanchored_pid(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);ns=g.make_runner(PLAN,'autoconf',out)
            child=types.SimpleNamespace(pid=999,returncode=None,wait=mock.Mock())
            ns['group_state']=lambda pid:'absent'
            with mock.patch.object(g.subprocess,'Popen',return_value=child),mock.patch.object(g.os,'waitid',side_effect=ChildProcessError('synthetic ECHILD')),mock.patch.object(g.os,'killpg') as kill,mock.patch.object(g.signal,'setitimer'):
                with self.assertRaises(ChildProcessError):ns['bounded']('native',['synthetic'],out,out,1,160)
            kill.assert_not_called();child.wait.assert_not_called()
            self.assertFalse(json.loads((out/'native.json').read_bytes())['anchor_confirmed'])

    def mock_phase(self, phase, mode='ok'):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);out=root/'evidence';build=root/'build';src=build/'verilator'
            p=copy.deepcopy(PLAN);p['build_root']=str(build);cfg=p['phases'][phase];cfg['evidence_root']=str(out);cfg['cwd']=str(src)
            p['source_qualification']={'manifest':{'sha256':'0'*64}}  # Local mocked INPUTS metadata only.
            cfg['required_outputs']=['verilator/generated'];now=[0.0];calls=[]
            def materialize(_):
                build.mkdir(mode=0o700);src.mkdir(mode=0o700)
            if phase!='autoconf':materialize(p)
            before={'user_cpu_seconds':0,'system_cpu_seconds':0,'maxrss_kib':0}
            after={'user_cpu_seconds':1,'system_cpu_seconds':.1,'maxrss_kib':512}
            def bounded(label,argv,cwd,evidence,wall,cpu):
                calls.append((wall,cpu));save(out/'native.json',{'cleanup_confirmed':mode!='cleanup_fail','exit_code':0});(out/'native.log').write_bytes(b'mocked native log\n');(out/'leader_samples.jsonl').write_bytes(b'{"scope":"synthetic"}\n')
                (src/'generated').write_bytes(b'synthetic generated bytes')
                if mode=='timeout':raise TimeoutError('mock work timeout')
                if mode=='cleanup_fail':raise ValueError('mock cleanup failed')
                if mode=='large_log':(out/'native.log').write_bytes(b'x'*(cfg['log_bytes']+1))
                if mode=='late':now[0]=cfg['total_seconds']+1
                return {'cleanup_confirmed':True,'exit_code':0},b''
            runner={'usage':mock.Mock(side_effect=[before,after]),'save':save,'bounded':bounded,'projection_hashes':{'supervisor':'mock','observation':'mock'}}
            with mock.patch.object(g,'load_plan',return_value=p),mock.patch.object(g,'validate_bindings'),mock.patch.object(g,'verify_own_sources'),mock.patch.object(g,'verify_reviews'),mock.patch.object(g,'verify_reviews_stable'),mock.patch.object(g,'verify_payload'),mock.patch.object(g,'pristine_config'),mock.patch.object(g,'materialize',side_effect=materialize),mock.patch.object(g,'make_runner',return_value=runner),mock.patch.object(g.time,'monotonic',side_effect=lambda:now[0]),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.signal,'signal'),mock.patch.object(g.subprocess,'Popen',side_effect=RuntimeError('no native spawn')):
                if mode=='ok':
                    result=g.execute(phase,0)
                    self.assertFalse(result['terminal_success']);self.assertFalse(result['backend_executed']);self.assertTrue((out/'BUILD_TREE.json').exists())
                else:
                    with self.assertRaises((ValueError,TimeoutError)):g.execute(phase,0)
                    self.assertFalse((out/'RESULT.json').exists())
                    if mode!='late':
                        usage=json.loads((out/'CHILD_USAGE.json').read_bytes());self.assertEqual(usage['after'],after)
                        self.assertTrue((out/'FAILURE.json').exists())
                        if mode in ('timeout','cleanup_fail'):self.assertIsNotNone(usage['failure_type'])
                self.assertEqual(calls,[(cfg['work_max_seconds'],cfg['cpu_seconds'])])

    def test_19_mock_autoconf_phase_output_and_usage(self):self.mock_phase('autoconf')
    def test_20_mock_configure_phase_same_tree(self):self.mock_phase('configure')
    def test_21_mock_make_phase_exact_budget(self):self.mock_phase('optimized_backend')
    def test_22_mock_timeout_retains_aftercleanup_usage(self):self.mock_phase('autoconf','timeout')
    def test_23_mock_cleanup_failure_retains_usage(self):self.mock_phase('configure','cleanup_fail')
    def test_24_mock_log_overflow_not_success(self):self.mock_phase('optimized_backend','large_log')
    def test_25_late_work_cannot_be_success(self):self.mock_phase('configure','late')

    def test_26_previous_pending_rejected(self):
        p=copy.deepcopy(PLAN)
        p['previous_actual']={'autoconf':None,'configure':None}
        fake={'manifest':{'path':'/x','bytes':1,'sha256':'0'*64},'summary':{'path':'/y','bytes':1,'sha256':'0'*64},'summary_claims':{'verdict':'PASS_TEST','outer_exit':0}}
        p['required_actual']={k:copy.deepcopy(fake) for k in ('stage','versions','tiny')}
        p['required_actual']['stage']['summary_claims']={'verdict':'PASS_TEST','original_outer_exit':0}
        p['stage_report']={'path':p['dependency_stage_root']+'/STAGING_REPORT.json','bytes':1,'sha256':'0'*64}
        for phase in ('configure','optimized_backend'):
            with self.assertRaisesRegex(ValueError,'previous generated actual identity PENDING'):g.validate_bindings(p,phase)
        g.validate_bindings(p,'autoconf')

    def test_27_inherited_alarm_refused(self):
        with mock.patch.object(g.signal,'getitimer',return_value=(1.0,0.0)),mock.patch.object(g,'load_plan') as load:
            with self.assertRaises(ValueError):g.execute('autoconf',0)
            load.assert_not_called()

    def test_28_new_config_and_ccache_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'home').mkdir(mode=0o700);(root/'verilator').mkdir(mode=0o700);(root/'bin').mkdir(mode=0o700)
            p=copy.deepcopy(PLAN);p['build_root']=str(root);p['environment']['PATH']=str(root/'bin')
            g.pristine_config(p,'configure');(root/'bin/ccache').write_bytes(b'no execution')
            with self.assertRaises(ValueError):g.pristine_config(p,'configure')
            (root/'home/.autom4te.cfg').write_bytes(b'x')
            with self.assertRaises(ValueError):g.pristine_config(p,'autoconf')


    def test_29_mock_child_limits_environment_and_affinity(self):
        for phase in g.PHASES:
            with tempfile.TemporaryDirectory() as td:
                out=Path(td);ns=g.make_runner(PLAN,phase,out);child=types.SimpleNamespace(pid=999,returncode=None)
                child.wait=lambda timeout:setattr(child,'returncode',0)
                ns['sample_leader']=lambda ch:None
                ns['group_state']=lambda pid:'absent' if child.returncode is not None else 'present'
                event=types.SimpleNamespace(si_pid=999,si_code=1,si_status=0)
                def popen(argv,**kw):
                    self.assertEqual(kw['env'],PLAN['environment'])
                    self.assertTrue(kw['start_new_session'])
                    self.assertNotIn('shell',kw)
                    kw['preexec_fn']()
                    return child
                with mock.patch.object(g.subprocess,'Popen',side_effect=popen),mock.patch.object(g.os,'waitid',return_value=event),mock.patch.object(g.os,'killpg'),mock.patch.object(g.signal,'setitimer'),mock.patch.object(g.resource,'setrlimit') as lim,mock.patch.object(g.os,'sched_getaffinity',return_value={4,7}),mock.patch.object(g.os,'sched_setaffinity') as affinity:
                    ns['bounded']('native',['mock'],out,out,1,PLAN['phases'][phase]['cpu_seconds'])
                cfg=PLAN['phases'][phase]
                self.assertEqual(lim.call_args_list,[mock.call(g.resource.RLIMIT_AS,(cfg['as_bytes'],cfg['as_bytes'])),mock.call(g.resource.RLIMIT_CPU,(cfg['cpu_seconds'],cfg['cpu_seconds'])),mock.call(g.resource.RLIMIT_FSIZE,(cfg['fsize_bytes'],cfg['fsize_bytes'])),mock.call(g.resource.RLIMIT_CORE,(0,0))])
                affinity.assert_called_once_with(0,{4})

    def test_30_previous_generated_tree_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);build=r/'build';build.mkdir(mode=0o700);(build/'configure').write_bytes(b'generated shell source');(build/'configure').chmod(0o600)
            inv=g.tree_inventory(build,1024)
            ip=write(r/'BUILD_TREE.json',inv)
            rp=write(r/'RESULT.json',{'phase':'autoconf','status':'BUILD_PHASE_EVIDENCE_PENDING_PARENT_ACCEPTANCE','terminal_success':False,'cleanup_confirmed':True,'build_tree_inventory_sha256':ip['sha256']})
            sr=write(r/'STAGING_REPORT.json',{'pending':True})
            p=copy.deepcopy(PLAN);p['build_root']=str(build);p['stage_report']=sr
            p['previous_actual']['autoconf']={'review':{'synthetic':True},'inventory':ip,'result':rp}
            def review(binding):
                return {'selected_count':473,'selected_bytes':11747893,'original_acquisition_fail_preserved':True,'build_tree_inventory_sha256':ip['sha256']}
            with mock.patch.object(g,'verify_review',side_effect=review):
                g.verify_reviews(p,'configure')
                (build/'configure').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'generated tree drift'):g.verify_reviews(p,'configure')

    def test_31_missing_five_version_or_tiny_binding_stops(self):
        fake={'manifest':{'path':'/x','bytes':1,'sha256':'0'*64},'summary':{'path':'/y','bytes':1,'sha256':'0'*64},'summary_claims':{'verdict':'PASS_TEST','outer_exit':0}}
        for missing in ('versions','tiny'):
            p=copy.deepcopy(PLAN);p['required_actual']={k:copy.deepcopy(fake) for k in ('stage','versions','tiny')};p['required_actual'][missing]=None
            p['required_actual']['stage']['summary_claims']={'verdict':'PASS_TEST','original_outer_exit':0}
            with self.assertRaisesRegex(ValueError,missing+' actual PENDING'):g.validate_bindings(p,'autoconf')

    def test_32_source_loader_verifies_before_project_execution(self):
        text=(HERE/'load_build_gate.py').read_text()
        self.assertLess(text.index('hashlib.sha256(raw).hexdigest() != expected'),text.index('exec(compile(raw'))
        self.assertIn('sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode',text)
        self.assertNotIn('import run_build_gate',text)


    def test_33_stage_original_outer_exit_zero_exact_claim(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);claims={'original_outer_exit':0,'verdict':'PASS_ACTUAL_FIXED67_STAGED_DATA_ONLY'}
            s=write(r/'SUMMARY.json',claims)
            m=write(r/'MANIFEST.json',{'files':{'SUMMARY.json':{'bytes':s['bytes'],'sha256':s['sha256']}}})
            b={'manifest':m,'summary':s,'summary_claims':claims}
            g.review_shape(b,'stage')
            result=g.verify_review(b)
            self.assertEqual(result,claims);self.assertNotIn('outer_exit',result)
            with self.assertRaises(ValueError):g.review_shape(b,'tiny')

    def test_34_stage_nonzero_original_outer_exit_rejected(self):
        b=synthetic_stage_binding()
        b['summary_claims']['original_outer_exit']=1
        with self.assertRaisesRegex(ValueError,'terminal actual acceptance claims'):g.review_shape(b,'stage')

    def test_35_stage_missing_original_field_rejects_outer_exit_alias(self):
        b=synthetic_stage_binding()
        del b['summary_claims']['original_outer_exit']
        b['summary_claims']['outer_exit']=0
        with self.assertRaisesRegex(ValueError,'terminal actual acceptance claims'):g.review_shape(b,'stage')


    def test_36_cold_relocation_keeps_production_unbound(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)/'relocated';repo.mkdir(mode=0o700)
            for key in ('supervisor','observation'):
                item=PLAN['published_sources'][key];target=repo/item['repo_relative']
                target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                target.write_bytes(g.fixed(item));target.chmod(0o600)
            relocated=cold_plan_for_repo(PRODUCTION_PLAN,repo)
            for phase in g.PHASES:
                self.assertEqual(g.projected_sources(relocated,phase),g.projected_sources(PLAN,phase))
            restored=copy.deepcopy(relocated);restored['published_sources']=copy.deepcopy(PRODUCTION_PLAN['published_sources'])
            self.assertEqual(restored,PRODUCTION_PLAN)
            self.assertEqual(g.load_plan(),PRODUCTION_PLAN)
            self.assertEqual(PRODUCTION_PLAN['required_actual'],{'stage':None,'versions':None,'tiny':None})
            self.assertNotIn(b'--repo',RAW)

    def test_37_relocated_support_tamper_rejects_before_ast(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)/'relocated';repo.mkdir(mode=0o700)
            for key in ('supervisor','observation'):
                item=PLAN['published_sources'][key];target=repo/item['repo_relative']
                target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                target.write_bytes(g.fixed(item));target.chmod(0o600)
            target=repo/PLAN['published_sources']['supervisor']['repo_relative']
            raw=target.read_bytes();target.write_bytes(bytes([raw[0]^1])+raw[1:])
            with mock.patch.object(g.ast,'parse',side_effect=RuntimeError('must not parse')) as parse:
                with self.assertRaisesRegex(ValueError,'fixed input SHA'):cold_plan_for_repo(PRODUCTION_PLAN,repo)
                parse.assert_not_called()

    def real_loader_refusal(self, execute):
        source=HERE/'load_build_gate.py';raw=source.read_bytes()
        if len(raw)!=2059 or hashlib.sha256(raw).hexdigest()!='5d5bfeae1ef084d09898e66685fc99621c7fa717cd90d75f4f991cb4bc38ddc6':
            raise ValueError('cold real loader identity mismatch before same-buffer compile')
        original_open=os.open;writes=[]
        def guarded_open(path,flags,*a,**kw):
            if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
                writes.append(str(path));raise RuntimeError('no filesystem write')
            return original_open(path,flags,*a,**kw)
        for phase in g.PHASES:
            argv=[str(source),'--phase',phase]+(['--execute-reviewed'] if execute else [])
            with mock.patch.object(sys,'argv',argv),mock.patch.object(os,'open',side_effect=guarded_open),mock.patch.object(os,'mkdir',side_effect=RuntimeError('no mkdir')) as mkdir,mock.patch.object(g.subprocess,'Popen',side_effect=RuntimeError('no native')) as spawn:
                if execute:
                    with self.assertRaisesRegex(ValueError,'stage actual PENDING'):
                        exec(compile(raw,str(source),'exec',dont_inherit=True),{'__name__':'__main__','__file__':str(source)})
                else:
                    with self.assertRaises(FileNotFoundError):
                        exec(compile(raw,str(source),'exec',dont_inherit=True),{'__name__':'__main__','__file__':str(source)})
                mkdir.assert_not_called();spawn.assert_not_called()
        self.assertEqual(writes,[])

    def test_38_real_loader_actual_entry_pending_before_side_effects(self):
        self.real_loader_refusal(True)

    def test_39_real_loader_default_inspection_unavailable_without_binding(self):
        self.real_loader_refusal(False)


if __name__=='__main__':
    unittest.main(verbosity=2)
