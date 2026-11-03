"""Small metadata/synthetic-negative tests only. Never imports Torch or runs a forward."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fixture_gate
from fixture_gate import FixtureMismatch, Gate
import run_portable
from safe_export import COMPLETE_CLEANUP

HERE = Path(__file__).resolve().parent

class ContractTests(unittest.TestCase):
    def test_frozen_inputs_complete(self):
        f=fixture_gate.frozen()
        records=f['frozen_fixture']['tensor_records']
        self.assertEqual((len(records),sum(v['bytes'] for v in records.values())),(24,10650624))
        self.assertEqual((len(f['weights']),sum(v['bytes'] for v in f['weights'])),(12,93595648))
        self.assertEqual((len(f['wheels']),sum(v['size_bytes'] for v in f['wheels'])),(26,238463458))
        self.assertEqual(f['frozen_fixture']['original_profile']['seed'],34930816)
        self.assertEqual(fixture_gate.sha(HERE/'config.json'),f['frozen_fixture']['original_profile']['config_sha256'])
        self.assertEqual(f['frozen_fixture']['rope1024']['sha256'],'4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815')

    def synthetic(self):
        pin=dict(shape=[2],dtype='torch.float32',bytes=2,sha256=hashlib.sha256(b'ab').hexdigest())
        return dict(frozen_fixture=dict(tensor_records={'a':pin},rope1024=dict(pin)))

    def test_gate_shape_dtype_hash_bytes_and_first_failure(self):
        for shape,dtype,data in (([3],'torch.float32',b'ab'),([2],'torch.bfloat16',b'ab'),([2],'torch.float32',b'ac'),([2],'torch.float32',b'a')):
            with self.subTest(shape=shape,dtype=dtype,data=data), tempfile.TemporaryDirectory() as d, patch('fixture_gate.frozen',self.synthetic):
                gate=Gate(d,['a'])
                with self.assertRaises(FixtureMismatch):gate.check('a',shape,dtype,data)
                row=json.loads((Path(d)/'CHECKS_INTERNAL.json').read_text())['a']
                self.assertEqual(row['observed_sha256'],hashlib.sha256(data).hexdigest())
                self.assertEqual(row['status'],'MISMATCH')
                self.assertNotIn('data',row)

    def test_missing_extra_duplicate_tensor_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch('fixture_gate.frozen',self.synthetic):
            gate=Gate(d,['a'])
            with self.assertRaises(FixtureMismatch):gate.finish()
            with self.assertRaises(FixtureMismatch):gate.check('unknown',[2],'torch.float32',b'ab')
            gate.check('a',[2],'torch.float32',b'ab')
            with self.assertRaises(FixtureMismatch):gate.check('a',[2],'torch.float32',b'ab')

    def test_historical_weight_sha_not_new_receipt_digest(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'weight';path.write_bytes(b'ac')
            expected=dict(name='w',shape=[1],dtype='BF16',bytes=2,start=0,end=1,url='https://example.test/pinned',shard_bytes=2,sha256=hashlib.sha256(b'ab').hexdigest())
            record=dict(expected,actual_sha256=hashlib.sha256(b'ac').hexdigest())
            with patch('fixture_gate.frozen',return_value={'weights':[expected]}):
                with self.assertRaises(FixtureMismatch):fixture_gate.check_weight(record,path)

    def report(self):
        return dict(native_exit=0,errors=[],status='PASS_PROCESS_ONLY',cleanup_proof={'status':COMPLETE_CLEANUP},observed_remaining=[],
                    log_capture={'pipe_eof_observed':True,'gzip_finalized':True},reader_join_barrier={'complete':True},
                    rss_telemetry={'all_written_bytes_verified':True},elapsed_seconds=1,observed_peak_rss=1,peak_stage_tree_bytes=1)

    def test_no_success_without_eof_cleanup_or_native_exit(self):
        for field,value in (('native_exit',1),('cleanup_proof',None),('log_capture',{'pipe_eof_observed':False,'gzip_finalized':True}),('reader_join_barrier',{'complete':False}),('rss_telemetry',{})):
            report=self.report();report[field]=value
            self.assertFalse(run_portable.complete_native(report))
            self.assertNotEqual(run_portable.stage_summary('reference',report,1)['status'],'PASS')

    def test_timeout_rss_disk_cpu_negative(self):
        for key,value in (('elapsed_seconds',601),('observed_peak_rss',3*(1<<30)+1),('peak_stage_tree_bytes',160*(1<<20)+1)):
            report=self.report();report[key]=value
            self.assertEqual(run_portable.stage_summary('reference',report,1)['status'],'FAIL')
        self.assertEqual(run_portable.stage_summary('reference',self.report(),1201)['status'],'FAIL')

    def test_source_only_two_forward_calls_and_explicit_dispatch(self):
        source=(HERE/'run_reference.py').read_text();tree=ast.parse(source)
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='call']
        self.assertEqual(len(calls),2)
        self.assertIn('expected_env = "avx512"',source)
        self.assertIn('torch.backends.cpu.get_cpu_capability() == "AVX512"',source)
        self.assertIn('gate.check(name, list(tensor.shape), str(tensor.dtype), data)',source)
        self.assertLess(source.index('gate.check(name'),source.index('with file.open("xb")'))
        self.assertIn('with torch.inference_mode(), torch.autocast("cpu", enabled=False)',source)

if __name__=='__main__':unittest.main()
