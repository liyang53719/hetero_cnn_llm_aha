"""Actual controller call graph with entirely mocked native stages, NOT a DUT test."""
import hashlib,json,pathlib,subprocess,sys,tempfile,time,types,unittest
from unittest.mock import patch
import flow
P=pathlib.Path;W=P(__file__).resolve().parent.parent
class T(unittest.TestCase):
 def test_order_and_identity_handoff(self):
  with tempfile.TemporaryDirectory()as td:
   base=P(td);repo=base/'repo';repo.mkdir();job=base/'job';runtime=W/'runtime';numeric=W/'numeric';sup=REPO/'candidates/ci_frontend_pipeline_r2_20261029'
   pins={str(p):flow.sha(p)for d in(runtime,numeric)for p in d.rglob('*')if p.is_file()and p.suffix in('.py','.json')and'__pycache__'not in p.parts}
   for name in('supervise_multiroot.py','strict_cleanup.py','lossless_log.py'):pins[str(sup/name)]=flow.sha(sup/name)
   for p in (P(flow.__file__).resolve(),P(flow.__file__).resolve().parent/'bootstrap_samejob.py',P(sys.executable).resolve()):pins[str(p)]=flow.sha(p)
   calls=[];sizes={};old_stat=P.stat
   def fake_stat(p,*args,**kwargs):
    st=old_stat(p,*args,**kwargs)
    if str(p)in sizes:
     row=list(st);row[6]=sizes[str(p)];return type(st)(row)
    return st
   def execute(argv,out,*args,**kwargs):
    name=P(out).name;calls.append(name);P(out).mkdir()
    if name=='archives':
     dest=job/'runs/archives/output';dest.mkdir();(dest/'ARCHIVES.json').write_text(json.dumps({'archives':[]}))
    elif name=='weights':
     dest=job/'runs/weights/output';dest.mkdir();(dest/'SUMMARY.json').write_text(json.dumps({'tensors':70,'tensor_bytes':3531306272}))
     for i in range(70):
      d=dest/'model';d.mkdir(exist_ok=True);f=d/f'tensor{i}.bin';f.write_bytes(b'x');n=1 if i<69 else 3531306272-69;sizes[str(f)]=n
      (d/f'tensor{i}.receipt.json').write_text(json.dumps({'actual_bytes':n,'actual_sha256':hashlib.sha256(b'x').hexdigest()}))
    result=dict(native_exit=0,errors=[],cleanup_proof={'status':'COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'},log_capture={'pipe_eof_observed':True,'gzip_finalized':True});(P(out)/'RESULT.json').write_text(json.dumps(result));return result
   def install(b,*args):
    calls.append('install_owner');root=P(b['owner_root']);root.mkdir();p=root/'owner.json';p.write_text('{}');return None,None,p
   def references(b,stage):calls.append('five_references');return {str(i):{'MOCK_ONLY':i}for i in range(5)}
   def build(argv,**kwargs):
    calls.append('one_original_backend');self.assertIn('--shared-owned-root',argv);self.assertIn('--remaining-tail-reserve-seconds',argv)
    d=job/'build/frontend';d.mkdir(parents=True);(d/'BUILD_ONLY_RESULT.json').write_text('{}');return types.SimpleNamespace(returncode=0)
   def tail(b,*args):
    calls.append('five_consumers');self.assertEqual(b['profiles'],list(range(5)));self.assertEqual(len(b['weights']),70);self.assertEqual(b['references'],{str(i):{'MOCK_ONLY':i}for i in range(5)})
    d=P(b['output']);d.mkdir();(d/'RESULT.json').write_text(json.dumps({'scope':'MOCK_ONLY_NO_DUT'}))
   def module(name,path):return {'actual_fresh_installer':types.SimpleNamespace(run=install),'actual_original_references':types.SimpleNamespace(run=references),'actual_five_diagnostics':types.SimpleNamespace(run=tail)}[name]
   identity=dict(run_id=1,source_commit='a'*40,launch_commit='b'*40)
   b=dict(schema='ONE_JOB_FIVE_M128_CHISEL_TEST_CALIBRATION_V1',job_started_monotonic=time.monotonic(),profiles=list(range(5)),tokens=128,matrix_macs=4096,vector_lanes=32,payload_uploads=False,final_rtl_replay=False,identity=identity,artifact_identity=identity,repo=str(repo),job_root=str(job),pins=pins,runtime_package=str(runtime),numeric_package=str(numeric),python=sys.executable,supervisor_dir=str(sup),shared_runtime_helper='MOCK',pipeline='MOCK',materialization_dir='MOCK',materializer='MOCK',dut_rss_bytes=3<<30,numeric_reserved_increment_bytes=1<<20,budgets=dict(archives=600,weights=2400,install=120,owner_bind=120,reference=120,provider=120,build=7200,parent=600,calibration_seconds={str(i):300 for i in range(5)}))
   binding=base/'B.json';binding.write_text(json.dumps(b));h=flow.sha(binding)
   env={'GITHUB_RUN_ID':'1','GITHUB_SHA':'b'*40,'GITHUB_RUN_ATTEMPT':'1','ImageVersion':'20261026.354.1'}
   with patch.dict('os.environ',env),patch.dict(sys.modules,{'supervise_multiroot':types.SimpleNamespace(execute=execute)}),patch.object(flow,'mod',side_effect=module),patch.object(subprocess,'check_output',return_value='a'*40+'\n'),patch.object(subprocess,'run',side_effect=build),patch('shutil.disk_usage',return_value=types.SimpleNamespace(free=100<<30)),patch.object(P,'stat',fake_stat):flow.run(b,binding,h)
   self.assertEqual(calls,['one_original_backend','archives','weights','install_owner','five_references','five_consumers'])
   self.assertEqual(json.loads((job/'FLOW_RESULT.json').read_text())['status'],'INCOMPLETE_DIAGNOSTIC_ONLY')
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--repo',type=P,required=True);args,remaining=parser.parse_known_args();REPO=args.repo.resolve();unittest.main(argv=[sys.argv[0],*remaining])
