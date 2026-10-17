#!/usr/bin/env python3
"""Cold differential wrapper tests. No target modules or native libraries import.

Only explicitly selected source declarations are AST-extracted. The real Host
FSM and exact port getters execute against scripted control-only owner edges.
No numerical owner tick, tensor payload, reference, FMA, package or CI work runs.
"""
import ast
import builtins
from collections import Counter, deque
from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace as NS
import unittest
import tempfile
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from candidates.qwen2_resident_matrix.attention_packed_m16_same_host import prepare, control_ports
_COLD_TEMP = tempfile.TemporaryDirectory(prefix='cold-m16-control-ports-')
HERE = Path(_COLD_TEMP.name)
SOURCE = HERE/'source'
RELATIVE = Path(control_ports.TARGET)
transform_bytes = control_ports.transform
prepare.prior.compose(SOURCE)
def build():
    target = HERE/'candidate'/RELATIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(transform_bytes((SOURCE/RELATIVE).read_bytes()))

sys.dont_write_bytecode = True
P = SOURCE / 'candidates/qwen2_resident_matrix'
CLOCK = NS(now=100.0, log=None)
def monotonic():
    if CLOCK.log is not None: CLOCK.log.append('deadline')
    return CLOCK.now

def require(condition, message):
    if not condition: raise ValueError(message)

def declarations(path, names, namespace):
    nodes = [n for n in ast.parse(path.read_text()).body if getattr(n, 'name', None) in names]
    require({n.name for n in nodes} == set(names), 'missing selected declarations')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)

def selected_class(path, original, new, methods, namespace, bases=()):
    cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == original)
    selected = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    require({n.name for n in selected} == set(methods), 'missing selected methods')
    cls = ast.ClassDef(name=new, bases=[ast.Name(id=b, ctx=ast.Load()) for b in bases],
        keywords=[], body=selected, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), str(path), 'exec'), namespace)
    return namespace[new]

G = dict(dataclass=dataclass, asdict=asdict, Counter=Counter, require=require, __name__=__name__)
declarations(P/'ffn_group/model.py', ['Job','PrefixJob','Command','Completion','OwnerResult','Services','Rejected','uint'], G)
G.update(RESET_DOMAIN=frozenset(), NULL=0xffffff, LIMIT=1<<56, WIDTH=8960)
Host = selected_class(P/'ffn_group/model.py','HostControl','Host', ['ports','tick','_fail'], G)
# Exact Dense getter hierarchy. The numerical/state-machine tick is omitted.
D = dict(dataclass=dataclass, __name__=__name__)
declarations(P/'transposed_down/model.py', ['ReadCommand','WriteCommand','WriteBeat','SeedRequest','SeedBeat','prefix_ddr_beat','output_coordinate'], D)
Base = selected_class(P/'transposed_down/model.py','DenseOwnerModel','Base',
    ['ports','_read_command','_write_command','_write_data','_seed_request','saving_prefix','chunk_start','chunk_end'], D)
Window = selected_class(P/'ffn_window/model.py','FfnWindowOwnerModel','Window', ['ports','_write_command','_write_data','chunk_start','chunk_end','saving_prefix'],D,('Base',))
Drain = selected_class(P/'ffn_drain/model.py','FfnDrainOwnerModel','Drain',['ports','_write_command','_write_data','saving_prefix'],D,('Window',))
D['down'] = NS(WriteBeat=D['WriteBeat'])
declarations(P/'ffn_drain/model.py',['WriteBeat'],D)
D['drain'] = NS(WriteBeat=D['WriteBeat'],down=D['down'])
D['Job']=G['Job']
declarations(P/'ffn_window/model.py',['FfnWindowRequest'],D)
D['window']=NS(FfnWindowRequest=D['FfnWindowRequest'])
declarations(P/'dense_block_reduce/k_window_model.py',['KWindowRequest'],D)
KWindow = selected_class(P/'dense_block_reduce/k_window_model.py','KWindowOwnerModel','KWindow',['_read_command','execution_end'],D,('Drain',))
Dense = selected_class(P/'dense_block_reduce/dense_drain.py','DenseReductionOwner','Dense',['_write_data'],D,('KWindow',))

