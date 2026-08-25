// SPDX-License-Identifier: Apache-2.0
// Multi-tile output-stationary equivalence in retained GemminiRocketConfig.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "include/gemmini_testutils.h"

#define ROWS 17
#define COLS 18
#define DEPTH 19
#define TI 2
#define TJ 2
#define TK 2
#define PAD_I 15
#define PAD_J 14
#define PAD_K 13

static elem_t A[ROWS][DEPTH] row_align(1);
static elem_t B[DEPTH][COLS] row_align(1);
static acc_t D[ROWS][COLS] row_align_acc(1);
static elem_t C_official[ROWS][COLS] row_align(1);
static elem_t C_raw[ROWS][COLS] row_align(1);

#define PACK_LOCAL(addr, cols, rows) \
  (((uint64_t)(rows) << (ADDR_LEN + 16)) | ((uint64_t)(cols) << ADDR_LEN) | (uint32_t)(addr))
#define RAW_CMD(funct, rs1_value, rs2_value) \
  ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC, (uint64_t)(rs1_value), (uint64_t)(rs2_value), funct)

static void run_official(void) {
  tiled_matmul(ROWS, COLS, DEPTH,
               (elem_t *)A, (elem_t *)B, (acc_t *)D, (elem_t *)C_official,
               DEPTH, COLS, COLS, COLS,
               MVIN_SCALE_IDENTITY, MVIN_SCALE_IDENTITY, MVIN_SCALE_IDENTITY,
               NO_ACTIVATION, ACC_SCALE_IDENTITY, 0, false,
               TI, TJ, TK, false, false, false, false, 0, OS);
}

static void raw_config_load(uint64_t stride, uint64_t channel) {
  const uint64_t scale = UINT64_C(0x3f800000);
  RAW_CMD(k_CONFIG,
          (scale << 32) | (UINT64_C(DIM) << 16) | (UINT64_C(1) << 8) |
              (channel << 3) | CONFIG_LD,
          stride);
}

static void run_raw_lowered(void) {
  const uint64_t scale = UINT64_C(0x3f800000);
  const uint32_t a_sp_start = 0;
  const uint32_t b_sp_start = BANK_NUM * BANK_ROWS - TK * TJ * DIM;
  const uint32_t d_sp_start = UINT32_C(1) << (ADDR_LEN - 1);
  const uint32_t c_sp_start = UINT32_C(3) << (ADDR_LEN - 2);

  RAW_CMD(k_CONFIG, (scale << 32) | (UINT64_C(1) << 16), UINT64_C(1) << 48);
  RAW_CMD(k_CONFIG, CONFIG_ST, (scale << 32) | COLS);
  raw_config_load(DEPTH, 0);
  raw_config_load(COLS, 1);
  raw_config_load(COLS * sizeof(acc_t), 2);

  raw_config_load(COLS * sizeof(acc_t), 0);
  for (int i = 0; i < TI; ++i) {
    for (int j = 0; j < TJ; ++j) {
      const int cols = DIM - (j == TJ - 1 ? PAD_J : 0);
      const int rows = DIM - (i == TI - 1 ? PAD_I : 0);
      const acc_t *dram = &D[i * DIM][j * DIM];
      const uint32_t local = d_sp_start + (i * TJ + j) * DIM;
      RAW_CMD(k_MVIN, (uintptr_t)dram, PACK_LOCAL(local, cols, rows));
    }
  }

  raw_config_load(COLS, 0);
  for (int k = 0; k < TK; ++k) {
    const int rows = DIM - (k == TK - 1 ? PAD_K : 0);
    const uint32_t local = b_sp_start + k * TJ * DIM;
    RAW_CMD(k_MVIN, (uintptr_t)&B[k * DIM][0],
            PACK_LOCAL(local, TJ * DIM - PAD_J, rows));
  }

  raw_config_load(DEPTH, 0);
  for (int i = 0; i < TI; ++i) {
    const int rows = DIM - (i == TI - 1 ? PAD_I : 0);
    const uint32_t local = a_sp_start + i * TK * DIM;
    RAW_CMD(k_MVIN, (uintptr_t)&A[i * DIM][0],
            PACK_LOCAL(local, TK * DIM - PAD_K, rows));
  }

  for (int i = 0; i < TI; ++i) {
    for (int j = 0; j < TJ; ++j) {
      const int c_cols = DIM - (j == TJ - 1 ? PAD_J : 0);
      const int c_rows = DIM - (i == TI - 1 ? PAD_I : 0);
      const uint32_t c_local = c_sp_start + (i * TJ + j) * DIM;
      for (int k = 0; k < TK; ++k) {
        const int a_cols = DIM - (k == TK - 1 ? PAD_K : 0);
        const uint32_t a_local = a_sp_start + (i * TK + k) * DIM;
        const uint32_t b_local = b_sp_start + (k * TJ + j) * DIM;
        const uint32_t out = k == TK - 1 ? c_local : UINT32_MAX;
        RAW_CMD(k_PRELOAD, PACK_LOCAL(UINT32_MAX, DIM, DIM),
                PACK_LOCAL(out, c_cols, c_rows));
        if (k == 0) {
          RAW_CMD(k_COMPUTE_PRELOADED,
                  PACK_LOCAL(a_local, a_cols, c_rows),
                  PACK_LOCAL(b_local, c_cols, a_cols));
        } else {
          RAW_CMD(k_COMPUTE_ACCUMULATE,
                  PACK_LOCAL(a_local, a_cols, c_rows),
                  PACK_LOCAL(b_local, c_cols, a_cols));
        }
      }
    }
  }

  for (int i = 0; i < TI; ++i) {
    for (int j = 0; j < TJ; ++j) {
      const int cols = DIM - (j == TJ - 1 ? PAD_J : 0);
      const int rows = DIM - (i == TI - 1 ? PAD_I : 0);
      const uint32_t local = c_sp_start + (i * TJ + j) * DIM;
      RAW_CMD(k_MVOUT, (uintptr_t)&C_raw[i * DIM][j * DIM],
              PACK_LOCAL(local, cols, rows));
    }
  }
  gemmini_fence();
}

int main(void) {
  uint64_t checksum = 0;
  for (int i = 0; i < ROWS; ++i) {
    for (int k = 0; k < DEPTH; ++k) A[i][k] = (elem_t)((i + 2 * k + 1) % 5);
  }
  for (int k = 0; k < DEPTH; ++k) {
    for (int j = 0; j < COLS; ++j) B[k][j] = (elem_t)((3 * k + j + 2) % 5);
  }
  for (int i = 0; i < ROWS; ++i) {
    for (int j = 0; j < COLS; ++j) D[i][j] = (acc_t)((i + j) % 4);
  }

  run_official();
  run_raw_lowered();

  for (int i = 0; i < ROWS; ++i) {
    for (int j = 0; j < COLS; ++j) {
      acc_t expected = D[i][j];
      for (int k = 0; k < DEPTH; ++k) expected += A[i][k] * B[k][j];
      const elem_t golden = (elem_t)expected;
      if (C_official[i][j] != golden || C_raw[i][j] != golden ||
          C_official[i][j] != C_raw[i][j]) {
        printf("GEMMINI_L2_MULTI_TILE_OS_EQ_FAIL i=%d j=%d official=%d raw=%d gold=%d\n",
               i, j, C_official[i][j], C_raw[i][j], golden);
        exit(1);
      }
      checksum = checksum * 131 + (uint8_t)C_raw[i][j];
    }
  }
  printf("GEMMINI_L2_MULTI_TILE_OS_EQ_PASS checksum=%lu\n", checksum);
  exit(0);
}
