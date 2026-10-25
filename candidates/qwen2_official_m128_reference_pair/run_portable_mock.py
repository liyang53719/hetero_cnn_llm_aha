"""Portable lightweight stdlib subset only; NOT the original 92-case suite.
No model imports, real worker launch, raw13 payload reads or network actions.
"""
import ast
import hashlib
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

class DenyML(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','numpy','transformers'}:
            raise AssertionError('Numerical import forbidden in portable source/mock subset')
sys.meta_path.insert(0,DenyML())
ROOT=Path(__file__).resolve().parent
HERE=ROOT/'full_reference_gate'
sys.path.insert(0,str(HERE))
import gate_common as common
import run_gate as launcher
spec=importlib.util.spec_from_file_location('portable_fresh_m128_capture',ROOT/'capture_pair/capture_pair.py')
pair=importlib.util.module_from_spec(spec);spec.loader.exec_module(pair)

class PortableSourceTests(unittest.TestCase):
    def test_eight_operational_sources_are_exact_frozen_bytes(self):
        m=json.loads((ROOT/'SOURCE_SHA256.json').read_text())
        self.assertEqual(len(m['files']),8)
        for name,wanted in m['files'].items():
            data=(ROOT/name).read_bytes()
            self.assertEqual({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},wanted,name)

    def test_public_entry_and_projection_are_execution_disabled(self):
        profile=json.loads((ROOT/'PROFILE_DRAFT.json').read_text())
        self.assertFalse(profile['launch_ready']);self.assertFalse(profile['execution_authority'])
        self.assertFalse(profile['runtime_closure_provided']);self.assertFalse(profile['raw13_payload_provided'])
        with self.assertRaises(pair.ExecutionDisabled):pair.run_capture(None,None,None)
        with self.assertRaisesRegex(ValueError,'not launch-ready'):launcher.validate_review({},'c'*64,'r'*64,{},profile)

    def test_all29_logical_geometry_and_precision(self):
        pins=pair.load_pins();self.assertEqual(set(pins['fields']),set(pair.FIELD_ORDER));self.assertEqual(len(pair.FIELD_ORDER),29)
        self.assertEqual(pins['geometry']['tokens'],128);self.assertEqual(pins['geometry']['chunk_count'],1)
        self.assertEqual(pins['fields']['x']['shape'],[1,128,1536])
        self.assertEqual(pins['fields']['k']['shape'],[1,2,128,128])
        self.assertEqual(pins['fields']['prob']['shape'],[1,12,128,128])
        self.assertEqual(pins['fields']['gate']['shape'],[1,128,8960])
        for name,f in pins['fields'].items():
            self.assertNotIn(16,f['shape']);self.assertEqual(f['export_f32_bytes'],4*math.prod(f['shape']))
            self.assertEqual(f['dtype'],'float32' if name=='softmax_fp32' else 'bfloat16')

    def test_original_config_requirements_remain_in_source(self):
        source=(ROOT/'capture_pair/capture_pair.py').read_text()
        self.assertIn('config.max_position_embeddings == 32768 and config.rope_theta == 1e6',source)
        self.assertEqual(source.count('past_key_value=None, output_attentions=True, use_cache=False'),2)
        self.assertIn('load_raw_bf16(torch, embedding)[:TOKENS]',source)
        self.assertFalse(pair.PAIR_PROFILE['all29_intermediate_noninterference_claimed'])

    def test_m128_causal_mask_counts_and_last_row(self):
        words=[x[0] for x in struct.iter_unpack('<H',pair.cold_mask_bytes())]
        self.assertEqual(len(words),16384);self.assertEqual(words.count(0),8256);self.assertEqual(words.count(0xff7f),8128)
        self.assertEqual(words[-128:],[0]*128);self.assertEqual(12*words.count(0),99072);self.assertEqual(12*words.count(0xff7f),97536)

    def test_single_layer_two_identical_calls_baseline_before_observer(self):
        source=(ROOT/'capture_pair/capture_pair.py').read_text();t=ast.parse(source)
        f=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='_capture_pair_impl')
        calls=sorted([n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='layer'],key=lambda n:n.lineno)
        constructors=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='Qwen2DecoderLayer']
        self.assertEqual(len(calls),2);self.assertEqual(len(constructors),1)
        self.assertEqual(ast.dump(calls[0],include_attributes=False),ast.dump(calls[1],include_attributes=False))
        self.assertLess(source.index('baseline_returned = layer('),source.index('observer = Observer('))

    def test_original_thresholds_and_geometry_byte_projection(self):
        pins=pair.load_pins();g=pins['comparison_gates']
        self.assertEqual(g['rowsum_abs_error_lte'],2e-5);self.assertFalse(g['nonfinite_allowed'])
        self.assertEqual(g['operator_bf16'],{'combine':'AND','max_abs_lte':0.03125,'mean_abs_lte':0.005})
        self.assertEqual(g['block_y'],{'combine':'AND','max_abs_lte':0.05,'mean_abs_lte':0.01})
        fields=pins['fields'];native=sum(math.prod(f['shape'])*(4 if f['dtype']=='float32' else 2) for f in fields.values())
        f32=sum(f['export_f32_bytes'] for f in fields.values());base=sum(2*math.prod(fields[n]['shape']) for n in ['y','prob'])
        self.assertEqual((native,f32,base),(16678912,32571392,786432));self.assertEqual(native+f32+base,50036736)

    def test_pair_bytes_reject_changed_second_output_without_all29_claim(self):
        values=(types.SimpleNamespace(payload=b'aa'),types.SimpleNamespace(payload=b'bb'))
        with patch.object(pair,'tensor_native_bytes',side_effect=lambda torch,t:t.payload):
            good=pair.compare_pair_outputs(None,{'y':b'aa','prob':b'bb'},values)
            bad=pair.compare_pair_outputs(None,{'y':b'aa','prob':b'cc'},values)
        self.assertTrue(good['passed']);self.assertFalse(bad['passed']);self.assertFalse(good['all29_intermediate_noninterference_claimed'])

class TerminalOutputBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name)
        self.payload=self.out/'synthetic_payload.bin';self.payload.write_bytes(b'')
        self.receipt={'status':'REFERENCE_PAIR_CAPTURE_AND_SELF_CHECKS_COMPLETE_NOT_DUT_PASS',
                      'passed':True,'limit_reason':None,'artifacts':{},'no_retry':True}
        self.seal={'schema':1,'status':self.receipt['status'],'numeric_acceptance':'NOT_RUN','artifacts':{}}

    def tearDown(self):self.tmp.cleanup()

    def resize(self,size):
        with self.payload.open('wb') as f:f.truncate(size)

    def finalize(self):
        return launcher.finalize_terminal_output(self.out,self.receipt,self.seal,
                                                completion_path=self.out/'COMPLETION_SEAL.json')

    def fit_exact(self,target):
        base=target-4096
        for _ in range(16):
            self.resize(base)
            projection=launcher.project_terminal_success(self.out,self.receipt,self.seal)
            difference=target-projection['projected_total_bytes']
            if not difference:return projection
            base+=difference
        self.fail('test could not reach exact byte boundary')

    def assert_failed_without_seal(self,reason=None):
        self.assertFalse((self.out/'COMPLETION_SEAL.json').exists())
        receipt=json.loads((self.out/'RECEIPT.json').read_text())
        self.assertFalse(receipt['passed']);self.assertEqual(receipt['status'],'FAIL_OFFICIAL_M128_REFERENCE_GATE')
        self.assertTrue(receipt['terminal_output_budget']['failure_diagnostics_may_exceed_success_limit'])
        self.assertTrue(receipt['terminal_output_budget']['no_artifacts_deleted_to_fit_limit'])
        if reason:self.assertIn(reason,receipt['limit_reason'])
        return receipt

    def test_exact_projection_uses_actual_encoded_receipt_and_seal_bytes(self):
        self.resize(73)
        p=launcher.project_terminal_success(self.out,self.receipt,self.seal)
        receipt_raw=common.encoded(p['receipt']);seal_raw=common.encoded(p['seal'])
        self.assertEqual(p['receipt_identity'],{'bytes':len(receipt_raw),'sha256':common.sha(receipt_raw)})
        self.assertEqual(p['seal_identity'],{'bytes':len(seal_raw),'sha256':common.sha(seal_raw)})
        self.assertEqual(p['projected_total_bytes'],73+len(receipt_raw)+len(seal_raw))
        self.assertEqual(p['seal']['terminal_output_budget']['final_output_bytes'],p['projected_total_bytes'])
        self.assertEqual(p['seal']['terminal_output_budget']['completion_seal_bytes'],len(seal_raw))
        self.assertEqual(set(p.name for p in self.out.iterdir()),{'synthetic_payload.bin'})

    def test_exact_80mib_final_output_is_accepted_and_sealed_last(self):
        p=self.fit_exact(83886080);events=[];real_write=launcher.write_new;real_rename=Path.rename
        def tracked_write(path,value):
            events.append(('write',Path(path).name));return real_write(path,value)
        def tracked_rename(source,target):
            events.append(('rename',Path(target).name));return real_rename(source,target)
        with patch.object(launcher,'write_new',side_effect=tracked_write),patch.object(Path,'rename',autospec=True,side_effect=tracked_rename):
            receipt,passed=self.finalize()
        self.assertTrue(passed);self.assertTrue(receipt['passed'])
        self.assertEqual(launcher.total_output(self.out),83886080)
        self.assertEqual(events[-1],('rename','COMPLETION_SEAL.json'))
        self.assertEqual(events,[('write','RECEIPT.json'),('write','COMPLETION_SEAL.pending.json'),('rename','COMPLETION_SEAL.json')])
        self.assertFalse((self.out/'COMPLETION_SEAL.pending.json').exists())
        seal=json.loads((self.out/'COMPLETION_SEAL.json').read_text())
        self.assertEqual(seal['terminal_output_budget']['final_output_bytes'],83886080)
        self.assertEqual(seal['receipt'],common.file_id(self.out/'RECEIPT.json'))
        self.assertEqual(common.file_id(self.out/'COMPLETION_SEAL.json'),p['seal_identity'])

    def test_one_byte_above_final_80mib_has_fail_receipt_and_no_seal(self):
        p=self.fit_exact(83886081);original_size=self.payload.stat().st_size
        receipt,passed=self.finalize();self.assertFalse(passed)
        self.assert_failed_without_seal('projected_final_output_limit_exceeded')
        self.assertEqual(self.payload.stat().st_size,original_size)
        self.assertFalse((self.out/'COMPLETION_SEAL.pending.json').exists())

    def test_parent_receipt_seal_overhead_cannot_escape_worker_payload_gate(self):
        self.resize(83886079)
        self.assertLess(launcher.total_output(self.out),common.LIMITS['output_bytes'])
        receipt,passed=self.finalize();self.assertFalse(passed)
        self.assert_failed_without_seal('projected_final_output_limit_exceeded')
        self.assertGreater(launcher.total_output(self.out),common.LIMITS['output_bytes'])
        self.assertEqual(self.payload.stat().st_size,83886079)

    def test_late_worker_output_after_last_poll_is_caught_at_terminal(self):
        self.resize(83886079);last_polled=launcher.total_output(self.out)
        self.assertLess(last_polled,common.LIMITS['output_bytes'])
        self.resize(83886081)
        after_cleanup=launcher.terminal_output_snapshot(self.out)
        self.assertEqual(launcher.terminal_limit_reason(after_cleanup),'terminal_output_limit_exceeded')
        receipt,passed=self.finalize();self.assertFalse(passed)
        self.assert_failed_without_seal('terminal_output_limit_exceeded')

    def test_late_log_growth_after_last_poll_is_caught_at_terminal(self):
        log=self.out/'stdout.log'
        with log.open('wb') as f:f.truncate(common.LIMITS['log_bytes_each']+1)
        self.assertEqual(launcher.terminal_limit_reason(launcher.terminal_output_snapshot(self.out)),'terminal_log_limit_exceeded')
        receipt,passed=self.finalize();self.assertFalse(passed)
        self.assert_failed_without_seal('terminal_log_limit_exceeded')
        self.assertEqual(log.stat().st_size,1048577)

    def test_changed_output_after_staging_preserves_both_candidates_and_fails(self):
        self.resize(101);real_write=launcher.write_new
        def late_write(path,value):
            result=real_write(path,value)
            if Path(path).name=='COMPLETION_SEAL.pending.json':(self.out/'late.synthetic').write_bytes(b'x')
            return result
        with patch.object(launcher,'write_new',side_effect=late_write):
            receipt,passed=self.finalize()
        self.assertFalse(passed);final=self.assert_failed_without_seal('terminal output changed after exact projection')
        preserved=final['terminal_output_budget']['preserved_rejected_candidates']
        self.assertEqual(set(preserved),{'RECEIPT.json.REJECTED','COMPLETION_SEAL.pending.json.REJECTED'})
        self.assertTrue(json.loads((self.out/'RECEIPT.json.REJECTED').read_text())['passed'])
        for name,identity in preserved.items():self.assertEqual(common.file_id(self.out/name),identity)
        self.assertEqual((self.out/'late.synthetic').read_bytes(),b'x')

    def test_oversized_output_after_staging_has_no_success_seal(self):
        self.fit_exact(83886080);real_write=launcher.write_new
        def late_write(path,value):
            result=real_write(path,value)
            if Path(path).name=='COMPLETION_SEAL.pending.json':(self.out/'late.synthetic').write_bytes(b'x')
            return result
        with patch.object(launcher,'write_new',side_effect=late_write):receipt,passed=self.finalize()
        self.assertFalse(passed);self.assert_failed_without_seal('terminal_output_limit_exceeded')
        self.assertTrue((self.out/'COMPLETION_SEAL.pending.json.REJECTED').exists())

    def test_previous_gate_failure_cannot_get_success_seal(self):
        self.receipt.update(passed=False,limit_reason='earlier_mock_limit')
        receipt,passed=self.finalize();self.assertFalse(passed)
        self.assert_failed_without_seal('earlier_mock_limit')
        self.assertFalse((self.out/'COMPLETION_SEAL.pending.json').exists())

    def test_cleanup_postflight_rechecks_precede_parent_terminal_projection(self):
        tree=ast.parse((HERE/'run_gate.py').read_text());f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='launch')
        calls=sorted((n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)),key=lambda n:n.lineno)
        snapshots=[n.lineno for n in calls if n.func.id=='terminal_output_snapshot']
        self.assertEqual(len(snapshots),2)
        postflight=next(n.lineno for n in calls if n.func.id=='manifest_postflight')
        finalizers=[n.lineno for n in calls if n.func.id=='finalize_terminal_output']
        self.assertLess(snapshots[0],postflight);self.assertLess(postflight,snapshots[1]);self.assertLess(snapshots[1],min(finalizers))
        final=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='finalize_terminal_output')
        source=ast.unparse(final)
        self.assertLess(source.index('actual = terminal_output_snapshot(out)'),source.index('pending.rename(completion_path)'))
        self.assertNotIn('.unlink(',source);self.assertNotIn('.remove(',source)

if __name__=='__main__':
    # Fail closed if a future edit accidentally routes these tests into a worker.
    with patch.object(launcher.subprocess,'Popen',side_effect=AssertionError('Real subprocess forbidden in portable subset')):
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    if {'torch','numpy','transformers'}&set(sys.modules):raise AssertionError('Forbidden numerical import')
    print('Portable 18-case lightweight subset only: 10 preserved terminal mocks + 8 new source/logical checks. Not the original 92-case suite, not independent9 reproduction, not execution approval.')
    raise SystemExit(not result.wasSuccessful())
