"""Bounded stdlib CHIRRTL structure gate. No backend import or execution.

This checks emitted selected structure, not behavioral/numerical equivalence,
low-FIRRTL legality, SystemVerilog, area, timing, or Matrix utilization.
"""
import hashlib
import json
from pathlib import Path
import re
import stat

STATUS = 'PASS_SELECTED_ON_CHIRRTL_STRUCTURE_ONLY'
ID = r'[A-Za-z_][A-Za-z0-9_$]*'
MODULE = re.compile(r'^  module ('+ID+r')\s*:\s*$')
INSTANCE = re.compile(r'^\s+inst ('+ID+r') of ('+ID+r')\s*$')
REGISTER = re.compile(r'^\s+reg(?:reset)? ('+ID+r')\s*:\s*(.+)')
FORBIDDEN = re.compile(r'^\s*(?:(?:public|private)\s+)?(?:extmodule|intmodule|intrinsic|defname)\b')
STRUCTURAL = re.compile(r'^\s*(?:(?:public|private)\s+)?(module|inst|regreset|reg|smem|cmem|mem)\b')
MEMORY = re.compile(r'^\s+(smem|cmem) ('+ID+r')\s*:\s*(.+)$')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def family(name, base):
    return re.fullmatch(re.escape(base)+r'(?:_\d+)?', name) is not None


