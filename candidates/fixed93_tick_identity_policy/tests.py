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

def source_proof(old,new):
    a,b=ast.parse(old),ast.parse(new);oldcls=next(x for x in a.body if isinstance(x,ast.ClassDef) and x.name=='Fixed93FullblockAttentionObservation')
    newcls=next(x for x in b.body if isinstance(x,ast.ClassDef) and x.name==oldcls.name)
    oldmethods={x.name:x for x in oldcls.body if isinstance(x,ast.FunctionDef)};newmethods={x.name:x for x in newcls.body if isinstance(x,ast.FunctionDef)}
    need(set(newmethods)-set(oldmethods)=={'_cheap_identity','_integrity'},'unexpected new method')
    changed={n for n in oldmethods if ast.dump(oldmethods[n])!=ast.dump(newmethods[n])}
    need(changed=={'__init__','__exit__','_trace'},'evidence helper changed')
    need(ast.get_source_segment(old,oldmethods['_identity'])==ast.get_source_segment(new,newmethods['_identity']),'original full identity changed')
    # Reverse only the declared statements, then compare the entire module.
    for name in ('_cheap_identity','_integrity'):newcls.body.remove(newmethods[name])
    init=newmethods['__init__'];found=[]
    for node in list(init.body):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='identity_tick_frame' for t in node.targets):
            found.append(node);init.body.remove(node)
    need(len(found)==1,'constructor scope assignment')
    exit_method=newmethods['__exit__'];found=[]
    for node in list(exit_method.body):
        if isinstance(node,ast.If) and ast.dump(node.test)==ast.dump(ast.parse('self.identity_tick_frame is not None',mode='eval').body):
            found.append(node);exit_method.body.remove(node)
    need(len(found)==1,'close open scope latch')
    trace=newmethods['_trace'];found=[]
    for node in list(trace.body):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='closing_tick' for t in node.targets):
            found.append(node);trace.body.remove(node)
        if isinstance(node,ast.If) and isinstance(node.test,ast.BoolOp) and any(isinstance(x,ast.Attribute) and x.attr=='disarmed' for x in node.test.values):
            need(isinstance(node.body[0],ast.If) and isinstance(node.body[0].test,ast.Name) and node.body[0].test.id=='closing_tick','matching early close');node.body.pop(0)
        if isinstance(node,ast.Try):
            need(len(node.finalbody)==1 and isinstance(node.finalbody[0],ast.If) and node.finalbody[0].test.id=='closing_tick','matching finally close')
            node.finalbody=[]
            calls=[x for x in node.body if isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='_integrity']
            need(len(calls)==1,'identity selector only once')
            calls[0].value.func.attr='_identity';calls[0].value.args=[]
    need(len(found)==1 and ast.dump(a)==ast.dump(b),'non-contract AST change')
    cheap=ast.parse(ast.get_source_segment(new,newmethods['_cheap_identity']))
    need('native_snapshot' not in ast.get_source_segment(new,newmethods['_cheap_identity']) and 'asdict' not in ast.get_source_segment(new,newmethods['_cheap_identity']),'cheap includes deep metadata')
    return sorted(changed),len(oldmethods)-len(changed)

def main():
    import time,statistics
    started=time.monotonic();old,oc=load(OLD);new,nc=load(ROOT/'overlay/narrow_fullblock_attention.py');_,wp=load(BASE/'cached_wholeblock.py')
    changed,unchanged=source_proof(old,new)
    need(retained(oc,wp)==retained(nc,wp),'outside six scalar consumers')
    x=within_retained(oc,wp);y=within_retained(nc,wp);need(x[0]==y[0] and x[1]>y[1]==2,'inside six consumers/evidence/check selection')
    need(ordinary(oc,wp)==ordinary(nc,wp),'prior op exemption changed')
    need(errors(oc,wp)==errors(nc,wp),'outside errors/regression')
    cases={'boundaries':boundaries(nc),'lifecycle':lifecycle(nc),'cheap_guards':cheap_guards(nc),'metadata_drift':metadata_drift(oc,nc)}
    for mode in ('normal','handled','throw'):
        x=real_ticks(oc,wp,mode);y=real_ticks(nc,wp,mode);need(x[:3]==y[:3],'real dispatcher evidence/exception drift '+mode)
    samples=[]
    for _ in range(3):
        before=time.process_time_ns();x=real_ticks(oc,wp,'normal',400);a=time.process_time_ns()-before
        before=time.process_time_ns();y=real_ticks(nc,wp,'normal',400);b=time.process_time_ns()-before
        need(x[:3]==y[:3] and y[3]==800 and x[3]>y[3],'benchmark scope/evidence')
        samples.append({'old_cpu_ns':a,'new_cpu_ns':b,'old_full_checks':x[3],'new_full_checks':y[3]})
    need(not ATTEMPTS and 'ctypes' not in sys.modules,'forbidden runtime operation')
    print(json.dumps({'status':'PASS_TICK_BOUNDARY_SOURCE_SYNTHETIC_ONLY','policy':'tick-boundary-metadata-integrity-v1','changed_original_methods':changed,
      'unchanged_original_methods':unchanged,'original_full_identity_bytes_unchanged':True,'cases':cases,'scalar_consumers':6,'field_slots':40,
      'within_scalar_full_checks':{'old':within_retained(oc,wp)[1],'new':within_retained(nc,wp)[1]},'original_shared_dispatcher_and_whole_listener':True,
      'mock_scope':'Synthetic frames, owner, profile, ABI metadata, sinks and terminal edge; original observer/dispatcher CodeTypes. No model/native or full 14-line/48-domain execution.',
      'transient_metadata_detection_equivalent':False,'production_events_or_values_changed':False,'benchmark_loops':400,'repeats':samples,
      'median_ratio':statistics.median(x['old_cpu_ns'] for x in samples)/statistics.median(x['new_cpu_ns'] for x in samples),
      'benchmark_scope':'synthetic metadata counters, not real 33-symbol ABI or M2 timing','wall_seconds':time.monotonic()-started,'forbidden_attempts':dict(ATTEMPTS),
      'native_executed':False,'model_executed':False,'M128_executed':False},sort_keys=True))

if __name__=='__main__':main()
