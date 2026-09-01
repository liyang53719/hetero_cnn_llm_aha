#include "hetero_qwen2_device_api.h"
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
struct state_t{int completions=0;int last=-1;};
static void completion(int layer,int status,const char * output,void * opaque){auto * state=static_cast<state_t *>(opaque);if(status){std::fprintf(stderr,"completion failure layer=%d status=%d\n",layer,status);return;}if(layer!=state->last+1||!std::filesystem::exists(std::string(output)+"/final_fp32.bin")){std::fprintf(stderr,"completion order\n");std::exit(5);}state->last=layer;state->completions++;}
int main(int argc,char ** argv){if(argc!=3){std::fprintf(stderr,"usage: input_root output_root\n");return 2;}state_t state;hetero_qwen2_submit_config config{argv[1],argv[2],completion,&state};const int status=hetero_qwen2_submit_588(&config);if(status||state.completions!=28||state.last!=27)return 3;const auto path=std::string(argv[2])+"/layer27/final_fp32.bin";const auto bytes=std::filesystem::file_size(path);if(bytes!=6291456)return 4;std::printf("HETERO_QWEN2_DEVICE_SUBMISSION_PASS commands=588 layers=28 completions=28 final_bytes=%llu in_process=1\n",(unsigned long long)bytes);return 0;}
