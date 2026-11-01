import hashlib,pathlib,unittest
D=pathlib.Path(__file__).resolve().parent
class ExportPathTests(unittest.TestCase):
 def test_only_fixed_path_and_join_changed(self):
  s=(D/'export_model_build.py').read_text()
  new=" artifact=front/'model_candidate_artifact'\n need(result['artifact']['manifest']['path']==str((artifact/'frozen_artifact.json').resolve(strict=True)),'fixed candidate artifact manifest path')\n payload=verify"
  old=" artifact=front/'frozen_artifact';payload=verify"
  self.assertEqual(s.count(new),1)
  self.assertEqual(hashlib.sha256(s.replace(new,old).encode()).hexdigest(),'3fbaf4a22155759fb66e1a5ff4e97fd4df1cba8365ceb931d1c472172262daa1')
if __name__=='__main__':unittest.main()
