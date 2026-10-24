"""MOCK-only observer contract test. No DUT import, native call or evidence read.
Complete sources are compiled; only exact observer CodeTypes are instantiated.
MOCK owner, service/native metadata, descriptors, frames and sinks are not admission.
"""
import argparse, ast, hashlib, json, sys, threading, types
from array import array
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
args=parser.parse_args(); BASE=args.baseline.resolve(); OLD=BASE/'narrow_fullblock_attention.py'
PINS={Path(k):v for k,v in json.loads((ROOT/'SOURCE_MANIFEST.json').read_bytes())['test_inputs'].items()}
S=types.SimpleNamespace
ATTEMPTS=Counter()
def audit(event,args):
    blocked=event.startswith(('subprocess.','ctypes.','socket.')) or event in ('os.system','os.exec','os.posix_spawn','os.spawn','os.fork','os.forkpty','pty.spawn')
    if event=='import':
        name=args[0].split('.')[0]
        blocked=blocked or name in ('ctypes','_ctypes','socket','_socket','urllib','http','requests','candidates')
    if blocked:
        ATTEMPTS[event]+=1
        raise RuntimeError('MOCK audit denied '+event)
sys.addaudithook(audit)

def need(ok,message):
    if not ok: raise ValueError(message)

def codes(root):
    yield root
    for c in root.co_consts:
        if type(c) is types.CodeType: yield from codes(c)

def load(path):
    raw=path.read_bytes(); need(hashlib.sha256(raw).hexdigest()==PINS[path],'source pin'); source=raw.decode('utf-8')
    return source,{c.co_qualname:c for c in codes(compile(source,str(path),'exec'))}

def fn(pool,name,g): return types.FunctionType(pool[name],g)

def native(lib):
    lib.calls+=1
    return lib.kind,{}, {}, {'MOCK_ABI':lib.abi}

MOCK='''
def _op(self, mode='normal'):
    if mode == 'throw': raise BOOM
    if mode == 'handled':
        try: raise BOOM
        except ValueError: pass
    return 7
def _attention(self):
    head = token = 0
    return self._op('normal')
def outer(self, mode='normal'):
    value = self._op(mode)
    return {'result_fire': True, 'value': value}
def tick(self, mode='normal'):
    value = 0
    for index in range(4):
        value += self.outer(mode)['value']
    return value
def unused(self): return None
'''
MC={c.co_name:c for c in codes(compile(MOCK,'<MOCK_ONLY>','exec'))}
OTHER=next(c for c in codes(compile('def _attention(self): pass','<MOCK_SAME_NAME>','exec')) if c.co_name=='_attention')

def attention(pool):
    g={'require':need,'threading':threading,'types':types,'sys':sys,'asdict':lambda p:dict(vars(p)),
       'native_snapshot':native,'array':array,'SENTINEL':0xdeadbeef}
    clients=S(Fixed93MatrixClient=type('Fixed93MatrixClient',(),{}),PackedQkClient=type('PackedQkClient',(),{}))
    matrix=S(LegacyMatrixClient=type('LegacyMatrixClient',(),{}))
    g['CLIENT_MODULE']='MOCK_CLIENT';g['MATRIX_MODULE']='MOCK_MATRIX'
    g['sys']=S(modules={'MOCK_CLIENT':clients,'MOCK_MATRIX':matrix},gettrace=sys.gettrace,settrace=sys.settrace)
    names=('_trace','_identity','_scalar','_line','_put','_event','_fence_event','_context')
    names += tuple(n for n in ('_cheap_identity','_integrity','__exit__') if 'Fixed93FullblockAttentionObservation.'+n in pool)
    attrs={n:fn(pool,'Fixed93FullblockAttentionObservation.'+n,g) for n in names}
    attrs['_h_t_k']=staticmethod(fn(pool,'Fixed93FullblockAttentionObservation._h_t_k',g))
    cls=type('MOCKAttention',(),attrs); a=cls(); boom=ValueError('MOCK original exception')
    owner_cls=type('MOCKOwner',(),{n:types.FunctionType(MC[n],{'BOOM':boom}) for n in ('_op','_attention','outer','tick')})
    owner=owner_cls(); owner.clock=123; owner.matrix_client=None
    lib=S(calls=0,kind=object(),abi=1); profile=S(width=1)
    owner.matrix=S(lib=lib,resource_address=0,profile=profile,_bindings={}); owner.scalar=object()
    a.owner=owner; a.services=(owner.matrix,owner.scalar); a.library=lib; a.resource_address=0
    a.profile=profile; a.profile_snapshot={'width':1}; a.binding_snapshot={}
    a.native_type=lib.kind; a.native_type_members={}; a.native_functions={}; a.native_signatures={'MOCK_ABI':1}
    a.mock_clients=clients;a.mock_matrix=matrix
    a.job_object=None; a.thread=threading.get_ident(); a.client_identity=None; a.identity_tick_frame=None
    a.codes={n:MC[n] if n in MC else MC['unused'] for n in ('_op','_attention','_matrix_step','_write','tick','_fault','_finish','packed_tick','packed_commit')}
    a.all_codes=frozenset((MC['_op'],MC['_attention'],MC['outer'],MC['tick']))
    a.scalar_code=a.exp_code=a.ticket_code=a.legacy_code=MC['unused']; a.service_codes={}
    a.disarmed=False; a.error=None; a.started=1; a.job={'m':1}; a.fold_coord=None; a.fold_index=0
    a.event_counts=Counter(); a.pending_normalization=None; a.normalization_reuse_count=0
    a.line={n:i+1000 for i,n in enumerate(('fold','dot','scale','denominator','inverse','normalize','qk_check','qk_pass','score','exp','output'))}
    a.line.update({n:-1000 for n in ('memory_accept','memory_match','write_ack','store_check','store_pass')})
    shapes=fn(pool,'field_shapes',g)(1)
    a.fields={}
    for name,shape in shapes.items():
        count=1
        for x in shape: count*=x
        a.fields[name]={'shape':shape,'words':array('I',[0xdeadbeef])*count,'frequency':bytearray(count)}
    a.records=[]; a.stream=S(failed=False,emit=lambda *x:a.records.append(x))
    a._callback=a._trace
    return a,boom

