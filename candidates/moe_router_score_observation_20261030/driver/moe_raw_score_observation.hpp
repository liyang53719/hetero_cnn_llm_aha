// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>
namespace moe_raw_score_observation {
inline void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Beat {uint64_t transactionId=0;uint32_t ownerSequence=0,profile=0,token=0,expert=0,score=0;};
// Host-side collector only. No writes/ready/service requests to hardware.
class Collector {
 uint32_t profile_,count_=0,owner_=0;uint64_t tx_=0;bool bound_=false,closed_=false;
 std::vector<uint32_t> data_;
public:
 explicit Collector(uint32_t profile):profile_(profile){require(profile<=4,"score profile bounds");if(profile>=3)data_.resize(32768);}
 uint32_t count()const{return count_;}
 uint64_t transactionId()const{return tx_;}uint32_t ownerSequence()const{return owner_;}
 void capture(const Beat& b,bool launched,bool fault){
  require(!closed_&&launched&&!fault,"score outside live clean launch");
  require(profile_>=3&&b.profile==profile_,"score wrong profile");
  require(b.token<128&&b.expert<256&&count_<32768,"score shape/count bounds");
  require(b.token==count_/256&&b.expert==count_%256,"score missing/duplicate/reordered event");
  require((b.score>>31)==0&&b.score<=0x3f800000,"score outside finite probability range");
  if(!bound_){tx_=b.transactionId;owner_=b.ownerSequence;bound_=true;}
  require(b.transactionId==tx_&&b.ownerSequence==owner_,"score owner changed");
  data_[count_++]=b.score;
 }
 void close(bool clean){require(!closed_&&clean,"score needs clean terminal");require(profile_<3||(bound_&&count_==32768),"score incomplete M128");closed_=true;}
 void write(const std::filesystem::path& dir)const{
  require(closed_,"score dump before terminal");if(profile_<3)return;
  auto p=dir/"router_selection_scores.fp32.actual.bin";require(!std::filesystem::exists(p),"fresh score evidence only");
  std::ofstream f(p,std::ios::binary);for(auto word:data_)for(unsigned i=0;i<4;i++)f.put(char(word>>(8*i)));
  f.close();require(bool(f),"score dump write/close failure");
 }
};
}
