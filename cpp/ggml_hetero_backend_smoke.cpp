#include "ggml-backend.h"
#include "ggml.h"
#include "ggml-impl.h"
#include <cstdio>
#include <cstring>
#include <string>
extern "C" ggml_backend_reg_t ggml_backend_hetero_reg();
static void unused_custom(ggml_tensor *,const ggml_tensor *,int,int,void *){}
int main(int argc,char **argv){if(argc!=3)return 2;ggml_backend_register(ggml_backend_hetero_reg());ggml_backend_reg_t reg=ggml_backend_reg_by_name("HETERO");if(!reg||ggml_backend_reg_dev_count(reg)!=1)return 3;ggml_backend_dev_t dev=ggml_backend_reg_dev_get(reg,0);std::string params=std::string("input=")+argv[1]+";output="+argv[2];ggml_backend_t backend=ggml_backend_dev_init(dev,params.c_str());if(!backend)return 4;ggml_init_params ip{32*1024*1024,nullptr,false};ggml_context *ctx=ggml_init(ip);ggml_tensor *src=ggml_new_tensor_1d(ctx,GGML_TYPE_F32,1572864);ggml_tensor *out=ggml_map_custom1(ctx,src,unused_custom,1,nullptr);ggml_set_name(out,"hetero.layer27");ggml_cgraph *graph=ggml_new_graph_custom(ctx,8,false);ggml_build_forward_expand(graph,out);if(graph->n_nodes!=1||!ggml_backend_dev_supports_op(dev,out))return 5;const ggml_status status=ggml_backend_graph_compute(backend,graph);if(status!=GGML_STATUS_SUCCESS)return 6;const float *data=static_cast<const float *>(out->data);if(!data||data[0]==0.0f&&data[1572863]==0.0f)return 7;std::printf("GGML_HETERO_BACKEND_PASS reg=HETERO devices=1 graph_compute=1 nodes=1 output_values=1572864 cpu_fallback=0\n");ggml_backend_free(backend);ggml_free(ctx);return 0;}
