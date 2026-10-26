"""Bounded common-collection declarations/topology/ABI checker, stdlib only.

Not a full FIRRTL grammar, legality/equivalence check or numerical execution.
Sixteen declarations of two explicitly qualified external provider families remain: provider SV is NOT parsed here.
Parent parsing memory has input/count bounds, not the child's hard AS/RSS cap.
"""
import hashlib
import json
from pathlib import Path
import re
import stat

# BEGIN EXACT INLINE ANNOTATION HELPER
"""Bounded selected CHIRRTL annotation header, not a general FIRRTL validator.
Only json/re imports. Caller reads the file once and supplies exact declaration-derived
DontTouch leaf targets plus all module names after its independent structure checks.
"""
import json
import re
MAX_HEADER_BYTES=8*1024*1024
MAX_ANNOTATIONS=100000
_CIRCUIT='OrderedQkRealMatrixCollection'
_DONT='firrtl.transforms.DontTouchAnnotation'
_DEDUP='firrtl.transforms.DedupGroupAnnotation'
_IDENT=re.compile(r'[A-Za-z_][A-Za-z0-9_$]{0,255}\Z',re.ASCII)
_REFERENCE=re.compile(r'~([A-Za-z_][A-Za-z0-9_$]{0,255})\|([A-Za-z_][A-Za-z0-9_$]{0,255})>([A-Za-z_][A-Za-z0-9_$]{0,255}(?:\.[A-Za-z_][A-Za-z0-9_$]{0,255}|\[(?:0|[1-9][0-9]{0,9})\])*)\Z',re.ASCII)
_MODULE=re.compile(r'~([A-Za-z_][A-Za-z0-9_$]{0,255})\|([A-Za-z_][A-Za-z0-9_$]{0,255})\Z',re.ASCII)
def _need(ok,why):
 if not ok:raise ValueError('annotation gate: '+why)
def _pairs(pairs):
 d={}
 for k,v in pairs:
  _need(k not in d,'duplicate JSON key');d[k]=v
 return d
def _constant(v):raise ValueError('annotation gate: nonstandard JSON constant '+v)
def _shape(annotations):
 _need(type(annotations) is list and 0<len(annotations)<=MAX_ANNOTATIONS,'nonempty bounded annotation list')
 for a in annotations:
  _need(type(a) is dict,'annotation object')
  cls=a.get('class')
  _need(cls in (_DONT,_DEDUP),'unknown annotation class')
  keys={'class','target'} if cls==_DONT else {'class','target','group'}
  _need(set(a)==keys,'exact annotation fields')
  _need(type(a['target']) is str and 0<len(a['target'])<=4096,'bounded target string')
  if cls==_DEDUP:_need(type(a['group']) is str and _IDENT.fullmatch(a['group']) is not None,'bounded group identifier')
def extract_header(text,circuit):
 """Return (strictly shaped annotations, offset after complete circuit-header line)."""
 _need(type(text) is str and circuit==_CIRCUIT,'fixed text/circuit')
 prefix='FIRRTL version 3.3.0\ncircuit '+circuit+' :%['
 _need(text.startswith(prefix),'exact version/circuit/embedded-annotation opening')
 # A bounded prefix copy prevents JSON decoding from consuming the module body.
 sample=text[:MAX_HEADER_BYTES+1]
 _need(len(sample[:len(prefix)].encode('utf-8'))<=MAX_HEADER_BYTES,'header prefix bytes')
 decoder=json.JSONDecoder(object_pairs_hook=_pairs,parse_constant=_constant)
 try:annotations,pos=decoder.raw_decode(sample,len(prefix))
 except (ValueError,RecursionError) as e:raise ValueError('annotation gate: malformed/bounded JSON') from e
 _shape(annotations)
 _need(pos<len(sample) and sample[pos]==']','wrapper closing bracket')
 end=sample.find('\n',pos+1)
 _need(end>=0,'complete header terminator within bound')
 suffix=sample[pos+1:end]
 _need(re.fullmatch(r'(?: @\[(?:\\.|[^\\\]\r\n])*\])?',suffix,re.ASCII) is not None,'no trailing header statement')
 end+=1
 _need(len(text[:end].encode('utf-8'))<=MAX_HEADER_BYTES,'header bytes cap')
 return annotations,end

