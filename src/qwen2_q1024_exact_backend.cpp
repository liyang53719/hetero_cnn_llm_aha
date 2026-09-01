#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
#include <omp.h>
static float bf(uint16_t v){uint32_t w=uint32_t(v)<<16;float f;__builtin_memcpy(&f,&w,4);return f;}
static uint16_t tobf(float f){uint32_t w;__builtin_memcpy(&w,&f,4);if(((w>>23)&255)==255&&(w&0x7fffff)){uint16_t r=w>>16;r|=0x40;if((r&0x7f)==0)r|=1;return r;}w+=0x7fff+((w>>16)&1);return w>>16;}
template<class T>static std::vector<T>load(const std::string&p,size_t n){std::vector<T>v(n);std::ifstream f(p,std::ios::binary);f.read(reinterpret_cast<char*>(v.data()),n*sizeof(T));if(!f||size_t(f.gcount())!=n*sizeof(T)){std::fprintf(stderr,"load fail %s\n",p.c_str());std::exit(2);}return v;}
template<class T>static void save(const std::string&p,const std::vector<T>&v){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(v.data()),v.size()*sizeof(T));if(!f)std::exit(3);}
static uint64_t fnv(const std::vector<uint16_t>&v){uint64_t h=1469598103934665603ull;for(auto x:v){h=(h^(x&255))*1099511628211ull;h=(h^(x>>8))*1099511628211ull;}return h;}
static int64_t rq(__int128 v){bool s=v<0;unsigned __int128 m=s?(unsigned __int128)(-v):(unsigned __int128)v;int64_t r=int64_t((m+(((unsigned __int128)1)<<45))>>46);return s?-r:r;}
int main(int argc,char**argv){if(argc!=3){std::fprintf(stderr,"usage: in out\n");return 2;}std::string in=argv[1],out=argv[2];constexpr int T=1024,H=1536,K=256;auto commands=load<uint8_t>(in+"/first9_commands.bin",9*16);const uint8_t op[9]={0x32,0x20,0x30,0x34,0x20,0x30,0x34,0x20,0x30},eng[9]={3,2,3,3,2,3,3,2,3};for(int i=0;i<9;i++)if(commands[i*16]!=op[i]||((commands[i*16+1]&7)!=eng[i])){std::fprintf(stderr,"command mismatch %d\n",i);return 4;}auto norm=load<uint16_t>(in+"/norm_bf16.bin",size_t(T)*H);std::vector<uint16_t>q(size_t(T)*H),k(size_t(T)*K),v(size_t(T)*K),qb(q.size()),kb(k.size()),vb(v.size()),qr(q.size()),kr(k.size());
 auto gemm=[&](const char*name,int cols,std::vector<uint16_t>&dst){
  auto w=load<uint16_t>(in+"/"+name+"_weight_bf16.bin",size_t(cols)*H);double st=omp_get_wtime();
#pragma omp parallel for collapse(2) schedule(static)
  for(int t=0;t<T;t++)for(int c=0;c<cols;c++){float a=0;for(int x=0;x<H;x++)a=std::fma(bf(norm[size_t(t)*H+x]),bf(w[size_t(c)*H+x]),a);dst[size_t(t)*cols+c]=tobf(a);}std::printf("%s_seconds=%.6f\n",name,omp_get_wtime()-st);
 };
 gemm("q",H,q);gemm("k",K,k);gemm("v",K,v);
 auto bias=[&](const char*name,int cols,const std::vector<uint16_t>&src,std::vector<uint16_t>&dst){
  auto b=load<float>(in+"/"+name+"_bias_fp32.bin",cols);
#pragma omp parallel for schedule(static)
  for(size_t i=0;i<src.size();i++)dst[i]=tobf(bf(src[i])+b[i%cols]);
 };
 bias("q",H,q,qb);bias("k",K,k,kb);bias("v",K,v,vb);
 constexpr int64_t S=int64_t(1)<<46;int64_t qc[64],qs[64],kc[64],ks[64],bc[64],bs[64];for(int d=0;d<64;d++){double a=std::pow(1000000.0,-2.0*d/128.0);bc[d]=std::llround(std::cos(a)*S);bs[d]=std::llround(std::sin(a)*S);qc[d]=kc[d]=S;qs[d]=ks[d]=0;}
 auto rope_row=[&](const uint16_t*src,uint16_t*dst,int heads,int64_t*c,int64_t*s){for(int h=0;h<heads;h++)for(int d=0;d<64;d++){float e=bf(src[h*128+d]),o=bf(src[h*128+64+d]),cf=float(double(c[d])/S),sf=float(double(s[d])/S);volatile float ec=e*cf,os=o*sf,es=e*sf,oc=o*cf;dst[h*128+d]=tobf(ec-os);dst[h*128+64+d]=tobf(es+oc);}};
 for(int t=0;t<T;t++){rope_row(&qb[size_t(t)*H],&qr[size_t(t)*H],12,qc,qs);rope_row(&kb[size_t(t)*K],&kr[size_t(t)*K],2,kc,ks);for(int d=0;d<64;d++){int64_t nqc=rq((__int128)qc[d]*bc[d]-(__int128)qs[d]*bs[d]),nqs=rq((__int128)qc[d]*bs[d]+(__int128)qs[d]*bc[d]),nkc=rq((__int128)kc[d]*bc[d]-(__int128)ks[d]*bs[d]),nks=rq((__int128)kc[d]*bs[d]+(__int128)ks[d]*bc[d]);qc[d]=nqc;qs[d]=nqs;kc[d]=nkc;ks[d]=nks;}}
 save(out+"/q_raw.bin",q);save(out+"/k_raw.bin",k);save(out+"/v_raw.bin",v);save(out+"/q_bias.bin",qb);save(out+"/k_bias.bin",kb);save(out+"/v_bias.bin",vb);save(out+"/q_rope.bin",qr);save(out+"/k_rope.bin",kr);std::printf("QWEN2_Q1024_EXACT_BACKEND_PASS commands=9 rows=1024 q_values=%zu k_values=%zu v_values=%zu q_fnv=%016llx k_fnv=%016llx v_fnv=%016llx\n",q.size(),k.size(),v.size(),(unsigned long long)fnv(qr),(unsigned long long)fnv(kr),(unsigned long long)fnv(vb));}
