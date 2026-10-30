import ast,importlib.util,pathlib,unittest
# Public, synthetic GNU readelf/ldd text only. Not captured runtime evidence.
# Resolve the sibling helper, independent of checkout path and current directory.
SOURCE=pathlib.Path(__file__).resolve().with_name('fresh_host.py')
s=importlib.util.spec_from_file_location('zero_needed_candidate',SOURCE);h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
D="""Dynamic section at offset 0x1000 contains 20 entries:
  Tag        Type                         Name/Value
 0x000000000000000c (INIT)               0x1000
 0x000000000000000d (FINI)               0x1010
 0x0000000000000019 (INIT_ARRAY)         0x2000
 0x000000000000001b (INIT_ARRAYSZ)       8 (bytes)
 0x000000000000001a (FINI_ARRAY)         0x2008
 0x000000000000001c (FINI_ARRAYSZ)       8 (bytes)
 0x000000006ffffef5 (GNU_HASH)           0x260
 0x0000000000000005 (STRTAB)             0x300
 0x0000000000000006 (SYMTAB)             0x280
 0x000000000000000a (STRSZ)              32 (bytes)
 0x000000000000000b (SYMENT)             24 (bytes)
 0x0000000000000003 (PLTGOT)             0x2100
 0x0000000000000002 (PLTRELSZ)           24 (bytes)
 0x0000000000000014 (PLTREL)             RELA
 0x0000000000000017 (JMPREL)             0x400
 0x0000000000000007 (RELA)               0x500
 0x0000000000000008 (RELASZ)             24 (bytes)
 0x0000000000000009 (RELAENT)            24 (bytes)
 0x000000006ffffff9 (RELACOUNT)          1
 0x0000000000000000 (NULL)               0x0
"""
H="""ELF Header:
  Class:                             ELF64
  Type:                              DYN (Shared object file)
  Machine:                           Advanced Micro Devices X86-64
  Number of program headers:         9
"""
P="""Elf file type is DYN (Shared object file)
Entry point 0x0
There are 9 program headers, starting at offset 64

Program Headers:
  Type           Offset   VirtAddr           PhysAddr           FileSiz  MemSiz   Flg Align
  LOAD           0x000000 0x0000000000000000 0x0000000000000000 0x000600 0x000600 R   0x1000
  LOAD           0x001000 0x0000000000001000 0x0000000000001000 0x000200 0x000200 R E 0x1000
  LOAD           0x002000 0x0000000000002000 0x0000000000002000 0x000100 0x000100 R   0x1000
  LOAD           0x003000 0x0000000000003000 0x0000000000003000 0x000300 0x000308 RW  0x1000
  DYNAMIC        0x003010 0x0000000000003010 0x0000000000003010 0x000180 0x000180 RW  0x8
  NOTE           0x000238 0x0000000000000238 0x0000000000000238 0x000024 0x000024 R   0x4
  GNU_EH_FRAME   0x002040 0x0000000000002040 0x0000000000002040 0x000030 0x000030 R   0x4
  GNU_STACK      0x000000 0x0000000000000000 0x0000000000000000 0x000000 0x000000 RW  0x10
  GNU_RELRO      0x003000 0x0000000000003000 0x0000000000003000 0x000200 0x000200 R   0x1
"""
L="\tstatically linked\n"
class Tests(unittest.TestCase):
 def check(self,role='PYTHON_EXTENSION',loaded=True,dynamic=D,header=H,programs=P,ldd=L):return h.loaded_python_zero_needed_class(role,loaded,dynamic,header,programs,ldd)
 def reject(self,**kw):
  with self.assertRaises(h.DependencyRejected) as got:self.check(**kw)
  self.assertEqual(got.exception.rejection_kind,'EMPTY_DEPENDENCY_LIST')
 def test_synthetic_loaded_python_dso_zero_needed_classification(self):self.assertEqual(self.check(),'LOADED_PYTHON_DSO_NO_DT_NEEDED')
 def test_wrong_roles(self):
  for role in h.QUERY_ROLES-{'PYTHON_EXTENSION'}:
   with self.subTest(role=role):self.reject(role=role)
 def test_not_currently_loaded(self):self.reject(loaded=False)
 def test_truthy_not_boolean(self):self.reject(loaded=1)
 def test_et_exec_rejected(self):self.reject(header=H.replace('DYN (Shared object file)','EXEC (Executable file)'))
 def test_missing_elf_header_rejected(self):self.reject(header='')
 def test_missing_dynamic_table(self):self.reject(dynamic='There is no dynamic section in this file.\n')
 def test_forbidden_loader_tags(self):
  for tag in ('NEEDED','FILTER','AUXILIARY','AUDIT','DEPAUDIT'):
   with self.subTest(tag=tag):self.reject(dynamic=D.replace('(INIT)', '('+tag+')',1))
 def test_truncated_dynamic_table(self):self.reject(dynamic='\n'.join(D.splitlines()[:-1]))
 def test_dynamic_count_mismatch(self):self.reject(dynamic=D.replace('contains 20 entries','contains 21 entries'))
 def test_dynamic_count_bound(self):self.reject(dynamic=D.replace('contains 20 entries','contains 513 entries'))
 def test_premature_null(self):self.reject(dynamic=D.replace('(INIT)','(NULL)',1))
 def test_multiple_dynamic_tables(self):self.reject(dynamic=D+D)
 def test_pt_interp(self):self.reject(programs=P.replace('  NOTE ', '  INTERP ',1))
 def test_interpreter_request_text(self):self.reject(programs=P+'\n[Requesting program interpreter: ignored]\n')
 def test_missing_program_table(self):self.reject(programs='')
 def test_truncated_program_table(self):self.reject(programs=P.replace('  NOTE           0x000238','  REMOVED           XX000238'))
 def test_ldd_exact_supported_output_only(self):
  for output in ('','\n','not a dynamic executable','statically linked\nlibx.so => not found','statically linked\nextra','linux-vdso.so.1 (0x123)'):
   with self.subTest(output=output):self.reject(ldd=output)
 def test_ordinary_empty_dependency_list_still_rejected(self):
  with self.assertRaises(h.DependencyRejected):h.dependency_paths('statically linked\n')
 def test_integration_still_requires_current_native_and_successful_queries(self):
  text=SOURCE.read_text();ast.parse(text)
  self.assertIn("r.returncode==0",text);self.assertIn('(not strict_stderr or not r.stderr)',text);self.assertIn("role=='PYTHON_EXTENSION' and p in native and output.strip()=='statically linked'",text)
  self.assertIn("classification=loaded_python_zero_needed_class(role,p in native,dynamic,header,programs,output)",text)
  self.assertIn("dependency_classes[pins[str(p)]]=classification",text)
  self.assertIn("tools=[P(sys.executable)",text);self.assertIn("p=add(p)",text)
  self.assertIn("paths=dependency_paths(output)",text);self.assertIn('for dep in paths:add(dep,dependency=True)',text)
  self.assertIn('total<=3*1024**3',text);self.assertIn('time.monotonic()-start<240',text)
if __name__=='__main__':unittest.main()
