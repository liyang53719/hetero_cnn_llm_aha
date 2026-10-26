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

# BEGIN INHERITED ANNOTATION HELPER (fixed circuit name only changed)
"""Bounded selected CHIRRTL annotation header, not a general FIRRTL validator.
Only json/re imports. Caller reads the file once and supplies exact declaration-derived
DontTouch leaf targets plus all module names after its independent structure checks.
"""
import json
import re
MAX_HEADER_BYTES=8*1024*1024
MAX_ANNOTATIONS=100000
_CIRCUIT='UnifiedSharedResourceCollection'
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
# END INHERITED ANNOTATION HELPER

STATUS = 'PASS_UNIFIED_COMMON_CHIRRTL_DECLARATIONS_ABI_SHARED_RESOURCE_GRAPH_ONLY'
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
    for port in expected['dont_touch_roots']:
        need(port in modules[expected['top']]['ports'],'collection dontTouch required port')
        for ref in type_leaf_paths(modules[expected['top']]['ports'][port][1],port):
            need(len(result)<100000,'total dontTouch target bound')
            result.append('~'+expected['top']+'|'+expected['top']+'>'+ref)
    need(len(result)==len(set(result)),'duplicate expected DontTouch target')
    return {'circuit':expected['top'],'modules':sorted(modules),'dont_touch_targets':result}


def direct_family_map(mod, expected_map):
    need(set(dict(mod['instances']))==set(expected_map),'exact selected instance names')
    got=dict(mod['instances'])
    for inst,base in expected_map.items():need(family(got[inst],base),'selected child family '+inst)
    return got


def selected_expression(expr,nodes,depth=0,seen=()):
    """Bounded scalar expression shape only for the explicit mode/unsupported gate.
    No expression evaluation, general FIRRTL semantics or behavioral proof.
    """
    need(depth<=32 and len(expr)<=65536,'selected scalar expression bound')
    x=compact(expr)
    literal=re.fullmatch(r'UInt<(\d+)>\((0h[0-9a-fA-F]+|[0-9]+)\)',x)
    if literal:
        w=int(literal[1]);v=int(literal[2][2:],16) if literal[2].startswith('0h') else int(literal[2])
        need(0<w<=64 and 0<=v<(1<<w),'selected literal bounds');return ('uint',w,v)
    if re.fullmatch(ID+r'(?:\.'+ID+r')*',x):
        if x in nodes:
            need(x not in seen,'selected expression cycle')
            return selected_expression(nodes[x],nodes,depth+1,seen+(x,))
        return ('ref',x)
    m=re.fullmatch(r'('+ID+r')\((.*)\)',x)
    need(m is not None and m[1] in ('and','geq','leq','mux'),'unsupported selected scalar primitive')
    args=[];balance=0;start=0
    for i,ch in enumerate(m[2]):
        if ch=='(':balance+=1
        elif ch==')':balance-=1;need(balance>=0,'selected expression parentheses')
        elif ch==',' and balance==0:args.append(m[2][start:i]);start=i+1
    need(balance==0,'selected expression parentheses');args.append(m[2][start:])
    need(len(args)==(3 if m[1]=='mux' else 2),'selected expression arity')
    return (m[1],*(selected_expression(a,nodes,depth+1,seen) for a in args))


