"""Read actual fresh GCC -MMD dependency evidence; never invokes a compiler."""
import hashlib,json,pathlib,re,posixpath,importlib.util
P=pathlib.Path
PRODUCER_IMPLEMENTATION_PINS={'build_producer.py': '83af62741237d0c75741ec767dafda29c15ffa8d5ceaf1976ae671d498bdce21', 'one_job_build_only.py': 'd00767427ce2a51e83cd22181cb931342541c235b7f757a2b0b3c0aa5545f951', 'pack_frozen_artifact.py': 'fdea250492dd0ea7493ffec0ecf8b639a9ba5d4026419c5025701066a69a97eb', 'p0_source_evidence.py': '88dd9877813027c1b32a6de2f253109a53884b0d52bce481df39ebc2aa01f32f'}
OBSERVER_HEADER_PINS={'resident_observation.hpp': '88185df7e27f3c0ffa7f3fd857e40f4a31fd72a69c876602519be2e3b0a69721', 'moe_raw_score_observation.hpp': 'fc029f28224bf07452b36702b6c81f5cd196fd7870e81fe980efce13bffaf9df'}
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
def verify_observer_dependencies(dependencies,driver,known):
 # Actual GCC -MMD paths, not guessed include directories or a self-reported flag.
 for name,want in OBSERVER_HEADER_PINS.items():
  matches=[p for p in dependencies if P(p).name==name]
  need(len(matches)==1 and matches[0]==str(P(driver).parent/name),'unique real observer header dependency '+name)
  need(known.get(matches[0])==want,'reviewed observer header identity '+name)
def capture(b,phase,supervisor,completed_phases):
 obj=P(b['obj']).resolve();driver=str(P(b['driver']).resolve());stem=P(driver).stem
 need(b['cpp_build_policy']==b['admission']['cpp_build_policy']==CPP_O1_POLICY and b['cpp_build_overrides']==b['admission']['cpp_build_overrides']==CPP_O1_OVERRIDES,'actual strict O1 admission before capture')
 record=dict(schema='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2',cpp_build_policy=CPP_O1_POLICY,cpp_build_overrides=list(CPP_O1_OVERRIDES),cwd=str(obj),driver=driver,depfile=text_pin(obj/(stem+'.d'),1024**2),object=pin(obj/(stem+'.o')),host_make=text_pin(obj/'VHostBlockTopV4.mk'),host_hierarchy=text_pin(obj/'VHostBlockTopV4_hier.mk'),global_make=text_pin(P(b['verilator_root'])/'include/verilated.mk'),host_link_receipt=supervisor,host_link_argv=phase['argv'],binary=pin(phase['output']),make_closure_pins=b['admission']['make_closure_pins'])
 header=parse_dep(record['depfile']['text'],obj,driver);record['resolved_sparse_header']=pin(header)
 need(b['pins'].get(header)==record['resolved_sparse_header']['sha256'],'resolved header belongs to original build input pins')
 record['dependencies']={p:pin(p) for p in parse_dependencies(record['depfile']['text'],obj,driver)}
 for p,v in record['dependencies'].items():need(b['pins'].get(p)==v['sha256'],'all actual non-system dependencies were prebuild pinned')
 verify_observer_dependencies(record['dependencies'],driver,b['pins'])
 record['compilation_phases']=[dict(phase=r['phase'],argv=r['argv'],output=r['output'],supervisor=r['supervisor'])for r in completed_phases]+[dict(phase=phase['name'],argv=phase['argv'],output=record['binary'],supervisor=supervisor)]
 need(len(record['compilation_phases'])==5,'actual complete five-phase compilation capture')
 for r in record['compilation_phases']:strict_native(r['supervisor'])
 return record

