"""Fresh same-job ELF startup-library identity; no simulated cycles or arithmetic.
prepare executes only the already pinned system loader --list. Never use for
arbitrary user binaries. Caller must first verify owning build/frozen source proof.
"""
import hashlib,json,pathlib,re,struct,stat,subprocess,tempfile,resource
P=pathlib.Path
INTERPRETERS={'/lib64/ld-linux-x86-64.so.2','/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2'}
def need(v,s):
 if not v:raise ValueError(s)
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p,max_bytes=512*1024**2):
 p=P(p);r=p.resolve(strict=True);s=r.stat();need(stat.S_ISREG(s.st_mode)and 0<=s.st_size<=max_bytes,'bounded regular ABI file');return dict(path=str(p),resolved=str(r),bytes=s.st_size,sha256=sha(r))
CACHE_NAMES=('HOME','TMPDIR','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME','TORCH_HOME','NUMBA_CACHE_DIR','MPLCONFIGDIR')
_OWNED_ENV_BINDING=None
_WORKSPACE_LOADER_BINDING=None
WORKSPACE_HELPER_SHA256='f310ea005bdaabc81d7d9b07d6be2eab8dc4ed435709a1cae1b5037ec9978070'

def canonical_directory(value):
 p=P(value);need(p.is_absolute()and '..'not in p.parts and p.is_dir(),'absolute existing owned directory')
 need(all(not q.is_symlink()for q in (p,*p.parents))and p==p.resolve(),'canonical owned directory without aliases')
 return p