def check_unsupported_evidence(product):
    nodes={};connections={}
    for line in product['lines']:
        m=re.fullmatch(r'\s+node ('+ID+r') = (.+)',line)
        if m:
            need(m[1] not in nodes and len(nodes)<10000,'bounded unique top nodes');nodes[m[1]]=m[2]
        m=re.fullmatch(r'\s+connect ('+ID+r'(?:\.'+ID+r')*),\s*(.+)',line)
        if m:connections.setdefault(m[1],[]).append(m[2])
    need(re.match(r'UInt<3>\s*,',product['registers'].get('mode','')),'three-bit resource mode register')
    need('resourceMode' in nodes,'resource mode node')
    expected_mode=('and',('geq',('ref','mode'),('uint',1,1)),('leq',('ref','mode'),('uint',3,4)))
    need(selected_expression(nodes['resourceMode'],nodes)==expected_mode,'only modes1..4 are resource modes; mode0 excluded')
    required={
      'io.completeBlockImplemented':('uint',1,0),
      'fabric.io.lease.valid':('and',('ref','admission.io.dispatch.valid'),expected_mode),
      'admission.io.completion.bits.status':('mux',('ref','rejected'),('uint',8,128),('ref','fabric.io.done.bits.status'))}
    for lhs,tree in required.items():
        need(len(connections.get(lhs,[]))==1,'one exact unsupported evidence assignment '+lhs)
        need(selected_expression(connections[lhs][0],nodes)==tree,'unsupported/control connection '+lhs)
    return {'completeBlockImplemented_constant':False,'resource_modes':[1,2,3,4],'excluded_complete_block_mode':0,'rejected_status_literal':128,'scope':'selected declarations/expression connections only, not a proof of every rejection handshake or completed block'}


def check_service(modules,expected):
    service=modules['MatrixPipelineService'];direct=service['instances']
    endpoints=[(i,c) for i,c in direct if family(c,'qwen2_matrix_command_endpoint')]
    gates=[(i,c) for i,c in direct if family(c,'tc_clk_gating')]
    other=dict((i,c) for i,c in direct if external_base(c,expected) is None)
    need(len(direct)==18 and len(endpoints)==8 and len(gates)==8 and set(other)=={'tags','values'},'service eight endpoint/eight ICG/tags/results')
    need(len({c for _,c in endpoints})==8 and len({c for _,c in gates})==8,'eight declared providers each family')
    need(family(other['tags'],'Queue8_Meta') and family(other['values'],'MatrixResultFifo'),'original tags/results FIFO')
    need('io' in service['ports'],'service ABI')
    io=service['ports']['io'][1]
    need(all(name not in io for name in ('seed','transposedDense','packedStepsDrained','returnTag','groupSequence')),'default unseeded/non-transposed/default-drain service ABI')
    tags=modules[other['tags']];values=modules[other['values']]
    need(not tags['instances'] and tags['memories']=={'ram':'cmem'},'metadata queue only memory')
    rows=re.findall(r'^\s+cmem ram\s*:\s*(\{.*\})\s*\[8\]\s*$',tags['text'],re.M)
    need(len(rows)==1 and compact(rows[0])=='{context:UInt<3>,last:UInt<1>,finish:UInt<1>,emit:UInt<1>}','8-entry original metadata shape')
    need(not values['instances'] and not values['memories'],'result FIFO register-only')
    need(set(values['registers'])=={'storage','head','tail','count'},'result FIFO exact registers')
    need(re.match(r'\{\s*value\s*:\s*UInt<32>\[256\]\[16\],\s*context\s*:\s*UInt<3>,\s*last\s*:\s*UInt<1>,\s*error\s*:\s*UInt<1>\}\[2\]\s*,',values['registers']['storage']),'two16x256 FP32 result buffers')
    for n,w in [('head',1),('tail',1),('count',2)]:need(re.match(r'UInt<'+str(w)+r'>\s*,',values['registers'][n]),'FIFO control width')
    return {'metadata_rows':8,'full_result_buffers':2,'words_per_result_buffer':4096,'default_optional_seed_transposed_drain_absent':True}


