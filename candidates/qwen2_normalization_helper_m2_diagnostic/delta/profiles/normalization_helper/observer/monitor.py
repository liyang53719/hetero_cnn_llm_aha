"""Read-only source-bound CPython monitoring of the actual ordered owner path.

New source-bound normalization-helper owner contract; no arithmetic/reference calls.
No runtime patching or callback injection into the owner.
AST-test filename aliases are explicit and cannot qualify a runtime profile.
"""
import ast,dis,hashlib,json,sys,threading,types
from pathlib import Path
PINS=json.loads(Path(__file__).with_name("SOURCE_PINS.json").read_text())
from .capture import Fields,need

def child(code,name):
    values=[x for x in code.co_consts if isinstance(x,types.CodeType) and x.co_name==name]
    need(len(values)==1,'ambiguous source code '+name);return values[0]

def bind(method,path,digest,classname,name,ast_test):
    path=__import__('pathlib').Path(path).resolve(strict=True);raw=path.read_bytes();need(hashlib.sha256(raw).hexdigest()==digest,'observer source drift')
    actual=method.__func__.__code__ if hasattr(method,'__func__') else method.__code__
    need(ast_test or actual.co_filename==str(path),'actual loaded source filename differs')
    tree=ast.parse(raw,filename=actual.co_filename)
    if ast_test:tree=ast.Module(body=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))],type_ignores=[])
    expected=child(child(compile(tree,actual.co_filename,'exec'),classname),name)
    need(actual==expected and actual.co_firstlineno==expected.co_firstlineno and actual.co_linetable==expected.co_linetable,'source-bound method differs '+classname+'.'+name)
    return actual

def lines(path,classname,method,statements):
    tree=ast.parse(__import__('pathlib').Path(path).read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname);fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method)
    result={}
    for key,statement in statements.items():
        expected=ast.dump(ast.parse(statement).body[0],include_attributes=False)
        hits=[n.lineno for n in ast.walk(fn) if isinstance(n,ast.stmt) and ast.dump(n,include_attributes=False)==expected]
        need(len(hits)==1,'missing/ambiguous point '+key);result[key]=hits[0]
    return result


NORMALIZATION_CONTRACT='normalization-helper-active-chain-v1'
NORMALIZATION_ROLES=frozenset(('run','work','consume','matrix','op','normalization','tick','client'))

def source_method(path,classname,name):
    tree=ast.parse(Path(path).read_text())
    classes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname]
    need(len(classes)==1,'normalization source class differs')
    methods=[n for n in classes[0].body if isinstance(n,ast.FunctionDef) and n.name==name]
    need(len(methods)==1,'normalization source method differs')
    return methods[0]

def call_site(code,node,*,direct_return=False):
    """CPython3.12 suspended Python CALL ends at its final inline CACHE.

    Exact AST expression positions identify one CALL. Three CACHE slots and
    their offsets are validated, never an arbitrary same-line instruction.
    """
    instructions=tuple(dis.get_instructions(code,show_caches=True,adaptive=False))
    span=(node.lineno,node.end_lineno,node.col_offset,node.end_col_offset)
    matches=[i for i,item in enumerate(instructions)
             if item.opname=='CALL' and tuple(item.positions)==span]
    need(len(matches)==1,'normalization CALL source span differs')
    index=matches[0];call=instructions[index]
    need(call.arg==len(node.args)+len(node.keywords),'normalization CALL argument count differs')
    caches=instructions[index+1:index+4]
    need(len(caches)==3 and all(item.opname=='CACHE' and item.offset==call.offset+2*(i+1)
         for i,item in enumerate(caches)),'CPython3.12 CALL cache layout differs')
    need(index+4<len(instructions) and instructions[index+4].opname!='CACHE','normalization CALL cache extent differs')
    following=instructions[index+4]
    if direct_return:need(following.opname=='RETURN_VALUE','normalization result not directly returned')
    return caches[-1].offset,following.offset if direct_return else None