class ScriptOwner(Dense):
    """Control event source only; no actual Dense state-machine or arithmetic."""
    def ports(self):
        if self.log is not None: self.log.append('owner.ports')
        return super().ports()
    def tick(self, **inputs):
        if self.log is not None: self.log.append('owner.tick')
        p = self.ports()
        self.clock += 1
        p.update(job_ready=p['job_ready'], response_fire=False)
        if 'job' in inputs and p['job_ready']:
            self.job = inputs['job']; self.state = 'execute'
        if inputs.get('abort'):
            self.error = 'Aborted'; self.state = 'drain'
        if inputs.get('poison_on_tick'):
            self.error = 'Protocol'
        if inputs.get('clear_poison_on_tick'):
            self.error = None
        if inputs.get('expire_on_tick'):
            CLOCK.now = 201.0
        if inputs.get('write_ack'):
            require(self.pending_acks > 0, 'unsolicited scripted ACK')
            self.pending_acks -= 1
        if inputs.get('emit_result'):
            require(self.pending_acks == 0, 'scripted terminal before ACK')
            p['response'] = (self.job.tag, self.error, self.job.write_bytes)
            p['response_fire'] = True
            self.state = 'locked' if self.error else 'idle'
        return p

E = dict(__name__=__name__)
Prefix = selected_class(P/'ffn_public/prefix_owners.py','PrefixOwner','Prefix',['ports'],E)
H = dict(__name__=__name__)
declarations(P/'attention_packed_owner/hooks.py',['ports'],H)
E['packed'] = NS(ports=H['ports'])
Attention = selected_class(P/'ffn_attention/attention_owner.py','AttentionOwner','Attention',['ports'],E)
class ReadMatrix:
    def __init__(self): self.owner=None; self.poison=False; self.log=None
    @property
    def reset_required(self):
        if self.log is not None: self.log.append('matrix.reset')
        return self.poison

# Pure getter declarations are used verbatim; no transport tick/constructor runs.
T = dict(require=require,__name__=__name__)
Transport = selected_class(P/'raw_kv_public/model.py','PublicKvTransport','Transport',['check_packed_binding'],T)
class ParentLoan: pass
S = dict(__name__=__name__)
Supply = selected_class(P/'raw_kv_attention/model.py','KvSupply','Supply',['reset_required'],S)
Mux = selected_class(P/'attention_packed_public/mux.py','ScratchMux','Mux',['reset_required'],S) if any(isinstance(n,ast.ClassDef) and n.name=='ScratchMux' for n in ast.parse((P/'attention_packed_public/mux.py').read_text()).body) else None
# Module names in a source-extracted method resolve only these inert types.
IMPORTS = {
 'candidates.qwen2_resident_matrix.raw_kv_public.model': NS(PublicKvTransport=Transport),
 'candidates.qwen2_resident_matrix.raw_kv_parent.model': NS(ParentLoan=ParentLoan),
 'candidates.qwen2_resident_matrix.dense_block_reduce.dense_drain': NS(DenseReductionOwner=ScriptOwner),
 'candidates.qwen2_resident_matrix.official_bf16.owners': NS(OfficialAttentionOwner=Attention),
}
def controlled_import(name, *args, **kwargs):
    if name in IMPORTS: return IMPORTS[name]
    raise AssertionError('unexpected target import: '+name)

METHODS = ['ports','reset_required','_host_edge','ordinary_edge','idle_edge',
 'accept_down_terminal','publish_completions','finish','_checked_attention_transport']
