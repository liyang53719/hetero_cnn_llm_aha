// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>
namespace moe_raw_score_observation {
inline void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
struct Beat {
 uint64_t transactionId=0;uint32_t ownerSequence=0,profile=0,token=0,expert=0,score=0;
 uint32_t kind=0,rank=0,last=0;
};
// Host-side collector only. Actual output scores are NEVER reconstructed from IDs.
class Collector {
 uint32_t profile_,events_=0,inputs_=0,outputs_=0,owner_=0;uint64_t tx_=0;
 uint32_t inputMismatches_=0,orderMismatches_=0,nonfinite_=0,negative_=0,negativeZero_=0,aboveOne_=0;
 bool bound_=false,closed_=false;
 std::vector<uint32_t> input_,selected_,ids_;
public:
 explicit Collector(uint32_t profile):profile_(profile){
  require(profile<=4,"score profile bounds");
  if(profile>=3){input_.resize(32768);selected_.resize(1024);ids_.resize(1024);}
 }
 uint32_t count()const{return inputs_;}uint32_t selectedCount()const{return outputs_;}
 uint32_t inputMismatches()const{return inputMismatches_;}uint32_t orderMismatches()const{return orderMismatches_;}
 uint32_t nonfiniteScores()const{return nonfinite_;}uint32_t negativeScores()const{return negative_;}
 uint32_t negativeZeroScores()const{return negativeZero_;}uint32_t aboveOneScores()const{return aboveOne_;}
 uint64_t transactionId()const{return tx_;}uint32_t ownerSequence()const{return owner_;}
 void capture(const Beat& b,bool launched,bool fault){
  require(!closed_&&launched&&!fault,"score outside live clean launch");
  require(profile_>=3&&b.profile==profile_,"score wrong profile");
  require(b.token<128&&b.expert<256&&events_<33792&&b.kind<=1&&b.last<=1,"score shape/count/event bounds");
  const auto token=events_/264,position=events_%264;
  require(b.token==token&&b.kind==uint32_t(position>=256),"score missing/duplicate/reordered event kind");
  // Every UInt32 score bit pattern is valid observation payload, including
  // NaN/Inf/negative/-0. Numeric classification never gates acquisition.
  if(bound_)require(b.transactionId==tx_&&b.ownerSequence==owner_,"score owner changed");
  if(b.kind==0){
   require(b.expert==position&&b.rank==0&&b.last==0,"score input index/metadata");
   input_[inputs_]=b.score;
  }else{
   const auto rank=position-256;
   require(b.rank==rank&&b.last==uint32_t(rank==7),"selected rank/last");
   for(uint32_t i=0;i<rank;i++)require(ids_[token*8+i]!=b.expert,"duplicate selected expert");
   // Numerical differences are evidence, NEVER a reason to discard actual bits.
   if(b.score!=input_[token*256+b.expert])++inputMismatches_;
   if(rank){
    const auto previous=selected_[outputs_-1];
    const auto nan=[](uint32_t x){return (x&0x7f800000)==0x7f800000&&(x&0x007fffff)!=0;};
    const auto key=[](uint32_t x){if((x&0x7fffffff)==0)x=0;return (x>>31)?~x:(x^0x80000000);};
    if(!nan(b.score)&&!nan(previous)&&key(b.score)>key(previous))++orderMismatches_;
   }
   // Store the REAL selection.out bits after validation. Do not gather input_.
   selected_[outputs_]=b.score;ids_[outputs_]=b.expert;
  }
  if(!bound_){tx_=b.transactionId;owner_=b.ownerSequence;bound_=true;}
  const bool nonfinite=(b.score&0x7f800000)==0x7f800000;
  if(nonfinite)++nonfinite_;
  if((b.score>>31)&&(b.score&0x7fffffff)!=0)++negative_;
  if(b.score==0x80000000)++negativeZero_;
  if(!nonfinite&&!(b.score>>31)&&b.score>0x3f800000)++aboveOne_;
  ++events_;if(b.kind==0)++inputs_;else ++outputs_;
 }
 void close(bool clean){
  require(!closed_&&clean,"score needs clean terminal");
  require(profile_<3||(bound_&&events_==33792&&inputs_==32768&&outputs_==1024),"score incomplete M128 input/output");
  closed_=true;
 }
 void write(const std::filesystem::path& dir)const{
  require(closed_,"score dump before terminal");if(profile_<3)return;
  const char* names[]={"router_selection_scores.fp32.actual.bin","router_selected_scores.fp32.actual.bin","router_selected_ids.u32.actual.bin"};
  const std::vector<uint32_t>* values[]={&input_,&selected_,&ids_};
  for(const auto name:names)require(!std::filesystem::exists(dir/name),"fresh score evidence only");
  for(unsigned n=0;n<3;n++){
   std::ofstream f(dir/names[n],std::ios::binary);
   for(auto word:*values[n])for(unsigned i=0;i<4;i++)f.put(char(word>>(8*i)));
   f.close();require(bool(f),"score dump write/close failure");
  }
 }
};
}
