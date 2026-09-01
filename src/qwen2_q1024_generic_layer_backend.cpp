#define main qwen2_layer0_tail_unused_main
#include "qwen2_q1024_layer0_tail_backend.cpp"
#undef main

#include <limits>

static int64_t round_q46(__int128 value) {
  const bool negative = value < 0;
  const unsigned __int128 magnitude = negative ? (unsigned __int128)(-value) : (unsigned __int128)value;
  const int64_t rounded = int64_t((magnitude + (((unsigned __int128)1) << 45)) >> 46);
  return negative ? -rounded : rounded;
}
static float exp2_pwl256_generic(float x) {
#ifdef QWEN2_ATTENTION_EXP2_EXACT_DIAG
  if (x >= 0.0f) return 1.0f;
  return float(std::exp2(double(x)));
#endif
#ifdef QWEN2_ATTENTION_EXP2_EXT32
  if (x < -32.0f) return 0.0f; if (x >= 0.0f) return 1.0f;
  const int index = std::max(0, std::min(511, int(std::floor(double(x) * 16.0)) + 512));
  const float x0 = float(index) / 16.0f - 32.0f, x1 = x0 + 1.0f / 16.0f;
#else
  if (x < -16.0f) return 0.0f; if (x >= 0.0f) return 1.0f;
#ifdef QWEN2_ATTENTION_EXP2_1024
  const int index = std::max(0, std::min(1023, int(std::floor((double(x) + 16.0) * 64.0))));
  const float x0 = -16.0f + float(index) / 64.0f, x1 = x0 + 1.0f / 64.0f;
#else
  const int index = std::max(0, std::min(255, int(std::floor(double(x) * 16.0)) + 256));
  const float x0 = float(index) / 16.0f - 16.0f, x1 = x0 + 1.0f / 16.0f;
#endif
#endif
  const float y0 = std::exp2(x0), y1 = std::exp2(x1);
  const float slope = float((double(y1) - double(y0)) / double(x1 - x0));
  return add32(mul32(slope, x), float(double(y0) - double(slope) * double(x0)));
}
static float reciprocal_generic(float x) {
  const uint32_t word = bits(x); const int exponent = int((word >> 23) & 255u); const uint32_t fraction = word & 0x7fffffu;
  const float normalized = from_bits((127u << 23) | fraction); const int index = int(fraction >> 19);
  const double x0 = 1.0 + double(index) / 16.0, x1 = x0 + 1.0 / 16.0;
  const float slope = float(((1.0 / x1) - (1.0 / x0)) / (1.0 / 16.0));
  float estimate = add32(mul32(slope, normalized), float(1.0 / x0 - double(slope) * x0));
  estimate = mul32(estimate, add32(2.0f, -mul32(normalized, estimate)));
  float result = mul32(estimate, from_bits(uint32_t(254 - exponent) << 23));
#ifdef QWEN2_ATTENTION_RECIP_NR2
  result = mul32(result, add32(2.0f, -mul32(x, result)));
#endif
  return result;
}

