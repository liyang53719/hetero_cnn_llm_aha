// SOURCE candidate. Native compile/full execution require separately accepted supervision.
#include "exact_math.hpp"
#include "sha256.hpp"
#include <algorithm>
#include <cfenv>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <vector>
#include <xmmintrin.h>

static void need(bool ok,const char* code){if(!ok)throw std::runtime_error(code);}
static float bf(float x){std::uint32_t u;std::memcpy(&u,&x,4);
  if((u&0x7f800000)!=0x7f800000)u=(u+0x7fff+((u>>16)&1))&0xffff0000;
  std::memcpy(&x,&u,4);return x;}
static float add(float a,float b){return a+b;}
#include "dot16.inc"

namespace fs=std::filesystem;
using pc1_math::Wide;using pc1_math::Signed;
static float f32(std::uint32_t u){float f;std::memcpy(&f,&u,4);return f;}
static std::uint32_t u32(float f){std::uint32_t u;std::memcpy(&u,&f,4);return u;}
static std::string sha(const std::vector<std::uint8_t>& bytes){
  auto h=same_buffer_loader_v1::Sha256::hash(bytes.data(),bytes.size());
  std::ostringstream s;s<<std::hex<<std::setfill('0');for(auto x:h)s<<std::setw(2)<<unsigned(x);return s.str();
}
static std::vector<std::uint8_t> read_fixed(const fs::path& p,std::size_t size,const std::string& digest){
  need(!fs::is_symlink(p)&&fs::is_regular_file(p)&&fs::file_size(p)==size,"INPUT_FILE");
  std::ifstream f(p,std::ios::binary);need(bool(f),"INPUT_OPEN");
  std::vector<std::uint8_t> bytes(size);f.read(reinterpret_cast<char*>(bytes.data()),std::streamsize(size));
  need(f.gcount()==std::streamsize(size)&&f.peek()==std::char_traits<char>::eof(),"INPUT_LENGTH");
  need(sha(bytes)==digest,"INPUT_HASH");return bytes;
}
static void write_new(const fs::path& p,const std::vector<std::uint8_t>& bytes){
  need(!fs::exists(p),"OUTPUT_EXISTS");std::ofstream f(p,std::ios::binary);
  need(bool(f),"OUTPUT_OPEN");f.write(reinterpret_cast<const char*>(bytes.data()),std::streamsize(bytes.size()));
  f.close();need(bool(f),"OUTPUT_WRITE");
}
template<class T>static std::vector<std::uint8_t> little_bytes(const std::vector<T>& values){
  std::vector<std::uint8_t> b;b.reserve(values.size()*sizeof(T));
  for(auto x:values)for(unsigned j=0;j<sizeof(T);++j)b.push_back(std::uint8_t(x>>(8*j)));
  return b;
}
static void environment(){
  static_assert(sizeof(float)==4 && sizeof(double)==8,"IEEE storage");
  static_assert(std::numeric_limits<float>::is_iec559 && std::numeric_limits<double>::is_iec559,"IEEE format");
  need(std::fegetround()==FE_TONEAREST,"ROUNDING_MODE");
  need((_mm_getcsr()&((1U<<15)|(1U<<6)|(3U<<13)))==0,"FTZ_DAZ_OR_ROUNDING");
}
static double upper(double x){return std::nextafter(x,std::numeric_limits<double>::infinity());}
static double lower(double x){return std::nextafter(x,0.0);}
static double analytic_bound(const Wide& abs_products){
  // 1536 FMAs + one add; outward FP64 arithmetic bounds gamma_1537*sum|ab|
  // plus gradual-underflow absolute error (1537 * 2^-150)/(1-1537*2^-24).
  const double a=1537.0*std::ldexp(1.0,-24),den=1.0-a;
  const double gamma=upper(a/den),eta=upper((1537.0*std::ldexp(1.0,-150))/den);
  return upper(upper(gamma*upper(pc1_math::as_double({abs_products,false})))+eta);
}
static void micro(){
  using pc1_math::Accumulator;using pc1_math::decode_bf16;
  auto exact=[](std::initializer_list<std::pair<std::uint16_t,std::uint16_t>> terms){
    Accumulator a;for(auto t:terms)a.product(decode_bf16(t.first),decode_bf16(t.second));return a.exact();};
  auto one=exact({{0x3f80,0x3f80}});
  need(pc1_math::fp32(one)==0x3f800000 && pc1_math::fp64(one)==0x3ff0000000000000ULL,"MICRO_ONE");
  need(pc1_math::fp32(exact({{0x3f80,0x3f80},{0xbf80,0x3f80}}))==0,"MICRO_CANCEL");
  need(pc1_math::fp32({Wide{},true})==0x80000000U,"MICRO_NEG_ZERO");
  need(pc1_math::fp32(exact({{0x0080,0x3380}}))==0,"MICRO_SUB_TIE_EVEN");
  need(pc1_math::fp32(exact({{0x8080,0x3380}}))==0x80000000U,"MICRO_NEG_UNDERFLOW");
  need(pc1_math::fp32(exact({{0x0080,0x3400},{0x0080,0x3380}}))==2,"MICRO_SUB_TIE_ODD");
  need(pc1_math::fp32(exact({{0x7f7f,0x7f7f}}))==0x7f800000,"MICRO_OVERFLOW");
  need(pc1_math::fp32(exact({{0xff7f,0x7f7f}}))==0xff800000,"MICRO_NEG_OVERFLOW");
  Accumulator capacity;for(int i=0;i<1536;++i)capacity.product(decode_bf16(0x7f7f),decode_bf16(0x7f7f));
  need(capacity.exact().magnitude.msb()<=532,"MICRO_CAPACITY");
  auto twice=capacity.positive;twice.add(capacity.positive);need(twice.compare(capacity.positive)>0,"MICRO_CARRY");
  auto canceled=Signed::difference(twice,twice);need(canceled.magnitude.zero(),"MICRO_WIDE_CANCEL");
  const float a=f32(0x3f800001),b=f32(0x3f7ffffe),c=-1.0f;
  volatile float product=a*b;
  need(u32(std::fma(a,b,c))==0xa8800000 && u32(product+c)==0,"MICRO_GENERIC_FMA");
  std::vector<float>x(1536,0),w(1536*16,1);const int blocks[2]={1024,512};float out[16]{};
  x[1]=1;x[1025]=16777216;x[1024]=-16777216;
  reference_qkv_pair_dot16(x.data(),w.data(),1536,16,0,blocks,2,out);need(u32(out[0])==0x3f800000,"MICRO_PARTIAL");
  std::fill(x.begin(),x.end(),0);x[1]=16777216;x[2]=1;x[3]=-16777216;
  reference_qkv_pair_dot16(x.data(),w.data(),1536,16,0,blocks,2,out);need(u32(out[0])==0x3f800000,"MICRO_PAIR");
  std::fill(x.begin(),x.end(),0);x[1]=1;x[0]=std::ldexp(1.0f,-8);
  reference_qkv_pair_dot16(x.data(),w.data(),1536,16,0,blocks,2,out);need(u32(out[0])==0x3f808000 && u32(bf(out[0]))==0x3f800000,"MICRO_NO_BF16");
  std::fill(x.begin(),x.end(),0);std::fill(w.begin(),w.end(),1);
  x[1]=std::ldexp(1.0f,-126);x[0]=x[1];
  for(int lane=0;lane<16;++lane){w[16+lane]=std::ldexp(1.0f,-23);w[lane]=std::ldexp(1.0f,-24);}
  reference_qkv_pair_dot16(x.data(),w.data(),1536,16,0,blocks,2,out);need(u32(out[0])==2,"MICRO_BF16_SUBNORMAL_FMA");
  std::cout<<"{\"status\":\"PASS_NATIVE_MICRO\",\"full_arrays_read\":false,\"official_raw_numeric_pass\":null}\n";
}
static int full(const fs::path& in,const fs::path& out){
  constexpr unsigned M=128,N=1536,K=1536,COUNT=M*N;
  need(fs::is_directory(out)&&fs::is_empty(out),"OUTPUT_NOT_EMPTY");
  auto nr=read_fixed(in/"independent_n0.f32le",786432,"3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f");
  auto wr=read_fixed(in/"wq.bf16le",4718592,"ad7ce2dae58deb01656348a6ee2bd6919ed6c2bc83f31b88eed75381cd718b72");
  std::vector<float>a(M*K),w(K*N);std::vector<pc1_math::Bf16>ad(M*K),wd(K*N);
  for(unsigned i=0;i<a.size();++i){std::uint32_t u=0;for(unsigned j=0;j<4;++j)u|=std::uint32_t(nr[4*i+j])<<(8*j);
    need((u&0xffff)==0,"N0_NOT_BF16_WIDENING");ad[i]=pc1_math::decode_bf16(std::uint16_t(u>>16));a[i]=f32(u);}
  for(unsigned i=0;i<w.size();++i){auto u=std::uint16_t(wr[2*i]|(std::uint16_t(wr[2*i+1])<<8));
    wd[i]=pc1_math::decode_bf16(u);w[i]=f32(std::uint32_t(u)<<16);}
  std::vector<std::uint32_t>math32(COUNT),typed(COUNT);std::vector<std::uint64_t>math64(COUNT);
  std::uint64_t equal=0,maxulp=0,zero_ref=0,zero_ref_nonzero_error=0;
  std::array<std::uint64_t,7>hist{};Wide maxerr,sumerr;unsigned maxindex=0;double maxrel_lo=0,maxrel_hi=0,maxbound=0;
  bool bounds_ok=true;const int blocks[2]={1024,512};
  for(unsigned m=0;m<M;++m)for(unsigned col=0;col<N;col+=16){
    // Independent exact real arithmetic: ascending k, no partials or pair permutation.
    std::array<pc1_math::Accumulator,16> exact{};
    for(unsigned k=0;k<K;++k)for(unsigned lane=0;lane<16;++lane)
      exact[lane].product(ad[m*K+k],wd[k*N+col+lane]);
    float t[16]{};reference_qkv_pair_dot16(a.data()+m*K,w.data(),K,N,int(col),blocks,2,t);
    for(unsigned lane=0;lane<16;++lane){const unsigned i=m*N+col+lane;auto truth=exact[lane].exact();
      math32[i]=pc1_math::fp32(truth);math64[i]=pc1_math::fp64(truth);typed[i]=u32(t[lane]);
      need((math32[i]&0x7f800000)!=0x7f800000 && std::isfinite(t[lane]),"NONFINITE_RESULT");
      equal+=math32[i]==typed[i];auto x=pc1_math::ordered_fp32(math32[i]),y=pc1_math::ordered_fp32(typed[i]);
      auto ulp=x>y?x-y:y-x;maxulp=std::max(maxulp,ulp);
      unsigned bucket=ulp==0?0:ulp==1?1:ulp<=3?2:ulp<=7?3:ulp<=15?4:ulp<=255?5:6;++hist[bucket];
      auto err=pc1_math::difference(pc1_math::from_fp32(typed[i]),truth).magnitude;
      sumerr.add(err);if(err.compare(maxerr)>0){maxerr=err;maxindex=i;}
      const double ed=pc1_math::as_double({err,false});
      if(truth.magnitude.zero()){++zero_ref;if(!err.zero())++zero_ref_nonzero_error;}
      else if(!err.zero()){
        const double rd=pc1_math::as_double({truth.magnitude,false});
        maxrel_lo=std::max(maxrel_lo,lower(lower(ed)/upper(rd)));
        maxrel_hi=std::max(maxrel_hi,upper(upper(ed)/lower(rd)));
      }
      const double bound=analytic_bound(exact[lane].sum_abs());std::uint64_t bu;std::memcpy(&bu,&bound,8);
      bounds_ok=bounds_ok && err.compare(pc1_math::from_fp64(bu).magnitude)<=0;maxbound=std::max(maxbound,bound);
    }
  }
  environment();
  // Re-read every complete original native input before publication; same-buffer hashes above govern computation.
  need(read_fixed(in/"independent_n0.f32le",786432,sha(nr))==nr,"N0_POSTFLIGHT");
  need(read_fixed(in/"wq.bf16le",4718592,sha(wr))==wr,"WQ_POSTFLIGHT");
  const auto mb=little_bytes(math32),db=little_bytes(math64),tb=little_bytes(typed);
  std::ostringstream r;r<<std::setprecision(17);
  r<<"{\"schema\":1,\"status\":\"COMPLETE_TWO_MODEL_DIAGNOSTIC\",\"elements\":"<<COUNT
   <<",\"logical_macs\":301989888,\"official_raw_numeric_pass\":null,\"application_accuracy_pass\":null"
   <<",\"rtl_executed\":false,\"typed_recipe_bit_exact_to_rtl\":null,\"nonfinite_count\":0"
   <<",\"bit_equal_to_math_fp32\":"<<equal<<",\"max_ulp_to_math_fp32\":"<<maxulp
   <<",\"ulp_histogram_0_1_2to3_4to7_8to15_16to255_over255\":[";
  for(unsigned i=0;i<hist.size();++i){if(i)r<<',';r<<hist[i];}
  r<<"],\"max_abs_error_exact_units_2pow_minus266_hex\":\""<<maxerr.hex()<<"\",\"max_abs_error_index\":"<<maxindex
   <<",\"sum_abs_error_exact_units_2pow_minus266_hex\":\""<<sumerr.hex()<<"\""
   <<",\"max_abs_error_rn_f64\":"<<pc1_math::as_double({maxerr,false})
   <<",\"mean_abs_error_approx_f64\":"<<pc1_math::as_double({sumerr,false})/COUNT
   <<",\"max_relative_error_lower\":"<<maxrel_lo<<",\"max_relative_error_upper\":"<<maxrel_hi
   <<",\"zero_math_reference_count\":"<<zero_ref<<",\"zero_reference_nonzero_error_count\":"<<zero_ref_nonzero_error
   <<",\"analytic_bound_all_satisfied\":"<<(bounds_ok?"true":"false")<<",\"max_analytic_bound\":"<<maxbound
   <<",\"math_fp32_sha256\":\""<<sha(mb)<<"\",\"math_fp64_sha256\":\""<<sha(db)<<"\",\"typed_fp32_sha256\":\""<<sha(tb)<<"\"}\n";
  // No complete receipt exists until all complete outputs have been closed successfully.
  write_new(out/"qraw.math.f32le",mb);write_new(out/"qraw.math.f64le",db);write_new(out/"qraw.typed.f32le",tb);
  auto rs=r.str();write_new(out/"RESULT.json",std::vector<std::uint8_t>(rs.begin(),rs.end()));
  std::cout<<"{\"status\":\"COMPLETE_TWO_MODEL_DIAGNOSTIC\",\"elements\":196608}\n";
  return bounds_ok?0:1;
}
int main(int argc,char**argv){
  try{environment();if(argc==2 && std::string(argv[1])=="--micro"){micro();return 0;}
    need(argc==4 && std::string(argv[1])=="--full","ARGUMENTS");return full(argv[2],argv[3]);}
  catch(const std::exception&){std::cerr<<"PC1_REFERENCE_FAILED\n";return 2;}
}
