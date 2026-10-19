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
SIZE=24501
SHA='3895215ac36cacdc88745588f6bc90a8ab4f28985f864abe428cbf444e38f47a'
RAW=(HERE/'run.py').read_bytes()

def load(raw):
    if len(raw)!=SIZE or hashlib.sha256(raw).hexdigest()!=SHA:
        raise ValueError('source rejected before compile')
    g=types.ModuleType('verified_run_cold');g.__file__=str(HERE/'run.py')
    exec(compile(raw,g.__file__,'exec',dont_inherit=True),g.__dict__)
    return g
G=load(RAW)
PINS=G.decode(G.exact(HERE/'RUN_PINS.json',G.PINS_SIZE,G.PINS_SHA))['files']


def fixture(ready=False):
    stages=[]
    if ready:
        stages=[{'name':n,'status':'EXIT0_CLEANED','exit_code':0,'cleanup_confirmed':True,'seconds':0.1,
                 'child_user_cpu_seconds':0.05,'child_system_cpu_seconds':0.01} for n in G.STAGES]
    return {'summary.json':{'schema':'host93-ci-summary-v1','status':'READY_REQUIRES_ACTIONS_EXIT0' if ready else 'INCOMPLETE',
             'failure_category':'NONE' if ready else 'INPUT_OR_CONTRACT','completed_components':list(G.COMPONENTS) if ready else [],
             'scope':{x:ready and x not in ('n0_numeric','weights_loaded') for x in G.SCOPES},'seconds':1.0},
            'source_hashes.json':{'schema':'host93-ci-source-hashes-v1','project_sources':[{'path':n,**p} for n,p in sorted(PINS.items())] if ready else [],
              'fixed_inputs':{'idma_archive':{'bytes':9926876,'sha256':'a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce'}},'generated':({'derived_backend':{'bytes':1,'sha256':'1'*64},'host_elf':{'bytes':1,'sha256':'1'*64},'host93_fir':{'bytes':42417256,'sha256':'264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'},'host93_sv':{'bytes':76366612,'sha256':'2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61'}} if ready else {})},
            'stage_exits.json':{'schema':'host93-ci-stage-exits-v1','stages':stages}}


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

    def mock_whole_job(self, fail_name=None):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);repo=base/'repo';repo.mkdir();out=base/'out';archive=base/'idma.zip'
            fixed={'bytes':1,'sha256':'1'*64,'path':str(base/'observed')}
            def cfg(name):
                x=dict(zip(('total_seconds','work_seconds','cpu_seconds','as_bytes','fsize_bytes','log_bytes'),G.PHASE_CAPS[name]));x['sample_rows']=x['total_seconds']+2;return x
            def group(names,result):
                def run(repo,work,call,*args):
                    for name in names:call(name,['/fixed/fixture'],base,{},cfg(name))
                    return result
                return types.SimpleNamespace(run=run)
            tools=group(G.STAGES[:18],{'backend':fixed})
            emission=group(G.STAGES[18:26],{'fir':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_fir']},'sv':{'path':fixed['path'],**fixture(True)['source_hashes.json']['generated']['host93_sv']}})
            execution=group(G.STAGES[-3:],{'elf':fixed})
            modules={'verified_ci_toolchain':tools,'verified_ci_host_emission':emission,'verified_ci_host_execution':execution}
            def native(*args):
                name=args[2]
                if name==fail_name:raise TimeoutError('synthetic boundary')
                return {'exit_code':0,'cleanup_confirmed':True},b'private synthetic',{'child_user_cpu_seconds':0.1,'child_system_cpu_seconds':0.01}
            support=types.SimpleNamespace(deadline_ready=lambda:None,fixed_support=lambda repo:(None,None,None),run_phase=native)
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
                code=G.execute(repo,out,archive,G.time.monotonic()+1000.)
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
        self.assertIsNone(stages[-1]['exit_code'])

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


if __name__=='__main__':unittest.main(verbosity=2)