static void run_pre(int layer, const std::string &input, const std::string &predecessor, const std::string &output) {
  constexpr int tokens=1024,hidden=1536,kv=256;
  const auto hidden_input = load<float>(predecessor + "/final_fp32.bin", size_t(tokens) * hidden);
  const auto norm_weight = load<uint16_t>(input + "/input_norm_weight_bf16.bin", hidden);
  const auto normalized = rmsnorm(hidden_input, norm_weight); std::vector<uint16_t> matrix_input(normalized.size());
#pragma omp parallel for schedule(static)
  for (size_t index=0;index<normalized.size();++index) matrix_input[index]=tobf(normalized[index]);
  auto project=[&](const char *name,int columns){
    auto raw_fp32=gemm(matrix_input,tokens,hidden,columns,input+"/"+name+"_weight_bf16.bin",name);std::vector<uint16_t> raw(raw_fp32.size()),biased(raw.size());
    const auto bias=load<float>(input+"/"+name+"_bias_fp32.bin",columns);
#pragma omp parallel for schedule(static)
    for(size_t index=0;index<raw.size();++index){raw[index]=tobf(raw_fp32[index]);biased[index]=tobf(add32(bf(raw[index]),bias[index%columns]));}
    save(output+"/"+name+"_raw.bin",raw);save(output+"/"+name+"_bias.bin",biased);return biased;
  };
  auto q=project("q",hidden),k=project("k",kv),v=project("v",kv);std::vector<uint16_t>qr(q.size()),kr(k.size());
  constexpr int64_t scale=int64_t(1)<<46;int64_t qc[64],qs[64],kc[64],ks[64],bc[64],bs[64];
  for(int dim=0;dim<64;++dim){const double angle=std::pow(1000000.0,-2.0*dim/128.0);bc[dim]=std::llround(std::cos(angle)*scale);bs[dim]=std::llround(std::sin(angle)*scale);qc[dim]=kc[dim]=scale;qs[dim]=ks[dim]=0;}
  auto rotate=[&](const uint16_t *source,uint16_t *destination,int heads,int64_t *cosine,int64_t *sine){for(int head=0;head<heads;++head)for(int dim=0;dim<64;++dim){const float even=bf(source[head*128+dim]),odd=bf(source[head*128+64+dim]),cf=float(double(cosine[dim])/scale),sf=float(double(sine[dim])/scale);destination[head*128+dim]=tobf(add32(mul32(even,cf),-mul32(odd,sf)));destination[head*128+64+dim]=tobf(add32(mul32(even,sf),mul32(odd,cf)));}};
  for(int token=0;token<tokens;++token){rotate(&q[size_t(token)*hidden],&qr[size_t(token)*hidden],12,qc,qs);rotate(&k[size_t(token)*kv],&kr[size_t(token)*kv],2,kc,ks);for(int dim=0;dim<64;++dim){const int64_t nqc=round_q46((__int128)qc[dim]*bc[dim]-(__int128)qs[dim]*bs[dim]),nqs=round_q46((__int128)qc[dim]*bs[dim]+(__int128)qs[dim]*bc[dim]),nkc=round_q46((__int128)kc[dim]*bc[dim]-(__int128)ks[dim]*bs[dim]),nks=round_q46((__int128)kc[dim]*bs[dim]+(__int128)ks[dim]*bc[dim]);qc[dim]=nqc;qs[dim]=nqs;kc[dim]=nkc;ks[dim]=nks;}}
  save(output+"/hidden_input_fp32.bin",hidden_input);save(output+"/input_norm_fp32.bin",normalized);save(output+"/q_rope.bin",qr);save(output+"/k_rope.bin",kr);save(output+"/v_bias.bin",v);
  std::printf("QWEN2_GENERIC_LAYER_PRE_PASS layer=%d commands=21 rows=1024 q_values=%zu k_values=%zu v_values=%zu hidden_in_fnv=%016llx\n",layer,qr.size(),kr.size(),v.size(),(unsigned long long)fnv32(hidden_input));
}

