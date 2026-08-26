// SPDX-License-Identifier: Apache-2.0
#define main l2_conv1x1_reference_main_unused
#include "gemmini_l2_conv1x1_equivalence.c"
#undef main

int main(void) {
  uint64_t checksum = 0;
  for (int r = 0; r < IN_DIM; r++)
    for (int c = 0; c < IN_DIM; c++)
      for (int ch = 0; ch < IN_CH; ch++) input[r][c][ch] = (r + 2*c + ch) % 5 - 2;
  for (int o = 0; o < OUT_CH; o++) {
    bias[o] = o - 2;
    for (int ch = 0; ch < IN_CH; ch++) {
      weights[o][ch] = (o + 2*ch) % 5 - 2;
      weights_mat[ch][o] = weights[o][ch];
    }
  }
  for (int p = 0; p < OUT_DIM*OUT_DIM; p++)
    for (int o = 0; o < OUT_CH; o++) out_raw[p][o] = 0;

  const uint64_t start = read_cycles();
  raw();
  const uint64_t end = read_cycles();
  for (int r = 0; r < OUT_DIM; r++)
    for (int c = 0; c < OUT_DIM; c++)
      for (int o = 0; o < OUT_CH; o++) {
        acc_t sum = bias[o];
        for (int ch = 0; ch < IN_CH; ch++) sum += input[r][c][ch] * weights[o][ch];
        const elem_t golden = (elem_t)sum;
        const int p = r * OUT_DIM + c;
        if (out_raw[p][o] != golden) {
          printf("GEMMINI_L4_CONV1X1_FAIL r=%d c=%d o=%d rtl=%d golden=%d\n",
                 r, c, o, out_raw[p][o], golden);
          exit(1);
        }
        checksum = checksum * 131 + (uint8_t)out_raw[p][o];
      }
  printf("GEMMINI_L4_CONV1X1_PASS checksum=%lu cycles=%lu dma_bytes=140 macs=192\n",
         checksum, end - start);
  exit(0);
}