def passthrough_type_tree(tpe):
    """Same bounded declared-type subset as type_leaf_paths; retain field flips.

    No FIRRTL behavioral evaluation. Rightmost serialized Vec dimension is outer.
    """
    tokens=re.findall(ID+r'|[0-9]+|[{}<>\[\],:]',tpe)
    need(''.join(tokens)==re.sub(r'\s+','',tpe),'passthrough type token coverage')
    need(len(tokens)<=200000,'passthrough type token bound')
    pos=0;nodes=0
    def peek():
        need(pos<len(tokens),'truncated passthrough type');return tokens[pos]
    def eat(token):
        nonlocal pos
        need(peek()==token,'passthrough type expected '+token);pos+=1
    def ident():
        nonlocal pos
        x=peek();need(re.fullmatch(ID,x) is not None,'passthrough type identifier');pos+=1;return x
    def number():
        nonlocal pos
        x=peek();need(re.fullmatch(r'[0-9]{1,7}',x) is not None,'passthrough type number');pos+=1
        n=int(x);need(0<n<=1048576,'passthrough type extent');return n
    def typ(depth=0):
        nonlocal nodes
        need(depth<=32,'passthrough type depth');nodes+=1;need(nodes<=100000,'passthrough type nodes')
        if peek()=='{':
            eat('{');fields=[];names=set()
            while peek()!='}':
                flip=peek()=='flip'
                if flip:eat('flip')
                name=ident();need(name not in names,'duplicate passthrough field');names.add(name)
                eat(':');fields.append((name,flip,typ(depth+1)))
                if peek()==',':eat(',');need(peek()!='}','trailing passthrough comma')
                else:need(peek()=='}','passthrough bundle delimiter')
            eat('}');need(fields,'empty passthrough bundle');node=('bundle',tuple(fields))
        else:
            base=ident();need(base in ('UInt','SInt','Clock','Reset','AsyncReset'),'passthrough ground type')
            width=None
            if base in ('UInt','SInt'):eat('<');width=number();eat('>')
            node=('leaf',base,width)
        while pos<len(tokens) and tokens[pos]=='[':
            eat('[');n=number();eat(']');node=('array',n,node)
            depth+=1;need(depth<=32,'passthrough vector depth')
        return node
    result=typ();need(pos==len(tokens),'trailing passthrough type');return result


def passthrough_leaves(node,path='',flip=False,limit=100000):
    """Expand one already-bounded subtree, returning suffix and relative flip."""
    out=[]
    def emit(n,p,f,depth=0):
        need(depth<=32,'passthrough leaf depth')
        if n[0]=='leaf':
            need(len(out)<limit,'passthrough leaf bound');out.append((p,f,n[1:]))
        elif n[0]=='array':
            need(n[1]<=limit,'passthrough array bound')
            for i in range(n[1]):emit(n[2],p+'['+str(i)+']',f,depth+1)
        else:
            for name,fieldflip,child in n[1]:emit(child,p+'.'+name,f^fieldflip,depth+1)
    emit(node,path,flip);return out


def passthrough_select(tree,suffix):
    """Select a static field/index subtree and accumulate flips above its root."""
    need(re.fullmatch(r'(?:\.'+ID+r'|\[(?:0|[1-9][0-9]{0,6})\])*',suffix) is not None,'static passthrough suffix')
    node=tree;flip=False
    parts=re.findall(r'\.('+ID+r')|\[([0-9]+)\]',suffix)
    need(len(parts)<=32,'passthrough reference depth')
    for name,index in parts:
        if name:
            need(node[0]=='bundle','field on non-bundle passthrough')
            fields={n:(f,c) for n,f,c in node[1]}
            need(name in fields,'unknown passthrough field');f,node=fields[name];flip^=f
        else:
            need(node[0]=='array' and int(index)<node[1],'passthrough index range');node=node[2]
    return node,flip


