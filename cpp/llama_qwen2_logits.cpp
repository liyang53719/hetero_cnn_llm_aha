#include "llama.h"
#include "ggml.h"
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <set>
#include <string>
#include <vector>
struct capture_data{std::ofstream out;std::set<std::string>seen;int index=0;bool enabled=false;explicit capture_data(const char*p):out(p){}};
static bool capture_cb(ggml_tensor*t,bool ask,void*opaque){if(!ask)return false;auto*d=static_cast<capture_data*>(opaque);if(!d->enabled)return false;std::string name=ggml_get_name(t);std::string key=name+"|"+ggml_op_name(t->op);if(!d->seen.insert(key).second)return false;d->out<<d->index++<<'\t'<<(name.empty()?"_":name)<<'\t'<<ggml_op_name(t->op)<<'\t'<<ggml_type_name(t->type)<<'\t';for(int i=0;i<GGML_MAX_DIMS;i++){if(i)d->out<<',';d->out<<t->ne[i];}d->out<<'\t';bool first=true;for(int i=0;i<GGML_MAX_SRC;i++)if(t->src[i]){if(!first)d->out<<',';std::string s=ggml_get_name(t->src[i]);d->out<<(s.empty()?"_":s);first=false;}d->out<<'\n';return false;}
int main(int argc,char**argv){if(argc!=5){std::cerr<<"usage: model.gguf tokens.txt logits.bin graph.tsv\n";return 2;}ggml_backend_load_all();llama_model_params mp=llama_model_default_params();mp.n_gpu_layers=0;llama_model*model=llama_model_load_from_file(argv[1],mp);if(!model)return 3;std::ifstream ti(argv[2]);std::vector<llama_token>tokens;int x;while(ti>>x)tokens.push_back((llama_token)x);if(tokens.size()!=1024){std::cerr<<"tokens="<<tokens.size()<<"\n";return 4;}capture_data capture(argv[4]);llama_context_params cp=llama_context_default_params();cp.n_ctx=1024;cp.n_batch=1024;cp.n_ubatch=1024;cp.n_threads=8;cp.n_threads_batch=8;cp.no_perf=false;cp.cb_eval=capture_cb;cp.cb_eval_user_data=&capture;llama_context*ctx=llama_init_from_model(model,cp);if(!ctx)return 5;capture.enabled=true;llama_batch batch=llama_batch_get_one(tokens.data(),tokens.size());if(llama_decode(ctx,batch)!=0)return 6;const llama_vocab*vocab=llama_model_get_vocab(model);int n=llama_vocab_n_tokens(vocab);const float*logits=llama_get_logits(ctx);if(!logits||n!=151936){std::cerr<<"vocab="<<n<<"\n";return 7;}std::ofstream out(argv[3],std::ios::binary);out.write(reinterpret_cast<const char*>(logits),size_t(n)*sizeof(float));int argmax=int(std::max_element(logits,logits+n)-logits);uint64_t fnv=1469598103934665603ULL;for(int i=0;i<n;i++){uint32_t u;std::memcpy(&u,&logits[i],4);for(int b=0;b<4;b++){fnv^=(u>>(8*b))&0xff;fnv*=1099511628211ULL;}}std::cout<<"LLAMA_QWEN2_LOGITS_PASS tokens=1024 ubatch=1024 capture=decode_only layers=28 vocab="<<n<<" argmax="<<argmax<<" graph_nodes="<<capture.index<<" logits_fnv64="<<std::hex<<fnv<<std::dec<<"\n";llama_perf_context_print(ctx);llama_free(ctx);llama_model_free(model);return 0;}
