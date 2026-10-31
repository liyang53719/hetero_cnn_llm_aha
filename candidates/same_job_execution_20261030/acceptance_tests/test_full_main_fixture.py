"""Full-size P1 main -> outer join fixture. ALL PROCESS/BUILD EVIDENCE IS MOCKED.
No DUT executes and no numerical PASS is claimed by this test. The production
expected/reference/compare/predicate/readers are deliberately left unpatched.
"""
import importlib.machinery
import contextlib, hashlib, io, json, os, pathlib, sys, tempfile, types, unittest
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
CANDIDATE=HERE.parent
sys.path.insert(0,str(CANDIDATE/'numeric'))
import consumer_owned as c
import dut_evidence as d
import required_acceptance as a

def pin(p):
 return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

def dump(p,v):p.write_text(json.dumps(v));return p

class FullMainFixture(unittest.TestCase):
 def exercise(self,mode,full_execution=False):
  with tempfile.TemporaryDirectory(prefix='synthetic_p1_main_fixture_') as tmp:
   root=pathlib.Path(tmp);refroot=root/'reference';refroot.mkdir();(refroot/'reference_only').mkdir()
   tensor_specs={
    'output_storage':([1,128,1024],'torch.bfloat16',b'\x80\x3f',128*1024),
    'final_cache.conv_states.0':([1,6144,4],'torch.bfloat16',b'\x00\x3f',6144*4),
    'final_cache.recurrent_states.0':([1,16,128,128],'torch.float32',b'\x00\x00\x00\x3f',16*128*128)}
   rec={};payloads={}
   for key,(shape,dtype,word,count) in tensor_specs.items():
    data=word*count;file=refroot/'reference_only'/(key+'.bin');file.write_bytes(data);rp=pin(file)
    rec[key]=dict(shape=shape,dtype=dtype,file=str(file.relative_to(refroot)),bytes=rp['bytes'],sha256=rp['sha256']);payloads[key]=data
   ref=dump(refroot/'RESULT.json',dict(profile=dict(profile=1),complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,tensor_records=rec))
   views=root/'views.tsv';views.write_text('HOST_COMPILED_INPUT_V2\n')
   runtime=root/'runtime.tsv';specs=[('output',262144,5),('history_out',49152,5),('state_out',1048576,4)]
   runtime.write_text('\n'.join(['HOST_COMPILED_INPUT_V2','launch\t0\t1','views\t'+str(views)]+['\t'.join(map(str,('observe',idx,name,4096+idx*2097152,size,dtype))) for idx,(name,size,dtype) in enumerate(specs)])+'\n')
   common={}
   for key in ('binary','sv','source_manifest','driver'):
    path=root/(key+'.fixture');path.write_bytes(('SYNTHETIC MOCK '+key).encode());common[key]=pin(path)
   receipt=dump(root/'build_receipt.json',dict(config_only=False,software_arithmetic_substitution=False,**{key+'_sha256':common[key]['sha256'] for key in common}))
   common['build_receipt']=pin(receipt)
   provider=dump(root/'provider.json',dict(scope='SYNTHETIC MOCK PROVIDER'))
   profile=dict(id=1,runtime=pin(runtime),views=pin(views),reference_result=pin(ref),provider_receipt=pin(provider))
   bundle=dump(root/'bundle.json',dict(scope='SYNTHETIC MOCK BUNDLE'))
   artifact=dump(root/'artifact.json',dict(scope='SYNTHETIC MOCK BUILD'))
   limits=dict(file_bytes=64*1024**2,max_active_cycles=1000,wall_seconds=100,cpu_seconds=100,address_space_bytes=1024**3)
   b=dict(layer=a.LAYER,matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common=common,profiles=[profile],limits=limits,coverage_policy={})
   args=types.SimpleNamespace(owned_environment=provider,owned_environment_sha256=pin(provider)['sha256'],expected_run_id=1,expected_launch_commit='1'*40,expected_source_commit='2'*40,strict_outer_supervised=True,artifact_manifest=artifact,artifact_manifest_sha256=pin(artifact)['sha256'],runtime_bundle=bundle,profile=1,calibration_wall_seconds=1,validate_only=False,output=root/'output',local_build_result_sha256='3'*64)
   full_budget=None
   if full_execution:
    budget_doc=dict(schema='FIVE_M128_FULL_EXECUTION_BUDGET_V1',ready=True,scope='WATCHDOG_ADMISSION_ONLY_NOT_NUMERICAL_ACCEPTANCE',tokens=128,matrix_macs=4096,vector_lanes=32,hardware_baseline_sha256=pin(CANDIDATE.parent/'ci_frontend_materialization_r2_20261029/OBSERVER_BASELINE_ACCEPTANCE.json')['sha256'],driver_sha256=pin(CANDIDATE.parent/'moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp')['sha256'],basis=dict(calibration_summary=pin(provider),independent_budget_review=pin(provider)),profiles={str(i):dict(wall_seconds=1,max_active_cycles=1000,estimated_complete_active_cycles=900,estimated_required_wall_seconds=1)for i in range(5)})
    full_budget=dump(root/'SYNTHETIC_FULL_BUDGET.json',budget_doc)
    args.execution_mode='FULL_BLOCK_ACCEPTANCE';args.full_block_budget=full_budget;args.full_block_budget_sha256=pin(full_budget)['sha256'];args.calibration_wall_seconds=None
   pid=os.getpid();tick=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
   def mock_execute(binary,runfile,target,log,execution_limits):
    # This is an explicitly mocked process receipt, not evidence of Popen.
    dump(log.with_suffix('.started.json'),dict(schema='ACTUAL_DUT_POPEN_V1',pid=pid+100000,consumer_pid=pid,consumer_start_tick=tick,inherited_group=pid,inherited_session=pid,binary_sha256=c.sha(binary),runtime_sha256=c.sha(runfile)))
    if mode=='timeout':raise TimeoutError('SYNTHETIC fixture timeout')
    target.mkdir();lines=['COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=1 cycles=100']
    keys=('output_storage','final_cache.conv_states.0','final_cache.recurrent_states.0')
    for idx,((name,size,dtype),key) in enumerate(zip(specs,keys)):
     if mode=='missing_state' and name=='state_out':continue
     data=payloads[key];self.assertEqual(len(data),size)
     (target/(name+'.actual.bin')).write_bytes(data);(target/(name+'.final.bin')).write_bytes(data)
     lines.append(f'HOST_FINAL_OUTPUT name={name} address={4096+idx*2097152} bytes={size} dtype={dtype} coverage=ACKNOWLEDGED_EVERY_BYTE')
    log.write_text('\n'.join(lines)+'\n');return 0
   mocked=dict(load_binding=lambda *unused:(b,{'artifact_identity':dict(scope='SYNTHETIC MOCK BUILD')}),verify_local_build=lambda *unused:{'scope':'SYNTHETIC MOCK BUILD'},verify_runtime_abi=lambda *unused:{'scope':'SYNTHETIC MOCK ABI'},execute=mock_execute)
   with contextlib.ExitStack() as stack:
    if full_execution:
     original_load=importlib.machinery.SourceFileLoader.exec_module
     def approve_synthetic_budget(loader,module):
      original_load(loader,module)
      if pathlib.Path(module.__file__).resolve()==(CANDIDATE/'execution_mode.py').resolve():module.ACCEPTED_FULL_ADMISSION_SHA256=pin(full_budget)['sha256']
     stack.enter_context(patch.object(importlib.machinery.SourceFileLoader,'exec_module',approve_synthetic_budget))
    for name,value in mocked.items():stack.enter_context(patch.object(c,name,value))
    stack.enter_context(patch.object(c.os,'getpgrp',return_value=pid));stack.enter_context(patch.object(c.os,'getsid',return_value=pid))
    stack.enter_context(patch.object(c.argparse.ArgumentParser,'parse_args',return_value=args))
    with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as stopped:c.main()
   self.assertEqual(stopped.exception.code,2)
   result=json.loads((args.output/'RESULT.json').read_text());row=result['profiles'][0]
   self.assertFalse(result['numerical_pass']);self.assertFalse(row['numerical_pass'])
   if full_execution:self.assertEqual(result['execution_admission']['execution_mode'],'FULL_BLOCK_ACCEPTANCE');self.assertEqual(result['execution_admission']['effective_limits']['wall_seconds'],1)
   leader=dict(pid=pid,start=tick,group=pid)
   outer=dump(root/'MOCK_OUTER.json',dict(worker_started=True,native_exit=2,errors=[],owner_identity=leader,cleanup_proof=dict(status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',owner_identity=leader,session=pid),log_capture=dict(pipe_eof_observed=True,gzip_finalized=True)))
   joined=d.verify(args.output,1,pin(artifact)['sha256'],pin(bundle)['sha256'],common['binary']['sha256'],pin(runtime)['sha256'],pin(outer))
   if mode=='complete':
    self.assertNotIn('error_class',row)
    self.assertEqual(row['qualification']['missing'],['verified_outer_cleanup_and_log_eof'])
    self.assertEqual({key:value['bytes'] for key,value in row['comparisons'].items()},{name:size for name,size,_ in specs})
    self.assertTrue(all(value['byte_mismatches']==0 for value in row['comparisons'].values()))
    self.assertEqual(joined['qualification']['status'],'PASS_FULL128_EXACT_REFERENCE')
    self.assertTrue(joined['numerical_pass'])
    self.assertFalse(a.aggregate([joined])['numerical_pass'])
   else:
    self.assertFalse(joined['numerical_pass']);self.assertEqual(joined['qualification']['status'],'INCOMPLETE')
    self.assertEqual(row['error_class'],'TimeoutError' if mode=='timeout' else 'ValueError')
   return result,joined
 def test_complete_full_size_main_then_outer_join(self):self.exercise('complete')
 def test_timeout_cannot_promote(self):self.exercise('timeout')
 def test_missing_full_state_cannot_promote(self):self.exercise('missing_state')
 def test_explicit_full_mode_complete(self):self.exercise('complete',True)
 def test_explicit_full_mode_timeout_not_completion(self):self.exercise('timeout',True)
 def test_explicit_full_mode_missing_state_not_completion(self):self.exercise('missing_state',True)
if __name__=='__main__':unittest.main()