def owned_environment(path,expected_sha):
 path=P(path);need(path.is_absolute()and path.is_file()and not path.is_symlink()and path.stat().st_size<=65536 and sha(path)==expected_sha,'independently pinned environment contract')
 need(path==path.resolve()and all(not q.is_symlink()for q in path.parents),'canonical environment metadata path')
 v=json.loads(path.read_text());need(set(v)=={'schema','identity','owner_root','watched_roots','cache_root','cache_paths'},'exact environment contract fields')
 need(v['schema']=='OWNED_EXECUTION_ENVIRONMENT_V1','owned environment schema')
 identity=v['identity']
 if isinstance(identity,dict) and identity.get('schema')=='CLOUD_EXECUTOR_IDENTITY_V1':
  import importlib.util
  helper=P(__file__).resolve().parent.parent/'executor_identity.py'
  need(sha(helper)=='e3011725f319f543c0d9ba08075efa9a9341eded6112187de4afe611d1987af4','reviewed cloud executor helper')
  spec=importlib.util.spec_from_file_location('abi_cloud_executor',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.verify_owner(identity)
 else:
  need(set(identity)=={'run_id','source_commit','launch_commit'}and type(identity['run_id'])is int and identity['run_id']>0,'owning job identity')
  for k in ('source_commit','launch_commit'):need(isinstance(identity[k],str)and re.fullmatch('[0-9a-f]{40}',identity[k])is not None,'exact environment commit identity')
  need(identity['source_commit']!=identity['launch_commit'],'distinct source/launch')
 owner=canonical_directory(v['owner_root']);root=canonical_directory(v['cache_root'])
 need(root!=owner and root.is_relative_to(owner)and path.is_relative_to(owner),'environment metadata/cache under owner')
 watched=v['watched_roots'];need(isinstance(watched,list)and 1<=len(watched)<=64,'bounded watched roots')
 watched=[canonical_directory(p)for p in watched]
 need(all(p==owner or p.is_relative_to(owner)for p in watched)and any(root.is_relative_to(p)for p in watched),'declared cache watch closure within owner')
 need(set(v['cache_paths'])==set(CACHE_NAMES),'exact cache key allowlist')
 paths={}
 for key in CACHE_NAMES:
  p=canonical_directory(v['cache_paths'][key]);need(p==root/key.lower(),'fixed cache directory mapping');paths[key]=str(p)
 return dict(path=str(path),bytes=path.stat().st_size,sha256=expected_sha),identity,paths

def configure_owned_environment(path,expected_sha,expected_identity):
 global _OWNED_ENV_BINDING
 _,identity,_=owned_environment(path,expected_sha);need(identity==expected_identity,'environment belongs to exact owning job');value=(str(P(path)),expected_sha)
 need(_OWNED_ENV_BINDING is None or _OWNED_ENV_BINDING==value,'immutable module environment binding')
 _OWNED_ENV_BINDING=value

def owned_environment_pin():
 need(_OWNED_ENV_BINDING is not None,'explicit owning environment required, no inheritance')
 return owned_environment(*_OWNED_ENV_BINDING)[0]

def clean_env():
 need(_OWNED_ENV_BINDING is not None,'explicit owning environment required, no inheritance')
 _,_,paths=owned_environment(*_OWNED_ENV_BINDING)
 return dict({'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'},**paths)

def elf_info(path,require_interpreter=True):
 need(type(require_interpreter)is bool,'explicit interpreter policy')
 p=P(path);size=p.stat().st_size;need(64<=size<=4*1024**3,'ELF file bound')
 with p.open('rb')as f:
  def read(off,n):
   need(0<=off<=size and 0<=n<=1024**2 and off+n<=size,'ELF bounded offset');f.seek(off);b=f.read(n);need(len(b)==n,'ELF truncated');return b
  h=read(0,64);need(h[:6]==b'\x7fELF\x02\x01' and h[6]==1,'ELF64 little endian version')
  typ,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,*_=struct.unpack('<HHIQQQIHHHHHH',h[16:]);need(typ in (2,3)and machine==62 and version==1 and ehsize==64 and phsize==56 and 0<phnum<=128,'ELF x86_64 program header')
  ph=[struct.unpack('<IIQQQQQQ',read(phoff+i*56,56))for i in range(phnum)]
  interp=[q for q in ph if q[0]==3];need(len(interp)==1 if require_interpreter else len(interp)<=1,'bounded PT_INTERP count');loader=None
  if interp:
   need(1<interp[0][5]<=4096,'bounded PT_INTERP');text=read(interp[0][2],interp[0][5]);need(text.endswith(b'\0')and text.count(b'\0')==1,'interpreter string');loader=text[:-1].decode('ascii');need(loader in INTERPRETERS,'reviewed system interpreter only')
  dyn=[q for q in ph if q[0]==2];need(len(dyn)==1 and dyn[0][5]<=65536 and dyn[0][5]%16==0,'bounded dynamic table');entries=[]
  for i in range(dyn[0][5]//16):
   tag,val=struct.unpack('<qQ',read(dyn[0][2]+16*i,16))
   if tag==0:break
   entries.append((tag,val))
  else:raise ValueError('unterminated dynamic table')
  need(not any(t in (15,29,0x6ffffefb,0x6ffffefc,0x7ffffffd,0x7fffffff)for t,v in entries),'RPATH/RUNPATH/AUDIT/DEPAUDIT/FILTER/AUXILIARY not admitted')
  st=[v for t,v in entries if t==5];sz=[v for t,v in entries if t==10];need(len(st)==len(sz)==1 and 0<sz[0]<=1024**2,'bounded dynamic strings')
  loads=[q for q in ph if q[0]==1 and q[3]<=st[0] and st[0]+sz[0]<=q[3]+q[5]];need(len(loads)==1,'mapped dynamic string table');q=loads[0];strings=read(q[2]+st[0]-q[3],sz[0]);names=[]
  for t,v in entries:
   if t!=1:continue
   need(v<len(strings),'needed string offset');end=strings.find(b'\0',v);need(end>v,'needed terminator');n=strings[v:end].decode('ascii');need(re.fullmatch(r'[A-Za-z0-9_+.-]{1,128}',n)is not None,'plain SONAME only');names.append(n)
  need((0<len(names)if require_interpreter else 0<=len(names))and len(names)<=32 and len(set(names))==len(names),'needed dependency count')
 return {'interpreter':loader,'needed':names,'machine':'ELF64_LE_X86_64'}
def parse_list(text,expected_interpreter=None):
 need(expected_interpreter is None or expected_interpreter in INTERPRETERS,'explicit reviewed PT_INTERP alias')
 need(len(text.encode())<=65536,'bounded loader output');resolved={};vdso=0
 for line in text.splitlines():
  line=line.strip()
  if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)',line):vdso+=1;continue
  m=re.fullmatch(r'([A-Za-z0-9_+.-]+) => (/[^\s]+) \(0x[0-9a-f]+\)',line)
  if m:key,path=m.groups()
  else:
   alias=re.fullmatch(r'(/[^\s]+) => (/[^\s]+) \(0x[0-9a-f]+\)',line)
   if alias is not None:
    need(expected_interpreter is not None and alias[1]==expected_interpreter,'only actual workspace PT_INTERP alias')
    key=P(expected_interpreter).name;path=alias[2]
   else:
    m=re.fullmatch(r'(/[^\s]+) \(0x[0-9a-f]+\)',line);need(m is not None,'unknown/unresolved loader output');path=m[1];key=P(path).name
  need(key not in resolved and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',path),'unique safe resolved library');resolved[key]=path
 need(vdso==1 and 1<=len(resolved)<=64,'complete loader dependency list');return resolved

def _list(loader,binary,workspace_prefix=None):
 def caps():
  resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536));resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 with tempfile.TemporaryFile(dir=clean_env()['TMPDIR'])as out,tempfile.TemporaryFile(dir=clean_env()['TMPDIR'])as err:
  p=subprocess.Popen(([str(loader),'--list',str(binary)]if workspace_prefix is None else [*workspace_prefix,'--list',str(binary)]),stdout=out,stderr=err,env=clean_env(),preexec_fn=caps)
  try:p.wait(timeout=20)
  finally:
   if p.poll()is None:p.kill();p.wait()
  out.seek(0);err.seek(0);b=out.read(65537);e=err.read(65537)
  need(p.returncode==0 and not e and len(b)<=65536,'loader list failed or truncated');return b.decode('ascii')