def validate_annotations(annotations,expected):
 """Target membership is exact; expected values must come from parsed port types.
Dedup group textual identifier is checked, not inferred model equivalence semantics.
"""
 _shape(annotations)
 _need(type(expected) is dict and set(expected)=={'circuit','modules','dont_touch_targets'},'exact expected schema')
 circuit=expected['circuit'];_need(circuit==_CIRCUIT,'fixed circuit')
 modules=expected['modules'];leaves=expected['dont_touch_targets']
 _need(type(modules) in (list,tuple,set) and 0<len(modules)<=10000,'module bound')
 _need(all(type(n) is str and _IDENT.fullmatch(n) for n in modules),'module identifiers')
 module_set=set(modules);_need(len(module_set)==len(modules),'duplicate expected module')
 _need(type(leaves) in (list,tuple,set) and 0<len(leaves)<=MAX_ANNOTATIONS,'DontTouch expected bound')
 leaf_set=set(leaves);_need(len(leaf_set)==len(leaves),'duplicate expected target')
 for target in leaf_set:
  _need(type(target) is str and len(target)<=4096,'expected target string')
  match=_REFERENCE.fullmatch(target)
  _need(match is not None and match[1]==circuit and match[2] in module_set,'expected target syntax/membership')
 seen_dont=set();seen_dedup=set();groups={}
 for a in annotations:
  t=a['target']
  if a['class']==_DONT:
   _need(t in leaf_set,'DontTouch target not exact declared allowed leaf')
   _need(t not in seen_dont,'duplicate DontTouch target');seen_dont.add(t)
  else:
   m=_MODULE.fullmatch(t)
   _need(m is not None and m[1]==circuit and m[2] in module_set,'Dedup target must be declared local module')
   _need(m[2] not in seen_dedup,'duplicate Dedup target');seen_dedup.add(m[2]);groups[m[2]]=a['group']
 _need(seen_dont==leaf_set,'complete expected DontTouch leaf set')
 _need(seen_dedup==module_set,'one Dedup annotation per declared component')
 return {'status':'PASS_SELECTED_EMBEDDED_ANNOTATION_SCHEMA_AND_EXACT_TARGET_SETS_ONLY','annotation_count':len(annotations),'dont_touch_count':len(seen_dont),'dedup_group_count':len(seen_dedup),'custom_file_emission_allowed':False,'full_annotation_semantics_verified':False}
# END EXACT INLINE ANNOTATION HELPER

STATUS = 'PASS_COMMON_COLLECTION_CHIRRTL_STRUCTURE_AND_DECLARED_PROVIDER_ABI_ONLY'
ID = r'[A-Za-z_][A-Za-z0-9_$]*'
MODULE = re.compile(r'^  (module|extmodule) ('+ID+r')\s*:\s*$')
INSTANCE = re.compile(r'^    inst ('+ID+r') of ('+ID+r')\s*$')
REGISTER = re.compile(r'^\s+reg(?:reset)? ('+ID+r')\s*:\s*(.+)')
MEMORY = re.compile(r'^\s+(smem|cmem) ('+ID+r')\s*:\s*(.+)$')
PORT = re.compile(r'^    (input|output) ('+ID+r')\s*:\s*(.+?)\s*$')
DEFNAME = re.compile(r'^    defname = ('+ID+r')\s*$')
STRUCTURAL = re.compile(r'^\s*(?:(?:public|private)\s+)?(module|extmodule|intmodule|intrinsic|defname|parameter|inst|regreset|reg|smem|cmem|mem|input|output|class|object|layer|declgroup|option|type|instchoice)\b')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def family(name, base):
    return re.fullmatch(re.escape(base)+r'(?:_\d+)?', name) is not None


def external_base(name, expected):
    found=[base for base in expected['external_ports'] if family(name,base)]
    need(len(found)<=1, 'ambiguous external family')
    return found[0] if found else None


def compact(s):
    return re.sub(r'\s+', '', s)