def whole(pool,a):
    g={'need':need,'types':types,'sys':sys,'threading':threading,'CaptureError':ValueError,
       'SUPPORT_ANCHORS':frozenset(('owner_attention','owner_matrix_step','owner_write','owner_tick','scalar_op','exp_negative','jsonable'))}
    attrs={n:fn(pool,'TraceDispatcher.'+n,g) for n in ('__init__','register','unregister','start','_dispatch','stop')}
    D=type('RealDispatcher',(),attrs)
    W=type('RealListener',(),{n:fn(pool,'WholeblockObservation.'+n,g) for n in ('_observe','_belongs')})
    w=W(); w.by_code={MC['_attention']:'owner_attention',MC['outer']:'public_MOCK',MC['tick']:'owner_tick'}; w.op_events=[]
    w.objects={'x':a.owner}; w.limits={'max_exception_frames':8}; w._exceptions=set(); w.records=[]; w.failure=None
    w._event=lambda key,frame,values:w.records.append((key,values))
    w._poison=lambda value:setattr(w,'failure',w.failure or value)
    d=D(a.all_codes,max_listeners=3,on_error=w._poison,line_codes=(MC['tick'],),scalar_code=None,exp_code=None,max_exception_frames=8)
    d.register(a._callback,a.all_codes); d.register(w._observe,w.by_code)
    # Test-only third subscriber; production wholeblock does NOT bind _op.
    d.register(lambda f,e,x:w.op_events.append(e),[MC['_op']])
    return d,w

def frame(observer,caller=None,**local):
    return S(f_code=MC['_op'],f_back=caller,f_locals={'self':observer.owner,**local},f_lineno=1,f_trace_lines=False)

def snapshot(a,w=None):
    return (a.error,a.records,dict(a.event_counts),[(k,tuple(v['words']),bytes(v['frequency'])) for k,v in a.fields.items()],
            None if w is None else (w.records,w.failure,w.op_events))

def retained(pool,wholepool):
    a,_=attention(pool); d,w=whole(wholepool,a)
    c=S(f_code=MC['_attention'],f_back=None,f_locals={'self':a.owner,'head':0,'token':0,'key':0,'col':0,'probabilities':[9],'maximum':3,'total':4})
    f=frame(a,c,operation='add',a=1,b=2)
    for label in ('fold',)*16+('dot','scale','scale','denominator','inverse','normalize'):
        c.f_lineno=a.line[label]
        f.f_locals['operation']='mul' if label in ('normalize','scale') else 'add'
        if label=='scale' and a.fields['scale_fp32']['frequency'][0]: f.f_locals['operation']='bf'
        d._dispatch(f,'call',None); d._dispatch(f,'return',9)
    need(a.error is None,'retained scalar path failed'); need(a.pending_normalization==((0,0,0),9),'normalization fence')
    need(sum(sum(x['frequency']) for x in a.fields.values())==40,'six scalar consumers/fields')
    need(len(d._listeners)==3 and d.failed is None,'composition changed')
    return snapshot(a,w)

