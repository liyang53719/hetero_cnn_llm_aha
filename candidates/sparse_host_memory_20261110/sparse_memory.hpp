#pragma once
#include <array>
#include <bitset>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <vector>
#include <limits>
// External testbench memory only: no arithmetic, reference values or fabricated
// producer receipts. Pages exist only when initialized or actually written.
class SparseHostMemory {
 struct Page {std::array<uint8_t,4096> data{};std::bitset<4096> valid;};
 struct Span {uint64_t base,end;};
 std::map<uint64_t,Page> pages;
 std::vector<Span> readonly;
 static void span(uint64_t a,uint64_t n){if(n>std::numeric_limits<uint64_t>::max()-a)throw std::out_of_range("memory address overflow");}
 bool locked(uint64_t a)const{for(const auto&s:readonly)if(a>=s.base&&a<s.end)return true;return false;}
 void put(uint64_t a,uint8_t b){auto&p=pages[a>>12];p.data[a&4095]=b;p.valid.set(a&4095);}
 public:
 size_t page_count()const{return pages.size();}
 void load_readonly(uint64_t a,const std::vector<uint8_t>&data){
  span(a,data.size());uint64_t end=a+data.size();
  for(const auto&s:readonly)if(a<s.end&&s.base<end)throw std::logic_error("readonly overlap");
  for(size_t i=0;i<data.size();++i){auto p=pages.find((a+i)>>12);if(p!=pages.end()&&p->second.valid[(a+i)&4095])throw std::logic_error("load overlaps previous write");}
  for(size_t i=0;i<data.size();++i)put(a+i,data[i]);
  readonly.push_back({a,end});
 }
 std::array<uint8_t,64> read64(uint64_t a)const{
  if(a&63){throw std::logic_error("unaligned AXI beat");}
  span(a,64);std::array<uint8_t,64> out{};
  for(size_t i=0;i<64;++i){auto p=pages.find((a+i)>>12);if(p==pages.end()||!p->second.valid[(a+i)&4095])throw std::logic_error("read lacks initialized or actual written byte");out[i]=p->second.data[(a+i)&4095];}return out;
 }
 void write64(uint64_t a,const std::array<uint8_t,64>&data,uint64_t mask){
  if(a&63){throw std::logic_error("unaligned AXI beat");}
  span(a,64);
  // Validate the whole transaction before any mutation.
  for(size_t i=0;i<64;++i)if((mask>>i)&1)if(locked(a+i))throw std::logic_error("write readonly input");
  for(size_t i=0;i<64;++i)if((mask>>i)&1)put(a+i,data[i]);
 }
};
