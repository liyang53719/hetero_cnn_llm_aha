"""Synthetic physical-cache readback and real original NumPy gate; no DUT model."""
from array import array
import copy
import hashlib
import unittest
from unittest.mock import patch
from . import comparator as C,gates


class ComparatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        from scripts import qwen2_layer0_model_gate as native
        cls.np=np;cls.native=native;cls.policy=native.load_policy(gates.ROOT)

    def fixture(self,official_token=None):
        np=self.np
        zero=b'\0'*131072
        if official_token is None:official_token=np.full(32768,0.00390625,dtype='<f4').tobytes()
        official_head=np.frombuffer(official_token,dtype='<f4').reshape(1,128,2,128).transpose(0,2,1,3).copy().tobytes()
        payloads=dict(k=official_head,v=official_token,cache_k=official_head,cache_v=official_head)
        reference={'outputs':{name:dict(shape=[1,2,128,128],sha256=hashlib.sha256(raw).hexdigest()) for name,raw in payloads.items()}}
        actual={}
        for name,raw in (('k',zero),('v',zero),('kv',zero+zero)):
            actual[name]=array('I');actual[name].frombytes(raw)
        sealed={n:dict(bytes=len(a)*4,sha256=hashlib.sha256(a.tobytes()).hexdigest()) for n,a in actual.items()}
        producers=[dict(name=name,sha256=sealed[name]['sha256'],finite=True,public_completion_retired=True,
            owner_terminal=True,ack_bytes=131072,job=dict(dst=address)) for name,address in (('k',1024),('v',132096))]
        report=dict(actual_outputs_sealed=True,whole_block_terminal=True,finalfence=True,numerical_policy=self.policy,
            execution={'host':{'launch_result':{'completed':21}}},same_live_identity_initial={'synthetic':7},
            same_live_identity_at_pc12={'synthetic':7},same_live_identity_final={'synthetic':7},
            sealed_actual_outputs=sealed,producers=producers,
            kv_append=dict(job=dict(kind='KvAppend',tag=9,write_bytes=262144,a=1024,b=132096,dst=263168),
                bytes=262144,exact_copy=True,coverage_64b_beats=4096,physical_counter_delta={'write_ack_bytes':262144},
                sha256=sealed['kv']['sha256'],k_sha256=sealed['k']['sha256'],v_sha256=sealed['v']['sha256']))
        legacy={field:{name:dict(official_numeric_pass=True) for name in names} for field,names in C.GROUPS}
        legacy.update(official_kv_comparison=dict(official_numeric_pass=True,official_kv_exact_copy=False),
            softmax_probability_sum=dict(passed=True),official_observed_node_pass=False,fullblock_pass=False,
            cold_cache_comparisons={name:dict(exact_cold_alias=False) for name in ('cache_k','cache_v')})
        return report,actual,reference,payloads,legacy

    def invoke(self,fixture):
        report,actual,reference,payloads,legacy=fixture
        with patch.object(C.old,'official',return_value=copy.deepcopy(legacy)):
            return C.official(gates.OUTPUT_ROOT/'ci01',report,None,actual,b'',reference,payloads,self.native,self.np)

    def test_tolerated_official_difference_and_same_live_exact_pass(self):
        result=self.invoke(self.fixture())
        self.assertIs(result['official_observed_node_pass'],True)
        self.assertIs(result['legacy_cross_oracle_contract_pass'],False)
        self.assertIs(result['official_kv_comparison']['official_kv_exact_copy'],False)
        self.assertIs(result['same_run_cache_comparison']['same_live_exact_copy'],True)
        self.assertNotIn('passed',result['same_run_cache_comparison'])
        self.assertTrue(all(row['official_numeric_pass'] for row in result['same_run_cache_original_comparisons'].values()))

    def test_final_kv_subspan_not_producer_substitution(self):
        fixture=self.fixture();report,actual,_,_,_=fixture
        actual['kv'][0]=0x3b800000
        # Even internally consistent changed final artifact cannot rewrite the
        # original admitted pc9 append commitment or use intact K/V as readback.
        report['sealed_actual_outputs']['kv']['sha256']=hashlib.sha256(actual['kv'].tobytes()).hexdigest()
        with self.assertRaises(ValueError):self.invoke(fixture)

    def test_same_run_identity_and_full_ack_required(self):
        for mutate in (lambda r:r['same_live_identity_final'].update(synthetic=8),
            lambda r:r['kv_append'].update(coverage_64b_beats=4095),
            lambda r:r['kv_append']['job'].update(a=999),lambda r:r['kv_append']['job'].update(write_bytes=262080),
            lambda r:r['producers'][0].update(ack_bytes=131008)):
            fixture=self.fixture();mutate(fixture[0])
            with self.assertRaises(ValueError):self.invoke(fixture)

    def test_original_fp64_mean_boundary_remains_failure(self):
        np=self.np
        small=[662700032,671088640,687865856,696254464,713031680,721420288,
               729808896,738197504,771751936,788529152,830472192,838860800,
               847249408,864026624,880803840,889192448,897581056,905969664,
               939524096,956301312,998244352,1006632960,1015021568]
        error=np.array([0]*27503+small+[1023410176]*5242,dtype='<u4').view('<f4')
        np.random.default_rng(3).shuffle(error)
        result=self.invoke(self.fixture(error.tobytes()))
        for row in result['same_run_cache_original_comparisons'].values():
            self.assertEqual(row['metrics']['max_abs'],0.03125)
            self.assertEqual(row['metrics']['mean_abs'],0.005000000000000001)
            self.assertIs(row['official_numeric_pass'],False)
        self.assertIs(result['official_observed_node_pass'],False)

    def test_original_signed_zero_bit_semantics_retained(self):
        np=self.np
        result=self.invoke(self.fixture(np.full(32768,-0.,dtype='<f4').tobytes()))
        for row in result['same_run_cache_original_comparisons'].values():
            self.assertEqual(row['metrics']['different_elements'],32768)
            self.assertIs(row['metrics']['bit_exact'],False)
            self.assertEqual(row['metrics']['mean_abs'],0.)

    def test_original_node_fail_cannot_be_hidden(self):
        for field,names in C.GROUPS:
            for name in names:
                fixture=self.fixture();fixture[-1][field][name]['official_numeric_pass']=False
                self.assertIs(self.invoke(fixture)['official_observed_node_pass'],False)

if __name__=='__main__':unittest.main()
