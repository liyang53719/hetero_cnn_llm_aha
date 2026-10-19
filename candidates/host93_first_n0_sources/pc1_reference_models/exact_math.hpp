// Exact BF16 real dot product, independent of DUT reduction order.
#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

namespace pc1_math {
inline void check(bool ok) { if (!ok) throw std::runtime_error("MATH_CONTRACT"); }
// Every finite BF16 = signed significand * 2^e, significand <=255,
// -133<=e<=120. Product / 2^-266 is an integer with at most 522 bits.
// 1536 terms need <=533 bits. Sum of 196608 such errors needs <=552.
// Nine 64-bit limbs give 576 bits; no truncation or wrapping is accepted.
struct Wide {
  std::array<std::uint64_t,9> limb{};
  bool zero() const { for(auto v:limb) if(v) return false; return true; }
  void add_limb(unsigned i,std::uint64_t v) {
    while(v) { check(i<limb.size()); auto old=limb[i]; limb[i]+=v;
      v=limb[i]<old; ++i; }
  }
  void add_shift(std::uint64_t v,unsigned shift) {
    if(!v) return;
    const unsigned i=shift/64, off=shift%64;
    add_limb(i,v<<off);
    if(off) add_limb(i+1,v>>(64-off));
  }
  void add(const Wide& x) { for(unsigned i=0;i<9;++i) add_limb(i,x.limb[i]); }
  int compare(const Wide& x) const {
    for(int i=8;i>=0;--i) if(limb[i]!=x.limb[i]) return limb[i]<x.limb[i]?-1:1;
    return 0;
  }
  Wide minus(const Wide& x) const {
    check(compare(x)>=0); Wide out; std::uint64_t borrow=0;
    for(unsigned i=0;i<9;++i) {
      auto a=limb[i], b=x.limb[i], t=a-b;
      auto borrow1=std::uint64_t(a<b), borrow2=std::uint64_t(t<borrow);
      out.limb[i]=t-borrow; borrow=borrow1|borrow2;
    }
    check(!borrow); return out;
  }
  int msb() const {
    for(int i=8;i>=0;--i) if(limb[i]) {
      auto v=limb[i];int bit=0;while(v>>1){v>>=1;++bit;}return i*64+bit;
    } return -1;
  }
  bool bit(unsigned n) const { check(n<576);return (limb[n/64]>>(n%64))&1; }
  bool below(unsigned n) const {
    check(n<=576);
    for(unsigned i=0;i<n/64;++i) if(limb[i])return true;
    return n%64 && (limb[n/64]&((std::uint64_t(1)<<(n%64))-1));
  }
  std::uint64_t right(unsigned shift) const {
    check(shift<576);unsigned i=shift/64,off=shift%64;
    auto v=limb[i]>>off;
    if(off && i+1<9)v|=limb[i+1]<<(64-off);
    return v;
  }
  std::string hex() const {
    std::ostringstream s;s<<std::hex;bool begun=false;
    for(int i=8;i>=0;--i) {
      if(begun)s<<std::setw(16)<<std::setfill('0')<<limb[i];
      else if(limb[i]){s<<limb[i];begun=true;}
    }return begun?s.str():"0";
  }
};
struct Signed {
  Wide magnitude;bool negative=false;
  static Signed difference(const Wide& positive,const Wide& negative) {
    if(positive.compare(negative)>=0)return {positive.minus(negative),false};
    return {negative.minus(positive),true};
  }
};
inline Signed difference(const Signed& a,const Signed& b) {
  if(a.negative!=b.negative){auto m=a.magnitude;m.add(b.magnitude);return {m,a.negative};}
  auto v=Signed::difference(a.magnitude,b.magnitude);
  if(!v.magnitude.zero())v.negative^=a.negative;
  return v;
}
struct Bf16 { unsigned sig,shift;bool negative; };
inline Bf16 decode_bf16(std::uint16_t x) {
  const unsigned exp=(x>>7)&255,frac=x&127;
  check(exp!=255);
  // e+133: subnormal=0; normal=exp-1.
  return {frac|(exp?128U:0U),exp?exp-1:0U,bool(x>>15)};
}
struct Accumulator {
  Wide positive,negative;
  void product(Bf16 a,Bf16 b) {
    (a.negative!=b.negative?negative:positive).add_shift(a.sig*b.sig,a.shift+b.shift);
  }
  Signed exact() const { return Signed::difference(positive,negative); }
  Wide sum_abs() const { auto s=positive;s.add(negative);return s; }
};
inline std::uint64_t rounded_bits(const Signed& x,unsigned frac,int emin,int emax,
                                  int bias,unsigned width) {
  const auto sign=std::uint64_t(x.negative)<<(width-1);
  if(x.magnitude.zero())return sign;
  int e=x.magnitude.msb()-266;
  int shift=(e<emin?emin:e)-int(frac)+266;
  std::uint64_t q;
  if(shift>0) {
    q=x.magnitude.right(unsigned(shift));
    const bool half=x.magnitude.bit(unsigned(shift-1));
    const bool sticky=x.magnitude.below(unsigned(shift-1));
    if(half && (sticky || (q&1)))++q;
  } else {
    check(x.magnitude.msb()<64 && -shift<64);
    q=x.magnitude.limb[0]<<(-shift);
  }
  if(q==(std::uint64_t(1)<<(frac+1))){q>>=1;++e;}
  if(e>emax) {
    const unsigned ebits=width-frac-1;
    return sign|(((std::uint64_t(1)<<ebits)-1)<<frac);
  }
  const auto exp=q>=(std::uint64_t(1)<<frac)?std::uint64_t((e<emin?emin:e)+bias):0;
  return sign|(exp<<frac)|(q&((std::uint64_t(1)<<frac)-1));
}
inline std::uint32_t fp32(const Signed& x) {return std::uint32_t(rounded_bits(x,23,-126,127,127,32));}
inline std::uint64_t fp64(const Signed& x) {return rounded_bits(x,52,-1022,1023,1023,64);}
inline double as_double(const Signed& x) {auto u=fp64(x);double v;std::memcpy(&v,&u,8);return v;}
inline Signed from_fp32(std::uint32_t u) {
  unsigned exp=(u>>23)&255,sig=(u&0x7fffff)|(exp?0x800000:0);
  check(exp!=255);Wide m;m.add_shift(sig,exp?exp+116:117);return {m,bool(u>>31)};
}
inline Signed from_fp64(std::uint64_t u) {
  unsigned exp=unsigned((u>>52)&2047);check(exp && exp!=2047);
  auto sig=(u&0xfffffffffffffULL)|0x10000000000000ULL;
  const int shift=int(exp)-1023-52+266;check(shift>=0);
  Wide m;m.add_shift(sig,unsigned(shift));return {m,bool(u>>63)};
}
inline std::uint64_t ordered_fp32(std::uint32_t u) {
  return u>>31?0x80000000ULL-(u&0x7fffffff):0x80000000ULL+u;
}
}
