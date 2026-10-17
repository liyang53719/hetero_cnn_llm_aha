import hashlib,io,json,tarfile,tempfile,unittest
from pathlib import Path
import export_source as e
import preprocess_closure as pc
HERE=Path(__file__).parent
class Postprocess(unittest.TestCase):
 def test_complete_synthetic_export(self):
  # Same layout as upstream git archive plus generated target/rtl merge.
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'idma/target/rtl';source.mkdir(parents=True)
   (source/'.gitignore').write_text('*.sv\n');(source/'include').mkdir();(source/'include/.gitkeep').write_text('')
   (source/'include/idma').mkdir();(source/'include/idma/compute.svh').write_text('`include "leaf.svh"\n');(source/'include/idma/leaf.svh').write_text('// synthetic header\n')
   (source/'idma_generated.sv').write_text('`include "idma/compute.svh"\nmodule idma_backend_rw_axi; endmodule\n')
   export=root/'idma_export';export.mkdir();data=io.BytesIO()
   with tarfile.open(fileobj=data,mode='w') as tf:
    for n,b in {'Bender.lock':(HERE/'Bender.lock.expected').read_bytes(),'target/rtl/.gitignore':b'*.sv\n','target/rtl/include/.gitkeep':b''}.items():
     x=tarfile.TarInfo(n);x.size=len(b);tf.addfile(x,io.BytesIO(b))
    for n,v in e.EXCLUDED_SYMLINKS.items():
     x=tarfile.TarInfo(n);x.type=tarfile.SYMTYPE;x.linkname=v['target'];tf.addfile(x)
   e.unpack_archive(data.getvalue(),export/'idma',e.EXCLUDED_SYMLINKS)
   e.merge_generated(source,export/'idma/target/rtl',root)
   clock=export/'deps/tech_cells_generic/src/rtl/tc_clk.sv';clock.parent.mkdir(parents=True);clock.write_bytes((HERE/'fixtures/tc_clk.sv').read_bytes())
   (export/'idma.f.in').write_text('+define+TARGET_SYNTHESIS\n+incdir+@ROOT@/idma/target/rtl/include\n@ROOT@/idma/target/rtl/idma_generated.sv\n')
   sources,includes,_=pc.parse_filelist(export/'idma.f.in',export);self.assertEqual(len(pc.admission(sources,includes,export)[0]),3)
   sources,includes,defines=pc.parse_filelist(export/'idma.f.in',export);allowed,missing=pc.admission(sources,includes,export)
   closure={'schema':2,'scope':'FIXED_TRUSTED_SOURCES_NOT_FILESYSTEM_SANDBOX','profile':pc.PROFILE,'tool_sha256':pc.TOOL_SHA,'initial_filelist_defines':defines,'unresolved_lexical_includes':missing,'admitted_input_hashes':{str(p.relative_to(export)):h for p,h in allowed.items()},'actual_dependency_hashes':{str(p.relative_to(export)):h for p,h in allowed.items()},'source_files':len(sources),'include_directories':len(includes),'excluded_links_unreferenced':True,'preprocessed_stdout_bytes':0,'preprocessed_stdout_sha256':'0'*64,'private_dependency_file_sha256':'0'*64}
   (export/'SOURCE_CLOSURE.json').write_text(json.dumps(closure));(export/'SOURCE_EXPORT_POLICY.json').write_text(json.dumps({'schema':1,'excluded_idma_symlinks':e.EXCLUDED_SYMLINKS}))
   (export/'COMMITS.json').write_text(json.dumps({'idma':e.PIN,**e.DEPS}))
   manifest={str(p.relative_to(export)):e.sha(p) for p in export.rglob('*') if p.is_file()};(export/'SHA256SUMS.json').write_text(json.dumps(manifest))
   self.assertEqual(e.verify_export(export),len(manifest))
   (export/'idma/target/rtl/include/idma/leaf.svh').unlink()
   with self.assertRaises(ValueError):e.verify_export(export)
 def test_merge_rejects_conflicting_tracked_file(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a=root/'a';b=root/'b';a.mkdir();b.mkdir();(a/'x').write_text('new');(b/'x').write_text('old')
   with self.assertRaises(ValueError):e.merge_generated(a,b,root)
 def test_duplicate_archive_member_rejected(self):
  data=io.BytesIO()
  with tarfile.open(fileobj=data,mode='w') as tf:
   for _ in range(2):tf.addfile(tarfile.TarInfo('duplicate'))
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):e.unpack_archive(data.getvalue(),Path(d)/'out')
 def test_all_unsupported_include_forms_rejected(self):
  examples=['module x; `include "missing.svh"\nendmodule','`include `MACRO\n','`include \\\n "name.svh"\n','`include "name.svh" trailing;\n']
  for source in examples:
   with self.subTest(source=source):
    with self.assertRaises(ValueError):pc.literal_includes(source)
 def test_comments_and_strings_are_not_directives(self):
  s='// `include "absent1"\n/* `include "absent2" */\ninitial $display("`include \\\"absent3\\\"");\n`include "real.svh" // real\n'
  self.assertEqual(pc.literal_includes(s),['real.svh'])
if __name__=='__main__':unittest.main()