def ordinary(pool,wholepool):
    a,_=attention(pool); d,w=whole(wholepool,a)
    for caller in (None,S(f_code=MC['outer']),S(f_code=OTHER)):
        f=frame(a,caller)
        for event,arg in (('call',None),('return',7),('return',None)):
            need(d._dispatch(f,event,arg) is d.callback,'dispatcher callback')
    f=S(f_code=MC['outer'],f_locals={'self':a.owner},f_back=None,f_lineno=1,f_trace_lines=False)
    d._dispatch(f,'return',{'result_fire':True})
    need(len(d._listeners)==3 and len(w.records)==1 and d.failed is None,'second listener lost')
    need(a.error is None and not a.records,'no-evidence normal callback')
    return snapshot(a,w),a.library.calls

def errors(pool,wholepool):
    results=[]
    a,_=attention(pool); f=frame(a); f.f_code=OTHER
    need(a._trace(f,'call',None) is None,'unknown code must not attach')
    f=frame(a)
    for event in ('line','MOCK_UNKNOWN'): a._trace(f,event,None)
    need(a.library.calls==2 and a.error is None,'non-call/return must retain identity')
    for bad in ('owner','thread'):
        a,_=attention(pool); f=frame(a)
        if bad=='owner': f.f_locals['self']=object()
        else: a.thread=-1
        need(a._trace(f,'call',None) is a._callback,'observer injected error')
        first=a.error; need(first is not None,'missing rejection')
        a._trace(f,'return',7); need(a.error==first,'not sticky'); results.append(first)
    for flag in ('disarmed','failed'):
        a,_=attention(pool); f=frame(a,self=object())
        if flag=='disarmed': a.disarmed=True
        else: a.stream.failed=True
        a.thread=-1; a._trace(f,'call',None)
        need(a.error is None and a.library.calls==0,'prior short circuit changed')
    for kind in (StopIteration,GeneratorExit):
        a,_=attention(pool); a._trace(frame(a),'exception',(kind,kind(),None))
        need(a.error is None and not a.records and a.library.calls==1,'control exception path')
    a,boom=attention(pool); d,w=whole(wholepool,a); f=frame(a); f.f_code=MC['outer']
    d._dispatch(f,'exception',(ValueError,boom,None))
    need(f.f_trace_lines and id(f) in d._resume_lines and id(f) in w._exceptions,'resume missing')
    d._dispatch(f,'line',None)
    need(not f.f_trace_lines and not d._resume_lines and not w._exceptions,'first resume line not cleared')
    d._dispatch(f,'return',7)
    need(w.failure is None and a.error and a.records,'handled exception semantics')
    a,boom=attention(pool); d,w=whole(wholepool,a); f=frame(a); f.f_code=MC['outer']
    d._dispatch(f,'exception',(ValueError,boom,None)); d._dispatch(f,'return',None)
    need(not d._resume_lines and not w._exceptions and w.failure,'unwinding exception debt/poison')
    return results

def drift(pool,kept):
    out=[]
    for kind in ('abi','profile'):
        a,_=attention(pool); f=frame(a)
        target=a.library if kind=='abi' else a.profile; attr='abi' if kind=='abi' else 'width'
        setattr(target,attr,2); a._trace(f,'call',None); a._trace(f,'return',7)
        if kept: a._trace(f,'line',None)
        setattr(target,attr,1); a._trace(f,'line',None)
        out.append(a.error)
    return out

def real_trace(pool,wholepool,mode):
    a,boom=attention(pool); d,w=whole(wholepool,a); original=None; result=None
    d.start()
    try:
        try: result=a.owner.outer(mode)
        except ValueError as e: original=e
    finally: d.stop()
    need(sys.gettrace() is None and d.failed is None and len(d._listeners)==3,'trace lifecycle')
    need(not d._resume_lines and not w._exceptions,'exception debt')
    if mode=='throw': need(original is boom and w.failure and a.error,'original exception/poison')
    else:
        need(result=={'result_fire':True,'value':7} and w.failure is None,'original return/handled exception')
        need(bool(a.error)==(mode=='handled'),'attention exception latch')
    return snapshot(a,w),result,original is boom

def priority(pool):
    a,_=attention(pool); a.library.abi=2; a._trace(frame(a,self=object()),'call',None); return a.error


def tick_frame(a):
    return S(f_code=MC['tick'],f_locals={'self':a.owner},f_back=None,f_lineno=1,f_trace_lines=False)

def inner_frame(a,t):
    return S(f_code=MC['outer'],f_locals={'self':a.owner},f_back=t,f_lineno=1,f_trace_lines=False)

