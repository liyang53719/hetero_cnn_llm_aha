"""Synthetic binary/text fixtures only; no compiler, actual model, or ELF execution."""
import copy,hashlib,importlib.util,os,struct,tempfile,unittest
from pathlib import Path
from unittest import mock
s=importlib.util.spec_from_file_location('check_build',Path(__file__).with_name('check_build.py'));c=importlib.util.module_from_spec(s);s.loader.exec_module(c)

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
def ar_header(name,n):return name.encode().ljust(16)+b'0'.ljust(12)+b'0'.ljust(6)+b'0'.ljust(6)+b'100644'.ljust(8)+str(n).encode().ljust(10)+b'`\n'
def ar_record(name,data):return ar_header(name,len(data))+data+(b'\n' if len(data)%2 else b'')
def archive_blob(names,payload,width=4):
 longtab=b'';offsets=[]
 for name in names:offsets.append(len(longtab));longtab+=name.encode()+b'/\n'
 indexnames=b''.join(('sym'+str(i)).encode()+b'\0' for i in range(len(names)));indexsize=width*(1+len(names))+len(indexnames)
 pos=8+60+indexsize+indexsize%2+60+len(longtab)+len(longtab)%2;positions=[]
 for name in names:positions.append(pos);pos+=60+len(payload)+len(payload)%2
 index=len(names).to_bytes(width,'big')+b''.join(x.to_bytes(width,'big') for x in positions)+indexnames
 return b'!<arch>\n'+ar_record('/SYM64/' if width==8 else '/',index)+ar_record('//',longtab)+b''.join(ar_record('/'+str(o),payload) for o in offsets)

class Fixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);build=self.root/'build';build.mkdir();self.units=[];self.staged=[];self.members=[]
  for i in range(39):
   name='VOrderedQkBehaviorCore__unit'+str(i);source=build/(name+'.cpp');source.write_text('// synthetic only\n');obj='build/'+name+'.o';dep='build/'+name+'.d';(self.root/obj).write_bytes(object_blob());(self.root/dep).write_text(name+'.o: '+str(source)+'\n');self.units.append(dict(object=obj,source=str(source),dependency=dep));self.staged.append('build/'+name+'.cpp')
   if i<36:self.members.append(dict(name=name+'.o',object=obj))
  self.ar=build/'VOrderedQkBehaviorCore__ALL.a';self.ar.write_bytes(archive_blob([x['name'] for x in self.members],object_blob()))
  self.exe=build/'VOrderedQkBehaviorCore';self.exe.write_bytes(executable_blob());self.exe.chmod(0o700)
  header=build/'VOrderedQkBehaviorCore__pch.h';header.write_text('// synthetic PCH source\n');self.staged.append('build/'+header.name);self.pchs=[]
  for flavor in ('fast','slow'):
   name=header.name+'.'+flavor+'.gch';dep=header.name+'.'+flavor+'.d';(build/name).write_bytes(b'gpch+014'+b'0123456789abcdef'+b'SYNTHETIC_NO_GCC');(build/dep).write_text(name+': '+str(header)+'\n');self.pchs.append(dict(path='build/'+name,dependency='build/'+dep,source=str(header),target=name))
  for i in range(5):
   name='synthetic_staged_'+str(i)+'.h';(build/name).write_text('// synthetic supplemental stage\n');self.staged.append('build/'+name)
  self.m={'build_plan':dict(translation_units=self.units,archive=dict(path='build/'+self.ar.name,members=self.members),pch=self.pchs,executable='build/'+self.exe.name,dependency_cwd='build',allowed_dependency_pins=[],staged_dependency_files=self.staged,model_symbol_prefix='VOrderedQkBehaviorCore')}
 def tearDown(self):self.tmp.cleanup()
 def check(self):return c.check(self.root,self.m)
 def reject(self):
  with self.assertRaises((ValueError,OSError)):self.check()
 def mutate(self,p,off,data):
  b=bytearray(p.read_bytes());b[off:off+len(data)]=data;p.write_bytes(b)
 def test_full_positive(self):
  r=self.check();self.assertEqual(r['status'],'PASS_FROZEN_MODEL_BUILD_ONLY');self.assertEqual((r['object_count'],r['dependency_count']),(39,41));self.assertFalse(r['model_executed']);self.assertFalse(r['scope']['behavior_pass'])
 def test_sym64_positive(self):self.ar.write_bytes(archive_blob([x['name'] for x in self.members],object_blob(),8));self.check()
 def test_mmd_continuation_positive(self):
  p=self.root/self.units[0]['dependency'];p.write_text(Path(self.units[0]['object']).name+': \\\n '+self.units[0]['source']+'\n');self.check()
 def test_cached_artifact_mutation_before_inventory(self):
  original=c.archive
  def change_after_archive(path,expected):
   result=original(path,expected);self.mutate(self.root/self.units[0]['object'],64,b'Z');return result
  with mock.patch.object(c,'archive',side_effect=change_after_archive):self.reject()
 def test_extra_file(self):(self.root/'build/extra').write_text('x');self.reject()
 def test_extra_dir(self):(self.root/'build/extra').mkdir();self.reject()
 def test_final_not_executable(self):self.exe.chmod(0o600);self.reject()
 def test_other_executable(self):(self.root/self.units[0]['object']).chmod(0o700);self.reject()
 def test_tmp_nonempty(self):(self.root/'tmp').mkdir();(self.root/'tmp/leftover').write_text('x');self.reject()
 def test_main_reserved_section(self):self.mutate(self.exe,0x500+24+6,struct.pack('<H',0xfff1));self.reject()
 def test_main_zero_size(self):self.mutate(self.exe,0x500+24+16,struct.pack('<Q',0));self.reject()
 def test_main_outside_section(self):self.mutate(self.exe,0x500+24+8,struct.pack('<Q',0x400820));self.reject()
 def test_object_bad_symbol_name(self):self.mutate(self.root/self.units[0]['object'],104,struct.pack('<I',99999));self.reject()
 def test_reader_changed_identity(self):
  p=self.root/self.units[0]['object'];r=c.Reader(p);self.mutate(p,64,b'Z')
  with self.assertRaises(ValueError):r.close()
 def test_object_wrong_machine(self):self.mutate(self.root/self.units[0]['object'],18,struct.pack('<H',3));self.reject()
 def test_object_big_endian(self):self.mutate(self.root/self.units[0]['object'],5,b'\x02');self.reject()
 def test_object_executable(self):self.mutate(self.root/self.units[0]['object'],16,struct.pack('<H',2));self.reject()
 def test_object_section_out_of_bounds(self):self.mutate(self.root/self.units[0]['object'],40,struct.pack('<Q',999999));self.reject()
 def test_object_archive_bytes_mismatch(self):self.mutate(self.root/self.units[0]['object'],64,b'Z');self.reject()
 def test_thin_archive(self):self.mutate(self.ar,0,b'!<thin>\n');self.reject()
 def test_archive_bad_mode(self):self.mutate(self.ar,8+40,b'8');self.reject()
 def test_archive_bad_uid(self):self.mutate(self.ar,8+28,b'X');self.reject()
 def test_archive_empty_index_name(self):self.mutate(self.ar,8+60+4*(1+36),b'\0');self.reject()
 def test_archive_zero_index(self):self.mutate(self.ar,8+60,b'\0'*4);self.reject()
 def test_archive_truncated(self):self.ar.write_bytes(self.ar.read_bytes()[:-1]);self.reject()
 def test_archive_index_wrong_member(self):self.mutate(self.ar,8+60+4,struct.pack('>I',1));self.reject()
 def test_archive_long_name_corrupt(self):
  b=self.ar.read_bytes();off=b.index(self.members[0]['name'].encode());self.mutate(self.ar,off,b'X');self.reject()
 def test_pch_partial_magic(self):self.mutate(self.root/self.pchs[0]['path'],0,b'gpcWrite');self.reject()
 def test_pch_checksum_mismatch(self):self.mutate(self.root/self.pchs[0]['path'],8,b'X');self.reject()
 def test_pch_truncated(self):(self.root/self.pchs[0]['path']).write_bytes(b'gpch+014');self.reject()
 def test_mmd_wrong_target(self):
  p=self.root/self.units[0]['dependency'];p.write_text('wrong.o: '+self.units[0]['source']+'\n');self.reject()
 def test_mmd_wrong_first_source(self):
  p=self.root/self.units[0]['dependency'];p.write_text(Path(self.units[0]['object']).name+': '+self.units[1]['source']+'\n');self.reject()
 def test_mmd_absent_logical_pch_rejected(self):
  p=self.root/self.units[0]['dependency'];p.write_text(p.read_text().strip()+' VOrderedQkBehaviorCore__pch.h.fast\n');self.reject()
 def test_mmd_extra_rule(self):
  p=self.root/self.units[0]['dependency'];p.write_text(p.read_text()+'extra: anything\n');self.reject()
 def test_mmd_make_expression(self):
  p=self.root/self.units[0]['dependency'];p.write_text(p.read_text().strip()+' $(shell_bad)\n');self.reject()
 def test_mmd_allowed_but_absent(self):
  missing=str(self.root/'absent.h');self.m['build_plan']['allowed_dependency_pins'].append({'path':missing});p=self.root/self.units[0]['dependency'];p.write_text(p.read_text().strip()+' '+missing+'\n');self.reject()
 def test_final_wrong_interpreter(self):self.mutate(self.exe,0x200,b'X');self.reject()
 def test_final_rwx(self):self.mutate(self.exe,64+4,struct.pack('<I',7));self.reject()
 def test_final_executable_stack(self):self.mutate(self.exe,64+3*56+4,struct.pack('<I',7));self.reject()
 def test_final_bad_entry(self):self.mutate(self.exe,24,struct.pack('<Q',0x500000));self.reject()
 def test_final_no_main(self):self.mutate(self.exe,0x401,b'xxxx');self.reject()
 def test_final_no_model(self):self.mutate(self.exe,0x400+6+5,b'X');self.reject()
 def test_final_wrong_needed(self):self.mutate(self.exe,0x301,b'X');self.reject()
 def test_final_dynamic_unmapped(self):self.mutate(self.exe,64+2*56+16,struct.pack('<Q',0x500240));self.reject()
 def test_final_extra_loader_tags(self):
  original=self.exe.read_bytes()
  for tag in (0x6ffffefc,0x6ffffefb,0x6ffffefa,0x7fffffff,0x7ffffffd):
   with self.subTest(tag=tag):
    self.exe.write_bytes(original);self.mutate(self.exe,0x240+3*16,struct.pack('<q',tag));self.reject()
 def test_final_runpath(self):self.mutate(self.exe,0x240+3*16,struct.pack('<q',29));self.reject()
 def test_duplicate_object(self):self.m['build_plan']['translation_units'][1]['object']=self.units[0]['object'];self.reject()
 def test_duplicate_mmd(self):self.m['build_plan']['translation_units'][1]['dependency']=self.units[0]['dependency'];self.reject()
 def test_output_symlink(self):
  p=self.root/self.units[0]['object'];data=p.read_bytes();p.unlink();other=self.root/'other';other.write_bytes(data);p.symlink_to(other);self.reject()
 def test_output_traversal(self):self.m['build_plan']['executable']='build/../build/'+self.exe.name;self.reject()

if __name__=='__main__':unittest.main(verbosity=2)