def normalization_sites(bindings,codes):
    """Prove exact forwarding AST, then bind the actual active instruction sites."""
    need(set(codes)==NORMALIZATION_ROLES,'normalization exact role inventory')
    op_binding,helper_binding=bindings['op'],bindings['normalization']
    need(Path(op_binding[1]).resolve()==Path(helper_binding[1]).resolve() and
         op_binding[2]==helper_binding[2] and op_binding[3:]==('AttentionOwner','_op') and
         helper_binding[3:]==('AttentionOwner','_normalization_helper'),'normalization binding roles differ')
    op=source_method(op_binding[1],'AttentionOwner','_op')
    helper=source_method(helper_binding[1],'AttentionOwner','_normalization_helper')
    expected=ast.parse("""class AttentionOwner:
    def _op(self, operation, a, b=0, *, policy='legacy_scalar'):
        if operation == 'div' or operation == 'mul':
            return self._normalization_helper(operation, a, b, policy=policy)
        return self.scalar.op(self, operation, a, b, policy=policy)
    def _normalization_helper(self, operation, a, b=0, *, policy='legacy_scalar'):
        return self.scalar.op(self, operation, a, b, policy=policy)
""").body[0].body
    need(ast.dump(op,include_attributes=False)==ast.dump(expected[0],include_attributes=False) and
         ast.dump(helper,include_attributes=False)==ast.dump(expected[1],include_attributes=False),
         'normalization direct forwarding source differs')
    op_wait,op_return=call_site(codes['op'],op.body[0].body[0].value,direct_return=True)
    helper_wait,helper_return=call_site(codes['normalization'],helper.body[0].value,direct_return=True)
    need(bindings['run'][3:]==('ProductionQk16Schedule','run'),'normalization run binding differs')
    run=source_method(bindings['run'][1],'ProductionQk16Schedule','run')
    result={'op_wait':op_wait,'op_return':op_return,'helper_wait':helper_wait,'helper_return':helper_return}
    for operation,statement in (
            ('div',"inverse = o._op('div', 0x3f800000, total)"),
            ('mul',"probability = o._op('mul', probability, inverse)")):
        expected=ast.dump(ast.parse(statement).body[0],include_attributes=False)
        hits=[n for n in ast.walk(run) if isinstance(n,ast.Assign) and ast.dump(n,include_attributes=False)==expected]
        need(len(hits)==1,'normalization caller assignment differs')
        result['run_'+operation+'_wait']=call_site(codes['run'],hits[0].value)[0]
    need(result['run_div_wait']!=result['run_mul_wait'],'normalization caller sites overlap')
    return types.MappingProxyType(result)

