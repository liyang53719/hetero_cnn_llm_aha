"""One bounded frontend qualification; never binary admission or numerical PASS.
New observed SV identity remains UNREVIEWED. Only one real driver TU is compiled.
"""
import argparse,hashlib,importlib.util,json,pathlib,re,sys
from build_producer import need,sha,pin,check_pins,TOP,CHILDREN,O0,validate_identity,DRIVER_SHA
from conditional_admission import overall,classes,hierarchy,header_ports
from driver_dependency_proof import parse_dependencies,verify_observer_dependencies,text_pin,GLOBAL_MK_SHA
D=pathlib.Path(__file__).resolve().parent
SCANNER_SHA='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
def write_new(path,data,cap=2*1024**2):
 raw=json.dumps(data,sort_keys=True,indent=2)+'\n';need(len(raw.encode())<=cap,'bounded metadata')
 with pathlib.Path(path).open('x')as f:f.write(raw)
def bounded(value,cap,label):
 need(len(json.dumps(value,sort_keys=True,indent=2).encode())<=cap,'metadata section cap '+label)
 return value
def observe_sv(sv,materialization,output):
 sv=pathlib.Path(sv);m=pathlib.Path(materialization)
 need(sv.is_file() and not sv.is_symlink() and 0<sv.stat().st_size<=512*1024**2,'bounded real emitted SV')
 need(sha(m/'sv_comment_only_identity.py')==SCANNER_SHA,'reviewed scanner identity')
 need(sha(D/'sv_inventory_single_pass.py')=='685b15b4f9bee8d23ac25ffc7d26aa718d55621e5fe1b9b2f3519669f24768d4','reviewed single-pass inventory identity')
 sys.path.insert(0,str(m));import sv_comment_only_identity as scanner
 from sv_inventory_single_pass import inventory
 observed=inventory(sv,scanner)
 r=dict(schema='OBSERVED_FRONTEND_SV_V1',status='OBSERVED_UNREVIEWED_NOT_ACCEPTED',scanner_sha256=SCANNER_SHA,numerical_pass=False,**observed)
 write_new(output,r,512*1024)
 return r

