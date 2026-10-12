"""Failure-evidence serialization only; no arithmetic or model execution."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from .run_projection_prefix import snapshot_bytes, preserve_failure, persist, ORDER, sha
from ..qwen35_gdn_prefill.typed_dense import TypedMemory


class PreservationTests(unittest.TestCase):
    def test_snapshots_preserve_bytes_and_never_overwrite_existing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);raw=bytes(range(64))
            receipt=snapshot_bytes(out,'raw/input.bin',raw)
            self.assertEqual(receipt,dict(file='raw/input.bin',bytes=64,sha256=sha(raw)))
            with self.assertRaises(FileExistsError):snapshot_bytes(out,'raw/input.bin',b'changed')
            self.assertEqual((out/'raw/input.bin').read_bytes(),raw)

    def test_failed_partial_staging_keeps_raw_data_and_unretired_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory=TypedMemory();bases={role:0x10000+index*0x1000 for index,role in enumerate(ORDER)}
            for base in bases.values():memory.allocate_output(base,64)
            region=memory.regions[bases['packed_q_gate']]
            region.storage[64:128]=bytes(range(64));region.written.add(0)
            owner=SimpleNamespace(state='drain')
            coordinator=SimpleNamespace(role='packed_q_gate',ticks=31,commands=[{}],response=None,
                matrix=SimpleNamespace(epoch=7,reset_required=True),memory=memory,aborted=True,locked=False,
                plan=SimpleNamespace(**bases),active=SimpleNamespace(owner=owner,counts={'step_fire':3}),
                report=lambda:dict(complete=False,fullprefix_success=False))
            report={};out=Path(tmp);preserve_failure(report,out,coordinator)
            self.assertEqual(report['active_at_failure']['matrix_epoch'],7)
            self.assertFalse(report['active_at_failure']['fullprefix_terminal'])
            saved=report['partial_staging']['packed_q_gate']
            self.assertEqual((out/saved['file']).read_bytes(),bytes(range(64)))
            self.assertEqual((saved['written_beats'],saved['acknowledged_beats']),(1,0))
            self.assertFalse(saved['published']);self.assertFalse(saved['complete_or_accepted'])
            self.assertFalse(region.published)
            self.assertEqual(report['evidence_preservation_errors'],[])
            damaged=memory.regions[bases['input_norm']]
            damaged.storage[0] ^= 1
            failed={'error':{'type':'OriginalFailure','message':'keep original'}}
            preserve_failure(failed,out/'guard_failure',coordinator)
            self.assertEqual(failed['error']['type'],'OriginalFailure')
            self.assertEqual(failed['evidence_preservation_errors'][0]['role'],'input_norm')
            self.assertIn('packed_q_gate',failed['partial_staging'])
            del coordinator.active
            del memory.regions[bases['input_norm']]
            binding_failed={'error':{'type':'OriginalBindingFailure','message':'keep original'}}
            preserve_failure(binding_failed,out/'binding_failure',coordinator)
            self.assertEqual(binding_failed['error']['type'],'OriginalBindingFailure')
            self.assertIsNone(binding_failed['active_at_failure'])
            self.assertEqual([e['role'] for e in binding_failed['evidence_preservation_errors']],
                             ['active_state','input_norm'])
            self.assertEqual(set(binding_failed['partial_staging']),set(ORDER)-{'input_norm'})

    def test_early_failure_does_not_invent_a_coordinator_or_replace_report_with_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            report={};preserve_failure(report,Path(tmp),None)
            self.assertEqual(report,{'active_at_failure':None})
            path=Path(tmp)/'summary.json';persist(path,{'status':'FAILED'});before=path.read_bytes()
            with self.assertRaises(ValueError):persist(path,{'bad':float('nan')})
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':unittest.main()
