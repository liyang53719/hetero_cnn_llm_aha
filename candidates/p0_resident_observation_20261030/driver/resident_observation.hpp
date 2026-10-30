// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>
namespace resident_observation {
inline void require(bool yes,const char* msg){if(!yes)throw std::runtime_error(msg);}
struct Beat {
 uint32_t identity=0,slot=0,ng=0,index=0,rows=0,cols=0;
 uint32_t gateTag=0,upTag=0,actTag=0,profile=0;
 std::array<uint32_t,16> value{};
};
// Host-side evidence storage only. No outputs/ready are returned to the DUT.
class Collector {
 static constexpr uint32_t Rows=128,Cols=8960,Tile=160,Groups=56,BeatsPerGroup=1280;
 uint32_t profile_,epoch_,commands_; bool bound_=false,closed_=false;
 uint32_t identity_=0,gate_=0,up_=0,act_=0;uint64_t count_=0;
 std::vector<uint8_t> seen_;std::array<std::vector<uint32_t>,2> data_;
public:
 Collector(uint32_t profile,uint32_t epoch,uint32_t commands):profile_(profile),epoch_(epoch),commands_(commands){
  require(profile<=4&&epoch<=65535&&commands>0&&commands<=65535,"observation launch bounds");
  if(profile==0){seen_.resize(2*Groups*BeatsPerGroup);for(auto& d:data_)d.resize(Rows*Cols);}
 }
 uint64_t count()const{return count_;}
 void capture(const Beat& b,uint32_t currentPc,bool launched,bool fault){
  require(!closed_&&launched&&!fault,"resident observation outside live clean execution");
  require(profile_==0&&b.profile==profile_,"resident observation wrong runtime profile");
  require(b.rows==Rows&&b.cols==Tile&&b.slot<2&&b.ng<Cols&&b.ng%Tile==0&&b.index<BeatsPerGroup,"resident observation shape/index bounds");
  require((b.gateTag>>16)==epoch_&&(b.upTag>>16)==epoch_&&(b.actTag>>16)==epoch_,"resident observation epoch");
  auto g=b.gateTag&65535,u=b.upTag&65535,a=b.actTag&65535;
  require(g<u&&u<a&&a<commands_&&currentPc==a,"resident observation retained command phase");
  require(b.identity!=0&&b.identity==uint32_t(b.gateTag+1),"resident identity derives from actual gate tag");
  if(!bound_){identity_=b.identity;gate_=b.gateTag;up_=b.upTag;act_=b.actTag;bound_=true;}
  require(b.identity==identity_&&b.gateTag==gate_&&b.upTag==up_&&b.actTag==act_,"resident observation owner changed");
  auto beat=b.slot*Groups*BeatsPerGroup+(b.ng/Tile)*BeatsPerGroup+b.index;
  require(!seen_[beat],"duplicate resident observation beat");
  // Explicit bijection from physical 16-bank beat to row-major FP32 values.
  auto rowBase=(b.index/Tile)*16,col=b.ng+b.index%Tile;
  for(unsigned lane=0;lane<16;lane++){
   require(((b.value[lane]>>23)&255)!=255,"nonfinite resident observation");
   data_[b.slot][(rowBase+lane)*Cols+col]=b.value[lane];
  }
  seen_[beat]=1;++count_;
 }
 void close(bool cleanTerminal){
  require(!closed_&&cleanTerminal,"resident collector requires clean Host terminal");
  require(profile_!=0||(bound_&&count_==2*Groups*BeatsPerGroup),"incomplete resident full128 coverage");
  for(auto b:seen_)require(b==1,"missing resident observation beat");closed_=true;
 }
 void write(const std::filesystem::path& directory)const{
  require(closed_,"resident evidence before terminal forbidden");if(profile_!=0)return;
  const char* names[]={"resident_gate.fp32.actual.bin","resident_up.fp32.actual.bin"};
  for(unsigned s=0;s<2;s++){
   auto p=directory/names[s];require(!std::filesystem::exists(p),"fresh resident evidence only");
   std::ofstream f(p,std::ios::binary);for(auto x:data_[s])for(unsigned byte=0;byte<4;byte++)f.put(char(x>>(8*byte)));
   f.close();require(bool(f),"resident output write/close failed");
  }
 }
};
}
