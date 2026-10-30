"""Read actual fresh GCC -MMD dependency evidence; never invokes a compiler."""
import hashlib,json,pathlib,re,posixpath
P=pathlib.Path
PRODUCER_IMPLEMENTATION_PINS={'build_producer.py': '82aef295be117550be5c7c878f6f70b78d6e195c17061bad0ac292593dd80bfe', 'one_job_build_only.py': 'd70c929243fd7e6b5b0ed266b2634e24b1c863715d14a5d34cde3604ebcc1015', 'pack_frozen_artifact.py': '773575951ecf63fca15d5c2082c098a2ca6bd0bc988a3a3df3aaaabba712119c', 'p0_source_evidence.py': '47a126be32385720fd3b3d94e848609f57c24174ea917110bdb1b221d916b800'}
GLOBAL_MK_SHA='74121398e5be12bf03721f1f0f5ce75e7c703635ec7e50920d43f9c4e31fcc0c'
def need(v,s):
 if not v:raise ValueError(s)
def digest(b):return hashlib.sha256(b).hexdigest()
def sha(p):
 with P(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
 p=P(p);need(p.is_absolute() and p.is_file() and not p.is_symlink(),'regular absolute generated evidence');return dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p))
def text_pin(p,cap=2*1024**2):
 v=pin(p);need(v['bytes']<=cap,'bounded retained metadata');raw=P(p).read_bytes();need(b'\0' not in raw,'text-only evidence');return dict(v,text=raw.decode('utf-8'))
def check_text(v,cap=2*1024**2):
 b=v['text'].encode();need(len(b)==v['bytes']<=cap and digest(b)==v['sha256'],'retained original text pin');return v['text']
def parse_dependencies(text,cwd,driver):
 need(0<len(text.encode())<=1024**2 and text.endswith('\n') and re.fullmatch(r'[A-Za-z0-9_./+ \t:\\\n-]+',text)is not None,'bounded ASCII canonical GCC dependency text')
 # Actual producer paths have no whitespace/metacharacters. No make evaluation.
 flat=text.replace('\\\n',' ');need('\\' not in flat,'only GCC backslash LF continuation');lines=[x.strip()for x in flat.splitlines()if x.strip()];need(len(lines)==1 and lines[0].count(':')==1,'one GCC dependency rule; no phony/make directives')
 target,body=lines[0].split(':');need(target.strip()==P(driver).stem+'.o','unique actual driver object target')
 tokens=body.split();need(tokens and len(tokens)==len(set(tokens)) and len(tokens)<=4096,'unique bounded dependencies')
 paths=[]
 for token in tokens:
  need(re.fullmatch(r'[/A-Za-z0-9_.+\-]+',token)is not None,'dependency path not plain')
  p=P(token);need('..' not in p.parts,'dependency parent traversal');p=p if p.is_absolute()else P(cwd)/p;paths.append(posixpath.normpath(str(p)))
 need(len(paths)==len(set(paths)),'unique normalized dependency paths')
 need(paths.count(posixpath.normpath(str(driver)))==1,'actual driver dependency')
 sparse=[p for p in paths if P(p).name=='sparse_write_memory.hpp'];need(len(sparse)==1,'one actually resolved sparse header dependency')
 return paths
