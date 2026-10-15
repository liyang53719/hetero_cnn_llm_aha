"""Pure synthetic metadata tests; no capture, Torch, payloads, or approval issuance."""
import copy
import unittest
from unittest.mock import patch
from . import policy as P
from . import validator as V


class ValidatorTests(unittest.TestCase):
    def fixture(self):
        raw=(V.ROOT/P.ORIGINAL_PINS).read_bytes();pins=P.original(raw)
        source='a'*64
        cert={'synthetic_opaque_commitment':True}  # issuer tests own actual admission schema
        cert_raw=P.encoded(cert);cert_sha=P.sha(cert_raw)
        identity=dict(bytes=1,sha256='b'*64)
        python=dict(path=str(V.F.PYTHON_HOME/'bin/python3.12'),**V.F.PYTHON_IDENTITY,device=1,inode=2)
        platform=dict(schema=1,status='CURRENT_PROCESS_PLATFORM_OBSERVED_ONLY',scope='PYTHON_ELF_AND_LOADED_LIBPYTHON_ONLY',
            python_version=[3,12,14],process_id=1,python=python,
            libpython=dict(path=str(V.F.LIBPYTHON),**identity,device=1,inode=3),independently_reviewed=False,
            historical_equivalence_claimed=False,full_system_closure=False,numeric_execution_allowed=False)
        native=copy.deepcopy(pins['runtime_native_files']);native['python']={k:python[k] for k in ('path','bytes','sha256')}
        boundary=dict(external_certificate_sha256=cert_sha,source_closure_sha256=source,
            source_manifest=dict(identity),pins=dict(identity),effective_pins_sha256='c'*64,
            sources={'synthetic_source':dict(identity)},raw13={P.RAW_ROOTS[s['manifest_role']]+'/'+s['local_name']+'.bin':{k:s[k] for k in ('bytes','sha256')} for s in pins['raw_tensors']},
            native_files=native,input_proofs={'synthetic_proof':dict(identity)},raw_support={},historical_receipts_revalidated=False)
        boundary['platform_files']={k:platform[k] for k in ('python','libpython')}
        outputs={}
        for name,geometry in P.geometry(raw).items():
            outputs[name]={**geometry,'native_stride':[1]*len(geometry['shape']),'storage_offset':0,'is_contiguous':True,
                'sha256':'d'*64,'native_sha256':'e'*64,'token_major_sha256':'f'*64,'file':name+'.f32le'}
        backend=dict(profile=P.PROFILE,mkldnn_enabled=False,threads=4,interop_threads=1,deterministic_algorithms=True)
        observation=dict(schema=1,run_id='new01',source_closure_sha256=source,boundary_before=boundary,boundary_after=copy.deepcopy(boundary),
            platform_before=platform,platform_after=copy.deepcopy(platform),
            runtime=V.PROFILE.apply(pins,{V.PROFILE.PROFILE_ENV:P.PROFILE,'ATEN_CPU_CAPABILITY':'avx2'})['runtime_requirements'],
            backend_before=backend,backend_after=copy.deepcopy(backend),
            typed_inputs={n:{k:s[k] for k in ('bytes','sha256')} for n,s in pins['producer_roles'].items()},outputs=outputs,
            legacy_comparison=dict(schema=1,status='CI_REFERENCE_ALL_COMPARISONS',scope='EXISTING_OUTPUTS_ONLY',
                compared_count=29,numeric_acceptance_claimed=False,
                records=[dict(node=node,categories=['HASH'],mismatch_count=3) for node in V.A.NODES]))
        return observation,cert_raw,dict(expected_certificate_sha256=cert_sha,expected_source_sha256=source)

    def validate(self,observation,cert,kwargs):
        with patch.object(V,'source_digest',return_value='a'*64) as source:
            result=V.validate(observation,cert,**kwargs)
            source.assert_called_once_with(V.ROOT)
            return result

    def test_new_hashes_and_old_mismatches_remain_pending(self):
        observation,cert,kwargs=self.fixture();result=self.validate(observation,cert,kwargs)
        self.assertEqual(result['status'],'VALIDATED_LOCAL_PENDING_REVIEW')
        for key in ('reference_freeze_available','dut_authorized','numerical_acceptance_claimed','source_authority_verified'):
            self.assertIs(result[key],False)
        self.assertNotIn('outputs',result)

    def test_missing_wrong_external_digest_and_changed_source_reject(self):
        observation,cert,kwargs=self.fixture()
        with self.assertRaises(TypeError):V.validate(observation,cert)
        with self.assertRaises(ValueError):self.validate(observation,cert+b' ',kwargs)
        with patch.object(V,'source_digest',return_value='9'*64):
            with self.assertRaises(ValueError):V.validate(observation,cert,**kwargs)

    def test_boundary_profile_platform_and_input_drift_reject(self):
        paths=[('backend_after','mkldnn_enabled'),('backend_before','threads'),
            ('boundary_after','effective_pins_sha256'),('platform_after','process_id'),
            ('runtime','capability')]
        for outer,key in paths:
            observation,cert,kwargs=self.fixture();observation[outer][key]='changed'
            with self.subTest(outer=outer),self.assertRaises(ValueError):self.validate(observation,cert,kwargs)
        for field in ('typed_inputs','outputs'):
            observation,cert,kwargs=self.fixture();observation[field].pop(next(iter(observation[field])))
            with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)
        observation,cert,kwargs=self.fixture();observation['typed_inputs']['x']['sha256']='0'*64
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)

    def test_geometry_cannot_be_rebased_to_observation(self):
        observation,cert,kwargs=self.fixture();observation['outputs']['q']['shape']=[1,1,1,1]
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)
        observation,cert,kwargs=self.fixture();observation['outputs']['q']['extra']='private'
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)

    def test_local_python_cannot_replace_fixed_ci_identity(self):
        observation,cert,kwargs=self.fixture()
        for boundary in ('platform_before','platform_after'):
            observation[boundary]['python']['path']='/opt/local/python'
            observation[boundary]['python']['bytes']=30894944
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)

    def test_raw_name_rebinding_and_python_alias_reject(self):
        observation,cert,kwargs=self.fixture()
        for edge in ('boundary_before','boundary_after'):
            values=observation[edge]['raw13'];values['arbitrary/path']=values.pop(next(iter(values)))
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)
        observation,cert,kwargs=self.fixture()
        for edge in ('platform_before','platform_after'):
            observation[edge]['python']['path']=str(V.F.PYTHON_HOME)+'/bin/../bin/python3.12'
        with self.assertRaises(ValueError):self.validate(observation,cert,kwargs)

    def test_platform_calls_delegate_without_new_framework(self):
        with patch.object(V.F,'observe',return_value={'status':'NOT_EXECUTED'}) as observe:
            self.assertEqual(V.observe_platform_before(),{'status':'NOT_EXECUTED'})
            observe.assert_called_once_with(execute=False)
        with patch.object(V.F,'verify_same',return_value={}) as verify:
            V.observe_platform_after({'synthetic':True});verify.assert_called_once_with({'synthetic':True})

    def test_platform_audit_read_set_is_exact_not_directory_permission(self):
        identity=dict(path=str(V.F.PYTHON_HOME/'bin/python3.12'),**V.F.PYTHON_IDENTITY)
        paths=V.platform_read_paths(identity)
        self.assertEqual(paths,(identity['path'],str(V.F.LIBPYTHON),'/proc/self/maps'))
        self.assertNotIn(str(V.F.PYTHON_HOME),paths)
        with self.assertRaises(ValueError):V.platform_read_paths({**identity,'path':'/opt/local/python'})

    def test_policy_is_pending_and_does_not_embed_reference_outputs(self):
        policy=P.policy();self.assertIn('PENDING',policy['status'])
        self.assertFalse(policy['reference_freeze_available']);self.assertFalse(policy['dut_authorized'])
        self.assertNotIn('outputs',policy);self.assertNotIn('prior18_expectations',policy)
        with self.assertRaises(ValueError):P.geometry(b'{}')

if __name__=='__main__':unittest.main()
