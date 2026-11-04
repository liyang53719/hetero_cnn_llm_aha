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
def clean_env():return {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
def elf_info(path):
 p=P(path);size=p.stat().st_size;need(64<=size<=4*1024**3,'ELF file bound')
 with p.open('rb')as f:
  def read(off,n):
   need(0<=off<=size and 0<=n<=1024**2 and off+n<=size,'ELF bounded offset');f.seek(off);b=f.read(n);need(len(b)==n,'ELF truncated');return b
  h=read(0,64);need(h[:6]==b'\x7fELF\x02\x01' and h[6]==1,'ELF64 little endian version')
  typ,machine,version,entry,phoff,shoff,flags,ehsize,phsize,phnum,*_=struct.unpack('<HHIQQQIHHHHHH',h[16:]);need(typ in (2,3)and machine==62 and version==1 and ehsize==64 and phsize==56 and 0<phnum<=128,'ELF x86_64 program header')
  ph=[struct.unpack('<IIQQQQQQ',read(phoff+i*56,56))for i in range(phnum)]
  interp=[q for q in ph if q[0]==3];need(len(interp)==1 and 1<interp[0][5]<=4096,'one bounded PT_INTERP');text=read(interp[0][2],interp[0][5]);need(text.endswith(b'\0')and text.count(b'\0')==1,'interpreter string');loader=text[:-1].decode('ascii');need(loader in INTERPRETERS,'reviewed system interpreter only')
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
  need(0<len(names)<=32 and len(set(names))==len(names),'needed dependency count')
 return {'interpreter':loader,'needed':names,'machine':'ELF64_LE_X86_64'}
def parse_list(text):
 need(len(text.encode())<=65536,'bounded loader output');resolved={};vdso=0
 for line in text.splitlines():
  line=line.strip()
  if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)',line):vdso+=1;continue
  m=re.fullmatch(r'([A-Za-z0-9_+.-]+) => (/[^\s]+) \(0x[0-9a-f]+\)',line)
  if m:key,path=m.groups()
  else:
   m=re.fullmatch(r'(/[^\s]+) \(0x[0-9a-f]+\)',line);need(m is not None,'unknown/unresolved loader output');path=m[1];key=P(path).name
  need(key not in resolved and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',path),'unique safe resolved library');resolved[key]=path
 need(vdso==1 and 1<=len(resolved)<=64,'complete loader dependency list');return resolved

def _list(loader,binary):
 def caps():
  resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536));resource.setrlimit(resource.RLIMIT_CPU,(15,15));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 with tempfile.TemporaryFile()as out,tempfile.TemporaryFile()as err:
  p=subprocess.Popen([str(loader),'--list',str(binary)],stdout=out,stderr=err,env=clean_env(),preexec_fn=caps)
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
def prepare(binary,binary_sha,tool_manifest,tool_sha,out):
 binary=P(binary).resolve();tool_manifest=P(tool_manifest).resolve();out=P(out);need(not out.exists(),'fresh ABI receipt');need(tool_manifest.stat().st_size<=32*1024**2,'bounded build tool manifest');need(sha(binary)==binary_sha and sha(tool_manifest)==tool_sha,'owning binary/tool manifest pins');tool=json.loads(tool_manifest.read_text());need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','tool manifest schema');pins=tool['pins'];info=elf_info(binary);loader=pin(info['interpreter']);need(pins.get(loader['resolved'])==loader['sha256'],'interpreter not in build tool pins');configs=config_pins();before=pin(binary,4*1024**3)
 text=_list(loader['resolved'],binary);resolved=parse_list(text);need(set(info['needed'])<=set(resolved),'direct dependencies absent from loader result');libraries={}
 for n,path in resolved.items():
  v=pin(path);need(pins.get(v['resolved'])==v['sha256'],'resolved library not bound by build tool inventory');libraries[n]=v
 need(loader['resolved']in {v['resolved']for v in libraries.values()},'interpreter absent from resolved list');need(pin(binary,4*1024**3)==before and pin(info['interpreter'])==loader and sha(tool_manifest)==tool_sha,'ABI probe inputs changed');check_configs(configs)
 receipt=dict(schema='SAME_JOB_ELF_STARTUP_ABI_V1',status='STARTUP_RESOLUTION_MATCHES_BUILD_TOOL_PINS_NOT_DUT_EXECUTION',binary=before,tool_manifest={'path':str(tool_manifest),'sha256':tool_sha},elf=info,loader=loader,libraries=libraries,configs=configs,environment=clean_env(),later_dlopen='NOT_QUALIFIED',loader_output_sha256=hashlib.sha256(text.encode()).hexdigest());raw=json.dumps(receipt,indent=2)+'\n';need(len(raw.encode())<=65536,'bounded ABI receipt');
 with out.open('x')as f:f.write(raw)
 return receipt

def verify(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha):
 receipt=P(receipt);need(receipt.is_file()and not receipt.is_symlink()and receipt.stat().st_size<=65536 and sha(receipt)==receipt_sha,'pinned ABI receipt');r=json.loads(receipt.read_text());need(r['schema']=='SAME_JOB_ELF_STARTUP_ABI_V1'and r['status']=='STARTUP_RESOLUTION_MATCHES_BUILD_TOOL_PINS_NOT_DUT_EXECUTION','ABI receipt scope');need(r['environment']==clean_env(),'clean execution environment contract');need(pin(binary,4*1024**3)==r['binary']and r['binary']['sha256']==binary_sha,'binary ABI identity');need(str(P(tool_manifest).resolve())==r['tool_manifest']['path']and sha(tool_manifest)==tool_sha==r['tool_manifest']['sha256'],'tool ABI identity');pins=json.loads(P(tool_manifest).read_text())['pins']
 need(r.get('later_dlopen')=='NOT_QUALIFIED','startup-only scope')
 need(isinstance(r['libraries'],dict) and 1<=len(r['libraries'])<=64,'bounded library map')
 need(set(r['elf']['needed'])<=set(r['libraries']),'missing direct dependency')
 need(r['loader']==pin(r['elf']['interpreter']),'interpreter mapping mismatch')
 need(r['loader']['resolved']in {v['resolved']for v in r['libraries'].values()},'missing interpreter library')
 for v in [r['loader'],*r['libraries'].values()]:need(pin(v['path'])==v and pins.get(v['resolved'])==v['sha256'],'startup library/alias drift')
 need(elf_info(binary)==r['elf'],'ELF identity drift');check_configs(r['configs']);return {'status':'PASS_STARTUP_ABI_IDENTITY_ONLY','receipt_sha256':receipt_sha,'libraries':len(r['libraries'])}

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--binary',type=P,required=True);ap.add_argument('--binary-sha256',required=True);ap.add_argument('--tool-manifest',type=P,required=True);ap.add_argument('--tool-manifest-sha256',required=True);ap.add_argument('--output',type=P,required=True);ap.add_argument('--execute-reviewed-loader-list',action='store_true');args=ap.parse_args()
 need(args.execute_reviewed_loader_list,'explicit reviewed loader-list admission under strict outer supervisor required')
 prepare(args.binary,args.binary_sha256,args.tool_manifest,args.tool_manifest_sha256,args.output)
 print(json.dumps({'status':'STARTUP_ABI_RECEIPT_ONLY_NOT_DUT_EXECUTION','receipt_sha256':sha(args.output)}))
