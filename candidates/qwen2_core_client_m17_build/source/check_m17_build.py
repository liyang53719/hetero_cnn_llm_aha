"""Bounded M17 single-TU/link artifact qualification; no compiler/model execution.
Nine parser/helper definitions below are copied byte-for-byte from the frozen
2143 build checker. Retained archive/runtime inputs are identity-checked only.
API check(run_root, manifest); exact stage14 + new3 = seventeen flat build files.
"""
import hashlib,os,re,stat,struct
from pathlib import Path
SUCCESS='PASS_FIXED_M17_SINGLE_TU_LINK_ONLY'
MAX_FILE=128*1024**2
MAX_TABLE=64*1024**2
MAX_SECTIONS=65535
MAX_SYMBOLS=2000000
MAX_NAME=8192
MAX_DEP=4*1024**2
MAX_DEP_TOKENS=100000
ALLOWED_NEEDED={'libstdc++.so.6','libm.so.6','libgcc_s.so.1','libc.so.6','libatomic.so.1'}


def need(ok,reason):
 if not ok:raise ValueError(reason)

def regular(path):
 p=Path(path);need(stat.S_ISREG(p.stat().st_mode),'not regular file');return p

def local(root,relative):
 need(isinstance(relative,str) and relative and not Path(relative).is_absolute(),'relative output path')
 need('..' not in Path(relative).parts,'output traversal')
 p=root
 for part in Path(relative).parts:
  p=p/part;need(not p.is_symlink(),'output path symlink')
 need(p.resolve().is_relative_to(root),'output outside root');return regular(p)

def signature(s):
 return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_nlink)

class Reader:
 def __init__(self,path):
  self.path=regular(path);before=self.path.lstat();need(stat.S_ISREG(before.st_mode),'reader endpoint not regular');self.before=signature(before);self.size=before.st_size;need(0<self.size<=MAX_FILE,'file size bound');self.f=self.path.open('rb')
  try:need(signature(os.fstat(self.f.fileno()))==self.before,'opened file identity drift')
  except BaseException:self.f.close();raise
 def close(self):
  try:need(signature(os.fstat(self.f.fileno()))==self.before and signature(self.path.lstat())==self.before,'parsed/hashed file identity changed')
  finally:self.f.close()
 def read(self,off,n):
  need(isinstance(off,int) and isinstance(n,int) and 0<=off<=self.size and 0<=n<=MAX_TABLE and n<=self.size-off,'read bounds')
  self.f.seek(off);data=self.f.read(n);need(len(data)==n,'short read');return data
 def digest(self,off=0,n=None):
  if n is None:n=self.size
  need(0<=off<=self.size and 0<=n<=self.size-off,'hash bounds');h=hashlib.sha256();self.f.seek(off)
  while n:
   b=self.f.read(min(n,1048576));need(bool(b),'short hash read');h.update(b);n-=len(b)
  return h.hexdigest()
 def cstring(self,off,limit):
  need(0<=limit<=MAX_TABLE,'string table bound');b=self.read(off,min(limit,MAX_NAME));k=b.find(b'\0');need(k>=0,'unterminated/long name');return b[:k].decode('ascii')

def symbol_rows(reader,section):
 for pos in range(section[4],section[4]+section[5],24*4096):
  data=reader.read(pos,min(24*4096,section[4]+section[5]-pos))
  yield from struct.iter_unpack('<IBBHQQ',data)

