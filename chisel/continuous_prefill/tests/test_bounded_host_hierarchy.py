# SPDX-License-Identifier: Apache-2.0
"""Build orchestration tests only; dummy archives are not hardware evidence."""
from pathlib import Path
import importlib.util,json,subprocess,sys,tempfile,unittest
SCRIPT=Path(__file__).resolve().parents[1]/'scripts/build_host_hierarchy_bounded.py'
spec=importlib.util.spec_from_file_location('bounded_host_hierarchy',SCRIPT);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class BoundedBuildTests(unittest.TestCase):
 def test_leaf_order_and_invalid_graphs(self):
  self.assertEqual(mod.graph('b/libb.a: b/x.mk a/liba.a\na/liba.a: a/x.mk\n'),['a/liba.a','b/libb.a'])
  for text in ('a/liba.a: b/libb.a\nb/libb.a: a/liba.a','a/liba.a: b/libb.a','../a/liba.a:','not a make graph'):
   with self.subTest(text=text),self.assertRaises(ValueError):mod.graph(text)
 def test_cleanup_preserves_libraries_rtl_and_symlinks(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);obj=root/'obj';obj.mkdir();rtl=root/'top.sv';rtl.write_text('module top; endmodule\n')
   library=obj/'libtop.a';library.write_bytes(b'archive test sentinel');pch=obj/'top.fast.gch';pch.write_bytes(b'rebuildable test sentinel')
   protected=root/'outside.gch';protected.write_bytes(b'keep');link=obj/'linked.gch';link.symlink_to(protected)
   freed=mod.clean(obj,root/'cleanup.json',rtl)
   self.assertEqual(freed,len(b'rebuildable test sentinel'));self.assertFalse(pch.exists());self.assertTrue(link.is_symlink());self.assertEqual(protected.read_bytes(),b'keep')
   self.assertEqual(library.read_bytes(),b'archive test sentinel');self.assertTrue(json.loads((root/'cleanup.json').read_text())['retained_hashes_equal'])
 def test_serial_make_and_bounded_cleanup(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);obj=root/'obj';obj.mkdir();(root/'generated').mkdir();(root/'generated/HostBlockTop.sv').write_text('module HostBlockTop; endmodule\n')
   (obj/'VHostBlockTop_hier.mk').write_text('b/libb.a: a/liba.a\n\tmkdir -p b; printf b > $@; printf pch > b/b.fast.gch\na/liba.a:\n\tmkdir -p a; printf a > $@; printf pch > a/a.fast.gch\n')
   (obj/'VHostBlockTop.mk').write_text('VHostBlockTop: a/liba.a b/libb.a\n\tprintf test_program > $@; printf pch > top.fast.gch\n')
   subprocess.run([sys.executable,str(SCRIPT),str(root),'--reserve-bytes','0'],check=True,stdout=subprocess.DEVNULL)
   result=json.loads((root/'bounded_build/result.json').read_text())
   self.assertEqual([x['target'] for x in result['stages']],['a/liba.a','b/libb.a','VHostBlockTop']);self.assertEqual(result['jobs'],1)
   self.assertEqual((obj/'VHostBlockTop').read_bytes(),b'test_program');self.assertFalse(list(obj.rglob('*.gch')))

if __name__=='__main__':unittest.main()