def within_retained(pool,wp):
    a,_=attention(pool); d,w=whole(wp,a); t=tick_frame(a)
    d._dispatch(t,'call',None)
    c=S(f_code=MC['_attention'],f_back=t,f_locals={'self':a.owner,'head':0,'token':0,'key':0,'col':0,'probabilities':[9],'maximum':3,'total':4})
    f=frame(a,c,operation='add',a=1,b=2)
    for label in ('fold',)*16+('dot','scale','scale','denominator','inverse','normalize'):
        c.f_lineno=a.line[label]; f.f_locals['operation']='mul' if label in ('normalize','scale') else 'add'
        if label=='scale' and a.fields['scale_fp32']['frequency'][0]: f.f_locals['operation']='bf'
        d._dispatch(f,'call',None); d._dispatch(f,'return',9)
    d._dispatch(t,'return',7)
    need(a.error is None and a.identity_tick_frame is None,'retained tick scope')
    need(sum(sum(x['frequency']) for x in a.fields.values())==40,'six consumers unchanged')
    return snapshot(a,w),a.library.calls

def boundaries(pool):
    a,_=attention(pool); t=tick_frame(a); f=inner_frame(a,t)
    a._trace(t,'call',None); need(a.library.calls==1 and a.identity_tick_frame==id(t),'full entry')
    a._trace(t,'line',None); a._trace(f,'call',None); a._trace(f,'return',7)
    need(a.library.calls==1 and a.error is None,'normal inside must cheap')
    a._trace(f,'exception',(StopIteration,StopIteration(),None));need(a.library.calls==2,'exception full')
    need(a.identity_tick_frame==id(t),'handled exception prematurely closed scope')
    a._trace(f,'MOCK_UNKNOWN',None);need(a.library.calls==3,'unknown event full')
    a._trace(t,'return',None);need(a.library.calls==4 and a.identity_tick_frame is None,'None return full/close')
    a._trace(inner_frame(a,None),'call',None);need(a.library.calls==5,'outside full')
    # Bootstrap remains full before _start, even inside the tick.
    a,_=attention(pool); t=tick_frame(a);a._trace(t,'call',None);a.started=0;order=[]
    a._start=lambda:(order.append(a.library.calls),setattr(a,'started',1))
    f=inner_frame(a,t);f.f_code=MC['_attention'];a._trace(f,'call',None)
    need(order==[2] and a.error is None,'bootstrap check before original start position')
    a._trace(t,'return',None)
    return 8

def lifecycle(pool):
    cases=0
    for bad in ('reentry','wrong_return','missing_call','detached','depth'):
        a,_=attention(pool); t=tick_frame(a)
        if bad!='missing_call':a._trace(t,'call',None)
        other=tick_frame(a)
        if bad=='reentry':a._trace(other,'call',None)
        elif bad in ('wrong_return','missing_call'):a._trace(other,'return',None)
        else:
            f=inner_frame(a,None)
            if bad=='depth':
                back=t
                for _ in range(130):back=S(f_back=back)
                f.f_back=back
            a._trace(f,'call',None)
        need(a.error is not None,'missing boundary rejection '+bad);first=a.error
        if bad!='missing_call':need(a.identity_tick_frame==id(t),'wrong frame cleared outer')
        a._trace(t,'return',None)
        need(a.identity_tick_frame is None and a.error==first,'scope close/sticky '+bad)
        cases+=1
    # Existing validation and close still run when a missing return is discovered.
    a,_=attention(pool);t=tick_frame(a);a._trace(t,'call',None);events=[]
    a.dispatcher=None;a._trace_intact=lambda:True;a._validate=lambda:events.append('validate')
    a.stream.close=lambda:events.append('close') or 'MOCK_SEAL';a.active=True;a.closed=False
    need(a.__exit__(None,None,None) is False,'exit replaced result')
    need(a.error and events==['validate','close'] and a.closed and a.identity_tick_frame is None,'missing return failed to close resources');cases+=1
    for bad in ('identity','tick','disarmed','stream_failed','terminal'):
        a,_=attention(pool);t=tick_frame(a);a._trace(t,'call',None)
        if bad=='identity':a.library.abi=2
        if bad=='tick':a._tick=lambda *x:(_ for _ in ()).throw(ValueError('MOCK _tick failure'))
        if bad=='terminal':a._tick=lambda *x:setattr(a,'disarmed',True)
        if bad=='disarmed':a.disarmed=True
        if bad=='stream_failed':a.stream.failed=True
        a._trace(t,'return',{} if bad in ('tick','terminal') else None)
        need(a.identity_tick_frame is None,'return cleanup '+bad)
        need(bool(a.error)==(bad in ('identity','tick')),'return latch '+bad);cases+=1
    return cases

