import copy,json,pathlib,tempfile,unittest
import verify_bounds as v
class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.summary=v.read_json(v.HERE/'BOUNDS.json');self.inventory=v.read_json(v.HERE/'NATIVE_TENSOR_INVENTORY.json')
    def test_five_profile_summary(self):self.assertEqual(v.check_summary(self.summary,self.inventory)['profiles'],5)
    def test_bytes_tamper(self):
        self.inventory[0]['bytes']+=2
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_dtype_tamper(self):
        self.inventory[0]['dtype']='FP8'
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_active_tamper(self):
        self.summary['route_evidence']['3']['active_experts']=8
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_cycle_tamper(self):
        self.summary['profiles'][4]['current_single_beat_dma_cycle_lower_bound']-=1
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_inventory_duplicate(self):
        self.inventory[-1]=copy.deepcopy(self.inventory[0])
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_path_fail_closed(self):
        for s in ('/private/file','../file','candidates/../../file'):
            with self.assertRaises(ValueError):v.repo_relative(s)
    def test_source_sha_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);(p/'x').write_text('not pinned')
            pins={'runtime_sources':{},'constructor_helper':{'repo_path':'x','sha256':'0'*64}}
            with self.assertRaises(ValueError):v.check_sources(pins,p)
    def test_units(self):self.assertAlmostEqual(v.bounds(8002994176,1496658624)['required_GBps_at_1GHz']['0.9'],689.4022699728127)
    def test_claimed_measurement_rejected(self):
        self.summary['assumptions']['hardware_frequency_or_bandwidth_measured']=True
        with self.assertRaises(ValueError):v.check_summary(self.summary,self.inventory)
    def test_summary_scope(self):
        r=v.run();self.assertIn('SUMMARY_ARITHMETIC_ONLY',r['status']);self.assertFalse(r['hardware_executed']);self.assertFalse(r['fresh_header_validation'])
if __name__=='__main__':unittest.main()
