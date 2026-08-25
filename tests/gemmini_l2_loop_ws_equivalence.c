// SPDX-License-Identifier: Apache-2.0
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

#define RAW_CMD(funct, rs1_value, rs2_value) \
  ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC, (uint64_t)(rs1_value), (uint64_t)(rs2_value), funct)

static void configure_ws_dma(void) {
  // gemmini_loop_ws() only emits the six LOOP_WS commands. Match the exact
  // execute/load/store setup performed by upstream tiled_matmul_outer().
  gemmini_extended_config_ex(WEIGHT_STATIONARY, NO_ACTIVATION, 0, 1,
                             false, false);
  gemmini_extended_config_st(COLS * sizeof(elem_t), NO_ACTIVATION,
                             ACC_SCALE_IDENTITY);
  gemmini_extended3_config_ld(DEPTH * sizeof(elem_t), MVIN_SCALE_IDENTITY,
                              false, 0);
  gemmini_extended3_config_ld(COLS * sizeof(elem_t), MVIN_SCALE_IDENTITY,
                              false, 1);
  gemmini_extended3_config_ld(COLS * sizeof(acc_t), MVIN_SCALE_IDENTITY,
                              false, 2);
}

static void official_loop(void) {
  configure_ws_dma();
  gemmini_loop_ws(TI, TJ, TK, PAD_I, PAD_J, PAD_K,
                  A, B, D, C_official,
                  DEPTH, COLS, COLS, COLS,
                  false, false, false, false, true,
                  NO_ACTIVATION, 0, 0, false);
  gemmini_fence();
}

static void raw_loop(void) {
  configure_ws_dma();
  RAW_CMD(k_LOOP_WS_CONFIG_BOUNDS,
          ((uint64_t)PAD_K << 32) | ((uint64_t)PAD_J << 16) | PAD_I,
          ((uint64_t)TK << 32) | ((uint64_t)TJ << 16) | TI);
  RAW_CMD(k_LOOP_WS_CONFIG_ADDRS_AB, (uintptr_t)A, (uintptr_t)B);
  RAW_CMD(k_LOOP_WS_CONFIG_ADDRS_DC, (uintptr_t)D, (uintptr_t)C_raw);
  RAW_CMD(k_LOOP_WS_CONFIG_STRIDES_AB, DEPTH, COLS);
  RAW_CMD(k_LOOP_WS_CONFIG_STRIDES_DC, COLS, COLS);
  RAW_CMD(k_LOOP_WS,
          ((uint64_t)NO_ACTIVATION << 8) | UINT64_C(1),
          0);
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
    for (int j = 0; j < COLS; ++j) D[i][j] = (elem_t)((i + j) % 4);
  }

  official_loop();
  raw_loop();

  for (int i = 0; i < ROWS; ++i) {
    for (int j = 0; j < COLS; ++j) {
      acc_t expected = D[i][j];
      for (int k = 0; k < DEPTH; ++k) expected += A[i][k] * B[k][j];
      const elem_t golden = (elem_t)expected;
      if (C_official[i][j] != golden || C_raw[i][j] != golden ||
          C_official[i][j] != C_raw[i][j]) {
        printf("GEMMINI_L2_LOOP_WS_EQ_FAIL i=%d j=%d official=%d raw=%d gold=%d\n",
               i, j, C_official[i][j], C_raw[i][j], golden);
        exit(1);
      }
      checksum = checksum * 131 + (uint8_t)C_raw[i][j];
    }
  }
  printf("GEMMINI_L2_LOOP_WS_EQ_PASS checksum=%lu\n", checksum);
  exit(0);
}
