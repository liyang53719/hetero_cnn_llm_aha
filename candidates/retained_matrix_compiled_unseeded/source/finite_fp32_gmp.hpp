// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <gmpxx.h>
#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <utility>

// Simulation ONLY. Mechanical integer port of pinned FiniteFp32Backend.scala.
// No host float/double, expected-output files, or approximation is used.
namespace retained_model {
inline void require(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
struct Rounded { uint32_t value; unsigned flags; };
struct Decoded { mpz_class n; int exponent; unsigned sign; };
inline bool finite(uint32_t x) { return (x & 0x7f800000u) != 0x7f800000u; }
inline Decoded decode(uint32_t x) {
  require(finite(x), "finite binary32 raw word required");
  const unsigned sign=x>>31, e=(x>>23)&255, f=x&0x7fffff;
  mpz_class n= e ? (0x800000u|f) : f;
  if(sign) n=-n;
  return {n, e ? int(e)-150 : -149, sign};
}
inline std::pair<mpz_class,bool> nearest(const mpz_class& n, int discard) {
  require(n>=0,"nearest magnitude");
  if(discard<=0) return {mpz_class(n << unsigned(-discard)),false};
  mpz_class q=n>>unsigned(discard);
  mpz_class r=n-(q<<unsigned(discard));
  const mpz_class half=mpz_class(1)<<unsigned(discard-1);
  if(r>half || (r==half && mpz_tstbit(q.get_mpz_t(),0))) ++q;
  return {q,r!=0};
}
inline Rounded round(const mpz_class& n0,int power,unsigned zero_sign) {
  require(zero_sign<=1,"zero sign");
  if(n0==0) return {zero_sign<<31,0};
  const uint32_t sign=n0<0?0x80000000u:0u;
  mpz_class n=n0; if(n<0) n=-n;
  const int discard=int(mpz_sizeinbase(n.get_mpz_t(),2))-24;
  auto initial=nearest(n,discard);
  mpz_class sig=initial.first;
  int unit=power+discard;
  if(sig >= (mpz_class(1)<<24)) { sig>>=1; ++unit; }
  const int exponent=unit+23;
  if(exponent>127) return {sign|0x7f800000u,5};
  if(exponent>=-126) return {sign|(uint32_t(exponent+127)<<23)|(uint32_t(sig.get_ui())&0x7fffffu),initial.second?1u:0u};
  const auto sub=nearest(n,-149-power);
  require(sub.first<=(mpz_class(1)<<23),"pinned tiny-round bound");
  return {sign|uint32_t(sub.first.get_ui()),sub.second?3u:0u};
}
inline Rounded fma(uint32_t a,uint32_t b,uint32_t c) {
  const auto aa=decode(a),bb=decode(b),cc=decode(c);
  const mpz_class pn=aa.n*bb.n;
  const int pe=aa.exponent+bb.exponent, e=std::min(pe,cc.exponent);
  const unsigned ps=aa.sign^bb.sign;
  const mpz_class exact=(pn<<unsigned(pe-e))+(cc.n<<unsigned(cc.exponent-e));
  return round(exact,e,(pn==0 && cc.n==0 && ps==cc.sign)?ps:0);
}
inline Rounded mul(uint32_t a,uint32_t b) {
  const auto aa=decode(a),bb=decode(b);
  return round(mpz_class(aa.n*bb.n),aa.exponent+bb.exponent,aa.sign^bb.sign);
}
inline Rounded add(uint32_t a,uint32_t b) {
  const auto aa=decode(a),bb=decode(b); const int e=std::min(aa.exponent,bb.exponent);
  return round(mpz_class((aa.n<<unsigned(aa.exponent-e))+(bb.n<<unsigned(bb.exponent-e))),e,aa.sign&bb.sign);
}
}
