"""Explicit equal/grouped-head physical layouts; no materialized Q/K expansion."""
from dataclasses import dataclass

@dataclass(frozen=True)
class PrepLayout:
    key_heads: int
    value_heads: int
    width: int = 128

    def __post_init__(self):
        if any(type(v) is not int for v in (self.key_heads,self.value_heads,self.width)) or (self.key_heads,self.value_heads,self.width) not in ((16,16,128),(16,32,128)):
            raise ValueError('only pinned 0.8B and 35B head geometries are admitted')

    @property
    def key_elements(self):return self.key_heads*self.width
    @property
    def vector_elements(self):return self.value_heads*self.width
    @property
    def conv_elements(self):return 2*self.key_elements+self.vector_elements
    @property
    def core_elements(self):return 3*self.vector_elements+16*self.value_heads
    @property
    def conv_row_bytes(self):return self.conv_elements*2
    @property
    def ab_row_bytes(self):return self.value_heads*4
    @property
    def core_row_bytes(self):return self.core_elements*4
    @property
    def a_log_bytes(self):return self.value_heads*4
    @property
    def dt_bias_bytes(self):return 64

    def source_head(self, role, value_head):
        if type(role) is not int or role not in (0,1,2) or type(value_head) is not int or not 0<=value_head<self.value_heads:
            raise ValueError('role/value head outside pinned layout')
        return value_head//(self.value_heads//self.key_heads) if role<2 else value_head

    def source_element(self,role,value_head):
        return (role*self.key_elements if role<2 else 2*self.key_elements)+self.source_head(role,value_head)*self.width

EQUAL_HEADS=PrepLayout(16,16)
GROUPED_35B=PrepLayout(16,32)


def grouped_source_identity(root):
    """Pin official geometry and repeat ordering, without executing a model."""
    import ast,hashlib,json
    from pathlib import Path
    root=Path(root)
    source='config/upstream/weight_headers/qwen3_5_35b_a3b/modeling_qwen3_5_moe.py'
    config='config/upstream/weight_headers/qwen3_5_35b_a3b/config.json'
    pins={source:'ea77a3979cb659dd04dc1f6a1cd7d3df53ddc5759e40eb0d5e98846e95b39d30',
          config:'5e4d7f74fec2f360eb9cfbfcd6ec0c4c76e684d3a11caaed259d9fd9bfbc7944'}
    raw={p:(root/p).read_bytes() for p in pins}
    if any(hashlib.sha256(raw[p]).hexdigest()!=h for p,h in pins.items()):
        raise ValueError('pinned35B official geometry source drift')
    cfg=json.loads(raw[config])['text_config']
    if tuple(cfg[k] for k in ('linear_num_key_heads','linear_num_value_heads','linear_key_head_dim','linear_value_head_dim'))!=(16,32,128,128):
        raise ValueError('grouped35B geometry drift')
    tree=ast.parse(raw[source])
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Qwen3_5MoeGatedDeltaNet')
    forward=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='forward')
    repeat=[n for n in forward.body if isinstance(n,ast.If) and ast.unparse(n.test)=='self.num_v_heads // self.num_k_heads > 1']
    wanted=['query = query.repeat_interleave(self.num_v_heads // self.num_k_heads, dim=2)',
            'key = key.repeat_interleave(self.num_v_heads // self.num_k_heads, dim=2)']
    if len(repeat)!=1 or [ast.unparse(n) for n in repeat[0].body]!=wanted:
        raise ValueError('official repeat_interleave ordering drift')
    return dict(source_sha256=pins,repeat_ast_sha256=hashlib.sha256(ast.dump(repeat[0]).encode()).hexdigest(),
        model_revision='62704185bd97ad488cfc404e7caea797396b74dc',
        transformers_revision='42ca97014c85d71a88ad60d55f08cb9fb4d26e2c',
        key_heads=16,value_heads=32,source_head='value_head//2',official_forward_executed=False,
        production_chisel_supports_grouped_heads=False,native_acceptance=False)
