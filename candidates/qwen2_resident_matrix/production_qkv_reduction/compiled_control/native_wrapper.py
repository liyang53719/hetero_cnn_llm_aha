"""Invoked only by an explicitly approved compiled-backend run."""
import os,sys,json,resource,hashlib,time,stat,re
from pathlib import Path
root=Path(os.environ['QKV_NATIVE_ROOT']);wrappers=Path(os.environ['QKV_NATIVE_WRAPPERS'])
name=Path(sys.argv[0]).name;requested=sys.argv[1:];args=list(requested)
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
for key in ['MAKEFILES','GNUMAKEFLAGS','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','GCC_SPECS','MAKEFLAGS','MFLAGS','MAKELEVEL','LD_PRELOAD','LD_LIBRARY_PATH']:os.environ.pop(key,None)
if name=='make':
 filtered=[];i=0
 while i<len(args):
  a=args[i]
  if a in ['-j','--jobs']:
   i+=1
   if i<len(args) and args[i].isdigit():i+=1
   continue
  if a.startswith('-j') or a.startswith('--jobs='):i+=1;continue
  if a.startswith('-') and not a.startswith('--') and 'j' in a[1:]:raise ValueError('combined make job option forbidden')
  if re.match(r'^\s*(?:CXX|CC|OBJCACHE|MAKE|SHELL|VM_PARALLEL_BUILDS)\s*(?::=|::=|:::=|\+=|\?=|!=|=)',a):raise ValueError('untrusted make override')
  filtered.append(a);i+=1
 args=['-j1','VM_PARALLEL_BUILDS=0']+filtered+['CXX='+str(wrappers/'g++'),'CC='+str(wrappers/'gcc'),'OBJCACHE=','MAKE='+str(wrappers/'make')]
 tool=Path('/usr/bin/make')
elif name=='verilator':
 tool=root/'usr/bin/verilator'
 if not any(a in ['--version','-V','--help'] for a in args):
  for i,a in enumerate(args):
   if a=='--threads' and (i+1==len(args) or args[i+1]!='1'):raise ValueError('conflicting Verilator threads')
   if a.startswith('--threads=') and a!='--threads=1':raise ValueError('conflicting Verilator threads')
   if a in ['--build','--binary','-j'] or a.startswith('--build-jobs'):raise ValueError('implicit Verilator native build forbidden')
  if '--threads' not in args and '--threads=1' not in args:args+=['--threads','1']
 os.environ['VERILATOR_ROOT']=str(root/'usr/share/verilator')
elif name in ['g++','c++']:tool=Path('/usr/bin/x86_64-linux-gnu-g++-14')
elif name=='gcc':tool=Path('/usr/bin/x86_64-linux-gnu-gcc-14')
else:raise ValueError('unknown wrapper')
event=('verilator_probe' if any(a in ['--version','-V','--help'] for a in requested) else 'verilator_build') if name=='verilator' else ('make_enter' if name=='make' else 'compiler_enter')
record=dict(event=event,tool=name,requested=requested,argv=[str(tool)]+args,as_limit=resource.getrlimit(resource.RLIMIT_AS),affinity=sorted(os.sched_getaffinity(0)))
line=(json.dumps(record,separators=(',',':'))+'\n').encode()
fd=os.open(os.environ['QKV_NATIVE_AUDIT'],os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
try:
 if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('native audit not regular')
 if os.fstat(fd).st_size+len(line)>1024*1024:raise ValueError('native argv log cap')
 os.write(fd,line)
finally:os.close(fd)
os.execv(str(tool),[str(tool)]+args)
