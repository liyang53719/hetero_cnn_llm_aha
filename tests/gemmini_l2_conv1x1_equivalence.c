// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "include/gemmini_testutils.h"
#define IN_DIM 4
#define IN_CH 3
#define OUT_CH 4
#define OUT_DIM 4
static elem_t input[IN_DIM][IN_DIM][IN_CH] row_align(1);
static elem_t weights[OUT_CH][IN_CH] row_align(1),weights_mat[IN_CH][OUT_CH] row_align(1);
static acc_t bias[OUT_CH] row_align_acc(1);
static elem_t out_official[OUT_DIM*OUT_DIM][OUT_CH] row_align(1);
static elem_t out_raw[OUT_DIM*OUT_DIM][OUT_CH] row_align(1);
#define RAW(f,a,b) ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC,(uint64_t)(a),(uint64_t)(b),f)
static void config(void){gemmini_extended_config_st(OUT_CH,NO_ACTIVATION,ACC_SCALE_IDENTITY);
  gemmini_extended3_config_ex(WEIGHT_STATIONARY,0,0,0,1,1,false,false,false);}
static void official(void){config();
  sp_tiled_conv(1,IN_DIM,IN_DIM,IN_CH,OUT_CH,OUT_DIM,OUT_DIM,OUT_DIM,OUT_DIM,
    1,0,1,1,IN_CH,OUT_CH,OUT_CH,1,1,0,
    1,OUT_DIM,OUT_DIM,OUT_CH,1,1,IN_CH,0,0,0,0,0,0,0,0,
    (elem_t*)input,(elem_t*)weights_mat,(elem_t*)out_official,(acc_t*)bias,
    NO_ACTIVATION,ACC_SCALE_IDENTITY,false,false,false,false,false,
    false,true,false,false,false,0,0);gemmini_fence();}
static void raw(void){config();
  RAW(k_LOOP_CONV_WS_CONFIG_1,((uint64_t)OUT_CH<<48)|((uint64_t)IN_CH<<32)|
      ((uint64_t)IN_DIM<<16)|1,((uint64_t)1<<48)|((uint64_t)OUT_DIM<<32)|
      ((uint64_t)OUT_DIM<<16)|OUT_DIM);
  RAW(k_LOOP_CONV_WS_CONFIG_2,((uint64_t)1<<48)|((uint64_t)OUT_DIM<<32)|
      ((uint64_t)1<<16)|((uint64_t)1<<8),((uint64_t)1<<48)|
      ((uint64_t)OUT_DIM<<32)|((uint64_t)OUT_DIM<<16)|OUT_CH);
  RAW(k_LOOP_CONV_WS_CONFIG_3,((uint64_t)1<<48)|((uint64_t)1<<32)|
      ((uint64_t)IN_CH<<16),IN_DIM);
  RAW(k_LOOP_CONV_WS_CONFIG_4,((uint64_t)OUT_DIM<<48)|1,
      ((uint64_t)IN_CH<<48)|((uint64_t)OUT_CH<<32)|((uint64_t)OUT_CH<<16)|OUT_DIM);
  RAW(k_LOOP_CONV_WS_CONFIG_5,(uintptr_t)weights_mat,(uintptr_t)out_raw);
  RAW(k_LOOP_CONV_WS_CONFIG_6,(uintptr_t)bias,(uintptr_t)input);
  RAW(k_LOOP_CONV_WS,(uint64_t)1<<8,1);gemmini_fence();}
int main(void){uint64_t checksum=0;
  for(int r=0;r<IN_DIM;r++)for(int c=0;c<IN_DIM;c++)for(int ch=0;ch<IN_CH;ch++)
    input[r][c][ch]=(r+2*c+ch)%5-2;
  for(int o=0;o<OUT_CH;o++){bias[o]=o-2;for(int ch=0;ch<IN_CH;ch++){
    weights[o][ch]=(o+2*ch)%5-2;weights_mat[ch][o]=weights[o][ch];}}
  official();raw();
  for(int r=0;r<OUT_DIM;r++)for(int c=0;c<OUT_DIM;c++)for(int o=0;o<OUT_CH;o++){
    acc_t sum=bias[o];for(int ch=0;ch<IN_CH;ch++)sum+=input[r][c][ch]*weights[o][ch];
    elem_t gold=(elem_t)sum;int p=r*OUT_DIM+c;
    if(out_official[p][o]!=gold||out_raw[p][o]!=gold){
      printf("GEMMINI_L2_CONV1X1_FAIL r=%d c=%d o=%d official=%d raw=%d gold=%d\n",
             r,c,o,out_official[p][o],out_raw[p][o],gold);exit(1);}
    checksum=checksum*131+(uint8_t)out_raw[p][o];}
  printf("GEMMINI_L2_CONV1X1_PASS checksum=%lu\n",checksum);exit(0);}
