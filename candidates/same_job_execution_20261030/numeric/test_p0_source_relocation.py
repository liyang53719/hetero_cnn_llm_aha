"""Pure source-byte relocation tests. No builder/runtime/ELF execution authority."""
import copy,json,pathlib,tempfile,unittest
import observation_contract as o
P=pathlib.Path
PATHS=dict(helper='candidates/fresh_original_top_recovery_20261028/source/DiagnoseOriginalHostMoePhaseV5.scala',host_top='candidates/moe_router_score_observation_20261030/source/HostBlockTopV4.scala',host_commands='candidates/p0_resident_observation_20261030/source/HostBlockCommandsV4.scala',owner_kernel='candidates/p0_resident_observation_20261030/source/QwenOwnerProtocol.scala',qkv_router='candidates/fresh_original_top_recovery_20261028/source/Public21QkvReductionRouter.scala',resident='candidates/p0_resident_observation_20261030/source/FfnResidentCoordinator.scala',bridge='candidates/p0_resident_observation_20261030/source/FfnTileSiluBridge.scala',driver='candidates/moe_router_score_observation_20261030/driver/host_axi_driver_non_dpi.cpp',sparse_memory='candidates/host_runtime_non_dpi_backend/source/sparse_write_memory.hpp')
class RelocationTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=P(self.t.name);repo=o.HERE.parents[2];locked=json.loads((o.HERE/'LOCKED_SOURCE_CONTRACT.json').read_text())['sources'];self.pins={};files=[];anchors={};generation={};catalog=[]
  for name,rel in PATHS.items():
   p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((repo/rel).read_bytes());row=dict(path=rel,bytes=p.stat().st_size,sha256=o.sha(p),origin_path='/synthetic/builder/'+rel,kind='ACTUAL_BUILD_INPUT');self.assertEqual({k:row[k]for k in('bytes','sha256')},locked[name]);files.append(row);anchors[name]=rel;generation[row['origin_path']]=row['sha256'];self.pins[str(p)]=row['sha256'];catalog.append({k:row[k]for k in('path','bytes','sha256')})
  for name in ('commands','descriptors','program_manifest'):anchors[name]='synthetic/'+name;files.append(dict(path=anchors[name],kind='RUNTIME_ONLY_CONTRACT'if name=='program_manifest'else'RUNTIME_EXPECTATION_NOT_BUILD_INPUT',**locked[name]))
  self.manifest=dict(files=files,generation_input_pins=generation,observation_policy_bindings={'P0':{'anchors':anchors}});self.catalog=dict(schema='REVIEWED_RELATIVE_SOURCE_CLOSURE_V1',files=catalog)
 def run_map(self):return o.relocation_records(self.manifest,str(self.root),self.pins,self.catalog)
 def rejects(self):
  with self.assertRaises(ValueError):self.run_map()
 def test_exact_nine_keeps_original_and_local_domains(self):
  r=self.run_map();self.assertEqual(set(r),set(PATHS))
  for name,row in r.items():self.assertEqual(row['origin_path'],'/synthetic/builder/'+PATHS[name]);self.assertEqual(row['local']['path'],str(self.root/PATHS[name]))
 def test_actual_source_mutation(self):(self.root/PATHS['helper']).write_bytes(b'wrong');self.rejects()
 def test_wrong_original_origin_even_same_bytes(self):self.manifest['files'][0]['origin_path']='/different/builder/source';self.rejects()
 def test_wrong_generation_pin(self):self.manifest['generation_input_pins'][self.manifest['files'][0]['origin_path']]='0'*64;self.rejects()
 def test_wrong_locked_role(self):self.manifest['observation_policy_bindings']['P0']['anchors']['helper']=PATHS['host_top'];self.rejects()
 def test_wrong_kind(self):self.manifest['files'][0]['kind']='RUNTIME_ONLY_CONTRACT';self.rejects()
 def test_missing_current_pin(self):self.pins.pop(str(self.root/PATHS['helper']));self.rejects()
 def test_wrong_current_catalog(self):self.catalog['files'][0]['sha256']='0'*64;self.rejects()
 def test_duplicate_catalog(self):self.catalog['files'].append(copy.deepcopy(self.catalog['files'][0]));self.rejects()
 def test_duplicate_manifest(self):self.manifest['files'].append(copy.deepcopy(self.manifest['files'][0]));self.rejects()
 def test_source_alias(self):
  p=self.root/PATHS['helper'];q=self.root/'elsewhere';p.rename(q);p.symlink_to(q);self.rejects()
 def test_root_alias(self):
  alias=self.root/'alias';alias.symlink_to(self.root)
  with self.assertRaises(ValueError):o.relocation_records(self.manifest,str(alias),self.pins,self.catalog)
 def test_path_escape(self):self.manifest['files'][0]['path']='../source';self.rejects()
 def test_no_program_relocation(self):self.assertFalse({'commands','descriptors','program_manifest'}&set(self.run_map()))
 def test_no_cloud_context_keeps_original_policy_path_gate(self):
  # source_links retains the original equality branch, without a default map.
  import inspect
  s=inspect.getsource(o.source_links);self.assertIn("if source_relocation is None:need(r['origin_path']==p['path']",s)
 def test_samejob_no_relocation(self):
  import consumer_owned as c
  from types import SimpleNamespace
  self.assertIsNone(c.approved_source_relocation(SimpleNamespace(profile=0,cloud_binding=None),{}))
 def test_cloud_without_approved_adapter_no_relocation(self):
  import consumer_owned as c
  from types import SimpleNamespace
  from unittest.mock import patch
  with patch.object(c,'cloud_invocation',return_value={'source_relocation':{'anchors':'FORGED'}}):
   self.assertIsNone(c.approved_source_relocation(SimpleNamespace(profile=0,cloud_binding=self.root/'unused'),{}))
 def test_unapproved_invocation_fails_before_source_map_or_build_check(self):
  import consumer_owned as c
  from types import SimpleNamespace
  from unittest.mock import patch
  budget=o.HERE.parent/'cloud_budget.py';b={'executor_adaptation':{'unapproved':True},'pins':{str(budget):o.sha(budget)}}
  with patch.object(c,'cloud_invocation',return_value=b),patch.object(c,'verify_local_build',side_effect=AssertionError('must reject first')):
   with self.assertRaises(ValueError):c.approved_source_relocation(SimpleNamespace(profile=0,cloud_binding=self.root/'unused'),{})
 def test_program_anchor_cannot_become_actual_source(self):
  self.manifest['files'][-1]['kind']='ACTUAL_BUILD_INPUT';self.rejects()
 def test_same_bytes_wrong_current_relative_catalog_path(self):
  row=self.catalog['files'][0];old=self.root/row['path'];new=self.root/'other/source.scala';new.parent.mkdir(parents=True);new.write_bytes(old.read_bytes());self.pins[str(new)]=row['sha256'];row['path']='other/source.scala';self.rejects()
 def test_duplicate_program_source_anchor_rejected(self):
  self.manifest['observation_policy_bindings']['P0']['anchors']['commands']=PATHS['helper'];self.rejects()
if __name__=='__main__':unittest.main()
