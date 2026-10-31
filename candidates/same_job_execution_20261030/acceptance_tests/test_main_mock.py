"""Mock process execution only: actual main wiring, NOT DUT/reference evidence."""
import contextlib, io, json, pathlib, struct, sys, tempfile, types, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'numeric'))
import consumer_owned as c
import moe_score_compare as m
class MainTests(unittest.TestCase):
 def test_actual_main_raw_path_stays_exit2(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);refdir=root/'ref';refdir.mkdir();(refdir/'reference_only').mkdir()
   data=struct.pack('<I',0x3b800000)*32768;raw=refdir/'reference_only/probs.bin';raw.write_bytes(data)
   rr=dict(profile={'profile':3},status='CAPTURED_FRESH_OFFICIAL_FULL_BLOCK_REFERENCE_ONLY',complete_block_tokens=128,exact_baseline_observer_output_equal=True,hardware_executed=False,numerical_comparison_with_hardware=False,router_policy='UNMODIFIED_OFFICIAL_TORCH_TOPK',raw_router_score_observation='ORIGINAL_FORWARD_LOCAL_RETURN_READONLY_PROFILE',no_reference_outputs_or_router_ids_allowed_in_hardware_stimulus=True,tensor_records={m.KEY:dict(shape=[128,256],dtype='torch.float32',bytes=len(data),file='reference_only/probs.bin',sha256=m.digest(data))})
   ref=refdir/'RESULT.json';ref.write_text(json.dumps(rr));views=root/'views';views.write_text('HEADER\n');runtime=root/'runtime';runtime.write_text('runtime')
   receipt=root/'receipt';receipt.write_text(json.dumps(dict(config_only=False,software_arithmetic_substitution=False,**{k+'_sha256':'0'*64 for k in ('binary','sv','source_manifest','driver')})))
   pins={k:dict(path=str(receipt),bytes=receipt.stat().st_size,sha256='0'*64) for k in ('binary','sv','source_manifest','driver','build_receipt')}
   profile=dict(id=3,runtime={'path':str(runtime)},views={'path':str(views)},reference_result={'path':str(ref)},provider_receipt={'path':str(receipt)})
   limits=dict(file_bytes=64*1024**2,max_active_cycles=1,wall_seconds=100,cpu_seconds=100,address_space_bytes=1024**3)
   b=dict(layer='CHISEL_EMITTED_SV_NUMERICAL_BACKEND',matrix_macs=4096,vector_lanes=32,moe_reference_contract='ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE',common=pins,profiles=[profile],limits=limits,coverage_policy={})
   args=types.SimpleNamespace(owned_environment=receipt,owned_environment_sha256='0'*64,expected_run_id=1,expected_launch_commit='1'*40,expected_source_commit='2'*40,strict_outer_supervised=True,artifact_manifest=receipt,artifact_manifest_sha256='0'*64,runtime_bundle=receipt,profile=3,calibration_wall_seconds=1,validate_only=False,output=root/'output',local_build_result_sha256='0'*64)
   ids=b''.join(struct.pack('<q',i%8) for i in range(1024));weights=bytes(2048);logits=bytes(65536)
   route=b''.join(struct.pack('<Q',(i//8)<<34|(i%8)<<31|(i%8)<<23|i//8) for i in range(1024))
   def execute(binary,runtime,target,log,limits):
    target.mkdir();(target/'output.actual.bin').write_bytes(bytes(4));(target/'output.final.bin').write_bytes(bytes(4))
    (target/'router_token_map.final.bin').write_bytes(route);(target/'router_logits_bf16.final.bin').write_bytes(logits);(target/'router_selection_scores.fp32.actual.bin').write_bytes(data)
    (target/'router_selected_scores.fp32.actual.bin').write_bytes(struct.pack('<I',0x3b800000)*1024);(target/'router_selected_ids.u32.actual.bin').write_bytes(b''.join(struct.pack('<I',i%8) for i in range(1024)))
    log.write_text('HOST_ROUTER_SELECTED_SCORE_V2 profile=3 transaction=0 owner=9 values=1024 score_bytes=4096 id_bytes=4096 dtype=FP32 index_dtype=UINT32 source=SELECTION_OUTPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\nCOMPLETE_ORIGINAL_HOST_DDR_REPLAY profile=3 cycles=1\nHOST_FINAL_OUTPUT name=output address=64 bytes=4 dtype=5 coverage=ACKNOWLEDGED_EVERY_BYTE\nHOST_FINAL_ROUTE_MAP bytes=8192 coverage=ACKNOWLEDGED_EVERY_BYTE\nHOST_FINAL_ROUTER_LOGITS bytes=65536 dtype=BF16 coverage=ACKNOWLEDGED_EVERY_BYTE\nHOST_ROUTER_RAW_SCORE_V1 profile=3 transaction=0 owner=9 values=32768 bytes=131072 dtype=FP32 source=SELECTION_INPUT_FIRE terminal=CLEAN coverage=EXACT_ONCE\n');return 0
   def reference(root,result,key,shape,dtype):return {'stage.mlp.gate.0.2':ids,'stage.mlp.gate.0.1':weights,'stage.mlp.gate.0.0':logits}[key]
   with contextlib.ExitStack() as stack:
    for name,value in dict(require_outer_context=lambda x:None,load_binding=lambda *a:(b,{'artifact_identity':{}}),verify_local_build=lambda *a:{},verify_runtime_abi=lambda *a:{},pin=lambda p:pathlib.Path(p['path']),records=lambda p:([],['launch','1','3'],{'output':(0,64,4,5)}),expected=lambda *a:{'output':bytes(4)},reference=reference,execute=execute,verify_current_observation_round=lambda *a:{'mock_only':True}).items():stack.enter_context(patch.object(c,name,value))
    stack.enter_context(patch.object(c.argparse.ArgumentParser,'parse_args',return_value=args))
    # records still requires its normal explicit views binding in actual main.
    stack.enter_context(patch.object(c,'records',return_value=([['views',str(views)]],['launch','1','3'],{'output':(0,64,4,5)})))
    with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as stop:c.main()
    self.assertEqual(stop.exception.code,2)
   result=json.loads((args.output/'RESULT.json').read_text());r=result['profiles'][0]
   self.assertNotIn('error',r);self.assertEqual(r['router']['raw_probability_diagnostics']['status'],'COMPARED_DIAGNOSTIC_ONLY')
   self.assertEqual(r['router']['raw_probability_diagnostics']['actual_selected_output']['status'],'COMPARED_ACTUAL_SELECTION_OUTPUT_DIAGNOSTIC_ONLY');self.assertEqual(r['missing_observations'],[]);self.assertEqual(r['status'],'INCOMPLETE');self.assertFalse(result['numerical_pass']);self.assertFalse(r['numerical_pass'])
if __name__=='__main__':unittest.main()