def declared_modules(data, expected, body_start):
    need(type(data) is bytes and 0<len(data)<=expected['max_bytes'], 'CHIRRTL byte bound')
    text=data.decode('utf-8',errors='strict')
    need('\x00' not in text, 'NUL in CHIRRTL')
    need(text.startswith('FIRRTL version '+expected['firrtl_version']+'\n'), 'exact pinned FIRRTL text version')
    need(len(re.findall(r'^circuit\s+',text,re.M))==1, 'one circuit')
    circuit=re.search(r'^circuit ('+ID+r')\s*:',text,re.M)
    need(circuit is not None and circuit.group(1)==expected['top'], 'common collection circuit')
    need(text.count('\n')+(not text.endswith('\n'))<=expected['max_lines'], 'CHIRRTL line-count bound')
    need(type(body_start) is int and 0<body_start<len(text),'validated annotation header end')
    header_lines=text[:body_start].count('\n')
    modules={};current=None;instance_count=register_count=0
    for number,line in enumerate(text.split('\n'),1):
        if number<=header_lines:continue # Header has its own exact8MiB byte gate.
        need(len(line.encode('utf-8'))<=expected['max_line_bytes'], 'CHIRRTL body line byte bound')
        code=line.split(' @[',1)[0]
        head=STRUCTURAL.match(code);kind=head.group(1) if head else None
        declaration=MODULE.fullmatch(code)
        if kind in ('module','extmodule'):
            need(declaration is not None, 'unparsed module declaration at line '+str(number))
        if declaration:
            flavor,name=declaration.groups()
            need(name not in modules, 'duplicate module '+name)
            need(len(modules)<expected['max_modules'], 'module bound')
            if flavor=='extmodule':need(external_base(name,expected) is not None, 'unknown external '+name)
            modules[name]={'kind':flavor,'lines':[],'instances':[],'instance_names':set(),'registers':{},'memories':{},'ports':{},'defname':None}
            current=modules[name];continue
        if current is None:
            need(head is None, 'structure before first module')
            need(not code.strip() or code.lstrip().startswith(';'),'unparsed post-header pre-module material')
            continue
        current['lines'].append(code)
        port=PORT.fullmatch(code)
        if kind in ('input','output'):need(port is not None, 'unparsed module port')
        if port:
            direction,name,tpe=port.groups()
            need(name not in current['ports'], 'duplicate module port')
            current['ports'][name]=[direction,tpe];continue
        if current['kind']=='extmodule':
            if not code.strip() or code.lstrip().startswith(';'):continue
            d=DEFNAME.fullmatch(code)
            need(d is not None and current['defname'] is None, 'external body/parameter/unparsed declaration')
            current['defname']=d.group(1);continue
        need(kind not in ('intmodule','intrinsic','defname','parameter','class','object','layer','declgroup','option','type','instchoice'), 'unsupported structural declaration at line '+str(number))
        instance=INSTANCE.fullmatch(code)
        if kind=='inst':need(instance is not None, 'unparsed/non-direct instance declaration')
        if instance:
            inst,child=instance.groups()
            need(inst not in current['instance_names'], 'duplicate instance')
            instance_count+=1
            need(instance_count<=expected['max_instances'], 'instance-count bound')
            need(len(current['instances'])<expected['max_instances_per_module'], 'per-module instance bound')
            current['instance_names'].add(inst);current['instances'].append((inst,child))
        register=REGISTER.fullmatch(code)
        if kind in ('reg','regreset'):need(register is not None, 'unparsed register declaration')
        memory=MEMORY.fullmatch(code)
        if kind in ('smem','cmem','mem'):need(memory is not None, 'unparsed/unsupported memory declaration')
        if memory:
            need(memory.group(2) not in current['memories'], 'duplicate memory')
            current['memories'][memory.group(2)]=memory.group(1)
        if register:
            register_count+=1
            need(register_count<=expected['max_registers'], 'register-count bound')
            need(register.group(1) not in current['registers'], 'duplicate register')
            current['registers'][register.group(1)]=register.group(2)
    need(expected['top'] in modules, 'collection missing')
    for name,mod in modules.items():
        for _,child in mod['instances']:need(child in modules, 'unresolved module '+child)
        mod['text']='\n'.join(mod['lines'])
        if mod['kind']=='extmodule':
            base=external_base(name,expected)
            need(mod['defname']==base, 'exact canonical external defname')
            need(mod['ports']==expected['external_ports'][base], 'exact external ABI '+name)
    need({n for n,m in modules.items() if m['kind']=='extmodule'}==set(expected['external_definition_names']), 'exact sixteen external definitions/two provider families')
    visiting=set();visited=set();heights={}
    def visit(name,depth=0):
        need(depth<=expected['max_hierarchy_depth'], 'hierarchy-depth bound')
        need(name not in visiting, 'recursive hierarchy')
        if name in visited:return heights[name]
        visiting.add(name);height=0
        for _,child in modules[name]['instances']:height=max(height,1+visit(child,depth+1))
        need(height<=expected['max_hierarchy_depth'], 'hierarchy-depth bound')
        visiting.remove(name);visited.add(name);heights[name]=height;return height
    visit(expected['top'])
    need(visited==set(modules), 'unreachable/unexpected emitted module')
    for name in modules:
        need(not any(family(name,b) for b in expected['forbidden_module_families']), 'unexpected top/service '+name)
    return modules,instance_count,register_count,heights[expected['top']]