def parse_dep(text,cwd,driver):return next(p for p in parse_dependencies(text,cwd,driver) if P(p).name=='sparse_write_memory.hpp')
def capture(b,phase,supervisor):
 obj=P(b['obj']).resolve();driver=str(P(b['driver']).resolve());stem=P(driver).stem
 record=dict(schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V1',cwd=str(obj),driver=driver,depfile=text_pin(obj/(stem+'.d'),1024**2),object=pin(obj/(stem+'.o')),host_make=text_pin(obj/'VHostBlockTopV4.mk'),host_hierarchy=text_pin(obj/'VHostBlockTopV4_hier.mk'),global_make=text_pin(P(b['verilator_root'])/'include/verilated.mk'),host_link_receipt=supervisor,host_link_argv=phase['argv'],binary=pin(phase['output']),make_closure_pins=b['admission']['make_closure_pins'])
 header=parse_dep(record['depfile']['text'],obj,driver);record['resolved_sparse_header']=pin(header)
 need(b['pins'].get(header)==record['resolved_sparse_header']['sha256'],'resolved header belongs to original build input pins')
 record['dependencies']={p:pin(p) for p in parse_dependencies(record['depfile']['text'],obj,driver)}
 for p,v in record['dependencies'].items():need(b['pins'].get(p)==v['sha256'],'all actual non-system dependencies were prebuild pinned')
 return record

def verify(r,m,policy,common,build_receipt,producer_repo):
 need(r['schema']=='ACTUAL_FRESH_DRIVER_DEPENDENCY_V1','actual driver dependency schema')
 for name,want in dict(PRODUCER_IMPLEMENTATION_PINS,**{'driver_dependency_proof.py':sha(__file__)}).items():
  expected=str(P(producer_repo)/'candidates/ci_frontend_pipeline_r2_20261029'/name)
  matches=[path for path in m['generation_input_pins']if path.endswith('/candidates/ci_frontend_pipeline_r2_20261029/'+name)]
  need(matches==[expected] and m['generation_input_pins'][expected]==want,'actual reviewed producer collection code '+name)
 driver=r['driver'];cwd=r['cwd'];stem=P(driver).stem
 for path in (driver,cwd):need(P(path).is_absolute() and posixpath.normpath(path)==path and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',path)is not None,'canonical original producer driver/cwd')
 need(P(cwd).is_absolute() and r['depfile']['path']==str(P(cwd)/(stem+'.d')) and r['object']['path']==str(P(cwd)/(stem+'.o')),'actual object/depfile location')
 text=check_text(r['depfile'],1024**2);selected=parse_dep(text,cwd,driver);header=r['resolved_sparse_header']
 dependencies=parse_dependencies(text,cwd,driver);need(set(r['dependencies'])==set(dependencies),'complete actual non-system dependency set')
 known={**m['generation_input_pins'],**m['derived_generated_pins']}
 for p,v in r['dependencies'].items():need(v['path']==p and v['bytes']>0 and known.get(p)==v['sha256'],'non-system dependency versus original generation/derived pin')
 need(selected==header['path'] and header['bytes']==policy['source_pins']['sparse_memory']['bytes'] and header['sha256']==policy['source_pins']['sparse_memory']['sha256'],'actual selected sparse header pin')
 need(m['generation_input_pins'].get(selected)==header['sha256'],'resolved dependency versus prebuild source pin')
 need(m['generation_input_pins'].get(driver)==common['driver']['sha256'],'actual dependency driver input pin')
 need(r['binary']['sha256']==common['binary']['sha256'] and r['object']['bytes']>0,'actual linked binary/object')
 host=check_text(r['host_make']);globalmk=check_text(r['global_make'])
 normalized=re.sub(r'\\\n',' ',host);lines=[' '.join(line.split('#',1)[0].split())for line in normalized.splitlines()if line.split('#',1)[0].strip()]
 need([x for x in lines if x.startswith('VM_USER_CLASSES ')]==['VM_USER_CLASSES = '+stem],'unique actual driver user class')
 need('VHostBlockTopV4: $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)' in lines and '$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@' in lines,'actual driver object linked into final target')
 need(r['global_make']['sha256']==GLOBAL_MK_SHA and m['generation_input_pins'].get(r['global_make']['path'])==GLOBAL_MK_SHA,'exact official -MMD make source')
 need('-MMD' in globalmk and 'VK_USER_OBJS = $(addsuffix .o, $(VM_USER_CLASSES))' in globalmk,'official dependency emission/user object mapping')
 need(r['host_make']['path']==str(P(cwd)/'VHostBlockTopV4.mk') and r['make_closure_pins'].get(r['host_make']['path'])==r['host_make']['sha256'] and m['derived_generated_pins'].get(r['host_make']['path'])==r['host_make']['sha256'],'actual admitted Host make pin')
 need(stem+'.o: '+driver in host and '$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<' in host,'actual explicit driver compile recipe')
 receipt=r['host_link_receipt'];need(receipt['native_exit']==0 and receipt['errors']==[] and receipt['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','actual host link completion')
 argv=receipt['argv'];need(argv==r['host_link_argv'] and argv[1:5]==['-C',cwd,'-f','VHostBlockTopV4.mk'] and argv[-1]=='VHostBlockTopV4','actual host link recipe identity')
 tool_path=P(common['build_receipt']['path']).parent/'tool_manifest.json';need(sha(tool_path)==build_receipt['tool_manifest_sha256'],'actual frozen compiler/tool manifest')
 tool=json.loads(tool_path.read_text());need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','actual compiler tool schema');tools=tool['compile_tools']
 need(argv[0]==tools['make'] and tool['pins'].get(str(P(tools['make']).resolve())) is not None and tool['pins'].get(str(P(tools['cxx']).resolve())) is not None,'actual make/compiler inventory role')
 hierarchy=check_text(r['host_hierarchy']);hp=r['host_hierarchy']['path']
 need(hp==str(P(cwd)/'VHostBlockTopV4_hier.mk') and m['derived_generated_pins'].get(hp)==r['host_hierarchy']['sha256']==r['make_closure_pins'].get(hp),'actual admitted hierarchy pin')
 flat=re.sub(r'\\\n',' ',hierarchy);assign=re.findall(r'^VM_HIER_LIBS\s*:=\s*(.*)$',flat,re.M);need(len(assign)==1,'actual unique hierarchy list');libs=assign[0].split()
 children=['bf16_context_lane_cluster16_rev8b_b_candidate_d','qwen2_matrix_command_endpoint_0','TransposedDenseDownOwner']
 need(len(libs)==3 and set(libs)=={'V'+n+'/lib'+n+'.a'for n in children},'actual three-child hierarchy')
 flags=['-j1','VM_HIER_VERILATION_INCLUDED=1','OPT_FAST=-O0','OPT_SLOW=-O0','OPT_GLOBAL=-O0','CXXFLAGS=-O0','CXX='+tools['cxx'],'LINK='+tools['cxx'],'AR='+tools['ar'],'RANLIB='+tools['ranlib'],'PERL='+tools['perl'],'PYTHON3='+tools['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=']
 expected=[tools['make'],'-C',cwd,'-f','VHostBlockTopV4.mk',*flags,'VM_HIER_LIBS='+' '.join(libs),'VHostBlockTopV4']
 need(argv==expected,'exact actual host-link make/tool/override/hierarchy argv')
 for name in ('make','cxx','ar','ranlib','perl','python'):need(str(P(tools[name]).resolve())in tool['pins'],'tool identity missing '+name)
 rows=[x for x in build_receipt['phases']if x['phase']=='host_link'];need(len(rows)==1 and rows[0]['native_exit']==0 and rows[0]['output_sha256']==common['binary']['sha256'],'frozen binary link phase')
 need(rows[0]['supervisor_receipt_sha256']==digest(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()),'actual build receipt binds retained host link receipt')
 return selected
