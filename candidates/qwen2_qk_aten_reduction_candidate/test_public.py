import unittest
import copy
from pathlib import Path
from candidates.qwen2_qk_aten_reduction_candidate import model,probe,public_summary
class PublicTests(unittest.TestCase):
    def test_cold(self):
        self.assertEqual(public_summary.run()['status'],'NOT_EXECUTED')
        self.assertEqual(probe.run()['status'],'NOT_EXECUTED')
    def metric(self):return {'max_abs':1.0,'mean_abs':0.25,'count':4,'different':1,'bit_diff_count':1}
    def test_metric_projection(self):
        self.assertEqual(public_summary.aggregate_metrics(self.metric()),self.metric())
    def test_reject_metadata_and_unknown_keys(self):
        m=self.metric();m['path']='private/path'
        with self.assertRaises(ValueError):public_summary.aggregate_metrics(m)
    def test_reject_numeric_injections(self):
        for key in ('max_abs','mean_abs'):
            for bad in ('private/path',{'path':'private'},[1],True,None,float('nan'),float('inf'),-1.0,10**1000):
                with self.subTest(key=key,value=type(bad).__name__):
                    m=self.metric();m[key]=bad
                    with self.assertRaises(ValueError):public_summary.aggregate_metrics(m)
    def test_reject_abnormal_counts(self):
        for key in ('count','different','bit_diff_count'):
            for bad in ('private',{},[],True,None,1.0,-1,1<<40):
                m=self.metric();m[key]=bad
                with self.assertRaises(ValueError):public_summary.aggregate_metrics(m)
        for changes in ({'count':0},{'different':5},{'bit_diff_count':5},{'different':2},{'mean_abs':2},{'max_abs':0}):
            m=self.metric();m.update(changes)
            with self.assertRaises(ValueError):public_summary.aggregate_metrics(m)
    def test_exact_verdict_and_counters(self):
        for bad in ('PASS',1,{},None):
            with self.assertRaises(ValueError):public_summary.verdict(bad)
        for bad in ('private/path',True,-1,1.0,3):
            with self.assertRaises(ValueError):public_summary.fixed_count(bad,4)
    def test_reference_is_after_candidate_loop(self):
        source=Path(probe.__file__).read_text()
        self.assertLess(source.index("for n in ('q','k'):"),source.index('official.prefix(raw,pins,torch,np)'))
        self.assertLess(source.index('own[n+\'r\'],own[n],owners[n]=model.original_bias_rope'),source.index('official.prefix(raw,pins,torch,np)'))
    def test_suffix_real_owner(self):
        source=Path(model.__file__).read_text()
        self.assertIn('OfficialPrefixOwner(scalar,max_tokens=1024)',source)
        self.assertIn('result=h.run(j)',source)
        self.assertIn("owner.ack_bytes==j.write_bytes",source)
    def test_no_fullblock_entrypoint(self):
        source=Path(probe.__file__).read_text()
        self.assertNotIn('fullgraph_execution',source)
        self.assertNotIn('OfficialPublicExecution(',source)
if __name__=='__main__':unittest.main()
