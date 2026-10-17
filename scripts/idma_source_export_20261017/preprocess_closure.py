"""Fixed-source admission and official Verilator -E evidence, not a sandbox.
No macro semantics are evaluated here. .d is data, never executed.
"""
import hashlib,json,re,shlex
from pathlib import Path
IDENT=r'[A-Za-z_][A-Za-z0-9_$]*'
TOOL_SHA='619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703'
SAFE_PATH=re.compile(r'^[A-Za-z0-9_./-]+$')
PROFILE={'builtin_list_scope':'verified_known_macros_not_exhaustive','engine':'Verilator','version':'5.032','builtin_macros_retained':['VERILATOR','verilator','verilator3'],'options':['-E','--no-std','--relative-includes','--MMD'],'single_compilation_unit':True}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def parse_filelist(path,root):
 root=Path(root).resolve();sources=[];includes=[];defines={}
 for raw in Path(path).read_text().splitlines():
  line=raw.strip()
  if not line or line.startswith('//'):continue
  for word in shlex.split(line):
   if word.startswith('+define+'):
    for definition in word[8:].split('+'):
     name,sep,value=definition.partition('=')
     need(re.fullmatch(IDENT,name) is not None and re.fullmatch(r"[A-Za-z0-9_.$'()-]*",value) is not None,'unsupported define')
     need(name not in defines or defines[name]==value,'conflicting define');defines[name]=value
    continue
   is_inc=word.startswith('+incdir+');names=word[8:].split('+') if is_inc else [word]
   for name in names:
    need(name.startswith('@ROOT@/'),'unapproved filelist token');raw_path=root/name[7:];need(not raw_path.is_symlink(),'filelist symlink');p=raw_path.resolve()
    need(p.is_relative_to(root) and SAFE_PATH.fullmatch(str(p)) is not None and not p.is_symlink(),'filelist boundary')
    need(p.is_dir() if is_inc else p.is_file(),'missing source/include')
    (includes if is_inc else sources).append(p)
 need(sources,'empty source list');return sources,list(dict.fromkeys(includes)),defines

def literal_includes(text):
 # Lexical only: skip comments/strings and paired paste tokens. All real include
 # directives must remain standalone literals; source line spoofing is rejected.
 clean=list(text);i=0;tokens=[]
 while i<len(text):
  if text.startswith('//',i):
   end=text.find('\n',i);end=len(text) if end<0 else end
   for j in range(i,end):clean[j]=' '
   i=end;continue
  if text.startswith('/*',i):
   end=text.find('*/',i+2);need(end>=0,'unterminated comment');end+=2
   for j in range(i,end):
    if clean[j]!='\n':clean[j]=' '
   i=end;continue
  if text.startswith('``',i):i+=2;continue
  if text[i]=='"' and not(i and text[i-1]=='`'):
   i+=1
   while i<len(text):
    if text[i]=='\\':i+=2;continue
    if text[i]=='"':i+=1;break
    i+=1
   continue
  if text[i]=='`':
   m=re.match(IDENT,text[i+1:])
   if m and m[0] in ('include','line'):tokens.append((i,m[0]))
  i+=1
 clean=''.join(clean);result=[]
 for pos,kind in tokens:
  need(kind!='line','source line directive forbidden')
  start=clean.rfind('\n',0,pos)+1;end=clean.find('\n',pos);end=len(clean) if end<0 else end
  m=re.fullmatch(r'\s*`include\s+"([^"\n\\]+)"\s*',clean[start:end]);need(m is not None,'nonliteral/inline/continued include forbidden')
  rel=Path(m[1]);need(not rel.is_absolute() and '..' not in rel.parts,'include escape forbidden');result.append(m[1])
 return result

def admission(sources,includes,root):
 root=root.resolve();queue=list(sources);allowed={};missing=set()
 # Include directories may be broad. Pin and lexically inspect every SV header
 # there as well as transitively discover literal includes; no external search.
 for base in includes:
  queue.extend(p for p in base.rglob('*') if p.suffix in ('.svh','.vh'))
 while queue:
  p=queue.pop();need(not p.is_symlink(),'input symlink');p=p.resolve()
  if p in allowed:continue
  need(len(allowed)<100000 and p.is_relative_to(root) and p.is_file(),'input boundary')
  need(p.stat().st_size<=64*1024*1024,'input size cap');allowed[p]=sha(p)
  for rel in literal_includes(p.read_text()):
   candidates=[(base/rel).resolve() for base in [p.parent,*includes]]
   for q in candidates:need(q.is_relative_to(root),'candidate include escaped root')
   target=next((q for q in candidates if q.is_file()),None)
   if target is None:missing.add(rel)  # May be inactive. Actual -E decides.
   else:queue.append(target)
 return allowed,sorted(missing)