def config_pins():
 preload=P('/etc/ld.so.preload');need(not preload.exists()or preload.stat().st_size==0,'nonempty system preload not admitted')
 cache=P('/etc/ld.so.cache');need(cache.is_file(),'loader cache required')
 return {'cache':pin(cache),'preload':pin(preload)if preload.exists()else None}
def check_configs(c):need(config_pins()==c,'loader cache/preload drift')
def workspace_module():
 import types
 path=P(__file__).resolve().with_name('workspace_loader.py');raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==WORKSPACE_HELPER_SHA256,'reviewed workspace loader helper')
 m=types.ModuleType('reviewed_workspace_loader');m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

def configure_workspace_loader(path,expected_sha,expected_builder_source,artifact_manifest_sha):
 global _WORKSPACE_LOADER_BINDING
 path=P(path);contract={'path':str(path),'bytes':path.stat().st_size,'sha256':expected_sha}
 doc=workspace_module().read(contract)
 need(doc['builder_source_commit']==expected_builder_source and doc['artifact_manifest_sha256']==artifact_manifest_sha,'workspace original builder/artifact identity')
 value=(str(path),expected_sha,expected_builder_source,artifact_manifest_sha)
 need(_WORKSPACE_LOADER_BINDING is None or _WORKSPACE_LOADER_BINDING==value,'immutable workspace loader binding');_WORKSPACE_LOADER_BINDING=value

def workspace_verified(binary,binary_sha,tool_manifest,tool_sha):
 need(_WORKSPACE_LOADER_BINDING is not None,'configured workspace loader required')
 path,digest,source,artifact=_WORKSPACE_LOADER_BINDING;p=P(path)
 contract={'path':path,'bytes':p.stat().st_size,'sha256':digest};module=workspace_module()
 verified=module.verify(contract,binary,binary_sha,tool_manifest,tool_sha,elf_info)
 need(verified['builder_source_commit']==source and verified['artifact_manifest_sha256']==artifact,'immutable workspace builder/artifact')
 return module,verified

def execution_argv(binary,runtime,output,cycles):
 argv=list(map(str,(binary,runtime,output,cycles)))
 if _WORKSPACE_LOADER_BINDING is None:return argv
 path,digest,source,artifact=_WORKSPACE_LOADER_BINDING;p=P(path);module=workspace_module();doc=module.read({'path':path,'bytes':p.stat().st_size,'sha256':digest})
 module,verified=workspace_verified(binary,doc['binary']['sha256'],doc['tool_manifest']['path'],doc['tool_manifest']['sha256'])
 return module.prefix(verified)+argv

