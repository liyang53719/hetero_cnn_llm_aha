import copy,json,pathlib,tempfile,unittest
import descriptor_metadata as m
D=pathlib.Path(__file__).resolve().parent

def fixture():
 contract=json.loads((D/'PORT_CONTRACT.json').read_text())
 details=dict(schema='OBSERVED_HIGH_DESCRIPTOR_V1',qualification=m.QUAL,main='HostBlockTopV4',canonical_algorithm='CanonicalHighGate_public_semantic_methods',module_count=1,annotation_count=1,target_dir_annotation_count=1,retained_annotation_count=0,annotation_classes={'firrtl2.options.TargetDirAnnotation':1},circuit_sha256='a'*64,ordered_annotations_sha256='b'*64,low_port_source='ORIGINAL_HELPER_HASH_BOUND_EXTRACTION_NOT_FULL_LOW_REPARSE',ports=[dict(name=n,direction=v[0],width=v[1],type='Clock' if n=='clock' else 'UInt<'+str(v[1])+'>') for n,v in {**contract['old_ports'],**contract['added_ports']}.items()])
 canonical=('TEMP_CANONICAL_SOURCEINFO_TARGETDIR_ONLY_V1\nmain\tHostBlockTopV4\ncircuit\t'+'a'*64+'\nannotations_order_preserved\t'+'b'*64+'\nmodule\tHostBlockTopV4\t'+'c'*64+'\n').encode()
 return canonical,details,contract

class Descriptor(unittest.TestCase):
 def setUp(self):self.c,self.d,self.k=fixture()
 def test_full_contract(self):
  r=m.validate(self.c,self.d,self.k);self.assertEqual(r['old_ports_unchanged'],85);self.assertEqual(r['added_output_bits'],948)
 def test_old_changed_width_direction_type(self):
  for key,value in [('width',2),('direction','output'),('type','UInt<1>')]:
   d=copy.deepcopy(self.d);d['ports'][0][key]=value
   with self.assertRaises(ValueError):m.validate(self.c,d,self.k)
 def test_added_direction_width_name(self):
  for key,value in [('width',2),('direction','input'),('name','unreviewed_extra')]:
   d=copy.deepcopy(self.d);d['ports'][-1][key]=value
   with self.assertRaises(ValueError):m.validate(self.c,d,self.k)
 def test_duplicate_or_missing_port(self):
  for ports in (self.d['ports'][:-1],self.d['ports'][:-1]+[self.d['ports'][0]]):
   with self.assertRaises(ValueError):m.validate(self.c,dict(self.d,ports=ports),self.k)
 def test_metadata_injection(self):
  for key,value in [('qualification','PASS'),('module_count',True),('module_count',1056),('annotation_count',8985),('annotation_classes',{'/path/secret':1}),('ports','payload')]:
   with self.assertRaises(ValueError):m.validate(self.c,dict(self.d,**{key:value}),self.k)
  with self.assertRaises(ValueError):m.validate(self.c,dict(self.d,extra='payload'),self.k)
 def test_canonical_digest_order_and_duplicate(self):
  for b in (self.c.replace(b'annotations_order_preserved',b'reordered'),self.c.replace(b'a'*64,b'd'*64),self.c+b'module\tHostBlockTopV4\t'+b'c'*64+b'\n',self.c[:-1]):
   with self.assertRaises(ValueError):m.validate(b,self.d,self.k)
 def test_json_duplicate_rejected(self):
  with self.assertRaises(ValueError):m.obj(b'{"schema":"a","schema":"b"}')
 def test_export_exact_three_and_identity(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);work=root/'work';dd=work/'descriptor';dd.mkdir(parents=True)
   (dd/'observed-canonical.tsv').write_bytes(self.c);(dd/'observed-details.json').write_text(json.dumps(self.d))
   (dd/'secret.raw.log').write_text('must not export')
   diag=work/'original_ir'/'host-diagnostic';diag.mkdir(parents=True)
   for n in m.INPUTS:(diag/n).write_bytes(b'x')
   artifacts={n:m.pin(b'x') for n in m.INPUTS}
   receipt=m.inspect(dd,artifacts,self.k)
   identity=dict(source_commit='a'*40,launch_commit='b'*40,launch_manifest_blob_sha='c'*40,run_id=1)
   summary=dict(identity,status='COMPLETE_ORIGINAL_HIGH_AND_OFFICIAL_LOW_DIAGNOSTIC_ONLY',artifacts=artifacts,descriptor=receipt,**{k:False for k in ('numerical_pass','canonical_pass','target_host_qualified','sv_generated','generated_abi_qualification','physical_resource_or_qor_qualification','block_numerical_pass')})
   out=root/'export';m.export(work,summary,identity,self.k,out);self.assertEqual({p.name for p in out.iterdir()},{*m.FILES,'provenance.json'})
   with self.assertRaises(ValueError):m.export(work,summary,identity,self.k,out)
   with self.assertRaises(ValueError):m.export(work,dict(summary,run_id=2),identity,self.k,root/'wrong')
   (dd/'observed-details.json').write_text(json.dumps(dict(self.d,module_count=2)))
   with self.assertRaises(ValueError):m.export(work,summary,identity,self.k,root/'drift')
 def test_changed_bound_input(self):
  with tempfile.TemporaryDirectory() as t:
   r=pathlib.Path(t)
   for n in m.INPUTS:(r/n).write_bytes(b'x')
   expected={n:m.pin(b'x') for n in m.INPUTS};m.verify_inputs(r,expected)
   (r/m.INPUTS[0]).write_bytes(b'y')
   with self.assertRaises(ValueError):m.verify_inputs(r,expected)
 def test_symlink_and_size(self):
  with tempfile.TemporaryDirectory() as t:
   r=pathlib.Path(t);(r/'real').write_bytes(b'abc');(r/'link').symlink_to(r/'real')
   with self.assertRaises(ValueError):m.read(r/'link',10)
   with self.assertRaises(ValueError):m.read(r/'real',2)
 def test_source_uses_original_public_api(self):
  s=(D/'ObservedHighDescriptor.scala').read_text()
  for method in ('moduleSemanticSha','circuitSemanticSha','annotationSemanticSha'):self.assertIn('CanonicalHighGate.'+method,s)
  for bad in ('CanonicalHighGate.main','==1056','==8985','SystemVerilogEmitter'):self.assertNotIn(bad,s)
  self.assertIn('portCircuit',s);self.assertIn('CREATE_NEW',s)
 def test_stage_bounds_and_exact_artifact_paths(self):
  s=(D/'run_ir_only.py').read_text();self.assertEqual(s.count("stage('compile155'"),1);self.assertIn("stage('helper_compile'",s);self.assertIn("stage('descriptor'",s)
  w=(D.parents[1]/'.github/workflows/hetero-observer-original-ir-only.yml').read_text()
  for name in (*m.FILES,'provenance.json'):self.assertIn('/observer-descriptor-metadata/'+name,w)
  self.assertNotIn('/observer-descriptor-metadata/*',w)

if __name__=='__main__':unittest.main()
