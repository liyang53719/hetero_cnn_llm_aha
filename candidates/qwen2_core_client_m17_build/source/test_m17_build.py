"""Only tiny synthetic files; no compiler, executable, model, or actual artifacts.
Retained stage fixtures are deliberately opaque bytes: qualification is hash-only.
"""
import ast,copy,hashlib,importlib.util,os,struct,tempfile,unittest
from pathlib import Path
from unittest import mock
s=importlib.util.spec_from_file_location('check_m17_build',Path(__file__).with_name('check_m17_build.py'));c=importlib.util.module_from_spec(s);s.loader.exec_module(c)

def elf_header(typ,entry,pho,sho,pn,sn,ssi):
 return struct.pack('<16sHHIQQQIHHHHHH',b'\x7fELF\x02\x01\x01'+b'\0'*9,typ,62,1,entry,pho,sho,0,64,56 if pn else 0,pn,64,sn,ssi)
def sh(kind,off,size,flags=0,addr=0,link=0,info=0,align=1,ent=0):return struct.pack('<IIQQQQIIQQ',0,kind,flags,addr,off,size,link,info,align,ent)
def object_blob():
 b=bytearray(512);b[:64]=elf_header(1,0,0,256,0,4,2);b[64:72]=b'NOT_CODE';b[72:75]=b'\0x\0';b[80:128]=bytes(24)+struct.pack('<IBBHQQ',1,0x12,0,1,0,4)
 b[256:512]=sh(0,0,0,align=0)+sh(1,64,8,6)+sh(3,72,3)+sh(2,80,48,link=2,info=1,align=8,ent=24);return bytes(b)
def executable_blob():
 b=bytearray(4096);b[:64]=elf_header(3,0x400800,64,0x900,4,7,4)
 interp=b'/lib64/ld-linux-x86-64.so.2\0';strings=b'\0libstdc++.so.6\0libc.so.6\0';symbols=b'\0main\0_ZN22VOrderedQkBehaviorCoreC1Ev\0';secstrings=b'\0.text\0.symtab\0.strtab\0.shstrtab\0.dynamic\0.dynstr\0'
 ph=[(1,5,0,0x400000,0x400000,4096,4096,4096),(3,4,0x200,0x400200,0x400200,len(interp),len(interp),1),(2,4,0x240,0x400240,0x400240,80,80,8),(0x6474e551,6,0,0,0,0,0,16)]
 for i,v in enumerate(ph):b[64+i*56:64+(i+1)*56]=struct.pack('<IIQQQQQQ',*v)
 b[0x200:0x200+len(interp)]=interp;b[0x300:0x300+len(strings)]=strings;b[0x400:0x400+len(symbols)]=symbols;b[0x600:0x600+len(secstrings)]=secstrings
 dyn=[(1,1),(1,strings.index(b'libc.so.6')),(5,0x400300),(10,len(strings)),(0,0)]
 for i,v in enumerate(dyn):b[0x240+i*16:0x250+i*16]=struct.pack('<qQ',*v)
 b[0x500:0x548]=bytes(24)+struct.pack('<IBBHQQ',1,0x12,0,1,0x400800,4)+struct.pack('<IBBHQQ',6,0x12,0,1,0x400810,4)
 b[0x800:0x820]=b'NOT_EXECUTABLE_SYNTHETIC_FIXTURE!!'
 ss=[sh(0,0,0,align=0),sh(1,0x800,32,6,0x400800),sh(2,0x500,72,link=3,info=1,align=8,ent=24),sh(3,0x400,len(symbols)),sh(3,0x600,len(secstrings)),sh(6,0x240,80,2,0x400240,link=6,align=8,ent=16),sh(3,0x300,len(strings),2,0x400300)]
 b[0x900:0x900+7*64]=b''.join(ss);return bytes(b)

class Fixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.build=self.root/'build';self.build.mkdir();staged=[]
  for name in sorted(c.STAGED_BASENAMES):
   blob=('OPAQUE SYNTHETIC RETAINED OR SOURCE INPUT: '+name+'\n').encode();p=self.build/name;p.write_bytes(blob)
   staged.append({'relative':'build/'+name,'path':'/not-read-retained-original/'+name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
  self.obj=self.root/c.OBJECT;self.obj.write_bytes(object_blob());self.dep=self.root/c.DEPENDENCY;self.dep.write_text('m17_main.o: m17_main.cpp\n');self.exe=self.root/c.EXECUTABLE;self.exe.write_bytes(executable_blob());self.exe.chmod(0o700)
  self.m={'staged_inputs':staged,'build_plan':{'translation_unit':{'object':c.OBJECT,'dependency':c.DEPENDENCY,'source':str(self.build/'m17_main.cpp'),'target':'m17_main.o'},'executable':c.EXECUTABLE,'dependency_cwd':'build','model_symbol_prefix':'VOrderedQkBehaviorCore','allowed_dependency_pins':[]}}
 def tearDown(self):self.tmp.cleanup()
 def check(self):return c.check(self.root,self.m)
 def reject(self):
  with self.assertRaises((ValueError,OSError)):self.check()
 def mutate(self,p,offset,data):
  b=bytearray(p.read_bytes());b[offset:offset+len(data)]=data;p.write_bytes(b)
 def needed(self,names):
  b=bytearray(executable_blob());strings=b'\0';offsets=[]
  for name in names:offsets.append(len(strings));strings+=name.encode()+b'\0'
  b[0x300:0x300+len(strings)]=strings;rows=[(1,x) for x in offsets]+[(5,0x400300),(10,len(strings)),(0,0)]
  for i,row in enumerate(rows):b[0x240+i*16:0x250+i*16]=struct.pack('<qQ',*row)
  dynlen=16*len(rows)
  struct.pack_into('<Q',b,64+2*56+32,dynlen);struct.pack_into('<Q',b,64+2*56+40,dynlen);struct.pack_into('<Q',b,0x900+5*64+32,dynlen);struct.pack_into('<Q',b,0x900+6*64+32,len(strings));self.exe.write_bytes(b)
 def test_missing_stimulus_header(self):(self.build/'stimulus_m17.hpp').unlink();self.reject()
 def test_stimulus_header_mutation(self):(self.build/'stimulus_m17.hpp').write_text('changed');self.reject()
 def test_mmd_with_stimulus_header(self):self.dep.write_text('m17_main.o: m17_main.cpp stimulus_m17.hpp expected_m17.hpp generated_abi.hpp\n');self.check()
 def test_minimal_needed_positive(self):
  r=self.check();self.assertEqual(r['status'],'PASS_FIXED_M17_SINGLE_TU_LINK_ONLY');self.assertEqual((r['artifact_count'],r['staged_input_count'],r['new_object_count'],r['dependency_count']),(17,14,1,1));self.assertFalse(r['model_executed']);self.assertFalse(r['scope']['behavior_pass']);self.assertFalse(r['scope']['numerical_pass']);self.assertFalse(r['scope']['retained_archive_members_reparsed']);self.assertEqual(len(r['artifact_inventory']),17)
 def test_four_needed_positive(self):self.needed(['libstdc++.so.6','libm.so.6','libgcc_s.so.1','libc.so.6']);self.check()
 def test_stage_hash_only_no_archive_runtime_parse(self):
  original=c.elf;calls=[]
  def tracked(path,*args,**kwargs):calls.append(Path(path).name);return original(path,*args,**kwargs)
  with mock.patch.object(c,'elf',side_effect=tracked):self.check()
  self.assertEqual(calls,['m17_main.o','VOrderedQkBehaviorCore_m17'])
 def test_new_source_and_staged_header_dependency_positive(self):self.dep.write_text('m17_main.o: \\\n '+str(self.build/'m17_main.cpp')+' generated_abi.hpp expected_m17.hpp VOrderedQkBehaviorCore.h\n');self.check()
 def test_external_pinned_dependency_positive(self):
  p=self.root/'external.h';p.write_text('synthetic');self.m['build_plan']['allowed_dependency_pins']=[{'path':str(p)}];self.dep.write_text(self.dep.read_text().strip()+' '+str(p)+'\n');self.check()
 def test_nine_copied_definitions_exact(self):
  old=Path(__file__).resolve().parents[1]/'qwen2_core_client_verilator_build_prepare_20261025T2143/check_build.py';new=Path(c.__file__);sources=[p.read_text() for p in (old,new)];names=('need','regular','local','signature','Reader','symbol_rows','elf','normalized','mmd')
  def definitions(text):return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  a,b=map(definitions,sources)
  for name in names:self.assertEqual(a[name],b[name],name)
  self.assertEqual(c.MAX_FILE,128*1024**2)
 def test_oversized_file_rejected_before_open(self):
  huge=mock.Mock(st_dev=1,st_ino=1,st_mode=0o100644,st_size=128*1024**2+1,st_mtime_ns=1,st_ctime_ns=1,st_nlink=1)
  with mock.patch.object(Path,'lstat',return_value=huge),mock.patch.object(Path,'open',side_effect=AssertionError('oversized file must not be opened')):
   with self.assertRaises(ValueError):c.Reader(self.obj)
 def test_staged_content_drift(self):
  for name in ('VOrderedQkBehaviorCore__ALL.a','verilated.o','VOrderedQkBehaviorCore.h','m17_main.cpp'):
   with self.subTest(name=name):
    p=self.build/name;original=p.read_bytes();p.write_bytes(original+b'X');self.reject();p.write_bytes(original)
 def test_staged_wrong_pin(self):self.m['staged_inputs'][0]['sha256']='0'*64;self.reject()
 def test_staged_count_or_role(self):
  original=copy.deepcopy(self.m)
  for mode in ('missing','duplicate','old_m1'):
   with self.subTest(mode=mode):
    self.m=copy.deepcopy(original)
    if mode=='missing':self.m['staged_inputs'].pop()
    elif mode=='duplicate':self.m['staged_inputs'][1]=copy.deepcopy(self.m['staged_inputs'][0])
    else:self.m['staged_inputs'][0]['relative']='build/m1_main.o'
    self.reject()
 def test_extra_old_m2_rejected(self):(self.build/'m2_main.o').write_bytes(b'old');self.reject()
 def test_extra_old_m1_rejected(self):(self.build/'m1_main.o').write_bytes(b'old');self.reject()
 def test_extra_old_dependency_rejected(self):(self.build/'m1_main.d').write_bytes(b'old');self.reject()
 def test_extra_pch_rejected(self):(self.build/'VOrderedQkBehaviorCore__pch.h.fast.gch').write_bytes(b'old');self.reject()
 def test_extra_directory_rejected(self):(self.build/'extra').mkdir();self.reject()
 def test_missing_new_object(self):self.obj.unlink();self.reject()
 def test_output_symlink(self):
  data=self.obj.read_bytes();self.obj.unlink();p=self.root/'other';p.write_bytes(data);self.obj.symlink_to(p);self.reject()
 def test_wrong_plan_roles(self):
  original=copy.deepcopy(self.m)
  for field,value in (('object','build/m1_main.o'),('dependency','build/m1_main.d'),('source',str(self.root/'m17_main.cpp')),('target','m1_main.o')):
   with self.subTest(field=field):self.m=copy.deepcopy(original);self.m['build_plan']['translation_unit'][field]=value;self.reject()
 def test_wrong_object_type(self):self.mutate(self.obj,16,struct.pack('<H',3));self.reject()
 def test_mmd_wrong_target(self):self.dep.write_text('m1_main.o: m17_main.cpp\n');self.reject()
 def test_mmd_wrong_source(self):self.dep.write_text('m17_main.o: generated_abi.hpp m17_main.cpp\n');self.reject()
 def test_mmd_unpinned_existing(self):
  p=self.root/'unlisted.h';p.write_text('synthetic');self.dep.write_text('m17_main.o: m17_main.cpp '+str(p)+'\n');self.reject()
 def test_mmd_pinned_but_absent(self):
  p=self.root/'absent.h';self.m['build_plan']['allowed_dependency_pins']=[{'path':str(p)}];self.dep.write_text('m17_main.o: m17_main.cpp '+str(p)+'\n');self.reject()
 def test_mmd_logical_pch_absent(self):self.dep.write_text('m17_main.o: m17_main.cpp VOrderedQkBehaviorCore__pch.h.fast\n');self.reject()
 def test_mmd_make_expression(self):self.dep.write_text('m17_main.o: m17_main.cpp $(shell_bad)\n');self.reject()
 def test_final_ET_EXEC_rejected(self):self.mutate(self.exe,16,struct.pack('<H',2));self.reject()
 def test_atomic_needed_rejected(self):self.needed(['libstdc++.so.6','libc.so.6','libatomic.so.1']);self.reject()
 def test_missing_stdcpp_rejected(self):self.needed(['libc.so.6']);self.reject()
 def test_final_mode_required(self):self.exe.chmod(0o600);self.reject()
 def test_nonfinal_executable_rejected(self):(self.build/'verilated.o').chmod(0o700);self.reject()
 def test_tmp_nonempty(self):(self.root/'tmp').mkdir();(self.root/'tmp/log').write_text('x');self.reject()
 def test_cached_input_mutation_rejected(self):
  original=c.elf
  def changed(path,*args,**kwargs):
   result=original(path,*args,**kwargs)
   if Path(path).name=='m17_main.o':p=self.build/'expected_m17.hpp';p.write_bytes(p.read_bytes()+b'X')
   return result
  with mock.patch.object(c,'elf',side_effect=changed):self.reject()
 def test_final_runpath_rejected(self):self.mutate(self.exe,0x240+3*16,struct.pack('<q',29));self.reject()
 def test_final_interpreter_rejected(self):self.mutate(self.exe,0x200,b'X');self.reject()

if __name__=='__main__':unittest.main(verbosity=2)
