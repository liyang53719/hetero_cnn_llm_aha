import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import preprocess_closure as p
class Preprocess(unittest.TestCase):
 def test_literal_comment_and_paste(self):
  text='// `include "ignored"\n`define X /``* legal *``/\n`define PORT(n) m_axi_``n``\n`include "ok.svh"\n'
  self.assertEqual(p.literal_includes(text),['ok.svh'])
 def test_unsupported_include_and_line(self):
  for text in ['`include `DYNAMIC\n','module x; `include "x"\n','`include "../x"\n','`include "/etc/passwd"\n','`line 1 "forged" 1\n']:
   with self.subTest(text=text),self.assertRaises(ValueError):p.literal_includes(text)
 def test_filelist_rejects_flags(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);f=root/'f'
   for text in ['-f bad','--cc','@ROOT@/../escape','+define+X=`DYNAMIC','+define+X=1+X=2']:
    f.write_text(text)
    with self.assertRaises(ValueError):p.parse_filelist(f,root)
 def test_filelist_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'x').symlink_to('/etc/passwd');(root/'f').write_text('@ROOT@/x')
   with self.assertRaises(ValueError):p.parse_filelist(root/'f',root)
 def test_admission_pins_all_headers_and_no_conditional_guess(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=root/'x.sv';s.write_text('`ifdef UVM\n`include "uvm_macros.svh"\n`endif\n');(root/'leaf.svh').write_text('// fixed header')
   allowed,missing=p.admission([s],[root],root);self.assertEqual(len(allowed),2);self.assertEqual(missing,['uvm_macros.svh'])
 def test_fake_preprocess_evidence_roundtrip(self):
  # Fake callback tests artifact logic only; no tool or subprocess is executed.
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);root=base/'export';root.mkdir();tool=base/'tool';tool.write_bytes(b'fake');s=root/'x.sv';s.write_text('`include "h.svh"\n');h=root/'h.svh';h.write_text('// header');f=root/'idma.f.in';f.write_text('+incdir+@ROOT@\n@ROOT@/x.sv\n')
   # root include notation must use the admitted trailing slash syntax.
   f.write_text('+incdir+@ROOT@/\n@ROOT@/x.sv\n')
   def run(argv,cwd):
    self.assertNotIn('-P',argv);self.assertNotIn('-f',argv);self.assertIn('-E',argv)
    mdir=Path(argv[argv.index('--Mdir')+1]);(mdir/'Vidma_source__ver.d').write_text(str(mdir/'Vidma_source')+': '+str(tool)+' '+str(s)+' '+str(h)+'\n');return b'preprocessed fixture\n'
   with patch.object(p,'TOOL_SHA',p.sha(tool)):
    record=p.generate(f,root,tool,base/'work',run);self.assertTrue(p.verify_record(root,record));self.assertEqual(len(record['actual_dependency_hashes']),2)
    record['actual_dependency_hashes']['../outside']='0'*64
    with self.assertRaises(ValueError):p.verify_record(root,record)
 def test_dependency_outside_and_ambiguous_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);mdir=root/'obj';mdir.mkdir();f=root/'deps';tool=root/'tool'
   for content in [str(mdir/'x')+': /etc/passwd\n','bad: a:b\n','/tmp/outside: '+str(tool)+'\n']:
    f.write_text(content)
    with self.assertRaises(ValueError):p.parse_dependencies(f,root,mdir,tool,{})
 def test_source_line_in_extra_header_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);s=root/'x.sv';s.write_text('module x;endmodule');(root/'unused.svh').write_text('`line 5 "forged" 1')
   with self.assertRaises(ValueError):p.admission([s],[root],root)
if __name__=='__main__':unittest.main()
