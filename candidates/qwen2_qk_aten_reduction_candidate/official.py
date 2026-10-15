"""Original pinned upstream AST reference, only called after candidate suffix."""
import ast
import hashlib
from candidates.qwen2_qk_aten_reduction_candidate import model

def prefix(raw,pins,torch,np):
    src='config/upstream/weight_headers/qwen2_1p5b/modeling_qwen2.py'
    model.need(model.sha(model.ROOT/src)==pins['sources'][src]['sha256'],'official source identity')
    ns={'torch':torch,'nn':torch.nn};nodes=pins['model_ast_nodes']
    def execute(indices):
        for i in indices:
            n=nodes[i];model.need(hashlib.sha256(n['source'].encode()).hexdigest()==n['source_sha256'],'original AST identity')
            exec(compile(ast.parse(n['source']),src,'exec'),ns)
    def expanded(name,shape):return torch.from_numpy(np.frombuffer(raw[name],'<f4').copy()).reshape(shape).to(torch.bfloat16)
    def arr(t):return t.detach().float().numpy().copy()
    execute(range(4));norm=ns['Qwen2RMSNorm'](1536,eps=1e-6).to(torch.bfloat16).eval()
    norm.weight=torch.nn.Parameter(expanded('gamma0',(1536,)),requires_grad=False)
    att=torch.nn.Module();att.hidden_size=1536;att.num_heads=12;att.num_key_value_heads=2
    att.num_key_value_groups=6;att.head_dim=128;ns['self']=att;execute(range(4,7))
    for letter,width in (('q',1536),('k',256),('v',256)):
        w=np.frombuffer(raw['w'+letter],'<u2').reshape(1536,width).T.copy();layer=getattr(att,letter+'_proj')
        layer.weight=torch.nn.Parameter(torch.from_numpy(w).view(torch.bfloat16),requires_grad=False)
        layer.bias=torch.nn.Parameter(expanded('b'+letter,(width,)),requires_grad=False)
    att.rotary_emb=ns['Qwen2RotaryEmbedding'](128,max_position_embeddings=256,base=1e6).to(torch.bfloat16)
    att.to(torch.bfloat16).eval()
    with torch.inference_mode():
        n0=norm(expanded('x',(1,128,1536)))
        ns.update(hidden_states=n0,self=att,bsz=1,q_len=128,kv_seq_len=128,
            position_ids=torch.arange(128,dtype=torch.long).unsqueeze(0))
        execute(range(7,10));out={'n0':arr(n0).reshape(128,1536),
           'qr':arr(ns['query_states']).reshape(128,1536),'kr':arr(ns['key_states']).reshape(128,256)}
        execute(range(10,15))
        out.update(q=arr(ns['query_states'].transpose(1,2).contiguous()).reshape(128,1536),
                   k=arr(ns['key_states'].transpose(1,2).contiguous()).reshape(128,256))
        rope=np.frombuffer(raw['rope'],'<f4').reshape(2,1024,64)[:,:128,:].copy()
        u=rope.view('<u4');rounded=((u+0x7fff+((u>>16)&1))&0xffff0000).view('<f4')
        model.need(all(arr(ns[n]).tobytes()==np.concatenate((rounded[i],rounded[i]),axis=-1).tobytes()
            for i,n in enumerate(('cos','sin'))),'raw/official rope binding')
    return out,ns,execute
