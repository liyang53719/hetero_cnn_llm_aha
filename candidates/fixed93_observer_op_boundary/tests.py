"""MOCK-only observer contract test. No DUT import, native call or evidence read.
Complete sources are compiled; only exact observer CodeTypes are instantiated.
MOCK owner, service/native metadata, descriptors, frames and sinks are not admission.
"""
import argparse, ast, hashlib, json, sys, threading, types
from array import array
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(); parser.add_argument('--baseline',type=Path,required=True)
BASE=parser.parse_args().baseline.resolve()
PINS={BASE/'observation/fullblock_attention.py':'31eaa951a093f4584c2adee16bd44744282ad7e989c2e23a3f657efaab4a15f9',
      ROOT/'fullblock_attention.py':'940e7929f99177fff04ade16c22a69309a3264454df9f0d822f7c7630abb1774',
      BASE/'capture/wholeblock.py':'181a17a663f303c37ccb79224ad2f0f1cf333115314987a9118a6f6115d9d6ea'}
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
def unused(self): return None
'''
MC={c.co_name:c for c in codes(compile(MOCK,'<MOCK_ONLY>','exec'))}
OTHER=next(c for c in codes(compile('def _attention(self): pass','<MOCK_SAME_NAME>','exec')) if c.co_name=='_attention')

def attention(pool):
    g={'require':need,'threading':threading,'types':types,'sys':sys,'asdict':lambda p:dict(vars(p)),
       'native_snapshot':native,'array':array,'SENTINEL':0xdeadbeef}
    names=('_trace','_identity','_scalar','_line','_put','_event','_fence_event','_context')
    attrs={n:fn(pool,'Fixed93FullblockAttentionObservation.'+n,g) for n in names}
    attrs['_h_t_k']=staticmethod(fn(pool,'Fixed93FullblockAttentionObservation._h_t_k',g))
    cls=type('MOCKAttention',(),attrs); a=cls(); boom=ValueError('MOCK original exception')
    owner_cls=type('MOCKOwner',(),{n:types.FunctionType(MC[n],{'BOOM':boom}) for n in ('_op','_attention','outer')})
    owner=owner_cls(); owner.clock=123; owner.matrix_client=None
    lib=S(calls=0,kind=object(),abi=1); profile=S(width=1)
    owner.matrix=S(lib=lib,resource_address=0,profile=profile,_bindings={}); owner.scalar=object()
    a.owner=owner; a.services=(owner.matrix,owner.scalar); a.library=lib; a.resource_address=0
    a.profile=profile; a.profile_snapshot={'width':1}; a.binding_snapshot={}
    a.native_type=lib.kind; a.native_type_members={}; a.native_functions={}; a.native_signatures={'MOCK_ABI':1}
    a.job_object=None; a.thread=threading.get_ident(); a.client_identity=None
    a.codes={n:MC[n] if n in MC else MC['unused'] for n in ('_op','_attention','_matrix_step','_write','tick','_fault','_finish','packed_tick','packed_commit')}
    a.all_codes=frozenset((MC['_op'],MC['_attention'],MC['outer']))
    a.scalar_code=a.exp_code=a.ticket_code=a.legacy_code=MC['unused']; a.service_codes={}
    a.disarmed=False; a.error=None; a.started=1; a.job={'m':1}; a.fold_coord=None; a.fold_index=0
    a.event_counts=Counter(); a.pending_normalization=None; a.normalization_reuse_count=0
    a.line={n:i+1000 for i,n in enumerate(('fold','dot','scale','denominator','inverse','normalize','qk_check','qk_pass','score','exp','output'))}
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
    w=W(); w.by_code={MC['_attention']:'owner_attention',MC['outer']:'public_MOCK'}; w.op_events=[]
    w.objects={'x':a.owner}; w.limits={'max_exception_frames':8}; w._exceptions=set(); w.records=[]; w.failure=None
    w._event=lambda key,frame,values:w.records.append((key,values))
    w._poison=lambda value:setattr(w,'failure',w.failure or value)
    d=D(a.all_codes,max_listeners=3,on_error=w._poison,line_codes=(),scalar_code=None,exp_code=None,max_exception_frames=8)
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

def main():
    old,oc=load(BASE/'observation/fullblock_attention.py'); new,nc=load(ROOT/'fullblock_attention.py'); wholetext,wc=load(BASE/'capture/wholeblock.py')
    ot,nt=ast.parse(old),ast.parse(new)
    trace=next(x for x in ast.walk(nt) if isinstance(x,ast.FunctionDef) and x.name=='_trace')
    guard=next(x for x in trace.body if isinstance(x,ast.Try)).body.pop(0)
    need(isinstance(guard,ast.If),'missing single guard')
    need(ast.dump(ot)==ast.dump(nt),'change outside inserted guard')
    need(retained(oc,wc)==retained(nc,wc),'six scalar consumers differ')
    osnap,oldcalls=ordinary(oc,wc); nsnap,newcalls=ordinary(nc,wc)
    need(osnap==nsnap and oldcalls==10 and newcalls==1,'normal records/identity boundary')
    need(errors(oc,wc)==errors(nc,wc),'single-fault errors differ')
    need(all(drift(oc,False)) and drift(nc,False)==[None,None],'transient drift NOT expected to be equivalent')
    need(all(drift(oc,True)) and all(drift(nc,True)),'retained boundary must detect persistent drift')
    need('native' in priority(oc) and 'owner' in priority(nc),'combined-fault priority difference')
    for mode in ('normal','handled','throw'):
        need(real_trace(oc,wc,mode)==real_trace(nc,wc,mode),'real trace differential '+mode)
    need('ctypes' not in sys.modules and not ATTEMPTS,'unexpected forbidden attempt')
    print(json.dumps({'status':'PASS_MOCK_CONTRACT_ONLY','source_sha256':list(PINS.values()),
        'unchanged':'all original AST except one inserted guard; includes 16 fields, line/exp/fence logic; not execution coverage of all domains',
        'identity_calls_normal_old_new':[oldcalls,newcalls],'expected_non_equivalence':'transient ABI/profile drift limited to removed identity boundaries',
        'wholeblock_op_binding':'NONE: independent MOCK op counts, real _observe only MOCK public/support codes','forbidden_attempts':dict(ATTEMPTS),'native_model_evidence_execution':False},sort_keys=True))

if __name__=='__main__':
    import os,resource
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(15,15)); resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20))
    main()