def cheap_guards(pool):
    cases=0
    for bad in ('thread','matrix','scalar','library','address','profile_object','binding_key','binding_object','job','client_type'):
        a,_=attention(pool);t=tick_frame(a);a._trace(t,'call',None)
        if bad=='thread':a.thread=-1
        elif bad=='matrix':a.owner.matrix=object()
        elif bad=='scalar':a.owner.scalar=object()
        elif bad=='library':a.owner.matrix.lib=object()
        elif bad=='address':a.owner.matrix.resource_address=1
        elif bad=='profile_object':a.owner.matrix.profile=S(width=1)
        elif bad=='binding_key':a.owner.matrix._bindings['x']=object()
        elif bad=='binding_object':
            a.binding_snapshot={'x':object()};a.owner.matrix._bindings={'x':object()}
        elif bad=='job':a.job_object=object();a.owner.job=object()
        else:a.owner.matrix_client=object()
        a._trace(inner_frame(a,t),'call',None)
        need(a.error is not None,'cheap identity missed '+bad);cases+=1
    # Exact real client predicates, with disclosed synthetic class identities.
    for bad in ('none','client_type','packed_type','legacy_type','client_service','packed_service','legacy_service','packed_owner','legacy_owner','replacement'):
        a,_=attention(pool)
        def make_client():
            c=a.mock_clients.Fixed93MatrixClient();c.service=a.services[0]
            c.packed=a.mock_clients.PackedQkClient();c.legacy=a.mock_matrix.LegacyMatrixClient()
            for x in (c.packed,c.legacy):x.owner=a.owner;x.service=a.services[0]
            return c
        a.owner.matrix_client=make_client();t=tick_frame(a);a._trace(t,'call',None)
        c=a.owner.matrix_client
        if bad=='client_type':a.owner.matrix_client=S(service=c.service,packed=c.packed,legacy=c.legacy)
        elif bad=='packed_type':c.packed=S(owner=a.owner,service=a.services[0])
        elif bad=='legacy_type':c.legacy=S(owner=a.owner,service=a.services[0])
        elif bad=='client_service':c.service=object()
        elif bad=='packed_service':c.packed.service=object()
        elif bad=='legacy_service':c.legacy.service=object()
        elif bad=='packed_owner':c.packed.owner=object()
        elif bad=='legacy_owner':c.legacy.owner=object()
        elif bad=='replacement':a.owner.matrix_client=make_client()
        a._trace(inner_frame(a,t),'call',None)
        need(bool(a.error)==(bad!='none'),'exact client guard '+bad);cases+=1
    # No added bindings-dict object identity: exact original key/object semantics.
    a,_=attention(pool);item=object();a.binding_snapshot={'x':item};a.owner.matrix._bindings={'x':item}
    t=tick_frame(a);a._trace(t,'call',None);a.owner.matrix._bindings={'x':item}
    a._trace(inner_frame(a,t),'call',None);a._trace(t,'return',None)
    need(a.error is None,'new bindings dictionary identity requirement');cases+=1
    return cases

def metadata_drift(old,new):
    cases=0
    for kind in ('abi','profile'):
        for persistent in (False,True):
            results=[]
            for pool in (old,new):
                a,_=attention(pool);t=tick_frame(a);a._trace(t,'call',None)
                target=a.library if kind=='abi' else a.profile;attr='abi' if kind=='abi' else 'width'
                setattr(target,attr,2);a._trace(inner_frame(a,t),'call',None)
                if not persistent:setattr(target,attr,1)
                a._trace(t,'return',None);results.append(a.error)
            need(results[0] is not None and bool(results[1])==persistent,'declared transient/persistent boundary')
            cases+=1
        # A failed full exception check prevents later cheap sampling in this tick.
        a,_=attention(new);t=tick_frame(a);a._trace(t,'call',None);a.library.abi=2
        f=inner_frame(a,t);a._trace(f,'exception',(StopIteration,StopIteration(),None));first=a.error
        need(first is not None,'full exception failed to latch');a.library.abi=1;before=a.library.calls
        a._trace(f,'call',None);need(a.library.calls==before+1 and a.error==first,'cheap after full failure')
        a._trace(t,'return',None);need(a.identity_tick_frame is None,'failed tick cleanup');cases+=1
    return cases

def real_ticks(pool,wp,mode,iterations=1):
    a,boom=attention(pool);d,w=whole(wp,a);caught=None;returns=[]
    d.start()
    try:
        try:
            for _ in range(iterations):returns.append(a.owner.tick(mode))
        except ValueError as exc:caught=exc
    finally:d.stop()
    need(sys.gettrace() is None and d.failed is None and not d._resume_lines and not w._exceptions,'real shared dispatcher exception/stop')
    need(a.identity_tick_frame is None,'real tick scope leak')
    if mode=='throw':need(caught is boom and a.error and w.failure,'exception original identity/poison')
    else:need(returns==[28]*iterations and caught is None and bool(a.error)==(mode=='handled'),'real return/handled error')
    return snapshot(a,w),returns,caught is boom,a.library.calls


