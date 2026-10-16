import unittest
import tempfile,shutil
from pathlib import Path
from unittest.mock import patch
from . import check_sources
from .storage import Scratch, Context, address
from ..raw_kv_parent.model import ParentLoan


class StorageTests(unittest.TestCase):
    def make(self, **kw):
        s=Scratch(enabled=True,**kw);s.acquire();return s

    def test_original_owner_identity_sequence_and_access_accounting(self):
        parent=ParentLoan(enabled=True)
        s=self.make(owner=parent.owner,stalls=2)
        self.assertIs(s.banks,parent.owner.a_banks)
        self.assertIs(s.parent.raw.banks,s.banks)
        c=s.begin(1,1,2)
        s.write_scores(c,0,(0x80000000,0x7fc00123))
        self.assertEqual(s.read_word(c,'score',0,0),0x80000000)
        self.assertEqual(s.read_word(c,'score',0,1),0x7fc00123)
        for key in range(2):s.write_probability(c,0,key,100+key)
        for key in range(2):
            self.assertEqual(s.read_word(c,'prob',0,key),100+key)
            s.write_probability(c,0,key,200+key,normalized=True)
        for key in range(2):self.assertEqual(s.read_word(c,'prob',0,key,normalized=True),200+key)
        n=s.counts['read_requests']+s.counts['write_requests']
        self.assertEqual(s.counts['edges'],1+5*n)
        self.assertEqual(s.counts['acks'],n)
        self.assertEqual(s.counts['bank_reads'],2*s.counts['read_requests'])
        self.assertEqual(s.counts['bank_writes'],2*s.counts['write_requests'])
        self.assertTrue(all(len(r)+len(w)==(2 if accept else 0) for _,r,w,accept,ack in s.events))
        self.assertIsNone(s.staging)
        self.assertTrue(all(x==0 for row in s.banks.words for x in row[:512]))
        s.release()

    def test_generation_invalidates_all_visibility(self):
        s=self.make();old=s.begin(0,0,1);s.write_scores(old,0,(1,))
        new=s.begin(0,1,1)
        with self.assertRaises(ValueError):s.read_word(old,'score',0,0)
        with self.assertRaises(ValueError):s.read_word(new,'score',0,0)
        with self.assertRaises(ValueError):s.read_word(Context(True,0,1,1),'score',0,0)
        self.assertFalse(s.initialized)
        s.write_scores(new,0,(2,));self.assertEqual(s.read_word(new,'score',0,0),2)
        s.release()

    def test_abort_accepted_write_drains_without_validity(self):
        s=self.make()
        c=s.begin(0,0,1)
        observations=[]
        def edge():
            if s.active and s.parent.raw.pending is not None:
                with self.assertRaises(ValueError):s.begin(0,1,1)
                with self.assertRaises(ValueError):s.release()
                observations.append(s.active)
                s.abort()
        s.edge=edge
        with self.assertRaisesRegex(ValueError,'retired poisoned'):s.write_scores(c,0,(123,))
        self.assertEqual(len(observations),1)
        self.assertTrue(s.parent.raw.drained)
        self.assertIsNone(s.active)
        self.assertFalse(s.initialized)
        self.assertEqual(s.score_written,[0]*6)
        self.assertEqual(s.counts['acks'],1)
        s.release()
        self.assertTrue(s.parent.raw.poison)

    def test_prefix_and_coordinate_guards(self):
        s=self.make();c=s.begin(1,0,2)
        for args in [('score',True,0),('score',0,True),('kv',0,0),('prob',6,0),('prob',0,128)]:
            with self.assertRaises(ValueError):address(*args)
        with self.assertRaises(ValueError):s.write_probability(c,0,1,1)
        with self.assertRaises(ValueError):s.write_probability(c,0,0,1,normalized=True)
        s.write_probability(c,0,0,1)
        with self.assertRaises(ValueError):s.read_word(c,'prob',0,1)
        with self.assertRaises(ValueError):s.read_word(c,'prob',0,0,normalized=True)
        with self.assertRaises(ValueError):s.write_scores(c,0,(1,))
        s.release()

    def test_actual_parent_source_drift_fails_closed(self):
        self.assertEqual(check_sources.check()['status'],'PASS_SOURCE_ONLY')
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for relative in (*check_sources.SOURCES,*check_sources.OWN):
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(check_sources.ROOT/relative,target)
            source=root/'candidates/qwen2_resident_matrix/dense_block_reduce/dense_drain.py'
            source.write_text(source.read_text()+'\n# changed actual owner\n')
            with patch.object(check_sources,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'source drift'):check_sources.check()

if __name__=='__main__':unittest.main()
