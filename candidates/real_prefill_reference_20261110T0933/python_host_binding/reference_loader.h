#pragma once
#include <filesystem>
#include <fstream>
#include <vector>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <algorithm>
#include "reference_pins.h"
inline std::vector<uint8_t> referenceBytes(const std::filesystem::path&root,const ReferencePin&p){
 std::ifstream f(root/(std::string(p.name)+".f32le"),std::ios::binary|std::ios::ate);
 if(!f||uint64_t(f.tellg())!=p.bytes)throw std::runtime_error("reference size");
 std::vector<uint8_t>b(p.bytes);f.seekg(0);f.read(reinterpret_cast<char*>(b.data()),b.size());
 if(!f)throw std::runtime_error("reference read");
 uint64_t h=1469598103934665603ULL;for(auto v:b)h=(h^v)*1099511628211ULL;
 if(h!=p.hash){throw std::runtime_error("reference fingerprint");}
 return b;
}
// Takes only the separate expected-value array. No DUT-memory/initialized API.
inline void loadReference(const std::filesystem::path&root,const ReferencePin&p,
 std::vector<float>&oracle,size_t offset,size_t words){
 if(words!=p.bytes/4||p.bytes%4||offset>oracle.size()||words>oracle.size()-offset)throw std::runtime_error("reference span");
 auto b=referenceBytes(root,p);
 for(size_t i=0;i<words;i++){uint32_t u=uint32_t(b[4*i])|(uint32_t(b[4*i+1])<<8)|(uint32_t(b[4*i+2])<<16)|(uint32_t(b[4*i+3])<<24);std::memcpy(&oracle[offset+i],&u,4);}
}
