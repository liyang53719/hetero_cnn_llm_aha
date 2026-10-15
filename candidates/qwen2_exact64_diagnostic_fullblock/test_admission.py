"""Cold admission regressions; no model, compiler, payload or CI execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from candidates.qwen2_exact64_diagnostic_fullblock import exact64_artifact as E, gates, job, supervisor

class Admission(unittest.TestCase):
    def test_default_entries_do_not_execute(self):
        for module in ('launch','runner','audit_probe'):
            p=subprocess.run([sys.executable,'-B','-m','candidates.qwen2_exact64_diagnostic_fullblock.'+module],cwd=E.ROOT,capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(json.loads(p.stdout)['status'],'NOT_EXECUTED')
    def test_policy_is_diagnostic(self):
        self.assertEqual(job.POLICY['scope'],'DIAGNOSTIC_SOFTWARE_OWNER')
        self.assertIs(job.POLICY['formal_fullblock_acceptance'],False)
        self.assertEqual(job.POLICY['performance'],'NO_GO')
        self.assertNotIn('authorization_v3',job.AUTH)
    def test_fixed_single_output(self):
        with patch.object(gates,'_canonical',side_effect=lambda x:Path(x)):
            with self.assertRaises(ValueError):gates.fresh_output(gates.OUTPUT_ROOT/'ci02',gates.DATA)
    def test_new_scope_receipt_not_formal_pass(self):
        text=Path(supervisor.__file__).read_text()
        self.assertIn("status='PASS_DIAGNOSTIC_SOFTWARE_OWNER'",text)
        self.assertIn('fullblock_pass=False,diagnostic_numeric_pass=passed',text)
        self.assertNotIn('fullblock_pass=passed',text)
        self.assertIn("'--kernel-library'",text)
    def test_old_review_cannot_approve_new_scope(self):
        old=dict(job.POLICY);old['scope']='M128_SOFTWARE_PUBLIC21_FULLBLOCK'
        self.assertFalse(all(type(old[k]) is type(v) and old[k]==v for k,v in job.POLICY.items()))
    def test_supervisor_requires_every_diagnostic_flag(self):
        result=dict(status='PASS_DIAGNOSTIC_SOFTWARE_OWNER',scope='DIAGNOSTIC_SOFTWARE_OWNER',
            diagnostic_acceptance_sealed=True,diagnostic_numeric_pass=True,whole_block_terminal=True,
            acceptance_sealed=False,fullblock_pass=False,chisel_full_prefill_pass=False,
            model_corresponds_to_current_chisel=False,performance='NO_GO',hardware_mapping='NOT_IMPLEMENTED')
        self.assertTrue(supervisor.diagnostic_complete(result))
        for key,value in result.items():
            missing=dict(result);del missing[key]
            self.assertFalse(supervisor.diagnostic_complete(missing))
            self.assertFalse(supervisor.diagnostic_complete({**result,key:not value if type(value) is bool else 'OLD_PASS'}))
        self.assertFalse(supervisor.diagnostic_complete({**result,'diagnostic_numeric_pass':1}))
    def test_joint_job_and_step_budget(self):
        with patch.object(job.time,'monotonic',return_value=10000.0):
            # Whole job remains ample, but slow preprocessing exhausts step reserve.
            with self.assertRaisesRegex(ValueError,'joint job/actual-step'):
                job.require_remaining(9900*10**9,9700.0,3330+122+60)
            # Conversely a fresh step cannot reset the old whole-job clock.
            with self.assertRaisesRegex(ValueError,'joint job/actual-step'):
                job.require_remaining(5600*10**9,10000.0,122+60)
            self.assertGreaterEqual(job.require_remaining(9900*10**9,10000.0,3330+122+60),3512)
    def test_postseal_real_child_exit_and_timeout(self):
        with tempfile.TemporaryFile() as log:
            self.assertEqual(job.bounded_child([sys.executable,'-B','-c','raise SystemExit(0)'],log,3),0)
            self.assertEqual(job.bounded_child([sys.executable,'-B','-c','raise SystemExit(2)'],log,3),2)
            with self.assertRaisesRegex(ValueError,'outer wall'):
                job.bounded_child([sys.executable,'-B','-c','import time; time.sleep(30)'],log,2.2)
    def fixture(self,d):
        library=d/'exact64.so';library.write_bytes(b'\x7fELF\x02\x01cold fixture')
        receipt=d/'compile.json';sources={'fixed.cpp':'a'*64}
        comp=dict(path=str(Path('/usr/bin/g++').resolve()),version='synthetic',**E.identity_file(Path('/usr/bin/g++').resolve()))
        value=dict(schema=1,status=E.STATUS,compiler=comp,argv=['fixture-only'],sources=sources,
            library=dict(path=str(library.relative_to(d)),**E.identity_file(library)),scope='DIAGNOSTIC_SOFTWARE_OWNER')
        receipt.write_text(json.dumps(value))
        return library,receipt,sources,value
    def test_artifact_verify_and_same_size_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib,receipt,sources,value=self.fixture(root)
            with patch.multiple(E,ROOT=root,LIBRARY=lib,RECEIPT=receipt),patch.object(E,'argv',return_value=['fixture-only']),patch.object(E.kernel,'source_check',return_value=sources):
                checked=E.verify();self.assertEqual(checked['library']['bytes'],lib.stat().st_size)
                lib.write_bytes(b'X'*lib.stat().st_size)
                with self.assertRaisesRegex(ValueError,'ELF'):E.verify()
    def test_artifact_rejects_schema_and_bool_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib,receipt,sources,value=self.fixture(root)
            with patch.multiple(E,ROOT=root,LIBRARY=lib,RECEIPT=receipt),patch.object(E,'argv',return_value=['fixture-only']),patch.object(E.kernel,'source_check',return_value=sources):
                for altered in ({**value,'extra':'private'}, {**value,'schema':True}, {**value,'library':{**value['library'],'bytes':True}}):
                    receipt.write_text(json.dumps(altered))
                    with self.assertRaises(ValueError):E.verify()
    def test_artifact_source_and_argv_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);lib,receipt,sources,value=self.fixture(root)
            with patch.multiple(E,ROOT=root,LIBRARY=lib,RECEIPT=receipt),patch.object(E,'argv',return_value=['fixture-only']),patch.object(E.kernel,'source_check',return_value=sources):
                for field,replacement in (('sources',{}),('argv',['looser-flags']),('scope','HARDWARE_PASS')):
                    receipt.write_text(json.dumps({**value,field:replacement}))
                    with self.assertRaises(ValueError):E.verify()
    def test_fresh_build_success_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'build';library=directory/'exact64.so';receipt=directory/'compile.json'
            comp=dict(path=str(Path('/usr/bin/g++').resolve()),version='synthetic',**E.identity_file(Path('/usr/bin/g++').resolve()))
            class Child:
                pid=99999999
                returncode=0
                def poll(self):return self.returncode
            def spawn(args,**kwargs):
                self.assertTrue(kwargs['start_new_session']);self.assertEqual(args,E.argv())
                library.write_bytes(b'\x7fELF\x02\x01cold compiled fixture');return Child()
            with patch.multiple(E,ROOT=root,DIRECTORY=directory,LIBRARY=library,RECEIPT=receipt),patch.object(E,'compiler',return_value=comp),patch.object(E.kernel,'source_check',return_value={'fixed.cpp':'a'*64}),patch.object(E.subprocess,'Popen',side_effect=spawn),patch('candidates.qwen2_live_attention_model_m128_bounded.v2.launch.group_exists',return_value=False):
                self.assertEqual(E.build()['library']['bytes'],len(b'\x7fELF\x02\x01cold compiled fixture'))
                with self.assertRaisesRegex(ValueError,'single fresh'):E.build()
    def test_failed_build_never_publishes_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'build';receipt=directory/'compile.json'
            class Child:
                pid=99999999
                returncode=1
                def poll(self):return self.returncode
            with patch.multiple(E,ROOT=root,DIRECTORY=directory,LIBRARY=directory/'exact64.so',RECEIPT=receipt),patch.object(E,'compiler',return_value={}),patch.object(E.kernel,'source_check',return_value={}),patch.object(E.subprocess,'Popen',return_value=Child()),patch('candidates.qwen2_live_attention_model_m128_bounded.v2.launch.group_exists',return_value=False):
                with self.assertRaisesRegex(ValueError,'compile failed'):E.build()
                self.assertFalse(receipt.exists());self.assertTrue((directory/'build.log').exists())
    def test_binding_required_before_elf_identity(self):
        with patch.dict('os.environ',{E.N.BINDING_ENV:''}):
            with self.assertRaisesRegex(ValueError,'explicit exact64 binding'):E.identity()

if __name__=='__main__':unittest.main()
