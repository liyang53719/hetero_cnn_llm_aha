#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
static constexpr int R=16,K=8960,N=1536;
static float ff(uint32_t w){float x;std::memcpy(&x,&w,4);return x;}static uint32_t bb(float x){uint32_t w;std::memcpy(&w,&x,4);return w;}static uint16_t bf(float x){uint32_t w=bb(x);return(uint16_t)((w+0x7fff+((w>>16)&1))>>16);}
template<class T>static std::vector<T>read(const std::string&p,int width){std::ifstream f(p);if(!f)throw std::runtime_error("open "+p);std::vector<T>v;std::string s;while(std::getline(f,s))if(!s.empty())v.push_back((T)std::stoul(s,nullptr,16));return v;}
static void write(const std::string&p,const std::vector<uint32_t>&v){std::ofstream f(p);f<<std::hex<<std::setfill('0');for(auto x:v)f<<std::setw(8)<<x<<'\n';}
int main(int c,char**v){if(c!=7)return 2;try{int batch=std::stoi(v[4]);auto all=read<uint32_t>(v[1],32);auto res=read<uint32_t>(v[2],32);auto w=read<uint16_t>(v[3],16);if(all.size()%K||res.size()!=R*N||w.size()!=1ull*K*N)throw std::runtime_error("count");size_t rows=all.size()/K;if(rows%R||batch<0||(size_t)(batch+1)*R>rows)throw std::runtime_error("batch");std::vector<float>x(R*K);for(int r=0;r<R;r++)for(int k=0;k<K;k++)x[r*K+k]=ff((uint32_t)bf(ff(all[(batch*R+r)*K+k]))<<16);std::vector<uint32_t>d(R*N),fin(R*N);
#pragma omp parallel for schedule(static)
for(int n=0;n<N;n++){float a[R]={};for(int k=0;k<K;k++){float ww=ff((uint32_t)w[k*N+n]<<16);for(int r=0;r<R;r++)a[r]=std::fma(x[r*K+k],ww,a[r]);}for(int r=0;r<R;r++)d[r*N+n]=bb(a[r]);}
for(size_t i=0;i<d.size();i++)fin[i]=bb(ff(d[i])+ff(res[i]));write(v[5],d);write(v[6],fin);std::cout<<"L5_Q_PREFILL_DOWN_CPP_GOLDEN_PASS workload="<<rows<<" batch="<<batch<<" rows=16 shape=8960x1536\n";}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}return 0;}
