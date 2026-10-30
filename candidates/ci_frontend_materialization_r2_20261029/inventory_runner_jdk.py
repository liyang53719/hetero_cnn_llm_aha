"""NEW toolchain inventory, never an inherited qualification or software install.
Read official runner JAVA_HOME_21_X64; require exact selected version/vendor.
All subsequent compile/canonical/transform/SV gates remain mandatory.
"""
import argparse,hashlib,json,os,pathlib,re,subprocess,platform,tempfile,resource,stat
class InventoryFailure(Exception):
 def __init__(self,code,metadata=None):self.code=code;self.metadata=metadata;super().__init__(code)
def need(ok,code):
 if not ok:raise InventoryFailure(code)
PUBLIC_EXTERNALS={'lib/security/cacerts':'/etc/ssl/certs/adoptium/cacerts'}
def external_record(home,p,target):
 alias=str(p.relative_to(home));meta={'alias_relative':alias,'resolved_target':str(target),'bytes':target.stat().st_size if target.is_file() else None}
 if PUBLIC_EXTERNALS.get(alias)!=str(target):raise InventoryFailure('JDK_UNKNOWN_EXTERNAL_ALIAS',meta)
 st=target.stat()
 if not stat.S_ISREG(st.st_mode) or target.is_symlink() or not 0<=st.st_size<=4*1024*1024:raise InventoryFailure('JDK_EXTERNAL_TARGET_NOT_BOUNDED_REGULAR',meta)
 with target.open('rb') as f:meta['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
 return meta
VERSION='21.0.13';BUILD='21.0.13+9'
RUNTIME_FORMS=(BUILD,BUILD+'-LTS')
def inventory(home,fresh_host_contract=None):
 home=pathlib.Path(home).resolve(strict=True)
 release={}
 for line in (home/'release').read_text().splitlines():
  m=re.fullmatch(r'([A-Z_]+)="([^"\n]*)"',line)
  if m:release[m[1]]=m[2]
 if release.get('JAVA_VERSION')!=VERSION or release.get('JAVA_RUNTIME_VERSION') not in RUNTIME_FORMS or release.get('IMPLEMENTOR')!='Eclipse Adoptium':raise InventoryFailure('JDK_RELEASE_IDENTITY_MISMATCH')
 if platform.machine() not in ('x86_64','amd64') or release.get('OS_ARCH') not in ('x86_64','amd64'):raise InventoryFailure('JDK_ARCH_MISMATCH')
 if fresh_host_contract is None:
  if os.environ.get('ImageVersion')!='20261026.354.1':raise InventoryFailure('RUNNER_IMAGE_MISMATCH')
 else:
  from fresh_host import validate_contract
  validate_contract(fresh_host_contract) # permits inventory only; original version/vendor still mandatory
 def probe_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
 with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
  probe=subprocess.run([str(home/'bin/java'),'-XshowSettings:properties','-version'],stdout=stdout,stderr=stderr,timeout=20,check=True,preexec_fn=probe_limit)
  stdout.seek(0);stderr.seek(0);probe_stdout=stdout.read(65536);probe_stderr=stderr.read(65536)
  if len(probe_stdout)+len(probe_stderr)>=65536:raise InventoryFailure('JDK_PROBE_LOG_CAP')
 props=dict(re.findall(r'^\s*(java.runtime.version|os.arch|java.vendor) = (.*)$',probe_stderr.decode('utf-8','replace'),re.M))
 if props.get('java.runtime.version') not in RUNTIME_FORMS or props.get('os.arch') not in ('amd64','x86_64') or props.get('java.vendor')!='Eclipse Adoptium':raise InventoryFailure('JDK_RUNTIME_IDENTITY_MISMATCH')
 rows=[];total=0
 for p in sorted(home.rglob('*')):
  if p.is_symlink():
   target=p.resolve(strict=True)
   row={'path':str(p.relative_to(home)),'symlink':os.readlink(p),'resolved_target':str(target)}
   if not target.is_relative_to(home):row['external_dependency']=external_record(home,p,target)
   rows.append(row);continue
  if not p.is_file():continue
  total+=p.stat().st_size
  if total>600_000_000:raise InventoryFailure('JDK_TREE_BUDGET')
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  rows.append({'path':str(p.relative_to(home)),'bytes':p.stat().st_size,'sha256':h})
 return {'status':'NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION','version':release,'actual_runtime_properties':props,'tree_bytes':total,'files':rows,'image_version':os.environ.get('ImageVersion'),'image_os':os.environ.get('ImageOS'),'required_gates':['fixed155 compile','fixed canonical AST90464ff baseline','original vs portable transform identity','same generated SV comparison/new approved SV hash','all five same binary numerical execution'],'old_pass_transfer':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--java-home',required=True);a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--fresh-host-contract',type=pathlib.Path);a.add_argument('--fresh-host-contract-sha256');v=a.parse_args()
 if v.output.exists():raise ValueError('fresh inventory output required')
 try:
  contract=None
  if v.fresh_host_contract is not None or v.fresh_host_contract_sha256 is not None:
   from fresh_host import load_contract
   contract=load_contract(v.fresh_host_contract,v.fresh_host_contract_sha256)
  result=inventory(v.java_home,contract)
 except Exception as e:
  code=e.code if isinstance(e,InventoryFailure) else ('JDK_PROBE_TIMEOUT' if isinstance(e,subprocess.TimeoutExpired) else 'JDK_PROBE_NONZERO' if isinstance(e,subprocess.CalledProcessError) else 'JDK_FILESYSTEM_ERROR' if isinstance(e,OSError) else 'JDK_UNCLASSIFIED_FAILURE')
  result={'status':'FAIL_JDK_INVENTORY','failure_code':code,'probe_timeout_seconds':20,'root_cause':'NOT_ESTABLISHED','old_pass_transfer':False}
  if isinstance(e,subprocess.CalledProcessError):result['probe_native_exit']=e.returncode
  if isinstance(e,InventoryFailure) and e.metadata is not None:result['external_alias_metadata']=e.metadata
  v.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(1)
 v.output.write_text(json.dumps(result,indent=2)+'\n')
