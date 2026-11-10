#pragma once
#include <stdint.h>
#define RETAINED_MATRIX_ABI_VERSION 131072u
#define RETAINED_MATRIX_INPUT_WORDS 37u
#define RETAINED_MATRIX_OUTPUT_WORDS 521u
#define RETAINED_MATRIX_CONTRACT_SHA256 "2702823111f4b275fdb56465e82152b107484c4139fe0d1f953251bfd2de9e9a"
#ifdef __cplusplus
extern "C" {
#endif
uint32_t retained_matrix_unseeded_v2_abi_version();
const char* retained_matrix_unseeded_v2_contract_sha256();
void* retained_matrix_unseeded_v2_create();
int retained_matrix_unseeded_v2_destroy(void*);
int retained_matrix_unseeded_v2_drive(void*,const uint32_t*,uint32_t);
int retained_matrix_unseeded_v2_eval(void*);
int retained_matrix_unseeded_v2_clock(void*,uint32_t);
int retained_matrix_unseeded_v2_read(void*,uint32_t*,uint32_t);
int retained_matrix_unseeded_v2_edge_counts(void*,uint64_t*,uint64_t*);
int retained_matrix_unseeded_v2_seed_request(void*,const uint32_t*,uint32_t);
#ifdef __cplusplus
}
#endif
