"""Tiny in-memory description tests. No build, network, files, or native loading."""
import copy
import json
import unittest
from unittest.mock import patch
import matrix_icg as recipe

class ContractTests(unittest.TestCase):
    def setUp(self): self.d = recipe.describe()
    def rejects(self, edit):
        edit(self.d)
        with self.assertRaises(ValueError): recipe.validate(self.d)
    def test_json_and_no_authority(self):
        self.assertEqual(json.loads(json.dumps(self.d)),self.d)
        self.assertFalse(self.d['execution_authority'])
        self.assertTrue(self.d['unresolved_prerequisites'])
    def test_no_io(self):
        with patch('builtins.open',side_effect=AssertionError('IO forbidden')):
            self.assertTrue(recipe.validate(recipe.describe()))
    def test_copy_isolation(self):
        self.d['generated_contract']['unit_names']['matrix'].clear()
        self.assertEqual(len(recipe.describe()['generated_contract']['unit_names']['matrix']),193)
    def test_duplicate_unit(self):
        self.rejects(lambda d:d['generated_contract']['unit_names']['matrix'].__setitem__(1,d['generated_contract']['unit_names']['matrix'][0]))
    def test_order(self):
        self.rejects(lambda d:d['generated_contract']['unit_names']['icg'].reverse())
    def test_missing_unit(self):
        self.rejects(lambda d:d['generated_contract']['unit_names']['icg'].pop())
    def test_bad_provider_digest(self):
        self.rejects(lambda d:d['generated_contract']['provider_files'].__setitem__('tc_clk.sv','0'*64))
    def test_duplicate_provider_basename(self):
        self.rejects(lambda d:d['generated_contract']['filelist_order']['matrix'].__setitem__(1,d['generated_contract']['filelist_order']['matrix'][0]))
    def test_unknown_provider(self):
        self.rejects(lambda d:d['generated_contract']['provider_files'].__setitem__('extra.sv','0'*64))
    def test_partial_fma(self):
        self.rejects(lambda d:d['generated_contract']['fma']['modules'].pop())
    def test_wrong_header(self):
        self.rejects(lambda d:d['generated_contract']['headers']['matrix'].__setitem__('Vqwen2_matrix_command_endpoint.h','0'*64))
    def test_duplicate_output_role(self):
        self.rejects(lambda d:d['stages'][1]['outputs'].__setitem__(0,d['stages'][0]['outputs'][0]))
    def test_duplicate_output_path(self):
        stages=[s for s in self.d['stages'] if '-o' in s['argv']]
        out=stages[0]['argv'][stages[0]['argv'].index('-o')+1]
        stages[1]['argv'][stages[1]['argv'].index('-o')+1]=out
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_duplicate_source(self):
        self.rejects(lambda d:d['inputs'].append(copy.deepcopy(d['inputs'][0])))
    def test_path_escape(self):
        self.rejects(lambda d:d['inputs'][0].__setitem__('path','../escape'))
    def test_placeholder(self):
        self.rejects(lambda d:d['stages'][0]['argv'].append('{tool:unbound}'))
    def test_unchanged_4096(self):
        self.rejects(lambda d:d['generated_contract']['ABI'].__setitem__('MACs_per_instance',64))
    def test_abi(self):
        self.rejects(lambda d:d['generated_contract']['ABI'].__setitem__('matrix_output_words',1))
    def test_unknown_type(self):
        with self.assertRaises(ValueError):recipe.verify_supplied_generated_units('new',[])
    def test_provider_bytes_fail_closed(self):
        with self.assertRaises(ValueError):recipe.verify_supplied_provider_bytes({k:b'' for k in self.d['generated_contract']['provider_files']})
    def test_unit_identity_api(self):
        for kind in ('matrix','icg'):
            self.assertTrue(recipe.verify_supplied_generated_units(kind,self.d['generated_contract']['unit_names'][kind]))
    def test_no_added_math_or_pch_flags(self):
        for s in self.d['stages']:
            self.assertFalse(any(x in s['argv'] for x in ['-ffast-math','--build','--binary','-march=native','-include-pch']))
            if '_compile_' in s['id']:self.assertNotIn('-std=c++17',s['argv'])
    def test_literal_relative_rpath(self):
        r=[s for s in self.d['stages'] if s['id'].endswith('_cabi_runner')]
        self.assertEqual(len(r),2)
        self.assertTrue(all('-Wl,-rpath,$ORIGIN/../lib' in s['argv'] for s in r))
    def test_archive_order(self):
        for kind in ('matrix','icg'):
            s=next(s for s in self.d['stages'] if s['id']=='matrix_icg.'+kind+'_archive')
            self.assertEqual([x.rsplit('/',1)[-1][:-2]+'.cpp' for x in s['argv'][3:]],self.d['generated_contract']['unit_names'][kind])
    def stage(self, suffix):
        return next(s for s in self.d['stages'] if s['id']=='matrix_icg.'+suffix)
    def test_changed_top_argv(self):
        s=self.stage('matrix_generate');s['argv'][s['argv'].index('--top-module')+1]='other'
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_changed_seed_argv(self):
        s=self.stage('matrix_generate');s['argv'][s['argv'].index("-GENABLE_ACCUMULATOR_SEED=1'b1")]="-GENABLE_ACCUMULATOR_SEED=1'b0"
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_changed_icg_argv(self):
        s=self.stage('icg_generate');s['argv'][s['argv'].index("-GIS_FUNCTIONAL=1'b1")]="-GIS_FUNCTIONAL=1'b0"
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_changed_compile_options(self):
        self.stage('matrix_compile_0')['argv'][1]='-O3'
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_changed_compile_contract(self):
        self.rejects(lambda d:d['generated_contract']['generated_compile_flags'].append('-ffast-math'))
    def test_changed_source_hash(self):
        self.rejects(lambda d:d['inputs'][0].__setitem__('sha256','1'*64))
    def test_changed_valid_source_path(self):
        self.rejects(lambda d:d['inputs'][0].__setitem__('path','other/source.py'))
    def test_absolute_source(self):
        self.rejects(lambda d:d['inputs'][0].__setitem__('path','/source.py'))
    def test_build_cwd_escape(self):
        self.rejects(lambda d:d['stages'][0].__setitem__('cwd','{build}/../outside'))
    def test_repo_output(self):
        s=self.stage('matrix_compile_0');s['argv'][s['argv'].index('-o')+1]='{repo}/object.o'
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_output_traversal(self):
        s=self.stage('matrix_compile_0');s['argv'][s['argv'].index('-o')+1]='{build}/../object.o'
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_omitted_provider_dependency(self):
        self.stage('providers')['inputs'].remove('matrix.compose_assets')
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_forward_input(self):
        self.stage('providers')['inputs'].append('matrix_icg.icg_library')
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_unknown_input(self):
        self.stage('providers')['inputs'].append('unbound')
        with self.assertRaises(ValueError):recipe.validate(self.d)
    def test_empty_preconditions(self):
        self.rejects(lambda d:d['stages'][0]['preconditions'].clear())
    def test_deleted_tool_provenance(self):
        self.rejects(lambda d:d['tools'][0].pop('prior_binary_sha256'))
    def test_malformed_placeholder(self):
        self.rejects(lambda d:d['stages'][0]['argv'].__setitem__(0,'{tool:python'))
    def test_all_fixed_abi_fields(self):
        for field,new in [('matrix_seed',False),('icg_functional',False),('matrix_top','other'),('icg_top','other')]:
            with self.subTest(field=field):
                d=recipe.describe();d['generated_contract']['ABI'][field]=new
                with self.assertRaises(ValueError):recipe.validate(d)
    def test_bool_is_not_integer(self):
        self.rejects(lambda d:d.__setitem__('execution_authority',0))
    def test_no_extra_claim(self):
        self.rejects(lambda d:d.__setitem__('portable_build_passed',True))
    def test_artifact_descriptor_required(self):
        self.rejects(lambda d:d['artifacts'].pop('verilator_root'))
    def test_aggregate_roles_required(self):
        self.rejects(lambda d:d['artifacts'].pop('matrix.compose_assets'))
    def test_artifact_readiness_cannot_be_promoted(self):
        self.rejects(lambda d:d['artifacts']['matrix_icg.original162'].__setitem__('verified',True))
    def test_aggregate_member_change(self):
        self.rejects(lambda d:d['aggregate_roles']['matrix.compose_assets'].pop())
    def test_source_list_requires_provider(self):
        self.rejects(lambda d:d['prerequisite_roles']['matrix_icg.matrix_source_list']['requires'].clear())
    def test_unresolved_tool_identity_is_fixed(self):
        java=next(t for t in self.d['tools'] if t['id']=='java')
        self.assertEqual(java['identity_status'],'UNRESOLVED')
        java.pop('identity_prerequisite')
        with self.assertRaises(ValueError):recipe.validate(self.d)
if __name__=='__main__':unittest.main()