def parse_dependencies(path,root,mdir,tool,allowed):
 deps=set()
 for line in path.read_text().splitlines():
  if not line.strip():continue
  need(line.count(':')==1,'dependency grammar');lhs,rhs=line.split(':')
  for word in lhs.split()+rhs.split():need(SAFE_PATH.fullmatch(word) is not None,'dependency character')
  for word in lhs.split():
   p=Path(word);p=p.resolve() if p.is_absolute() else (root/p).resolve();need(p.is_relative_to(mdir),'dependency target escape')
  for word in rhs.split():
   p=Path(word);p=p.resolve() if p.is_absolute() else (root/p).resolve();need(p==tool or p in allowed,'unknown dependency');deps.add(p)
 return deps

def generate(filelist,root,tool,work,run):
 root=root.resolve();tool=tool.resolve();need(sha(tool)==TOOL_SHA,'preprocessor tool drift')
 sources,includes,defines=parse_filelist(filelist,root);allowed,missing=admission(sources,includes,root)
 need(not work.exists(),'fresh preprocessor work');work.mkdir();mdir=work/'obj';mdir.mkdir()
 argv=[str(tool),*PROFILE['options'],'--Mdir',str(mdir),'--prefix','Vidma_source']
 argv+=['+define+'+n+('='+v if v else '') for n,v in defines.items()]
 argv+=['+incdir+'+str(p) for p in includes]+[str(p) for p in sources]
 stdout=run(argv,root)  # Callback owns original global deadline and file bounds.
 dep=mdir/'Vidma_source__ver.d';need(dep.is_file(),'missing actual preprocessor dependencies');deps=parse_dependencies(dep,root,mdir,tool,allowed)
 need(set(sources)<=deps,'missing source dependency')
 for p,h in allowed.items():need(sha(p)==h,'postprocessor input drift')
 need(sha(tool)==TOOL_SHA,'postprocessor tool drift')
 return {'schema':2,'scope':'FIXED_TRUSTED_SOURCES_NOT_FILESYSTEM_SANDBOX','profile':PROFILE,'initial_filelist_defines':defines,'admitted_input_bytes':sum(p.stat().st_size for p in allowed),'preprocessed_stdout_sampled_limit_bytes':32*1024*1024,'source_files':len(set(sources)),'include_directories':len(includes),'admitted_input_hashes':{str(p.relative_to(root)):h for p,h in sorted(allowed.items())},'actual_dependency_hashes':{str(p.relative_to(root)):allowed[p] for p in sorted(deps) if p!=tool},'unresolved_lexical_includes':missing,'preprocessed_stdout_sha256':hashlib.sha256(stdout).hexdigest(),'preprocessed_stdout_bytes':len(stdout),'private_dependency_file_sha256':sha(dep),'tool_sha256':TOOL_SHA,'excluded_links_unreferenced':True}

def verify_record(root,record):
 need(record.get('scope')=='FIXED_TRUSTED_SOURCES_NOT_FILESYSTEM_SANDBOX','closure scope drift')
 need(record['schema']==2 and record['profile']==PROFILE and record['tool_sha256']==TOOL_SHA,'closure profile drift')
 sources,includes,defines=parse_filelist(root/'idma.f.in',root);allowed,missing=admission(sources,includes,root)
 need(record['initial_filelist_defines']==defines and record['unresolved_lexical_includes']==missing,'closure admission drift')
 need(record['admitted_input_hashes']=={str(p.relative_to(root)):h for p,h in sorted(allowed.items())},'closure input drift')
 need(record['source_files']==len(set(sources)) and record['include_directories']==len(includes),'closure counts drift')
 need(record['excluded_links_unreferenced'] is True,'excluded links claim missing')
 need(type(record['preprocessed_stdout_bytes']) is int and 0<=record['preprocessed_stdout_bytes']<=32*1024*1024,'preprocessed size record')
 for key in ('preprocessed_stdout_sha256','private_dependency_file_sha256'):need(re.fullmatch('[0-9a-f]{64}',record[key]) is not None,'invalid evidence hash')
 actual=record['actual_dependency_hashes'];need(all(n in record['admitted_input_hashes'] and record['admitted_input_hashes'][n]==h for n,h in actual.items()),'actual dependency drift')
 need({str(p.relative_to(root)) for p in sources}<=set(actual),'source absent from recorded dependency')
 return True
