import os
from pathlib import Path
import tempfile
import unittest
import live_budget as b

class LiveBudget(unittest.TestCase):
    def snapshot(self):
        return dict(schema='SAMPLED_OWNED_LIVE_BYTES_V1', complete=True,
                    bytes=100, free_bytes=10*1024**3, finished_monotonic=100)
    def call(self, **kwargs):
        params=dict(extra_bytes=200,phase_seconds=300,job_started=0,now=100)
        params.update(kwargs)
        return b.admit(self.snapshot(),**params)
    def test_dedup_nested_hardlinks_and_ignore_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'a').write_bytes(b'x'*17);(p/'sub').mkdir()
            os.link(p/'a',p/'sub'/'copy');(p/'outside').symlink_to('/no/such/target')
            s=b.census([p,p/'sub'])
            self.assertEqual((s['bytes'],s['files'],s['symlinks_not_followed']),(17,1,1))
    def test_entry_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'a').touch();(p/'b').touch()
            with self.assertRaisesRegex(ValueError,'entry census cap'):b.census([p],max_entries=1)
    def test_root_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'real').mkdir();(p/'alias').symlink_to(p/'real')
            with self.assertRaisesRegex(ValueError,'root alias'):b.census([p/'alias'])
    def test_special_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);os.mkfifo(p/'fifo')
            with self.assertRaisesRegex(ValueError,'nonregular'):b.census([p])
    def test_bounded_phase(self):
        r=self.call(acquisition=True);self.assertEqual(r['resulting_byte_ceiling'],300)
        self.assertEqual(r['resource_peak_qualification'],'INCOMPLETE_SAMPLED_NOT_CONTINUOUS')
    def test_deadline_not_five_times_20000(self):
        with self.assertRaisesRegex(ValueError,'remaining job wall'):self.call(phase_seconds=100000)
        s=self.snapshot();s['finished_monotonic']=20999
        with self.assertRaisesRegex(ValueError,'remaining job wall'):b.admit(s,extra_bytes=0,phase_seconds=5,job_started=0,now=20999)
    def test_bytes_and_floor(self):
        with self.assertRaises(ValueError):self.call(extra_bytes=b.TREE_CAP)
        s=self.snapshot();s['free_bytes']=b.ACQUISITION_FLOOR-1
        with self.assertRaisesRegex(ValueError,'8GiB'):b.admit(s,extra_bytes=0,phase_seconds=5,job_started=0,now=100,acquisition=True)
        s['free_bytes']=b.FREE_RESERVE
        with self.assertRaisesRegex(ValueError,'disk reserve'):b.admit(s,extra_bytes=1,phase_seconds=5,job_started=0,now=100)
    def test_bad_stale_values(self):
        for kw in ({'extra_bytes':True},{'phase_seconds':float('nan')},{'now':103},{'now':99}):
            with self.assertRaises(ValueError):self.call(**kw)
if __name__=='__main__':unittest.main()