# The following fixture adds all four distinct owner CodeTypes without executing
# model bodies. The constructor table AST is executed literally from new source.
EXTRA={c.co_name:c for c in codes(compile('def _matrix_step(self): pass\ndef _write(self): pass','<MOCK_OWNER_LINES>','exec'))}
MC.update(EXTRA)
GROUPS={'_attention':('qk_check','qk_pass','score','exp','output'),
 '_matrix_step':('matrix_input_fp32','matrix_input','pv_check','pv_pass'),
 'tick':('memory_accept','memory_match','write_ack'),'_write':('store_check','store_pass')}
TABLE_CODE=None
_old_attention=attention

def attention(pool):
    a,boom=_old_attention(pool)
    a.all_codes=frozenset((*a.all_codes,MC['_matrix_step'],MC['_write']))
    for index,name in enumerate(name for names in GROUPS.values() for name in names):a.line[name]=2000+index
    exec(TABLE_CODE,{'self':a,'types':types,'frozenset':frozenset,'require':need,'sum':sum,'map':map,'len':len})
    return a,boom

def source_proof(old,new):
    a,b=ast.parse(old),ast.parse(new)
    ac=next(n for n in a.body if isinstance(n,ast.ClassDef) and n.name=='Fixed93FullblockAttentionObservation')
    bc=next(n for n in b.body if isinstance(n,ast.ClassDef) and n.name==ac.name)
    am={n.name:n for n in ac.body if isinstance(n,ast.FunctionDef)}
    bm={n.name:n for n in bc.body if isinstance(n,ast.FunctionDef)}
    need(am.keys()==bm.keys(),'method set changed')
    changed={n for n in am if ast.dump(am[n])!=ast.dump(bm[n])}
    need(changed=={'__init__','_trace'},'unexpected source delta')
    init=bm['__init__']; nodes=init.body[-2:]
    need(isinstance(nodes[0],ast.Assign) and nodes[0].targets[0].attr=='evidence_lines','constructor table placement')
    need(isinstance(nodes[1],ast.Expr) and nodes[1].value.func.id=='require','table assertion')
    global TABLE_CODE
    TABLE_CODE=compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'<EXACT_NEW_CONSTRUCTOR_TABLE>','exec')
    del init.body[-2:]
    trace=bm['_trace']; tr=next(n for n in trace.body if isinstance(n,ast.Try))
    matches=[n for n in tr.body if isinstance(n,ast.If) and 'self.evidence_lines' in ast.unparse(n.test)]
    need(len(matches)==1,'one new listener selector');tr.body.remove(matches[0])
    need(ast.dump(a)==ast.dump(b),'whole-module reverse AST mismatch')
    for name in am.keys()-changed:
        need(ast.get_source_segment(old,am[name])==ast.get_source_segment(new,bm[name]),'unchanged method bytes '+name)
    return sorted(changed),len(am)-len(changed)

def setup(pool,wp):
    a,_=attention(pool);d,w=whole(wp,a)
    # Rebuild the same real dispatcher with the original real wholeblock listener
    # and an extra TEST-ONLY listener subscribed to every owner line.
    D=type(d); seen=[]
    w.by_code.update({MC[n]:'owner_'+n.strip('_') for n in GROUPS})
    w.by_code[MC['_matrix_step']]='owner_matrix_step';w.by_code[MC['_write']]='owner_write'
    d=D(a.all_codes,max_listeners=3,on_error=w._poison,line_codes=tuple(MC[n] for n in GROUPS),scalar_code=None,exp_code=None,max_exception_frames=8)
    d.register(a._callback,a.all_codes);d.register(w._observe,w.by_code)
    d.register(lambda f,e,x:seen.append((f.f_code.co_name,e,f.f_lineno)),a.all_codes)
    return a,d,w,seen

def client(a):
    c=a.mock_clients.Fixed93MatrixClient();c.service=a.services[0]
    c.packed=a.mock_clients.PackedQkClient();c.legacy=a.mock_matrix.LegacyMatrixClient()
    for x in (c.packed,c.legacy):x.owner=a.owner;x.service=a.services[0]
    c.packed.tag=7;a.owner.matrix_client=c

def line_frame(a,t,name,line):
    ctx=S(f_code=MC['_attention'],f_locals={'self':a.owner,'head':0,'token':0,'key':0,'col':0},f_back=t,f_lineno=-5,f_trace_lines=False)
    f=S(f_code=MC[name],f_locals={'self':a.owner},f_back=ctx,f_lineno=line,f_trace_lines=False)
    if name=='_attention':f.f_back=t;f.f_locals.update(head=0,token=0,key=0,col=0)
    if name=='tick':f=t;f.f_lineno=line
    if name=='_matrix_step':f.f_locals.update(opcode=0x24,col=0,a=(9,)*16,lanes=(3,)*16)
    return f,ctx

