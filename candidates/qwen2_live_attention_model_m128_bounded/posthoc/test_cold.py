"""Seal-metadata and audit controls only; no reference tensor comparisons."""
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from . import validation as v, runner
from .audit import ReadOnlyGate


def context():
    r, _ = v.load_receipts(); p = v.pins()
    review = json.loads((v.ROOT / p['independent_seal_review']['path']).read_text())
    return r, review, ReadOnlyGate(v.OUTPUT_ROOT / 'posthoc_cold_absent', r, review)


class PosthocColdTests(unittest.TestCase):
    def test_default_not_executed(self):
        stream = io.StringIO()
        with patch.object(runner, 'run', side_effect=AssertionError('comparison forbidden')), contextlib.redirect_stdout(stream):
            self.assertEqual(runner.main([]), 0)
        self.assertEqual(json.loads(stream.getvalue())['status'], 'NOT_EXECUTED')

    def test_exact_receipt_seal_positive(self):
        r, _ = v.load_receipts()
        v.verify_seal(r, v.pins())
        self.assertEqual(len(v.artifact_specs(r)), 41)

    def test_seal_negative_mutations(self):
        base, _ = v.load_receipts()
        mutations = [lambda r: r.update(actual_outputs_sealed=False),
            lambda r: r['held_boundary'].update(pc=11),
            lambda r: r['backend_debts'].update(matrix_owned=True),
            lambda r: r['attention']['accepted'].update(matrix_requests=1188863),
            lambda r: r['physical_memory']['outputs']['att'].update(published=True),
            lambda r: r.update(oracle_reference_reads=['premature']),
            lambda r: r['source_sha256_before'].update(forged='0' * 64),
            lambda r: r.update(fullblock_pass=True)]
        for mutate in mutations:
            r = copy.deepcopy(base); mutate(r)
            with self.assertRaises(ValueError): v.verify_seal(r, v.pins())

    def test_only_exact_runtime_reads_and_new_output_writes(self):
        r, review, gate = context()
        for path in gate.runtime: gate.audit('open', (str(path), 'rb', 0))
        self.assertEqual(len(gate.runtime_reads), 6)
        for path in (next(iter(gate.runtime)), gate.run / 'RESULT.json'):
            with self.assertRaises(ValueError): gate.audit('open', (str(path), 'wb', os.O_WRONLY))
        with self.assertRaises(ValueError): gate.audit('open', (str(v.ROOT / 'work/unknown/lib.so'), 'rb', 0))
        with self.assertRaises(ValueError): gate.audit('ctypes.dlopen', (str(next(iter(gate.runtime))),))
        with self.assertRaises(ValueError): gate.audit('subprocess.Popen', ('python',))
        gate.audit('open', (str(gate.out / 'RESULT.json'), 'w', os.O_WRONLY))

    def test_oracle_closed_until_verified_seal(self):
        _, _, gate = context()
        for path in gate.oracles:
            with self.assertRaises(ValueError): gate.audit('open', (str(path), 'rb', 0))
        self.assertEqual(gate.reference_reads, [])
        gate.opened = True
        for path in gate.oracles: gate.audit('open', (str(path), 'rb', 0))
        self.assertEqual(len(gate.reference_reads), 19)

    def test_real_audit_hook_small_runtime_positive_and_negatives(self):
        code = '''
import ctypes,json,sys
from candidates.qwen2_live_attention_model_m128_bounded.posthoc import validation as v
from candidates.qwen2_live_attention_model_m128_bounded.posthoc.audit import ReadOnlyGate
r,_=v.load_receipts();p=v.pins();review=json.loads((v.ROOT/p['independent_seal_review']['path']).read_text())
gate=ReadOnlyGate(v.OUTPUT_ROOT/'posthoc_cold_absent',r,review);sys.addaudithook(gate.audit)
s=p['runtime_native_files']['libc10.so'];path=v.ROOT/s['path']
v.require(path.stat().st_size==s['bytes'] and v.sha(path)==s['sha256'],'runtime identity mismatch')
for operation in (lambda:ctypes.CDLL(None),lambda:next(iter(gate.oracles)).read_bytes(),lambda:(gate.run/'RESULT.json').open('wb')):
 try:operation()
 except ValueError:pass
 else:raise ValueError('negative admitted')
v.require(not gate.reference_reads,'oracle payload was read')
print(json.dumps(dict(status='PASS_REAL_READONLY_RUNTIME_AUDIT',runtime_bytes=s['bytes'],oracle_payload_reads=0)))
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code], cwd=v.ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['status'], 'PASS_REAL_READONLY_RUNTIME_AUDIT')

    def test_real_comparison_imports_and_frozen_reference_metadata(self):
        code = '''
import json,sys
from candidates.qwen2_live_attention_model_m128_bounded.posthoc import validation as v
from candidates.qwen2_live_attention_model_m128_bounded.posthoc.audit import ImportGuard,ReadOnlyGate
from candidates.qwen2_live_attention_model_m128_bounded.posthoc.runner import verify_input_identity,verify_inventory,verify_records
r,_=v.load_receipts();p=v.pins();out=v.OUTPUT_ROOT/'posthoc_cold_absent'
review=json.loads((v.ROOT/p['independent_seal_review']['path']).read_text())
sys.addaudithook(ImportGuard(out).audit)
import numpy as np
from scripts import qwen2_layer0_model_gate as native
from candidates.qwen2_live_attention_model_m128 import gates as original,compare
gate=ReadOnlyGate(out,r,review);sys.addaudithook(gate.audit)
v.sources()
verify_inventory(v.ROOT/p['run_path'],review)
v.verify_artifacts(v.ROOT/p['run_path'],r)
verify_records(r['tools_before'])
verify_records(r['native_artifact_reuse']['artifact_identity_before'])
verified=verify_input_identity(r,review)
v.require(len(verified['inputs'])==9 and len(verified['raw_inputs'])==8,'input/raw identity role counts')
capture=v.FrozenCapture(v.ROOT/p['run_path'],r)
pv=np.frombuffer(capture._bytes('pv_bf16'),'<u4').reshape(12,128,128).transpose(1,0,2).copy().tobytes()
v.require(pv==(v.ROOT/p['run_path']/'att.f32le').read_bytes(),'PV layout')
metadata=original.validate_reference_metadata(v.ROOT/p['data_path'],v.ROOT/p['reference_path'])
policy=native.load_policy(v.ROOT)
v.require(set(metadata['outputs'])==original.REFERENCES,'metadata outputs')
v.require(not gate.reference_reads and not any(n=='torch' or n.startswith('torch.') for n in sys.modules),'payload/Torch import')
v.require(len(set(gate.runtime_reads))==6,'six real runtime identities not checked')
print(json.dumps(dict(status='PASS_REAL_FROZEN_REFERENCE_METADATA',complete_pre_oracle_preparation=True,runtime_files=6,reference_payload_reads=0,torch_imported=False,comparison_executed=False)))
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code], cwd=v.ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['status'], 'PASS_REAL_FROZEN_REFERENCE_METADATA')


if __name__ == '__main__': unittest.main()
