#define main qwen2_tail_unused_main
#include "qwen2_q1024_layer0_tail_backend.cpp"
#undef main

int main(int argc,char **argv){
  if(argc!=4){std::fprintf(stderr,"usage: input_dir layer27_dir output_dir\n");return 2;}
  const std::string input=argv[1],layer27=argv[2],output=argv[3];constexpr int tokens=1024,hidden=1536,vocab=151936;
  const auto all=load<float>(layer27+"/final_fp32.bin",size_t(tokens)*hidden);std::vector<float>last(hidden);std::copy(all.end()-hidden,all.end(),last.begin());
  const auto norm_weight=load<uint16_t>(input+"/final_norm_weight_bf16.bin",hidden);const auto normalized=rmsnorm(last,norm_weight);std::vector<uint16_t>matrix_input(hidden);for(int index=0;index<hidden;++index)matrix_input[index]=tobf(normalized[index]);
  const auto logits=gemm(matrix_input,1,hidden,vocab,input+"/lm_head_weight_bf16.bin","lm_head");save(output+"/final_norm_fp32.bin",normalized);save(output+"/logits_fp32.bin",logits);
  const int argmax=int(std::max_element(logits.begin(),logits.end())-logits.begin());
  std::printf("QWEN2_Q1024_FINAL_HEAD_BACKEND_PASS final_norm_values=1536 vocab=151936 argmax=%d logits_fnv=%016llx\n",argmax,(unsigned long long)fnv32(logits));return 0;
}