def hook_one(pool,wp,name,label):
    a,d,w,seen=setup(pool,wp);client(a);t=tick_frame(a);d._dispatch(t,'call',None)
    f,ctx=line_frame(a,t,name,a.line[label])
    f.f_locals.update(lanes=(3,)*16,output=(4,)*16,probabilities=[],difference=5,probability=6,words=(7,)*16,address=4096)
    a.pending_normalization=((0,0,0),9)
    a.lease={'tag':7,'state':'borrowed','scores':0,'count':1}
    q=S(tag=2,address=4096,write=False,mask=0xffff,data=b'\x00'*64)
    r=S(tag=2,error=False,data=b'\x01'*64,nbytes=64)
    a.owner.request=q;a.owner.ack_bytes=64;a.pending_memory=None;a.last_memory_tag=-1
    if label in ('memory_match','write_ack'):a.pending_memory=(2,4096,False)
    f.f_locals.update(q=q,r=r)
    d._dispatch(f,'line',None);d._dispatch(t,'return',None)
    need(a.error is None and a.identity_tick_frame is None and w.failure is None,'hook failed '+label+':'+str(a.error))
    need(len(seen)==3 and seen[1][1]=='line','other subscriber lost hook')
    return snapshot(a,w),seen,a.library.calls

def all_hooks(oc,nc,wp):
    result=[]
    for name,labels in GROUPS.items():
        for label in labels:
            x=hook_one(oc,wp,name,label);y=hook_one(nc,wp,name,label)
            need(x==y,'hook fields/events differ '+label);result.append({'label':label,'events':len(x[0][1]),'field_slots':sum(sum(v[2]) for v in x[0][3])})
    return result

def nonhooks(oc,nc,wp):
    count=0
    for pool in (oc,nc):
        for name in GROUPS:
            a,d,w,seen=setup(pool,wp);t=tick_frame(a);d._dispatch(t,'call',None)
            f,_=line_frame(a,t,name,-50);before=snapshot(a,w)
            d._dispatch(f,'line',None)
            need(snapshot(a,w)==before,'nonhook produced evidence '+name)
            need(seen[-1]==(MC[name].co_name,'line',-50),'other subscriber lost nonhook')
            d._dispatch(t,'return',None);need(a.error is None and a.identity_tick_frame is None,'nonhook scope');count+=1
    return count

def local_drift(oc,nc,wp):
    out=[]
    for bad in ('opcode','col_type','col_range','col_align','causal','context'):
        for persistent in (False,True):
            found=[]
            for pool in (oc,nc):
                a,d,w,seen=setup(pool,wp);t=tick_frame(a);d._dispatch(t,'call',None)
                f,ctx=line_frame(a,t,'_matrix_step',-50);original=dict(f.f_locals);prior=dict(ctx.f_locals)
                if bad=='opcode':f.f_locals['opcode']=0
                if bad=='col_type':ctx.f_locals['col']=True
                if bad=='col_range':ctx.f_locals['col']=128
                if bad=='col_align':ctx.f_locals['col']=1
                if bad=='causal':ctx.f_locals['key']=1
                if bad=='context':f.f_back=t
                d._dispatch(f,'line',None);early=a.error
                if not persistent:f.f_locals=original;ctx.f_locals=prior;f.f_back=ctx
                f.f_lineno=a.line['pv_pass'];d._dispatch(f,'line',None)
                d._dispatch(t,'return',None)
                need(a.identity_tick_frame is None,'local drift leaked scope')
                found.append((early is not None,a.error is not None))
            need(found[0]==(True,True) and found[1]==(False,persistent),'declared local sampling difference '+bad)
            out.append({'kind':bad,'persistent':persistent,'old':found[0],'new':found[1]})
    # Cheap identity mutation only on a skipped line, restored before a hook.
    for bad in ('matrix','profile_object','binding'):
        found=[]
        for pool in (oc,nc):
            a,d,w,seen=setup(pool,wp);t=tick_frame(a);d._dispatch(t,'call',None)
            f,_=line_frame(a,t,'_attention',-50);m=a.owner.matrix;p=m.profile
            if bad=='matrix':a.owner.matrix=object()
            elif bad=='profile_object':m.profile=object()
            else:m._bindings['extra']=object()
            d._dispatch(f,'line',None)
            a.owner.matrix=m;m.profile=p;m._bindings={}
            f.f_lineno=a.line['qk_pass'];d._dispatch(f,'line',None);d._dispatch(t,'return',None)
            found.append(a.error is not None)
        need(found==[True,False],'transient cheap identity contract '+bad)
        out.append({'kind':bad,'old_rejected':True,'new_rejected':False})
    return out

