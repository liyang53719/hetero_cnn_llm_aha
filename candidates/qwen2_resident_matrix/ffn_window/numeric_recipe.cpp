// SPDX-License-Identifier: Apache-2.0
// HOST-ONLY. Reuse the unchanged five physical accumulator banks and exact
// accepted packet mapping; this is neither native Matrix nor RTL execution.
#include "../transposed_down/numeric_smoke.cpp"

// Independent direct logical dot reference, invoked only AFTER actual Gate,
// Up and SiLU tile-bank output responses have all completed. Raw A is FP32;
// source weights are output-major BF16 [8960][1536]. No packet coordinates,
// physical-bank contents or expected producer output enter this computation.
extern "C" int fw_reference(const uint32_t* a,const uint16_t* weight,
                             uint32_t* out,unsigned rows,unsigned cols,unsigned ng){
  if((rows!=16&&rows!=128)||!cols||cols>160||cols%32||ng%32||ng+cols>8960)return -1;
  for(unsigned m=0;m<rows;m++)for(unsigned n=0;n<cols;n++){
    float sum=0.0f;
    for(unsigned k=0;k<1536;k++)
      sum=std::fma(bf(fp(a[m*1536+k])),fp(uint32_t(weight[(ng+n)*1536+k])<<16),sum);
    if(!std::isfinite(sum))return -2;
    out[m*cols+n]=bits(sum);
  }
  return 0;
}