static void run_attention(int layer,const std::string &output){
#ifdef QWEN2_ATTENTION_BLOCK32_DIAG
  constexpr int block=32;
#else
  constexpr int block=128;
#endif
  constexpr int tokens=1024,heads=12,kv_heads=2,dim=128,hidden=1536,kv=256;
  const auto q=load<uint16_t>(output+"/q_rope.bin",size_t(tokens)*hidden),k=load<uint16_t>(output+"/k_rope.bin",size_t(tokens)*kv),v=load<uint16_t>(output+"/v_bias.bin",size_t(tokens)*kv);
  std::vector<float> attention(size_t(tokens)*hidden),m_values(size_t(tokens)*heads),l_values(size_t(tokens)*heads);double max_error=0.0;const float scale=from_bits(0x3db504f3u),log2e=from_bits(0x3fb8aa3bu);
#pragma omp parallel for collapse(2) schedule(dynamic,1) reduction(max:max_error)
  for(int query=0;query<tokens;++query)for(int head=0;head<heads;++head){const int kv_head=head/6;const size_t qb=size_t(query)*hidden+head*dim;float gm=-std::numeric_limits<float>::infinity(),gl=0,go[dim]={};double tm=-std::numeric_limits<double>::infinity(),tl=0,to[dim]={};
    for(int bs=0;bs<=query;bs+=block){const int end=std::min(query+1,bs+block);float bm=-std::numeric_limits<float>::infinity(),bl=0,bo[dim]={};for(int key=bs;key<end;++key){const size_t kb=size_t(key)*kv+kv_head*dim;float dot=0;for(int d=0;d<dim;++d)dot=std::fma(bf(q[qb+d]),bf(k[kb+d]),dot);const float score=mul32(dot,scale);if(key==bs){bm=score;bl=1;for(int d=0;d<dim;++d)bo[d]=bf(v[kb+d]);}else{const float nm=std::max(bm,score),a=exp2_pwl256_generic(mul32(add32(bm,-nm),log2e)),b=exp2_pwl256_generic(mul32(add32(score,-nm),log2e));bl=add32(mul32(bl,a),b);for(int d=0;d<dim;++d)bo[d]=add32(mul32(bo[d],a),mul32(bf(v[kb+d]),b));bm=nm;}const double s=score,nm=std::max(tm,s),a=std::isinf(tm)?0.0:std::exp(tm-nm),b=std::exp(s-nm);tl=tl*a+b;for(int d=0;d<dim;++d)to[d]=to[d]*a+double(bf(v[kb+d]))*b;tm=nm;}
      if(bs==0){gm=bm;gl=bl;std::copy(bo,bo+dim,go);}else{const float nm=std::max(gm,bm),a=exp2_pwl256_generic(mul32(add32(gm,-nm),log2e)),b=exp2_pwl256_generic(mul32(add32(bm,-nm),log2e));gl=add32(mul32(gl,a),mul32(bl,b));for(int d=0;d<dim;++d)go[d]=add32(mul32(go[d],a),mul32(bo[d],b));gm=nm;}}
    const float inverse=reciprocal_generic(gl);m_values[size_t(query)*heads+head]=gm;l_values[size_t(query)*heads+head]=gl;for(int d=0;d<dim;++d){const float value=mul32(go[d],inverse);attention[qb+d]=value;max_error=std::max(max_error,std::abs(double(value)-to[d]/tl));}}
  save(output+"/attention_fp32.bin",attention);save(output+"/attention_m_fp32.bin",m_values);save(output+"/attention_l_fp32.bin",l_values);
  std::printf("QWEN2_GENERIC_LAYER_ATTENTION_PASS layer=%d commands=21 rows=1024 updates=6297600 merges=43008 score_matrix_bytes=0 max_error=%.9g attention_fnv=%016llx\n",layer,max_error,(unsigned long long)fnv32(attention));if(max_error>0.002)std::exit(5);
}

