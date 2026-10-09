from pathlib import Path
import importlib
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np

import host_bf16_qkv_reference as projection
import host_bf16_qk_rope_reference as norm_rope
import host_bf16_attention_core_reference as core


class CandidateContract(unittest.TestCase):
    def test_window_geometry_preserves_fixed_budget(self):
        self.assertEqual(projection.validate_windows(projection.WINDOWS), projection.WINDOWS)
        self.assertEqual(projection.validate_windows(core.WINDOWS), core.WINDOWS)
        invalid = [[], (), (('cold',0,1),), (('cold',0,1),)*2,
                   (('cold',0,1),('cold',1,2)), (('cold',True,1),('cold',1,1)),
                   (('cold',0,1),('cold',128,1)), (('unknown',0,1),('cold',1,1)),
                   (('cold',0,1),('cold',1,True)), [['cold',0,1],['cold',1,1]]]
        for windows in invalid:
            with self.subTest(windows=windows), self.assertRaises(ValueError):
                projection.validate_windows(windows)

    def test_same_imported_authority_class(self):
        self.assertIs(norm_rope.projection, projection)
        self.assertIs(core.projection, projection)
        self.assertEqual(Path(projection.__file__).resolve(),projection.ROOT/'chisel/continuous_prefill/scripts/host_bf16_qkv_reference.py')
        with self.assertRaises(TypeError): projection.FreshProjectionReferenceSession()
        with self.assertRaises(TypeError): norm_rope.FreshAttentionReferenceSession()
        with self.assertRaises(ValueError): core.prepare_attention_core_expectations(None,None,None)

    def test_increasing_k_fma_witness_and_masked_zero_terms(self):
        query = np.zeros((1,8,256), dtype='<f4')
        cache = np.zeros((2,2,512), dtype='<f4')
        cache[1,0] = np.float32(1.0)
        cache[1,1] = np.float32(3.0)
        out, trace = core.gqa.causal_gqa(query, cache, query_start=1, cache_length=2, return_trace=True)
        self.assertTrue(np.array_equal(out, np.full((1,2048),2,dtype='<f4')))
        raw, expected = core.matrix_fma_witness(query, cache, trace, out)
        self.assertEqual(raw.shape, (8192,3))
        self.assertEqual(expected.shape, (8192,2))
        self.assertEqual(len(core.bf16_bytes(out)),4096)
        mutated = dict(trace)
        mutated['qk_fp32'] = trace['qk_fp32'].copy()
        mutated['qk_fp32'][0,0,0] = 1
        with self.assertRaises(ValueError): core.matrix_fma_witness(query,cache,mutated,out)
        bad = out.copy(); bad[0,0] = 3
        with self.assertRaises(ValueError): core.matrix_fma_witness(query,cache,trace,bad)


if __name__ == '__main__': unittest.main()