def exact_ports(mod, expected, reset=None):
    need(set(mod['ports'])==set(expected), 'exact port names')
    for name,direction in expected.items():need(mod['ports'][name][0]==direction, 'exact port direction '+name)
    if reset is not None:
        need(mod['ports']['clock']==['input','Clock'], 'exact clock')
        need(mod['ports']['reset']==['input',reset], 'exact reset')
        need([n for n,(d,t) in mod['ports'].items() if d=='input' and t=='Clock']==['clock'], 'single module clock')


def flat_fma_fields(tpe):
    need(tpe.startswith('{') and tpe.endswith('}'), 'FMA io aggregate')
    parts=tpe[1:-1].split(',');out={}
    for part in parts:
        m=re.fullmatch(r'\s*(flip\s+)?('+ID+r')\s*:\s*UInt<(\d+)>\s*',part)
        need(m is not None, 'unparsed FMA scalar field')
        flip,name,width=m.groups();need('io_'+name not in out,'duplicate FMA field')
        out['io_'+name]={'direction':'input' if flip else 'output','width':int(width)}
    return out


def type_leaf_paths(tpe, root, limit=100000):
    """Bounded pinned-serializer UInt/SInt/Clock/Reset aggregate subset.

    Mirrors the already-reviewed Vec/bundle flattening direction/order, but
    preserves FIRRTL target dots and bracket indices, not Verilog underscores.
    Directions are immaterial to dontTouch target identity.
    """
    tokens=re.findall(ID+r'|[0-9]+|[{}<>\[\],:]',tpe)
    need(''.join(tokens)==re.sub(r'\s+','',tpe),'annotation target type token coverage')
    need(len(tokens)<=200000,'annotation type token bound')
    pos=0;nodes=0
    def peek():
        need(pos<len(tokens),'truncated annotation port type');return tokens[pos]
    def eat(token):
        nonlocal pos
        need(peek()==token,'annotation port type expected '+token);pos+=1
    def ident():
        nonlocal pos
        name=peek();need(re.fullmatch(ID,name) is not None,'annotation type identifier');pos+=1;return name
    def number():
        nonlocal pos
        x=peek();need(re.fullmatch(r'[0-9]{1,7}',x) is not None,'annotation type number');pos+=1
        n=int(x);need(0<n<=1048576,'annotation type extent');return n
    def typ(depth=0):
        nonlocal nodes
        need(depth<=32,'annotation type depth bound');nodes+=1;need(nodes<=100000,'annotation type node bound')
        if peek()=='{':
            eat('{');fields=[];names=set()
            while peek()!='}':
                if peek()=='flip':eat('flip')
                field=ident();need(field not in names,'duplicate annotation bundle field');names.add(field)
                eat(':');fields.append((field,typ(depth+1)))
                if peek()==',':eat(',');need(peek()!='}','trailing bundle comma')
                else:need(peek()=='}','annotation bundle delimiter')
            eat('}');node=('bundle',fields)
        else:
            base=ident();need(base in ('UInt','SInt','Clock','Reset','AsyncReset'),'unsupported annotation target type')
            if base in ('UInt','SInt'):eat('<');number();eat('>')
            node=('leaf',)
        while pos<len(tokens) and tokens[pos]=='[':
            eat('[');n=number();eat(']');node=('array',n,node)
            depth+=1;need(depth<=32,'annotation vector depth bound')
        return node
    tree=typ();need(pos==len(tokens),'trailing annotation type tokens');out=[]
    def emit(node,path,depth=0):
        need(depth<=32,'annotation leaf depth bound')
        if node[0]=='leaf':
            need(len(out)<limit,'annotation leaf-count bound');out.append(path)
        elif node[0]=='array':
            need(node[1]<=limit,'annotation array bound')
            for i in range(node[1]):emit(node[2],path+'['+str(i)+']',depth+1)
        else:
            for name,child in node[1]:emit(child,path+'.'+name,depth+1)
    emit(tree,root);return out


