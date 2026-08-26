// SPDX-License-Identifier: Apache-2.0
// L4 production-lowered INT8 GEMM numerical and cycle measurement.
#define main l2_reference_main_unused
#include "gemmini_l2_multi_tile_os_equivalence.c"
#undef main

int main(void) {
  uint64_t checksum = 0;
  for (int i = 0; i < ROWS; ++i) {
    for (int k = 0; k < DEPTH; ++k) A[i][k] = (elem_t)((i + 2 * k + 1) % 5);
  }
  for (int k = 0; k < DEPTH; ++k) {
    for (int j = 0; j < COLS; ++j) B[k][j] = (elem_t)((3 * k + j + 2) % 5);
  }
  for (int i = 0; i < ROWS; ++i) {
    for (int j = 0; j < COLS; ++j) {
      D[i][j] = (acc_t)((i + j) % 4);
      C_raw[i][j] = 0;
    }
  }

  const uint64_t start = read_cycles();
  run_raw_lowered();
  const uint64_t end = read_cycles();

  for (int i = 0; i < ROWS; ++i) {
    for (int j = 0; j < COLS; ++j) {
      acc_t expected = D[i][j];
      for (int k = 0; k < DEPTH; ++k) expected += A[i][k] * B[k][j];
      const elem_t golden = (elem_t)expected;
      if (C_raw[i][j] != golden) {
        printf("GEMMINI_L4_INT8_GEMM_FAIL i=%d j=%d rtl=%d golden=%d\n",
               i, j, C_raw[i][j], golden);
        exit(1);
      }
      checksum = checksum * 131 + (uint8_t)C_raw[i][j];
    }
  }
  printf("GEMMINI_L4_INT8_GEMM_PASS checksum=%lu cycles=%lu dma_bytes=2195 macs=5814\n",
         checksum, end - start);
  exit(0);
}
