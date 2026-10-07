#include <stdint.h>
#include <string.h>
#include <fenv.h>
#pragma STDC FENV_ACCESS ON
uint32_t op(uint32_t aa, uint32_t bb, int mul, int* flags) {
 float a,b; memcpy(&a,&aa,4);memcpy(&b,&bb,4);
 volatile float x=a,y=b,z;
 feclearexcept(FE_ALL_EXCEPT);
 if(mul)z=x*y;else z=x+y;
 int f=fetestexcept(FE_ALL_EXCEPT);
 *flags=((f&FE_INVALID)?16:0)|((f&FE_DIVBYZERO)?8:0)|((f&FE_OVERFLOW)?4:0)|((f&FE_UNDERFLOW)?2:0)|((f&FE_INEXACT)?1:0);
 float out=z;uint32_t bits;memcpy(&bits,&out,4);return bits;
}
