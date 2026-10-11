};

static uint64_t checksum(const std::vector<float>& v,size_t begin,size_t count) {
  uint64_t h=1469598103934665603ULL;
  for(size_t i=begin;i<begin+count;i++){h^=bits(v[i]);h*=1099511628211ULL;}
  return h;
}
static void oneCase(int M,int K,int N,int chunk,int pattern,bool withBias) {
  const size_t wi=size_t(M)*K,bi=wi+size_t(K)*N,oi=bi+N;
  Harness source(M,oi+size_t(M)*N);
  uint32_t seed=0x52d78a31u;
  auto random=[&](){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;};
  for(int m=0;m<M;m++)for(int k=0;k<K;k++) {
    float x=fp(0x3f000000u+(random()&0x007fffffu));
    if(random()&1)x=-x;
    if(pattern==1)x=k==K-1?fp(0x80010000u):0.0f;
    if(pattern==2)x=k==0?fp(52u<<23):0.0f; // 2^-75
    if(pattern==3)x=1.0f;
    if(pattern==4)x=(k&1)?fp(0x80000000u):0.0f;
    source.reference[size_t(m)*K+k]=x;
  }
  for(int k=0;k<K;k++)for(int n=0;n<N;n++) {
    float x=bf(float(int(random()%257)-128)/128.0f);
    if(pattern==1)x=k==K-1?fp(0x00010000u):0.0f;
    if(pattern==2)x=k==0?fp(53u<<23):0.0f; // 2^-74, product is FP32 min subnormal
    if(pattern==3)x=k==0?16777216.0f:(k==1?1.0f:(k==2?-16777216.0f:0.0f));
    if(pattern==4)x=(n&1)?-1.0f:1.0f;
    source.reference[wi+size_t(k)*N+n]=x;
  }
  for(int n=0;n<N;n++)source.reference[bi+n]=(pattern==1||pattern==4)?fp(0x80000000u):
    (pattern==2?0.0f:(pattern==3?1.0f:fp(0x35800000u+uint32_t(n))));
  Harness reference=source;
  reference.dense(0,wi*4,oi*4,K,N,withBias?int64_t(bi*4):-1);
  const auto inputHash=checksum(source.reference,0,oi),expected=checksum(reference.reference,oi,size_t(M)*N);
  for(bool rmw:{false,true}) {
    Harness mapped=source;
    mapped.transposed(0,wi*4,oi*4,K,N,withBias?int64_t(bi*4):-1,rmw,chunk);
    for(size_t i=0;i<size_t(M)*N;i++) {
      need(std::isfinite(reference.reference[oi+i]),"synthetic oracle outside finite domain");
      need(bits(mapped.reference[oi+i])==bits(reference.reference[oi+i]),"v0 bit mismatch");
      if(pattern==1)need(bits(mapped.reference[oi+i])==0x80000000u,"negative zero lost");
      if(pattern==2)need(bits(mapped.reference[oi+i])==1u,"FP32 subnormal lost");
      if(pattern==3)need(bits(mapped.reference[oi+i])==bits(withBias?1.0f:0.0f),"K or bias order changed");
    }
    need(checksum(mapped.reference,0,oi)==inputHash,"readonly fixture changed");
    need(checksum(mapped.reference,oi,size_t(M)*N)==expected,"output hash mismatch");
  }
  std::cout<<"BIT_EXACT m="<<M<<" k="<<K<<" n="<<N<<" chunk="<<chunk
    <<" pattern="<<pattern<<" bias="<<withBias<<" values="<<M*N<<" fnv64="<<expected<<std::endl;
}

