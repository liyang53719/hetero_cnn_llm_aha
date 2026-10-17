"""Cold package checks. No compiler invocation."""
import argparse,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from reproduce_sources import rebuild
HERE=Path(__file__).resolve().parent
class Tests(unittest.TestCase):
    def test_reconstruction(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'source';r=rebuild(PROD,QK,HF,out)
            self.assertEqual(r,dict(source_count=92,compiler_started=False))
            pins=json.loads((HERE/'PLANNED_SOURCE_PINS.json').read_text())
            self.assertEqual({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*.scala')},pins)
            with self.assertRaises(ValueError):rebuild(PROD,QK,HF,out)
    def test_missing_or_tampered_input_refused(self):
        with tempfile.TemporaryDirectory() as d:
            fake=Path(d)/'hf';fake.mkdir()
            for f in HF.glob('*.scala'):(fake/f.name).write_bytes(f.read_bytes())
            first=next(fake.glob('*.scala'));first.write_text('tampered')
            out=Path(d)/'output'
            with self.assertRaises(ValueError):rebuild(PROD,QK,fake,out)
            self.assertFalse(out.exists())
    def test_safe_projection(self):
        data=json.loads((HERE/'SAFE_COMPILE_RESULT.json').read_text())
        self.assertFalse(data['portable_driver_java_executed']);self.assertFalse(data['rtl'])
        text=json.dumps(data)
        for forbidden in ('owner_identity','ppid','start_ticks','fingerprint','/workspace/','/usr/lib/'):self.assertNotIn(forbidden,text)
    def test_recipe_identity(self):
        pins=json.loads((HERE.parent/'ARTIFACT_HASHES.json').read_text())
        for rel,h in pins.items():self.assertEqual(hashlib.sha256((HERE.parent/rel).read_bytes()).hexdigest(),h)
    def test_explicit_roots_and_no_binaries(self):
        driver=(HERE/'compile_only.py').read_text()
        for arg in ('--source-root','--dependency-cache','--java'):self.assertIn(arg,driver)
        for p in HERE.parent.rglob('*'):
            self.assertNotIn(p.suffix,('.class','.jar','.fir','.v','.sv'))
            if p.is_file():self.assertNotIn('/'+'workspace'+'/scratch/',p.read_text())
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('production-source','qk16-source','hardfloat-scala'):p.add_argument('--'+n,required=True,type=Path)
    a,rest=p.parse_known_args();PROD=a.production_source;QK=a.qk16_source;HF=a.hardfloat_scala
    unittest.main(argv=[sys.argv[0]]+rest)
