#pragma once
#ifdef __cplusplus
extern "C" {
#endif
typedef void (*hetero_qwen2_completion_cb)(int layer, int status, const char * output_dir, void * user_data);
typedef int (*hetero_qwen2_completion_ready_cb)(int layer, int attempt, void * user_data);
typedef struct {
  const char * input_root;
  const char * output_root;
  hetero_qwen2_completion_cb completion_cb;
  void * completion_user_data;
  hetero_qwen2_completion_ready_cb completion_ready_cb;
  int max_completion_waits;
} hetero_qwen2_submit_config;
int hetero_qwen2_submit_588(const hetero_qwen2_submit_config * config);
#ifdef __cplusplus
}
#endif