def check_collection_passthrough(collection,expected):
    """Direct recursive FIRRTL connect coverage for the five fixed namespace roots.

    Aggregate connect reverses its leaf assignment for each relative flipped field.
    After that reversal, each leaf's sink must match the fixed root's cumulative flip.
    Exactly one connection per leaf; no expression, rename, cross-root or override.
    This is bounded syntactic wiring evidence, not general FIRRTL legality/equivalence.
    """
    pairs={('port' if inst=='top' else inst+'Port'):inst+'.io' for inst in expected['collection_instances']}
    trees={root:passthrough_type_tree(collection['ports'][root][1]) for root in pairs}
    wanted={root:{p:(f,t) for p,f,t in passthrough_leaves(tree)} for root,tree in trees.items()}
    need(sum(map(len,wanted.values()))==4616,'fixed 4616 declared passthrough leaves')
    endpoints={root:(root,True) for root in pairs}
    endpoints.update({child:(root,False) for root,child in pairs.items()})
    seen=set();clock_seen=set();connections=0
    def reference(x):
        need(len(x)<=4096 and re.fullmatch(ID+r'(?:\.'+ID+r'|\[(?:0|[1-9][0-9]{0,6})\])*',x) is not None,'direct static passthrough reference')
        found=[(key,r,public) for key,(r,public) in endpoints.items() if x==key or x.startswith(key+'.') or x.startswith(key+'[')]
        need(len(found)==1,'unknown/cross-namespace passthrough endpoint')
        key,root,public=found[0];return root,public,x[len(key):]
    for line in collection['lines']:
        if not line.strip() or line.lstrip().startswith(';'):continue
        if PORT.fullmatch(line) or INSTANCE.fullmatch(line):continue
        match=re.fullmatch(r'    connect (.+),\s*(.+?)\s*',line)
        need(match is not None,'unsupported/conditional collection statement')
        lhs,rhs=match.groups()
        if (lhs,rhs) in (('top.clock','clock'),('top.reset','reset')):
            need(lhs not in clock_seen,'duplicate collection clock/reset connection');clock_seen.add(lhs);continue
        lroot,lpublic,lsuffix=reference(lhs);rroot,rpublic,rsuffix=reference(rhs)
        need(lroot==rroot and lpublic!=rpublic and lsuffix==rsuffix,'same root/suffix with opposite endpoint sides')
        node,aboveflip=passthrough_select(trees[lroot],lsuffix)
        for relpath,relativeflip,tpe in passthrough_leaves(node):
            path=lsuffix+relpath;key=(lroot,path)
            need(path in wanted[lroot] and wanted[lroot][path]==(aboveflip^relativeflip,tpe),'declared passthrough leaf identity')
            actual_public_sink=lpublic^relativeflip
            need(actual_public_sink==(not wanted[lroot][path][0]),'passthrough leaf direction/flip')
            need(key not in seen,'duplicate/overlapping passthrough leaf');seen.add(key)
        connections+=1;need(connections<=4616,'passthrough connection count bound')
    need(clock_seen=={'top.clock','top.reset'},'exact collection clock and reset passthrough')
    need(seen=={(r,p) for r,leaves in wanted.items() for p in leaves},'complete exact passthrough leaf coverage')
    return {'leaf_count':len(seen),'connect_count':connections,'roots':len(pairs),'clock_reset_connections':len(clock_seen)}


