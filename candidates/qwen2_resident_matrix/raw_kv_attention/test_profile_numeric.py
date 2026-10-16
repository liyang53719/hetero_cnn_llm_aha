"""Cold schedule/entrypoint tests; never invoke native numerical services."""
from collections import Counter
import os
import unittest
from unittest.mock import patch
from .profile_numeric import scalar_schedule,Checkpoints,run_calibration,source_snapshot
from .streaming import profile

class ProfilePreparation(unittest.TestCase):
    def test_complete_small_schedules_match_source_counts(self):
        for tokens in (1,2,4,8):
            counts=Counter();stages=Counter()
            for operation,policy,stage,coords,select_input in scalar_schedule(tokens):
                counts[operation]+=1
                if stage:stages[stage]+=1
            expected=profile(tokens)
            self.assertEqual(dict(counts),expected['scalar_counts_no_cutoff'])
            self.assertEqual(sum(counts.values()),6696*tokens*(tokens+1)//2+1548*tokens)
            self.assertEqual(stages['dots'],12*tokens*(tokens+1)//2)
            self.assertEqual(stages['probabilities'],8*stages['dots'])
            self.assertEqual(stages['output'],tokens*1536)

    def test_m128_counts_without_iterating_schedule(self):
        p=profile(128)
        self.assertEqual(p['kv_reads'],1585152)
        self.assertEqual(p['native_fmas'],811597824)
        self.assertEqual(p['scalar_total_no_cutoff'],55480320)
        self.assertEqual(p['unique_kv_lines'],4096)
        self.assertEqual(p['output_writes']*16,196608)

    def test_missing_native_library_is_not_success(self):
        with patch.dict(os.environ,{},clear=True):code,result=run_calibration()
        self.assertEqual(code,2);self.assertEqual(result['status'],'NOT_RUN')
        self.assertFalse(result['m128_executed'])

    def test_calibration_new_source_freeze_is_complete(self):
        hashes=source_snapshot()
        for name in ('streaming.py','reference_profile.py','profile_numeric.py',
                     'test_streaming.py','test_reference_profile.py','test_profile_numeric.py'):
            self.assertIn('candidates/qwen2_resident_matrix/raw_kv_attention/'+name,hashes)
        self.assertTrue(all(len(digest)==64 for digest in hashes.values()))

    def test_schedule_and_coverage_fail_closed(self):
        check=Checkpoints(1,None)
        with self.assertRaisesRegex(ValueError,'schedule'):
            check(('mul',0,0,0,'legacy_scalar'))
        with self.assertRaisesRegex(ValueError,'missing'):
            Checkpoints(1,None).finish()
        for bad in (True,0,3,129):
            with self.assertRaises(ValueError):next(scalar_schedule(bad))

if __name__=='__main__':unittest.main()