static void run_attention_blocked_rtl(int layer,const std::string &output){
  constexpr int tokens=1024,heads=12,dim=128,hidden=1536,kv=256,block=128,tile=32;
  const auto q=load<uint16_t>(output+"/q_rope.bin",size_t(tokens)*hidden),k=load<uint16_t>(output+"/k_rope.bin",size_t(tokens)*kv),v=load<uint16_t>(output+"/v_bias.bin",size_t(tokens)*kv);
  std::vector<float> attention(size_t(tokens)*hidden),m_values(size_t(tokens)*heads),l_values(size_t(tokens)*heads);double max_error=0.0;const float scale=from_bits(0x3db504f3u),log2e=from_bits(0x3fb8aa3bu);
  auto merge=[&](float am,float al,float *ao,float bm,float bl,const float *bo,float &om,float &ol,float *oo){if(al==0){om=bm;ol=bl;std::copy(bo,bo+dim,oo);return;}if(bl==0){om=am;ol=al;std::copy(ao,ao+dim,oo);return;}om=std::max(am,bm);const float alpha=exp2_pwl256_generic(mul32(add32(am,-om),log2e)),beta=exp2_pwl256_generic(mul32(add32(bm,-om),log2e));ol=add32(mul32(al,alpha),mul32(bl,beta));for(int d=0;d<dim;++d)oo[d]=add32(mul32(ao[d],alpha),mul32(bo[d],beta));};
#pragma omp parallel for collapse(2) schedule(dynamic,1) reduction(max:max_error)
  for(int query=0;query<tokens;++query)for(int head=0;head<heads;++head){const int kv_head=head/6;const size_t qb=size_t(query)*hidden+head*dim;float block_m[8],block_l[8],block_o[8][dim];int block_count=0;double tm=-std::numeric_limits<double>::infinity(),tl=0,to[dim]={};
    for(int bs=0;bs<=query;bs+=block){const int bend=std::min(query+1,bs+block);float tile_m_values[4],tile_l_values[4],tile_o_values[4][dim];int tile_count=0;
      for(int ts=bs;ts<bend;ts+=tile){const int tend=std::min(bend,ts+tile),count=tend-ts;float scores[tile]={},weights[tile]={};float tile_m=-std::numeric_limits<float>::infinity();
        for(int lane=0;lane<count;++lane){const int key=ts+lane;const size_t kb=size_t(key)*kv+kv_head*dim;float dot=0;for(int d=0;d<dim;++d)dot=std::fma(bf(q[qb+d]),bf(k[kb+d]),dot);scores[lane]=mul32(dot,scale);tile_m=std::max(tile_m,scores[lane]);const double s=scores[lane],nm=std::max(tm,s),a=std::isinf(tm)?0.0:std::exp(tm-nm),b=std::exp(s-nm);tl=tl*a+b;for(int d=0;d<dim;++d)to[d]=to[d]*a+double(bf(v[kb+d]))*b;tm=nm;}
        for(int lane=0;lane<count;++lane)weights[lane]=exp2_pwl256_generic(mul32(add32(scores[lane],-tile_m),log2e));float reduce[tile];for(int lane=0;lane<tile;++lane)reduce[lane]=lane<count?weights[lane]:0.0f;for(int width=tile;width>1;width>>=1)for(int lane=0;lane<width/2;++lane)reduce[lane]=add32(reduce[lane*2],reduce[lane*2+1]);const float tile_l=reduce[0];float tile_o[dim]={};
        for(int d=0;d<dim;++d){float accumulator=0;for(int lane=0;lane<count;++lane){const uint16_t hi=tobf(weights[lane]);accumulator=std::fma(bf(hi),bf(v[size_t(ts+lane)*kv+kv_head*dim+d]),accumulator);}for(int lane=0;lane<count;++lane){const uint16_t hi=tobf(weights[lane]),lo=tobf(add32(weights[lane],-bf(hi)));accumulator=std::fma(bf(lo),bf(v[size_t(ts+lane)*kv+kv_head*dim+d]),accumulator);}tile_o[d]=accumulator;}
        tile_m_values[tile_count]=tile_m;tile_l_values[tile_count]=tile_l;std::copy(tile_o,tile_o+dim,tile_o_values[tile_count]);tile_count++;
      }
      while(tile_count>1){int next=0;for(int index=0;index<tile_count;index+=2){if(index+1<tile_count){float nm,nl,no[dim];merge(tile_m_values[index],tile_l_values[index],tile_o_values[index],tile_m_values[index+1],tile_l_values[index+1],tile_o_values[index+1],nm,nl,no);tile_m_values[next]=nm;tile_l_values[next]=nl;std::copy(no,no+dim,tile_o_values[next]);}else{tile_m_values[next]=tile_m_values[index];tile_l_values[next]=tile_l_values[index];if(next!=index)std::copy(tile_o_values[index],tile_o_values[index]+dim,tile_o_values[next]);}next++;}tile_count=next;}
      block_m[block_count]=tile_m_values[0];block_l[block_count]=tile_l_values[0];std::copy(tile_o_values[0],tile_o_values[0]+dim,block_o[block_count]);block_count++;
    }
    while(block_count>1){int next=0;for(int index=0;index<block_count;index+=2){if(index+1<block_count){float nm,nl,no[dim];merge(block_m[index],block_l[index],block_o[index],block_m[index+1],block_l[index+1],block_o[index+1],nm,nl,no);block_m[next]=nm;block_l[next]=nl;std::copy(no,no+dim,block_o[next]);}else{block_m[next]=block_m[index];block_l[next]=block_l[index];if(next!=index)std::copy(block_o[index],block_o[index]+dim,block_o[next]);}next++;}block_count=next;}
    const float gm=block_m[0],gl=block_l[0];float *go=block_o[0];
    const float inverse=reciprocal_generic(gl);m_values[size_t(query)*heads+head]=gm;l_values[size_t(query)*heads+head]=gl;for(int d=0;d<dim;++d){const float value=mul32(go[d],inverse);attention[qb+d]=value;max_error=std::max(max_error,std::abs(double(value)-to[d]/tl));}
  }
  save(output+"/attention_fp32.bin",attention);save(output+"/attention_m_fp32.bin",m_values);save(output+"/attention_l_fp32.bin",l_values);
  std::printf("QWEN2_GENERIC_LAYER_BLOCKED_RTL_ATTENTION_PASS layer=%d commands=21 rows=1024 updates=6297600 tile32=1 merges=43008 score_matrix_bytes=0 max_error=%.9g attention_fnv=%016llx\n",layer,max_error,(unsigned long long)fnv32(attention));if(max_error>0.002)std::exit(5);
}

