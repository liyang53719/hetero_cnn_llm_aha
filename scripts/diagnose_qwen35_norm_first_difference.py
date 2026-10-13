"""Independent one-head fixed-recipe replay of a retained norm difference.

No producer, owner execution, new arithmetic policy or numerical gate.
"""
import argparse,json,struct,hashlib
from pathlib import Path
from candidates.qwen35_gdn_prefill.gated_norm.test_model import oracle_head,ref_add,ref_mul,ref_div,ref_sqrt,ref_bf,reference_exp,rms
from candidates.qwen35_35b_gated_norm import payload
def require(condition):
 if not condition:raise ValueError('norm first-difference evidence contract')
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--summary',type=Path,required=True);ap.add_argument('--summary-sha256',required=True)
ap.add_argument('--payload',type=Path,required=True);ap.add_argument('--manifest-sha256',required=True)
ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
require(not args.out.exists() and args.out.resolve().is_relative_to(Path('work').resolve()))
summary_raw=args.summary.read_bytes();require(hashlib.sha256(summary_raw).hexdigest()==args.summary_sha256)
r=json.loads(summary_raw);m=r['tokens'];require(m in (16,128) and r['sources_unchanged'])
obs={x['stage']:x for x in r['observations']}
def raw(rec):
 b=Path(rec['path']).read_bytes();require(len(b)==rec['bytes'] and hashlib.sha256(b).hexdigest()==rec['sha256']);return b
core=raw(obs['chunk']['output']);z=raw(obs['z']['output']);actual=raw(obs['gated_norm']['output']);native=raw(r['gated_norm_reference'])
_,values=payload.load(args.payload,args.manifest_sha256);w=values['layers.0.linear_attn.norm.weight']
i=r['gated_norm_diagnostics']['first_bit_mismatch'];require(type(i) is int and 0<=i<m*4096)
require(actual[i*2:i*2+2]!=native[i*2:i*2+2])
head,lane=divmod(i,128);start=head*256
require(oracle_head(core[start:start+256],z[start:start+256],w)==actual[start:start+256])
x=struct.unpack('<128H',core[start:start+256]);zz=struct.unpack('<128H',z[start:start+256]);ww=struct.unpack('<128I',w)
total=0
for a in x:total=ref_add(total,ref_mul(a<<16,a<<16))
mean=ref_mul(total,rms.word(1/128));eps=ref_add(mean,rms.word(1e-6));inv=ref_div(rms.word(1),ref_sqrt(eps))
normfp=ref_mul(x[lane]<<16,inv);normbf=ref_bf(normfp);weighted=ref_mul(ww[lane],normbf);gate=zz[lane]<<16;e=reference_exp(gate);recip=ref_div(rms.word(1),ref_add(rms.word(1),e));sig=ref_mul(recip,e if gate>>31 else rms.word(1));silu=ref_mul(sig,gate);outfp=ref_mul(weighted,silu);outbf=ref_bf(outfp)
calculated=dict(variance=mean,variance_eps=eps,inverse_rms=inv,normalized_fp32=normfp,normalized_bf16=normbf,weighted_fp32=weighted,silu_fp32=silu,gated_fp32=outfp,output_bf16=outbf)
result={}
for name,bits in calculated.items():
 item=r['gated_norm_intermediates'][name];b=raw(item['record']);isbf=name in ('normalized_bf16','output_bf16');index=head if name in ('variance','variance_eps','inverse_rms') else i
 other=struct.unpack_from('<H' if isbf else '<I',b,index*(2 if isbf else 4))[0]<<(16 if isbf else 0)
 f=lambda n:struct.unpack('<f',struct.pack('<I',n))[0]
 result[name]=dict(bitexact=bits==other,absolute_difference=abs(f(bits)-f(other)),fixed_recipe_bits=hex(bits),native_bits=hex(other))
report=dict(status='ONE_HEAD_INDEPENDENT_FIXED_RECIPE_REPLAY_DIAGNOSTIC',tokens=m,index=i,token=head//32,head=head%32,lane=lane,head_output_matches_actual=True,actual_intermediates_observed=False,new_policy=False,new_threshold=False,nodes=result)
report['summary_sha256']=args.summary_sha256
report['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path('candidates/qwen35_gdn_prefill/gated_norm/test_model.py'),Path('candidates/qwen2_resident_matrix/ffn_public/test_prefix_owners.py'))}
args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
