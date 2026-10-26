"""Bounded, source-informed CIRCT 1.62.1 emitted-SV structural guard.
Not a general SV parser, compiler, equivalence proof, or behavior test.
Imports no HDL tools. Actual generated target must be terminal/cleaned before use.
"""
import hashlib
import json
import re
import stat
import os
from pathlib import Path

IDENT = r'[A-Za-z_][A-Za-z_0-9$]*'
MOD = re.compile(r'^module\s+('+IDENT+r')\s*\(\s*$')
PORT = re.compile(r'^(?:(input|output)\s+)?(?:(?:wire|logic)\s+)?(?:(signed)\s+)?(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?('+IDENT+r')$')
CONNECTION = re.compile(r'\s*\.('+IDENT+r')\s*\(')
TWO = re.compile(r'^('+IDENT+r')\s+('+IDENT+r')\s*(.*)$')
MEM = re.compile(r'^reg\s+\[(\d+)\s*:\s*(\d+)\]\s+('+IDENT+r')\s*\[(\d+)\s*:\s*(\d+)\]\s*;$')
FORBID = re.compile(r'\b(?:extern|interface|modport|primitive|endprimitive|program|package|endpackage|import|export|bind|class|endclass|specify|endspecify)\b')
SYSTEM_FORBID = re.compile(r'\$(?:readmem\w*|fopen|system|sdf_annotate)\b')
KEYWORDS = set('wire reg logic assign always always_ff always_comb always_latch initial begin end if else for case casez casex endcase integer genvar localparam parameter generate endgenerate function endfunction task endtask return automatic assert assume cover'.split())
MACROS = {'ASSERT_VERBOSE_COND','ASSERT_VERBOSE_COND_','STOP_COND','STOP_COND_','SYNTHESIS'}

# Only known emitted declaration initializers and continuous assignments enter
# continuation state. No unknown declaration/call is turned into an expression.
EXPR_START = re.compile(r'^(?:(?:wire|logic|reg)\s+(?:signed\s+)?(?:\[\s*\d+\s*:\s*\d+\s*\]\s*)?'+IDENT+r'|assign\s+'+IDENT+r'(?:\[\s*\d+(?:\s*:\s*\d+)?\s*\])*)\s*=\s*(.*)$')
EXPR_TOKEN = re.compile(r"\s*(?:([0-9][0-9_]*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|'[01xXzZ]|[0-9][0-9_]*)|("+IDENT+r"|\$[A-Za-z_][A-Za-z_0-9$]*)|([(){}\[\],?:~!%^&*+|<>/=-]))")
EXPR_FORBID = KEYWORDS | set('module endmodule input output inout tri wand wor supply0 supply1 defparam typedef struct union enum const static virtual new void int bit byte shortint longint realtime real event time fork join join_any join_none wait do while repeat forever disable force release'.split())
EXPR_CALLS = {'$signed', '$unsigned'}
# Actual inventory: nine plain-name nonblocking RHSs and one blocking RHS.
# Exact fixed CIRCT 1.62.1 ReservedWords.def names (includes macro guards).
# This is the exporter namespace exclusion table, not a general SV grammar.
PINNED_RESERVED_NAMES = frozenset('ENABLE_INITIAL_REG_ INIT_RANDOM INIT_RANDOM_PROLOG_ PRINTF_COND PRINTF_COND_ RANDOM RANDOMIZE RANDOMIZE_DELAY RANDOMIZE_GARBAGE_ASSIGN RANDOMIZE_INVALID_ASSIGN RANDOMIZE_MEM_INIT RANDOMIZE_REG_INIT STOP_COND STOP_COND_ SYNTHESIS VCS alias always always_comb always_ff always_latch and assert assign assume attribute automatic before begin bind bins binsof bit break buf bufif0 bufif1 byte case casex casez cell chandle checker class clocking cmos config const constraint context continue cover covergroup coverpoint cross deassign default defparam design disable dist do edge else end endattribute endcase endclass endclocking endconfig endfunction endgenerate endgroup endinterface endmodule endpackage endprimitive endprogram endproperty endsequence endspecify endtable endtask enum event expect export extends extern final first_match for force foreach forever fork forkjoin function generate genvar highz0 highz1 if iff ifnone ignore_bins illegal_bins import incdir include initial initvar inout input inside instance int integer interconnect interface intersect join join_any join_none large liblist library local localparam logic longint macromodule matches medium modport module nand negedge new nmos nor noshowcancelled not notif0 notif1 null or output package packed parameter pmos posedge primitive priority program property protected pull0 pull1 pulldown pullup pulsestyle_ondetect pulsestyle_onevent pure rand randc randcase randsequence rcmos real realtime ref reg release repeat return rnmos rpmos rtran rtranif0 rtranif1 scalared sequence shortint shortreal showcancelled signed small solve specify specparam static strength string strong0 strong1 struct super supply0 supply1 table tagged task this throughout time timeprecision timeunit tran tranif0 tranif1 tri tri0 tri1 triand trior trireg type typedef union unique unsigned use var vectored virtual void wait wait_order wand weak0 weak1 while wildcard wire with within wor xnor xor'.split())
PROC_EXPR_START = re.compile(r'^(?P<lhs>'+IDENT+r')\s*(?:<=|=(?!=))\s*(?P<rhs>.*)$')


