"""Pure exact source/contract gates; no compiler, runtime, or authority mocks."""
import ast,importlib.util,json,pathlib,tempfile,unittest,shutil,hashlib
D=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('first_fault_policy_tested',D/'first_fault_policy.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.repo=pathlib.Path(self.tmp.name).resolve();self.doc=p.decode_contract((D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes());src=D.parents[1]
  for row in self.doc.values():
   if type(row)is dict and 'repo_path'in row:
    dst=self.repo/row['repo_path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/row['repo_path'],dst)
  fixture=ast.parse((src/'candidates/moe_router_score_observation_20261030/driver/test_terminal_finite_host.py').read_text())
  legacy=ast.literal_eval(next(n.value for n in fixture.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='LEGACY_HEADER'for t in n.targets)))
  self.assertEqual(hashlib.sha256(legacy.encode()).hexdigest(),self.doc['host_observer']['sha256'])
  (self.repo/self.doc['host_observer']['repo_path']).write_text(legacy)
  q=self.repo/p.CONTRACT_REPO_PATH;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(D/'FIRST_FAULT_DRIVER_CONTRACT.json',q)
  sc=self.repo/p.SOURCE_CONTRACT_REPO_PATH;sc.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/p.SOURCE_CONTRACT_REPO_PATH,sc)
  self.binding={'repo':str(self.repo),'driver':str(self.repo/self.doc['diagnostic_driver']['repo_path']),'first_fault_driver_contract':{'path':str(q),'sha256':p.CONTRACT_SHA},'generation_contract':str(self.repo/self.doc['hardware_generation_contract']['repo_path']),'generation_contract_sha256':self.doc['hardware_generation_contract']['sha256'],'model_source_contract':str(self.repo/p.SOURCE_CONTRACT_REPO_PATH),'pins':{str(f):p.sha(f)for f in self.repo.rglob('*')if f.is_file()}}
 def test_default_is_original(self):self.assertIsNone(p.binding_policy({}));self.assertEqual(p.expected_driver_sha({}),p.LEGACY_DRIVER_SHA)
 def test_actual_source_roles_and_inverse(self):self.assertEqual(p.load_source_contract(self.repo),self.doc)
 def test_actual_binding_all_roles(self):self.assertEqual(p.binding_policy(self.binding),self.doc);self.assertEqual(p.expected_driver_sha(self.binding),self.doc['diagnostic_driver']['sha256'])
 def test_contract_mutation_rejected(self):
  with self.assertRaises(ValueError):p.decode_contract((D/'FIRST_FAULT_DRIVER_CONTRACT.json').read_bytes()+b' ')
 def test_newdriver_mutation_rejected(self):
  f=self.repo/self.doc['diagnostic_driver']['repo_path'];f.write_bytes(f.read_bytes()+b'\n')
  with self.assertRaises(ValueError):p.load_source_contract(self.repo)
 def test_new_executor_helper_cannot_satisfy_old_contract(self):
  f=self.repo/self.doc['host_observer']['repo_path'];f.write_bytes((D.parents[1]/self.doc['host_observer']['repo_path']).read_bytes())
  with self.assertRaisesRegex(ValueError,'host_observer'):p.load_source_contract(self.repo)
 def test_helper_mutation_rejected(self):
  f=self.repo/self.doc['host_observer']['repo_path'];f.write_bytes(f.read_bytes()+b'\n')
  with self.assertRaises(ValueError):p.load_source_contract(self.repo)
 def test_missing_role_rejected(self):
  (self.repo/self.doc['probe_config']['repo_path']).unlink()
  with self.assertRaises(ValueError):p.load_source_contract(self.repo)
 def test_symlink_role_rejected(self):
  f=self.repo/self.doc['host_observer']['repo_path'];g=f.with_suffix('.copy');f.rename(g);f.symlink_to(g)
  with self.assertRaises(ValueError):p.load_source_contract(self.repo)
 def test_missing_source_contract_rejects_new_binding(self):
  (self.repo/p.SOURCE_CONTRACT_REPO_PATH).unlink()
  with self.assertRaises(ValueError):p.binding_policy(self.binding)
 def test_wrong_selector_rejected(self):
  self.binding['first_fault_driver_contract']['sha256']='0'*64
  with self.assertRaises(ValueError):p.binding_policy(self.binding)
 def test_no_diag_evidence_through_old_schema(self):
  with self.assertRaises(ValueError):p.artifact_policy({'schema':'MODEL_CANDIDATE_FIVE_PROFILE_BUILD_ARTIFACT_V1'},{'readonly_probe':{}})
if __name__=='__main__':unittest.main()
