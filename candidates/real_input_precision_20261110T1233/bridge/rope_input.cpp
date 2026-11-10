// Input-only extraction of pinned host_real_inputs.cpp line 123, not forward/reference evaluation.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <vector>
int main(int argc,char**argv){if(argc!=2)return 2;constexpr unsigned MAX_TOKENS=1024,HD=128;std::vector<float> a(2*MAX_TOKENS*HD/2);
for(unsigned t=0;t<MAX_TOKENS;t++)for(unsigned i=0;i<HD/2;i++){double angle=t/std::pow(1000000.0,2.0*i/HD);a[size_t(t)*HD/2+i]=float(std::cos(angle));a[size_t(MAX_TOKENS)*HD/2+size_t(t)*HD/2+i]=float(std::sin(angle));}
std::ofstream o(argv[1],std::ios::binary);for(float f:a){uint32_t u;std::memcpy(&u,&f,4);for(unsigned b=0;b<4;b++)o.put(char(u>>(8*b)));}return o?0:3;}