def annotation_expectation(modules, expected):
    result=[]
    roots={expected['top']:('port','observation','scoreWrite','prePort','mulPort','postPort','roundPort'),
           expected['core']:('io','observation','testScoreWrite')}
    for module,names in roots.items():
        for port in names:
            need(port in modules[module]['ports'],'dontTouch required port')
            for ref in type_leaf_paths(modules[module]['ports'][port][1],port):
                need(len(result)<100000,'total dontTouch target bound')
                result.append('~'+expected['top']+'|'+module+'>'+ref)
    need(len(result)==len(set(result)),'duplicate expected dontTouch target')
    return {'circuit':expected['top'],'modules':sorted(modules),
            'dont_touch_targets':result}


def check_collection_service(modules, expected):
    collection=modules[expected['top']];shell=modules[expected['shell']]
    need(dict(collection['instances'])==expected['collection_instances'],'exact collection five namespace roots')
    need(dict(shell['instances'])==expected['shell_instances'],'exact selected shell three children')
    exact_ports(collection,{'clock':'input','reset':'input','port':'output','observation':'output','scoreWrite':'output','prePort':'output','mulPort':'output','postPort':'output','roundPort':'output'},'UInt<1>')
    exact_ports(shell,{'clock':'input','reset':'input','io':'output','observation':'output','scoreWrite':'output'},'Reset')
    for a,b in [('port','io'),('observation','observation'),('scoreWrite','scoreWrite')]:
        need(compact(collection['ports'][a][1])==compact(shell['ports'][b][1]),'collection pass-through ABI '+a)
    core=modules[expected['core']]
    for a,b in [('observation','observation'),('scoreWrite','testScoreWrite')]:
        need(compact(shell['ports'][a][1])==compact(core['ports'][b][1]),'readonly selected observation ABI '+a)
    for inst,child in expected['collection_instances'].items():
        if inst=='top':continue
        fma=modules[child];exact_ports(fma,{'io':'output'})
        need(flat_fma_fields(fma['ports']['io'][1])==expected['fma_abi'][child],'original FMA declared ABI '+child)
        need(compact(collection['ports'][inst+'Port'][1])==compact(fma['ports']['io'][1]),'FMA common-namespace exposure '+inst)
    service=modules['MatrixPipelineService'];direct=service['instances']
    endpoints=[(i,c) for i,c in direct if family(c,'qwen2_matrix_command_endpoint')]
    gates=[(i,c) for i,c in direct if family(c,'tc_clk_gating')]
    other=dict((i,c) for i,c in direct if external_base(c,expected) is None)
    need(len(direct)==18 and len(endpoints)==8 and len(gates)==8 and set(other)=={'tags','values'}, 'service eight endpoint/eight ICG/tags/results')
    need(len({c for _,c in endpoints})==8 and len({c for _,c in gates})==8,'eight distinct declared provider modules per family')
    need(family(other['tags'],'Queue8_Meta') and family(other['values'],'MatrixResultFifo'),'original tags/results FIFO classes')
    need('packedStepsDrained : UInt<1>' in service['ports']['io'][1], 'selected drain-status ABI')
    need('seed' not in service['ports']['io'][1].lower() and 'transposedDense' not in service['ports']['io'][1], 'unseeded/non-transposed service ABI')
    tags=modules[other['tags']]
    need(not tags['instances'] and tags['memories']=={'ram':'cmem'}, 'original tag queue memory-only storage')
    rows=re.findall(r'^\s+cmem ram\s*:\s*(\{.*\})\s*\[8\]\s*$',tags['text'],re.M)
    need(len(rows)==1, 'eight metadata queue rows')
    need(compact(rows[0])=='{context:UInt<3>,last:UInt<1>,finish:UInt<1>,emit:UInt<1>}','unseeded tag metadata fields')
    values=modules[other['values']]
    need(not values['instances'] and not values['memories'],'two-result FIFO register storage only')
    need(set(values['registers'])=={'storage','head','tail','count'},'original result FIFO register set')
    need(re.match(r'\{\s*value\s*:\s*UInt<32>\[256\]\[16\],\s*context\s*:\s*UInt<3>,\s*last\s*:\s*UInt<1>,\s*error\s*:\s*UInt<1>\}\[2\]\s*,',values['registers']['storage']), 'two full 16x256 FP32 result buffers')
    for name,width in [('head',1),('tail',1),('count',2)]:need(re.match(r'UInt<'+str(width)+r'>\s*,',values['registers'][name]),'result FIFO control width')
    memo={}
    def extcounts(name):
        if name in memo:return memo[name]
        out={x:int(modules[name]['kind']=='extmodule' and external_base(name,expected)==x) for x in expected['external_ports']}
        for _,child in modules[name]['instances']:
            for k,v in extcounts(child).items():
                out[k]+=v;need(out[k]<=8,'extra selected/provider external occurrence')
        memo[name]=out;return out
    selected=extcounts(expected['shell'])
    need(selected=={x:8 for x in expected['external_ports']}, 'selected shell external closure counts')
    need(extcounts(expected['top'])==selected,'FMA siblings contain no extra externals')
    return {'selected_shell':expected['shell'],'collection_direct_instances':expected['collection_instances'],
            'shell_direct_instances':expected['shell_instances'],'qualified_external_occurrences':selected,
            'external_declaration_abi':expected['external_ports'],'fma_declared_abi':expected['fma_abi'],
            'service_metadata_rows':8,'service_result_buffers':2,'service_result_words_per_buffer':4096}

