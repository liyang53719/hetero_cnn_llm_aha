#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include "fp32_exp2_pwl_table.h"
static float fb(uint32_t x){return std::bit_cast<float>(x);}static uint32_t ub(float x){return std::bit_cast<uint32_t>(x);}static float add(float a,float b){volatile float x=a+b;return x;}static float mul(float a,float b){volatile float x=a*b;return x;}static float ex2(float x){int q=(int)std::floor((double)x*16);if(q<-256)return 0;if(q>=0)return 1;auto c=kCoeff.at(q+256);return add(mul(fb(c>>32),x),fb((uint32_t)c));}static float ex(float x){return ex2(mul(x,fb(0x3fb8aa3b)));}
int main(int argc,char**argv){std::ifstream f(argc>1?argv[1]:"tests/vectors/fp32_mlo_merge_vectors.txt");std::string line;int n=0;while(std::getline(f,line)){std::istringstream s(line);std::array<uint32_t,18>r{};for(auto&x:r)s>>std::hex>>x;float ma=fb(r[0]),la=fb(r[1]),mb=fb(r[2]),lb=fb(r[3]);std::array<float,4>oa,ob,o;for(int i=0;i<4;i++){oa[i]=fb(r[4+i]);ob[i]=fb(r[8+i]);}float m,l;if((ub(la)&0x7fffffff)==0){m=mb;l=lb;o=ob;}else if((ub(lb)&0x7fffffff)==0){m=ma;l=la;o=oa;}else{m=std::max(ma,mb);float a=ex(add(ma,-m)),b=ex(add(mb,-m));l=add(mul(la,a),mul(lb,b));for(int i=0;i<4;i++)o[i]=add(mul(oa[i],a),mul(ob[i],b));}if(ub(m)!=r[12]||ub(l)!=r[13])return 2;for(int i=0;i<4;i++)if(ub(o[i])!=r[14+i])return 3;n++;}std::cout<<"{\"status\":\"PASS\",\"cases\":"<<n<<"}\n";return n?0:4;}
