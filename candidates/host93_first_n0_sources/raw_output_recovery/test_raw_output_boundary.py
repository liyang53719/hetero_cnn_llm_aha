"""Real pinned acquisition entry through source/path admission; stop before network.

No payload, runtime import, native process, or GitHub operation. The successful
boundary case is not acquisition success: a test sentinel stops strict_opener.
"""
import argparse, contextlib, hashlib, io, os, stat, sys, tempfile, time, types, unittest
from pathlib import Path
from unittest import mock

STAGE='candidates/host93_ci_recovery/first_n0/stage_entry.py'
STAGE_PIN=(5627,'a3fad553a94bb07b210b32b947cbeaf15dc2fa6b4c314317d99132d6458bedd5')
RUN='candidates/host93_ci_recovery/run.py'
RUN_PIN=(77219,'853d7d53c2b85376b643a90ae1421d9d9766c5ad6d415e8e5ddf1570ab0aa79c')
PIPELINE='candidates/host93_ci_recovery/first_n0/pipeline.py'
PIPELINE_PIN=(28972,'ccb2a03c1fa3211de3e8467a020107c693a591c8b94ff6dba0653191bb9bbc7f')
WORKFLOW_PIN=(5347,'bee96f354ba9819ab748ec1cd8e0614484be88166f062433aef7146659e49e42')
BASE_WORKFLOW_PIN=(5179,'0878fdfa6c13891be297a5e942dcce5cfbac491e4b92488097e743be43a5a4c7')
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Tests require -I -S -B')
ap=argparse.ArgumentParser(allow_abbrev=False)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--workflow',type=Path,required=True)
ap.add_argument('--base-workflow',type=Path,required=True)
args,rest=ap.parse_known_args()
def checked(path,pin):
    if not path.is_absolute() or '..' in path.parts or any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('source path')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        a=os.fstat(f.fileno());raw=f.read(pin[0]+1);z=os.fstat(f.fileno())
    sig=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if not stat.S_ISREG(a.st_mode) or sig(a)!=sig(z) or sig(z)!=sig(path.stat(follow_symlinks=False)):raise ValueError('source identity')
    if (len(raw),hashlib.sha256(raw).hexdigest())!=pin:raise ValueError('source pin')
    return raw

def cold_audit(event,values):
    if event.startswith(('socket.','subprocess.','ctypes.dlopen')) or event in ('os.system','os.fork','os.posix_spawn','os.exec'):
        raise RuntimeError('cold network/process forbidden')
sys.addaudithook(cold_audit)
entry_raw=checked(args.repo/STAGE,STAGE_PIN)
E=types.ModuleType('_pinned_raw_entry');E.__file__=str(args.repo/STAGE);sys.modules[E.__name__]=E
exec(compile(entry_raw,E.__file__,'exec',dont_inherit=True),E.__dict__)
RUN_TEXT=checked(args.repo/RUN,RUN_PIN).decode()
PIPELINE_TEXT=checked(args.repo/PIPELINE,PIPELINE_PIN).decode()
WORKFLOW=checked(args.workflow,WORKFLOW_PIN).decode()
BASE_WORKFLOW=checked(args.base_workflow,BASE_WORKFLOW_PIN).decode()