def completed(r):
 need(r.get('native_exit')==0 and not r.get('errors') and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','stage incomplete')
 need(r.get('log_capture',{}).get('pipe_eof_observed') is True and r.get('log_capture',{}).get('gzip_finalized') is True,'stage logs not finalized')
def no_compiled(obj,allowed=()):
 products={str(p.relative_to(obj)) for p in obj.rglob('*') if p.is_file() and (p.suffix in ('.o','.a','.gch') or p.name==TOP)}
 need(products==set(allowed),'unexpected compiled product/archive/binary')
def qualify_frontend(b,obj,host,frontend_receipt,out,stage,deadline):
 deadline();validate_identity(b['artifact_identity'])
 need(b['artifact_identity']['source_commit']==b['repo_sha'],'source/artifact identity mismatch')
 obj=pathlib.Path(obj).resolve();host=pathlib.Path(host).resolve();out=pathlib.Path(out).resolve();root=pathlib.Path(b['verilator_root']).resolve()
 check_pins(b['pins']);check_pins(b['verified_gate_pins']);check_pins(b['compile_tool_pins']);no_compiled(obj)
 for p in (obj,host,b['driver'],b['driver_include'],root):need(re.fullmatch(r'[/A-Za-z0-9_.+\-]+',str(p)) is not None,'make path metacharacter')
 completed(json.loads(pathlib.Path(frontend_receipt).read_text()))
 need(str(pathlib.Path(frontend_receipt).resolve())in b['verified_gate_pins'] and str(host)in b['verified_gate_pins'],'actual frontend binding')
 ports=header_ports((obj/(TOP+'.h')).read_text());expected=json.loads((D/'OBSERVER_HOST_PORTS_122.json').read_text())
 need(len(ports)==122 and ports==expected,'actual complete122 ABI differs from independently accepted LOW contract')
 tools=b['compile_tools'];inventory=json.loads(pathlib.Path(b['compile_tool_manifest']).read_text())
 need(inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and inventory['compile_tools']==tools and inventory['pins']==b['compile_tool_pins'] and inventory['aliases']==b.get('compile_aliases',{}),'compile inventory mismatch')
 need(str(pathlib.Path(b['compile_tool_manifest']).resolve())in b['pins'],'inventory prebound')
 for key in ('make','cxx','ar','ranlib','perl','python'):
  p=pathlib.Path(tools[key]);need(p.is_absolute() and p.is_file() and str(p.resolve())in b['compile_tool_pins'],'pinned compiler role')
 globalmk=root/'include/verilated.mk';need(b['pins'].get(str(globalmk))==GLOBAL_MK_SHA==sha(globalmk),'official GCC -MMD recipe')
 makepins={str(globalmk):sha(globalmk)};maketexts={str(globalmk):text_pin(globalmk)};refs=[]
 for prefix in ['V'+n for n in CHILDREN]+[TOP]:
  cwd=obj if prefix==TOP else obj/prefix
  for name in (prefix+'.mk',prefix+'_classes.mk'):
   p=cwd/name;need(not p.is_symlink(),'make symlink');makepins[str(p)]=sha(p);maketexts[str(p)]=text_pin(p)
  overall((cwd/(prefix+'.mk')).read_text(),prefix,root,cwd,b['driver'],b['driver_include'],obj.parent)
  refs+=classes((cwd/(prefix+'_classes.mk')).read_text(),prefix,cwd,root)
 h=obj/(TOP+'_hier.mk');hierarchy(h.read_text());makepins[str(h)]=sha(h);maketexts[str(h)]=text_pin(h)
 admission=out/'frontend_only_admission';admission.mkdir()
 from native_dependency_guard import admit_native_dependencies
 prefixes={TOP:obj,**{'V'+n:obj/('V'+n)for n in CHILDREN}}
 derived,deppins,deprows=admit_native_dependencies(obj,prefixes,{**b['pins'],**b['verified_gate_pins'],**b['compile_tool_pins']},admission)
 makepins.update(deppins)
 for r in refs:need(r in derived or r in b['pins'],'unbound class source')
 for inc in re.findall(r'^include\s+\$\(VERILATOR_ROOT\)/([^\s]+)',globalmk.read_text(),re.M):
  p=root/inc;need(str(p)in b['pins'],'tool make include bound');makepins[str(p)]=sha(p);maketexts[str(p)]=text_pin(p)
 driver=pathlib.Path(b['driver']).resolve();stem=driver.stem
 need(not (obj/(stem+'.d')).exists(),'fresh driver dependency required')
 known={**b['pins'],**b['verified_gate_pins'],**b['compile_tool_pins'],**derived}
 for p in obj.rglob('*'):
  if p.is_file() and p.suffix in ('.cpp','.h','.sv','.v','.dat'):need(str(p.resolve())in known,'generated input outside admitted closure')
 argv=[tools['make'],'-C',str(obj),'-f',TOP+'.mk','-j1','VM_HIER_VERILATION_INCLUDED=1',*O0,'CXX='+tools['cxx'],'LINK='+tools['cxx'],'AR='+tools['ar'],'RANLIB='+tools['ranlib'],'PERL='+tools['perl'],'PYTHON3='+tools['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=','VM_HIER_LIBS=',stem+'.o']
 env={k:'' for k in ('MAKEFLAGS','MFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS','LDLIBS','OBJCACHE','MAKEFILES','MAKEOVERRIDES','USER_CPPFLAGS','USER_LDLIBS','COMPILER_PATH','LIBRARY_PATH','CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH','LD_PRELOAD','LD_LIBRARY_PATH')};env.update(PATH='/usr/bin:/bin',LC_ALL='C')
 for p,target in b.get('compile_aliases',{}).items():need(str(pathlib.Path(p).resolve(strict=True))==target,'compiler alias drift')
 r=stage('driver_tu_only',argv,seconds=300,rss=3,tree=2_000_000_000,env_override=env,extra_watch_roots=[str(obj)],extra_pins={**known,**makepins})
 completed(r);deadline();check_pins(known);check_pins(makepins)
 for p,target in b.get('compile_aliases',{}).items():need(str(pathlib.Path(p).resolve(strict=True))==target,'compiler alias drift after stage')
 no_compiled(obj,[stem+'.o'])
 dep=text_pin(obj/(stem+'.d'),256*1024);deps=parse_dependencies(dep['text'],obj,str(driver));verify_observer_dependencies(deps,str(driver),known)
 dependencies={p:pin(p)for p in deps}
 for p,v in dependencies.items():need(known.get(p)==v['sha256'],'actual GCC dependency not prebound')
 object_pin=pin(obj/(stem+'.o'))
 with (obj/(stem+'.o')).open('rb')as f:raw=f.read(20)
 need(raw[:6]==b'\x7fELF\x02\x01' and raw[16:18]==b'\x01\x00','actual GCC relocatable object only')
 identity=json.loads((out/'sv_identity/sv-identity.json').read_text());need(identity['raw_sha256']==sha(host) and identity['status']=='OBSERVED_UNREVIEWED_NOT_ACCEPTED','SV measured identity drift')
 serial=json.loads((out/'SERIAL_FRONTEND_RESULT.json').read_text());need(serial['scanner_exited_before_children']is True and [x['prefix']for x in serial['stages']]==['V'+n for n in CHILDREN]+[TOP],'one serial full hardware frontend')
 for x in serial['stages']:completed(x['receipt'])
 result=dict(schema='OBSERVED_FRONTEND_DRIVER_TU_V1',status='OBSERVED_UNREVIEWED_NO_BINARY_OR_NUMERICAL_PASS',artifact_identity=b['artifact_identity'],source_commit=b['repo_sha'],matrix_macs=4096,vector_lanes=32,profiles=list(range(5)),canonical_manifest_sha256=b['canonical_manifest_sha256'],sv=identity,ports=ports,host_header=pin(obj/(TOP+'.h')),make_closure=maketexts,make_closure_pins=makepins,native_dependency_metadata=deprows,driver_dependency=dict(schema='ACTUAL_DRIVER_TU_ONLY_DEPENDENCY_V1',depfile=dep,object=object_pin,dependencies=dependencies,argv=argv,supervisor=dict(native_exit=r['native_exit'],errors=[],cleanup_status=r['cleanup_proof']['status'],pipe_eof_observed=True,gzip_finalized=True)),tool_manifest_sha256=sha(b['compile_tool_manifest']),compiler_identity={k:dict(path=v,sha256=b['compile_tool_pins'][v])for k,v in tools.items()},stage_exits=json.loads((out/'stage_exits.json').read_text()),archive_link_executed=False,numerical_pass=False,sv_accepted=False)
 bounded(result['sv'],512*1024,'sv');bounded(result['make_closure'],512*1024,'make');bounded(result['driver_dependency']['dependencies'],256*1024,'gcc dependencies');bounded(result['driver_dependency']['depfile'],384*1024,'gcc depfile JSON');bounded(result['make_closure_pins'],32*1024,'make pins');bounded(result['ports'],32*1024,'ports');bounded(result['stage_exits'],32*1024,'stage exits');bounded(result['native_dependency_metadata'],32*1024,'native metadata')
 result['cpu_capability_observation']={'avx512f': 'avx512f' in pathlib.Path('/proc/cpuinfo').read_text().split(), 'predicate':'original_P0_runtime_cpuinfo_exact_token', 'runtime_qualified':False}
 deadline();result=project_qualification(result,b['artifact_identity']);write_new(out/'FRONTEND_QUALIFICATION.json',result,EXPORT_CAP);deadline()
 return result
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--observe-sv',required=True);a.add_argument('--materialization',required=True);a.add_argument('--output',required=True);v=a.parse_args();observe_sv(v.observe_sv,v.materialization,v.output)

STAGES=['compile155','helper_compile','original_high','canonical_micro','canonical_full','transform_new_toolchain','emit_host','sv_identity','emit_fma','subset','frontend']+['frontend_native_V'+n for n in CHILDREN]+['frontend_native_'+TOP,'driver_tu_only']
EXPORT_CAP=2*1024**2-65536

def project_qualification(r,artifact_identity):
 """Read-only strict finite metadata validation. Never reclassifies observation."""
 def keys(v,w):need(type(v)is dict and set(v)==set(w.split()),'exact metadata fields')
 def integer(v,cap=2**63):need(type(v)is int and 0<=v<=cap,'bounded integer')
 def digest(v):need(type(v)is str and re.fullmatch('[0-9a-f]{64}',v)is not None,'digest')
 def path(v):need(type(v)is str and len(v)<=4096 and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',v)is not None and str(pathlib.PurePosixPath(v))==v and '..'not in pathlib.PurePosixPath(v).parts,'normalized necessary path')
 def pinrow(v,text=False,cap=2**30):
  keys(v,'path bytes sha256'+(' text' if text else ''));path(v['path']);integer(v['bytes'],cap);digest(v['sha256'])
  if text:
   t=v['text'];need(type(t)is str and '\0'not in t and len(t.encode())==v['bytes'] and hashlib.sha256(t.encode()).hexdigest()==v['sha256'],'exact bounded text pin')
   need(re.search(r'(?i)(github_pat_|gh[pousr]_|bearer\s|authorization|\b(?:password|secret|token)\s*[=:])',t)is None,'unsafe metadata text')
 keys(r,'schema status artifact_identity source_commit matrix_macs vector_lanes profiles canonical_manifest_sha256 sv ports host_header make_closure make_closure_pins native_dependency_metadata driver_dependency tool_manifest_sha256 compiler_identity stage_exits archive_link_executed numerical_pass sv_accepted cpu_capability_observation')
 validate_identity(artifact_identity);need(r['artifact_identity']==artifact_identity and r['source_commit']==artifact_identity['source_commit'],'exact run source launch binding')
 need(r['schema']=='OBSERVED_FRONTEND_DRIVER_TU_V1' and r['status']=='OBSERVED_UNREVIEWED_NO_BINARY_OR_NUMERICAL_PASS','observation-only schema')
 need(r['matrix_macs']==4096 and r['vector_lanes']==32 and r['profiles']==list(range(5)),'fixed shared hardware')
 for k in ('archive_link_executed','numerical_pass','sv_accepted'):need(r[k]is False,'no inherited qualification')
 need(r['canonical_manifest_sha256']=='00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c','reviewed actual canonical')
 digest(r['tool_manifest_sha256']);pinrow(r['host_header'])
 keys(r['compiler_identity'],'cxx ar ranlib perl python make cc1plus as ld collect2')
 for v in r['compiler_identity'].values():keys(v,'path sha256');path(v['path']);digest(v['sha256'])
 sv=r['sv'];keys(sv,'schema status raw_sha256 normalized_sha256 bytes scanner_sha256 counts modules numerical_pass');need(sv['schema']=='OBSERVED_FRONTEND_SV_V1' and sv['status']=='OBSERVED_UNREVIEWED_NOT_ACCEPTED' and sv['numerical_pass']is False and sv['scanner_sha256']==SCANNER_SHA,'SV observation only')
 digest(sv['raw_sha256']);digest(sv['normalized_sha256']);integer(sv['bytes'],512*1024**2)
 need(type(sv['counts'])is dict and set(sv['counts'])<=set('recognized_sourceinfo_comments directory_changed_comments unrecognized_sourceinfo_comments'.split()),'scanner counter names')
 for v in sv['counts'].values():integer(v)
 need(type(sv['modules'])is list and 0<len(sv['modules'])<=2048,'full bounded module list');names=[]
 for m in sv['modules']:
  keys(m,'module bytes raw_sha256 normalized_sha256 sourceinfo_count');need(type(m['module'])is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]{0,127}',m['module'])is not None,'module identifier');names.append(m['module']);integer(m['bytes'],512*1024**2);integer(m['sourceinfo_count']);digest(m['raw_sha256']);digest(m['normalized_sha256'])
 need(len(set(names))==len(names) and sum(m['bytes']for m in sv['modules'])==sv['bytes'],'complete module coverage')
 need(r['ports']==json.loads((D/'OBSERVER_HOST_PORTS_122.json').read_text()) and len(r['ports'])==122,'exact measured ABI')
 need(type(r['make_closure'])is dict and 1<=len(r['make_closure'])<=32 and type(r['make_closure_pins'])is dict and len(r['make_closure_pins'])<=64,'bounded Make closure')
 for p,v in r['make_closure'].items():
  path(p);pinrow(v,True,512*1024);need(v['path']==p and p.endswith('.mk') and r['make_closure_pins'].get(p)==v['sha256'],'bound Make text')
 for p,h in r['make_closure_pins'].items():path(p);digest(h);need(p.endswith(('.mk','.d')),'Make/dependency path suffix')
 need(type(r['native_dependency_metadata'])is list and len(r['native_dependency_metadata'])==5,'exact five native metadata rows')
 expectednative={TOP+'__ver.d',TOP+'__hierVer.d'}|{'V'+n+'/V'+n+'__ver.d'for n in CHILDREN}
 need({v.get('relative_path')for v in r['native_dependency_metadata']}==expectednative,'exact native dependency set')
 for v in r['native_dependency_metadata']:
  keys(v,'relative_path bytes sha256 targets prerequisites');need(type(v['relative_path'])is str and re.fullmatch('[A-Za-z0-9_/.-]+',v['relative_path'])is not None and not v['relative_path'].startswith('/') and '..'not in pathlib.PurePosixPath(v['relative_path']).parts,'native relative path');digest(v['sha256']);integer(v['bytes'],1024**2);integer(v['targets']);integer(v['prerequisites'])
 d=r['driver_dependency'];keys(d,'schema depfile object dependencies argv supervisor');need(d['schema']=='ACTUAL_DRIVER_TU_ONLY_DEPENDENCY_V1','TU only schema');pinrow(d['depfile'],True,256*1024);pinrow(d['object'])
 need(type(d['dependencies'])is dict and 1<=len(d['dependencies'])<=4096,'dependency count')
 for p,v in d['dependencies'].items():path(p);pinrow(v);need(p==v['path'],'dependency identity')
 drivers=[p for p in d['dependencies']if pathlib.Path(p).name=='host_axi_driver_non_dpi.cpp'];need(len(drivers)==1,'one actual driver');driver=drivers[0];need(d['dependencies'][driver]['sha256']==DRIVER_SHA,'actual reviewed driver pin');cwd=str(pathlib.Path(d['object']['path']).parent)
 need(d['object']['path']==cwd+'/host_axi_driver_non_dpi.o' and d['depfile']['path']==cwd+'/host_axi_driver_non_dpi.d','actual GCC locations')
 deps=parse_dependencies(d['depfile']['text'],cwd,driver);need(set(deps)==set(d['dependencies']),'actual GCC complete dependency set');verify_observer_dependencies(deps,driver,{p:v['sha256']for p,v in d['dependencies'].items()})
 a=d['argv'];need(type(a)is list and len(a)==24 and all(type(x)is str and len(x)<=4096 for x in a),'exact bounded driver command')
 need(a[1:11]==['-C',cwd,'-f',TOP+'.mk','-j1','VM_HIER_VERILATION_INCLUDED=1',*O0],'driver exact prefix/options')
 path(a[0]);need(a[0]==r['compiler_identity']['make']['path'],'actual make role')
 for value,key in zip(a[11:17],('CXX','LINK','AR','RANLIB','PERL','PYTHON3')):
  need(value.startswith(key+'='),'compiler role argv');path(value[len(key)+1:])
 need([x.split('=',1)[1]for x in a[11:17]]==[r['compiler_identity'][k]['path']for k in ('cxx','cxx','ar','ranlib','perl','python')],'actual compiler role argv')
 need(a[17:]==['OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=','VM_HIER_LIBS=','host_axi_driver_non_dpi.o'],'single TU exact target/overrides')
 # Generated Make text is explicitly requested metadata, not an arbitrary text slot.
 from conditional_admission import lines
 from build_producer import assignment
 globalrows=[v for p,v in r['make_closure'].items()if pathlib.Path(p).name=='verilated.mk'];need(len(globalrows)==1 and globalrows[0]['sha256']==GLOBAL_MK_SHA,'official pinned global Make text')
 root=pathlib.Path(globalrows[0]['path']).parent.parent;obj=pathlib.Path(cwd);hostpath=str(obj/(TOP+'.mk'));need(hostpath in r['make_closure'],'actual Host Make')
 flags=assignment(r['make_closure'][hostpath]['text'],'VM_USER_CFLAGS');need(len(flags)==2 and flags[0]=='-std=c++17' and flags[1].startswith('-I'),'actual driver include flag');include=flags[1][2:];path(include)
 expectedmake={globalrows[0]['path'],str(obj/(TOP+'_hier.mk'))}
 for prefix in ['V'+n for n in CHILDREN]+[TOP]:
  at=obj if prefix==TOP else obj/prefix
  mk=str(at/(prefix+'.mk'));cl=str(at/(prefix+'_classes.mk'));expectedmake.update((mk,cl));need(mk in r['make_closure'] and cl in r['make_closure'],'complete generated Make set')
  overall(r['make_closure'][mk]['text'],prefix,root,at,driver,include,obj.parent)
  rows=lines(r['make_closure'][cl]['text']);switches={'VM_C11':'1','VM_TIMING':'0','VM_COVERAGE':'0','VM_PARALLEL_BUILDS':'1','VM_TRACE':'0','VM_TRACE_VCD':'0','VM_TRACE_FST':'0'}
  need(len(rows)==13,'exact classes Make grammar')
  for row,(k,v)in zip(rows[:7],switches.items()):need(row==k+' = '+v,'class switch')
  for row,k in zip(rows[7:],('VM_CLASSES_FAST','VM_CLASSES_SLOW','VM_SUPPORT_FAST','VM_SUPPORT_SLOW','VM_GLOBAL_FAST','VM_GLOBAL_SLOW')):
   need(row.startswith(k+' +='),'class variable');names=row[len(k)+3:].split();need(len(names)==len(set(names)) and all(re.fullmatch('[A-Za-z0-9_]+',n)and (n in ('verilated','verilated_dpi','verilated_threads')if k.startswith('VM_GLOBAL')else n.startswith(prefix))for n in names),'bounded generated class names')
 need(set(r['make_closure'])==expectedmake,'no extra Make text slots');hierarchy(r['make_closure'][str(obj/(TOP+'_hier.mk'))]['text'])
 s=d['supervisor'];keys(s,'native_exit errors cleanup_status pipe_eof_observed gzip_finalized');need(s==dict(native_exit=0,errors=[],cleanup_status='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP',pipe_eof_observed=True,gzip_finalized=True),'actual complete TU receipt')
 need(type(r['stage_exits'])is list and [x.get('name')for x in r['stage_exits']]==STAGES,'exact16 stage identities')
 for v in r['stage_exits']:
  keys(v,'name status native_exit rss elapsed');need(v['status']=='PASS_PROCESS_ONLY' and v['native_exit']==0,'actual complete stage');integer(v['rss'],13*1024**3);need(type(v['elapsed'])in(int,float)and 0<=v['elapsed']<=1830,'bounded stage elapsed')
 c=r['cpu_capability_observation'];keys(c,'avx512f predicate runtime_qualified');need(type(c['avx512f'])is bool and c['predicate']=='original_P0_runtime_cpuinfo_exact_token' and c['runtime_qualified']is False,'capability not runtime qualification')
 bounded(r['compiler_identity'],16384,'compiler identity');bounded(r,EXPORT_CAP,'total controlled export')
 return json.loads(json.dumps(r))
