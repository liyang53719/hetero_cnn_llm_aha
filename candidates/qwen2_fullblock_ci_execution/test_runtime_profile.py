"""Pure cold profile tests: no native/runtime/model execution."""
import copy
import json
import unittest
from unittest.mock import patch
from candidates.qwen2_fullblock_ci_execution import runtime_profile as p


class RuntimeProfileTests(unittest.TestCase):
    def pins(self):
        return {'capture_environment':{'ATEN_CPU_CAPABILITY':None,'OMP_NUM_THREADS':'4',
                                      'MKL_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1'},
                'runtime_requirements':{'capability':'AVX512','torch_build_sha256':'a'*64,
                                        'threads':4,'numpy':'2.3.5','nested':[1,{'x':2}]},
                'other':{'sources':['unchanged'],'numeric_pass':False}}

    def candidate(self):
        return {p.PROFILE_ENV:p.CANDIDATE,'ATEN_CPU_CAPABILITY':'avx2'}

    def aten_gemm_candidate(self):
        return {p.PROFILE_ENV:p.ATEN_GEMM_CANDIDATE,'ATEN_CPU_CAPABILITY':'avx2'}

    def test_distinct_explicit_backend_request_default_unchanged(self):
        self.assertIsNone(p.mkldnn_enabled({}))
        self.assertIsNone(p.mkldnn_enabled(self.candidate()))
        self.assertIs(p.mkldnn_enabled(self.aten_gemm_candidate()),False)
        self.assertIs(p.disable_mkldnn({}),False)
        self.assertIs(p.disable_mkldnn(self.candidate()),False)
        self.assertIs(p.disable_mkldnn(self.aten_gemm_candidate()),True)
        self.assertIs(p.selected(self.aten_gemm_candidate()),True)
        self.assertEqual(p.profile(self.aten_gemm_candidate()),'avx2-aten-gemm-v1')

    def test_new_backend_profile_same_three_pin_fields_only(self):
        pins=self.pins();before=copy.deepcopy(pins);env=self.aten_gemm_candidate();env_before=dict(env)
        result=p.apply(pins,env)
        self.assertEqual(result,p.apply(pins,self.candidate()))
        self.assertEqual(pins,before);self.assertEqual(env,env_before)
        self.assertEqual(set(result),set(pins))
        self.assertEqual(set(result['capture_environment']),set(pins['capture_environment']))
        self.assertEqual(set(result['runtime_requirements']),set(pins['runtime_requirements']))

    def test_backend_request_strict_validation_no_auto_selection(self):
        for env in ({'ATEN_CPU_CAPABILITY':'avx2'},
                    {p.PROFILE_ENV:p.ATEN_GEMM_CANDIDATE},
                    {p.PROFILE_ENV:p.ATEN_GEMM_CANDIDATE,'ATEN_CPU_CAPABILITY':'AVX2'},
                    {p.PROFILE_ENV:'avx2-aten-gemm-v2','ATEN_CPU_CAPABILITY':'avx2'}):
            with self.subTest(env=env),self.assertRaises(ValueError):p.disable_mkldnn(env)

    def test_new_profile_rejects_all_present_backend_overrides(self):
        for key in ('ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
            for value in ('',None,'AVX2','AUTO',False):
                env={**self.aten_gemm_candidate(),key:value}
                for action in (p.profile,p.selected,p.disable_mkldnn,p.mkldnn_enabled):
                    with self.subTest(key=key,value=value,action=action.__name__),self.assertRaises(ValueError):
                        action(env)
                with self.assertRaises(ValueError):p.apply(self.pins(),env)

    def test_backend_override_rejection_does_not_change_old_profiles(self):
        for env in ({},self.candidate()):
            for key in ('ONEDNN_MAX_CPU_ISA','DNNL_MAX_CPU_ISA','MKL_CBWR'):
                for value in ('',None,'AVX2'):
                    self.assertEqual(p.apply(self.pins(),{**env,key:value}),p.apply(self.pins(),env))
                    self.assertIsNone(p.mkldnn_enabled({**env,key:value}))

    def test_selected_boolean_and_strict_validation(self):
        self.assertIs(p.selected({}),False)
        self.assertIs(p.selected(self.candidate()),True)
        with self.assertRaises(ValueError):p.selected({'ATEN_CPU_CAPABILITY':'avx2'})
        with self.assertRaises(ValueError):p.selected({p.PROFILE_ENV:'unknown'})

    def test_default_semantics_and_serialized_bytes_unchanged(self):
        pins=self.pins();before=json.dumps(pins,sort_keys=True).encode()
        result=p.apply(pins,environ={})
        self.assertEqual(json.dumps(result,sort_keys=True).encode(),before)
        self.assertEqual(json.dumps(pins,sort_keys=True).encode(),before)
        self.assertIsNot(result,pins)
        self.assertIsNone(p.profile({}))

    def test_deep_copy_default_and_candidate(self):
        for env in ({},self.candidate(),self.aten_gemm_candidate()):
            pins=self.pins();before=copy.deepcopy(pins);result=p.apply(pins,environ=env)
            result['runtime_requirements']['nested'][1]['x']=999
            result['other']['sources'].append('new')
            self.assertEqual(pins,before)

    def test_candidate_exactly_three_leaf_changes(self):
        pins=self.pins();before=copy.deepcopy(pins);env=self.candidate();env_before=dict(env)
        actual=p.apply(pins,environ=env);expected=copy.deepcopy(pins)
        expected['capture_environment']['ATEN_CPU_CAPABILITY']='avx2'
        expected['runtime_requirements']['capability']='AVX2'
        expected['runtime_requirements']['torch_build_sha256']='4096ae2ff210db4a4da17fe7e5ef17c7715c4e4dc5d4175a9357b83bf820075a'
        self.assertEqual(actual,expected);self.assertEqual(pins,before);self.assertEqual(env,env_before)
        self.assertEqual(p.profile(env),p.CANDIDATE)

    def test_default_rejects_any_set_aten_value(self):
        for value in ('','avx2','avx512','AVX512','default','0',False,0):
            with self.subTest(value=value),self.assertRaises(ValueError):
                p.apply(self.pins(),environ={'ATEN_CPU_CAPABILITY':value})

    def test_candidate_requires_exact_lowercase_aten(self):
        for value in (None,'','AVX2','avx512',' avx2','avx2 ',False,0):
            with self.subTest(value=value),self.assertRaises(ValueError):
                p.apply(self.pins(),environ={p.PROFILE_ENV:p.CANDIDATE,'ATEN_CPU_CAPABILITY':value})
        with self.assertRaises(ValueError):p.apply(self.pins(),environ={p.PROFILE_ENV:p.CANDIDATE})

    def test_unknown_profile_never_inferred_or_ignored(self):
        for value in ('','default','AVX2','avx2-candidate-v2',' avx2-candidate-v1',False,0,[],{}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                p.apply(self.pins(),environ={p.PROFILE_ENV:value,'ATEN_CPU_CAPABILITY':'avx2'})

    def test_reads_current_environment_without_writes(self):
        for env in ({},self.candidate(),self.aten_gemm_candidate()):
            with patch.dict(p.os.environ,env,clear=True):
                before=dict(p.os.environ)
                self.assertEqual(p.apply(self.pins()),p.apply(self.pins(),environ=env))
                self.assertEqual(dict(p.os.environ),before)

    def test_invalid_selection_does_not_copy_or_touch_pins(self):
        with patch.object(p.copy,'deepcopy',side_effect=AssertionError('pins touched')):
            with self.assertRaises(ValueError):p.apply(object(),environ={p.PROFILE_ENV:'unknown'})

    def test_missing_candidate_fields_rejected_no_mutation(self):
        for group,key in (('capture_environment','ATEN_CPU_CAPABILITY'),
                          ('runtime_requirements','capability'),('runtime_requirements','torch_build_sha256')):
            pins=self.pins();del pins[group][key];before=copy.deepcopy(pins)
            with self.assertRaises(ValueError):p.apply(pins,environ=self.candidate())
            self.assertEqual(pins,before)


if __name__=='__main__':unittest.main()