def validate_expression(chunks, max_depth):
    """Lexical containment, not width/value/equivalence or general SV grammar."""
    text=' '.join(chunks).strip()
    need(text.endswith(';') and text.count(';')==1,'expression requires one final semicolon')
    text=text[:-1].strip();at=0;stack=[];previous=None;tokens=0
    while at<len(text):
        m=EXPR_TOKEN.match(text,at);need(m is not None,'unsupported expression token')
        number,ident,op=m.groups();token=number or ident or op
        kind='atom' if number or ident else 'operator'
        if ident:
            need(ident not in EXPR_FORBID,'structural/declaration keyword in expression')
            need(not ident.startswith('$') or ident in EXPR_CALLS,'unreviewed expression system call')
        if previous:
            pk,pt=previous
            need(not (pk=='atom' and kind=='atom'),'adjacent atoms / split declaration in expression')
            if token=='(' and pk=='atom':need(pt in EXPR_CALLS,'unreviewed function / instance call in expression')
        if op in ('(', '[', '{'):
            stack.append(op);need(len(stack)<=max_depth,'expression nesting bound')
        elif op in (')',']','}'):
            need(stack and stack[-1]=={')':'(',']':'[','}':'{'}[op],'unbalanced expression delimiters');stack.pop()
        # '=' is not an assignment operator inside these expressions. The
        # emitted comparison spellings ==/!=/<=/>= remain lexically admitted.
        if token=='=':
            following=m.end()
            while following<len(text) and text[following].isspace():following+=1
            need((previous and previous[1] in ('=','!','<','>')) or (following<len(text) and text[following]=='='),'nested assignment in expression')
        previous=(kind,token);tokens+=1;at=m.end()
    need(tokens>0 and not stack,'empty/unfinished expression')


def need(ok, msg):
    if not ok: raise ValueError(msg)


def clean_line(line, block):
    # Fast path for ordinary firtool output. The slow path retains lexical state.
    if not block and '/*' not in line and '"' not in line:
        return line.split('//',1)[0], False
    out=[];i=0
    while i<len(line):
        if block:
            j=line.find('*/',i)
            if j<0: return ''.join(out), True
            i=j+2;block=False;continue
        if line.startswith('//',i): break
        if line.startswith('/*',i): block=True;i+=2;continue
        if line[i]=='"':
            out.append('""');i+=1;closed=False
            while i<len(line):
                if line[i]=='\\': i+=2;continue
                if line[i]=='"': i+=1;closed=True;break
                i+=1
            need(closed,'unterminated/multiline string outside supported emitted syntax')
            continue
        out.append(line[i]);i+=1
    return ''.join(out),block


def regular(path, cap):
    st=path.lstat();need(stat.S_ISREG(st.st_mode),'nonregular/symlink output '+str(path))
    need(0<st.st_size<=cap,'output byte bound '+str(path))
    return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)


