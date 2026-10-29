"""Verilator 5.032 exact supported make grammar; source-only until caller executes stages."""
from pathlib import Path
import re,json,os,copy,shlex,hashlib
from build_producer import need,sha,check_pins,CHILDREN,TOP,DRIVER_SHA
D=Path(__file__).parent

def lines(s):
 # Only comments/whitespace/continuations normalized, never evaluate make.
 s=re.sub(r'\\\n',' ',s)
 return [' '.join(x.split()) for l in s.splitlines() if (x:=l.split('#',1)[0].strip())]

def header_ports(s):
 out={}
 for m in re.finditer(r'VL_(IN|OUT)(8|16|64|W)?\(&?(\w+),(\d+),(\d+)(?:,(\d+))?\);',s):
  direction,kind,name,hi,lo,words=m.groups();w=int(hi)-int(lo)+1
  need(name not in out and int(lo)==0,'duplicate/nonzero-lsb port')
  need((kind=='8' and w<=8) or(kind=='16' and 8<w<=16) or(kind is None and 16<w<=32) or(kind=='64' and 32<w<=64) or(kind=='W' and w>64 and int(words)==(w+31)//32),'port storage mismatch')
  out[name]=['input' if direction=='IN' else 'output',w]
 need(len(re.findall(r'\bVL_(?:IN|OUT)\w*\(',s))==len(out),'unsupported header port')
 return out

def overall(s,prefix,root,cwd,driver,driver_include,frontend_cwd):
 """Entire noncomment overall.mk syntax must match official EmitMk template.
 Values are constrained against admitted paths, never expanded by GNU make here.
 """
 a=lines(s);host=prefix==TOP;name=prefix[1:];driver=Path(driver)
 default=TOP if host else 'lib'+name
 base=[f'default: {default}','PERL = perl','PYTHON3 = python3',f'VERILATOR_ROOT = {root}','SYSTEMC_INCLUDE ?=','SYSTEMC_LIBDIR ?=','VM_PROFC = 0','VM_SC = 0','VM_SP_OR_SC = $(VM_SC)','VM_PCLI = 1','VM_SC_TARGET_ARCH = linux',f'VM_PREFIX = {prefix}',f'VM_MODPREFIX = {prefix}']
 need(a[:len(base)]==base,'overall constants/template drift '+prefix);a=a[len(base):]
 def take(key):
  need(a and a[0].startswith(key+' ='),'overall assignment '+key)
  return a.pop(0)[len(key)+2:].split()
 flags=take('VM_USER_CFLAGS');ld=take('VM_USER_LDLIBS');classes=take('VM_USER_CLASSES');dirs=take('VM_USER_DIR')
 approved=['-std=c++17','-I'+str(driver_include)]
 need(flags==approved if host else flags in (['-fPIC'],['-fPIC']+approved),'noncontract CFLAGS')
 need(ld==['-lcrypto'] if host else ld in ([],['-lcrypto']),'noncontract LDLIBS')
 need(classes==[driver.stem] if host else classes==[],'driver classes')
 expected_dirs={os.path.relpath(frontend_cwd,cwd)}
 if host:expected_dirs.add(os.path.relpath(driver.parent,cwd))
 # Verilator filenameRelativePath retains absolute when outside same root.
 actual_dirs={str((Path(cwd)/v).resolve()) for v in dirs}
 need(actual_dirs=={str((Path(cwd)/v).resolve()) for v in expected_dirs} and len(dirs)==len(expected_dirs),'user directories')
 tail=[f'include {prefix}_classes.mk']
 if host:tail += [f'include {prefix}_hier.mk']
 tail+=['include $(VERILATOR_ROOT)/include/verilated.mk']
 if host:
  tail += ['VPATH += $(VM_USER_DIR)',f'{driver.stem}.o: {driver}','$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<',f'{TOP}: $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)','$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@']
 else:tail += [f'lib{name}.a: $(VK_OBJS) $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) {name}.o $(VM_HIER_LIBS)',f'lib{name}: lib{name}.a']
 need(a==tail,'overall recipes/include/targets drift '+prefix)

def classes(s,prefix,cwd,root):
 a=lines(s);switches={'VM_C11':'1','VM_TIMING':'0','VM_COVERAGE':'0','VM_PARALLEL_BUILDS':'1','VM_TRACE':'0','VM_TRACE_VCD':'0','VM_TRACE_FST':'0'}
 for k,v in switches.items():need(a.pop(0)==k+' = '+v,'class switches')
 refs=[]
 for key in ('VM_CLASSES_FAST','VM_CLASSES_SLOW','VM_SUPPORT_FAST','VM_SUPPORT_SLOW','VM_GLOBAL_FAST','VM_GLOBAL_SLOW'):
  need(a and a[0].startswith(key+' +='),'class variable')
  names=a.pop(0)[len(key)+3:].split()
  need(len(names)==len(set(names)),'duplicate class')
  for n in names:
   need(re.fullmatch(r'[A-Za-z0-9_]+',n) is not None,'class injection')
   if key.startswith('VM_GLOBAL'):
    need(n in ('verilated','verilated_dpi','verilated_threads'),'unsupported runtime class')
    p=Path(root)/'include'/(n+'.cpp')
   else:
    need(n.startswith(prefix),'unexpected generated class prefix');p=Path(cwd)/(n+'.cpp')
   need(p.is_file() and not p.is_symlink(),'class source absent');refs.append(str(p.resolve()))
 need(not a,'extra class directives');return refs

def hierarchy(s):
 a=lines(s);need(a[0]=='ifndef VM_HIER_VERILATION_INCLUDED' and a[-1]=='endif','hierarchy complete guard')
 # No directive may terminate/reopen the excluded body; with command-line guard
 # GNU make skips all inner recipes/assignments without evaluating expressions.
 need(not any(re.match(r'^(?:ifn?def|ifeq|ifneq|else|endif)\b',x) for x in a[1:-1]),'nested/escaped hierarchy guard')
 m=re.search(r'^VM_HIER_LIBS\s*:=\s*(.*)$',re.sub(r'\\\n',' ',s),re.M);need(m is not None,'missing libraries')
 libs=m[1].split();want=['V'+n+'/lib'+n+'.a' for n in CHILDREN]
 need(len(libs)==3 and set(libs)==set(want),'hierarchy topology drift');return libs

def admit_build(b,obj,host,frontend_receipt,out):
 """Caller already completed source/canonical/SV/frontend stages in this run.
 Require their actual receipt files/pins, not a manual hash for future outputs.
 """
 obj=Path(obj).resolve();out=Path(out)
 for p in (obj,host,out,b['driver'],b['driver_include'],b['verilator_root']):need(re.fullmatch(r'[/A-Za-z0-9_.+\-]+',str(p)) is not None,'make path metacharacter')
 out.mkdir(exist_ok=False)
 need(sha(b['driver'])==DRIVER_SHA,'driver identity')
 check_pins(b['pins']);check_pins(b['verified_gate_pins'])
 receipt=json.loads(Path(frontend_receipt).read_text())
 need(receipt['native_exit']==0 and not receipt['errors'] and receipt.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','frontend actual completion')
 need(str(Path(frontend_receipt).resolve()) in b['verified_gate_pins'],'unbound frontend completion')
 need(str(Path(host).resolve()) in b['verified_gate_pins'],'unbound emitted source')
 root=Path(b['verilator_root']).resolve();tools=b['compile_tools'];check_pins(b['compile_tool_pins'])
 inventory=json.loads(Path(b['compile_tool_manifest']).read_text())
 need(inventory['schema']=='INSTALLED_GNU_BUILD_TOOLS_V1' and inventory['compile_tools']==tools and inventory['pins']==b['compile_tool_pins'] and inventory['aliases']==b.get('compile_aliases',{}),'compile inventory binding mismatch')
 need(str(Path(b['compile_tool_manifest']).resolve()) in b['pins'],'compile inventory receipt unbound')
 for key in ('make','cxx','ar','ranlib','perl','python'):
  p=Path(tools[key]);need(p.is_absolute() and p.is_file() and str(p.resolve()) in b['compile_tool_pins'],'compiler/tool identity missing '+key)
 globalmk=root/'include/verilated.mk';need(str(globalmk) in b['pins'],'unbound official global make rules')
 need(header_ports((obj/(TOP+'.h')).read_text())==json.loads((D/'HOST_PORTS.json').read_text()),'actual Host85 ABI mismatch')
 refs=[];makepins={str(globalmk):sha(globalmk)}
 for prefix in ['V'+n for n in CHILDREN]+[TOP]:
  cwd=obj if prefix==TOP else obj/prefix
  for name in (prefix+'.mk',prefix+'_classes.mk'):
   p=cwd/name;need(not p.is_symlink(),'make symlink');makepins[str(p)]=sha(p)
  overall((cwd/(prefix+'.mk')).read_text(),prefix,root,cwd,b['driver'],b['driver_include'],obj.parent)
  refs+=classes((cwd/(prefix+'_classes.mk')).read_text(),prefix,cwd,root)
 h=obj/(TOP+'_hier.mk');hierarchy(h.read_text());makepins[str(h)]=sha(h)
 # Generated deps makefiles are official optional include targets: reject any
 # preexisting .d/.o/.a/PCH, so no foreign dep recipe enters first build.
 derived={}
 for p in obj.rglob('*'):
  need(not p.is_symlink(),'generated tree symlink')
  if p.is_file():
   need(p.suffix not in ('.o','.a','.gch','.d'),'previous compiled/dependency product')
   if p.suffix in ('.mk','.cpp','.h','.v','.sv','.dat','.f'):derived[str(p.resolve())]=sha(p)
 for r in refs:
  need(r in derived or r in b['pins'],'unbound class source')
 # version/config rules included by official verilated.mk also pinned baseline.
 for inc in re.findall(r'^include\s+\$\(VERILATOR_ROOT\)/([^\s]+)',globalmk.read_text(),re.M):
  p=root/inc;need(str(p) in b['pins'],'unbound tool make include');makepins[str(p)]=sha(p)
 bb=copy.deepcopy(b);bb.update(schema='FIXED_BINARY_BUILD_BINDING_V1',source_commit=b['repo_sha'],obj=str(obj),sv=str(Path(host).resolve()),make=tools['make'],cxx=tools['cxx'],ar=tools['ar'])
 bb['compile_aliases']=b.get('compile_aliases',{})
 bb['pins']={**b['pins'],**b['verified_gate_pins'],**b['compile_tool_pins'],**derived}
 identity_path=Path(b['sv_identity_receipt']).resolve();serial_path=Path(b['serial_frontend_receipt']).resolve();subset=Path(b['fma_subset']).resolve()
 for p in (identity_path,serial_path,subset):need(str(p) in b['verified_gate_pins'],'unbound actual frontend identity artifact')
 identity=json.loads(identity_path.read_text());normalized='6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5'
 need(identity.get('status')=='PASS_SV_SOURCEINFO_DIRECTORY_IDENTITY_ONLY_NO_NUMERICS' and identity.get('phase')=='complete' and identity.get('expected_normalized_sha256')==normalized and identity.get('actual_normalized_sha256')==normalized and identity.get('raw_sha256')==sha(host),'raw/normalized Top identity drift')
 serial=json.loads(serial_path.read_text());need(serial.get('scanner_exited_before_children') is True,'serial frontend provenance')
 need([r['prefix'] for r in serial['stages']]==['V'+n for n in CHILDREN]+[TOP],'actual serial receipt stages')
 for row in serial['stages']:
  r=row['receipt'];need(r.get('native_exit')==0 and not r.get('errors') and r.get('cleanup_proof',{}).get('status')=='COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP','actual serial stage incomplete')
 native_plan=obj.parent/'SERIAL_NATIVE_PLAN.json';need(sha(native_plan)==serial['plan_manifest_sha256'],'native plan manifest drift')
 rows=json.loads(native_plan.read_text())['stages'];need([r['prefix'] for r in rows]==['V'+n for n in CHILDREN]+[TOP],'native plan stage topology')
 semantics=[]
 for row in rows:
  path=Path(row['args']).resolve();need(path.parent==obj and path.name==row['prefix']+'__hierMkArgs.f' and sha(path)==row['args_sha256'],'native args identity')
  tokens=shlex.split(path.read_text());need('--cc' in tokens and '--build' not in tokens and '--binary' not in tokens,'native frontend-only args')
  need(tokens.count('--prefix')==1 and tokens[tokens.index('--prefix')+1]==row['prefix'],'native prefix')
  options={}
  for key in ('--top-module','--prefix','--lib-create','--hierarchical-child','--threads','--build-jobs','--verilate-jobs','-CFLAGS','-LDFLAGS'):
   options[key]=[tokens[i+1] for i,t in enumerate(tokens[:-1]) if t==key]
  semantics.append(dict(prefix=row['prefix'],args_sha256=sha(path),argv=tokens,semantic_options=options,exe='--exe' in tokens,build=False))
 wrappers={}
 for n in CHILDREN:
  matches=list((obj/('V'+n)).glob('*.sv'));need(len(matches)==1,'matching wrapper count')
  wrappers[str(matches[0].resolve())]=sha(matches[0])
 wrapper_aggregate=hashlib.sha256(json.dumps(wrappers,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 physical_closure=dict(top_raw_sha256=sha(host),top_normalized_sha256=normalized,sv_identity_receipt_sha256=sha(identity_path),fma_subset=dict(path=str(subset),sha256=sha(subset),bytes=subset.stat().st_size),provider_sources={p:b['pins'][p] for p in b['provider_sources']},idma_include_dirs=b['idma_include_dirs'],idma_defines=b['idma_defines'],native_plan_manifest_sha256=sha(native_plan),initial_frontend_argv=b['initial_frontend_argv'],native_plan=semantics,matching_wrapper_pins=wrappers,matching_wrapper_aggregate_sha256=wrapper_aggregate,serial_frontend_receipt_sha256=sha(serial_path))
 bb['pins'][str(native_plan)]=sha(native_plan)
 source_manifest=out/'source_manifest.json'
 source_manifest.write_text(json.dumps(dict(schema='FIXED_COMMON_SOURCE_IDENTITY_V1',source_commit=b['repo_sha'],matrix_macs=4096,vector_lanes=32,sv_sha256=sha(host),driver_sha256=sha(b['driver']),source_pins={p:h for p,h in b['pins'].items() if p.startswith(b['repo']+'/') and Path(p).suffix in ('.scala','.sv','.v','.cpp','.h')},verified_gate_pins=b['verified_gate_pins'],provider_source_pins={p:b['pins'][p] for p in b['provider_sources']},generation_input_pins=b['pins'],derived_generated_pins=derived,fixed_source_overlay=b['fixed_source_overlay'],canonical_manifest_sha256=b['canonical_manifest_sha256'],physical_closure=physical_closure),indent=2)+'\n')
 bb['source_manifest']=str(source_manifest.resolve());bb['tool_manifest']=str(Path(b['compile_tool_manifest']).resolve())
 bb['pins'].update({bb['source_manifest']:sha(source_manifest),bb['tool_manifest']:sha(bb['tool_manifest'])})
 bb['admission']=dict(status='ACTUAL_MAKE_CLOSURE_REVIEWED',method='CONDITIONAL_V5032_EXACT_TEMPLATE',source_commit=b['repo_sha'],make_closure_pins=makepins,no_implicit_frontend=True,uniform_O0_no_fast_math=True,header_85_ports_and_driver_ABI_reviewed=True)
 (out/'derived_admission.json').write_text(json.dumps(bb['admission'],indent=2)+'\n')
 (out/'derived_input_pins.json').write_text(json.dumps(bb['pins'],indent=2)+'\n')
 return bb
