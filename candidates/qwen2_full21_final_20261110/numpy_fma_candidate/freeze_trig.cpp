#include <cmath>
#include <fstream>
int main(int argc,char**argv){constexpr unsigned MAX_TOKENS=1024,HD=128;
std::ofstream c(argv[1],std::ios::binary),s(argv[2],std::ios::binary);
for(unsigned t=0;t<MAX_TOKENS;t++)for(unsigned i=0;i<HD/2;i++){
double angle=t/std::pow(1000000.0,2.0*i/HD);
float cv=float(std::cos(angle)),sv=float(std::sin(angle));
c.write(reinterpret_cast<const char*>(&cv),4);s.write(reinterpret_cast<const char*>(&sv),4);}
return !c || !s;}
