"""Fresh isolated CLI checks using synthetic public identities, not run evidence."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
HERE=Path(__file__).resolve().parent

def load(name):
    p=HERE/(name+'.py');m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
V=load('verify_artifact');S=load('identity_schema');sys.modules['identity_schema']=S
T=load('test_fixture');F=load('receipt_fixture')


class IsolatedCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        full,pins=V.load_sources(F.FREEZE);compiled=V.derive_compile_sources(F.FREEZE,full,pins)
        cls.values,_,_=F.build(V,T.build_manifest(pins[128]['inputs'],compile_sources=compiled))
    def exercise(self,*,optimized=False,mutate=None,wrong_job=False,drift_helper=False,preexisting_out=False):
        values=copy.deepcopy(self.values)
        if mutate:mutate(values)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw=F.archive(F.raws(V,values));(root/'artifact.zip').write_bytes(raw)
            for name in ('verify_artifact.py','identity_schema.py'):shutil.copyfile(HERE/name,root/name)
            if drift_helper:
                with (root/'identity_schema.py').open('ab') as f:f.write(b'\n# mutated fixture copy\n')
            if preexisting_out:(root/'result.json').write_bytes(b'PRESERVE')
            args=[sys.executable,'-I','-B',*(['-O'] if optimized else []),str(root/'verify_artifact.py'),
                '--artifact',str(root/'artifact.zip'),'--artifact-sha256',hashlib.sha256(raw).hexdigest(),
                '--run-id',V.RUN_ID,'--job-id','1' if wrong_job else V.JOB_ID,'--artifact-id','987654',
                '--freeze',str(F.FREEZE),'--out',str(root/'result.json')]
            p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
            result=(root/'result.json').read_bytes() if (root/'result.json').exists() else None
            self.assertFalse(list(root.rglob('*.pyc')))
            return p,result
    def test_01_normal_synthetic_cli(self):
        p,r=self.exercise();self.assertEqual(p.returncode,0,p.stderr.decode());v=json.loads(r)
        self.assertEqual(v['raw_source_files'],465);self.assertFalse(v['github_metadata_independently_fetched'])
        self.assertFalse(v['private_tensor_bytes_replayed']);self.assertEqual(len(v['files']),8)
    def test_02_optimized_synthetic_cli(self):
        p,r=self.exercise(optimized=True);self.assertEqual(p.returncode,0,p.stderr.decode());self.assertEqual(json.loads(r)['ci']['run_id'],V.RUN_ID)
    def test_03_source_pin_failure(self):
        p,r=self.exercise(drift_helper=True);self.assertNotEqual(p.returncode,0);self.assertIsNone(r);self.assertIn(b'VALIDATOR_SOURCE_PIN',p.stderr)
    def test_04_wrong_actual_job(self):
        p,r=self.exercise(wrong_job=True);self.assertNotEqual(p.returncode,0);self.assertIsNone(r);self.assertIn(b'ACTUAL_RUN_JOB_BINDING',p.stderr)
    def test_05_orphan_artifact(self):
        p,r=self.exercise(mutate=lambda v:v['summary.json'].update(replay_identity_ready=False));self.assertNotEqual(p.returncode,0);self.assertIsNone(r)
    def test_06_no_overwrite(self):
        p,r=self.exercise(preexisting_out=True);self.assertNotEqual(p.returncode,0);self.assertEqual(r,b'PRESERVE')
    def test_07_qualified_metadata_no_direct_claim(self):
        def mutate(v):
            m=v['replay_identity.json'];m['identity']['runs']['128']['full']['loaded_providers']['rope']['verification']='DIRECT_FILE_REHASH'
            m['identity_sha256']=V.sha(V.encoded(m['identity']));v['summary.json']['replay_identity_sha256']=V.sha(V.encoded(m))
        p,r=self.exercise(mutate=mutate);self.assertNotEqual(p.returncode,0);self.assertIsNone(r)

if __name__=='__main__':unittest.main(verbosity=2)