def public(path,name):
    env=dict(G, time=NS(monotonic=monotonic), numeric=NS(group=NS(OwnerResult=G['OwnerResult'])),
             __builtins__=dict(vars(builtins),__import__=controlled_import))
    declarations(path,['ErrorTerminal'],env)
    cls=selected_class(path,'PublicExecution',name,METHODS,env)
    # Log observations separately from semantic state; the only intended delta.
    for method in ('ports','reset_required','_checked_attention_transport'):
        original=getattr(cls,method)
        def wrapped(self,*a,_m=method,_f=original,**kw):
            if self.log is not None:self.log.append('x.'+_m)
            return _f(self,*a,**kw)
        setattr(cls,method,wrapped)
    reduced_env = dict(__name__=__name__, PublicControl=cls)
    return selected_class(P/'dense_block_reduce/public_execution.py','ReducedPublicExecution',name+'Reduced',
        ['reset_required'],reduced_env,('PublicControl',))

build()
BASE = public(SOURCE/RELATIVE,'Baseline')
CAND = public(HERE/'candidate'/RELATIVE,'Candidate')
class Trace:
    def __init__(self): self.events=[]
    def event(self,event): self.events.append(event)

def fixture(cls, *, admitted=False, bound_transport=False, coupled=False, trace_getters=True):
    log=[] if trace_getters else None
    job=G['Job']('Dense',0,0x1000,0x2000,0x3000,16,32,256,2048,True)
    owner=ScriptOwner()
    owner.__dict__.update(log=log,clock=0,state='execute' if admitted else 'idle',error=None,
      job=job if admitted else None,workspace=None,restoring=False,seed_state='idle',seed_outstanding=False,
      read_active=None,a_hold=None,a_rmw_pending=None,group_started=True,group_done=False,
      fifo=deque(),write_state='idle',write_bytes=2048,load_k=256,window_request=None,
      window_result=None,lease=None,enable_ffn_window=True,enable_ffn_drain=True,
      drain_request=None,drain_result=None,drain_phase='idle',drain_poison=False,pending_acks=0,
      a_beat=0,a_row=0,ready=[False,False],read_sequence=0,write_sequence=0,load_depth=0,load_beat=0,n_base=0,
      seed_context=0,seed_index=0,seed_hold=(0,)*16,group_sequence=1,chunk_index=0,
      write_row=0,write_row_beat=0,write_context=0,write_prefix_index=0,write_index=0,
      final_value=[list(range(256)) for _ in range(16)],accepted_write=NS(beats=2))
    owner.a_banks=object();owner.b_banks=object()
    owner.tiles=NS(idle=True,poison=False,leased=False,banks=owner.a_banks)
    scalar=NS(client=None)
    matrix=ReadMatrix();matrix.log=log
    prefix=Prefix();prefix.__dict__.update(state='idle',poison=False,scalar=scalar,request=None,result=None)
    attention=Attention();attention.__dict__.update(state='idle',poison=False,scalar=scalar,matrix=matrix,
      request=None,result=None,memory_pending=False,matrix_request=None,scratch_request=None,scratch_pending=False,packed_schedule=None)
    host=Host();command=G['Command'](0x20,2,0,1,2,0,1)
    host.__dict__.update(frontend=None,program=[command],current_command=command,pc=0,
      state='waitDone' if admitted else 'issue',group=None,bound=job,enabled=True,legacy_attention=True,
      group_commands=(),completion_index=0,status=None,reason=None,poison=False,result=None,
      jobs=int(admitted),completed=0,useful=0,executed=0,written=0,events={0},published=[],virtual=[])
    x=cls();x.__dict__.update(log=log,owner=owner,host=host,prefix_owner=prefix,attention_owner=attention,
      matrix_service=matrix,coupled=None,reduction=None,attention_transport=None,attention_transport_binding=None,
      deadline=200.0,counts=Counter(),requests=[],completions=[],trace=Trace(),completion_ready=False,
      result_ready=False,launch_result=None,down_job=job if admitted else None,down_terminal=None,
      down_start_tick=0 if admitted else None,down_terminal_tick=None,last_host_edge=None,
      bank_ids=(id(owner),id(owner.a_banks),id(owner.b_banks),id(owner.tiles.banks)))
    if coupled:
        C=selected_class(P/'ffn_fullgroup/check_numeric.py','Coupled','Coupled',['services'],dict(group=NS(Services=G['Services'])))
        x.coupled=C();x.coupled.owner=owner;x.coupled.silu_busy=False;x.coupled.c=NS(poison=False)
    if bound_transport:
        parent=ParentLoan();parent.owner=owner;parent.raw=NS(banks=owner.a_banks,poison=False,enabled=True)
        parent.enabled=True;parent.poison=False
        supply=Supply();supply.__dict__.update(parent=parent,poison=False,scratch_mux=None,enabled=True)
        transport=Transport();transport.__dict__.update(owner=attention,parent=parent,job=job,
          supply=supply,packed_profile=None,packed_binding=None)
        x.attention_transport=transport
        x.attention_transport_binding=(transport,supply,parent,job,attention,matrix,scalar)
    CLOCK.log=log;CLOCK.now=100.0
    return x,job

