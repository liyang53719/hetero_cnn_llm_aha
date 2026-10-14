"""Separate read-only source-bound observer for explicit PV32 four-repeat owner.

Old observers and their eight-repeat acceptance remain unchanged. These external
capture buffers never supply owner operands, results or physical memory.
"""
import ast
from dataclasses import asdict
from pathlib import Path
import sys
import threading
import types
from candidates.qwen2_resident_matrix.official_bf16 import observation as original
from candidates.qwen2_resident_matrix.official_bf16 import observation_monitoring as monitoring
from candidates.qwen2_resident_matrix.dense_block_reduce import matrix_binding,profile
from candidates.qwen2_resident_matrix.ffn_public.prefix_arithmetic import ScalarService
from . import pv32_owner

ROOT=Path(__file__).resolve().parents[2]
SELF='candidates/qwen2_live_attention_model_m128/pv32_observation.py'
OWNER='candidates/qwen2_live_attention_model_m128/pv32_owner.py'
BASE_OWNER='candidates/qwen2_resident_matrix/ffn_attention/attention_owner.py'
require=original.require


def verify_extra(owner,sources):
    require(type(owner) is pv32_owner.OfficialPV32AttentionOwner and
        type(owner.matrix) is matrix_binding.ProfiledMatrixService and type(owner.scalar) is ScalarService,
        'exact PV32 owner and original profiled Matrix/Scalar required')
    count=0
    for relative in (SELF,OWNER,'candidates/qwen2_resident_matrix/dense_block_reduce/matrix_binding.py',
                     'candidates/qwen2_resident_matrix/dense_block_reduce/profile.py'):
        require(relative in sources,'PV32 observer closure missing '+relative)
        count+=original._verify_module(sys.modules[relative[:-3].replace('/','.')],relative)
    owner.matrix.profile.validate(1536)
    return count


