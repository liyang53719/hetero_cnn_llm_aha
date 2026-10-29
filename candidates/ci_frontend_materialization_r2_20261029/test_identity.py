import io,unittest
from sv_comment_only_identity import digest
class Tests(unittest.TestCase):
 def test_all_observed_shapes(self):
  for loc in ['63:28','63:{28,44}','63:28 61:74','63:28 42:56 63:73','63:{28,44} 61:74','63:28 61:{2,4}','63:{2,4,6}','63:28 other/B.scala 9:1']:
   a=('wire x; // @[original/dir/A.scala '+loc+']\n').encode();b=a.replace(b'original/dir/',b'runner/new/').replace(b'other/',b'runner2/')
   self.assertEqual(digest(io.BytesIO(a)),digest(io.BytesIO(b)),loc)
 def test_all_nondirectory_changes_rejected(self):
  base=b'wire [3:0] x = 4\'d3; // @[a/A.scala 63:{28,44} 61:74]\n'
  for a,b in [(b'3:0',b'4:0'),(b"4'd3",b"4'd4"),(b'=',b'+'),(b'A.scala',b'B.scala'),(b'28,44',b'28,45'),(b'61:74',b'61:75')]:self.assertNotEqual(digest(io.BytesIO(base)),digest(io.BytesIO(base.replace(a,b))))
 def test_pragmas_strings_and_unknown_preserved(self):
  for a,b in [(b'// verilator public\n',b'// verilator clock_enable\n'),(b'// synthesis translate_off\n',b'// synthesis translate_on\n'),(b'"a/A.scala 3:4"',b'"b/A.scala 3:4"'),(b'/* @[a/A.scala 3:4] */',b'/* @[b/A.scala 3:4] */'),(b'// @[a/A.scala {3,4}:7]\n',b'// @[b/A.scala {3,4}:7]\n')]:self.assertNotEqual(digest(io.BytesIO(a)),digest(io.BytesIO(b)))
if __name__=='__main__':unittest.main()
