"""NEW toolchain inventory, never an inherited qualification or software install.
Read official runner JAVA_HOME_21_X64; require exact selected version/vendor.
All subsequent compile/canonical/transform/SV gates remain mandatory.
"""
import argparse,hashlib,json,os,pathlib,re,subprocess,platform
VERSION='21.0.13';BUILD='21.0.13+9'
RUNTIME_FORMS=(BUILD,BUILD+'-LTS')
def inventory(home):
 home=pathlib.Path(home).resolve(strict=True)
 release={}
 for line in (home/'release').read_text().splitlines():
  m=re.fullmatch(r'([A-Z_]+)="([^"\n]*)"',line)
  if m:release[m[1]]=m[2]
 if release.get('JAVA_VERSION')!=VERSION or release.get('JAVA_RUNTIME_VERSION') not in RUNTIME_FORMS or release.get('IMPLEMENTOR')!='Eclipse Adoptium':raise ValueError('Runner JDK drift; explicitly select/review a NEW tool identity')
 if platform.machine() not in ('x86_64','amd64') or release.get('OS_ARCH') not in ('x86_64','amd64'):raise ValueError('amd64 required')
 if os.environ.get('ImageVersion')!='20261026.354.1':raise ValueError('Runner image rolled; explicit new image review required')
 probe=subprocess.run([str(home/'bin/java'),'-XshowSettings:properties','-version'],capture_output=True,text=True,timeout=20,check=True)
 if len(probe.stdout)+len(probe.stderr)>65536:raise ValueError('runtime probe log cap')
 props=dict(re.findall(r'^\s*(java.runtime.version|os.arch|java.vendor) = (.*)$',probe.stderr,re.M))
 if props.get('java.runtime.version') not in RUNTIME_FORMS or props.get('os.arch') not in ('amd64','x86_64') or props.get('java.vendor')!='Eclipse Adoptium':raise ValueError('actual JVM version/vendor/arch mismatch')
 rows=[];total=0
 for p in sorted(home.rglob('*')):
  if p.is_symlink():
   target=p.resolve(strict=True)
   if not target.is_relative_to(home):raise ValueError('External JDK symlink requires explicit dependency inventory')
   rows.append({'path':str(p.relative_to(home)),'symlink':os.readlink(p)});continue
  if not p.is_file():continue
  total+=p.stat().st_size
  if total>600_000_000:raise ValueError('JDK tree budget')
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  rows.append({'path':str(p.relative_to(home)),'bytes':p.stat().st_size,'sha256':h})
 return {'status':'NEW_TOOLCHAIN_INVENTORY_ONLY_PENDING_FRESH_QUALIFICATION','version':release,'actual_runtime_properties':props,'tree_bytes':total,'files':rows,'image_version':os.environ.get('ImageVersion'),'image_os':os.environ.get('ImageOS'),'required_gates':['fixed155 compile','fixed canonical AST90464ff baseline','original vs portable transform identity','same generated SV comparison/new approved SV hash','all five same binary numerical execution'],'old_pass_transfer':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--java-home',required=True);a.add_argument('--output',type=pathlib.Path,required=True);v=a.parse_args()
 if v.output.exists():raise ValueError('fresh inventory output required')
 result=inventory(v.java_home);v.output.write_text(json.dumps(result,indent=2)+'\n')
