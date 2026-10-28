// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "affine_readonly_memory.hpp"
#include <charconv>
#include <fstream>
#include <map>
#include <set>
namespace stimulus {
inline uint64_t decimal(const std::string& s){uint64_t n=0;auto r=std::from_chars(s.data(),s.data()+s.size(),n);require(!s.empty()&&r.ec==std::errc()&&r.ptr==s.data()+s.size(),"decimal TSV field");return n;}
inline std::vector<std::string> split(const std::string& s,char sep){std::vector<std::string> v;size_t a=0;for(;;){auto b=s.find(sep,a);v.push_back(s.substr(a,b-a));if(b==std::string::npos)return v;a=b+1;}}
inline std::vector<uint64_t> vectorField(const std::string& s,uint64_t rank){auto fs=split(s,',');require(fs.size()==rank,"TSV vector rank");std::vector<uint64_t> v;for(const auto& f:fs)v.push_back(decimal(f));return v;}
struct ViewAllocation {std::string name;uint64_t base,bytes;};
// Every unique source is SHA-256 verified on the same open mapped file.
// Caller must retain exclusive immutable source ownership throughout execution.
inline void loadViews(const std::string& path,const std::vector<ViewAllocation>& allocations,ReadOnly& memory){
 std::ifstream f(path);require(bool(f),"view manifest open");std::string line;require(bool(std::getline(f,line))&&line=="AFFINE_BYTES_V1","view manifest version");
 std::map<std::string,std::shared_ptr<File>> files;std::map<std::string,std::pair<uint64_t,std::string>> pins;std::set<std::string> covered;size_t count=0,total=0;
 while(std::getline(f,line)){require(++count<=65536&&line.size()<=8192,"bounded view row");total+=line.size();require(total<=16*1024*1024,"bounded view manifest");auto x=split(line,'\t');require(x.size()==16&&x[0]=="map","view row fields");
  View v;v.address=decimal(x[2]);v.allocationBase=decimal(x[3]);v.allocationBytes=decimal(x[4]);auto rank=decimal(x[5]);require(rank>0&&rank<=8,"view rank");v.shape=vectorField(x[6],rank);v.destinationStrides=vectorField(x[7],rank);v.sourceOffset=decimal(x[9]);v.sourceStrides=vectorField(x[10],rank);auto se=decimal(x[11]),de=decimal(x[12]);require(se<=4&&de<=4,"element sizes");v.sourceElementBytes=unsigned(se);v.destinationElementBytes=unsigned(de);
  bool allocation=false;for(const auto& a:allocations)if(a.base==v.allocationBase&&a.bytes==v.allocationBytes){allocation=true;covered.insert(a.name);}require(allocation,"view exact readonly allocation binding");
  if(x[13]=="zero"){v.transform=Transform::Zero;require(x[8]=="-"&&x[15]=="-"&&decimal(x[14])==0&&se==0&&v.sourceOffset==0,"zero view source prohibited");for(auto s:v.sourceStrides)require(s==0,"zero source stride");}
  else {require(x[13]=="identity"||x[13]=="bf16_to_fp32_bits","view transform");v.transform=x[13]=="identity"?Transform::Identity:Transform::Bf16ToFp32Bits;require(!x[8].empty()&&x[8][0]=='/'&&x[15].size()==64&&std::all_of(x[15].begin(),x[15].end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}),"source absolute path and SHA pin");auto bytes=decimal(x[14]);auto pin=std::make_pair(bytes,x[15]);auto p=pins.emplace(x[8],pin);require(p.second||p.first->second==pin,"conflicting source pins");auto it=files.find(x[8]);if(it==files.end()){auto source=std::make_shared<File>(x[8],bytes);source->verifySha256(x[15]);it=files.emplace(x[8],std::move(source)).first;}v.source=it->second;}
  memory.addView(std::move(v));
 }
 require(f.eof()&&count>0,"complete view manifest");for(const auto& a:allocations)require(covered.count(a.name)==1,"readonly allocation missing views");
}
}