def prepare_workspace(binary,binary_sha,tool_manifest,tool_sha,out):
 binary=P(binary).resolve();tool_manifest=P(tool_manifest).resolve();out=P(out);need(not out.exists(),'fresh workspace ABI receipt')
 module,verified=workspace_verified(binary,binary_sha,tool_manifest,tool_sha);configs=config_pins();before=pin(binary,4<<30);environment=clean_env();owner=owned_environment_pin()
 text=_list(verified['loader']['resolved'],binary,module.prefix(verified));libraries=module.resolved_libraries(parse_list(text,expected_interpreter=verified['elf']['interpreter']),verified,pin)
 _,after=workspace_verified(binary,binary_sha,tool_manifest,tool_sha)
 need(after==verified and pin(binary,4<<30)==before and clean_env()==environment and owned_environment_pin()==owner,'workspace ABI probe inputs changed');check_configs(configs)
 receipt=dict(schema='WORKSPACE_ELF_STARTUP_ABI_OWNED_ENV_V1',status='STARTUP_RESOLUTION_MATCHES_ORIGINAL_BUILDER_WORKSPACE_BYTES_NOT_DUT_EXECUTION',binary=before,tool_manifest={'path':str(tool_manifest),'sha256':tool_sha},elf=verified['elf'],loader=pin(verified['loader']['resolved']),libraries=libraries,configs=configs,owned_environment=owner,environment=environment,later_dlopen='NOT_QUALIFIED',loader_output_sha256=hashlib.sha256(text.encode()).hexdigest(),workspace_loader=verified['manifest'])
 raw=json.dumps(receipt,indent=2)+'\n';need(len(raw.encode())<=65536,'bounded workspace ABI receipt')
 with out.open('x')as f:f.write(raw)
 return receipt

def verify_workspace(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha):
 receipt=P(receipt);need(receipt.is_file()and not receipt.is_symlink()and receipt.stat().st_size<=65536 and sha(receipt)==receipt_sha,'pinned workspace ABI receipt');r=json.loads(receipt.read_text())
 need(set(r)=={'schema','status','binary','tool_manifest','elf','loader','libraries','configs','owned_environment','environment','later_dlopen','loader_output_sha256','workspace_loader'},'exact workspace ABI receipt fields')
 need(r['schema']=='WORKSPACE_ELF_STARTUP_ABI_OWNED_ENV_V1'and r['status']=='STARTUP_RESOLUTION_MATCHES_ORIGINAL_BUILDER_WORKSPACE_BYTES_NOT_DUT_EXECUTION'and r['later_dlopen']=='NOT_QUALIFIED','workspace startup-only receipt')
 module,verified=workspace_verified(binary,binary_sha,tool_manifest,tool_sha)
 need(r['workspace_loader']==verified['manifest']and r['elf']==verified['elf'],'actual workspace closure binding')
 need(r['owned_environment']==owned_environment_pin()and r['environment']==clean_env(),'same actual owned environment')
 need(r['binary']==pin(binary,4<<30)and r['binary']['sha256']==binary_sha and r['tool_manifest']=={'path':str(P(tool_manifest).resolve()),'sha256':tool_sha},'actual binary/tool ABI identity')
 need(r['loader']==pin(verified['loader']['resolved']),'actual workspace loader bytes')
 need(type(r['libraries'])is dict and set(r['libraries'])==set(verified['libraries']),'exact resolved six-library closure')
 actual=module.resolved_libraries({k:v['path']for k,v in r['libraries'].items()},verified,pin);need(actual==r['libraries'],'workspace startup library/alias drift')
 need(type(r['loader_output_sha256'])is str and re.fullmatch('[0-9a-f]{64}',r['loader_output_sha256']),'bounded loader-output digest');check_configs(r['configs'])
 return dict(status='PASS_STARTUP_ABI_IDENTITY_ONLY',receipt_sha256=receipt_sha,libraries=len(actual),workspace_loader=verified['manifest'])

