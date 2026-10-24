"""MOCK-only observer contract test. No DUT import, native call or evidence read.
Complete sources are compiled; only exact observer CodeTypes are instantiated.
MOCK owner, service/native metadata, descriptors, frames and sinks are not admission.
"""
import argparse, ast, hashlib, json, sys, threading, types
from array import array
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--old-observer',type=Path,required=True)
args=parser.parse_args(); BASE=args.baseline.resolve(); OLD=args.old_observer.resolve()
# Portable packaging change only: resolve each pinned source through explicit CLI roots.
INPUT_SPECS=json.loads((ROOT/'PORTABLE_MANIFEST.json').read_bytes())['test_inputs']
def portable_input(key):
    if key == 'old_observer': return OLD
    kind,relative=key.split('/',1)
    return {'package':ROOT,'baseline':BASE,'old_observer_parent':OLD.parent}[kind]/relative
PINS={portable_input(key):spec['sha256'] for key,spec in INPUT_SPECS.items()}
for key,spec in INPUT_SPECS.items():
    raw=portable_input(key).read_bytes()
    if len(raw)!=spec['bytes'] or hashlib.sha256(raw).hexdigest()!=spec['sha256']:
        raise ValueError('portable input pin mismatch: '+key)
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
    import time,statistics,os
    start=time.monotonic()
    old,oc=load(OLD);new,nc=load(ROOT/'overlay/narrow_fullblock_attention.py')
    wt,wc=load(BASE/'capture/wholeblock.py');nt,nw=load(ROOT/'overlay/wholeblock.py')
    proofs=[]
    for before,after,cls,method in ((old,new,'Fixed93FullblockAttentionObservation','_trace'),(wt,nt,'TraceDispatcher','_dispatch')):
        a,b=ast.parse(before),ast.parse(after)
        klass=next(n for n in b.body if isinstance(n,ast.ClassDef) and n.name==cls)
        fun=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name==method)
        assignment=fun.body.pop(0)
        need(isinstance(assignment,ast.Assign) and ast.dump(assignment.value)==ast.dump(ast.parse('frame.f_code',mode='eval').body),'one local immutable frame code snapshot')
        class Restore(ast.NodeTransformer):
            def visit_Name(self,node):
                if node.id=='code' and isinstance(node.ctx,ast.Load):return ast.copy_location(ast.Attribute(value=ast.Name(id='frame',ctx=ast.Load()),attr='f_code',ctx=ast.Load()),node)
                return node
        Restore().visit(fun)
        need(ast.dump(a)==ast.dump(b),'non-cache AST change '+method);proofs.append(cls+'.'+method)
    need(retained(oc,wc)==retained(nc,nw),'all six scalar consumers/40 slots differ')
    o,oldcalls=ordinary(oc,wc);n,newcalls=ordinary(nc,nw)
    need(o==n and oldcalls==newcalls==1,'ordinary events or identity count drift')
    need(errors(oc,wc)==errors(nc,nw),'exception/owner/thread/poison drift')
    need(drift(oc,False)==drift(nc,False)==[None,None],'op-boundary policy changed')
    need(all(drift(oc,True)) and all(drift(nc,True)),'persistent drift no longer rejected')
    need(priority(oc)==priority(nc),'fault diagnostic priority changed')
    for mode in ('normal','handled','throw'):
        need(real_trace(oc,wc,mode)==real_trace(nc,nw,mode),'original exception/return/listeners drift')
    # Install the original hook CodeTypes, not a new fast-return implementation.
    _,fp=load(BASE/'frozen_layout.py');_,ip=load(OLD.parent/'m2_io.py')
    _,xp=load(BASE/'source/candidates/qwen2_resident_matrix/ffn_public/check_prefix_numeric.py')
    def impossible(*_):raise AssertionError('benchmark attempted filesystem/runtime behavior')
    env={'os':os,'Path':Path,'need':need,'sys':sys,'getattr':getattr}
    fl=types.MethodType(types.FunctionType(fp['FrozenLayout.audit_write'],env),S(_write_path=impossible))
    io=types.MethodType(types.FunctionType(ip['CalibrationIO.audit'],env),S())
    def cell(x):return (lambda:x).__closure__[0]
    cc=xp['frozen_exec.<locals>.audit'];bindings={'state':{'active':False},'hashes':{},'observed':set()}
    inactive=types.FunctionType(cc,env,closure=tuple(cell(bindings[n]) for n in cc.co_freevars))
    sys.addaudithook(fl);sys.addaudithook(io);sys.addaudithook(inactive)
    counts=Counter();counting={'active':False}
    def count_audit(event,args):
        if counting['active'] and event=='object.__getattr__':counts[args[1]]+=1
    sys.addaudithook(count_audit)
    current=sys._getframe();counting['active']=True;before=counts['f_code'];value=current.f_code
    need(counts['f_code']==before+1,'real CPython f_code auditing absent')
    try:current.f_code=value
    except AttributeError:pass
    else:raise AssertionError('real frame f_code unexpectedly writable')
    counting['active']=False
    def measure(pool,wp):
        a,_=attention(pool);d,w=whole(wp,a);counts.clear();counting['active']=True
        t=time.process_time_ns();d.start()
        try:
            for _ in range(1800):need(a.owner.outer('normal')=={'result_fire':True,'value':7},'return')
        finally:d.stop()
        elapsed=time.process_time_ns()-t;counting['active']=False
        need(d.failed is None and a.error is None and w.failure is None,'benchmark listener poison')
        return elapsed,dict(counts),snapshot(a,w),a.library.calls
    samples=[]
    for repeat in range(3):
        x=measure(oc,wc);y=measure(nc,nw)
        need(x[2:]==y[2:],'benchmark actual evidence/identity counts drift')
        need(y[1]['f_code']<x[1]['f_code'],'no audited-read reduction')
        samples.append(dict(old_cpu_ns=x[0],new_cpu_ns=y[0],old_audit=x[1],new_audit=y[1],identity_calls_each=x[3]))
    need(not ATTEMPTS and 'ctypes' not in sys.modules,'native/model import')
    oldmedian=statistics.median(x['old_cpu_ns'] for x in samples);newmedian=statistics.median(x['new_cpu_ns'] for x in samples)
    print(json.dumps(dict(status='PASS_CALLBACK_LOCAL_CODE_CACHE_SYNTHETIC_ONLY',ast_inverse_proofs=proofs,
        retained_scalar_consumers=6,retained_field_slots=40,original_shared_dispatcher=True,
        installed_original_audit_hooks=['FrozenLayout.audit_write','CalibrationIO.audit','inactive frozen_exec.audit'],
        mock_scope='MOCK owner/profile/native metadata and synthetic operations; original methods and true runtime frames/dispatcher/audit events',
        real_M2_executed=False,native_executed=False,model_executed=False,full_identity_frequency_changed=False,
        audit_readonly_f_code_proven=True,audited_read_count_intentionally_reduced=True,
        loops_per_variant=1800,repeats=3,measurements=samples,old_median_cpu_ns=oldmedian,new_median_cpu_ns=newmedian,
        ratio=oldmedian/newmedian,wall_seconds=time.monotonic()-start,forbidden_attempts=dict(ATTEMPTS)),sort_keys=True))

if __name__=='__main__':
    import os,resource
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20))
    main()
