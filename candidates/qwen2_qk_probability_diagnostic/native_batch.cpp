// Bounded diagnostic scheduler, not a replacement model or hardware model.
// All Matrix FMA operations call the unchanged, receipt-verified native library.
#include <cstdint>
#include <cstring>
#include <cfenv>
#include <cmath>
extern "C" {
int td_reset(); int matrix_guard_enable(); int matrix_acquire(unsigned,uint64_t);
int matrix_owner_reply_retire(unsigned,uint64_t); int matrix_release(unsigned,uint64_t);
int matrix_normal_group(unsigned,unsigned,uint32_t,unsigned);
int matrix_normal_step(unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,const uint16_t*,const uint16_t*,uint32_t*);
uint64_t matrix_ticket(); uint64_t matrix_normal_fmas();
int matrix_result_retire(uint64_t,unsigned,unsigned);
int matrix_done_retire(uint64_t,uint32_t,unsigned);
int matrix_legacy_reply_retire(uint64_t);
}
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float fp(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static uint32_t bf(uint32_t u){return (u&0x7f800000)==0x7f800000?u:(u+0x7fff+((u>>16)&1))&0xffff0000;}
static float add(float a,float b){volatile float x=a+b;return x;}
static float mul(float a,float b){volatile float x=a*b;return x;}
extern "C" int diagnostic_qk(const uint32_t* q,const uint32_t* k,unsigned rows,
    uint32_t* parts,uint32_t* sums,uint32_t* dots,uint32_t* scores,uint64_t* fmas){
  if(!q||!k||!parts||!sums||!dots||!scores||!fmas||!rows||rows>128||std::fegetround()!=FE_TONEAREST)return -1;
  if(td_reset()||matrix_guard_enable()||matrix_acquire(2,1))return -2;
  uint16_t a[16],b[256]={};uint32_t out[4096];
  for(unsigned t=0;t<rows;t++)for(unsigned h=0;h<12;h++)for(unsigned key=0;key<=t;key++){
    unsigned i=(h*128+t)*128+key;uint32_t tag=i+1;
    if(matrix_normal_group(0x23,8,tag,1))return -3;
    uint64_t ticket=matrix_ticket();
    for(unsigned s=0;s<8;s++){
      for(unsigned l=0;l<16;l++){a[l]=bf(q[t*1536+h*128+s*16+l])>>16;b[l]=bf(k[key*256+(h/6)*128+s*16+l])>>16;}
      unsigned last=s==7;
      if(matrix_normal_step(s,0,s==0,last,last,1,a,b,out)!=1)return -4;
      if(matrix_result_retire(ticket,0,last))return -5;
      if(last&&matrix_done_retire(ticket,tag,0))return -6;
      if(matrix_legacy_reply_retire(ticket))return -7;
    }
    float sum=0;
    for(unsigned l=0;l<16;l++){parts[i*16+l]=out[l*256+l];sum=add(sum,fp(parts[i*16+l]));}
    sums[i]=bits(sum);dots[i]=bf(sums[i]);scores[i]=bf(bits(mul(fp(dots[i]),fp(0x3db504f3))));
  }
  *fmas=matrix_normal_fmas();
  if(matrix_owner_reply_retire(2,1)||matrix_release(2,1))return -8;
  return 0;
}