static void swapProbe() {
  const uint16_t multipliers[]={0,0x8000,1,0x8001,0x3f80,0xbf80,0x7f7f,0xff7f,0x0080,0x3f01};
  const uint32_t prefixes[]={0,0x80000000u,1,0x80000001u,0x3f800000u,0xbf800000u,0x7f7fffffu,0xff7fffffu};
  uint64_t pairs=0,nonfinite=0;
  for(unsigned u=0;u<65536;u++)if((u&0x7f80)!=0x7f80)for(auto b:multipliers)for(auto c:prefixes) {
    volatile float av=fp(u<<16),bv=fp(uint32_t(b)<<16),cv=fp(c);
    const float original=std::fma(av,bv,cv),swapped=std::fma(bv,av,cv);
    need(bits(original)==bits(swapped),"finite operand swap mismatch");
    nonfinite+=!std::isfinite(original);pairs++;
  }
  // Two explicitly forbidden arithmetic rewrites must be distinguishable.
  volatile float big=16777216.0f,one=1.0f,minusbig=-16777216.0f,zero=0.0f;
  float ordered=std::fma(one,big,zero);ordered=std::fma(one,one,ordered);ordered=std::fma(one,minusbig,ordered);
  need(bits(ordered)==0u&&bits(add(add(big,minusbig),one))==bits(one),"K reassociation negative control");
  float seeded=std::fma(one,big,one);seeded=std::fma(one,minusbig,seeded);
  need(bits(seeded)==0u&&bits(add(std::fma(one,minusbig,std::fma(one,big,zero)),one))==bits(one),
       "bias-seeding negative control");
  std::cout<<"OPERAND_SWAP finite_bf16_values=65280 triplets="<<pairs
    <<" bit_mismatches=0 nonfinite_results="<<nonfinite<<" forbidden_rewrites_detected=2"<<std::endl;
}

static void errorCases() {
  const int M=16,K=16,N=32;const size_t wi=M*K,bi=wi+K*N,oi=bi+N;
  unsigned rejects=0;
  for(unsigned kind=0;kind<9;kind++)for(bool rmw:{false,true}) {
    Harness h(M,oi+M*N);
    for(size_t i=0;i<oi;i++)h.reference[i]=1.0f;
    if(kind==0)h.reference[0]=fp(0x7fc00042u);
    if(kind==1)h.reference[0]=fp(0x7f800000u);
    if(kind==2)h.reference[wi]=fp(0xff800000u);
    if(kind==3)h.reference[wi]=fp(0x7fc00043u);
    if(kind==4)h.reference[0]=fp(0x7f7fffffu); // finite FP32 rounds to BF16 infinity
    if(kind==5)h.reference[wi]=fp(0x3f800001u); // outside exact-BF16 weight fixture domain
    if(kind==6){h.reference[0]=fp(0x7f7f0000u);h.reference[wi]=fp(0x7f7f0000u);}
    if(kind==7)h.reference[bi]=fp(0x7f800000u);
    if(kind==8){h.reference[wi]=fp(0x7f7f0000u);h.reference[bi]=fp(0x7f7fffffu);}
    bool caught=false;try {h.transposed(0,wi*4,oi*4,K,N,bi*4,rmw);}catch(const std::runtime_error&){caught=true;}
    need(caught,"nonfinite/domain violation silently accepted");rejects++;
  }
  std::cout<<"DOMAIN_ERRORS cases="<<rejects<<" rejected="<<rejects
    <<" protocol_fault_drain_tested=0"<<std::endl;
}
int main() {
  try {
    verifyFloatEnvironment();swapProbe();
    oneCase(16,16,16,1536,0,false);
    oneCase(32,32,32,1536,0,true);
    oneCase(16,272,160,1536,0,true);
    oneCase(32,272,192,128,0,true); // B refill, A chunk, N group and tail boundaries
    oneCase(16,1536,32,1536,0,false); // maximum proposed full A depth, bounded M/N
    oneCase(128,272,192,128,0,true); // bounded synthetic: all eight physical slices
    for(int pattern=1;pattern<=4;pattern++)oneCase(pattern&1?16:32,32,48,16,pattern,true);
    errorCases();
    std::cout<<"SMALL_COMPARISON_PASS cases=10 mapped_runs=20 official_forward=0 official_m128_numeric=0 synthetic_m128=1"<<std::endl;
    return 0;
  }catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
