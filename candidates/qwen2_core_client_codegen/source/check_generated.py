"""Bounded source-informed output contract for fixed Verilator5.032 codegen.
No C++/Make evaluation, compilation, native invocation or SV parser. Checks the
complete public port declaration ABI and exact selected Make source/flag graph;
not general C++ semantics, linkage, simulation or initialization equivalence.
"""
import hashlib,json,os,re,stat
from pathlib import Path
PREFIX='VOrderedQkBehaviorCore'
IDENT=r'[A-Za-z_][A-Za-z0-9_]*'
PORT=re.compile(r'VL_(INOUT|IN|OUT)(8|16|64|W)?\(\s*&('+IDENT+r')\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)\s*;')
ASSIGN=re.compile(r'([A-Z][A-Z0-9_]*)\s*(\+=|\?=|=)\s*(.*)')
GROUPS=tuple('VM_'+a+'_'+b for a in ('CLASSES','SUPPORT','GLOBAL') for b in ('FAST','SLOW'))
def need(ok,why):
 if not ok:raise ValueError(why)
def bounded_text(path,limit,lines=50000):
 p=Path(path);before=p.lstat();need(stat.S_ISREG(before.st_mode) and not p.is_symlink() and 0<before.st_size<=limit,'bounded regular content input')
 with p.open('rb') as stream:raw=stream.read(limit+1)
 need(len(raw)==before.st_size<=limit,'bounded stable content read');text=raw.decode('utf8');need('\x00' not in text,'nonbinary source content')
 chunks=text.splitlines();need(len(chunks)<=lines and all(len(x.encode())<=65536 for x in chunks),'bounded source lines')
 after=p.lstat();need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'source content stable during read')
 return text,dict(path=str(p),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def header_contract(text,ports):
 need(ports and len(ports)<=8859,'bounded expected ports');code=[];actual={};access=None;guard=None;guard_defined=False;guard_closed=False;class_seen=False;class_closed=False;depth=0
 api_patterns=((r'explicit '+PREFIX+r'\(VerilatedContext\* contextp,\s*const char\* name = "TOP"\);','context constructor'),(r'void eval\(\) \{ eval_step\(\);\s*\}','eval API'),(r'void eval_step\(\);','eval_step API'),(r'void final\(\);','final API'))
 api_counts={label:0 for pattern,label in api_patterns}
 for raw in text.splitlines():
  # This fixed emitter emits // comments; reject unhandled block-comment syntax.
  line=raw.split('//',1)[0].strip()
  need('/*' not in line and '*/' not in line,'unsupported header block-comment syntax')
  if not line:continue
  if line.startswith('#'):
   if line.startswith('#ifndef '):
    need(guard is None and not class_seen,'single outer generated include guard');guard=line.split()[1];need(guard=='VERILATED_VORDEREDQKBEHAVIORCORE_H_','exact selected header guard')
   elif line.startswith('#define '):need(guard is not None and line=='#define '+guard and not guard_defined,'matching single header guard define');guard_defined=True
   elif line=='#endif':need(guard_defined and not guard_closed and class_closed and depth==0,'matching outer guard after closed main class');guard_closed=True
   elif line.startswith('#include '):need(not class_seen and not guard_closed and line=='#include "verilated.h"','fixed public runtime include')
   else:raise ValueError('unsupported conditional/macro in public header')
   continue
  need(not guard_closed and not class_closed,'no code after main class/header guard')
  was_depth=depth
  if re.fullmatch(r'class alignas\(VL_CACHE_LINE_BYTES\) '+PREFIX+r' VL_NOT_FINAL : public VerilatedModel \{',line):
   need(not class_seen and guard_defined,'one selected public model class');class_seen=True;access='private'
  elif not class_seen:need('{' not in line and '}' not in line,'no unparsed scope before selected main class')
  if line in ('public:','private:','protected:'):
   need(class_seen and depth==1,'class-level access specifier');access=line[:-1]
  if re.search(r'\bVL_(?:IN|OUT)',line):
   m=PORT.fullmatch(line);need(m is not None and class_seen and depth==1 and access=='public','fully parsed public port reference declaration')
   direction,suffix,name,msb,lsb,words=m.groups();need(direction!='INOUT' and name not in actual,'no bidirectional/duplicate port');width=int(msb)-int(lsb)+1
   want='8' if width<=8 else '16' if width<=16 else '' if width<=32 else '64' if width<=64 else 'W'
   need(width>0 and int(lsb)==0 and (suffix or '')==want,'exact unsigned scalar storage macro and packed bounds')
   need((words is None and want!='W') or (want=='W' and words is not None and int(words)==(width+31)//32),'exact wide-word count')
   actual[name]=dict(direction='input' if direction=='IN' else 'output',width=width,signed=False)
   need(len(actual)<=8859,'bounded public ports')
  for pattern,label in api_patterns:
   if re.fullmatch(pattern,line):
    need(class_seen and depth==1 and access=='public','public selected-class '+label);api_counts[label]+=1
  if class_seen:
   braces=re.sub(r'"(?:\\.|[^"\\])*"','""',line)
   for ch in braces:
    if ch=='{':depth+=1
    elif ch=='}':depth-=1;need(depth>=0,'nonnegative class brace scope')
   if depth==0:
    need(was_depth==1 and line=='};','exact selected class close');class_closed=True
  code.append(line)
 need(guard is not None and guard_defined and guard_closed and class_seen,'complete generated header wrapper')
 need(actual==ports,'complete public port ABI equals independent reviewed original SV')
 need(class_closed and depth==0,'closed selected class scope')
 for label,count in api_counts.items():need(count==1,'one public selected-class '+label)
 return dict(port_count=len(actual),inputs=sum(x['direction']=='input' for x in actual.values()),outputs=sum(x['direction']=='output' for x in actual.values()),all_width_direction_storage_refs_match=True,constructor_eval_final_declarations_match=True,cpp_type_compile_verified=False)
def logical_lines(text):
 result=[];pending=[];size=0;recipe=False
 for line in text.splitlines():
  need(len(line)<=65536,'bounded Make physical line')
  if not pending and (not line.strip() or line.lstrip().startswith('#')):
   need(not line.startswith('\t') or not line.strip(),'no hidden recipe-comment statement');continue
  if not pending:recipe=line.startswith('\t')
  need(not line.lstrip().startswith('#') or not pending,'no comment embedded in continuation')
  cont=line.endswith('\\');part=line[:-1] if cont else line
  pending.append(part.strip());size+=len(part);need(len(pending)<=1024 and size<=131072,'bounded Make continuation')
  if cont:continue
  result.append((' '.join(x for x in pending if x),recipe));pending=[];size=0;recipe=False
 need(not pending and len(result)<=2000,'complete bounded Make logical statements')
 return result
def parse_assignments(statements):
 values={};other=[]
 for line,recipe in statements:
  m=ASSIGN.fullmatch(line)
  if m:
   key,op,value=m.groups();need(not recipe and key not in values,'nonrecipe unique Make variable');values[key]=(op,value)
  else:other.append((line,recipe))
 return values,other
def top_make_contract(text,model_dir,harness_cpp,tool_root):
 values,other=parse_assignments(logical_lines(text));allowed={'PERL','PYTHON3','VERILATOR_ROOT','SYSTEMC_INCLUDE','SYSTEMC_LIBDIR','VM_PROFC','VM_SC','VM_SP_OR_SC','VM_PCLI','VM_SC_TARGET_ARCH','VM_PREFIX','VM_MODPREFIX','VM_USER_CFLAGS','VM_USER_LDLIBS','VM_USER_CLASSES','VM_USER_DIR','VPATH'}
 need(set(values)==allowed,'closed selected top Make variables')
 exact={'PERL':('=','perl'),'PYTHON3':('=','python3'),'VERILATOR_ROOT':('=',str(tool_root)),'VM_PROFC':('=','0'),'VM_SC':('=','0'),'VM_SP_OR_SC':('=','$(VM_SC)'),'VM_PCLI':('=','1'),'VM_PREFIX':('=',PREFIX),'VM_MODPREFIX':('=',PREFIX),'VM_USER_CFLAGS':('=','-std=c++17'),'VM_USER_LDLIBS':('=',''),'VM_USER_CLASSES':('=',Path(harness_cpp).stem),'VPATH':('+=','$(VM_USER_DIR)')}
 for key,value in exact.items():need(values[key]==value,'exact Make variable '+key)
 for key in ('SYSTEMC_INCLUDE','SYSTEMC_LIBDIR','VM_SC_TARGET_ARCH'):
  op,value=values[key];need(op==('?'+'=' if key.startswith('SYSTEMC_') else '=') and re.fullmatch(r'[A-Za-z0-9_./-]*',value),'non-expanded unused SystemC constant')
 op,dirs=values['VM_USER_DIR'];ds=dirs.split();need(op=='=' and len(ds)==2 and len(set(ds))==2 and all(re.fullmatch(r'[A-Za-z0-9_./-]+',d) for d in ds),'two literal user search directories')
 model=Path(model_dir);want={str(Path(harness_cpp).parent.resolve()),str(model.parent.resolve())};need({str((model/d).resolve()) for d in ds}==want,'only frozen harness and fresh cwd search roots')
 expected=['default: '+PREFIX,'include '+PREFIX+'_classes.mk','include $(VERILATOR_ROOT)/include/verilated.mk',Path(harness_cpp).stem+'.o: '+str(harness_cpp),'$(OBJCACHE) $(CXX) $(CXXFLAGS) $(CPPFLAGS) $(OPT_FAST) -c -o $@ $<',PREFIX+': $(VK_USER_OBJS) $(VK_GLOBAL_OBJS) $(VM_PREFIX)__ALL.a $(VM_HIER_LIBS)','$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@']
 norm=lambda line:' '.join(line.split())
 need([(norm(x),recipe) for x,recipe in other]==[(line,i in (4,6)) for i,line in enumerate(expected)],'exact Make syntax and TAB compile/link recipes, no added commands')
 return dict(prefix=PREFIX,verilator_root=str(tool_root),user_classes=[Path(harness_cpp).stem],user_directories=ds,user_cpp_rule=str(harness_cpp),cpp_standard='c++17',unused_systemc_constants={key:values[key][1] for key in ('SYSTEMC_INCLUDE','SYSTEMC_LIBDIR','VM_SC_TARGET_ARCH')},extra_user_sources=False,make_executed=False)
def classes_contract(text,model_dir,tool_root):
 values,other=parse_assignments(logical_lines(text));switches={'VM_C11':'1','VM_TIMING':'0','VM_COVERAGE':'0','VM_TRACE':'0','VM_TRACE_VCD':'0','VM_TRACE_FST':'0'}
 need(not other and set(values)==set(switches)|{'VM_PARALLEL_BUILDS'}|set(GROUPS),'closed generated class-list file')
 for key,value in switches.items():need(values[key]==('=',value),'exact class switch '+key)
 need(values['VM_PARALLEL_BUILDS'] in (('=','0'),('=','1')),'binary generated parallel-build choice')
 lists={}
 for key in GROUPS:
  op,value=values[key];items=value.split();need(op=='+=' and len(items)<=512 and len(items)==len(set(items)),'bounded unique class list')
  need(all(re.fullmatch(IDENT,x) for x in items),'literal class basenames only');lists[key]=items
 need(lists['VM_GLOBAL_FAST']==['verilated','verilated_threads'] and lists['VM_GLOBAL_SLOW']==[],'only pinned non-SystemC non-DPI non-timing runtime classes')
 generated=[x for key,items in lists.items() if not key.startswith('VM_GLOBAL') for x in items]
 need(generated and len(generated)==len(set(generated)) and all(x.startswith(PREFIX) for x in generated),'unique selected generated source set')
 actual={p.stem for p in Path(model_dir).glob('*.cpp')};need(set(generated)==actual,'all and only generated C++ source files referenced exactly once; default outputGroups=0')
 for name in lists['VM_GLOBAL_FAST']:need((Path(tool_root)/'include'/(name+'.cpp')).is_file(),'pinned runtime source exists')
 return dict(generated_cpp_count=len(generated),generated_cpp_stems=sorted(generated),groups=lists,all_generated_cpp_listed_once=True,default_output_groups=0,parallel_build_metadata=int(values['VM_PARALLEL_BUILDS'][1]),compiler_or_make_invoked=False)
def check(model_dir,ports,harness_cpp,tool_root):
 model=Path(model_dir);h,hp=bounded_text(model/(PREFIX+'.h'),2*1024*1024);mk,mp=bounded_text(model/(PREFIX+'.mk'),256*1024,5000);cl,cp=bounded_text(model/(PREFIX+'_classes.mk'),256*1024,5000)
 return dict(status='PASS_GENERATED_PUBLIC_ABI_AND_SELECTED_MAKE_CONTENT_CONTRACT_ONLY',header=header_contract(h,ports),makefile=top_make_contract(mk,model,harness_cpp,tool_root),classes=classes_contract(cl,model,tool_root),content_files=[hp,mp,cp],dependency_dat_and_d_are_opaque_pinned_metadata=True,full_cpp_semantics_or_compile=False,behavior=False)