def builder_tool_pin(tool,name):
 """Inventory already stored builder-resolved paths. Do not resolve on executor."""
 value=tool['compile_tools'][name]
 need(type(value)is str and value.startswith('/')and not value.startswith('//')and posixpath.normpath(value)==value and str(pathlib.PurePosixPath(value))==value and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',value),'canonical original builder tool path')
 need(value in tool['pins'],'original builder tool pin required')
 return value

# Builder e015 captured these bytes with the original collector. This executor
# verifier is a separately reviewed adapter, NOT the producer's collection code.
PRODUCER_DEPENDENCY_CAPTURE_SHA='80186b8c5727eeb9054b9e5b284fb27ba6baa7388f491d4ba996409086daa5f4'
COMPILE_RECIPE_TOKENS=('$(OBJCACHE)','$(CXX)','$(CXXFLAGS)','$(CPPFLAGS)','$(OPT_FAST)','-c','-o','$@','$<')

def verify_driver_compile_recipe(host,stem,driver):
 """One exact generated target and recipe; ASCII horizontal whitespace only.
 Does not evaluate Make or shell. Preserves actual text/hash elsewhere. Only the
 observed separator multiplicity is insignificant; every command token remains.
 """
 need(isinstance(host,str)and '\r'not in host,'LF-only actual Make text')
 lines=host.split('\n')
 target=re.compile(re.escape(stem+'.o:')+r'[ \t]+'+re.escape(driver)+r'[ \t]*')
 positions=[i for i,line in enumerate(lines)if target.fullmatch(line)]
 need(len(positions)==1,'unique exact actual driver object target')
 # Reject second alternative/rule for the same target, not only exact matches.
 need(sum(bool(re.match(re.escape(stem+'.o')+r'[ \t]*:',line))for line in lines)==1,'no alternate driver target')
 i=positions[0];need(i+1<len(lines),'actual compile recipe required')
 line=lines[i+1];need(line.startswith('\t')and all(ord(c)<128 for c in line),'original tab-prefixed ASCII recipe')
 tokens=tuple(re.split(r'[ \t]+',line.strip(' \t')))
 need(tokens==COMPILE_RECIPE_TOKENS,'exact actual compile command tokens; no extra shell syntax')
 for following in lines[i+2:]:
  if not following.strip(' \t')or following.lstrip(' \t').startswith('#'):continue
  need(not following.startswith('\t'),'no second driver compile recipe')
  break
 return dict(status='EXACT_GENERATED_DRIVER_RECIPE_ASCII_HORIZONTAL_WHITESPACE_ONLY',tokens=list(tokens))

O1_PRODUCER_IMPLEMENTATION_PINS={'build_producer.py': '2af6a461efc0009bcd0727bd21e98a47a0f7c7ce1a488f5adad0a3b043500667', 'conditional_admission.py': '5f3aaed6267b599baa468c5b2bae7f4bb1946c81cbeab67b926822cf09803513', 'one_job_build_only.py': 'ef5977abd0c5721985c4f3a0125321c04fdcb5fc2292542474c3ebf577e407d6', 'pack_frozen_artifact.py': '5af02d7c4fc153cb3b2b580b227c6f4251c046678e31374ead996ec4b6981944', 'p0_source_evidence.py': '88dd9877813027c1b32a6de2f253109a53884b0d52bce481df39ebc2aa01f32f'}
O1_PRODUCER_DEPENDENCY_CAPTURE_SHA='0b63202e401b1477087a246d5ea233bfd4dcd36ccd80e0c0a03ee323c030a60f'
def o1_collector_sha():return O1_PRODUCER_DEPENDENCY_CAPTURE_SHA

CPP_O0_POLICY='CPP_O0_LEGACY_V1'
CPP_O1_POLICY='CPP_O1_STRICT_V1'
CPP_O0_OVERRIDES=['OPT_FAST=-O0','OPT_SLOW=-O0','OPT_GLOBAL=-O0','CXXFLAGS=-O0']
CPP_O1_OVERRIDES=['OPT_FAST=-O1','OPT_SLOW=-O1','OPT_GLOBAL=-O1','CXXFLAGS=-O1 -fno-fast-math -ffp-contract=off']
CHILDREN=('bf16_context_lane_cluster16_rev8b_b_candidate_d','qwen2_matrix_command_endpoint_0','TransposedDenseDownOwner')

def strict_native(receipt):
 need(type(receipt['native_exit'])is int and receipt['native_exit']==0 and receipt['errors']==[],'actual native zero no compiler errors')
 need((receipt.get('cleanup_proof')or{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP'and(receipt.get('log_capture')or{}).get('pipe_eof_observed')is True and(receipt.get('log_capture')or{}).get('gzip_finalized')is True,'actual compiler cleanup/EOF/gzip complete')

CANDIDATE_IMPLEMENTATION_PINS = {'candidates/ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py': '0b63202e401b1477087a246d5ea233bfd4dcd36ccd80e0c0a03ee323c030a60f', 'candidates/model_candidate_build_20261101/candidate_binary_producer.py': 'd0418ba1fde333633cc0642c118cbf07fccb598f3d966b7977df5f9947e38d53', 'candidates/model_candidate_build_20261101/candidate_build_producer.py': '0cae3214256459cb2259d85402a78aec81bd064465834b8fe01d0893f8f0d495', 'candidates/model_candidate_build_20261101/candidate_conditional_admission.py': 'd8c64a3eb04c342fbd0327f2a4519b7c99cbcd58f22235d0d7f33de8509e338c', 'candidates/model_candidate_build_20261101/candidate_generation_gate.py': '3dfe4bb10f1e8daed36fd5991090e465d34d9fc96463c06dee4a9a15e9cc37d5', 'candidates/model_candidate_build_20261101/model_source_evidence.py': '2798ac6a61b5f5424f968ff672fbc40bad95b9c1330125bdbbb4d93f04f83974', 'candidates/model_candidate_build_20261101/one_job_model_candidate.py': 'ae5dd0847ee4dd9846f3376d624211024d40239296b4435efa99b7d6fcae1460', 'candidates/model_candidate_build_20261101/pack_model_candidate.py': 'bb0c0a5b43690d16c8c2d1ad76351814aca935d0224128dbd26e24ee35abe774'} # Independently source-reviewed candidate implementations; no execution authority.
CANDIDATE_REQUIRED_IMPLEMENTATIONS = {
 'candidates/model_candidate_build_20261101/candidate_build_producer.py',
 'candidates/model_candidate_build_20261101/candidate_conditional_admission.py',
 'candidates/model_candidate_build_20261101/candidate_binary_producer.py',
 'candidates/model_candidate_build_20261101/one_job_model_candidate.py',
 'candidates/model_candidate_build_20261101/pack_model_candidate.py',
 'candidates/model_candidate_build_20261101/candidate_generation_gate.py',
 'candidates/model_candidate_build_20261101/model_source_evidence.py',
 'candidates/ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py',
}
COLLECTOR_PATH='candidates/ci_frontend_pipeline_r2_20261029/driver_dependency_proof.py'
def compilation_policy(r,m,build_receipt):
 need(set(CANDIDATE_IMPLEMENTATION_PINS)==CANDIDATE_REQUIRED_IMPLEMENTATIONS,'candidate implementation contract not frozen')
 need(all(type(h)is str and re.fullmatch('[0-9a-f]{64}',h)for h in CANDIDATE_IMPLEMENTATION_PINS.values()),'candidate implementation SHA')
 need(CANDIDATE_IMPLEMENTATION_PINS[COLLECTOR_PATH]==O1_PRODUCER_DEPENDENCY_CAPTURE_SHA,'original capture bytes unchanged')
 need(r['schema']=='ACTUAL_FRESH_DRIVER_DEPENDENCY_V2','candidate actual V2 GCC capture')
 need(all(h.get('cpp_build_policy')==CPP_O1_POLICY and h.get('cpp_build_overrides')==CPP_O1_OVERRIDES for h in (r,m,build_receipt)),'candidate strict O1 only')
 need(build_receipt.get('schema')=='MODEL_CANDIDATE_BUILD_RECEIPT_V1'and build_receipt.get('status')=='UNREVIEWED_MODEL_BUILD','explicit unreviewed candidate build')
 return CPP_O1_POLICY,list(CPP_O1_OVERRIDES),dict(CANDIDATE_IMPLEMENTATION_PINS)

def expected_phase_argv(cwd,tools,overrides,libs):
 flags=['-j1','VM_HIER_VERILATION_INCLUDED=1',*overrides,'CXX='+tools['cxx'],'LINK='+tools['cxx'],'AR='+tools['ar'],'RANLIB='+tools['ranlib'],'PERL='+tools['perl'],'PYTHON3='+tools['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=']
 result={}
 for name in CHILDREN:
  child=str(P(cwd)/('V'+name));result['archive_'+name]=[tools['make'],'-C',child,'-f','V'+name+'.mk',*flags,'VM_HIER_LIBS=','lib'+name+'.a']
 for phase,target in [('host_archive','VHostBlockTopV4__ALL.a'),('host_link','VHostBlockTopV4')]:
  result[phase]=[tools['make'],'-C',cwd,'-f','VHostBlockTopV4.mk',*flags,'VM_HIER_LIBS='+' '.join(libs),target]
 return result

def verify_compilation_policy(r,m,build_receipt,tool,producer_repo=None):
 """All-profile build policy proof. No compiler/ELF execution or P0 waiver.
 Missing fields mean historical O0 only with its original fixed producer pins;
 V2 binds all five actual supervised compiler phases to the exact reviewed O1.
 """
 policy,overrides,implementations=compilation_policy(r,m,build_receipt)
 suffix='/candidates/model_candidate_build_20261101/candidate_build_producer.py'
 roots=[p[:-len(suffix)]for p in m['generation_input_pins']if p.endswith(suffix)]
 need(len(roots)==1,'unique original reviewed build producer root')
 repo=roots[0];need(producer_repo is None or str(producer_repo)==repo,'same original producer root')
 need(repo.startswith('/')and posixpath.normpath(repo)==repo and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',repo),'canonical producer source root')
 for name,want in implementations.items():
  expected=str(P(repo)/name)
  matches=[path for path in m['generation_input_pins']if path.endswith('/'+name)]
  need(matches==[expected]and m['generation_input_pins'][expected]==want,'policy-specific reviewed producer collection code '+name)
 need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','actual compiler inventory schema')
 tools=tool['compile_tools']
 for name in ('make','cxx','ar','ranlib','perl','python'):need(builder_tool_pin(tool,name)==tools[name],'exact original tool identity '+name)
 cwd=r['cwd'];need(type(cwd)is str and cwd.startswith('/')and posixpath.normpath(cwd)==cwd and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',cwd),'canonical build cwd')
 hostmake=check_text(r['host_make']);globalmake=check_text(r['global_make'])
 need(r['global_make']['sha256']==GLOBAL_MK_SHA and m['generation_input_pins'].get(r['global_make']['path'])==GLOBAL_MK_SHA,'exact original global compiler recipes unchanged')
 hostpath=r['host_make']['path'];need(hostpath==str(P(cwd)/'VHostBlockTopV4.mk')and m['derived_generated_pins'].get(hostpath)==r['host_make']['sha256']==r['make_closure_pins'].get(hostpath),'actual admitted driver Make input')
 verify_driver_compile_recipe(hostmake,P(r['driver']).stem,r['driver'])
 hierarchy=check_text(r['host_hierarchy']);hp=r['host_hierarchy']['path']
 need(hp==str(P(cwd)/'VHostBlockTopV4_hier.mk')and m['derived_generated_pins'].get(hp)==r['host_hierarchy']['sha256']==r['make_closure_pins'].get(hp),'actual policy hierarchy source')
 flat=re.sub(r'\\\n',' ',hierarchy);assign=re.findall(r'^VM_HIER_LIBS\s*:=\s*(.*)$',flat,re.M);need(len(assign)==1,'unique actual hierarchy list');libs=assign[0].split()
 need(len(libs)==3 and set(libs)=={'V'+name+'/lib'+name+'.a'for name in CHILDREN},'same actual three-child hardware hierarchy')
 expected=expected_phase_argv(cwd,tools,overrides,libs)
 host=r['host_link_receipt'];strict_native(host)
 need(r['host_link_argv']==host['argv']==expected['host_link'],'exact host compile/link policy/tool argv')
 need(m['source_commit']==build_receipt['source_commit'],'same producer source commit')
 summaries=build_receipt['phases'];need(type(summaries)is list and [x['phase']for x in summaries]==list(expected),'exact five original build phases')
 for row in summaries:need(type(row['native_exit'])is int and row['native_exit']==0,'all five native build phases complete')
 need(summaries[-1]['supervisor_receipt_sha256']==digest(json.dumps(host,sort_keys=True,separators=(',',':')).encode()),'actual retained host receipt bound to build summary')
 need(r['binary']['sha256']==build_receipt['binary_sha256']==summaries[-1]['output_sha256'],'actual linked binary identity')
 if policy==CPP_O1_POLICY:
  actual=r['compilation_phases'];need(type(actual)is list and len(actual)==5,'all O1 translation-unit phases retained')
  for record,summary,(name,argv)in zip(actual,summaries,expected.items()):
   need(set(record)=={'phase','argv','output','supervisor'}and record['phase']==name==summary['phase'],'actual compiler phase record')
   receipt=record['supervisor'];strict_native(receipt)
   need(record['argv']==receipt['argv']==summary['argv']==argv,'exact O1 policy on every child/global/host/driver TU; no extra flags')
   need(digest(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode())==summary['supervisor_receipt_sha256'],'actual each compiler receipt bound to frozen build')
   output=record['output'];need(set(output)=={'path','bytes','sha256'}and type(output['bytes'])is int and output['bytes']>0 and output['sha256']==summary['output_sha256'],'actual archive/output identity')
   need(output['path']==str(P(argv[2])/argv[-1]),'actual exact target product')
  need(actual[-1]['supervisor']==host and actual[-1]['output']==r['binary'],'same real host link product')
 return dict(policy=policy,make_overrides=overrides,producer_source_commit=m['source_commit'],collector_sha256=implementations[COLLECTOR_PATH],actual_compilation_phases=5 if policy==CPP_O1_POLICY else None,scope='COMPILATION_POLICY_ONLY_NOT_NUMERICAL')

def verify(r,m,policy,common,build_receipt,producer_repo):
 selected_policy,selected_overrides,implementations=compilation_policy(r,m,build_receipt)
 for name,want in implementations.items():
  expected=str(P(producer_repo)/name)
  matches=[path for path in m['generation_input_pins']if path.endswith('/'+name)]
  need(matches==[expected]and m['generation_input_pins'][expected]==want,'actual reviewed producer collection code '+name)
 driver=r['driver'];cwd=r['cwd'];stem=P(driver).stem
 for path in (driver,cwd):need(P(path).is_absolute() and posixpath.normpath(path)==path and re.fullmatch(r'/[A-Za-z0-9_./+\-]+',path)is not None,'canonical original producer driver/cwd')
 need(P(cwd).is_absolute() and r['depfile']['path']==str(P(cwd)/(stem+'.d')) and r['object']['path']==str(P(cwd)/(stem+'.o')),'actual object/depfile location')
 text=check_text(r['depfile'],1024**2);selected=parse_dep(text,cwd,driver);header=r['resolved_sparse_header']
 dependencies=parse_dependencies(text,cwd,driver);need(set(r['dependencies'])==set(dependencies),'complete actual non-system dependency set')
 known={**m['generation_input_pins'],**m['derived_generated_pins']}
 verify_observer_dependencies(dependencies,driver,known)
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
 verify_driver_compile_recipe(host,stem,driver)
 receipt=r['host_link_receipt'];need(receipt['native_exit']==0 and receipt['errors']==[] and receipt['cleanup_proof']['status']=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','actual host link completion')
 argv=receipt['argv'];need(argv==r['host_link_argv'] and argv[1:5]==['-C',cwd,'-f','VHostBlockTopV4.mk'] and argv[-1]=='VHostBlockTopV4','actual host link recipe identity')
 tool_path=P(common['build_receipt']['path']).parent/'tool_manifest.json';need(sha(tool_path)==build_receipt['tool_manifest_sha256'],'actual frozen compiler/tool manifest')
 tool=json.loads(tool_path.read_text());need(tool['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1','actual compiler tool schema');tools=tool['compile_tools']
 need(argv[0]==tools['make'] and builder_tool_pin(tool,'make')==tools['make']and builder_tool_pin(tool,'cxx')==tools['cxx'],'actual make/compiler inventory role')
 hierarchy=check_text(r['host_hierarchy']);hp=r['host_hierarchy']['path']
 need(hp==str(P(cwd)/'VHostBlockTopV4_hier.mk') and m['derived_generated_pins'].get(hp)==r['host_hierarchy']['sha256']==r['make_closure_pins'].get(hp),'actual admitted hierarchy pin')
 flat=re.sub(r'\\\n',' ',hierarchy);assign=re.findall(r'^VM_HIER_LIBS\s*:=\s*(.*)$',flat,re.M);need(len(assign)==1,'actual unique hierarchy list');libs=assign[0].split()
 children=['bf16_context_lane_cluster16_rev8b_b_candidate_d','qwen2_matrix_command_endpoint_0','TransposedDenseDownOwner']
 need(len(libs)==3 and set(libs)=={'V'+n+'/lib'+n+'.a'for n in children},'actual three-child hierarchy')
 flags=['-j1','VM_HIER_VERILATION_INCLUDED=1',*selected_overrides,'CXX='+tools['cxx'],'LINK='+tools['cxx'],'AR='+tools['ar'],'RANLIB='+tools['ranlib'],'PERL='+tools['perl'],'PYTHON3='+tools['python'],'OBJCACHE=','OPT=','USER_CPPFLAGS=','USER_LDLIBS=','USER_LDFLAGS=']
 expected=[tools['make'],'-C',cwd,'-f','VHostBlockTopV4.mk',*flags,'VM_HIER_LIBS='+' '.join(libs),'VHostBlockTopV4']
 need(argv==expected,'exact actual host-link make/tool/override/hierarchy argv')
 for name in ('make','cxx','ar','ranlib','perl','python'):need(builder_tool_pin(tool,name)==tools[name],'tool identity missing '+name)
 rows=[x for x in build_receipt['phases']if x['phase']=='host_link'];need(len(rows)==1 and rows[0]['native_exit']==0 and rows[0]['output_sha256']==common['binary']['sha256'],'frozen binary link phase')
 need(rows[0]['supervisor_receipt_sha256']==digest(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()),'actual build receipt binds retained host link receipt')
 verify_compilation_policy(r,m,build_receipt,tool,producer_repo)
 return selected

HOST_PORTS_SHA='289f230ec8fc85e7aee0396ab34424f505855074a762707e874fbf8a2f45ca08'
SPARSE_HEADER={'bytes':1979,'sha256':'63206761274600c98352aea72281cee305d33a96e406a74bc51f665484845368'}
def header_ports(s):
 out={}
 for m in re.finditer(r'VL_(IN|OUT)(8|16|64|W)?\(&?(\w+),(\d+),(\d+)(?:,(\d+))?\);',s):
  direction,kind,name,hi,lo,words=m.groups();w=int(hi)-int(lo)+1
  need(name not in out and int(lo)==0,'duplicate/nonzero-lsb port')
  need((kind=='8' and w<=8) or(kind=='16' and 8<w<=16) or(kind is None and 16<w<=32) or(kind=='64' and 32<w<=64) or(kind=='W' and w>64 and int(words)==(w+31)//32),'port storage mismatch')
  out[name]=['input' if direction=='IN' else 'output',w]
 need(len(re.findall(r'\bVL_(?:IN|OUT)\w*\(',s))==len(out),'unsupported header port')
 return out

def verify_candidate_compilation(manifest,source,receipt,payloadroot):
 """Pure complete candidate compilation proof. No runtime or review authority.
 Reuses original Make/.d/argv/link algorithms; candidate implementation pins
 are fixed in this verifier, never taken as accepted values from the artifact.
 """
 pack_path=P(__file__).resolve().with_name('pack_model_candidate.py')
 need(set(CANDIDATE_IMPLEMENTATION_PINS)==CANDIDATE_REQUIRED_IMPLEMENTATIONS and sha(pack_path)==CANDIDATE_IMPLEMENTATION_PINS.get('candidates/model_candidate_build_20261101/pack_model_candidate.py'),'candidate actual pack implementation before import')
 spec=importlib.util.spec_from_file_location('_candidate_compilation_pack_api',pack_path);pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
 need(P(pack.__file__).resolve()==pack_path,'exact explicit pack import')
 validate_export=pack.validate_export;STAGES=pack.STAGES;json_file=pack.json_file
 root=P(payloadroot).resolve(strict=True);validate_export(root)
 need(manifest==json_file(root/'frozen_artifact.json',65536) and source==json_file(root/'source_manifest.json',16<<20) and receipt==json_file(root/'build_receipt.json',65536),'arguments equal actual seven-file bytes')
 e=source.get('model_candidate_build_evidence');need(type(e)is dict and set(e)=={'schema','driver_dependency','actual_stage_receipts','fixed_source_overlay','actual_host_header'}and e['schema']=='MODEL_CANDIDATE_ACTUAL_BUILD_EVIDENCE_V1','complete candidate actual build evidence')
 need(set(e['actual_stage_receipts'])==set(STAGES),'exact twenty retained receipts')
 for n,s in zip(STAGES,receipt['stages']):
  text=e['actual_stage_receipts'][n];r=json.loads(check_text(text));strict_native(r)
  need(s['name']==n and s['native_exit']==0 and s['receipt_sha256']==text['sha256'],'actual stage order and raw receipt pin')
 dep=e['driver_dependency']
 for phase in dep.get('compilation_phases',[]):
  need(phase.get('phase')in STAGES[-5:]and phase.get('supervisor')==json.loads(check_text(e['actual_stage_receipts'][phase['phase']])),'same retained compiler and20stage receipt')
 common=dict(manifest['common']);common['build_receipt']=dict(common['build_receipt'],path=str(root/'build_receipt.json'))
 suffix='/candidates/model_candidate_build_20261101/candidate_build_producer.py'
 roots=[p[:-len(suffix)]for p in source['generation_input_pins']if p.endswith(suffix)];need(len(roots)==1,'actual candidate builder source root')
 producer_repo=roots[0]
 selected=verify(dep,source,{'source_pins':{'sparse_memory':SPARSE_HEADER}},common,receipt,producer_repo)
 tool=json_file(root/'tool_manifest.json',32<<20);result=verify_compilation_policy(dep,source,receipt,tool,producer_repo)
 h=e['actual_host_header'];header=check_text(h);need(P(h['path']).name=='VHostBlockTopV4.h'and dep['dependencies'].get(h['path'])=={k:h[k]for k in ('path','bytes','sha256')},'actual GCC compiled header text pin')
 contract_path=P(__file__).resolve().parent.parent/'ci_frontend_pipeline_r2_20261029/OBSERVER_HOST_PORTS_122.json'
 need(sha(contract_path)==HOST_PORTS_SHA,'unchanged explicit public ABI contract')
 expected=json.loads(contract_path.read_text());need(len(expected)==122 and header_ports(header)==expected,'actual complete122 header ABI')
 return dict(result,status='VERIFIED_MODEL_CANDIDATE_COMPILATION_NOT_NUMERICAL_ADMISSION',resolved_sparse_header=selected,actual_stage_count=20,actual_header_ports=122,numerical_pass=False,final_rtl_executed=False,external_review_required=True)