def canonical(value):
    if is_dataclass(value):return canonical(asdict(value))
    if isinstance(value,dict):return {str(k):canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,deque)):return [canonical(v) for v in value]
    if isinstance(value,set):return sorted(value)
    return value

def getter_graph(value, seen=None):
    # Snapshot every reachable fixture instance field without invoking getters.
    # Opaque bank tokens keep identity; cycles use stable traversal references.
    seen={} if seen is None else seen
    if value is None or isinstance(value,(bool,int,float,str)):return value
    if isinstance(value,(dict,list,tuple,deque,set)) or hasattr(value,'__dict__'):
        identity=id(value)
        if identity in seen:return {'ref':seen[identity]}
        seen[identity]=len(seen)
        if isinstance(value,dict):return {str(k):getter_graph(v,seen) for k,v in value.items()}
        if isinstance(value,(list,tuple,deque,set)):return [getter_graph(v,seen) for v in value]
        return {k:getter_graph(v,seen) for k,v in vars(value).items() if k!='log'}
    return {'opaque_id':id(value)}

def state(x):
    return canonical(dict(owner=dict(clock=x.owner.clock,state=x.owner.state,error=x.owner.error,
      job=x.owner.job,pending_acks=x.owner.pending_acks),host={k:getattr(x.host,k) for k in
      ('state','pc','jobs','completed','status','reason','poison','result','events','published','virtual','useful','executed','written')},
      counts=x.counts,requests=x.requests,completions=x.completions,launch_result=x.launch_result,
      down_job=x.down_job,down_terminal=x.down_terminal,down_start_tick=x.down_start_tick,
      down_terminal_tick=x.down_terminal_tick,last_host_edge=x.last_host_edge,trace=x.trace.events))

def outcome(fn):
    try:return dict(returned=canonical(fn()))
    except Exception as exc:return dict(exception=type(exc).__name__,message=str(exc))

