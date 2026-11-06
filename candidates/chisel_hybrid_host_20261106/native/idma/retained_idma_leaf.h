#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Actual retained leaf only. No memory implementation, response echo, or clock
   advancement occurs in drive/eval. Caller controls every clock transition. */
void* retained_idma_create(void);
void retained_idma_destroy(void* handle);
/* Additive checked lifecycle and fixed word ABI metadata, V1 transport. */
int retained_idma_destroy_checked(void* handle);
uint32_t retained_idma_abi_version(void);
uint32_t retained_idma_response_words(void);
uint32_t retained_idma_request_words(void);
int retained_idma_drive(void* handle, uint32_t reset_n, uint32_t request_valid,
                       uint64_t source, uint64_t destination, uint32_t length,
                       uint32_t response_ready,
                       const uint32_t* read_response_17,
                       const uint32_t* write_response_17);
int retained_idma_eval(void* handle);
int retained_idma_clock(void* handle, uint32_t clock_level);
int retained_idma_read(void* handle, uint32_t* request_ready,
                      uint32_t* response_valid, uint32_t* response_error,
                      uint32_t* busy, uint32_t* read_request_25,
                      uint32_t* write_request_25);
#ifdef __cplusplus
}
#endif
