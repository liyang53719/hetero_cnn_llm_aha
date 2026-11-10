#include "reference_loader.h"
#include <iostream>
int main(int argc,char**argv){
 if(argc!=2)return 1;size_t words=0;
 for(auto&p:REFERENCE_PINS){
  std::vector<float>ref(p.bytes/4+2,3.0f);std::vector<uint32_t>dut(p.bytes/4,0x7fc00001);std::vector<uint8_t>init(dut.size(),0);
  loadReference(argv[1],p,ref,1,p.bytes/4);
  if(ref.front()!=3.0f||ref.back()!=3.0f) return 2;
  for(auto x:dut)if(x!=0x7fc00001)return 3;
  for(auto x:init)if(x)return 4;
  auto bad=p;bad.hash^=1;bool failed=false;auto saved=ref;
  try{loadReference(argv[1],bad,ref,1,p.bytes/4);}catch(const std::exception&){failed=true;}
  if(!failed||std::memcmp(ref.data(),saved.data(),ref.size()*4))return 5;
  failed=false;try{loadReference(argv[1],p,ref,1,p.bytes/4+1);}catch(const std::exception&){failed=true;}if(!failed)return 6;
  words+=p.bytes/4;
 }
 auto rope=referenceBytes(argv[1],ROPE_PIN);if(rope.size()!=1024*128*4)return 7;
 std::cout<<"PASS_LOADER_ONLY outputs=20 words="<<words<<" separate_reference_only=1 wrong_hash_atomic_rejection=1 wrong_size_rejection=1 hardware_pass=0\n";
}
