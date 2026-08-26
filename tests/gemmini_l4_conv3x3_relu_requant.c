// SPDX-License-Identifier: Apache-2.0
#define main l2_conv3x3_requant_reference_main_unused
#include "gemmini_l2_conv_requant_equivalence.c"
#undef main
int main(void){uint64_t checksum=0;
  for(int r=0;r<IN_DIM;r++)for(int c=0;c<IN_DIM;c++)for(int ch=0;ch<IN_CH;ch++)input[r][c][ch]=(elem_t)(((r*3+c*2+ch)%5)-2);
  for(int o=0;o<OUT_CH;o++){bias[o]=o*3-4;for(int kr=0;kr<KERNEL;kr++)for(int kc=0;kc<KERNEL;kc++)for(int ch=0;ch<IN_CH;ch++){
    elem_t v=(elem_t)(((o+kr*2+kc+ch)%5)-2);weights[o][kr][kc][ch]=v;weights_mat[(kr*KERNEL+kc)*IN_CH+ch][o]=v;}}
  for(int p=0;p<PIXELS;p++)for(int o=0;o<OUT_CH;o++)out_raw[1][p][o]=0;
  uint64_t start=read_cycles();raw_loop_conv(1);uint64_t end=read_cycles();
  for(int r=0;r<OUT_DIM;r++)for(int c=0;c<OUT_DIM;c++)for(int o=0;o<OUT_CH;o++){
    elem_t g=golden(1,r,c,o);int p=r*OUT_DIM+c;if(out_raw[1][p][o]!=g){printf("GEMMINI_L4_CONV3X3_REQUANT_RELU_FAIL r=%d c=%d o=%d rtl=%d gold=%d\n",r,c,o,out_raw[1][p][o],g);exit(1);}checksum=checksum*131+(uint8_t)out_raw[1][p][o];}
  printf("GEMMINI_L4_CONV3X3_REQUANT_RELU_PASS checksum=%lu cycles=%lu dma_bytes=299 macs=2700\n",checksum,end-start);exit(0);}
