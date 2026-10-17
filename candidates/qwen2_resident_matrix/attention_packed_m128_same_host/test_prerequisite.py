"""Cold synthetic receipt chain; actual original M16 terminal replay, no numerics."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from . import contract as C, prerequisite as P
from ..attention_packed_m16_same_host import prepare as old_prepare
from ..attention_packed_m16_same_host import test_terminal_validator as fixture_module


class PrerequisiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.job=Path(cls.tmp.name);cls.root=cls.job/'m16';cls.root.mkdir()
        cls.ci=dict(commit='1'*40,run_id='123',run_attempt='1')
        cls.composition=old_prepare.compose(cls.root/'source',git_head=cls.ci['commit'],
            producer_package=old_prepare.ROOT/'candidates/qwen2_resident_matrix/portable_official_producer')
        cls.sources=cls.composition['source_sha256']
        for name in P.FILES.values():(cls.root/name).parent.mkdir(parents=True,exist_ok=True)
        (cls.root/'setup/tiny/source').mkdir(parents=True)
        (cls.root/'setup/tiny/build').mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def write(self,name,value):
        path=self.root/P.FILES.get(name,name);raw=C.encoded(value);path.write_bytes(raw)
        return dict(path=str(path),sha256=C.sha(raw))

    def setUp(self):
        (self.job/'M16_PREREQUISITE.json').unlink(missing_ok=True)
        self.nonce='b'*64
        self.producer=dict(attempt_nonce=self.nonce,source_manifest_sha256='c'*64,
            host=dict(synthetic_host=True),runtime_identity=dict(synthetic_runtime=True),ci=self.ci)
        pp=self.write('producer_manifest',self.producer)
        self.q=dict(schema=1,profile='qwen2-fresh-same-host-m16-producer-qualified-v1',status='PASS_FRESH_M16_PRODUCER',
            attempt_nonce=self.nonce,producer_manifest_sha256=pp['sha256'],producer_source_manifest_sha256='c'*64,
            host_sha256=C.sha(C.encoded(self.producer['host'])),runtime_identity_sha256=C.sha(C.encoded(self.producer['runtime_identity'])),
            ci=self.ci,child_pid=100,child_exit_code=0,owned_group_cleanup_complete=True,producer_native_gate_validated=True,
            elapsed_seconds=1,claims={k:False for k in ('actual_chain_executed','full_public_admission','full_29_node_acceptance',
                'rtl_execution','hardware_recipe_acceptance','old_pass_inherited')},fresh_tiny_result_sha256='d'*64,
            fresh_tiny_source_manifest_sha256='e'*64)
        qp=self.write('producer_qualification',self.q)
        snapshot=self.root/P.FILES['snapshot'];r,s,_=fixture_module.fixture(snapshot)
        for item in (r,s,r['observation']):item['source_sha256']=self.sources
        r['source_sha256_after']=self.sources;s['source_manifest_sha256']=C.sha(fixture_module.V.encoded(self.sources,pretty=True))
        r['executed_imports_observed']=sorted(self.sources)
        binary=self.root/'setup/tiny/build/official_bf16_matrix_silu.so';binary.write_bytes(b'SYNTHETIC_NOT_AN_ELF_NOT_EXECUTED')
        built=dict(library=str(binary),library_sha256=C.sha(binary.read_bytes()))
        compilep=self.write('setup/tiny/build/official_bf16_compile.json',built)
        bins=dict(compile_receipt=compilep['path'],compile_sha256=compilep['sha256'],library=str(binary),library_sha256=built['library_sha256'])
        r['binaries']=s['binaries']=bins
        sp=self.write('snapshot',s);r['snapshot_sha256']=sp['sha256'];ap=self.write('actual',r)
        from . import terminal_m16
        self.validation=terminal_m16.validate_terminal(ap['path'],ap['sha256'],self.sources,sp['path'],sp['sha256'])
        ch=dict(schema=1,profile=P.M16_PROFILE,status='VALIDATED_FRESH_M16_CHILD_RESULT',attempt_nonce=self.nonce,
            producer_receipt_sha256=qp['sha256'],source_manifest_sha256=C.sha(C.encoded(self.sources)),summary_sha256=ap['sha256'],
            snapshot_sha256=sp['sha256'],validation=self.validation,parent_must_authenticate_exit_and_cleanup=True,
            full_29_node_acceptance=False,rtl_execution=False,hardware_recipe_acceptance=False,old_pass_inherited=False)
        cp=self.write('child_result',ch)
        f=dict(schema=1,profile='qwen2-fresh-same-host-m16-combined-v1',status='PASS_FRESH_SAME_HOST_M16_ASSIGNED27',
            ci=self.ci,attempt_nonce=self.nonce,producer_receipt_sha256=qp['sha256'],child_result_sha256=cp['sha256'],
            child_pid=200,child_exit_code=0,owned_group_cleanup_complete=True,elapsed_seconds=1,validation=self.validation,
            claims={k:False for k in ('full_29_node_acceptance','full_m128_acceptance','rtl_execution','hardware_recipe_acceptance','old_pass_inherited')})
        self.write('full_receipt',f)
        self.observed=dict(pid=200,observed_exit_code=0,final_exit_code=0,owned_group_cleanup_complete=True)

    def seal(self):
        return P.seal(self.job/'M16_PREREQUISITE.json',m16_root=self.root,parent_pid=os.getpid(),observed_full=self.observed,ci=self.ci)

    def verify(self,path,sha,**changes):
        kwargs=dict(m16_root=self.root,parent_pid=os.getpid(),ci=self.ci,attempt_nonce=self.nonce,
            host_sha256=self.q['host_sha256'],runtime_identity_sha256=self.q['runtime_identity_sha256'],current_sources=self.sources)
        kwargs.update(changes);return P.verify(path,sha,**kwargs)

    def test_complete_current_chain_replays_original_and_same_elf(self):
        path,sha,value=self.seal();self.assertEqual(self.verify(path,sha,library=value['library']),value)
        self.assertEqual(len(value['source_sha256']),357);self.assertEqual(value['validation']['assigned_official_gates'],27)
        self.assertEqual(value['validation']['official_observed_stages'],28)
        self.assertFalse(value['old_pass_inherited']);self.assertFalse(value['m128_verdict_inherited'])

    def test_current_parent_ci_nonce_host_runtime_cannot_be_inherited(self):
        path,sha,_=self.seal()
        for key,value in [('parent_pid',os.getpid()+1),('attempt_nonce','f'*64),('ci',dict(self.ci,run_id='other')),
            ('host_sha256','f'*64),('runtime_identity_sha256','f'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify(path,sha,**{key:value})

    def test_projection_canonical_types_cannot_be_rebound(self):
        path,sha,value=self.seal()
        for field,replacement in [('parent_pid',float(os.getpid())),('schema',True)]:
            bad=copy.deepcopy(value);bad[field]=replacement;raw=C.encoded(bad);path.write_bytes(raw)
            with self.subTest(field=field),self.assertRaises(ValueError):self.verify(path,C.sha(raw))
        bad=copy.deepcopy(value);bad['validation']['schema']=True;raw=C.encoded(bad);path.write_bytes(raw)
        with self.assertRaises(ValueError):self.verify(path,C.sha(raw))

    def test_same_elf_and_same_compile_receipt_mandatory(self):
        path,sha,value=self.seal()
        for field in ('receipt','binary'):
            lib=copy.deepcopy(value['library']);lib[field]['sha256']='f'*64
            with self.subTest(field=field),self.assertRaises(ValueError):self.verify(path,sha,library=lib)
        lib=copy.deepcopy(value['library']);lib['origin_root']='/historical/source'
        with self.assertRaises(ValueError):self.verify(path,sha,library=lib)

    def test_observed_zero_cleanup_and_live_sealing_parent_required(self):
        for key,value in [('pid',201),('observed_exit_code',1),('final_exit_code',1),
                          ('observed_exit_code',False),('owned_group_cleanup_complete',False)]:
            obs=dict(self.observed);obs[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                P.seal(self.job/'M16_PREREQUISITE.json',m16_root=self.root,parent_pid=os.getpid(),observed_full=obs,ci=self.ci)
        with self.assertRaises(ValueError):P.seal(self.job/'M16_PREREQUISITE.json',m16_root=self.root,
            parent_pid=os.getpid()+1,observed_full=self.observed,ci=self.ci)

    def test_missing_full_child_or_forged_actual_pass_does_not_authorize(self):
        for role in ('actual','snapshot','child_result','full_receipt','producer_qualification'):
            path=self.root/P.FILES[role];raw=path.read_bytes();value=json.loads(raw);value['status']='PASS'
            path.write_bytes(C.encoded(value))
            with self.subTest(role=role),self.assertRaises(ValueError):self.seal()
            path.write_bytes(raw)

    def test_complete_source_map_cannot_shrink_to24_or_unrelated_full_map(self):
        path=self.root/P.FILES['actual'];raw=path.read_bytes();value=json.loads(raw)
        for replacement in (C.read_json(C.HERE/'compatible-sources.json'),dict(self.sources,**{'extra.py':'f'*64})):
            value['source_sha256']=replacement;path.write_bytes(C.encoded(value))
            with self.assertRaises(ValueError):self.seal()
        path.write_bytes(raw)

    def test_all24_unchanged_owner_arithmetic_service_sources_required(self):
        expected=C.read_json(C.HERE/'compatible-sources.json')
        self.assertEqual(P.compatible_sources(self.sources,self.sources),expected)
        for name in expected:
            changed=dict(self.sources);changed[name]='f'*64
            with self.subTest(name=name),self.assertRaises(ValueError):P.compatible_sources(changed,self.sources)

    def test_dynamic_actual_commit_contract_source_drift_rejected(self):
        p=self.root/'source/candidates/qwen2_resident_matrix/attention_packed_m16_same_host/SOURCE_CONTRACT.json'
        raw=p.read_bytes();value=json.loads(raw);value['git_head']='2'*40;p.write_bytes(C.encoded(value))
        try:
            with self.assertRaises(ValueError):self.seal()
        finally:p.write_bytes(raw)


if __name__=='__main__':unittest.main()