def guards(nc,wp):
    cases=[]
    for bad in ('thread','owner','wrong_tick','detached','depth'):
        a,d,w,seen=setup(nc,wp);t=tick_frame(a);d._dispatch(t,'call',None)
        f,_=line_frame(a,t,'_attention',-50)
        if bad=='thread':a.thread=-1
        if bad=='owner':f.f_locals['self']=object()
        if bad=='wrong_tick':f=tick_frame(a);f.f_lineno=-50;f.f_back=t
        if bad=='detached':f.f_back=None
        if bad=='depth':
            back=t
            for _ in range(130):back=S(f_back=back)
            f.f_back=back
        need(a._trace(f,'line',None) is a._callback,'guard escaped into model')
        first=a.error;need(first is not None,'missed guard '+bad)
        a.thread=threading.get_ident();before=a.library.calls
        good,_=line_frame(a,t,'_attention',-50);a._trace(good,'line',None)
        need(a.library.calls==before+1 and a.error==first,'sticky failure still skipped identity')
        a._trace(t,'return',None);need(a.identity_tick_frame is None,'guard cleanup');cases.append(bad)
    a,d,w,seen=setup(nc,wp);f,_=line_frame(a,None,'_matrix_step',-50);f.f_locals['opcode']=0
    a._trace(f,'line',None);need(a.error and a.library.calls==1,'outside-tick line filtered');cases.append('outside_tick')
    return cases

def real_dispatch(pool,wp,mode,iterations=1):
    a,d,w,seen=setup(pool,wp);caught=None;values=[]
    d.start()
    try:
        try:
            for _ in range(iterations):values.append(a.owner.tick(mode))
        except ValueError as e:caught=e
    finally:d.stop()
    need(sys.gettrace() is None and not d._resume_lines and not w._exceptions and d.failed is None,'real resume/dispatcher')
    need(a.identity_tick_frame is None,'real scope leak')
    need(bool(a.error)==(mode!='normal'),'real exception latch')
    return snapshot(a,w),seen,values,None if caught is None else str(caught),a.library.calls

def main():
    import time,statistics
    start=time.monotonic();old,oc=load(OLD);new,nc=load(ROOT/'overlay/narrow_fullblock_attention.py');_,wp=load(BASE/'cached_wholeblock.py')
    changed,unchanged=source_proof(old,new)
    hooks=all_hooks(oc,nc,wp);nh=nonhooks(oc,nc,wp);drifts=local_drift(oc,nc,wp);guard=guards(nc,wp)
    need(retained(oc,wp)==retained(nc,wp),'outside scalar six anchors')
    need(within_retained(oc,wp)==within_retained(nc,wp),'inside scalar six anchors/40 slots')
    need(ordinary(oc,wp)==ordinary(nc,wp),'original op exemption changed')
    need(errors(oc,wp)==errors(nc,wp),'exception recovery changed')
    need(boundaries(oc)==boundaries(nc),'call/return/unknown/exception boundaries')
    need(lifecycle(oc)==lifecycle(nc),'reentry/missing call/return/disarm/close')
    need(cheap_guards(oc)==cheap_guards(nc),'retained cheap guards')
    for mode in ('normal','handled','throw'):
        need(real_dispatch(oc,wp,mode)==real_dispatch(nc,wp,mode),'real dispatcher events/exception '+mode)
    samples=[]
    for _ in range(3):
        t=time.process_time_ns();x=real_dispatch(oc,wp,'normal',400);a=time.process_time_ns()-t
        t=time.process_time_ns();y=real_dispatch(nc,wp,'normal',400);b=time.process_time_ns()-t
        need(x==y,'benchmark evidence/other listeners changed')
        samples.append({'old_cpu_ns':a,'new_cpu_ns':b,'full_checks_each':x[-1],'other_listener_lines':sum(e=='line' for _,e,_ in x[1])})
    need(not ATTEMPTS and 'ctypes' not in sys.modules,'forbidden operation')
    print(json.dumps({'status':'PASS_EVENT_ONLY_OWNER_LINES_SOURCE_SYNTHETIC_ONLY','policy':'event-only-owner-lines-v1',
      'changed_methods':changed,'unchanged_methods':unchanged,'hook_results':hooks,'nonhook_cases':nh,'local_and_identity_drift':drifts,
      'guards':guard,'scalar_anchors':6,'scalar_field_slots':40,'real_dispatcher_other_listener_events_identical':True,
      'matrix_hook_original_checks_unchanged':True,'exception_resume_and_tick_lifecycle_unchanged':True,
      'scope':'Original observer/dispatcher/whole listener CodeTypes, synthetic owner/service/profile/native metadata, frame locals and sink. No model/native import or computation.',
      'old_integrity_sampling_equivalent':False,'all_48_domains_executed':False,'M128_executed':False,'actual_authorized':False,
      'benchmark':samples,'synthetic_median_ratio':statistics.median(x['old_cpu_ns'] for x in samples)/statistics.median(x['new_cpu_ns'] for x in samples),
      'wall_seconds':time.monotonic()-start,'forbidden_attempts':dict(ATTEMPTS)},sort_keys=True))

if __name__=='__main__':main()
