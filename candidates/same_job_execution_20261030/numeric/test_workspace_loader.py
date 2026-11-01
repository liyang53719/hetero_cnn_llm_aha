"""Synthetic pinned metadata and fake ELF reader; never runs loader or binary."""
import json,pathlib,tempfile,unittest
import workspace_loader as w
P=pathlib.Path
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.base=P(self.t.name);self.root=self.base/'libs';self.root.mkdir();self.art=self.base/'artifact';self.art.mkdir()
  self.binary=self.art/'dut.bin';self.binary.write_bytes(b'SYNTHETIC-NOT-ELF');self.tool=self.art/'tool_manifest.json';self.provenance=self.base/'provenance.json';self.provenance.write_text('{"synthetic":true}')
  self.libs={};pins={}
  for name in sorted(w.SONAMES):
   target='libstdc++.so.6.0.33'if name=='libstdc++.so.6'else name;p=self.root/target;p.write_bytes(('SYNTHETIC '+name).encode());original='/usr/lib/x86_64-linux-gnu/'+target
   self.libs[name]={'pin':self.pin(p),'original_resolved':original};pins[original]=w.sha(p)
  (self.root/'libstdc++.so.6').symlink_to('libstdc++.so.6.0.33')
  self.tool.write_text(json.dumps({'schema':'INSTALLED_GNU_BUILD_TOOLS_V1','pins':pins}));self.frozen=self.art/'frozen_artifact.json';self.frozen_doc={'artifact_identity':{'source_commit':'a'*40},'common':{'binary':{'sha256':w.sha(self.binary)}},'tool_manifest':{'sha256':w.sha(self.tool)}};self.frozen.write_text(json.dumps(self.frozen_doc))
  self.doc=dict(schema='PINNED_WORKSPACE_ELF_STARTUP_V1',scope='ORIGINAL_BUILDER_DSO_BYTES_NOT_NUMERICAL',builder_source_commit='a'*40,artifact_manifest_sha256=w.sha(self.frozen),binary=self.pin(self.binary),tool_manifest=self.pin(self.tool),root=str(self.root),libraries=self.libs,aliases={'libstdc++.so.6':'libstdc++.so.6.0.33'},provenance=self.pin(self.provenance),later_dlopen='NOT_QUALIFIED',numerical_pass=False)
  self.path=self.base/'workspace.json';self.calls=[];self.save()
 def pin(self,p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':w.sha(p)}
 def save(self):self.path.write_text(json.dumps(self.doc));self.contract=self.pin(self.path)
 def reader(self,p,require_interpreter=True):
  self.calls.append((str(p),require_interpreter));return {'needed':sorted(w.SONAMES)if require_interpreter else ['libc.so.6']}
 def verify(self,reader=None):return w.verify(self.contract,self.binary,w.sha(self.binary),self.tool,w.sha(self.tool),reader or self.reader)
 def rejects(self):
  with self.assertRaises((ValueError,KeyError)):self.verify()
 def test_exact_six_original_objects(self):
  v=self.verify();self.assertEqual(len(self.calls),7);self.assertEqual(set(v['libraries']),w.SONAMES);self.assertEqual(w.prefix(v),[str(self.root/'ld-linux-x86-64.so.2'),'--inhibit-cache','--library-path',str(self.root)])
 def test_external_contract_pin(self):self.contract['sha256']='0'*64;self.rejects()
 def test_library_bytes_tamper(self):(self.root/'libc.so.6').write_bytes(b'wrong');self.rejects()
 def test_builder_tool_pin_different(self):
  d=json.loads(self.tool.read_text());d['pins'][self.libs['libc.so.6']['original_resolved']]='0'*64;self.tool.write_text(json.dumps(d));self.doc['tool_manifest']=self.pin(self.tool);self.frozen_doc['tool_manifest']['sha256']=w.sha(self.tool);self.frozen.write_text(json.dumps(self.frozen_doc));self.doc['artifact_manifest_sha256']=w.sha(self.frozen);self.save();self.rejects()
 def test_wrong_binary_argument_hash(self):
  with self.assertRaises(ValueError):w.verify(self.contract,self.binary,'0'*64,self.tool,w.sha(self.tool),self.reader)
 def test_wrong_tool_argument_hash(self):
  with self.assertRaises(ValueError):w.verify(self.contract,self.binary,w.sha(self.binary),self.tool,'0'*64,self.reader)
 def test_manifest_source_join(self):self.doc['builder_source_commit']='b'*40;self.save();self.rejects()
 def test_manifest_pin(self):self.doc['artifact_manifest_sha256']='0'*64;self.save();self.rejects()
 def test_manifest_binary_join(self):
  self.frozen_doc['common']['binary']['sha256']='0'*64;self.frozen.write_text(json.dumps(self.frozen_doc));self.doc['artifact_manifest_sha256']=w.sha(self.frozen);self.save();self.rejects()
 def test_unknown_library(self):self.doc['libraries']['evil.so']=self.libs['libc.so.6'];self.save();self.rejects()
 def test_extra_file(self):(self.root/'evil').write_bytes(b'no');self.rejects()
 def test_hwcaps_directory(self):(self.root/'glibc-hwcaps').mkdir();self.rejects()
 def test_alias_absolute_rejected(self):
  p=self.root/'libstdc++.so.6';p.unlink();p.symlink_to(self.root/'libstdc++.so.6.0.33');self.rejects()
 def test_alias_regular_file_rejected(self):
  p=self.root/'libstdc++.so.6';p.unlink();p.write_bytes(b'no');self.rejects()
 def test_alias_contract_drift(self):self.doc['aliases']={};self.save();self.rejects()
 def test_private_root_alias(self):
  alias=self.base/'alias';alias.symlink_to(self.root);self.doc['root']=str(alias);self.save();self.rejects()
 def test_library_pin_symlink_rejected(self):self.doc['libraries']['libstdc++.so.6']['pin']=self.pin(self.root/'libstdc++.so.6');self.save();self.rejects()
 def test_original_noncanonical_path(self):self.libs['libc.so.6']['original_resolved']='/usr/lib/x86_64-linux-gnu/../libc.so.6';self.save();self.rejects()
 def test_original_role_basename_mismatch_even_hash_pinned(self):
  d=json.loads(self.tool.read_text());wrong='/usr/lib/x86_64-linux-gnu/wrong.so';d['pins'][wrong]=self.libs['libc.so.6']['pin']['sha256'];self.libs['libc.so.6']['original_resolved']=wrong
  self.tool.write_text(json.dumps(d));self.doc['tool_manifest']=self.pin(self.tool);self.frozen_doc['tool_manifest']['sha256']=w.sha(self.tool);self.frozen.write_text(json.dumps(self.frozen_doc));self.doc['artifact_manifest_sha256']=w.sha(self.frozen);self.save()
  with self.assertRaisesRegex(ValueError,'SONAME-to-basename'):self.verify()
 def test_bad_dependency_closure(self):
  def reader(p,require_interpreter=True):return {'needed':sorted(w.SONAMES)if require_interpreter else ['evil.so']}
  with self.assertRaises(ValueError):self.verify(reader)
 def test_binary_missing_direct_dependency(self):
  def reader(p,require_interpreter=True):return {'needed':['libc.so.6']}
  with self.assertRaises(ValueError):self.verify(reader)
 def test_not_numeric_or_dlopen_qualification(self):
  for k,v in [('numerical_pass',True),('later_dlopen','PASS')]:
   old=self.doc[k];self.doc[k]=v;self.save();self.rejects();self.doc[k]=old
 def observed(self,p):return {**self.pin(P(p).resolve()),'path':str(p),'resolved':str(P(p).resolve())}
 def test_actual_resolved_closure(self):
  v=self.verify();paths={n:str(self.root/n)for n in w.SONAMES};r=w.resolved_libraries(paths,v,self.observed);self.assertEqual(set(r),w.SONAMES)
 def test_actual_system_fallback_rejected(self):
  v=self.verify();paths={n:str(self.root/n)for n in w.SONAMES};outside=self.base/'libc.so.6';outside.write_bytes((self.root/'libc.so.6').read_bytes());paths['libc.so.6']=str(outside)
  with self.assertRaises(ValueError):w.resolved_libraries(paths,v,self.observed)
 def test_actual_extra_or_missing_resolution(self):
  v=self.verify();paths={n:str(self.root/n)for n in w.SONAMES};paths.pop('libm.so.6')
  with self.assertRaises(ValueError):w.resolved_libraries(paths,v,self.observed)
 def test_actual_pin_drift(self):
  v=self.verify();paths={n:str(self.root/n)for n in w.SONAMES}
  def pin(p):return dict(self.observed(p),sha256='0'*64)
  with self.assertRaises(ValueError):w.resolved_libraries(paths,v,pin)
if __name__=='__main__':unittest.main()
