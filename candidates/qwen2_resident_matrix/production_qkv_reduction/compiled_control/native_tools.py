"""Pinned, offline native tool admission. No downloaded binary runs at import."""
import hashlib,json,os,sys,re
from pathlib import Path
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def preflight(root):
 pins=json.loads((Path(__file__).parent/'NATIVE_TOOL_PINS.json').read_text())
 actual={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file()}
 need(actual==pins['files'],'exact native tool inventory/hash mismatch')
 for n,h in pins['system'].items():need(sha(Path(n))==h,'system tool drift '+n)
 info=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 need(int(info['MemAvailable'].split()[0])>=4*1024*1024,'available memory below 4GiB')
 need(bool(os.sched_getaffinity(0)),'no allowed CPU')
def activate(root,out):
 wrappers=out/'native_wrappers';wrappers.mkdir()
 for name in ['verilator','make','g++','gcc','c++']:
  p=wrappers/name;p.write_text('#!'+sys.executable+'\n'+(Path(__file__).parent/'native_wrapper.py').read_text());p.chmod(0o700)
 with (out/'native_argv.jsonl').open('xb') as audit:pass
 os.environ['QKV_NATIVE_ROOT']=str(root);os.environ['QKV_NATIVE_AUDIT']=str(out/'native_argv.jsonl')
 os.environ['QKV_NATIVE_WRAPPERS']=str(wrappers)
 os.environ['PATH']=str(wrappers)+':/usr/bin:/bin'
 for n in ['MAKEFILES','GNUMAKEFLAGS','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','GCC_SPECS','MAKEFLAGS','MFLAGS','MAKELEVEL','VERILATOR_ROOT','VERILATOR_BIN','CCACHE_PREFIX','CCACHE_DIR','LD_PRELOAD','LD_LIBRARY_PATH','CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS','ARFLAGS','VERILATOR_FLAGS','VERILATOR_CXX','CXX','CC']:
  os.environ.pop(n,None)
 os.environ.update(CXX=str(wrappers/'g++'),CC=str(wrappers/'gcc'),OBJCACHE='',CCACHE_DISABLE='1')

def validate_audit(path):
 records=[json.loads(line) for line in path.read_text().splitlines()]
 need(bool(records),'missing native argv evidence')
 for row in records:
  need(row['as_limit']==[2*1024**3]*2 and len(row['affinity'])==1,'native limit drift')
  if row['tool']=='make':
   need(row['argv'].count('-j1')==1,'native make not single job')
   need([a for a in row['argv'] if re.match(r'^\s*VM_PARALLEL_BUILDS\s*(?::=|::=|:::=|\+=|\?=|!=|=)',a)]==['VM_PARALLEL_BUILDS=0'],'native single translation unit config')
   need(not any(x.startswith('--jobs') or (x.startswith('-j') and x!='-j1') for x in row['argv'][1:]),'conflicting native jobs')
 need(any(r['tool']=='make' for r in records),'no native build observed')
 need(any(r['tool'] in ['g++','c++'] for r in records),'compiler wrapper bypass')
 need(any(r['tool']=='verilator' for r in records),'Verilator wrapper bypass')
