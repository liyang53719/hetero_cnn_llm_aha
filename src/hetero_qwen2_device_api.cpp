#define QWEN2_ATTENTION_BLOCKED_RTL
#define QWEN2_ATTENTION_EXP2_EXT32
#define QWEN2_GENERIC_MAIN qwen2_generic_layer_embedded_main
#include "qwen2_q1024_generic_layer_backend.cpp"
#undef QWEN2_GENERIC_MAIN
#include "hetero_qwen2_device_api.h"
#include <filesystem>

static int run_stage(const std::string & stage,int layer,const std::string & input,const std::string & predecessor,const std::string & output){
  std::string layer_text=std::to_string(layer);char * argv[6];argv[0]=const_cast<char *>("hetero-device");argv[1]=const_cast<char *>(stage.c_str());argv[2]=layer_text.data();argv[3]=const_cast<char *>(input.c_str());argv[4]=const_cast<char *>(predecessor.c_str());argv[5]=const_cast<char *>(output.c_str());return qwen2_generic_layer_embedded_main(6,argv);
}
extern "C" int hetero_qwen2_submit_588(const hetero_qwen2_submit_config * config){
  if(!config||!config->input_root||!config->output_root)return 2;const std::string inputs=config->input_root,outputs=config->output_root;std::filesystem::create_directories(outputs);
  for(int layer=0;layer<28;++layer){const std::string input=inputs+"/layer"+std::to_string(layer),output=outputs+"/layer"+std::to_string(layer),predecessor=layer==0?inputs+"/embedding":outputs+"/layer"+std::to_string(layer-1);std::filesystem::create_directories(output);for(const char * stage:{"pre","attention","oproj","gate","up","down"}){const int status=run_stage(stage,layer,input,predecessor,output);if(status){if(config->completion_cb)config->completion_cb(layer,status,output.c_str(),config->completion_user_data);return status;}}if(config->completion_ready_cb){const int limit=config->max_completion_waits>0?config->max_completion_waits:1024;int attempt=0;while(!config->completion_ready_cb(layer,attempt,config->completion_user_data)){if(++attempt>=limit){if(config->completion_cb)config->completion_cb(layer,6,output.c_str(),config->completion_user_data);return 6;}}}if(config->completion_cb)config->completion_cb(layer,0,output.c_str(),config->completion_user_data);}
  {constexpr int tokens=1024,hidden=1536,vocab=151936;const auto all=load<float>(outputs+"/layer27/final_fp32.bin",size_t(tokens)*hidden);std::vector<float>last(hidden);std::copy(all.end()-hidden,all.end(),last.begin());const auto nw=load<uint16_t>(inputs+"/final_head/final_norm_weight_bf16.bin",hidden);const auto normalized=rmsnorm(last,nw);std::vector<uint16_t>mi(hidden);for(int i=0;i<hidden;++i)mi[i]=tobf(normalized[i]);const auto logits=gemm(mi,1,hidden,vocab,inputs+"/final_head/lm_head_weight_bf16.bin","lm_head");std::filesystem::create_directories(outputs+"/final");save(outputs+"/final/final_norm_fp32.bin",normalized);save(outputs+"/final/logits_fp32.bin",logits);}
  return 0;
}