def check_unified(modules,expected):
    collection=modules[expected['top']];product=modules[expected['product']];fabric=modules[expected['fabric']]
    need(dict(collection['instances'])==expected['collection_instances'],'exact five common namespace roots')
    direct_family_map(product,expected['product_instances']);fabric_map=direct_family_map(fabric,expected['fabric_instances'])
    exact_ports(collection,{'clock':'input','reset':'input','port':'output','prePort':'output','mulPort':'output','postPort':'output','roundPort':'output'},'UInt<1>')
    exact_ports(product,{'clock':'input','reset':'input','io':'output'},'Reset')
    need(compact(product['ports']['io'][1])==compact(expected['top_io_type']),'exact source-derived unified product IO ABI')
    need(compact(collection['ports']['port'][1])==compact(product['ports']['io'][1]),'same collection/product ABI')
    for inst,child in expected['collection_instances'].items():
        port='port' if inst=='top' else inst+'Port'
        if inst!='top':
            fma=modules[child];exact_ports(fma,{'io':'output'})
            need(flat_fma_fields(fma['ports']['io'][1])==expected['fma_abi'][child],'original FMA declared ABI')
            need(compact(collection['ports'][port][1])==compact(fma['ports']['io'][1]),'FMA namespace port ABI')
    passthrough=check_collection_passthrough(collection,expected)
    memo={}
    families=list(expected['expected_counts'])+list(expected['external_ports'])
    def counts(name):
        if name in memo:return memo[name]
        out={b:int(family(name,b)) for b in families}
        for _,child in modules[name]['instances']:
            for b,v in counts(child).items():
                out[b]+=v;need(out[b]<=64,'bounded counted resource occurrences')
        memo[name]=out;return out
    selected=counts(expected['product'])
    for b,n in expected['expected_counts'].items():need(selected[b]==n,'single product physical resource count '+b)
    for b in expected['external_ports']:need(selected[b]==8,'eight external instances '+b)
    need(counts(expected['top'])==selected,'namespace siblings do not add selected product resources')
    vector=modules[fabric_map['vector']];exact_ports(vector,{'clock':'input','reset':'input','io':'output'},'Reset')
    need(compact(vector['ports']['io'][1])==compact(expected['vector_io_type']),'fixed16-lane vector ABI')
    need(len(vector['instances'])==16 and all(family(c,'HeteroFP32Alu') for _,c in vector['instances']),'16 original direct vector ALUs')
    scalar=modules[fabric_map['scalar']]
    direct_family_map(scalar,{'alu':'HeteroFP32Alu','div':'DivSqrtRecFM_small_e8_s24','conv':'RecFNToIN_e8_s24_i32','integer':'INToRecFN_i32_e8_s24'})
    alus=[c for _,c in vector['instances']]+[dict(scalar['instances'])['alu']]
    for name in alus:
        alu=modules[name];exact_ports(alu,{'clock':'input','reset':'input','io':'output'},'Reset')
        direct_family_map(alu,{'add':'AddRecFN','mul':'MulRecFN'})
        fields=flat_fma_fields(alu['ports']['io'][1])
        need(fields=={'io_op':{'direction':'input','width':1},'io_x':{'direction':'input','width':32},'io_y':{'direction':'input','width':32},'io_out':{'direction':'output','width':32},'io_exceptionFlags':{'direction':'output','width':5}},'original FP32 ALU ABI')
    owner=modules[fabric_map['stateOwner']]
    need(not owner['instances'] and not owner['memories'],'state transfer owner no extra compute/memory child')
    need(re.match(r'UInt<512>\s*,',owner['registers'].get('payload','')),'one64-byte state transfer payload register')
    admission=modules['UnifiedBlockAdmission'];need(not admission['instances'] and not admission['memories'],'admission is only controller')
    return {'selected_product':expected['product'],'passthrough':passthrough,'collection_is_product_or_simulation_top':False,'recursive_product_resource_occurrences':selected,'vector_alu_occurrences':16,'scalar_alu_occurrences':1,'physical_matrix_endpoint_slots':8*512,'issued_or_effective_MAC_measured':False,'namespace_fma_siblings':4,'service':check_service(modules,expected),'unsupported_evidence':check_unsupported_evidence(product)}


def parse_bytes(data, expected):
    need(type(data) is bytes and 0<len(data)<=expected['max_bytes'],'CHIRRTL byte bound')
    annotations,body_start=extract_header(data.decode('utf-8',errors='strict'),expected['top'])
    modules,instances,registers,depth=declared_modules(data,expected,body_start)
    report=check_unified(modules,expected)
    annotation_report=validate_annotations(annotations,annotation_expectation(modules,expected))
    return dict(report,status=STATUS,firrtl_sha256=hashlib.sha256(data).hexdigest(),firrtl_bytes=len(data),annotation_report=annotation_report,top=expected['top'],module_count=len(modules),reachable_module_count=len(modules),instance_count=instances,register_count=registers,hierarchy_depth=depth,expectation_sha256=hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest(),scope={'chisel_construction_and_chirrtl_only':True,'selected_shared_resource_graph':True,'provider_sv_linted':False,'physical_fma_closed':False,'firrtl_semantic_or_lowering_validation':False,'behavior_executed':False,'numerical_pass':False,'systemverilog_generated':False,'rtl_simulated':False,'fullblock_accepted':False,'matrix_mac_utilization':None})


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
