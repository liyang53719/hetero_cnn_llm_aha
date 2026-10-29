"""Mock loader-resolution boundary; never executes loader or DUT."""
import unittest,tempfile,pathlib,json,unittest.mock as mock
import runtime_abi as a
P=pathlib.Path
class T(unittest.TestCase):
 def fixture(self,root):
  files={}
  for n in ('dut','loader','libc.so.6','cache'):
   files[n]=root/n;files[n].write_bytes(n.encode())
  info={'interpreter':str(files['loader']),'needed':['libc.so.6'],'machine':'ELF64_LE_X86_64'}
  tool=root/'tool.json';tool.write_text(json.dumps({'schema':'INSTALLED_GNU_BUILD_TOOLS_V1','pins':{str(files[n]):a.sha(files[n])for n in ('loader','libc.so.6')}}));receipt=root/'abi.json'
  text=f"linux-vdso.so.1 (0x1)\nlibc.so.6 => {files['libc.so.6']} (0x2)\n{files['loader']} (0x3)\n"
  return files,tool,receipt,info,text
 def run_case(self,mutation=None):
  with tempfile.TemporaryDirectory()as d:
   f,t,r,i,text=self.fixture(P(d));binary_sha=a.sha(f['dut']);tool_sha=a.sha(t)
   def cfg():return {'cache':a.pin(f['cache']),'preload':None}
   with mock.patch.object(a,'elf_info',return_value=i),mock.patch.object(a,'_list',return_value=text)as probe,mock.patch.object(a,'config_pins',side_effect=cfg):
    a.prepare(f['dut'],binary_sha,t,tool_sha,r);probe.assert_called_once()
    if mutation:mutation(f,t,r)
    return a.verify(r,a.sha(r),f['dut'],binary_sha,t,tool_sha)
 def test_prepared_receipt_verified(self):self.assertEqual(self.run_case()['libraries'],2)
 def test_library_drift(self):
  with self.assertRaises(ValueError):self.run_case(lambda f,t,r:f['libc.so.6'].write_bytes(b'drift'))
 def test_cache_drift(self):
  with self.assertRaises(ValueError):self.run_case(lambda f,t,r:f['cache'].write_bytes(b'drift'))
 def test_environment_drift(self):
  def mutate(f,t,r):
   x=json.loads(r.read_text());x['environment']['LD_PRELOAD']='/forbidden/x.so';r.write_text(json.dumps(x))
  with self.assertRaises(ValueError):self.run_case(mutate)
 def test_tool_manifest_drift(self):
  with self.assertRaises(ValueError):self.run_case(lambda f,t,r:t.write_text('{}'))
 def test_missing_library_loader_and_scope(self):
  def change(kind):
   def mutation(f,t,r):
    x=json.loads(r.read_text())
    if kind=='missing':x['libraries'].pop('libc.so.6')
    elif kind=='loader':x['loader']=x['libraries']['libc.so.6']
    elif kind=='no_loader':x['libraries'].pop('loader')
    else:x['later_dlopen']='PASS'
    r.write_text(json.dumps(x))
   return mutation
  for kind in ('missing','loader','no_loader','scope'):
   with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_case(change(kind))
if __name__=='__main__':unittest.main()
