"""Bounded, read-only build-container qualification, not execution or semantic validation.
API check(run_root, manifest); build_plan contains exact stage/object/dependency roles.
Only stdlib, no executable imports or subprocess. See explicit parser limits below.
"""
import hashlib,os,re,stat,struct
from pathlib import Path
SUCCESS='PASS_FROZEN_MODEL_BUILD_ONLY'
MAX_FILE=384*1024**2
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

def archive(path,expected):
 """GNU ordinary ar only: validate headers, long names, index offsets and member hashes."""
 need(len(expected)==36 and len({x['name'] for x in expected})==36,'archive expected members')
 wants={x['name']:x for x in expected};r=Reader(path)
 try:
  need(r.read(0,8)==b'!<arch>\n','not ordinary ar (thin forbidden)');pos=8;longnames=None;index=None;members=[];headers=set()
  while pos<r.size:
   need(len(members)<=36,'archive member bound');h=r.read(pos,60);need(h[58:]==b'`\n','ar header trailer')
   raw=h[:16].decode('ascii').rstrip(' ');s=h[48:58].decode('ascii').strip(' ');need(bool(re.fullmatch('[0-9]+',s)),'ar decimal size');n=int(s);start=pos+60
   for off,width,pattern in ((16,12,'[0-9]+'),(28,6,'[0-9]+'),(34,6,'[0-9]+'),(40,8,'[0-7]+')):
    field=h[off:off+width].decode('ascii').strip(' ');need((not field and raw in ('/','//','/SYM64/')) or bool(re.fullmatch(pattern,field)),'ar numeric metadata')
   need(n<=r.size-start,'ar member range')
   if raw=='//':need(longnames is None and n<=1048576,'GNU long-name table');longnames=r.read(start,n)
   elif raw in ('/','/SYM64/'):
    need(index is None and n<=MAX_TABLE,'GNU symbol index count/size');index=(raw,r.read(start,n))
   else:
    if raw.startswith('/'):
     need(raw[1:].isdigit() and longnames is not None,'GNU long-name reference');off=int(raw[1:]);need(off<len(longnames) and (off==0 or longnames[off-1:off]==b'\n'),'GNU long-name offset boundary')
     end=longnames.find(b'/\n',off);need(end>=off,'GNU long-name terminator');name=longnames[off:end].decode('ascii')
    else:need(raw.endswith('/'),'short ar name terminator');name=raw[:-1]
    need(name in wants and '/' not in name and name not in [x['name'] for x in members],'unexpected/duplicate archive member')
    w=wants[name];digest=r.digest(start,n);need(n==w['bytes'] and digest==w['sha256'],'archive/object identity mismatch')
    headers.add(pos);members.append({'name':name,'bytes':n,'sha256':digest})
   pos=start+n
   if n%2:need(r.read(pos,1)==b'\n','ar alignment padding');pos+=1
  need(pos==r.size and set(wants)=={x['name'] for x in members} and index is not None,'archive closure')
  tag,b=index;width=8 if tag=='/SYM64/' else 4;need(len(b)>=width,'index prefix');count=int.from_bytes(b[:width],'big');need(0<count<=MAX_SYMBOLS and width*(count+1)<=len(b),'index offset table')
  for off in range(width,width*(count+1),width):need(int.from_bytes(b[off:off+width],'big') in headers,'index references nonmember')
  names=b[width*(count+1):];cursor=0
  for unused in range(count):
   end=names.find(b'\0',cursor);need(cursor<end<cursor+MAX_NAME,'index symbol string');cursor=end+1
  need(not names[cursor:].strip(b'\0'),'index trailing data')
  return {'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before),'members':members,'index_symbols':count}
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

def check(root,manifest):
 root=Path(root).resolve();need(root.is_dir(),'run root');plan=manifest['build_plan'];units=plan['translation_units'];pchs=plan['pch'];ar=plan['archive']
 need(len(units)==39 and len(pchs)==2 and len(ar['members'])==36 and len(plan['staged_dependency_files'])==45,'fixed build cardinalities')
 need(len({u['object'] for u in units})==39 and len({u['dependency'] for u in units}|{x['dependency'] for x in pchs})==41,'duplicate object/MMD role')
 cwd=root/plan.get('dependency_cwd','build');need(cwd.resolve().is_relative_to(root) and cwd.is_dir() and not cwd.is_symlink(),'dependency cwd')
 allowed={os.path.normpath(x['path']) for x in plan['allowed_dependency_pins']}
 allowed.update(str(local(root,x)) for x in plan['staged_dependency_files'])
 objects={};dependencies=[]
 for u in units:
  objects[u['object']]=elf(local(root,u['object']),'object')
  dependencies.append(mmd(local(root,u['dependency']),cwd,u.get('target',Path(u['object']).name),u['source'],allowed))
 expected=[]
 for member in ar['members']:
  need(member['object'] in objects and Path(member['object']).name==member['name'],'archive object mapping')
  expected.append(dict(name=member['name'],**{k:objects[member['object']][k] for k in ('bytes','sha256')}))
 archive_result=archive(local(root,ar['path']),expected)
 checksums=[];pch_results=[]
 for p in pchs:
  r=Reader(local(root,p['path']))
  try:
   need(r.size>24 and r.read(0,8)==b'gpch+014','GCC14 C++ PCH format');checksum=r.read(8,16);checksums.append(checksum)
   pch_results.append({'path':p['path'],'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before),'checksum':checksum.hex(),'format_only_not_full_GCC_validation_or_use':True})
  finally:r.close()
  dependencies.append(mmd(local(root,p['dependency']),cwd,p.get('target',Path(p['path']).name),p['source'],allowed))
 need(checksums[0]==checksums[1],'PCH executable checksums differ')
 result=elf(local(root,plan['executable']),'executable',plan.get('model_symbol_prefix','VOrderedQkBehaviorCore'))
 expected=plan['staged_dependency_files']+[u['object'] for u in units]+[u['dependency'] for u in units]+[p['path'] for p in pchs]+[p['dependency'] for p in pchs]+[ar['path'],plan['executable']]
 need(len(expected)==len(set(expected))==129 and all(Path(x).parent==Path('build') for x in expected),'exact 129 flat build roles')
 actual=[]
 with os.scandir(root/'build') as scan:
  for e in scan:
   need(e.is_file(follow_symlinks=False),'build contains directory/symlink/special');actual.append('build/'+e.name)
 need(set(actual)==set(expected),'unexpected/missing build artifact')
 tmp=root/'tmp'
 if os.path.lexists(tmp):need(tmp.is_dir() and not tmp.is_symlink() and not any(tmp.iterdir()),'successful build tmp not empty')
 cached={**objects,ar['path']:archive_result,plan['executable']:result}
 cached.update({p['path']:v for p,v in zip(pchs,pch_results)})
 cached.update({u['dependency']:v for u,v in zip(units+pchs,dependencies)})
 inventory=[]
 for relative in sorted(expected):
  p=local(root,relative)
  if relative in cached:v=cached[relative]
  else:
   r=Reader(p)
   try:v={'bytes':r.size,'sha256':r.digest(),'file_identity':list(r.before)}
   finally:r.close()
  final=p.lstat();need(signature(final)==tuple(v['file_identity']),'artifact changed between parse/hash and final inventory');mode=stat.S_IMODE(final.st_mode);need(bool(mode&0o111)==(relative==plan['executable']),'artifact executable permission role')
  inventory.append({'relative':relative,'path':str(p),'bytes':v['bytes'],'sha256':v['sha256'],'mode':oct(mode),'file_identity':list(signature(final))})
 return {'status':SUCCESS,'model_executed':False,'artifact_inventory':inventory,'artifact_count':129,'object_count':len(objects),'objects':objects,'archive':archive_result,'pch':pch_results,'dependency_count':len(dependencies),'dependencies':dependencies,'executable':result,'scope':{'build_container_and_linkage_structure_only':True,'model_executed':False,'behavior_pass':False,'numerical_pass':False,'utilization_known':False,'PCH_validated_by_GCC_or_use_proven':False,'MMD_is_not_complete_system_header_closure':True}}
