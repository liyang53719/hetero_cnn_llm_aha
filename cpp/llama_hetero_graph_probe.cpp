#include "llama.h"
#include "ggml-backend.h"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
int main(int argc,char **argv){if(argc!=6)return 2;setenv("HETERO_INPUT_ROOT",argv[3],1);setenv("HETERO_OUTPUT_ROOT",argv[4],1);setenv("HETERO_PROBE_PATH",argv[5],1);ggml_backend_reg_t reg=ggml_backend_load(argv[1]);if(!reg)return 3;ggml_backend_dev_t devices[2]={ggml_backend_reg_dev_get(reg,0),nullptr};llama_model_params mp=llama_model_default_params();mp.devices=devices;mp.n_gpu_layers=-1;llama_model *model=llama_model_load_from_file(argv[2],mp);if(!model)return 4;llama_context_params cp=llama_context_default_params();cp.n_ctx=1024;cp.n_batch=1024;cp.n_ubatch=1024;cp.n_threads=8;cp.n_threads_batch=8;llama_context *ctx=llama_init_from_model(model,cp);if(!ctx)return 5;std::ifstream token_file(std::string(argv[3])+"/../llama_cpp_qwen2_baseline/tokens.txt");if(!token_file)token_file.open("work/results/llama_cpp_qwen2_baseline/tokens.txt");std::vector<llama_token>tokens;int value;while(token_file>>value)tokens.push_back(value);if(tokens.size()!=1024)return 6;llama_batch batch=llama_batch_get_one(tokens.data(),tokens.size());const int decode=llama_decode(ctx,batch);if(decode==0)return 7;llama_free(ctx);llama_model_free(model);if(!std::filesystem::exists(argv[5])||std::filesystem::file_size(argv[5])<32)return 8;std::printf("LLAMA_HETERO_GRAPH_PROBE_PASS decode_failed_explicit=1 cpu_fallback=0 probe=%s\n",argv[5]);ggml_backend_unload(reg);return 0;}
