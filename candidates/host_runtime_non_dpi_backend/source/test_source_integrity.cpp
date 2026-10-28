#include "affine_readonly_memory.hpp"
#include <fstream>
#include <iostream>
using namespace stimulus;
template<class F> void rejected(F f){bool fail=false;try{f();}catch(const std::exception&){fail=true;}require(fail,"negative must reject");}
int main(int argc,char**argv){require(argc==2,"fresh synthetic fixture path");require(access(argv[1],F_OK)!=0,"fresh fixture only");{std::ofstream f(argv[1],std::ios::binary);f<<"abc";}File f(argv[1],3);f.verifySha256("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");rejected([&]{f.verifySha256(std::string(64,'0'));});{std::ofstream out(argv[1],std::ios::binary|std::ios::app);out<<'d';}rejected([&]{f.checkStable();});std::cout<<"PASS_SOURCE_INTEGRITY_ONLY known_SHA wrong_SHA mutation\n";}
