#!/usr/bin/env python3
"""Publisher Git-mechanics tests; synthetic proof fixtures are NOT DUT evidence.

Creates new repositories under OWNER_TEST_ARTIFACTS, never removes test data.
"""
import hashlib,json,os,subprocess,sys,unittest,uuid
from pathlib import Path
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'scripts'))
from publish_owner_regression import publish,selected_files

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(os.environ.get('OWNER_TEST_ARTIFACTS','/tmp/owner_publication_tests'))/uuid.uuid4().hex
        self.root.mkdir(parents=True);self.repo=self.root/'repo';self.remote=self.root/'origin.git';self.out=self.root/'outputs'
        self.repo.mkdir();self.out.mkdir()
        self.git('init','-b','main');self.git('config','user.name','Publisher Fixture Test');self.git('config','user.email','fixture@example.invalid')
        (self.repo/'dut.scala').write_text('// Synthetic publisher unit fixture; no DUT simulation\n')
        self.git('add','dut.scala');self.git('commit','-m','synthetic publication test fixture')
        self.source=self.git('rev-parse','HEAD').strip()
        subprocess.run(['git','init','--bare','--initial-branch=main',str(self.remote)],check=True,stdout=subprocess.DEVNULL)
        self.git('remote','add','origin',str(self.remote));self.git('push','-u','origin','main')
        self.identity={'dut.scala':hashlib.sha256((self.repo/'dut.scala').read_bytes()).hexdigest()}
        (self.out/'base17').mkdir();(self.out/'base17/sources.sha256.json').write_text(json.dumps(self.identity))
        (self.out/'REGRESSION_RESULT.json').write_text(json.dumps({'status':'PASS_FIXED_HOST_OWNER_REGRESSION','source_commit':self.source,'profile':'tiny','unit_fixture_only':True}))
        (self.out/'gate.exit').write_text('0\n');(self.out/'tensor.f32le').write_bytes(bytes(range(128)))
        (self.out/'emitted.sv').write_bytes(b'// emitter exact-byte unit fixture\n\n')
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.repo),*args],stderr=subprocess.DEVNULL).decode()
    def test_exact_byte_publication_and_idempotence(self):
        before=self.git('rev-parse','HEAD');status=self.git('status','--porcelain')
        result=publish(self.repo,self.out,self.source)
        self.assertEqual(self.git('rev-parse','HEAD'),before);self.assertEqual(self.git('status','--porcelain'),status)
        raw=subprocess.check_output(['git','--git-dir',str(self.remote),'show',result['commit']+':'+result['path']+'/tensor.f32le'])
        self.assertEqual(raw,bytes(range(128)))
        self.assertEqual(subprocess.check_output(['git','--git-dir',str(self.remote),'show',result['commit']+':'+result['path']+'/emitted.sv']),b'// emitter exact-byte unit fixture\n\n')
        again=publish(self.repo,self.out,self.source);self.assertTrue(again['already_present']);self.assertEqual(again['commit'],result['commit'])
    def test_failed_gate_rejected(self):
        (self.out/'gate.exit').write_text('1\n')
        with self.assertRaises(ValueError):publish(self.repo,self.out,self.source)
    def test_wrong_tested_commit_rejected(self):
        with self.assertRaises(ValueError):publish(self.repo,self.out,'0'*40)
    def test_changed_main_source_rejected(self):
        (self.repo/'dut.scala').write_text('// changed\n');self.git('commit','-am','changed source');changed=self.git('rev-parse','HEAD').strip();self.git('push','origin','main')
        # Separate publisher checkout at the genuine old source, without reset.
        checkout=self.root/'old_checkout';subprocess.run(['git','clone',str(self.remote),str(checkout)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['git','-C',str(checkout),'checkout','--detach',self.source],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with self.assertRaisesRegex(ValueError,'main changed a tested source'):publish(checkout,self.out,self.source)
        self.assertEqual(subprocess.check_output(['git','--git-dir',str(self.remote),'rev-parse','main']).decode().strip(),changed)
    def test_unrelated_main_advance_is_preserved(self):
        other=self.root/'other';subprocess.run(['git','clone',str(self.remote),str(other)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def g(*args):return subprocess.check_output(['git','-C',str(other),*args],stderr=subprocess.DEVNULL)
        g('config','user.name','Fixture');g('config','user.email','fixture@example.invalid');(other/'note.md').write_text('unrelated work\n');g('add','note.md');g('commit','-m','unrelated');g('push','origin','main')
        result=publish(self.repo,self.out,self.source)
        self.assertEqual(subprocess.check_output(['git','--git-dir',str(self.remote),'show',result['commit']+':note.md']),b'unrelated work\n')
    def test_existing_different_evidence_not_overwritten(self):
        first=publish(self.repo,self.out,self.source)
        (self.out/'tensor.f32le').write_bytes(b'mutated proof')
        with self.assertRaisesRegex(ValueError,'overwrite different evidence'):publish(self.repo,self.out,self.source)
        self.assertEqual(subprocess.check_output(['git','--git-dir',str(self.remote),'rev-parse','main']).decode().strip(),first['commit'])
    def test_filtered_objects_and_symlinks_not_published(self):
        for d in ['obj','negative_artifacts','test_run_dir','classes']:
            (self.out/d).mkdir();(self.out/d/'never.json').write_text('{}')
        secret=self.root/'outside.txt';secret.write_text('excluded unit fixture');(self.out/'escape.txt').symlink_to(secret)
        names=selected_files(self.out)
        self.assertFalse(any('never' in p or 'escape' in p for p in names))
        self.assertIn('tensor.f32le',names)

if __name__=='__main__':unittest.main(verbosity=2)
