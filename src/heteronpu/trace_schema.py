"""Deterministic model/backend trace schema and offline replayer (E0)."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import hashlib,json,math,struct
from typing import Mapping,Sequence
DTYPE_BYTES={'fp32':4,'fp16':2,'bf16':2,'int8':1,'uint8':1,'int32':4};FLOATS={'fp32','fp16','bf16'}
def _bf16(v:float)->int:
    b=int.from_bytes(struct.pack('<f',float(v)),'little');return ((b+0x7fff+((b>>16)&1))>>16)&0xffff
def _encode(dtype:str,values:Sequence[float|int])->bytes:
    if dtype=='fp32':return b''.join(struct.pack('<f',float(v)) for v in values)
    if dtype=='fp16':return b''.join(struct.pack('<e',float(v)) for v in values)
    if dtype=='bf16':return b''.join(_bf16(float(v)).to_bytes(2,'little') for v in values)
    if dtype=='int8':return bytes(int(v)&0xff for v in values)
    if dtype=='uint8':return bytes(int(v) for v in values)
    if dtype=='int32':return b''.join(int(v).to_bytes(4,'little',signed=True) for v in values)
    raise ValueError(dtype)
def _decode(dtype:str,p:bytes,i:int)->float|int:
    w=DTYPE_BYTES[dtype];d=p[i*w:(i+1)*w]
    if dtype=='fp32':return struct.unpack('<f',d)[0]
    if dtype=='fp16':return struct.unpack('<e',d)[0]
    if dtype=='bf16':return struct.unpack('<f',(int.from_bytes(d,'little')<<16).to_bytes(4,'little'))[0]
    if dtype=='int8':return int.from_bytes(d,'little',signed=True)
    if dtype=='uint8':return d[0]
    return int.from_bytes(d,'little',signed=True)
def _strides(shape):
    out=[];s=1
    for d in reversed(shape):out.append(s);s*=d
    return tuple(reversed(out))
def _indices(n:int,k:int=16):return tuple(range(n)) if n<=k else tuple(sorted({round(i*(n-1)/(k-1)) for i in range(k)}))
@dataclass(frozen=True)
class TensorSnapshot:
    name:str;dtype:str;shape:tuple[int,...];strides:tuple[int,...];byte_length:int;sha256:str;samples:tuple[tuple[int,float|int],...];payload_hex:str|None=None;artifact:str|None=None
    @classmethod
    def from_values(cls,name,dtype,shape,values,*,retain_payload_bytes=4096,artifact=None):
        dtype=dtype.lower();shape=tuple(int(x) for x in shape);count=math.prod(shape)
        if count!=len(values) or any(x<=0 for x in shape):raise ValueError('shape')
        p=_encode(dtype,values);samples=tuple((i,_decode(dtype,p,i)) for i in _indices(count))
        return cls(name,dtype,shape,_strides(shape),len(p),hashlib.sha256(p).hexdigest(),samples,p.hex() if len(p)<=retain_payload_bytes else None,artifact)
    def validate(self):
        if self.dtype not in DTYPE_BYTES or len(self.shape)!=len(self.strides):raise ValueError('tensor metadata')
        if self.byte_length!=math.prod(self.shape)*DTYPE_BYTES[self.dtype]:raise ValueError('bytes')
        if len(self.sha256)!=64:raise ValueError('hash')
        if self.payload_hex is not None:
            p=bytes.fromhex(self.payload_hex)
            if len(p)!=self.byte_length or hashlib.sha256(p).hexdigest()!=self.sha256:raise ValueError('payload')
@dataclass(frozen=True)
class StateSnapshot:
    domain:str;sequence_id:int;generation:int;key:str;tensor:TensorSnapshot
    def validate(self):
        if not self.domain or self.sequence_id<0 or self.generation<0 or not self.key:raise ValueError('state')
        self.tensor.validate()
@dataclass(frozen=True)
class NodeTrace:
    node_id:str;layer:int;op:str;inputs:tuple[TensorSnapshot,...];outputs:tuple[TensorSnapshot,...];state_reads:tuple[StateSnapshot,...]=();state_writes:tuple[StateSnapshot,...]=();attrs:tuple[tuple[str,str|int|float|bool],...]=()
    def validate(self):
        if not self.node_id or not self.op:raise ValueError('node')
        for x in self.inputs+self.outputs:x.validate()
        for x in self.state_reads+self.state_writes:x.validate()
@dataclass(frozen=True)
class TraceBundle:
    model_id:str;revision:str;token_ids:tuple[int,...];nodes:tuple[NodeTrace,...];schema_version:int=1
    def validate(self):
        if self.schema_version!=1 or not self.model_id or not self.revision:raise ValueError('header')
        if len({n.node_id for n in self.nodes})!=len(self.nodes):raise ValueError('duplicate node')
        for n in self.nodes:n.validate()
    def to_dict(self):self.validate();return asdict(self)
    def to_json(self):return json.dumps(self.to_dict(),sort_keys=True,indent=2)+'\n'
    @property
    def sha256(self):return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    @classmethod
    def from_dict(cls,raw:Mapping[str,object]):
        def t(v):return TensorSnapshot(str(v['name']),str(v['dtype']),tuple(v['shape']),tuple(v['strides']),int(v['byte_length']),str(v['sha256']),tuple((int(x[0]),x[1]) for x in v['samples']),v.get('payload_hex'),v.get('artifact'))
        def s(v):return StateSnapshot(str(v['domain']),int(v['sequence_id']),int(v['generation']),str(v['key']),t(v['tensor']))
        nodes=[]
        for v in raw['nodes']:nodes.append(NodeTrace(str(v['node_id']),int(v['layer']),str(v['op']),tuple(t(x) for x in v['inputs']),tuple(t(x) for x in v['outputs']),tuple(s(x) for x in v.get('state_reads',[])),tuple(s(x) for x in v.get('state_writes',[])),tuple((str(x[0]),x[1]) for x in v.get('attrs',[]))))
        out=cls(str(raw['model_id']),str(raw['revision']),tuple(int(x) for x in raw['token_ids']),tuple(nodes),int(raw.get('schema_version',1)));out.validate();return out
    @classmethod
    def from_json(cls,payload):return cls.from_dict(json.loads(payload))
@dataclass(frozen=True)
class TraceDifference:path:str;kind:str;expected:object;actual:object
def compare_traces(a:TraceBundle,b:TraceBundle,*,atol=1e-5,rtol=1e-4):
    a.validate();b.validate();d=[]
    for f in ('model_id','revision','token_ids'):
        if getattr(a,f)!=getattr(b,f):d.append(TraceDifference(f,'metadata',getattr(a,f),getattr(b,f)))
    if len(a.nodes)!=len(b.nodes):return tuple(d+[TraceDifference('nodes','length',len(a.nodes),len(b.nodes))])
    for ni,(x,y) in enumerate(zip(a.nodes,b.nodes)):
        p=f'nodes[{ni}]'
        for f in ('node_id','layer','op','attrs'):
            if getattr(x,f)!=getattr(y,f):d.append(TraceDifference(f'{p}.{f}','metadata',getattr(x,f),getattr(y,f)))
        for c in ('inputs','outputs'):
            xa,ya=getattr(x,c),getattr(y,c)
            if len(xa)!=len(ya):d.append(TraceDifference(f'{p}.{c}','length',len(xa),len(ya)));continue
            for ti,(u,v) in enumerate(zip(xa,ya)):
                q=f'{p}.{c}[{ti}]'
                if (u.name,u.dtype,u.shape,u.strides,u.byte_length)!=(v.name,v.dtype,v.shape,v.strides,v.byte_length):d.append(TraceDifference(q,'tensor_metadata',asdict(u),asdict(v)));continue
                if u.sha256==v.sha256:continue
                close=len(u.samples)==len(v.samples) and all(i==j and (abs(float(xv)-float(yv))<=atol+rtol*abs(float(xv)) if u.dtype in FLOATS else xv==yv) for (i,xv),(j,yv) in zip(u.samples,v.samples))
                if not close:d.append(TraceDifference(f'{q}.samples','numeric',u.samples,v.samples))
        for c in ('state_reads','state_writes'):
            xa,ya=getattr(x,c),getattr(y,c)
            if len(xa)!=len(ya):d.append(TraceDifference(f'{p}.{c}','length',len(xa),len(ya)));continue
            for si,(u,v) in enumerate(zip(xa,ya)):
                if (u.domain,u.sequence_id,u.generation,u.key,u.tensor.sha256)!=(v.domain,v.sequence_id,v.generation,v.key,v.tensor.sha256):d.append(TraceDifference(f'{p}.{c}[{si}]','state',asdict(u),asdict(v)))
    return tuple(d)
def synthetic_trace():
    h=TensorSnapshot.from_values('hidden','bf16',(1,8),[.1*i for i in range(8)]);g0=StateSnapshot('gdn_matrix',7,3,'layer0/head0',TensorSnapshot.from_values('gdn_before','fp32',(2,2),[0,.1,.2,.3]));o=TensorSnapshot.from_values('gdn_output','bf16',(1,8),[.2*i-.3 for i in range(8)]);g1=StateSnapshot('gdn_matrix',7,3,'layer0/head0',TensorSnapshot.from_values('gdn_after','fp32',(2,2),[.1,.2,.4,.8]));q=TensorSnapshot.from_values('qsa_selected','int32',(4,),[0,31,127,255]);m=TensorSnapshot.from_values('moe_route','int32',(2,),[3,9])
    return TraceBundle('Qwen/Qwen3.8-Flash-Next','synthetic-contract-revision',(11,7,5),(NodeTrace('layer0.gdn',0,'gated_deltanet',(h,),(o,),(g0,),(g1,),(('chunk',64),)),NodeTrace('layer3.qsa',3,'qsa_sparse_attention',(o,),(q,),attrs=(('selected_budget',2048),)),NodeTrace('layer3.moe',3,'moe_router',(o,),(m,),attrs=(('top_k',10),))))
def trace_schema_report():
    a=synthetic_trace();payload=a.to_json();b=TraceBundle.from_json(payload)
    if compare_traces(a,b):raise AssertionError('roundtrip')
    raw=json.loads(payload);raw['nodes'][2]['outputs'][0]['payload_hex']=None;raw['nodes'][2]['outputs'][0]['sha256']='0'*64;raw['nodes'][2]['outputs'][0]['samples'][0][1]=99;c=TraceBundle.from_dict(raw);diff=compare_traces(a,c)
    if not diff:raise AssertionError('mutation')
    return {'schema_version':1,'status':'PASS','evidence_class':'trace_schema_and_replayer_E0_not_official_weight_trace','trace_sha256':a.sha256,'serialized_bytes':len(payload.encode()),'nodes':len(a.nodes),'exact_roundtrip_differences':0,'mutation_differences':len(diff),'required_official_fields':['model_id_and_immutable_revision','node_layer_op_identity','tensor_dtype_shape_stride_hash_samples','state_domain_sequence_generation_key','QSA_selected_tokens','MoE_route_and_weights','PLE_row_ids','MTP_accepted_prefix_and_state_generation'],'remaining_local_gates':['official_runtime_capture','artifact_file_binding','per_node_official_vs_backend_replay','tolerance_review']}