class Observation:
    def __init__(self,owner,rows,base_fields,bindings,*,ast_definition_test=False,selective_lines=False):
        need(sys.version_info[:2]==(3,12) and sys.implementation.name=='cpython','CPython3.12 required')
        need(type(ast_definition_test) is bool,'explicit test provenance')
        need(PINS.get('observation_contract')==NORMALIZATION_CONTRACT,'normalization contract pin differs')
        need(selective_lines is True,'normalization helper requires explicit selective contract')
        self.normalization_contract=NORMALIZATION_CONTRACT
        need(set(bindings)==set(PINS['roles']),'exact binding roles required')
        need(all(item[2]==PINS['roles'][key] for key,item in bindings.items()),'binding is not published selected source')
        base_path=Path(sys.modules[base_fields.__module__].__file__).resolve(strict=True)
        for name in ('__init__','_put','_bytes','field_summary'):
            bind(getattr(base_fields,name),base_path,PINS['buffer_sha256'],'PackedFields',name,False)
        self.owner=owner;self.data=Fields(base_fields(rows));self.ast_test=ast_definition_test
        self.thread=threading.get_ident();self.error=None;self.tool=None;self.started=False;self.closed=False
        self.services=(owner.matrix,owner.scalar,owner.packed_schedule,owner.ordered_adapter)
        need(owner.ordered_adapter is not None,'ordered path must be explicitly installed')
        self.codes={};self.specs=bindings
        for key,(method,path,digest,cls,name) in bindings.items():self.codes[key]=bind(method,path,digest,cls,name,ast_definition_test)
        self.normalization_sites=normalization_sites(bindings,self.codes)
        self._normalization_sites_source=self.normalization_sites
        self._normalization_role_codes=tuple((role,self.codes[role]) for role in ('run','op','normalization'))
        self.points=lines(bindings['run'][1],'ProductionQk16Schedule','run',{
            'commit':'maximum = retired.maximum','exponential':"total = o._op('add', total, probability)",
            'store':'yield from o._write(j.dst + (token * 1536 + head * 128 + col) * 4, output)'})
        # Match exact statements unique to scan/scale; never arithmetic reconstruction.
        self.workpoints=lines(bindings['work'][1],'OrderedFoldAdapter','tick',{
            'scan':"if not fp.finite(work.result.value[work.row][16*j+work.row]):\n    work.faults[j]=True",
            'scale':"if self.observe is not None:self.observe('scale',j,total,dot,r.value,score)"})
        self.matrixpoint=lines(bindings['matrix'][1],'AttentionOwner','_matrix_step',{'packet':'result = yield LegacyRequest(opcode, a, b, clear, last, steps)'})['packet']
        self.clientpoint=lines(bindings['client'][1],'PackedClient','tick',{'pre':'p = self.ports()'})['pre']
        need(type(selective_lines) is bool,'explicit selective opt-in')
        self.selective_lines=selective_lines
        self.selected_lines=types.MappingProxyType(self.line_selection()) if selective_lines else None
        self._line_selection_source=self.selected_lines
        self._line_role_codes=tuple(self.codes.items()) if selective_lines else None
        # Per-instance immutable identity index; strong code refs prevent id reuse.
        self._line_by_identity=(types.MappingProxyType({id(code):(code,points)
            for code,points in self.selected_lines.items()}) if selective_lines else None)
        self.prob={};self.client=None;self.tag_work={};self.client_pre=None
    def line_selection(self):
        need(set(self.codes)==NORMALIZATION_ROLES,'selective exact eight roles')
        need(len(set(self.codes.values()))==8,'selective duplicate code')
        need(set(self.points)=={'commit','exponential','store'} and set(self.workpoints)=={'scan','scale'},'selective missing point')
        roles={'run':tuple(self.points.values()),'work':tuple(self.workpoints.values()),'client':(self.clientpoint,),'matrix':(self.matrixpoint,),'op':(),'normalization':(),'consume':(),'tick':()}
        selected={}
        for role,points in roles.items():
            need(all(type(n) is int and n>0 for n in points) and len(set(points))==len(points),'selective duplicate/invalid point')
            selected[self.codes[role]]=frozenset(points)
        need(sum(map(len,selected.values()))==7,'selective seven points')
        return selected
    def monitor_masks(self):
        m=sys.monitoring.events
        need(self.selective_lines is True and self.normalization_contract==NORMALIZATION_CONTRACT,'normalization selective contract differs')
        need(self.normalization_sites is self._normalization_sites_source,'normalization call-site map replaced')
        need(all(self.codes[role] is code for role,code in self._normalization_role_codes),'normalization role identity drift')
        # Revalidate identities/point inventory immediately before installation.
        need(self.selected_lines==self.line_selection(),'selective point drift')
        need(self.selected_lines is self._line_selection_source,'selective point map replaced')
        need(all(self.codes[role] is code for role,code in self._line_role_codes),
             'selective role code identity drift')
        need(len(self._line_by_identity)==len(self.codes),'selective identity cache extent')
        for code in self.codes.values():
            row=self._line_by_identity.get(id(code))
            need(row is not None and row[0] is code and row[1]==self.selected_lines[code],
                 'selective identity cache drift')
        return {code:(0 if role=='op' else m.PY_RETURN|(m.LINE if self.selected_lines[code] else 0))
                for role,code in self.codes.items()}

    def context(self):
        f=sys._getframe(1)
        while f is not None:
            if f.f_code is self.codes['run'] and f.f_locals.get('self') is self.services[2]:return f.f_locals
            f=f.f_back
        g=self.owner.program
        while g is not None and hasattr(g,'gi_frame'):
            f=g.gi_frame
            if f is not None and f.f_code is self.codes['run'] and f.f_locals.get('self') is self.services[2]:return f.f_locals
            g=getattr(g,'gi_yieldfrom',None)
        raise ValueError('active original schedule frame missing')
    def bind_work(self,work):
        c=self.context();need(self.owner.ordered_work is work and work.result.service_result is self.owner.matrix.result,'live result owner differs')
        a=self.data.bind(work,c['head'],c['token'],c['first'],c['count']);self.tag_work[work.result.tag]=work
        self.client=self.owner.matrix_client.packed
        return a
    def __enter__(self):
        need(self.ast_test,'normalization production requires qualified fullgraph lease adapter')
        need(not self.closed and self.tool is None and self.owner.state=='idle' and not self.owner.poison and sys.gettrace() is None,'single-use idle observation')
        masks=self.monitor_masks()
        mon=sys.monitoring
        for tool in (3,4):
            if mon.get_tool(tool) is None and not mon.get_events(tool):self.tool=tool;break
        need(self.tool is not None,'monitor tool busy');mon.use_tool_id(self.tool,'ordered-fold-observer')
        mon.register_callback(self.tool,mon.events.LINE,self._line);mon.register_callback(self.tool,mon.events.PY_RETURN,self._return)
        for code in self.codes.values():mon.set_local_events(self.tool,code,masks[code] if isinstance(masks,dict) else masks)
        return self
    def stop(self):
        if self.tool is not None:
            m=sys.monitoring
            for code in self.codes.values():m.set_local_events(self.tool,code,0)
            m.register_callback(self.tool,m.events.LINE,None);m.register_callback(self.tool,m.events.PY_RETURN,None);m.free_tool_id(self.tool);self.tool=None
        self.closed=True
    def __exit__(self,*exc):self.stop();return False
    def fail(self,error):
        if self.error is None:self.error=type(error).__name__+': '+str(error)
        # Observation failure never substitutes a DUT value or changes a ready bit.
        self.stop()
    def _line(self,code,line):
        try:
            if self.selective_lines:
                if self.selected_lines is not self._line_selection_source:raise ValueError('selective point map replaced')
                row=self._line_by_identity.get(id(code))
                if row is None or row[0] is not code:raise ValueError('selective foreign code')
                points=row[1]
                if line not in points:return
            need(threading.get_ident()==self.thread,'observer thread changed')
            f=sys._getframe(1);a=f.f_locals;o=self.owner
            if code is self.codes['work'] and a.get('self') is self.services[3]:
                w=a['work']
                if line==self.workpoints['scan']:
                    self.bind_work(w);j=a['j'];meta=self.data.work[id(w)]
                    self.data.single('dot_parts',(meta['h'],meta['t'],meta['first']+j,w.row),(w.result.value[w.row][16*j+w.row],))
                elif line==self.workpoints['scale']:
                    self.bind_work(w);self.data.scale(w,a['j'],a['total'],a['dot'],a['score'])
            elif code is self.codes['run'] and a.get('self') is self.services[2]:
                if line==self.points['commit']:self.data.commit(a['work'],a['retired'],a['scores'])
                elif line==self.points['exponential']:
                    self.data.single('softmax_exp',(a['head'],a['token'],len(a['probabilities'])-1),(a['probability'],))
                elif line==self.points['store']:
                    c=(a['head'],a['token'],a['col']);self.data.single('pv_raw',c,tuple(a['lanes']));self.data.single('pv_bf16',c,tuple(a['output']))
            elif code is self.codes['client'] and a.get('self') is self.client and line==self.clientpoint:
                self.client_pre=a['self'].state
            elif code is self.codes['matrix'] and a.get('self') is o and line==self.matrixpoint and a['opcode']==0x24:
                c=self.context();key=(c['head'],c['token'],c['key'],c['col']);need(key in self.prob,'missing actual normalization return')
                self.data.probability(*key,self.prob.pop(key),a['a'][0]<<16)
        except Exception as error:self.fail(error)
    def _return(self,code,offset,value):
        try:
            f=sys._getframe(1);a=f.f_locals;o=self.owner
            if code is self.codes['consume'] and value is True:
                w=a['self'];need(id(w) in self.data.work,'unowned consume');self.data.consume(w,a['retired'],value)
            elif code is self.codes['normalization'] and a.get('self') is o:
                sites=self.normalization_sites
                need(sites is self._normalization_sites_source and
                     all(self.codes[role] is bound for role,bound in self._normalization_role_codes),
                     'normalization source identity drift')
                need(f.f_code is code and offset==sites['helper_return'] and f.f_lasti==offset,
                     'normalization actual helper return differs')
                caller=f.f_back
                if caller is not None and caller.f_code is self.codes['op']:
                    schedule=caller.f_back
                    if schedule is not None and schedule.f_code is self.codes['run']:
                        b=caller.f_locals;c=schedule.f_locals
                        if b.get('self') is not o or c.get('self') is not self.services[2] or c.get('o') is not o:return
                        need(caller.f_lasti==sites['op_wait'],'normalization active forwarding call differs')
                        need(all(a[name] is b[name] for name in ('operation','a','b','policy')),
                             'normalization forwarded arguments differ')
                        operation=a['operation']
                        need(type(operation) is str and operation in ('div','mul') and
                             type(a['policy']) is str and a['policy']=='legacy_scalar',
                             'normalization opcode/policy differs')
                        need(o.scalar is self.services[1] and o.scalar.client is o,'normalization scalar ownership differs')
                        need(schedule.f_lasti==sites['run_'+operation+'_wait'],'normalization active schedule call differs')
                        if operation=='div':
                            need(a['a']==0x3f800000 and a['b']==c['total'],'normalizer operands changed')
                            need(a['b'] is c['total'],'normalizer actual total forwarding differs')
                            self.data.single('normalizer',(c['head'],c['token'],0),(c['maximum'],c['total'],value))
                        else:
                            need(a['b']==c['inverse'],'probability inverse differs')
                            need(a['a'] is c['probability'] and a['b'] is c['inverse'],'probability actual operand forwarding differs')
                            key=(c['head'],c['token'],c['key'],c['col'])
                            need(key not in self.prob,'duplicate probability return');self.prob[key]=value
            elif code is self.codes['client'] and a.get('self') is self.client and isinstance(value,dict):
                if value.get('service_result_fire') or value.get('service_done_fire'):
                    client=a['self'];need(client.tag in self.tag_work,'unowned packed service retirement');w=self.tag_work[client.tag];meta=self.data.work[id(w)]
                    if value.get('service_result_fire'):
                        need(self.client_pre=='release_result' and meta['retired']==meta['count'] and not meta.get('ack'),'early/duplicate result ACK');meta['ack']=True;self.data.acks+=1
                    if value.get('service_done_fire'):
                        need(self.client_pre=='wait_done' and meta.get('ack') and not meta.get('done'),'early/duplicate done');meta['done']=True;self.data.dones+=1
                        self.data.release(w);del self.tag_work[client.tag]
            elif code is self.codes['tick'] and a.get('self') is o and isinstance(value,dict):
                if value.get('job_fire'):need(not self.started and o.job.m==self.data.rows,'wrong/duplicate job');self.started=True
                if value.get('response_fire'):
                    clean=(self.started and value['response'].status is None and o.state=='idle' and not o.poison and o.matrix.owner is None and o.scalar.client is None and o.matrix.result is None and o.matrix.done is None and not o.matrix.reset_required and o.matrix_client is None and not o.memory_pending and not o.scratch_pending and not o.scratch_leased)
                    self.data.terminal=dict(clean=clean,state=o.state,same_services=(o.matrix,o.scalar,o.packed_schedule,o.ordered_adapter)==self.services)
                    need(self.data.terminal['same_services'],'service identity changed')
        except Exception as error:self.fail(error)
    def seal(self):
        need(self.closed and self.tool is None,'monitor must stop before seal');need(self.error is None,'observer failed: '+str(self.error));need(not self.prob,'unfinished normalization observation')
        report=self.data.seal();report['execution_provenance']='AST_DEFINITION_SOFTWARE_TEST_ONLY' if self.ast_test else 'NORMAL_LOADED_SOURCE_SOFTWARE'
        report['observation_contract']=self.normalization_contract
        report['normalization_boundary']='helper_PY_RETURN_before_op_return'
        report['original_owner_bytes_unchanged']=False
        report['speculative_scale_not_committed']=True;report['observer_launches_native_or_rtl']=False
        return report
