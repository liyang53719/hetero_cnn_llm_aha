#include "hetero_qwen2_device_api.h"
#include <cstdio>
#include <filesystem>
struct state_t{unsigned lfsr=0x51a9cafe;int completions=0,stalls=0,last=-1;};
static int ready(int,int,void *opaque){auto *s=static_cast<state_t *>(opaque);s->lfsr=(s->lfsr<<1)|(((s->lfsr>>31)^(s->lfsr>>21)^(s->lfsr>>1)^s->lfsr)&1);const int value=(s->lfsr&0x11)!=0;if(!value)s->stalls++;return value;}
static void complete(int layer,int status,const char *output,void *opaque){auto *s=static_cast<state_t *>(opaque);if(status||layer!=s->last+1||!std::filesystem::exists(std::string(output)+"/final_fp32.bin")){std::fprintf(stderr,"completion error\n");std::exit(3);}s->last=layer;s->completions++;}
int main(int argc,char **argv){if(argc!=3)return 2;state_t state;hetero_qwen2_submit_config config{argv[1],argv[2],complete,&state,ready,64};const int status=hetero_qwen2_submit_588(&config);if(status||state.completions!=28||state.stalls<=0)return 4;std::printf("HETERO_QWEN2_BACKPRESSURE_PASS layers=28 groups=7 completions=28 stalls=%d watchdog=64 status=0 checkpoints=28\n",state.stalls);return 0;}