def elf(path,kind,model_marker='VOrderedQkBehaviorCore'):
 r=Reader(path)
 try:
  h=struct.unpack('<16sHHIQQQIHHHHHH',r.read(0,64));ident,typ,machine,ver,entry,pho,sho,flags,eh,pe,pn,se,sn,ssi=h
  need(ident[:7]==b'\x7fELF\x02\x01\x01' and ident[7] in (0,3),'ELF64 little-endian identity')
  need(machine==62 and ver==1 and flags==0 and eh==64,'ELF x86_64 header')
  need((typ==1 if kind=='object' else typ in (2,3)),'ELF type')
  need(0<sn<=MAX_SECTIONS and se==64 and ssi<sn,'section header count/size')
  need(sho>=64 and sho+sn*64<=r.size,'section table range')
  sections=[struct.unpack('<IIQQQQIIQQ',r.read(sho+i*64,64)) for i in range(sn)]
  need(sections[0][1]==0,'section zero')
  for s in sections:
   name,st,fl,addr,off,size,link,info,align,entsize=s
   need(align==0 or align&(align-1)==0,'section alignment')
   need(st==8 or off+size<=r.size,'section content range')
   if kind!='object':need(not (fl&1 and fl&4),'writable executable section')
   if st in (2,11):
    need(entsize==24 and size%24==0 and size//24<=MAX_SYMBOLS,'symbol table bounds')
    need(link<sn and sections[link][1]==3 and sections[link][5]<=MAX_TABLE,'symbol string table')
  need(sections[ssi][1]==3,'section-name string table')
  need(any(s[1]==2 for s in sections),'full symbol table absent')
  need(sum(s[5]//24 for s in sections if s[1] in (2,11))<=MAX_SYMBOLS,'aggregate symbol count bound')
  for s in sections:
   if s[1] not in (2,11):continue
   strings=sections[s[6]]
   for no,info,other,shndx,value,size in symbol_rows(r,s):
    need(no<strings[5] and (shndx<sn or shndx>=0xff00),'symbol name offset/section index')
  if kind=='object':need(pn==0 and entry==0,'relocatable object program headers/entry')
  else:need(0<pn<=4096 and pe==56 and pho>=64 and pho+pn*56<=r.size,'program header bounds')
  ph=[struct.unpack('<IIQQQQQQ',r.read(pho+i*56,56)) for i in range(pn)]
  for t,f,o,v,p,fs,ms,a in ph:
   need(o+fs<=r.size and fs<=ms,'program file/memory bounds')
   need(a in (0,1) or a&(a-1)==0,'program alignment')
   if t==1:
    need(not (f&2 and f&1),'RWX load segment')
    need(a in (0,1) or (o-v)%a==0,'load alignment congruence')
  needed=[];main=None;model=False
  if kind!='object':
   loads=[x for x in ph if x[0]==1];need(loads,'PT_LOAD absent')
   def mapped(addr,size=1,executable=False):
    candidates=[x for x in loads if x[3]<=addr and addr+size<=x[3]+x[5] and (not executable or x[1]&1)]
    need(len(candidates)==1,'address not in unique file-backed load');return candidates[0][2]+addr-candidates[0][3]
   need(entry>0,'entry zero');mapped(entry,1,True)
   interp=[x for x in ph if x[0]==3];need(len(interp)==1,'PT_INTERP count')
   x=interp[0];need(r.read(x[2],x[5])==b'/lib64/ld-linux-x86-64.so.2\0','PT_INTERP identity')
   stack=[x for x in ph if x[0]==0x6474e551];need(len(stack)==1 and not stack[0][1]&1,'executable/missing GNU stack')
   dynamic=[x for x in ph if x[0]==2];need(len(dynamic)==1,'PT_DYNAMIC count');x=dynamic[0]
   need(x[5]%16==0 and x[5]<=MAX_TABLE,'dynamic bounds');need(mapped(x[3],x[5])==x[2],'PT_DYNAMIC address/file mapping');dt=[];ended=False
   for pos in range(x[2],x[2]+x[5],16):
    tag,val=struct.unpack('<qQ',r.read(pos,16))
    if tag==0:ended=True;break
    need(tag not in (15,29,0x6ffffefc,0x6ffffefb,0x6ffffefa,0x7fffffff,0x7ffffffd),'extra loader path/object tag forbidden');dt.append((tag,val))
   need(ended,'unterminated dynamic section')
   strtab=[v for t,v in dt if t==5];strsz=[v for t,v in dt if t==10]
   need(len(strtab)==len(strsz)==1 and 0<strsz[0]<=MAX_TABLE,'dynamic string table')
   base=mapped(strtab[0],strsz[0]);needed=[]
   for tag,value in dt:
    if tag==1:need(value<strsz[0],'DT_NEEDED offset');needed.append(r.cstring(base+value,strsz[0]-value))
   need(len(needed)==len(set(needed)) and set(needed)<=ALLOWED_NEEDED and {'libstdc++.so.6','libc.so.6'}<=set(needed),'DT_NEEDED set')
   for s in sections:
    if s[1] not in (2,11):continue
    strings=sections[s[6]]
    for no,info,other,shndx,value,size in symbol_rows(r,s):
     need(no<strings[5],'symbol name offset')
     if not shndx:continue
     need(shndx<sn or shndx>=0xff00,'symbol section index')
     name=r.cstring(strings[4]+no,strings[5]-no)
     selected_main=name=='main'
     selected_model=name.startswith('_Z') and model_marker in name and info&15==2
     if selected_main or selected_model:
      need(0<shndx<sn and info&15==2 and size>0,'ordinary positive-sized function definition required')
      sec=sections[shndx];need(sec[2]&6==6 and sec[3]<=value and value+size<=sec[3]+sec[5],'function not within allocated executable section');mapped(value,size,True)
     if selected_main:need(info>>4 in (1,2),'main symbol binding');main=value
     if selected_model:model=True
   need(main is not None and model,'main/model defined symbols absent')
  return {'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before),'elf_type':typ,'machine':machine,'entry':entry,'section_count':sn,'needed':needed,'main':main,'model_symbol_found':model}
 finally:r.close()

def normalized(cwd,text):
 need(isinstance(text,str) and bool(re.fullmatch(r'[A-Za-z0-9_./+@%=-]+',text)),'dependency path grammar')
 return os.path.normpath(text if os.path.isabs(text) else str(cwd/text))

def mmd(path,cwd,target,source,allowed):
 r=Reader(path)
 try:
  need(r.size<=MAX_DEP,'MMD file size');text=r.read(0,r.size).decode('ascii')
  need('\r' not in text and '\0' not in text,'MMD encoding');text=text.replace('\\\n',' ')
  lines=[x for x in text.splitlines() if x.strip()];need(len(lines)==1 and lines[0].count(':')==1,'single MMD rule')
  left,right=lines[0].split(':');targets=left.split();deps=right.split()
  need(targets==[target] and 0<len(deps)<=MAX_DEP_TOKENS,'MMD exact target/dependency count')
  need(normalized(cwd,deps[0])==normalized(cwd,source),'MMD first source')
  paths=[]
  for dep in deps:
   name=normalized(cwd,dep);need(name in allowed,'MMD unpinned/unstaged dependency');regular(name);paths.append(name)
  return {'target':target,'first_source':paths[0],'dependency_count':len(paths),'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before)}
 finally:r.close()

STAGED_BASENAMES={
 'VOrderedQkBehaviorCore.h','VOrderedQkBehaviorCore_HeteroFP32Alu.h',
 'VOrderedQkBehaviorCore__Syms.h','VOrderedQkBehaviorCore___024root.h',
 'VOrderedQkBehaviorCore__pch.h','VOrderedQkBehaviorCore_banks_bank_2240x128.h',
 'VOrderedQkBehaviorCore_banks_bank_48x128.h','generated_abi.hpp','expected_m17.hpp','stimulus_m17.hpp',
 'm17_main.cpp','VOrderedQkBehaviorCore__ALL.a','verilated.o','verilated_threads.o'}
OBJECT='build/m17_main.o'
DEPENDENCY='build/m17_main.d'
EXECUTABLE='build/VOrderedQkBehaviorCore_m17'
M17_NEEDED={'libstdc++.so.6','libm.so.6','libgcc_s.so.1','libc.so.6'}

def exact_build(root,expected):
 build=root/'build';need(build.is_dir() and not build.is_symlink(),'build directory')
 actual=[]
 with os.scandir(build) as scan:
  for e in scan:
   need(e.is_file(follow_symlinks=False),'build contains directory/symlink/special')
   actual.append('build/'+e.name)
 need(set(actual)==expected and len(actual)==17,'exact seventeen build files')
 tmp=root/'tmp'
 if os.path.lexists(tmp):need(tmp.is_dir() and not tmp.is_symlink() and not any(tmp.iterdir()),'successful build tmp not empty')

def check(root,manifest):
 root=Path(root).resolve();need(root.is_dir(),'run root')
 plan=manifest['build_plan'];unit=plan['translation_unit'];staged=manifest['staged_inputs']
 need(plan['dependency_cwd']=='build' and plan['executable']==EXECUTABLE and plan['model_symbol_prefix']=='VOrderedQkBehaviorCore','fixed M17 build plan')
 need(unit['object']==OBJECT and unit['dependency']==DEPENDENCY and unit['target']=='m17_main.o','fixed single-TU output roles')
 cwd=root/'build'
 need(normalized(cwd,unit['source'])==str(cwd/'m17_main.cpp'),'fixed staged M17 first source')
 expected_stage={'build/'+x for x in STAGED_BASENAMES}
 need(len(staged)==14 and {x['relative'] for x in staged}==expected_stage,'exact fourteen staged identities')
 expected=expected_stage|{OBJECT,DEPENDENCY,EXECUTABLE};need(len(expected)==17,'distinct build roles');exact_build(root,expected)
 cached={}
 for pin in staged:
  relative=pin['relative'];need(type(pin['bytes']) is int and pin['bytes']>0 and isinstance(pin['sha256'],str) and re.fullmatch('[0-9a-f]{64}',pin['sha256']),'staged pin format')
  r=Reader(local(root,relative))
  try:
   v={'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before)}
   need(v['bytes']==pin['bytes'] and v['sha256']==pin['sha256'],'staged input content changed')
   cached[relative]=v
  finally:r.close()
 allowed=set()
 for pin in plan['allowed_dependency_pins']:
  path=pin['path'];need(isinstance(path,str) and os.path.isabs(path),'dependency pin absolute path')
  allowed.add(os.path.normpath(path))
 allowed.update(str(root/x) for x in expected_stage)
 obj=elf(local(root,OBJECT),'object');cached[OBJECT]=obj
 dep=mmd(local(root,DEPENDENCY),cwd,unit['target'],unit['source'],allowed);cached[DEPENDENCY]=dep
 exe=elf(local(root,EXECUTABLE),'executable',plan['model_symbol_prefix']);cached[EXECUTABLE]=exe
 need(exe['elf_type']==3 and set(exe['needed'])<=M17_NEEDED,'M17 ET_DYN/four-library closure')
 exact_build(root,expected)
 inventory=[]
 for relative in sorted(expected):
  p=local(root,relative);v=cached[relative];final=p.lstat()
  need(signature(final)==tuple(v['file_identity']),'artifact changed before final inventory')
  mode=stat.S_IMODE(final.st_mode);need(bool(mode&0o111)==(relative==EXECUTABLE),'artifact executable permission role')
  inventory.append({'relative':relative,'path':str(p),'bytes':v['bytes'],'sha256':v['sha256'],'mode':oct(mode),'file_identity':list(signature(final))})
 return {'status':SUCCESS,'model_executed':False,'artifact_count':17,'staged_input_count':14,'new_object_count':1,'dependency_count':1,'artifact_inventory':inventory,'object':obj,'dependency':dep,'executable':exe,'scope':{'single_harness_TU_and_link_structure_only':True,'retained_archive_and_runtime_objects_hash_only':True,'retained_archive_members_reparsed':False,'model_recompiled':False,'model_executed':False,'behavior_pass':False,'numerical_pass':False,'utilization_known':False,'MMD_is_not_complete_system_header_closure':True}}