class PV32AttentionObservation(monitoring.OfficialAttentionMonitoringObservation):
    def __init__(self,owner,*,source_sha256):
        require(sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12) and not sys.flags.optimize,
            'CPython3.12 nonoptimized monitoring required')
        self.owner,self.sources=owner,dict(source_sha256)
        self.execution_sources=original.verify_source_snapshot(self.sources)
        self.loaded_functions_checked=monitoring.verify_monitoring_dependencies(owner,self.sources)
        self.extra_loaded_checked=verify_extra(owner,self.sources)
        self.services=(owner.matrix,owner.scalar);self.instrumentation_sha256=original.base.sha(Path(__file__).read_bytes())
        self.codes={};methods={}
        for name in ('_attention','_matrix_step','_pv32_step','tick'):
            relative=BASE_OWNER if name=='_matrix_step' else OWNER
            clsname='AttentionOwner' if name=='_matrix_step' else 'OfficialPV32AttentionOwner'
            path=ROOT/relative;raw=path.read_text();cls=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name==clsname)
            method=getattr(owner,name);code=original._code(original._code(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),clsname),name)
            require(isinstance(method,types.MethodType) and original._same_code(method.__func__.__code__,code),'loaded target drift '+name)
            self.codes[name]=method.__func__.__code__;methods[name]=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
        def point(method,statement):
            expected=ast.dump(ast.parse(statement).body[0],include_attributes=False)
            points=[n.lineno for n in ast.walk(methods[method]) if isinstance(n,ast.stmt) and ast.dump(n,include_attributes=False)==expected]
            require(len(points)==1,'ambiguous new observer point '+statement);return points[0]
        self.points=dict(score=point('_attention','scores.append(score)'),exp=point('_attention','probabilities.append(probability)'),
            matrix=point('_matrix_step','return lanes'),
            pv=point('_pv32_step',"self.counts['pv32_selected_lane_results']+=32"),
            store=point('_pv32_step','yield from self._write(destination+half*4,output)'))
        self.thread=threading.get_ident();self.active=self.closed=self.disarmed=False
        self.started=0;self.job=self.terminal=self.retirement=self.error=None;self.fields={}
        self.tool_id=None;self._tool_name='pv32-observer-'+str(id(self));self._registered={};self._configured={}
        self._line_callback=self._monitor_line;self._return_callback=self._monitor_return
        self._target_lines={self.codes['_attention']:frozenset((self.points['score'],self.points['exp'])),
            self.codes['_matrix_step']:frozenset((self.points['matrix'],)),
            self.codes['_pv32_step']:frozenset((self.points['pv'],self.points['store']))}

    def __enter__(self):
        require(verify_extra(self.owner,self.sources)==self.extra_loaded_checked,'new observer dependency changed')
        return super().__enter__()

    def __exit__(self,kind,error,traceback):
        try:return super().__exit__(kind,error,traceback)
        finally:require(verify_extra(self.owner,self.sources)==self.extra_loaded_checked,'new observer dependency changed at exit')

    def _line(self,frame):
        local=frame.f_locals
        if frame.f_code is self.codes['_attention']:
            if frame.f_lineno==self.points['score']:
                coord=(local['head'],local['token'],local['key'])
                self._put('unrounded_dot_sum',coord,(local['total'],));self._put('dot_bf16',coord,(local['dot'],))
                self._put('scores_bf16',coord,(local['score'],))
            elif frame.f_lineno==self.points['exp']:
                self._put('softmax_exp',(local['head'],local['token'],len(local['probabilities'])),(local['probability'],))
            return
        outer=frame.f_back
        require(outer is not None and outer.f_code is self.codes['_attention'] and outer.f_locals.get('self') is self.owner,
            'PV32 actual observation caller mismatch')
        ctx=outer.f_locals;h,t,k=ctx['head'],ctx['token'],ctx['key']
        if frame.f_code is self.codes['_matrix_step']:
            require(local['opcode']==0x23,'new owner must keep original helper QK-only')
            if local['last']:self._put('dot_parts',(h,t,k,0),tuple(local['lanes']))
        elif frame.f_lineno==self.points['pv']:
            self._put('softmax_fp32',(h,t,k),(ctx['probability'],))
            self._put('prob_bf16',(h,t,k),(local['a'][0]<<16,))
            self._put('normalizer',(h,t,0),(ctx['maximum'],ctx['total'],ctx['inverse']))
            if local['last']:self._put('pv_raw',(h,t,ctx['col']),tuple(local['result'].value[0][i] for i in range(32)))
        elif frame.f_lineno==self.points['store']:
            self._put('pv_bf16',(h,t,ctx['col']+local['half']),tuple(local['output']))

    def _coverage(self):
        m=self.job['m']
        for name,f in self.fields.items():
            for h in range(12):
                for t in range(m):
                    if name in ('normalizer','pv_raw','pv_bf16'):
                        width=3 if name=='normalizer' else 128
                        repeats=4*(t+1) if name=='normalizer' else 1
                        start=(h*m+t)*width;targets=((start+i,repeats) for i in range(width))
                    else:
                        width=16 if name=='dot_parts' else 1
                        repeats=4 if name in ('softmax_fp32','prob_bf16') else 1
                        targets=(((h*m*m+t*m+k)*width+i,repeats if k<=t else 0) for k in range(m) for i in range(width))
                    for index,wanted in targets:
                        if f['frequency'][index]!=wanted or f['observed'][index]!=bool(wanted) or (not wanted and f['words'][index]!=original.SENTINEL):return False
        return True

    def report(self):
        require(self.closed and not self.active,'close observer before acceptance')
        complete=self.error is None and self.started==1 and self.terminal is not None
        if complete:
            m=self.job['m'];causal=12*m*(m+1)//2
            counts=dict(dot_parts=16*causal,unrounded_dot_sum=causal,dot_bf16=causal,scores_bf16=causal,
                softmax_exp=causal,softmax_fp32=causal,prob_bf16=causal,normalizer=12*m*3,pv_raw=12*m*128,pv_bf16=12*m*128)
            writes=dict(counts,softmax_fp32=4*causal,prob_bf16=4*causal,normalizer=12*causal)
            r=self.retirement
            complete=(self.terminal['status'] is None and self.terminal['tag']==self.job['tag'] and
                self.terminal['write_bytes']==self.job['write_bytes']==m*1536*4 and r['same_services'] and r['same_job'] and
                r['state']=='idle' and not r['poison'] and r['matrix_released'] and not r['matrix_reset_required'] and
                r['client_retired'] and not r['memory_pending'] and r['scalar_released'] and self._coverage() and
                all(sum(self.fields[n]['observed'])==c and self.fields[n]['writes']==writes[n] for n,c in counts.items()))
        return dict(schema='qwen2-pv32-readonly-observation-v1',status='COMPLETE_PV32_OWNER_OBSERVATION_NOT_OFFICIAL_ACCEPTED' if complete else 'INCOMPLETE',
            source_sha256=self.sources,instrumentation_sha256=self.instrumentation_sha256,
            loaded_functions_checked=self.loaded_functions_checked,extra_loaded_functions_checked=self.extra_loaded_checked,
            job=self.job,terminal=self.terminal,accepted_retirement=self.retirement,observer_error=self.error,
            fields={n:dict(shape=f['shape'],words=len(f['words']),observed_words=sum(f['observed']),
                raw_sha256=original.base.sha(self._bytes(n)),presence_sha256=original.base.sha(bytes(f['observed'])),
                frequency_sha256=original.base.sha(self._bytes(n,'frequency')),writes=f['writes'],identical_repeats=f['repeats']) for n,f in self.fields.items()},
            probability_repeats=4,causal_only=True,future_scores_observed=False,full_29_node_gate=False,
            whole_block_terminal_observed=False,physical_publication_observed=False,hardware_simulation=False,
            trace_api='source-bound CPython3.12 sys.monitoring read-only callbacks')