def parse_connections(chunks):
    text=''.join(chunks).strip()
    need(text.endswith(');'),'instance terminator')
    text=text[:-2];at=0;ports={}
    while at<len(text):
        m=CONNECTION.match(text,at)
        need(m is not None,'unsupported/positional instance connection')
        name=m[1];need(name not in ports,'duplicate named instance port')
        at=m.end();start=at;depth=1
        while at<len(text) and depth:
            if text[at]=='(':depth+=1
            elif text[at]==')':depth-=1
            if depth:at+=1
        need(depth==0,'unterminated port expression')
        ports[name]=bool(text[start:at].strip());at+=1
        while at<len(text) and text[at].isspace():at+=1
        if at<len(text):
            need(text[at]==',','connection separator');at+=1
            while at<len(text) and text[at].isspace():at+=1
            need(at<len(text),'trailing instance comma')
    return ports


def parse_sv(path, expectation):
    e=expectation;before=regular(path,e['max_sv_bytes']);modules={};cur=None
    header=False;direction=None;width=None;signed=False;pending=None;paren=0
    block=False;directives=[];conditional_depth=0;line_count=0;instance_count=0
    expression=None;expression_count=0
    total_ports=0;has_header=False;digest=hashlib.sha256();total_bytes=0
    with path.open('rb') as stream:
        for raw in iter(lambda:stream.readline(e['max_line_bytes']+1),b''):
            line_count+=1;total_bytes+=len(raw);digest.update(raw)
            need(line_count<=e['max_lines'] and len(raw)<=e['max_line_bytes'],'SV line bounds')
            if expression is not None:
                need(total_bytes-expression['start_byte']<=e['max_expression_bytes'] and line_count-expression['start_line']+1<=e['max_expression_lines'],'expression continuation bound')
            line=raw.decode('utf-8',errors='strict')
            if line_count==1: has_header=line.rstrip()=='// Generated by CIRCT firtool-1.62.1'
            code,block=clean_line(line,block);s=code.strip()
            if not s:continue
            need(not FORBID.search(s) and not SYSTEM_FORBID.search(s),'external/unsupported SV construct')
            need('#' not in s and '\\' not in s,'unsupported parameter/delay/escaped identifier syntax')
            if s.startswith('`'):
                d=re.fullmatch(r'`(ifdef|ifndef|else|endif|define)\b\s*(.*)',s)
                need(d is not None,'unsupported preprocessor directive')
                op,arg=d.groups()
                if op in ('ifdef','ifndef'):
                    need(arg in MACROS,'unknown conditional macro');conditional_depth+=1
                elif op=='endif':
                    need(not arg and conditional_depth>0,'unbalanced endif');conditional_depth-=1
                elif op=='else':need(not arg and conditional_depth>0,'unbalanced else')
                else:
                    parts=arg.split(None,1);need(len(parts)==2,'macro definition form')
                    name,body=parts
                    allowed={'ASSERT_VERBOSE_COND_':{'1','(`ASSERT_VERBOSE_COND)'},'STOP_COND_':{'1','(`STOP_COND)'}}
                    need(name in allowed and body in allowed[name],'unreviewed macro definition body')
                directives.append(op);need(len(directives)<=e['max_directives'],'directive cap')
                need(not header and pending is None and expression is None,'conditional port/instance/expression syntax not admitted')
                continue
            for macro in re.findall(r'`('+IDENT+r')',s):need(macro in MACROS,'unknown macro use')
            if expression is not None:
                expression['chunks'].append(s)
                if ';' in s:
                    validate_expression(expression['chunks'],e['max_expression_depth'])
                    expression=None;expression_count+=1
                continue
            m=MOD.fullmatch(s)
            if m:
                name=m[1];need(cur is None and not conditional_depth,'nested/conditional module')
                need(name not in modules and len(modules)<e['max_modules'],'duplicate/module cap')
                cur={'ports':{},'instances':{},'memories':{},'body_lines':0,'initial_blocks':0,'body_paren_depth':0,'body_begin_depth':0};modules[name]=cur;cur['name']=name
                header=True;direction=None;width=None;signed=False;continue
            if re.search(r'\bmodule\b',s):raise ValueError('unparsed module declaration')
            if s=='endmodule':
                need(cur is not None and not header and pending is None and not conditional_depth,'unbalanced/incomplete/conditional module')
                need(cur['body_lines']>0,'empty/blackbox-like module')
                need(cur['body_paren_depth']==0 and cur['body_begin_depth']==0,'unfinished module body parentheses/begin-end')
                cur=None;continue
            if re.search(r'\bendmodule\b',s):raise ValueError('unparsed endmodule')
            need(cur is not None,'code outside modules')
            if header:
                ending=s.endswith(');')
                if ending:s=s[:-2].strip()
                if s:
                    parts=s.split(',')
                    for part in parts:
                        if not part.strip():continue
                        p=PORT.fullmatch(part.strip());need(p is not None,'unsupported ANSI port')
                        dr,sg,hi,lo,name=p.groups()
                        if dr:
                            direction=dr;signed=bool(sg);width=(abs(int(hi)-int(lo))+1) if hi is not None else 1
                        else:need(sg is None and hi is None,'width/direction inheritance ambiguity')
                        need(direction is not None and name not in cur['ports'],'missing/duplicate port')
                        cur['ports'][name]={'direction':direction,'width':width,'signed':signed}
                        total_ports+=1;need(len(cur['ports'])<=e['max_ports_per_module'] and total_ports<=e['max_total_ports'],'port bounds')
                if ending:header=False
                continue
            cur['body_lines']+=1
            if re.match(r'^initial\b',s):cur['initial_blocks']+=1
            if pending is not None:
                pending['chunks'].append(s+'\n');pending['text_bytes']+=len(raw)
                need(pending['text_bytes']<=e['max_instance_text_bytes'],'instance connection text bound')
                paren+=s.count('(')-s.count(')');need(paren>=0,'unbalanced instance')
                if paren==0:
                    pending['ports']=parse_connections(pending.pop('chunks'));pending.pop('text_bytes');pending=None
                continue
            initializer=EXPR_START.fullmatch(s)
            procedural=PROC_EXPR_START.fullmatch(s) if ';' not in s else None
            first_word=re.match(IDENT,s)
            if ';' not in s and re.search(r'(?:<=|>=|=)\s*$',s) and not initializer and (first_word is None or first_word[0] not in KEYWORDS):
                need(procedural is not None,'unsupported assignment/comparison head')
            if procedural:
                need(procedural['lhs'] not in (EXPR_FORBID | PINNED_RESERVED_NAMES),'reserved procedural lvalue')
                need(cur['body_paren_depth']==0,'procedural RHS inside control parentheses')
            rhs=initializer[1] if initializer else (procedural['rhs'] if procedural else None)
            if rhs is not None and ';' not in s:
                need(not conditional_depth,'conditional initializer continuation not admitted')
                need(len(raw)<=e['max_expression_bytes'],'expression continuation byte bound')
                expression={'chunks':[rhs],'start_byte':total_bytes-len(raw),'start_line':line_count}
                continue
            bare=re.fullmatch(r'('+IDENT+r')\s*\(?',s)
            need(bare is None or bare[1] in KEYWORDS,'unsupported split declaration/call')
            mm=MEM.fullmatch(s)
            if mm:
                hi,lo,name,a,b=mm.groups();need(name not in cur['memories'],'duplicate memory')
                cur['memories'][name]=dict(width=abs(int(hi)-int(lo))+1,depth=abs(int(a)-int(b))+1)
            pair=TWO.fullmatch(s)
            if pair and pair[1] not in KEYWORDS:
                target,name,tail=pair.groups();need(tail=='(','unparsed potential instance/declaration')
                need(name not in cur['instances'] and not conditional_depth,'duplicate/conditional instance')
                item=dict(target=target,ports={},chunks=[],text_bytes=0);cur['instances'][name]=item
                instance_count+=1;need(instance_count<=e['max_instances'] and len(cur['instances'])<=e['max_instances_per_module'],'instance bounds')
                pending=item;paren=1
            if pending is None:
                # Track only outer normal-body delimiters. Port headers,
                # instance connections and bounded RHS expressions have their
                # own independent state. This is not procedural semantics.
                for token in re.findall(r'\b(?:begin|end)\b|[()]',s):
                    key='body_paren_depth' if token in ('(',')') else 'body_begin_depth'
                    cur[key]+=1 if token in ('(','begin') else -1
                    need(0<=cur[key]<=e['max_expression_depth'],'module body delimiter bound/balance')
    need(before==regular(path,e['max_sv_bytes']),'SV changed while checking')
    need(total_bytes==before[2] and has_header,'exact generated-version header/bytes')
    need(not block and not conditional_depth and cur is None and pending is None and expression is None,'unfinished lexical/structural state')
    top=e['top'];need(top in modules,'missing common collection')
    external=e['external_ports']
    need(set(external)=={'qwen2_matrix_command_endpoint','tc_clk_gating'},'exact qualified external family set')
    need(not (set(external)&set(modules)),'external provider definition must not be fabricated inside emitted SV')
    for name,ports in e['selected_module_ports'].items():
        need(name in modules and modules[name]['ports']==ports,'exact selected flattened ABI '+name)
    need(modules[top]['ports']==e['top_ports'],'exact flattened collection ABI')
    for name,mod in modules.items():
        need(not any(re.fullmatch(x+r'(?:_\d+)?',name) for x in e['forbidden_module_families']),'forbidden hardware family')
        for inst in mod['instances'].values():
            target=inst['target'];need(target in modules or target in external,'unresolved/unqualified external instance '+target)
            target_ports=external[target] if target in external else modules[target]['ports']
            need(set(inst['ports'])<=set(target_ports),'unresolved named instance port')
            need(all(inst['ports'].get(n) is True for n,p in target_ports.items() if p['direction']=='input'),'omitted/empty input instance port')
            if target in external:
                need(set(inst['ports'])==set(target_ports) and all(inst['ports'].values()),'qualified provider requires every named port nonempty')
    visiting=set();done=set();order=[];stack=[(top,False,0)]
    while stack:
        name,finish,depth=stack.pop();need(depth<=e['max_hierarchy_depth'],'hierarchy depth')
        if finish:visiting.remove(name);done.add(name);order.append(name);continue
        if name in done:continue
        need(name not in visiting,'recursive module graph');visiting.add(name);stack.append((name,True,depth))
        for inst in reversed(list(modules[name]['instances'].values())):
            if inst['target'] not in external:stack.append((inst['target'],False,depth+1))
    need(done==set(modules),'unreachable emitted module')
    def family(name):return re.sub(r'_\d+$','',name)
    def counts(name):
        result={}
        for inst in modules[name]['instances'].values():result[family(inst['target'])]=result.get(family(inst['target']),0)+1
        return result
    for parent,children in e['exact_direct_instances'].items():
        need(parent in modules,'selected parent missing')
        need({n:i['target'] for n,i in modules[parent]['instances'].items()}==children,'exact collection/shell instances '+parent)
    core=e['core'];service=e['service'];need(core in modules and service in modules,'missing core/service')
    direct=counts(core)
    for name,count in e['direct_instance_counts'].items():need(direct.get(name)==count,'direct selected core structure '+name)
    for inst_name,shape in e['top_memory_instances'].items():
        need(inst_name in modules[core]['instances'],'missing selected core memory instance')
        target=modules[core]['instances'][inst_name]['target'];mems=list(modules[target]['memories'].values())
        need(mems==[shape],'selected memory storage shape')
    for inst_name,target_family in e['service_required_instances'].items():
        inst=modules[service]['instances'].get(inst_name)
        need(inst is not None and family(inst['target'])==target_family,'missing service tag/result queue '+inst_name)
    direct_external={n:sum(i['target']==n for i in modules[service]['instances'].values()) for n in external}
    need(direct_external==e['external_occurrences'],'exact direct service external instances')
    # Postorder sums count actual hierarchy occurrences, not only shared definitions.
    capacities={};occurrences={}
    for name in order:
        cap={};ext={n:0 for n in external}
        for item in modules[name]['memories'].values():
            key=(item['width'],item['depth']);cap[key]=cap.get(key,0)+1
        for inst in modules[name]['instances'].values():
            target=inst['target']
            if target in external:ext[target]+=1;continue
            for k,v in capacities[target].items():cap[k]=cap.get(k,0)+v
            for k,v in occurrences[target].items():ext[k]+=v
        capacities[name]=cap;occurrences[name]=ext
    need(occurrences[top]==e['external_occurrences'],'exact common-hierarchy external occurrence count')
    fabric=modules[core]['instances'].get('fabric');need(fabric is not None,'missing core fabric')
    need(capacities[fabric['target']].get((128,2240))==16,'core local SRAM 16 x 128 x 2240')
    return dict(status='PASS_REAL_MATRIX_COMMON_SV_STRUCTURE_ONLY',sv_bytes=total_bytes,sv_sha256=digest.hexdigest(),lines=line_count,continued_expression_count=expression_count,module_count=len(modules),instance_count=instance_count,reachable_defined_module_count=len(done),top=top,top_port_count=len(modules[top]['ports']),selected_shell=e['shell'],collection_is_simulation_top=False,selected_module_port_counts={n:len(modules[n]['ports']) for n in e['selected_module_ports']},direct_core_instance_counts=direct,core_sram_banks=16,qualified_external_defnames=sorted(external),qualified_external_occurrences=occurrences[top],external_implementation_definitions_in_emitted_sv=0,provider_implementation_qualified=False,full_physical_fma_closure_verified=False,external_file_initialization=False,initial_block_count=sum(m['initial_blocks'] for m in modules.values()),storage_initial_contents_and_latency_verified=False,scope='bounded emitted declarations/selected ABI/defined graph plus exactly two unresolved qualified provider ABIs; provider SV lint and real arithmetic closure still required',behavior_pass=False,numerical_pass=False,mac_utilization=None)


