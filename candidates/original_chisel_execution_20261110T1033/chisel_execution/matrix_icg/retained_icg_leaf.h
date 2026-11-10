#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define RETAINED_ICG_ABI_VERSION 65536u
uint32_t retained_icg_abi_version(void);
void* retained_icg_create(void);
int retained_icg_destroy(void* handle);
int retained_icg_drive(void* handle,uint32_t enable,uint32_t test_enable);
int retained_icg_eval(void* handle);
int retained_icg_clock(void* handle,uint32_t level);
int retained_icg_read(void* handle,uint32_t* gated_clock);
int retained_icg_edge_counts(void* handle,uint64_t* positive,uint64_t* negative,
                            uint64_t* gated_positive,uint64_t* gated_negative);
#ifdef __cplusplus
}
#endif
