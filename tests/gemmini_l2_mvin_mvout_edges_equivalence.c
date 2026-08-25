// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "include/gemmini_testutils.h"

#define CASES 5
#define STRIDE 24
#define BYTES (16 * STRIDE + 8)
#define SENTINEL ((elem_t)0x55)

static const uint8_t rows[CASES] = {1, 1, 16, 15, 16};
static const uint8_t cols[CASES] = {1, 16, 1, 16, 15};
static elem_t edge_in[CASES][BYTES] row_align(1);
static elem_t edge_official[CASES][BYTES] row_align(1);
static elem_t edge_raw[CASES][BYTES] row_align(1);
static acc_t acc_in[16][16] row_align_acc(1);
static elem_t acc8_official[16][16] row_align(1);
static elem_t acc8_raw[16][16] row_align(1);
static acc_t acc32_official[16][16] row_align_acc(1);
static acc_t acc32_raw[16][16] row_align_acc(1);

#define PACK_LOCAL(addr, ncols, nrows) \
  (((uint64_t)(nrows) << (ADDR_LEN + 16)) | ((uint64_t)(ncols) << ADDR_LEN) | (uint32_t)(addr))
#define RAW_CMD(funct, rs1_value, rs2_value) \
  ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC, (uint64_t)(rs1_value), (uint64_t)(rs2_value), funct)

static void raw_config_load(uint64_t stride) {
  const uint64_t scale = UINT64_C(0x3f800000);
  RAW_CMD(k_CONFIG, (scale << 32) | (UINT64_C(DIM) << 16) |
                        (UINT64_C(1) << 8) | CONFIG_LD, stride);
}

static void raw_config_store(uint64_t stride) {
  const uint64_t scale = UINT64_C(0x3f800000);
  RAW_CMD(k_CONFIG, CONFIG_ST, (scale << 32) | stride);
}

static void raw_config_ex(void) {
  const uint64_t scale = UINT64_C(0x3f800000);
  RAW_CMD(k_CONFIG, (scale << 32) | (UINT64_C(1) << 16), UINT64_C(1) << 48);
}

static void run_edge_official(void) {
  for (int n = 0; n < CASES; ++n) {
    const uint32_t local = n * 32;
    const int in_offset = n + 1;
    const int out_offset = n + 1;
    gemmini_config_ld(STRIDE);
    gemmini_config_st(STRIDE);
    gemmini_extended_mvin(&edge_in[n][in_offset], local, cols[n], rows[n]);
    gemmini_extended_mvout(&edge_official[n][out_offset], local, cols[n], rows[n]);
  }
  gemmini_fence();
}

static void run_edge_raw(void) {
  for (int n = 0; n < CASES; ++n) {
    const uint32_t local = n * 32;
    const int in_offset = n + 1;
    const int out_offset = n + 2; // intentional destination-only difference
    raw_config_load(STRIDE);
    raw_config_store(STRIDE);
    RAW_CMD(k_MVIN, (uintptr_t)&edge_in[n][in_offset],
            PACK_LOCAL(local, cols[n], rows[n]));
    RAW_CMD(k_MVOUT, (uintptr_t)&edge_raw[n][out_offset],
            PACK_LOCAL(local, cols[n], rows[n]));
  }
  gemmini_fence();
}

static void run_acc_official(void) {
  const uint32_t acc8 = UINT32_C(1) << (ADDR_LEN - 1);
  const uint32_t acc32 = UINT32_C(5) << (ADDR_LEN - 3);
  gemmini_config_ld(DIM * sizeof(acc_t));
  gemmini_config_ex(OUTPUT_STATIONARY, NO_ACTIVATION, 0);
  gemmini_config_st(DIM * sizeof(elem_t));
  gemmini_extended_mvin(acc_in, acc8, 15, 16);
  gemmini_extended_mvout(acc8_official, acc8, 15, 16);
  gemmini_config_ld(DIM * sizeof(acc_t));
  gemmini_config_ex(OUTPUT_STATIONARY, NO_ACTIVATION, 0);
  gemmini_config_st(DIM * sizeof(acc_t));
  gemmini_extended_mvin(acc_in, acc32, 16, 15);
  gemmini_extended_mvout(acc32_official, acc32, 16, 15);
  gemmini_fence();
}

static void run_acc_raw(void) {
  const uint32_t acc8 = UINT32_C(1) << (ADDR_LEN - 1);
  const uint32_t acc32 = UINT32_C(5) << (ADDR_LEN - 3);
  raw_config_load(DIM * sizeof(acc_t));
  raw_config_ex();
  raw_config_store(DIM * sizeof(elem_t));
  RAW_CMD(k_MVIN, (uintptr_t)acc_in, PACK_LOCAL(acc8, 15, 16));
  RAW_CMD(k_MVOUT, (uintptr_t)acc8_raw, PACK_LOCAL(acc8, 15, 16));
  raw_config_load(DIM * sizeof(acc_t));
  raw_config_ex();
  raw_config_store(DIM * sizeof(acc_t));
  RAW_CMD(k_MVIN, (uintptr_t)acc_in, PACK_LOCAL(acc32, 16, 15));
  RAW_CMD(k_MVOUT, (uintptr_t)acc32_raw, PACK_LOCAL(acc32, 16, 15));
  gemmini_fence();
}

int main(void) {
  uint64_t checksum = 0;
  memset(edge_official, SENTINEL, sizeof(edge_official));
  memset(edge_raw, SENTINEL, sizeof(edge_raw));
  for (int n = 0; n < CASES; ++n) {
    for (int r = 0; r < 16; ++r) {
      for (int c = 0; c < STRIDE; ++c) {
        edge_in[n][n + 1 + r * STRIDE + c] = (elem_t)(n * 17 + r * 3 + c);
      }
    }
  }
  for (int r = 0; r < 16; ++r)
    for (int c = 0; c < 16; ++c) acc_in[r][c] = r * 7 - c * 3;

  run_edge_official();
  run_edge_raw();
  run_acc_official();
  run_acc_raw();

  for (int n = 0; n < CASES; ++n) {
    for (int r = 0; r < rows[n]; ++r) {
      for (int c = 0; c < cols[n]; ++c) {
        const elem_t expected = edge_in[n][n + 1 + r * STRIDE + c];
        const elem_t official = edge_official[n][n + 1 + r * STRIDE + c];
        const elem_t raw = edge_raw[n][n + 2 + r * STRIDE + c];
        if (official != expected || raw != expected) {
          printf("GEMMINI_L2_MVIN_MVOUT_EDGE_FAIL n=%d r=%d c=%d o=%d raw=%d gold=%d\n",
                 n, r, c, official, raw, expected);
          exit(1);
        }
        checksum = checksum * 131 + (uint8_t)raw;
      }
    }
  }
  for (int r = 0; r < 16; ++r) {
    for (int c = 0; c < 16; ++c) {
      if (c < 15 && (acc8_official[r][c] != (elem_t)acc_in[r][c] ||
                     acc8_raw[r][c] != (elem_t)acc_in[r][c])) {
        printf("GEMMINI_L2_ACC8_EDGE_FAIL r=%d c=%d\n", r, c);
        exit(1);
      }
      if (r < 15 && (acc32_official[r][c] != acc_in[r][c] ||
                     acc32_raw[r][c] != acc_in[r][c])) {
        printf("GEMMINI_L2_ACC32_EDGE_FAIL r=%d c=%d\n", r, c);
        exit(1);
      }
    }
  }
  printf("GEMMINI_L2_MVIN_MVOUT_EDGES_EQ_PASS checksum=%lu\n", checksum);
  exit(0);
}
