// SPDX-License-Identifier: Apache-2.0
// L2 retained-RocketTile equivalence: official Gemmini C macros versus the
// exact raw CUSTOM_3 payloads emitted by gemmini_rocc_lowering.py.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "include/gemmini_testutils.h"

#define M 3
#define N 5
#define K 7

static elem_t A[M][K] row_align(1) = {
    {1, 2, 3, 4, 1, 2, 3},
    {2, 1, 4, 3, 2, 1, 4},
    {3, 2, 1, 2, 3, 4, 1},
};
static elem_t B[K][N] row_align(1) = {
    {1, 2, 3, 1, 2}, {2, 1, 2, 3, 1}, {3, 2, 1, 2, 3},
    {1, 3, 2, 1, 2}, {2, 2, 3, 2, 1}, {3, 1, 1, 3, 2},
    {1, 2, 2, 1, 3},
};
static elem_t D[M][N] row_align(1) = {
    {1, 0, 2, 1, 3}, {0, 2, 1, 3, 1}, {2, 1, 0, 2, 1},
};
static elem_t C_macro[M][N] row_align(1);
static elem_t C_raw[M][N] row_align(1);
static elem_t gold[M][N] row_align(1);

enum {
  A_SP = 0,
  B_SP = DIM,
  D_SP = 2 * DIM,
  C_SP = 3 * DIM,
};

#define PACK_LOCAL(addr, cols, rows) \
  (((uint64_t)(rows) << (ADDR_LEN + 16)) | ((uint64_t)(cols) << ADDR_LEN) | (uint32_t)(addr))
#define RAW_CMD(funct, rs1_value, rs2_value) \
  ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC, (uint64_t)(rs1_value), (uint64_t)(rs2_value), funct)

static void run_official(void) {
  gemmini_config_ex(OUTPUT_STATIONARY, NO_ACTIVATION, 0);
  gemmini_config_st(N * sizeof(elem_t));
  gemmini_config_ld(K * sizeof(elem_t));
  gemmini_extended_mvin(A, A_SP, K, M);
  gemmini_config_ld(N * sizeof(elem_t));
  gemmini_extended_mvin(B, B_SP, N, K);
  gemmini_config_ld(N * sizeof(elem_t));
  gemmini_extended_mvin(D, D_SP, N, M);
  gemmini_extended_preload(D_SP, C_SP, N, M, N, M);
  gemmini_extended_compute_preloaded(A_SP, B_SP, K, M, N, K);
  gemmini_extended_mvout(C_macro, C_SP, N, M);
  gemmini_fence();
}

static void run_raw_lowered(void) {
  const uint64_t scale_identity = UINT64_C(0x3f800000);
  const uint64_t config_ex_rs1 = (scale_identity << 32) | (UINT64_C(1) << 16);
  const uint64_t config_ex_rs2 = UINT64_C(1) << 48;
  const uint64_t config_ld_rs1 = (scale_identity << 32) | (UINT64_C(DIM) << 16) |
                                 (UINT64_C(1) << 8) | CONFIG_LD;
  const uint64_t config_st_rs1 = CONFIG_ST;

  RAW_CMD(k_CONFIG, config_ex_rs1, config_ex_rs2);
  RAW_CMD(k_CONFIG, config_st_rs1, (scale_identity << 32) | (N * sizeof(elem_t)));
  RAW_CMD(k_CONFIG, config_ld_rs1, K * sizeof(elem_t));
  RAW_CMD(k_MVIN, (uintptr_t)A, PACK_LOCAL(A_SP, K, M));
  RAW_CMD(k_CONFIG, config_ld_rs1, N * sizeof(elem_t));
  RAW_CMD(k_MVIN, (uintptr_t)B, PACK_LOCAL(B_SP, N, K));
  RAW_CMD(k_CONFIG, config_ld_rs1, N * sizeof(elem_t));
  RAW_CMD(k_MVIN, (uintptr_t)D, PACK_LOCAL(D_SP, N, M));
  RAW_CMD(k_PRELOAD, PACK_LOCAL(D_SP, N, M), PACK_LOCAL(C_SP, N, M));
  RAW_CMD(k_COMPUTE_PRELOADED, PACK_LOCAL(A_SP, K, M), PACK_LOCAL(B_SP, N, K));
  RAW_CMD(k_MVOUT, (uintptr_t)C_raw, PACK_LOCAL(C_SP, N, M));
  gemmini_fence();
}

int main(void) {
  uint64_t checksum = 0;
  for (int i = 0; i < M; ++i) {
    for (int j = 0; j < N; ++j) {
      acc_t value = D[i][j];
      for (int k = 0; k < K; ++k) value += A[i][k] * B[k][j];
      gold[i][j] = (elem_t)value;
    }
  }

  run_official();
  run_raw_lowered();

  for (int i = 0; i < M; ++i) {
    for (int j = 0; j < N; ++j) {
      if (C_macro[i][j] != gold[i][j] || C_raw[i][j] != gold[i][j] ||
          C_macro[i][j] != C_raw[i][j]) {
        printf("GEMMINI_L2_ROCC_EQ_FAIL i=%d j=%d macro=%d raw=%d gold=%d\n",
               i, j, C_macro[i][j], C_raw[i][j], gold[i][j]);
        exit(1);
      }
      checksum = checksum * 131 + (uint8_t)C_raw[i][j];
    }
  }
  printf("GEMMINI_L2_ROCC_EQ_PASS checksum=%lu\n", checksum);
  exit(0);
}