def check_original_core(modules, expected):
    core=modules[expected['core']];body=core['text'];direct=core['instances']
    counts={base:sum(family(child,base) for _,child in direct) for base in expected['direct_instances']}
    need(counts==expected['direct_instances'], 'direct selected instance counts')
    need(len(direct)==sum(expected['direct_instances'].values()), 'extra direct core instance')
    need(re.search(r'^\s+input clock\s*:\s*Clock\s*$',body,re.M), 'one core clock port')
    clocks=re.findall(r'^\s+input ('+ID+r')\s*:\s*Clock\s*$',body,re.M)
    need(clocks==['clock'], 'exactly one top input clock')
    ports=re.findall(r'^\s+(input|output) ('+ID+r')\s*:',body,re.M)
    need(set(ports)=={('input','clock'),('input','reset'),('output','io'),('output','testScoreWrite'),('output','observation')} and len(ports)==5, 'exact selected top port set')
    need(re.search(r'^\s+input reset\s*:\s*Reset\s*$',body,re.M), 'nested original core abstract Reset port')
    io=next((line for line in core['lines'] if re.match(r'^\s+output io\s*:',line)),None)
    need(io is not None, 'original core ABI')
    for field in expected['required_io_fields']:
        need(re.search(r'\b'+re.escape(field)+r'\s*:',io), 'missing ABI field '+field)
    for field in expected['forbidden_io_fields']:
        need(not re.search(r'\b'+re.escape(field)+r'\s*:',io), 'unexpected profile ABI '+field)
    need(core['memories']=={name:'smem' for name,_,_ in expected['memories']}, 'exact core scratch memory set')
    for name,width,depth in expected['memories']:
        pattern=r'^\s+smem '+re.escape(name)+r'\s*:\s*UInt<'+str(width)+r'>\s*\['+str(depth)+r'\]\s*$'
        need(len(re.findall(pattern,body,re.M))==1, 'exact synchronous scratch '+name)
    need(re.match(r'UInt<7>\s*,',core['registers'].get('state','')), 'seven-bit original state')
    need(re.match(r'UInt<32>\[16\]\s*,',core['registers'].get('acc','')), 'original sixteen-word accumulator')
    need(re.match(r'UInt<1>\[16\]\s*,',core['registers'].get('orderedQkFault','')), 'selected sixteen sticky fault bits')
    for state in expected['ordered_state_codes']:
        literal=r'UInt<7>\((?:0h'+format(state,'x')+'|'+str(state)+r')\)'
        need(re.search(r'eq\(state,\s*'+literal+r'\)',body), 'selected state comparison '+str(state))
        need(re.search(r'connect state,\s*'+literal,body), 'selected state transition '+str(state))
    for output in ('testScoreWrite','observation'):
        need(re.search(r'^\s+output '+output+r'\s*:',body,re.M), 'readonly output '+output)
    need(re.search(r'connect testScoreWrite.valid,\s*UInt<1>\((?:0h1|1)\)',body), 'actual write-site probe enable')
    client_instances=[(inst,child) for inst,child in direct if family(child,'PackedAttentionStreamClient')]
    client_inst,client_name=client_instances[0]
    client=modules[client_name]
    need(set(client['registers'])=={'state','descriptor','index','poison'}, 'unchanged enabled client control-only register set')
    need(re.match(r'UInt<3>\s*,',client['registers']['state']), 'enabled eight-state client')
    need(re.match(r'UInt<8>\s*,',client['registers']['index']), 'client index width')
    need(re.match(r'UInt<1>\s*,',client['registers']['poison']), 'client poison width')
    descriptor=client['registers']['descriptor']
    for part in ('tag : UInt<32>','pv : UInt<1>','count : UInt<8>'):
        need(part in descriptor, 'client descriptor field '+part)
    need(not client['instances'] and not re.search(r'^\s+(?:s?mem|cmem)\b',client['text'],re.M), 'client has no arithmetic/memory child')
    for lhs,rhs in expected['client_port_connections']:
        lhs=lhs.replace('$CLIENT',client_inst);rhs=rhs.replace('$CLIENT',client_inst)
        need(re.search(r'^\s+connect '+re.escape(lhs)+r',\s*'+re.escape(rhs)+r'\s*$',body,re.M), 'actual client port connection '+lhs)
    alus=[child for _,child in direct if family(child,'HeteroFP32Alu')]
    for name in alus:
        alu=modules[name]
        for base in ('AddRecFN','MulRecFN'):
            need(sum(family(child,base) for _,child in alu['instances'])==1, 'real FP32 primitive '+name+'/'+base)
        need('exceptionFlags : UInt<5>' in alu['text'], 'strict flags present '+name)
    fabrics=[child for _,child in direct if family(child,'SharedL2Fabric')]
    banks=re.findall(r'^\s+smem ('+ID+r')\s*:\s*UInt<8>\[16\]\s*\['+str(expected['core_fabric_rows_per_bank'])+r'\]\s*$',modules[fabrics[0]]['text'],re.M)
    need(len(banks)==16 and len(set(banks))==16, 'sixteen original core SRAM banks at original capacity')
    return {'direct_instance_counts':counts,'direct_instance_names':[list(x) for x in direct],
            'selected_state_codes':expected['ordered_state_codes'],'core_sram_banks':len(banks),
            'core_sram_rows_per_bank':expected['core_fabric_rows_per_bank'],
            'client_control_registers':sorted(client['registers']),'strict_vector_alu_instances':len(alus)}


