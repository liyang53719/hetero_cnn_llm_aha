"""Offline receipt/ZIP negative tests with explicitly synthetic public JSON."""
import copy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
import warnings
import zipfile

HERE=Path(__file__).resolve().parent

def load(name):
    path=HERE/(name+'.py');module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),module.__dict__);return module
V=load('verify_artifact');F=load('receipt_fixture')


class OfflineArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.base,cls.pins,cls.full=F.build(V)
    def setUp(self):self.values=copy.deepcopy(self.base)
    def check(self):
        raw=F.raws(V,self.values);values,chains=V.validate_receipts(raw,self.values['summary.json']['ci'],self.pins)
        V.validate_provenance(values,raw,chains,self.full);return values,chains
    def reject(self,fn):
        fn()
        with self.assertRaises((V.VerificationError,KeyError,TypeError)):self.check()
    def test_01_receipt_and_provenance_positive(self):self.assertEqual(set(self.check()[1]),{'16','128'})
    def test_02_orphan_artifact_not_ready(self):self.reject(lambda:self.values['summary.json'].update(replay_identity_ready=False))
    def test_03_failure_after_numerical_pass(self):self.reject(lambda:self.values['summary.json'].update(status='FAILED_SAME_HOST_M128_ATTEMPT',phase='replay_identity_finalize',replay_identity_failure={'phase':'replay_identity_finalize','error_class':'TimeoutError','code':'UNKNOWN'}))
    def test_04_manifest_hash_drift(self):self.reject(lambda:self.values['replay_identity.json']['provenance'].update(producer_context_sha256='9'*64))
    def test_05_wrong_commit(self):self.reject(lambda:self.values['full_m128_summary.json']['ci'].update(commit='0'*40))
    def test_06_wrong_nonce(self):self.reject(lambda:self.values['full_m16_summary.json'].update(attempt_nonce='0'*64))
    def test_07_private_public_receipt_confusion(self):self.reject(lambda:self.values['producer_summary.json'].update(producer_qualification_sha256=V.sha(V.encoded(self.values['producer_summary.json']))))
    def test_08_wrong_child_hash(self):self.reject(lambda:self.values['full_m128_summary.json'].update(child_result_sha256='0'*64))
    def test_09_wrong_source_map(self):self.reject(lambda:self.values['source_hashes.json']['inputs'].update({'forged.py':'0'*64}))
    def test_10_wrong_static_source(self):self.reject(lambda:self.values['source_hashes.json']['composed_sources_template'].pop(next(iter(self.values['source_hashes.json']['composed_sources_template']))))
    def test_11_bool_exit_rejected(self):self.reject(lambda:self.values['stage_exits.json']['stages'][-1].update(final_exit_code=False))
    def test_12_wrong_phase_order(self):self.reject(lambda:self.values['stage_exits.json']['stages'].reverse())
    def test_13_unavailable_timing_allowed(self):
        event=self.values['stage_exits.json']['stages'][-1];event['timing_diagnostic'].update(status='UNAVAILABLE',reason='MEASUREMENT_UNAVAILABLE',wall_seconds=None,reaped_children_user_cpu_seconds=None,reaped_children_system_cpu_seconds=None);self.check()
    def test_14_timing_no_acceptance(self):self.reject(lambda:self.values['stage_exits.json']['stages'][-1]['timing_diagnostic'].update(acceptance=True))
    def test_15_timing_negative(self):self.reject(lambda:self.values['stage_exits.json']['stages'][-1]['timing_diagnostic'].update(wall_seconds=-1))
    def test_16_full29_rejected(self):self.reject(lambda:self.values['full_m128_summary.json']['validation'].update(full_29_node_acceptance=True))
    def test_17_provenance_rebound_but_wrong(self):
        m=self.values['replay_identity.json'];m['provenance']['m128_full_receipt_sha256']='0'*64;self.values['summary.json']['replay_identity_sha256']=V.sha(V.encoded(m))
        with self.assertRaises(V.VerificationError):self.check()
    def test_18_extra_summary_fields(self):self.reject(lambda:self.values['summary.json'].update(private_path='/private/no'))
    def test_19_stage_cleanup_false(self):self.reject(lambda:self.values['stage_exits.json']['stages'][-1].update(owned_group_cleanup_complete=False))
    def test_20_stage_pid_binding(self):self.reject(lambda:self.values['stage_exits.json']['stages'][-1].update(pid=999))
    def test_21_canonical_receipt(self):
        raw=F.raws(V,self.values);raw['summary.json']=json.dumps(self.values['summary.json'],indent=2).encode()
        with self.assertRaises(V.VerificationError):V.validate_receipts(raw,self.values['summary.json']['ci'],self.pins)
    def test_22_strict_json(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b'\xff',b'['*1100):
            with self.subTest(raw=raw[:24]),self.assertRaises(V.VerificationError):V.strict(raw)
    def test_23_json_size(self):
        with self.assertRaises(V.VerificationError):V.strict(b' '*(V.MAX_MEMBER+1))
    def test_24_zip_exact_positive(self):
        raw=F.raws(V,self.values);self.assertEqual(V.zip_members(F.archive(raw)),raw)
    def test_25_zip_wrong_members(self):
        for name in ('../summary.json','extra.json','/absolute.json'):
            raw=F.raws(V,self.values);raw[name]=raw.pop('summary.json')
            with self.subTest(name=name),self.assertRaises(V.VerificationError):V.zip_members(F.archive(raw))
    def test_26_duplicate_zip(self):
        target=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(target,'w') as z:
                for name,raw in F.raws(V,self.values).items():z.writestr(name,raw)
                z.writestr('summary.json',b'{}')
        with self.assertRaises(V.VerificationError):V.zip_members(target.getvalue())
    def test_27_zip_symlink(self):
        target=io.BytesIO()
        with zipfile.ZipFile(target,'w') as z:
            for name,raw in F.raws(V,self.values).items():
                info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=((stat.S_IFLNK|0o777) if name=='summary.json' else (stat.S_IFREG|0o600))<<16;z.writestr(info,raw)
        with self.assertRaises(V.VerificationError):V.zip_members(target.getvalue())
    def test_28_zip_oversize(self):
        raw=F.raws(V,self.values);raw['summary.json']=b'x'*(V.MAX_MEMBER+1)
        with self.assertRaises(V.VerificationError):V.zip_members(F.archive(raw))
    def test_29_file_alias(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'real').write_bytes(b'{}');(p/'link').symlink_to(p/'real')
            with self.assertRaises(V.VerificationError):V.read_safe(p/'link')
    def test_30_bad_artifact_digest(self):
        raw=F.archive(F.raws(V,self.values))
        with self.assertRaisesRegex(V.VerificationError,'ARTIFACT_SHA'):V.verify(raw,artifact_sha256='0'*64,ci=self.values['summary.json']['ci'],freeze=F.FREEZE)
    def test_31_old_attempt_rejected(self):
        ci=dict(self.values['summary.json']['ci'],run_attempt='2')
        with self.assertRaisesRegex(V.VerificationError,'CI_VALUES'):V.verify(b'',artifact_sha256=V.sha(b''),ci=ci,freeze=F.FREEZE)
    def test_32_source_read_pin(self):
        full,pins=V.load_sources(F.FREEZE);self.assertEqual(full,self.full);self.assertEqual(len(pins[128]['inputs']),464)

    def test_33_wrong_actual_run(self):
        ci=dict(self.values['summary.json']['ci'],run_id='39012470402')
        with self.assertRaisesRegex(V.VerificationError,'CI_VALUES'):V.verify(b'',artifact_sha256=V.sha(b''),ci=ci,freeze=F.FREEZE)
    def test_34_unsupported_zip_codec(self):
        target=io.BytesIO()
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_BZIP2) as z:
            for name,raw in F.raws(V,self.values).items():z.writestr(name,raw)
        with self.assertRaisesRegex(V.VerificationError,'ZIP_MEMBER_TYPE_SIZE'):V.zip_members(target.getvalue())

    def test_35_resource_floors(self):
        for receipt,field in (('summary.json','resources_before_setup'),('m16_attempt_summary.json','resources_before_setup'),('m16_attempt_summary.json','resources_after_setup')):
            for key,value in (('cpu_affinity',3),('available_memory_bytes',8*1024**3-1),('available_disk_bytes',8*1024**3-1),('cpu_affinity',True)):
                self.values=copy.deepcopy(self.base);self.values[receipt][field][key]=value
                with self.subTest(receipt=receipt,field=field,key=key,value=value),self.assertRaisesRegex(V.VerificationError,'RESOURCE_VALUES'):self.check()

class CompleteSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S=load('identity_schema');sys.modules['identity_schema']=cls.S
        cls.T=load('test_fixture')
        full,pins=V.load_sources(F.FREEZE)
        cls.compiled=V.derive_compile_sources(F.FREEZE,full,pins)
        cls.base,cls.pins,cls.full=F.build(V,cls.T.build_manifest(pins[128]['inputs'],compile_sources=cls.compiled))
    def setUp(self):self.values=copy.deepcopy(self.base)
    def check(self):
        raws=F.raws(V,self.values);values,chains=V.validate_receipts(raws,self.values['summary.json']['ci'],self.pins)
        inventory=self.S.validate_manifest(values['replay_identity.json'],self.pins[128]['inputs'],compile_sources=self.compiled)
        V.validate_provenance(values,raws,chains,self.full);return inventory
    def rebind(self):
        m=self.values['replay_identity.json'];m['identity_sha256']=V.sha(V.encoded(m['identity']))
        self.values['summary.json']['replay_identity_sha256']=V.sha(V.encoded(m))
    def test_36_complete_public_synthetic_positive(self):
        self.assertEqual(self.check()['status'],'PUBLIC_IDENTITY_SCHEMA_AND_BINDINGS_VALID')
    def test_37_tensor_schema_corruption_after_all_hashes_rebound(self):
        self.values['replay_identity.json']['identity']['runs']['128']['native'].pop(next(iter(self.values['replay_identity.json']['identity']['runs']['128']['native'])))
        self.rebind()
        with self.assertRaises(ValueError):self.check()
    def test_38_stable_identity_hash_must_match(self):
        self.values['replay_identity.json']['identity_sha256']='0'*64
        self.values['summary.json']['replay_identity_sha256']=V.sha(V.encoded(self.values['replay_identity.json']))
        with self.assertRaises(ValueError):self.check()
    def test_39_metadata_cannot_grant_authority(self):
        self.values['replay_identity.json']['authority']['freeze_readiness_granted']=True;self.rebind()
        with self.assertRaises(ValueError):self.check()
    def test_40_full_file_source_pin_is_required(self):
        raw=F.archive(F.raws(V,self.values))
        # This executes the same verifier as CLI, with its final checked local
        # schema module. It does not mock the schema, read private tensors or
        # authenticate a real GitHub execution.
        report=V.verify(raw,artifact_sha256=V.sha(raw),ci=self.values['summary.json']['ci'],freeze=F.FREEZE)
        self.assertEqual(report['status'],'PASS_PUBLIC_REPLAY_IDENTITY_AND_RECEIPT_BINDING')
        self.assertFalse(report['github_metadata_independently_fetched'])
        self.assertFalse(report['private_tensor_bytes_replayed'])
        self.assertFalse(report['actual_git_publication_proof_replayed'])

    def test_41_authenticated_generated_compile_map(self):
        self.assertEqual(V.sha(V.encoded(self.compiled)),'0e298008babe63514b05405190831b7cf265e6dc82956bef648f9dbbbff36db0')
        self.assertEqual(self.compiled[V.BASE+'ffn_attention/matrix_numeric.cpp'],'1ddf017ffda70af19a70385cfffe1d5a405113f27d73378410a7fa2575bcfa25')
        self.assertNotEqual(self.compiled[V.BASE+'ffn_attention/matrix_numeric.cpp'],self.full[V.BASE+'ffn_attention/matrix_numeric.cpp'])
    def test_42_wrong_raw_compile_map_rejected(self):
        m=self.values['replay_identity.json'];m['provenance']['combined_library']['source_map_sha256']=V.sha(V.encoded({n:self.full[n] for n in V.COMPILE_PATHS}));self.rebind()
        with self.assertRaises(ValueError):self.check()
    def test_43_disagreeing_composed_compile_map_rejected(self):
        pins=copy.deepcopy(self.pins);pins[16]['composed_sources'][V.COMPILE_PATHS[0]]=self.full[V.COMPILE_PATHS[0]]
        with self.assertRaisesRegex(V.VerificationError,'COMPOSED_COMPILE_BINDING'):V.derive_compile_sources(F.FREEZE,self.full,pins)
    def test_44_tiny_contract_pin_required(self):
        full=dict(self.full);full[V.TINY_CONTRACT]='0'*64
        with self.assertRaisesRegex(V.VerificationError,'TINY_CONTRACT_PIN'):V.derive_compile_sources(F.FREEZE,full,self.pins)

if __name__=='__main__':unittest.main(verbosity=2)