def prepare(binary,binary_sha,tool_manifest,tool_sha,out):
 if _WORKSPACE_LOADER_BINDING is not None:return prepare_workspace(binary,binary_sha,tool_manifest,tool_sha,out)
 binary=P(binary).resolve();tool_manifest=P(tool_manifest).resolve();out=P(out);need(not out.exists(),'fresh ABI receipt');need(tool_manifest.stat().st_size<=32*1024**2,'bounded build tool manifest');need(sha(binary)==binary_sha and sha(tool_manifest)==tool_sha,'owning binary/tool manifest pins');tool=json.loads(tool_manifest.read_text());need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','tool manifest schema');pins=tool['pins'];info=elf_info(binary);loader=pin(info['interpreter']);need(pins.get(loader['resolved'])==loader['sha256'],'interpreter not in build tool pins');configs=config_pins();before=pin(binary,4*1024**3)
 text=_list(loader['resolved'],binary);resolved=parse_list(text);need(set(info['needed'])<=set(resolved),'direct dependencies absent from loader result');libraries={}
 for n,path in resolved.items():
  v=pin(path);need(pins.get(v['resolved'])==v['sha256'],'resolved library not bound by build tool inventory');libraries[n]=v
 need(loader['resolved']in {v['resolved']for v in libraries.values()},'interpreter absent from resolved list');need(pin(binary,4*1024**3)==before and pin(info['interpreter'])==loader and sha(tool_manifest)==tool_sha,'ABI probe inputs changed');check_configs(configs)
 receipt=dict(schema='SAME_JOB_ELF_STARTUP_ABI_OWNED_ENV_V2',status='STARTUP_RESOLUTION_MATCHES_BUILD_TOOL_PINS_NOT_DUT_EXECUTION',binary=before,tool_manifest={'path':str(tool_manifest),'sha256':tool_sha},elf=info,loader=loader,libraries=libraries,configs=configs,owned_environment=owned_environment_pin(),environment=clean_env(),later_dlopen='NOT_QUALIFIED',loader_output_sha256=hashlib.sha256(text.encode()).hexdigest());raw=json.dumps(receipt,indent=2)+'\n';need(len(raw.encode())<=65536,'bounded ABI receipt');
 with out.open('x')as f:f.write(raw)
 return receipt

def verify(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha):
 if _WORKSPACE_LOADER_BINDING is not None:return verify_workspace(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha)
 receipt=P(receipt);need(receipt.is_file()and not receipt.is_symlink()and receipt.stat().st_size<=65536 and sha(receipt)==receipt_sha,'pinned ABI receipt');r=json.loads(receipt.read_text());need(r['schema']=='SAME_JOB_ELF_STARTUP_ABI_OWNED_ENV_V2'and r['status']=='STARTUP_RESOLUTION_MATCHES_BUILD_TOOL_PINS_NOT_DUT_EXECUTION','ABI receipt scope');need(r['owned_environment']==owned_environment_pin()and r['environment']==clean_env(),'same pinned owned execution environment contract');need(pin(binary,4*1024**3)==r['binary']and r['binary']['sha256']==binary_sha,'binary ABI identity');need(str(P(tool_manifest).resolve())==r['tool_manifest']['path']and sha(tool_manifest)==tool_sha==r['tool_manifest']['sha256'],'tool ABI identity');pins=json.loads(P(tool_manifest).read_text())['pins']
 need(r.get('later_dlopen')=='NOT_QUALIFIED','startup-only scope')
 need(isinstance(r['libraries'],dict) and 1<=len(r['libraries'])<=64,'bounded library map')
 need(set(r['elf']['needed'])<=set(r['libraries']),'missing direct dependency')
 need(r['loader']==pin(r['elf']['interpreter']),'interpreter mapping mismatch')
 need(r['loader']['resolved']in {v['resolved']for v in r['libraries'].values()},'missing interpreter library')
 for v in [r['loader'],*r['libraries'].values()]:need(pin(v['path'])==v and pins.get(v['resolved'])==v['sha256'],'startup library/alias drift')
 need(elf_info(binary)==r['elf'],'ELF identity drift');check_configs(r['configs']);return {'status':'PASS_STARTUP_ABI_IDENTITY_ONLY','receipt_sha256':receipt_sha,'libraries':len(r['libraries'])}

HANDOFF_HELPER_SHA256='06ac175b7c1f8ca5b1dc19891a52c09f58f17fec521ee96e0f581ca4011ef0c5'

def adaptation_checker(contract):
 # Bootstrap checker source trust before any adapter code executes. The hard-pinned
 # handoff helper verifies the external adaptation pin, catalog and checker bytes.
 import types
 path=P(__file__).resolve().with_name('artifact_handoff.py')
 need(path.is_file()and all(not p.is_symlink()for p in(path,*path.parents)),'canonical handoff checker source')
 raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==HANDOFF_HELPER_SHA256,'reviewed handoff checker before import')
 module=types.ModuleType('abi_pinned_artifact_handoff');module.__file__=str(path);exec(compile(raw,str(path),'exec'),module.__dict__)
 return module.adaptation_module(contract)

