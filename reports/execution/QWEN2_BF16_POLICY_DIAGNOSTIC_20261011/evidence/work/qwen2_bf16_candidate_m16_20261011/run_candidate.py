from pathlib import Path
import hashlib,importlib.util,json,subprocess,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/qwen2_block_recipe_m16_release_20261011'
NATIVE=ROOT/'work/qwen2_layer0_model_gate_cold_m16_20261011'
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=load(ROOT/'scripts/qwen2_block_recipe_model.py','recipe')
n=load(ROOT/'scripts/qwen2_layer0_model_gate.py','native')
receipt=r.validate_recipe_receipt(ROOT,BASE);native=r.validate_native_receipt(ROOT,NATIVE,receipt)
source=(BASE/'generated/software_recipe.cpp').read_text()
changes=[]
def replace(old,new,label,evidence):
 global source
 if source.count(old)!=1:raise ValueError('candidate patch boundary '+label)
 source=source.replace(old,new)
 changes.append(dict(label=label,original=old,replacement=new,official_source=evidence))
replace('bf(mul(mul(get(in,size_t(t)*H+i),inv),get(gamma,i)))','bf(mul(bf(mul(get(in,size_t(t)*H+i),inv)),get(gamma,i)))','RMS normalized BF16 before gamma','modeling_qwen2.py:85-90')
replace('bias>=0?add(sums[j],get(bias,col+j)):sums[j]','bf(bias>=0?add(sums[j],get(bias,col+j)):sums[j])','Dense output BF16 after unchanged bias order','modeling_qwen2.py:228-231,255-257,313; BF16 nn.Linear output')
replace('c=get(OFF_COS,size_t(t)*HD/2+j),s=get(OFF_SIN,size_t(t)*HD/2+j)','c=bf(get(OFF_COS,size_t(t)*HD/2+j)),s=bf(get(OFF_SIN,size_t(t)*HD/2+j))','RoPE table BF16 materialization','modeling_qwen2.py:119-126')
replace('put(out,ix,add(mul(x,c),-mul(y,s)));put(out,ix+HD/2,add(mul(x,s),mul(y,c)));','put(out,ix,bf(add(bf(mul(x,c)),-bf(mul(y,s)))));put(out,ix+HD/2,bf(add(bf(mul(x,s)),bf(mul(y,c)))));','RoPE BF16 products then BF16 sum','modeling_qwen2.py:162-163')
replace('p[k]=mul(sum,float(1.0/std::sqrt(double(HD))));max=std::max(max,p[k]);','p[k]=bf(mul(bf(sum),float(1.0/std::sqrt(double(HD)))));candidateScores[(size_t(h)*tokens+t)*tokens+k]=p[k];candidateLogits[(size_t(h)*tokens+t)*tokens+k]=k<=t?p[k]:fp(0xff7f0000u);if(k<=t)max=std::max(max,p[k]);','QK BF16 dot result then BF16 scaled result','modeling_qwen2.py:283')
replace('put(OFF_ATT,size_t(t)*H+h*HD+j,sum);','put(OFF_ATT,size_t(t)*H+h*HD+j,bf(sum));','PV output BF16 after unchanged FP32 accumulation','modeling_qwen2.py:302')
replace('put(OFF_R,i,add(get(OFF_X,i),get(OFF_O,i)))','put(OFF_R,i,bf(add(get(OFF_X,i),get(OFF_O,i))))','Attention residual BF16','modeling_qwen2.py:776')
replace('put(OFF_ACT,i,mul(mul(sig,g),get(OFF_UP,i)))','candidateSilu[i]=bf(mul(sig,g));put(OFF_ACT,i,bf(mul(candidateSilu[i],get(OFF_UP,i))))','SiLU output BF16 then product BF16','modeling_qwen2.py:179-180')
replace('put(OFF_Y,i,add(get(OFF_R,i),get(OFF_DOWN,i)))','put(OFF_Y,i,bf(add(get(OFF_R,i),get(OFF_DOWN,i))))','Final residual BF16','modeling_qwen2.py:782')
# Read-only observers. Extra masked-future scores are diagnosis only; they never
# participate in the causal max, probability or PV calculation.
replace('  std::vector<float> reference; unsigned tokens;','  std::vector<float> reference; unsigned tokens;\n  std::vector<float> candidateScores,candidateLogits,candidateSoftmax,candidateProb,candidateSilu;','Additional software diagnostic buffers','diagnostic_only_not_hardware')
replace('void attention(){std::vector<float> p(tokens);','void attention(){candidateScores.resize(size_t(HEADS)*tokens*tokens);candidateLogits.resize(candidateScores.size());candidateSoftmax.assign(candidateScores.size(),0);candidateProb.assign(candidateScores.size(),0);std::vector<float> p(tokens);','Attention observer allocation','diagnostic_only_not_hardware')
replace('for(unsigned k=0;k<=t;k++){float parts[16]={};','for(unsigned k=0;k<tokens;k++){float parts[16]={};','Observe masked-future score values without consuming them','diagnostic_only_not_hardware')
replace('float inv=1.0f/sum;\n    for(int j=0;j<HD;j++)','float inv=1.0f/sum;\n    for(unsigned k=0;k<=t;k++){candidateSoftmax[(size_t(h)*tokens+t)*tokens+k]=mul(p[k],inv);candidateProb[(size_t(h)*tokens+t)*tokens+k]=bf(mul(p[k],inv));}\n    for(int j=0;j<HD;j++)','Observe FP32 softmax and BF16 probability','diagnostic_only_not_hardware')
replace('  void computeReference(){','  void computeReference(){candidateSilu.resize(size_t(tokens)*F);','Observe SiLU materialization','diagnostic_only_not_hardware')
replace('  model.computeReference();','''  model.computeReference();
  auto dump=[&](const char* name,const std::vector<float>& values){std::ofstream f(std::filesystem::path(argv[3])/(std::string(name)+".f32le"),std::ios::binary);f.write(reinterpret_cast<const char*>(values.data()),values.size()*4);need(bool(f),"candidate diagnostic write failed");};
  dump("scores",model.candidateScores);dump("logits",model.candidateLogits);dump("softmax_fp32",model.candidateSoftmax);dump("prob",model.candidateProb);dump("silu",model.candidateSilu);''','Export diagnostic tensors','diagnostic_only_not_hardware')