def check_tree(root, expectation):
    root=Path(root);e=expectation
    st=root.lstat();need(stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode),'output root must be nonsymlink directory')
    required={'CLAIM.json','worker.log','tool/firtool',e['fir_input'],e['sv_output']}
    allowed=required|{e['annotation_output']};allowed_dirs={'home','tmp','empty-path'}
    # Supervisor-created private directories may be empty only; their children
    # are absent from both the file and directory allowlists.
    for rel in allowed:
        for parent in Path(rel).parents:
            if str(parent)!='.':allowed_dirs.add(parent.as_posix())
    seen=set();items=0
    def walk_error(error):raise error
    for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        for name in dirs+files:
            items+=1;need(items<=32,'output tree item bound')
            p=Path(directory)/name;st=p.lstat();rel=p.relative_to(root).as_posix()
            need(not stat.S_ISLNK(st.st_mode),'output tree symlink')
            if stat.S_ISDIR(st.st_mode):need(rel in allowed_dirs,'unexpected output directory '+rel);continue
            need(stat.S_ISREG(st.st_mode),'output tree nonregular')
            need(rel in allowed,'unexpected output '+rel);seen.add(rel)
    need(required<=seen,'missing required output')
    anno=root/e['annotation_output'];anno_result={'present':False}
    if anno.exists():
        before=regular(anno,e['max_annotation_bytes'])
        with anno.open('rb') as stream:data=stream.read(e['max_annotation_bytes']+1)
        need(len(data)==before[2],'annotation read bound')
        v=json.loads(data);need(isinstance(v,list) and len(v)<=e['max_annotation_count'],'annotation array bounds')
        need(before==regular(anno,e['max_annotation_bytes']),'annotation changed')
        # Not part of provider behavior qualification; original firtool JSON is preserved.
        anno_result=dict(present=True,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),count=len(v),requires_independent_content_review=True)
    out=parse_sv(root/e['sv_output'],e);out['annotations']=anno_result
    return out
