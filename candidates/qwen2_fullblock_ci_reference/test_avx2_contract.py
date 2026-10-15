"""The new candidate reaches the original numerical contract without native imports."""
import copy
import os
import unittest
from unittest.mock import patch
from .test_metadata import R

ENV={'QWEN2_CI_RUNTIME_PROFILE':'avx2-candidate-v1','ATEN_CPU_CAPABILITY':'avx2'}

class Avx2ContractTests(unittest.TestCase):
    def effective(self):
        with patch.object(R,'CI_ROOT',R.ROOT), patch.object(R,'observed_python',return_value={'path':'/test/python',**R.PYTHON_IDENTITY}):
            return R.runtime_pins()

    def test_original_rejects_candidate_but_exact_adapter_preserves_math_contract(self):
        with patch.dict(os.environ,ENV,clear=True), patch.object(R,'CI_ROOT',R.ROOT), \
             patch.object(R,'observed_python',return_value={'path':'/test/python',**R.PYTHON_IDENTITY}):
            pins=self.effective();before=copy.deepcopy(pins)
            with self.assertRaises(R.Rejected): R.O.check_contract(pins)
            R.check_contract(pins)
            self.assertEqual(pins,before)
            with patch.object(R,'source_manifest'),patch.object(R,'load_pins',return_value=pins), \
                 patch.object(R,'checked',side_effect=RuntimeError('passed contract and reached source read')):
                with self.assertRaisesRegex(RuntimeError,'passed contract'):
                    R.source_check(R.ROOT,pins)

    def test_runtime_environment_and_numerical_drift_rejected(self):
        with patch.dict(os.environ,ENV,clear=True), patch.object(R,'CI_ROOT',R.ROOT), \
             patch.object(R,'observed_python',return_value={'path':'/test/python',**R.PYTHON_IDENTITY}):
            base=self.effective()
            mutations=[('runtime_requirements',k,None) for k in base['runtime_requirements']]
            mutations += [('capture_environment',k,None) for k,v in base['capture_environment'].items() if v is not None]
            mutations += [('contract','rows',1),('contract','rms_norm_eps',1e-5),('capture_limits','wall_seconds',121)]
            for section,key,value in mutations:
                pins=copy.deepcopy(base);pins[section][key]=value
                with self.subTest(section=section,key=key),self.assertRaises(R.Rejected):R.check_contract(pins)

    def test_default_retains_original_validator(self):
        with patch.dict(os.environ,{},clear=True):
            pins=R.O.load_pins();R.check_contract(pins)
            pins['runtime_requirements']['capability']='AVX2'
            with self.assertRaises(R.Rejected):R.check_contract(pins)

if __name__=='__main__':unittest.main()