class Equivalence(unittest.TestCase):
    def pair(self,inputs, *, setup=None, expected_error=None, **options):
        results=[];logs=[]
        for cls in (BASE,CAND):
            x,j=fixture(cls,**options)
            if setup:setup(x)
            args={k:(j if v=='JOB' else v) for k,v in inputs.items()}
            result=outcome(lambda:x.ordinary_edge(**args))
            results.append((result,state(x)));logs.append(list(x.log))
        self.assertEqual(*results)
        if expected_error is None:
            self.assertNotIn('exception', results[0][0], results[0][0])
        else:
            self.assertEqual(results[0][0].get('exception'),'ValueError')
            self.assertIn(expected_error,results[0][0]['message'])
        if 'job' in inputs:
            self.assertEqual(*logs,'admission observation order changed')
        else:
            x,_=fixture(BASE,**options)
            if setup:setup(x)
            probe=outcome(x.ports);prefix=list(x.log)
            if 'exception' in probe:
                self.assertEqual(logs[0], ['x.ports']+logs[1], 'failed pure read changed rejection order')
            else:
                self.assertEqual(logs[0],prefix+logs[1], 'delta exceeds one discarded pre-edge ports walk')
        return results[0],logs
    def test_admission_order(self):self.pair(dict(job='JOB'),coupled=True,bound_transport=True)
    def test_admission_job_mismatch(self):self.pair(dict(job=G['Job']('Dense',9,1,2,3,16,32,256,2048,True)),expected_error='ordinary Down differs')
    def test_stall_normal_and_retained_bindings(self):
        for coupled in (False,True):
            for transport in (False,True):
                with self.subTest(coupled=coupled,transport=transport):
                    self.pair(dict(write_data_ready=False),admitted=True,coupled=coupled,bound_transport=transport)
    def test_unchanged_preexisting_reset(self):
        self.pair({},admitted=True,setup=lambda x:setattr(x.owner,'error','Protocol'))
    def test_same_edge_reset_is_still_observed(self):self.pair(dict(poison_on_tick=True),admitted=True)
    def test_preedge_reset_not_lost_when_cleared(self):self.pair(dict(clear_poison_on_tick=True),admitted=True,setup=lambda x:setattr(x.owner,'error','Protocol'))
    def test_abort_error_result(self):self.pair(dict(abort=True,emit_result=True),admitted=True)
    def test_success_result_is_not_public_completion(self):self.pair(dict(emit_result=True),admitted=True)
    def test_no_admission_rejected(self):self.pair({},expected_error='without public job admission')
    def test_expired_deadline_unchanged(self):self.pair({},admitted=True,setup=lambda x:setattr(x,'deadline',99.0),expected_error='host budget exceeded')
    def test_identity_failure_unchanged(self):self.pair({},admitted=True,setup=lambda x:setattr(x,'bank_ids',(0,0,0,0)),expected_error='replaced owner/banks')
    def test_transport_binding_failure_before_tick(self):
        self.pair({},admitted=True,bound_transport=True,setup=lambda x:setattr(x,'attention_transport_binding',None),expected_error='transport identity changed')
    def test_deadline_crossed_during_owner_tick(self):
        self.pair(dict(expire_on_tick=True),admitted=True,expected_error='host budget exceeded')
    def test_transform_rejects_any_source_drift(self):
        with self.assertRaisesRegex(ValueError,'exact executed composed source'):
            transform_bytes((SOURCE/RELATIVE).read_bytes()+b'\n')
    def test_duplicate_terminal_rejected(self):
        self.pair(dict(emit_result=True),admitted=True,setup=lambda x:setattr(x,'down_terminal',(0,None,2048)),expected_error='duplicate ordinary terminal')
    def test_late_ack_rejected(self):self.pair(dict(write_ack=True),admitted=True,expected_error='unsolicited scripted ACK')
    def test_matrix_poison_rejected_with_owner_error_terminal(self):
        self.pair(dict(abort=True,emit_result=True),admitted=True,setup=lambda x:setattr(x.matrix_service,'poison',True))
    def test_all_getter_reads_are_state_preserving(self):
        for coupled in (False,True):
            for transport in (False,True):
                x,_=fixture(BASE,admitted=True,coupled=coupled,bound_transport=transport)
                before=getter_graph(x)
                for _ in range(3):x.ports()
                self.assertEqual(before,getter_graph(x))
    def test_reachable_ordinary_wire_getter_states(self):
        def phase(name):
            def setup(x):
                o=x.owner
                if name=='a_read':o.state='a_load'
                if name=='b_read':o.state='execute';o.load_k=0
                if name=='write_request':o.write_state='request'
                if name=='write_data':o.write_state='data'
                if name.startswith('seed_'):
                    o.workspace=NS(split_k=128,base=0x8000,generation=1)
                    o.restoring=True;o.seed_state=name[5:];o.chunk_index=1
                    o.prefix_valid=True;o.committed_prefix_end=128
                    o.restored_contexts=0;o.prefix_saved_contexts=0
            return setup
        for name in ('a_read','b_read','write_request','write_data','seed_begin','seed_read','seed_send'):
            with self.subTest(phase=name):
                self.pair({},admitted=True,coupled=True,bound_transport=True,setup=phase(name))
    def test_getter_only_drain_and_kwindow_states(self):
        for mode in ('drain','kwindow'):
            x,j=fixture(BASE,admitted=True)
            if mode=='drain':
                x.owner.state='ffn_drain';x.owner.drain_request=NS(job=j,ng=0,cols=32)
                x.owner.drain_phase='write';x.owner.write_state='data'
            else:
                x.owner.window_request=D['KWindowRequest'](j,1,0,32,0,False,k_begin=0,k_end=128,block_id=1)
                x.owner.load_k=0
            before=repr({k:v for k,v in vars(x.owner).items() if k!='log'})
            first=x.owner.ports();second=x.owner.ports()
            self.assertEqual(first,second)
            self.assertEqual(before,repr({k:v for k,v in vars(x.owner).items() if k!='log'}))
    def test_reduction_loan_reset_getter(self):
        def setup(x):
            v=dict(dataclass=dataclass,__name__=__name__,ZERO=(0,)*16)
            declarations(P/'dense_block_reduce/vector_add_model.py',['Result'],v)
            loan_cls=selected_class(P/'dense_block_reduce/vector_add_model.py','VectorLoanModel','Loan',['ports'],v)
            loan=loan_cls();loan.__dict__.update(active=False,poison=True,state='idle',error=False,value=(0,)*16)
            x.reduction=NS(c=NS(poison=False),sum=NS(poison=False),loan=loan)
        self.pair({},admitted=True,setup=setup)
    def test_ack_stalls_and_whole_result_trace(self):
        traces=[]
        for cls in (BASE,CAND):
            x,j=fixture(cls,coupled=True,bound_transport=True)
            transcript=[]
            def step(fn):transcript.append((outcome(fn),state(x)))
            step(lambda:x.ordinary_edge(job=j))
            x.owner.pending_acks=1
            for _ in range(3):step(lambda:x.ordinary_edge(write_data_ready=False))
            step(lambda:x.ordinary_edge(write_ack=True))
            step(lambda:x.ordinary_edge(emit_result=True))
            report=dict(completion=list(x.down_terminal),completed=True,same_owner_and_banks=True,
                accepted={'response_handshakes':1},physical_traffic={'down_ack_bytes':j.write_bytes},
                protocol_model_ticks=x.owner.clock,useful_macs=0,executed_macs=0)
            step(lambda:x.accept_down_terminal(report))
            step(lambda:x.publish_completions((0,)))
            step(x.finish)
            self.assertEqual(x.launch_result['completed'],1)
            self.assertEqual(x.counts['completion_fire'],1)
            self.assertEqual(x.counts['result_fire'],1)
            self.assertEqual(x.counts['completion_backpressure_edges'],3)
            self.assertEqual(x.counts['result_backpressure_edges'],3)
            traces.append(transcript)
        self.assertEqual(*traces)
        (HERE/'CONTROL_TRACE.json').write_text(json.dumps(traces[0],sort_keys=True,indent=2)+'\n')

    def test_source_composition_binds_transformed_runner_and_helper(self):
        out = HERE/'integrated-source'
        result = prepare.compose(out, git_head='1'*40,
            producer_package=ROOT/'candidates/qwen2_resident_matrix/portable_official_producer')
        self.assertEqual(hashlib.sha256((out/RELATIVE).read_bytes()).hexdigest(), control_ports.CANDIDATE_SHA256)
        self.assertEqual(hashlib.sha256((SOURCE/RELATIVE).read_bytes()).hexdigest(), control_ports.BASELINE_SHA256)
        observer = json.loads((out/'candidates/qwen2_resident_matrix/attention_packed_observation/pins.json').read_bytes())
        self.assertEqual(observer['runtime'][str(RELATIVE)], control_ports.CANDIDATE_SHA256)
        self.assertEqual(result['source_sha256'][str(RELATIVE)], control_ports.CANDIDATE_SHA256)
        for name in ('control_ports.py','test_control_ports.py'):
            key = 'candidates/qwen2_resident_matrix/attention_packed_m16_same_host/'+name
            self.assertEqual(result['source_sha256'][key], hashlib.sha256((ROOT/key).read_bytes()).hexdigest())

if __name__ == '__main__':
    unittest.main(verbosity=2)
