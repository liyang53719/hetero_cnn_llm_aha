import unittest,tempfile,json,hashlib,copy
from pathlib import Path
from prefix import validate_prefix
class Prefix(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.p=Path(self.t.name);(self.p/'m').mkdir();(self.p/'m'/'n.partial').write_bytes(b'abcdefgh')
  self.s={'model':'m','name':'n','bytes':12,'start':100,'end':111,'shard_bytes':200,'url':'https://huggingface.co/pinned'}
  self.rows=[{'identity':'shard-header','url':self.s['url'],'status_check':'PASS_RANGE_BYTES_ONLY','etag':'E','sha256':'H'}]
  for start,b in [(100,b'abcd'),(104,b'efgh')]:
   self.rows.append({'identity':'n','url':self.s['url'],'status_check':'PASS_RANGE_BYTES_ONLY','etag':'E','status':206,'start':start,'end':start+3,'bytes':4,'expected_bytes':4,'content_length':'4','content_range':f'bytes {start}-{start+3}/200','sha256':hashlib.sha256(b).hexdigest()})
  (self.p/'ACQUISITION_PLAN.json').write_text(json.dumps({'specs':[self.s]}))
 def tearDown(self):self.t.cleanup()
 def run_check(self):
  (self.p/'requests.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in self.rows));return validate_prefix(self.p,self.s,'E','H')
 def test_valid(self):self.assertEqual(len(self.run_check()[1]),2)
 def test_missing(self):self.rows.pop(1);self.assertRaises(ValueError,self.run_check)
 def test_wrong_hash(self):self.rows[1]['sha256']='bad';self.assertRaises(ValueError,self.run_check)
 def test_truncated(self):(self.p/'m'/'n.partial').write_bytes(b'abcdef');self.assertRaises(ValueError,self.run_check)
 def test_overlap(self):self.rows.append(copy.deepcopy(self.rows[1]));self.assertRaises(ValueError,self.run_check)
 def test_etag(self):self.rows[2]['etag']='other';self.assertRaises(ValueError,self.run_check)
 def test_header(self):self.rows[0]['sha256']='other';self.assertRaises(ValueError,self.run_check)
 def test_unreceipted(self):(self.p/'m'/'n.partial').write_bytes(b'abcdefghi');self.assertRaises(ValueError,self.run_check)
 def test_size(self):self.rows[1]['content_length']='8';self.assertRaises(ValueError,self.run_check)
 def test_failed_not_used(self):self.rows[2]['status_check']='FAIL';self.assertRaises(ValueError,self.run_check)
if __name__=='__main__':unittest.main()
