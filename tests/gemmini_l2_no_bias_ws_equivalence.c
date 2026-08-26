// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "include/gemmini_testutils.h"
#define M 17
#define N 18
#define K 19
static elem_t A[M][K] row_align(1),B[K][N] row_align(1);
static elem_t C_official[M][N] row_align(1),C_raw[M][N] row_align(1);
#define RAW(f,a,b) ROCC_INSTRUCTION_RS1_RS2(XCUSTOM_ACC,(uint64_t)(a),(uint64_t)(b),f)
static void config(void){
  gemmini_extended_config_ex(WEIGHT_STATIONARY,NO_ACTIVATION,0,1,false,false);
  gemmini_extended_config_st(N,NO_ACTIVATION,ACC_SCALE_IDENTITY);
  gemmini_extended3_config_ld(K,MVIN_SCALE_IDENTITY,false,0);
  gemmini_extended3_config_ld(N,MVIN_SCALE_IDENTITY,false,1);
  gemmini_extended3_config_ld(0,MVIN_SCALE_IDENTITY,false,2);
}
static void official(void){config();gemmini_loop_ws(2,2,2,15,14,13,A,B,NULL,C_official,
  K,N,0,N,false,false,false,false,false,NO_ACTIVATION,0,0,false);gemmini_fence();}
static void raw(void){config();
  RAW(k_LOOP_WS_CONFIG_BOUNDS,((uint64_t)13<<32)|((uint64_t)14<<16)|15,
      ((uint64_t)2<<32)|((uint64_t)2<<16)|2);
  RAW(k_LOOP_WS_CONFIG_ADDRS_AB,(uintptr_t)A,(uintptr_t)B);
  RAW(k_LOOP_WS_CONFIG_ADDRS_DC,0,(uintptr_t)C_raw);
  RAW(k_LOOP_WS_CONFIG_STRIDES_AB,K,N);RAW(k_LOOP_WS_CONFIG_STRIDES_DC,0,N);
  RAW(k_LOOP_WS,0,0);gemmini_fence();}
int main(void){uint64_t checksum=0;
  for(int i=0;i<M;i++)for(int k=0;k<K;k++)A[i][k]=(i+2*k+1)%5-2;
  for(int k=0;k<K;k++)for(int j=0;j<N;j++)B[k][j]=(3*k+j+2)%5-2;
  official();raw();
  for(int i=0;i<M;i++)for(int j=0;j<N;j++){acc_t sum=0;
    for(int k=0;k<K;k++)sum+=A[i][k]*B[k][j];elem_t gold=(elem_t)sum;
    if(C_official[i][j]!=gold||C_raw[i][j]!=gold){
      printf("GEMMINI_L2_NO_BIAS_WS_FAIL i=%d j=%d official=%d raw=%d gold=%d\n",
             i,j,C_official[i][j],C_raw[i][j],gold);exit(1);}
    checksum=checksum*131+(uint8_t)C_raw[i][j];}
  printf("GEMMINI_L2_NO_BIAS_WS_PASS checksum=%lu\n",checksum);exit(0);}
