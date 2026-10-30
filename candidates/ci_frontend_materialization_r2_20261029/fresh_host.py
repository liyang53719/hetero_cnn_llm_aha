"""Bounded fresh-host identity only, never old PASS transfer or CPU-policy waiver.
Called inside existing owning bootstrap before expensive compilation. Not full OS
attestation: kernel/package labels are provenance; explicit execution files are pins.
"""
import argparse, hashlib, importlib, json, os, pathlib, platform, re, subprocess, sys, time
P=pathlib.Path
INJECTION=('LD_PRELOAD','LD_LIBRARY_PATH','LD_AUDIT','LD_DEBUG','PYTHONPATH','PYTHONHOME','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','PERL5LIB','PERL5OPT','BASH_ENV','ENV','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH')
KEYS={'schema','run_id','source_commit','launch_commit'}
def need(v,m):
 if not v:raise ValueError(m)
def sha(p):
 with P(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def validate_contract(c,identity=None,env=None):
 env=os.environ if env is None else env
 need(isinstance(c,dict) and set(c)==KEYS and c['schema']=='BOUNDED_FRESH_HOST_V1','explicit fresh-host contract')
 need(type(c['run_id']) is int and c['run_id']>0 and all(isinstance(c[k],str) and re.fullmatch('[0-9a-f]{40}',c[k]) for k in ('source_commit','launch_commit')) and c['source_commit']!=c['launch_commit'],'contract identity fields')
 need(str(c['run_id'])==env.get('GITHUB_RUN_ID') and c['launch_commit']==env.get('GITHUB_SHA') and env.get('GITHUB_RUN_ATTEMPT')=='1','fresh actual first owning job')
 if identity is not None:need(all(c[k]==identity[k] for k in ('run_id','source_commit','launch_commit')),'contract source/run/launch mismatch')
 return c
def load_contract(path,digest,identity=None):
 need(path is not None and isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'contract path/hash pair')
 p=P(path);need(p.is_file() and not p.is_symlink() and p.stat().st_size<4096 and sha(p)==digest,'pinned bounded contract')
 return validate_contract(json.loads(p.read_text()),identity)
def reject_injection(env):
 need(not any(env.get(k) for k in INJECTION),'ambient execution search-path injection')
# Fixed production policy: same system/toolcache families as before. Resolve
# spelling and aliases before admission; a lexical '..' is not itself an escape.
DEPENDENCY_ROOTS=(P('/usr'),P('/lib'),P('/lib64'),P('/opt/hostedtoolcache'))
QUERY_ROLES={'SYSTEM_TOOL','JDK_EXECUTABLE','JDK_LIBRARY','VERILATOR_BINARY','PYTHON_EXTENSION','UNKNOWN'}
REJECTIONS={'UNRESOLVED_LIBRARY','EMPTY_DEPENDENCY_LIST','MISSING_TARGET','NONREGULAR_TARGET','CANONICAL_ROOT_REJECTED'}
class DependencyRejected(ValueError):
 def __init__(self,kind,parent_component=False):
  need(kind in REJECTIONS,'fixed dependency rejection kind')
  self.rejection_kind=kind;self.parent_component=bool(parent_component)
  super().__init__('unexpected ELF dependency root' if kind=='CANONICAL_ROOT_REJECTED' else 'unresolved ELF dependency' if kind in ('UNRESOLVED_LIBRARY','EMPTY_DEPENDENCY_LIST') else 'unresolved ELF dependency target')
def dependency_roots():
 # System aliases /lib -> /usr/lib are legal, but a trusted root may not turn an
 # unrelated directory into an approved dependency location through a symlink.
 roots=[]
 for root in DEPENDENCY_ROOTS:
  if not root.exists():continue
  resolved=root.resolve(strict=True)
  need(resolved.is_dir() and any(resolved.is_relative_to(p) for p in DEPENDENCY_ROOTS),'approved dependency root alias escaped')
  roots.append(resolved)
 need(roots,'approved dependency roots unavailable')
 return tuple(roots)
def resolve_dependency(path,roots=None):
 p=P(path);parent='..' in p.parts
 if not p.is_absolute():raise DependencyRejected('CANONICAL_ROOT_REJECTED',parent)
 lexical=DEPENDENCY_ROOTS if roots is None else tuple(roots)
 if not any(P(os.path.normpath(str(p))).is_relative_to(root) for root in lexical):raise DependencyRejected('CANONICAL_ROOT_REJECTED',parent)
 try:r=p.resolve(strict=True)
 except (OSError,RuntimeError) as exc:raise DependencyRejected('MISSING_TARGET',parent) from exc
 allowed=dependency_roots() if roots is None else tuple(roots)
 if not any(r.is_relative_to(root) for root in allowed):raise DependencyRejected('CANONICAL_ROOT_REJECTED',parent)
 if not r.is_file():raise DependencyRejected('NONREGULAR_TARGET',parent)
 return r
def dependency_paths(text,roots=None):
 if 'not found' in text or '=> not' in text:raise DependencyRejected('UNRESOLVED_LIBRARY')
 paths=re.findall(r'(?:=>\s*)?(/[^\s]+)\s+\(',text)
 if not paths:raise DependencyRejected('EMPTY_DEPENDENCY_LIST')
 for path in paths:resolve_dependency(path,roots)
 return paths # retain original loader spelling so add() records raw -> real alias
def validate_compile_inventory(record):
 need(record.get('schema')=='INSTALLED_GNU_BUILD_TOOLS_V1' and record.get('qualification')=='IDENTITY_AND_SUPPORTED_OPTIONS_ONLY_NOT_COMPILE_OR_NUMERICAL_PASS','original GNU identity scope')
 deps=record.get('dynamic_dependencies');tools=record.get('compile_tools')
 need(isinstance(deps,dict) and isinstance(tools,dict) and bool(tools) and set(deps)==set(tools),'all GNU tool loader queries recorded')
 for name,text in deps.items():
  need(isinstance(text,str) and len(text.encode())<131072,'bounded GNU dependency query')
  need('not found' not in text and '=> not' not in text,'unresolved GNU tool ELF dependency '+name)
 return record
def jdk_query_context(home):
 home=P(home).resolve(strict=True);roots=[(home/'lib/server').resolve(strict=True),(home/'lib').resolve(strict=True)]
 need(all(p.is_dir() and p.is_relative_to(home) for p in roots),'JDK query roots must stay in inventoried home')
 return {'LD_LIBRARY_PATH':':'.join(map(str,roots))}
def inventory(contract,java_home,verilator_root):
 validate_contract(contract);reject_injection(os.environ)
 need(sys.version_info[:2]==(3,12) and platform.machine()=='x86_64','original Python/architecture contract')
 need(platform.system()=='Linux','Linux runtime required')
 os_release=platform.freedesktop_os_release()
 need(os_release.get('ID')=='ubuntu' and os_release.get('VERSION_ID')=='24.04' and os.environ.get('ImageOS')=='ubuntu24','explicit Ubuntu24 fresh-host profile')
 need(re.fullmatch(r'[0-9]{8}\.[0-9]+\.[0-9]+',os.environ.get('ImageVersion','')) is not None,'record actual runner image provenance')
 start=time.monotonic();pins={};aliases={};total=0
 def add(path,dependency=False):
  nonlocal total
  p=P(path);r=resolve_dependency(p) if dependency else p.resolve(strict=True);need(r.is_file(),'regular runtime dependency required')
  if p!=r:aliases[str(p)]=str(r)
  if str(r) not in pins:
   total+=r.stat().st_size;need(total<=3*1024**3 and len(pins)<10000 and time.monotonic()-start<240,'bounded identity inventory cap')
   pins[str(r)]=sha(r)
  return r
 env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LANG':'C'}
 def query(argv,context=None):
  query_env=dict(env);query_env.update(context or {})
  r=subprocess.run(list(map(str,argv)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=query_env,timeout=15)
  need(r.returncode==0 and len(r.stdout)+len(r.stderr)<131072,'bounded dependency query failed')
  return r.stdout.decode('utf-8','strict')
 # Bound the actual interpreter and stdlib modules used by bootstrap/materializers,
 # not every Python module or every OS file. Native extension dependencies included.
 modules=('argparse','hashlib','json','pathlib','platform','subprocess','tempfile','resource','stat','shutil','urllib.request','ssl','zipfile','tarfile','gzip','bz2','lzma','ctypes','encodings.utf_8','encodings.ascii')
 for name in modules:importlib.import_module(name)
 python_root=P(sys.base_prefix).resolve();native=[]
 for module in list(sys.modules.values()):
  f=getattr(module,'__file__',None)
  if not f:continue
  p=P(f)
  if p.is_file() and p.resolve().is_relative_to(python_root) and ('site-packages' not in p.parts and 'dist-packages' not in p.parts):
   p=add(p)
   if p.suffix=='.so':native.append(p)
 tools=[P(sys.executable),P('/bin/sh'),P('/bin/bash'),P('/usr/bin/perl'),P('/usr/bin/readelf'),P('/usr/bin/dirname'),P('/usr/bin/git'),P('/usr/bin/gh'),P('/usr/bin/dpkg-deb'),P('/usr/bin/ldd'),P('/usr/bin/dpkg-query')]
 jh=P(java_home).resolve(strict=True);vr=P(verilator_root).resolve(strict=True);jdk_context=jdk_query_context(jh)
 targets=tools+[jh/'bin/java',vr/'verilator-package/usr/bin/verilator_bin']+list(jh.rglob('*.so'))+native
 dependencies={};query_contexts={}
 for p in targets:
  p=add(p)
  with p.open('rb') as f:elf=f.read(4)==b'\x7fELF'
  if not elf:continue # trusted distro scripts are pinned, not sent to ldd
  role='JDK_LIBRARY' if p.is_relative_to(jh) and p.suffix=='.so' else 'JDK_EXECUTABLE' if p==jh/'bin/java' else 'VERILATOR_BINARY' if p==vr/'verilator-package/usr/bin/verilator_bin' else 'PYTHON_EXTENSION' if p in native else 'SYSTEM_TOOL'
  try:
   dynamic=query(['/usr/bin/readelf','-d',p])
   if 'There is no dynamic section in this file.' in dynamic:
    dependencies[str(p)]=[];continue # actual static ELF, not missing dependency
   context=jdk_context if p.is_relative_to(jh) and p.suffix=='.so' else {}
   output=query(['/usr/bin/ldd',p],context);paths=dependency_paths(output);dependencies[str(p)]=paths;query_contexts[str(p)]=context
   for dep in paths:add(dep,dependency=True) # repeat canonical admission at pin time
  except Exception as exc:
   exc.query_role=role;raise
 for p in (P('/etc/os-release'),P('/usr/bin/perl')):add(p)
 return dict(schema='BOUNDED_FRESH_HOST_IDENTITY_V1',contract=contract,qualification='IDENTITY_ONLY_PENDING_ORIGINAL_BUILD_AND_NUMERICAL_GATES',old_pass_transfer=False,image_version=os.environ.get('ImageVersion'),image_os=os.environ.get('ImageOS'),kernel=platform.release(),python=sys.version,pins=pins,aliases=aliases,elf_dependencies=dependencies,elf_query_contexts=query_contexts,hashed_bytes=total,scope='explicit Python/bootstrap shell tools and JDK/Verilator ELF dependencies; not full OS or numerical qualification',not_qualified=['P0 CPU policy','compiler execution','canonical AST and generated SV','block numerics','final RTL replay'])
def failure_metadata(exc):
 # Fixed codes only; traceback stays local. Unknown exceptions do not invent cause.
 text=str(exc)
 reason='UNCLASSIFIED_EXCEPTION'
 if 'unresolved ELF dependency' in text:reason='ELF_DEPENDENCY_UNRESOLVED'
 elif 'unexpected ELF dependency root' in text:reason='ELF_DEPENDENCY_ROOT_REJECTED'
 elif 'search-path injection' in text:reason='SEARCH_PATH_INJECTION_REJECTED'
 elif 'contract' in text or 'owning job' in text:reason='CONTRACT_REJECTED'
 elif 'JDK query roots' in text:reason='JDK_QUERY_ROOT_REJECTED'
 elif isinstance(exc,subprocess.TimeoutExpired):reason='QUERY_TIMEOUT'
 elif 'dependency query failed' in text:reason='QUERY_FAILED'
 elif isinstance(exc,OSError):reason='FILESYSTEM_UNAVAILABLE'
 result=dict(schema='FRESH_HOST_NATIVE_FAILURE_V1',status='FAILED',phase='BOUNDED_HOST_INVENTORY',reason=reason,numeric_pass=False)
 role=getattr(exc,'query_role','UNKNOWN');result['query_role']=role if isinstance(role,str) and role in QUERY_ROLES else 'UNKNOWN'
 if isinstance(exc,DependencyRejected):result.update(rejection_kind=exc.rejection_kind,had_parent_component=exc.parent_component)
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--contract',type=P,required=True);a.add_argument('--contract-sha256',required=True);a.add_argument('--java-home',type=P,required=True);a.add_argument('--verilator-root',type=P,required=True);a.add_argument('--output',type=P,required=True);v=a.parse_args()
 try:
  c=load_contract(v.contract,v.contract_sha256);need(not v.output.exists(),'fresh receipt only');result=inventory(c,v.java_home,v.verilator_root)
  with v.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 except Exception as exc:
  try:
   with (v.output.parent/'FRESH_HOST_NATIVE_FAILURE.json').open('x') as f:json.dump(failure_metadata(exc),f);f.write('\n')
  except OSError:pass # no invented receipt for abrupt exit/unavailable filesystem
  raise
