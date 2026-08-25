// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "include/gemmini_testutils.h"

#define IN_DIM 5
#define IN_CH 3
#define OUT_CH 4
#define KERNEL 3
#define OUT_DIM 5
#define PATCH (KERNEL * KERNEL * IN_CH)
#define PIXELS (OUT_DIM * OUT_DIM)

static elem_t input[IN_DIM][IN_DIM][IN_CH] row_align(1);
static elem_t weights[OUT_CH][KERNEL][KERNEL][IN_CH] row_align(1);
static elem_t weights_mat[PATCH][OUT_CH] row_align(1);
static acc_t bias[OUT_CH] row_align_acc(1);
static elem_t out_official[2][PIXELS][OUT_CH] row_align(1);
static elem_t out_raw[2][PIXELS][OUT_CH] row_align(1);

#define RAW_CMD(funct, rs1_value, rs2_value) \
  ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC, (uint64_t)(rs1_value), (uint64_t)(rs2_value), funct)

static void configure_conv(int activation, acc_scale_t scale) {
  gemmini_extended_config_st(OUT_CH, activation, scale);
  gemmini_extended3_config_ex(WEIGHT_STATIONARY, 0, 0, 0,
                              1, 1, false, false, false);
}

static void run_official(int mode) {
  const int activation = mode == 0 ? NO_ACTIVATION : RELU;
  const acc_scale_t scale = mode == 0 ? ACC_SCALE_IDENTITY : 0.5f;
  configure_conv(activation, scale);
  sp_tiled_conv(
      1, IN_DIM, IN_DIM, IN_CH, OUT_CH, OUT_DIM, OUT_DIM, OUT_DIM, OUT_DIM,
      1, 1, KERNEL, 1, IN_CH, OUT_CH, OUT_CH,
      1, 1, 0,
      1, OUT_DIM, OUT_DIM, OUT_CH, KERNEL, KERNEL, IN_CH,
      1, 1, 1, 1, 0, 0, 0, 0,
      (elem_t *)input, (elem_t *)weights_mat,
      (elem_t *)out_official[mode], (acc_t *)bias,
      activation, scale,
      false, false, false, false, false,
      false, true, false, false, false, 0, 0);
  gemmini_fence();
}

static void raw_config_conv(int activation, uint32_t scale_bits) {
  RAW_CMD(k_CONFIG, ((uint64_t)activation << 2) | CONFIG_ST,
          ((uint64_t)scale_bits << 32) | OUT_CH);
  RAW_CMD(k_CONFIG, (UINT64_C(1) << 16) | (WEIGHT_STATIONARY << 2) | CONFIG_EX,
          UINT64_C(1) << 48);
}

static void raw_loop_conv(int mode) {
  const int activation = mode == 0 ? NO_ACTIVATION : RELU;
  const uint32_t scale_bits = mode == 0 ? UINT32_C(0x3f800000) : UINT32_C(0x3f000000);
  raw_config_conv(activation, scale_bits);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_1,
          (UINT64_C(OUT_CH) << 48) | (UINT64_C(IN_CH) << 32) |
              (UINT64_C(IN_DIM) << 16) | 1,
          (UINT64_C(1) << 56) | (UINT64_C(1) << 48) |
              (UINT64_C(OUT_DIM) << 32) | (UINT64_C(OUT_DIM) << 16) | OUT_DIM);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_2,
          (UINT64_C(KERNEL) << 48) | (UINT64_C(OUT_DIM) << 32) |
              (UINT64_C(1) << 16) | (UINT64_C(1) << 8),
          (UINT64_C(1) << 48) | (UINT64_C(OUT_DIM) << 32) |
              (UINT64_C(OUT_DIM) << 16) | OUT_CH);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_3,
          (UINT64_C(KERNEL) << 48) | (UINT64_C(KERNEL) << 32) |
              (UINT64_C(IN_CH) << 16) | 1,
          (UINT64_C(1) << 48) | (UINT64_C(1) << 32) |
              (UINT64_C(1) << 24) | IN_DIM);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_4,
          (UINT64_C(OUT_DIM) << 48) | 1,
          (UINT64_C(IN_CH) << 48) | (UINT64_C(OUT_CH) << 32) |
              (UINT64_C(OUT_CH) << 16) | OUT_DIM);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_5, (uintptr_t)weights_mat,
          (uintptr_t)out_raw[mode]);
  RAW_CMD(k_LOOP_CONV_WS_CONFIG_6, (uintptr_t)bias, (uintptr_t)input);
  RAW_CMD(k_LOOP_CONV_WS, UINT64_C(3) << 8,
          ((uint64_t)activation << 3) | 1);
  gemmini_fence();
}

static elem_t golden(int mode, int orow, int ocol, int och) {
  acc_t sum = bias[och];
  for (int kr = 0; kr < KERNEL; ++kr) {
    for (int kc = 0; kc < KERNEL; ++kc) {
      const int ir = orow + kr - 1;
      const int ic = ocol + kc - 1;
      if (ir < 0 || ir >= IN_DIM || ic < 0 || ic >= IN_DIM) continue;
      for (int ch = 0; ch < IN_CH; ++ch)
        sum += input[ir][ic][ch] * weights[och][kr][kc][ch];
    }
  }
  elem_t value = ACC_SCALE(sum, mode == 0 ? ACC_SCALE_IDENTITY : 0.5f);
  if (mode != 0 && value < 0) value = 0;
  return value;
}

int main(void) {
  uint64_t checksum = 0;
  for (int r = 0; r < IN_DIM; ++r)
    for (int c = 0; c < IN_DIM; ++c)
      for (int ch = 0; ch < IN_CH; ++ch)
        input[r][c][ch] = (elem_t)(((r * 3 + c * 2 + ch) % 5) - 2);
  for (int och = 0; och < OUT_CH; ++och) {
    bias[och] = och * 3 - 4;
    for (int kr = 0; kr < KERNEL; ++kr)
      for (int kc = 0; kc < KERNEL; ++kc)
        for (int ch = 0; ch < IN_CH; ++ch) {
          const elem_t value = (elem_t)(((och + kr * 2 + kc + ch) % 5) - 2);
          weights[och][kr][kc][ch] = value;
          weights_mat[(kr * KERNEL + kc) * IN_CH + ch][och] = value;
        }
  }
  for (int mode = 0; mode < 2; ++mode) {
    run_official(mode);
    raw_loop_conv(mode);
  }
  for (int mode = 0; mode < 2; ++mode)
    for (int r = 0; r < OUT_DIM; ++r)
      for (int c = 0; c < OUT_DIM; ++c)
        for (int och = 0; och < OUT_CH; ++och) {
          const int pixel = r * OUT_DIM + c;
          const elem_t expected = golden(mode, r, c, och);
          if (out_official[mode][pixel][och] != expected ||
              out_raw[mode][pixel][och] != expected) {
            printf("GEMMINI_L2_CONV_EQ_FAIL mode=%d r=%d c=%d ch=%d o=%d raw=%d gold=%d\n",
                   mode, r, c, och, out_official[mode][pixel][och],
                   out_raw[mode][pixel][och], expected);
            exit(1);
          }
          checksum = checksum * 131 + (uint8_t)out_raw[mode][pixel][och];
        }
  printf("GEMMINI_L2_CONV_REQUANT_EQ_PASS checksum=%lu\n", checksum);
  exit(0);
}
