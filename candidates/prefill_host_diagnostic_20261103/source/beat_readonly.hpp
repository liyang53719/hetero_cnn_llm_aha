// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "affine_readonly_memory.hpp"
#include <array>
namespace stimulus_candidate {
// Extracted experiment only. Caller must retain allocation/virtual guards, source
// SHA admission and checkStable cadence. Never caches file bytes across calls.
class BeatReadOnly {
 struct Entry { stimulus::View view; bool dense; };
 std::vector<Entry> entries;
 // Sorted indices, not copies of source data. Equal starts retain insertion order.
 std::vector<size_t> starts;
 static bool dense(const stimulus::View& v) {
  uint64_t dest=v.destinationElementBytes, src=v.sourceElementBytes;
  for(auto it=v.order.rbegin();it!=v.order.rend();++it) {
   size_t i=*it; if(v.shape[i]==1)continue;
   if(v.destinationStrides[i]!=dest)return false;
   if(v.transform!=stimulus::Transform::Zero&&v.sourceStrides[i]!=src)return false;
   dest=stimulus::mul(dest,v.shape[i]);
   if(v.transform!=stimulus::Transform::Zero)src=stimulus::mul(src,v.shape[i]);
  }
  return true;
 }
 public:
 void addView(stimulus::View v) {
  stimulus::require(entries.size()<65536,"view count");v.validate();
  bool d=dense(v);size_t id=entries.size();entries.push_back({std::move(v),d});
  auto p=std::upper_bound(starts.begin(),starts.end(),entries[id].view.address,
   [&](uint64_t a,size_t j){return a<entries[j].view.address;});try { starts.insert(p,id); }
  catch (...) { entries.pop_back(); throw; } // keep both containers logically transactional
 }
 void checkStable()const { for(const auto& e:entries)if(e.view.source)e.view.source->checkStable(); }
 // Exactly the old read's bounds and byte/error order, split into bounded beats.
 void read(uint64_t address,uint8_t* out,size_t n)const {
  stimulus::require(out!=nullptr&&n>0&&n<=4096,"bounded byte read");stimulus::add(address,n);
  for(size_t done=0;done<n;) {size_t count=std::min<size_t>(64,n-done);readPart(address+done,out+done,count);done+=count;}
 }
 private:
 void readPart(uint64_t a,uint8_t* out,size_t n)const {
  uint64_t end=a+n; // read already checked whole range.
  std::array<uint8_t,64> values{}, hits{};
  auto stop=std::lower_bound(starts.begin(),starts.end(),end,
   [&](size_t j,uint64_t b){return entries[j].view.address<b;});
  for(auto it=starts.begin();it!=stop;++it) {
   const auto& e=entries[*it];const auto& v=e.view;if(v.end<=a)continue;
   uint64_t lo=std::max(a,v.address),hi=std::min(end,v.end);
   for(uint64_t b=lo;b<hi;++b) {
    uint8_t value=0;bool mapped=true;
    if(e.dense) {
     uint64_t rel=b-v.address;
     if(v.transform==stimulus::Transform::Zero)value=0;
     else if(v.transform==stimulus::Transform::Identity)value=v.source->data[v.sourceOffset+rel];
     else value=(rel%4<2)?0:v.source->data[v.sourceOffset+(rel/4)*2+rel%4-2];
    } else mapped=v.byte(b,value); // exact affine membership for holes/transposes
    if(mapped){size_t j=b-a;values[j]=value;if(hits[j]<2)++hits[j];}
   }
  }
  // Important: first failing byte and already-written prefix match old read.
  for(size_t j=0;j<n;++j) {
   stimulus::require(hits[j]!=2,"ambiguous overlapping immutable views");
   stimulus::require(hits[j]==1,"unmapped immutable byte");out[j]=values[j];
  }
 }
};
}