int main(int argc,char **argv){
  if(argc!=6){std::fprintf(stderr,"usage: stage layer input_dir predecessor_dir output_dir\n");return 2;}const std::string stage=argv[1],input=argv[3],predecessor=argv[4],output=argv[5];const int layer=std::stoi(argv[2]);validate_commands(input);constexpr int tokens=1024,hidden=1536,intermediate=8960;
  if(stage=="pre")run_pre(layer,input,predecessor,output);else if(stage=="attention"){
#ifdef QWEN2_ATTENTION_BLOCKED_RTL
    run_attention_blocked_rtl(layer,output);
#else
    run_attention(layer,output);
#endif
  }else if(stage=="oproj"){const auto probabilities=load<float>(output+"/attention_fp32.bin",size_t(tokens)*hidden);std::vector<uint16_t>mi(probabilities.size());
#pragma omp parallel for schedule(static)
    for(size_t i=0;i<mi.size();++i)mi[i]=tobf(probabilities[i]);const auto projected=gemm(mi,tokens,hidden,hidden,input+"/oproj_weight_bf16.bin","oproj");const auto original=load<float>(output+"/hidden_input_fp32.bin",projected.size());std::vector<float>residual(projected.size());
#pragma omp parallel for schedule(static)
    for(size_t i=0;i<residual.size();++i)residual[i]=add32(projected[i],original[i]);const auto nw=load<uint16_t>(input+"/post_norm_weight_bf16.bin",hidden);const auto normalized=rmsnorm(residual,nw);save(output+"/oproj_fp32.bin",projected);save(output+"/residual1_fp32.bin",residual);save(output+"/postnorm_fp32.bin",normalized);std::printf("QWEN2_GENERIC_LAYER_OPROJ_PASS layer=%d values=%zu\n",layer,projected.size());
  }else if(stage=="gate"||stage=="up"){const auto normalized=load<float>(output+"/postnorm_fp32.bin",size_t(tokens)*hidden);std::vector<uint16_t>mi(normalized.size());
#pragma omp parallel for schedule(static)
    for(size_t i=0;i<mi.size();++i)mi[i]=tobf(normalized[i]);const auto values=gemm(mi,tokens,hidden,intermediate,input+"/"+stage+"_weight_bf16.bin",stage.c_str());save(output+"/"+stage+"_fp32.bin",values);if(stage=="up"){const auto gate=load<float>(output+"/gate_fp32.bin",values.size());const auto rom=load<uint16_t>(input+"/silu_lut_fp16.bin",128);std::vector<uint16_t>product(values.size());
#pragma omp parallel for schedule(static)
      for(size_t i=0;i<product.size();++i)product[i]=fused_silu(tobf(gate[i]),tobf(values[i]),rom);save(output+"/silu_product_bf16.bin",product);}std::printf("QWEN2_GENERIC_LAYER_%s_PASS layer=%d values=%zu\n",stage.c_str(),layer,values.size());
  }else if(stage=="down"){const auto product=load<uint16_t>(output+"/silu_product_bf16.bin",size_t(tokens)*intermediate);const auto down=gemm(product,tokens,intermediate,hidden,input+"/down_weight_bf16.bin","down");const auto residual=load<float>(output+"/residual1_fp32.bin",down.size());std::vector<float>final(down.size());
#pragma omp parallel for schedule(static)
    for(size_t i=0;i<final.size();++i)final[i]=add32(down[i],residual[i]);save(output+"/down_fp32.bin",down);save(output+"/final_fp32.bin",final);std::printf("QWEN2_GENERIC_LAYER_DOWN_PASS layer=%d values=%zu final_fnv=%016llx\n",layer,final.size(),(unsigned long long)fnv32(final));
  }else{return 2;}return 0;
}
