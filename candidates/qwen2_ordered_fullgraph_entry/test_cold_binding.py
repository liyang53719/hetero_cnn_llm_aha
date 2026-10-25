"""Preparation checks only; no actual cold target import."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import cold_binding as cold
if Path(cold.__file__).resolve()!=HERE/'cold_binding.py':raise RuntimeError('foreign cold_binding')

class ColdPreparation(unittest.TestCase):
    def test_changed_config_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.json';p.write_text('{}')
            expected=cold.sha(p);p.write_text('{} ');out=Path(tmp)/'out'
            with self.assertRaisesRegex(ValueError,'config hash'):
                cold.main(['--config',str(p),'--config-sha',expected,'--output',str(out)])
            self.assertFalse(out.exists())
    def test_exact_initializer_set(self):
        self.assertEqual(len(cold.INITIALIZERS),4)
        self.assertEqual(set(cold.INITIALIZERS.values()),{'load_module','_pinned_module'})
    def test_profile_is_data_constant(self):
        self.assertEqual(cold.PROFILE,'candidates/qwen2_resident_matrix/dense_block_reduce/profile.py')
    def test_no_dynamic_library_call(self):
        tree=ast.parse((HERE/'cold_binding.py').read_text())
        calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertNotIn('CDLL',calls);self.assertNotIn('configure_library',calls)
    def test_old_gate_reused(self):
        src=(HERE/'cold_binding.py').read_text()
        for value in ('cold.ColdGuard','cold.raw_modules','cold.collect_maps','inventory.collect_modules','cold.stop_task_profile'):
            self.assertIn(value,src)
    def test_complete_raw_before_validation(self):
        src=(HERE/'cold_binding.py').read_text()
        self.assertLess(src.index("target/'MODULES_RAW.json'"),src.index('mr=inventory.collect_modules'))
        self.assertLess(src.index("target/'MAPS.txt'"),src.index('mr=inventory.collect_modules'))
    def test_report_does_not_upgrade_numeric(self):
        src=(HERE/'cold_binding.py').read_text()
        self.assertIn("'fullgraph_acceptance':'TEMP_NOT_EXECUTED'",src)
        self.assertIn("'numeric_executed':False",src)

if __name__=='__main__':unittest.main()
