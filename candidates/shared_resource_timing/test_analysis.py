import copy,unittest
from .analyze_prefix import analyze,PHASES

def fixture():
    return dict(tokens=128,full_block=False,rtl_executed=False,sources_unchanged=True,native_artifacts_unchanged=True,execution=dict(full_qkv=True,output_columns=[dict(columns=8192,start=0)],terminals=[dict(stage=p,status=None) for p in PHASES],stages=[dict(stage=p,report=dict(counts=dict(read_bytes=640,write_bytes=64,ticks=22))) for p in PHASES],scalar_operations=dict(add=100,mul=20,mul_ieee_rne=10),matrix_service=dict(dense_fma_calls=4311744512,counters=dict(dense_steps=1052672))))
class AnalysisTests(unittest.TestCase):
    def test_prefix_bounds_never_full_block_or_measured(self):
        r=analyze(fixture());self.assertEqual(r['scalar_basic_II3_floor_span'],389);self.assertEqual(r['ddr_single_512bit_payload_floor_slots'],143)
        self.assertIsNone(r['full_block_cycles']);self.assertIsNone(r['full_block_mac_utilization']);self.assertIsNone(r['busy_duty']);self.assertFalse(r['rtl_measured'])
    def test_missing_terminal_phase_or_failed_result_rejected(self):
        for which in ('terminal','phase','failed','duplicate'):
            s=fixture()
            if which=='terminal':s['execution']['terminals'].pop()
            elif which=='phase':s['execution']['stages'].pop()
            elif which=='failed':s['execution']['terminals'][0]['status']='Memory'
            else:s['execution']['stages'][1]['stage']=PHASES[0]
            with self.assertRaises(ValueError):analyze(s)
    def test_no_m16_padding_or_negative_counts_silently_promoted(self):
        s=fixture();s['execution']['output_columns']=8160
        with self.assertRaises(ValueError):analyze(s)
        s=fixture();s['tokens']=16
        with self.assertRaises(ValueError):analyze(s)
        s=fixture();s['execution']['scalar_operations']['add']=-1
        with self.assertRaises(ValueError):analyze(s)
if __name__=='__main__':unittest.main()