source='// WORK-ONLY CANDIDATE. Not the frozen canonical recipe or implemented hardware.\n'+source
cpp=OUT/'candidate.cpp';cpp.write_text(source)
(OUT/'block_layout.h').write_bytes((BASE/'generated/block_layout.h').read_bytes())
command=['g++',*r.FLAGS,str(cpp),'-o',str(OUT/'candidate')]
subprocess.run(command,check=True,capture_output=True,text=True,timeout=120)
stages=OUT/'stages';stages.mkdir()
start=time.monotonic();run=subprocess.run([str(OUT/'candidate'),str(BASE/'readonly_arena.f32le'),'16',str(stages)],capture_output=True,text=True,timeout=60);elapsed=time.monotonic()-start
(OUT/'run.log').write_text(run.stdout+run.stderr)
if run.returncode:raise ValueError(run.stderr)
policy=n.load_policy(ROOT);comparisons={}
for kind in ('native','independent'):
 entries=[]
 for name in (*r.STAGE_NAMES,'scores','logits','softmax_fp32','prob','silu'):
  entry=native['modes']['bf16']['phases'][0]['stages'][name]
  ref=np.fromfile(NATIVE/entry[kind+'_file'],dtype='<f4')
  path=stages/(f'phase_{r.STAGE_NAMES.index(name)}_{name}_recipe.f32le' if name in r.STAGE_NAMES else name+'.f32le')
  actual=np.fromfile(path,dtype='<f4')
  metrics=n.compare(actual,ref);verdict=n.stage_verdict(name,metrics,'bf16',policy)
  entries.append(dict(name=name,metrics=metrics,verdict=verdict,sha256=r.file_sha(path)))
 comparisons[kind]=entries
# BF16 table conversion should be an independently checked input, not native injection.
layout=json.loads((BASE/'generated/layout.json').read_text());regions={x['name']:x for x in layout['regions']}
a=np.memmap(BASE/'readonly_arena.f32le',dtype='<f4',mode='r')
tables={}
for name in ('cos','sin'):
 off=regions[name]['offset']//4;array=a[off:off+16*64].reshape(16,64).copy();array=n.bf16(array);array=np.concatenate([array,array],axis=1)
 actual=np.fromfile(NATIVE/'bf16/phase_0'/f'native_{name}.f32le',dtype='<f4').reshape(16,128)
 tables[name]=dict(bit_exact=np.array_equal(array.view('<u4'),actual.view('<u4')),max_abs=float(np.max(np.abs(array-actual))))
result=dict(status='CANDIDATE_ONLY_NOT_IMPLEMENTED',tokens=16,elapsed_seconds=elapsed,policy=policy,
 changes=changes,comparisons=comparisons,table_check=tables,canonical_result_sha256=r.file_sha(BASE/'RESULT.json'),native_result_sha256=r.file_sha(NATIVE/'RESULT.json'),
 candidate_cpp_sha256=r.file_sha(cpp),candidate_binary_sha256=r.file_sha(OUT/'candidate'),compile_command=command,
 retains_dense_increasing_K_FMA=True,retains_original_FP32_bias_order=True,retains_QK_16_partial_FP32_reduction=True,retains_exp_poly7=True,
 observation_only_extra_future_scores=True,rtl_executed=False,hardware_cycles=None,hardware_utilization=None,
 final_source_sha256={p:r.file_sha(ROOT/p) for p in ['scripts/qwen2_block_recipe_model.py','tests/test_qwen2_block_recipe_model.py']})
(OUT/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
for kind,entries in comparisons.items():
 print(kind,'failed',[(e['name'],e['metrics']['max_abs'],e['metrics']['mean_abs']) for e in entries if e['verdict']['passed'] is False])
 print(kind,'y',next(e for e in entries if e['name']=='y')['metrics'])
print('tables',tables,'seconds',elapsed)