def parse_bytes(data, expected):
    need(type(data) is bytes and 0<len(data)<=expected['max_bytes'], 'CHIRRTL byte bound')
    text=data.decode('utf-8',errors='strict')
    need('\x00' not in text, 'NUL in CHIRRTL')
    need(text.startswith('FIRRTL version '+expected['firrtl_version']+'\n'), 'exact pinned FIRRTL text version')
    need(len(re.findall(r'^circuit\s+',text,re.M))==1, 'one circuit')
    match=re.search(r'^circuit ('+ID+r')\s*:',text,re.M)
    need(match is not None and match.group(1)==expected['top'], 'selected top circuit')
    need(text.count('\n')<=expected['max_lines'], 'CHIRRTL line-count bound')
    modules={};current=None;instance_count=register_count=0
    for number,line in enumerate(text.splitlines(),1):
        need(len(line.encode('utf-8'))<=expected['max_line_bytes'], 'CHIRRTL line byte bound')
        code=line.split(' @[',1)[0]
        need(FORBIDDEN.match(code) is None, 'external/intrinsic/blackbox declaration at line '+str(number))
        declaration=MODULE.match(code)
        head=STRUCTURAL.match(code)
        if head and head.group(1)=='module':
            need(declaration is not None, 'unparsed module declaration at line '+str(number))
        if declaration:
            name=declaration.group(1)
            need(name not in modules, 'duplicate module '+name)
            need(len(modules)<expected['max_modules'], 'module bound')
            modules[name]={'lines':[], 'instances':[], 'instance_names':set(), 'registers':{}, 'memories':{}}
            current=modules[name]
            continue
        if current is None:
            need(head is None, 'structure before first module')
            continue # Header annotations before first module are metadata only.
        current['lines'].append(code)
        instance=INSTANCE.match(code)
        if head and head.group(1)=='inst':
            need(instance is not None, 'unparsed instance declaration at line '+str(number))
        if instance:
            need(instance.group(1) not in current['instance_names'], 'duplicate instance')
            instance_count+=1
            need(instance_count<=expected['max_instances'], 'instance-count bound')
            need(len(current['instances'])<expected['max_instances_per_module'], 'per-module instance bound')
            current['instance_names'].add(instance.group(1))
            current['instances'].append(instance.groups())
        register=REGISTER.match(code)
        if head and head.group(1) in ('reg','regreset'):
            need(register is not None, 'unparsed register declaration')
        memory=MEMORY.match(code)
        if head and head.group(1) in ('smem','cmem','mem'):
            need(memory is not None, 'unparsed/unsupported memory declaration')
        if memory:
            need(memory.group(2) not in current['memories'], 'duplicate memory')
            current['memories'][memory.group(2)]=memory.group(1)
        if register:
            register_count+=1
            need(register_count<=expected['max_registers'], 'register-count bound')
            need(register.group(1) not in current['registers'], 'duplicate register')
            current['registers'][register.group(1)]=register.group(2)
    need(expected['top'] in modules, 'top module missing')
    for name,mod in modules.items():
        for _,child in mod['instances']:
            need(child in modules, 'unresolved module '+child)
        mod['text']='\n'.join(mod['lines'])
    visiting=set();visited=set()
    def visit(name,depth=0):
        need(depth<=expected['max_hierarchy_depth'], 'hierarchy-depth bound')
        need(name not in visiting, 'recursive hierarchy')
        if name in visited:return
        visiting.add(name)
        for _,child in modules[name]['instances']:visit(child,depth+1)
        visiting.remove(name);visited.add(name)
    visit(expected['top'])
    need(visited==set(modules), 'unreachable/unexpected emitted module')
    forbidden_families=expected['forbidden_module_families']
    for name in modules:
        need(not any(family(name,base) for base in forbidden_families), 'unexpected top/service '+name)
    core=modules[expected['top']];body=core['text'];direct=core['instances']
    counts={base:sum(family(child,base) for _,child in direct) for base in expected['direct_instances']}
    need(counts==expected['direct_instances'], 'direct selected instance counts')
    need(len(direct)==sum(expected['direct_instances'].values()), 'extra direct core instance')
    need(re.search(r'^\s+input clock\s*:\s*Clock\s*$',body,re.M), 'one core clock port')
    clocks=re.findall(r'^\s+input ('+ID+r')\s*:\s*Clock\s*$',body,re.M)
    need(clocks==['clock'], 'exactly one top input clock')
    ports=re.findall(r'^\s+(input|output) ('+ID+r')\s*:',body,re.M)
    need(set(ports)=={('input','clock'),('input','reset'),('output','io'),('output','testScoreWrite'),('output','observation')} and len(ports)==5, 'exact selected top port set')
    need(re.search(r'^\s+input reset\s*:\s*UInt<1>\s*$',body,re.M), 'default top-level Bool reset port')
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
    return {'status':STATUS,'firrtl_sha256':hashlib.sha256(data).hexdigest(),'firrtl_bytes':len(data),
            'top':expected['top'],'module_count':len(modules),'reachable_module_count':len(visited),'instance_count':instance_count,'register_count':register_count,
            'direct_instance_counts':counts,'direct_instance_names':[list(x) for x in direct],
            'selected_state_codes':expected['ordered_state_codes'],'core_sram_banks':len(banks),
            'core_sram_rows_per_bank':expected['core_fabric_rows_per_bank'],
            'client_control_registers':sorted(client['registers']),'strict_vector_alu_instances':len(alus),
            'no_external_or_intrinsic_modules':True,'expectation_sha256':hashlib.sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'scope':{'chisel_construction_and_chirrtl_output_only':True,'selected_structure_check':True,
                     'firrtl_semantic_or_lowering_validation':False,'behavior_executed':False,
                     'numerical_pass':False,'systemverilog_generated':False,'rtl_simulated':False,
                     'fullblock_accepted':False,'matrix_mac_utilization':None}}


def check(path, expected_binding):
    path=Path(path)
    before=path.lstat()
    need(stat.S_ISREG(before.st_mode) and not path.is_symlink(), 'regular CHIRRTL artifact')
    need(0<before.st_size<=expected_binding['max_bytes'], 'file byte bound')
    with path.open('rb') as stream:
        data=stream.read(expected_binding['max_bytes']+1)
    after=path.lstat()
    need((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
         (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), 'CHIRRTL changed during audit')
    need(len(data)==before.st_size, 'CHIRRTL extent')
    result=parse_bytes(data,expected_binding)
    result['path']=str(path)
    return result