def parse_bytes(data, expected):
    need(type(data) is bytes and 0<len(data)<=expected['max_bytes'],'CHIRRTL byte bound')
    annotations,body_start=extract_header(data.decode('utf-8',errors='strict'),expected['top'])
    modules,instances,registers,depth=declared_modules(data,expected,body_start)
    core=check_original_core(modules,expected)
    new=check_collection_service(modules,expected)
    annotation_report=validate_annotations(annotations,annotation_expectation(modules,expected))
    return dict(core,**new,status=STATUS,firrtl_sha256=hashlib.sha256(data).hexdigest(),firrtl_bytes=len(data),
                annotation_report=annotation_report,top=expected['top'],module_count=len(modules),reachable_module_count=len(modules),
                instance_count=instances,register_count=registers,hierarchy_depth=depth,
                expectation_sha256=hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                scope={'chisel_construction_and_chirrtl_output_only':True,'common_namespace_and_selected_structure_check':True,
                       'sixteen_external_declarations_two_provider_families_remain':True,'provider_sv_linted':False,'physical_fma_closed':False,
                       'firrtl_semantic_or_lowering_validation':False,'behavior_executed':False,'numerical_pass':False,
                       'systemverilog_generated':False,'rtl_simulated':False,'fullblock_accepted':False,'matrix_mac_utilization':None})


def check(path, expected):
    path=Path(path);before=path.lstat()
    need(stat.S_ISREG(before.st_mode) and not path.is_symlink(),'regular CHIRRTL artifact')
    need(0<before.st_size<=expected['max_bytes'],'file byte bound')
    with path.open('rb') as stream:data=stream.read(expected['max_bytes']+1)
    after=path.lstat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'CHIRRTL changed during audit')
    need(len(data)==before.st_size,'CHIRRTL extent')
    result=parse_bytes(data,expected);result['path']=str(path);return result