class StopBeforeNetwork(Exception):pass
class Boundary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='n0-path-fixture-',dir='/tmp');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.opener_calls=0;self.collect_calls=0;self.source_calls=0;self.prepared=[]
        # This load is the production exact-byte loader; the two contract
        # functions below are wrappers around original functions, not mocks.
        original_load=E.module
        def loading(path,pin):
            m=original_load(path,pin)
            original_check=m.check_sources;original_prepare=m.prepare_output
            def source(*a,**kw):
                self.source_calls+=1
                return original_check(*a,**kw)
            def prepare(*a,**kw):
                result=original_prepare(*a,**kw);self.prepared.append(result);return result
            def opener(*a,**kw):
                self.opener_calls+=1
                raise StopBeforeNetwork('synthetic pre-network stop')
            def collect(*a,**kw):
                self.collect_calls+=1
                raise RuntimeError('collect must not be called')
            m.check_sources=source;m.prepare_output=prepare;m.strict_opener=opener;m.collect_fixed=collect
            return m
        p=mock.patch.object(E,'module',side_effect=loading);p.start();self.addCleanup(p.stop)
    def invoke(self,out):
        captured=io.StringIO()
        with contextlib.redirect_stdout(captured):
            code=E.main(['--stage','raw','--repo',str(args.repo),'--out',str(out),'--deadline',str(time.monotonic()+30),'--execute'])
        self.assertEqual(code,1);self.assertEqual(self.source_calls,1);self.assertEqual(self.collect_calls,0)
        return captured.getvalue().strip()
    def reject(self,out,code):
        self.assertEqual(self.invoke(out),'N0_ACQUISITION_FAILED:RAW_OUTPUT:'+code)
        self.assertEqual(self.opener_calls,0);self.assertEqual(self.prepared,[])
    def accept(self,out):
        self.assertEqual(self.invoke(out),'N0_ACQUISITION_FAILED:RAW_ACQUIRE:UNEXPECTED')
        self.assertEqual(self.opener_calls,1);self.assertEqual(self.prepared,[out])
        self.assertEqual(sorted(p.name for p in out.iterdir()),['segments','tensors'])
        self.assertEqual(list((out/'segments').iterdir()),[]);self.assertEqual(list((out/'tensors').iterdir()),[])
    def test_old_work_ancestor_rejected(self):
        parent=self.root/'work'/'runner-temp'/'host93-ci-private'/'n0_frontdoor';parent.mkdir(parents=True)
        self.reject(parent/'raw','RAW_RULE_014');self.assertFalse((parent/'raw').exists())
    def test_new_exact_workflow_shape_accepts_to_network_boundary(self):
        run_id=str(time.time_ns());root=Path('/tmp')/('host93-first-n0-'+run_id+'-1')
        root.mkdir(mode=0o700);self.addCleanup(lambda:__import__('shutil').rmtree(root))
        parent=root/'n0_frontdoor';parent.mkdir(mode=0o700)
        self.accept(parent/'raw')
    def test_work_leaf_rejected(self):self.reject(self.root/'work','RAW_RULE_014')
    def test_workspace_component_is_not_work(self):
        parent=self.root/'workspace';parent.mkdir();self.accept(parent/'raw')
    def test_work_suffix_component_is_not_work(self):
        parent=self.root/'work-root';parent.mkdir();self.accept(parent/'raw')
    def test_existing_output_still_rejected(self):
        out=self.root/'raw';out.mkdir();self.reject(out,'RAW_RULE_025')
    def test_missing_parent_still_rejected(self):self.reject(self.root/'absent'/'raw','RAW_RULE_025')
    def test_symlink_ancestor_still_rejected(self):
        target=self.root/'real';target.mkdir();link=self.root/'alias';link.symlink_to(target,target_is_directory=True)
        self.reject(link/'raw','RAW_RULE_041')
    def test_inside_repository_still_rejected_without_write(self):
        out=args.repo/('n0-path-test-'+str(time.time_ns()));self.reject(out,'RAW_RULE_026');self.assertFalse(out.exists())

class Workflow(unittest.TestCase):
    def test_exact_small_workflow_delta(self):
        transformed=BASE_WORKFLOW.replace('# TEMP_SOURCE: canonical M128 first N0 only; exact reference recovery and full-value tolerance comparison, no full-block claim.','# TEMP_SOURCE: fixed fresh /tmp output root satisfies unchanged raw acquisition path admission.')
        transformed=transformed.replace('    env:\n      PYTHONDONTWRITEBYTECODE:', '    env:\n      HOST93_PRIVATE_ROOT: /tmp/host93-first-n0-${{ github.run_id }}-${{ github.run_attempt }}\n      PYTHONDONTWRITEBYTECODE:',1)
        transformed=transformed.replace('          test "$GITHUB_RUN_ATTEMPT" = 1\n','          test "$GITHUB_RUN_ATTEMPT" = 1\n          [[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]]\n          test "$HOST93_PRIVATE_ROOT" = "/tmp/host93-first-n0-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"\n',1)
        transformed=transformed.replace('"$RUNNER_TEMP/host93-ci-private"','"$HOST93_PRIVATE_ROOT"').replace('${{ runner.temp }}/host93-ci-private/evidence/','${{ env.HOST93_PRIVATE_ROOT }}/evidence/')
        self.assertEqual(WORKFLOW,transformed)
        self.assertEqual(WORKFLOW.count('--out "$HOST93_PRIVATE_ROOT"'),2)
        self.assertEqual(WORKFLOW.count('${{ env.HOST93_PRIVATE_ROOT }}/evidence/'),3)
        self.assertNotIn('host93-ci-private',WORKFLOW)
    def test_existing_path_chain_and_freshness_unchanged(self):
        self.assertIn("pipeline.run_frontdoor(repo,out/'n0_frontdoor'",RUN_TEXT)
        self.assertIn("'--out',work/'raw'",PIPELINE_TEXT)
        self.assertIn('not os.path.lexists(out)',RUN_TEXT)
        self.assertIn("RAW_RULE_014",entry_raw.decode())

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