def configure_cli(args):
 expected=dict(run_id=args.expected_run_id,source_commit=args.expected_source_commit,launch_commit=args.expected_launch_commit)
 loader=getattr(args,'workspace_loader',None);loader_sha=getattr(args,'workspace_loader_sha256',None)
 adaptation=getattr(args,'executor_adaptation',None);adaptation_sha=getattr(args,'executor_adaptation_sha256',None);artifact_sha=getattr(args,'artifact_manifest_sha256',None)
 need((loader is None)==(loader_sha is None)and(adaptation is None)==(adaptation_sha is None),'paired workspace/adaptation pins')
 need((loader is None)==(adaptation is None),'workspace requires explicit executor adaptation')
 if args.executor_identity is not None:
  identity=P(args.executor_identity)
  need(identity.is_absolute()and identity==identity.resolve()and all(not p.is_symlink()for p in(identity,*identity.parents))and identity.is_file()and identity.stat().st_size<=65536 and sha(identity)==args.executor_identity_sha256,'actual executor identity pin')
  expected=json.loads(identity.read_text())
  if adaptation is None:need(expected.get('source_commit')==args.expected_source_commit,'same builder/executor source without adaptation')
  else:
   need(type(artifact_sha)is str and re.fullmatch('[0-9a-f]{64}',artifact_sha),'actual frozen artifact manifest hash')
   mf=P(args.binary).parent/'frozen_artifact.json'
   need(mf.is_absolute()and mf==mf.resolve()and all(not p.is_symlink()for p in(mf,*mf.parents))and mf.is_file()and mf.stat().st_size<=65536 and sha(mf)==artifact_sha,'original frozen artifact pin')
   frozen=json.loads(mf.read_text());builder=frozen['artifact_identity']
   need(builder['source_commit']==args.expected_source_commit and builder['launch_commit']==args.expected_launch_commit and type(builder['run_id'])is int and builder['run_id']==args.expected_run_id,'actual builder launch/source/run')
   directory=P(__file__).resolve().parent.parent;catalog=directory/'SOURCE_PINS.json'
   ap=P(adaptation);contract={'path':str(ap),'bytes':ap.stat().st_size,'sha256':adaptation_sha};source={'path':str(catalog),'bytes':catalog.stat().st_size,'sha256':sha(catalog)}
   module=adaptation_checker(contract)
   module.verify(contract,builder,expected,current_source_pins_pin=source,repo=directory.parents[1])
 else:
  need(args.executor_identity_sha256 is None and loader is None and adaptation is None,'paired cloud execution identity')
 configure_owned_environment(args.owned_environment,args.owned_environment_sha256,expected)
 if loader is not None:configure_workspace_loader(loader,loader_sha,args.expected_source_commit,artifact_sha)

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--binary',type=P,required=True);ap.add_argument('--binary-sha256',required=True);ap.add_argument('--tool-manifest',type=P,required=True);ap.add_argument('--tool-manifest-sha256',required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--expected-run-id',type=int,required=True);ap.add_argument('--expected-source-commit',required=True);ap.add_argument('--expected-launch-commit',required=True);ap.add_argument('--owned-environment',type=P,required=True);ap.add_argument('--owned-environment-sha256',required=True);ap.add_argument('--executor-identity',type=P);ap.add_argument('--executor-identity-sha256');ap.add_argument('--workspace-loader',type=P);ap.add_argument('--workspace-loader-sha256');ap.add_argument('--executor-adaptation',type=P);ap.add_argument('--executor-adaptation-sha256');ap.add_argument('--artifact-manifest-sha256');ap.add_argument('--execute-reviewed-loader-list',action='store_true');args=ap.parse_args()
 need(args.execute_reviewed_loader_list,'explicit reviewed loader-list admission under strict outer supervisor required')
 configure_cli(args)
 prepare(args.binary,args.binary_sha256,args.tool_manifest,args.tool_manifest_sha256,args.output)
 print(json.dumps({'status':'STARTUP_ABI_RECEIPT_ONLY_NOT_DUT_EXECUTION','receipt_sha256':sha(args.output)}))
