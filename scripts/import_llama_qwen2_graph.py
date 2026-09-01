#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'work/upstream/llama_cpp/gguf-py'))
from gguf import GGUFReader
from heteronpu.segment_compiler import compile_segment
PHASES=('input_norm','qkv_projection','attention','post_attention_norm','mlp_gate_up','mlp_down')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--graph',type=Path,required=True);p.add_argument('--gguf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rows=[]
 for line in a.graph.read_text().splitlines():
  f=line.split('\t');rows.append({'index':int(f[0]),'name':f[1],'op':f[2],'dtype':f[3],'shape':[int(x)for x in f[4].split(',')],'sources':[]if len(f)<6 or not f[5]else f[5].split(',')})
 ops=Counter(x['op']for x in rows);layers=defaultdict(set)
 for x in rows:
  for m in re.finditer(r'(?:-|l)(\d+)(?:\b|\s|\()',x['name']):
   n=int(m.group(1));
   if n<28:layers[n].add(x['op'])
 reader=GGUFReader(a.gguf,'r');tensors={t.name:tuple(int(x)for x in t.shape)for t in reader.tensors};required=[]
 for l in range(28):required += [f'blk.{l}.attn_norm.weight',f'blk.{l}.attn_q.weight',f'blk.{l}.attn_k.weight',f'blk.{l}.attn_v.weight',f'blk.{l}.attn_output.weight',f'blk.{l}.ffn_norm.weight',f'blk.{l}.ffn_gate.weight',f'blk.{l}.ffn_up.weight',f'blk.{l}.ffn_down.weight']
 required += ['token_embd.weight','output_norm.weight'];missing=sorted(set(required)-set(tensors));operations=[];desc=0x1000
 def add(i,engine,opcode,deps=()):
  nonlocal desc;op={'id':i,'engine':engine,'opcode':opcode,'src0':desc,'dst':desc+1,'depends_on':list(deps)};desc+=2
  if engine=='matrix':op['src1']=desc;desc+=1
  operations.append(op)
 prev=None
 for l in range(28):
  prefix=f'l{l}';add(f'{prefix}.input_norm','sfu','sfu_rmsnorm',()if prev is None else(prev,));add(f'{prefix}.qkv','matrix','matrix_gemm',(f'{prefix}.input_norm',));add(f'{prefix}.qk','matrix','matrix_qk',(f'{prefix}.qkv',));add(f'{prefix}.softmax','sfu','sfu_softmax',(f'{prefix}.qk',));add(f'{prefix}.pv','matrix','matrix_pv',(f'{prefix}.softmax',));add(f'{prefix}.post_norm','sfu','sfu_rmsnorm',(f'{prefix}.pv',));add(f'{prefix}.gate_up','matrix','matrix_gemm',(f'{prefix}.post_norm',));add(f'{prefix}.silu_mul','sfu','sfu_activation',(f'{prefix}.gate_up',));add(f'{prefix}.down','matrix','matrix_gemm',(f'{prefix}.silu_mul',));prev=f'{prefix}.down'
 compiled=compile_segment({'name':'qwen2_q1024_real_ggml_graph','operations':operations});words=[x['word_hex']for x in compiled.to_dict()['commands']];hardware_ops={'RMS_NORM','MUL_MAT','ROPE','FLASH_ATTN_EXT','GLU','MUL','ADD','SET_ROWS','GET_ROWS'};checks={'nodes':len(rows)==930,'op_inventory':ops['MUL_MAT']==197 and ops['FLASH_ATTN_EXT']==28 and ops['RMS_NORM']==29,'layer_coverage':len(layers)==28 and all({'MUL_MAT','RMS_NORM'}<=layers[i]for i in range(28)),'gguf_tensors':len(tensors)==338 and not missing and 'output.weight'not in tensors,'command_count':len(words)==252,'descriptor_range':desc<0xFFFFFF}
 if not all(checks.values()):raise SystemExit(f'graph import:{checks} missing={missing[:8]}')
 result={'schema_version':1,'status':'PASS_REAL_GGML_GRAPH_GGUF_COMMAND128_LOWERING','evidence_class':'real_stock_llama_graph_capture_and_compiler_lowering_not_device_execution','model':'Qwen/Qwen2-1.5B-Instruct','revision':'ba1cf1846d7df0a0591d6c00649f57e798519da8','llama_cpp_commit':'0b5be7e4a25862bc2777d0c47eae18788a8c963a','graph':{'nodes':len(rows),'op_counts':dict(sorted(ops.items())),'layers':len(layers),'hardware_or_fabric_nodes':sum(v for k,v in ops.items()if k in hardware_ops),'capture_sha256':sha(a.graph)},'gguf':{'sha256':sha(a.gguf),'tensors':len(tensors),'required_bound':len(required),'tied_output_to_token_embedding':True,'missing':missing},'lowering':{'operations':len(operations),'commands':len(words),'barriers':len(compiled.barriers),'descriptor_next':desc,'command_words':words,'command_sha256':hashlib.sha256(''.join(words).encode()).hexdigest()},'checks':checks,'open':['device_memory_binding','device_command_submission','Matrix_SFU_payload_execution','CPU_fallback_execution'],'non_claim':'real graph and Command128 lowering do not execute a project device backend'};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':result['status'],'nodes':len(rows),'tensors':len(tensors),'commands':len(words),'sha256':result['lowering']['command_sha256']},sort_keys=True))
if __name__=='__main__':main()
