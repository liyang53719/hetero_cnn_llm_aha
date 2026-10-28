// SPDX-License-Identifier: Apache-2.0
#pragma once
// Byte-only stimulus mapping of sources verified by the caller. No operator, oracle, routing or numeric evaluation.
// The TSV loader verifies full SHA-256 on this same open mapping before admission.
// External mutation is forbidden; stat stability checks detect changes, not OS-level immutability.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <openssl/evp.h>
namespace stimulus {
inline void require(bool v,const char* m){if(!v)throw std::runtime_error(m);}
inline uint64_t add(uint64_t a,uint64_t b){require(b<=UINT64_MAX-a,"address overflow");return a+b;}
inline uint64_t mul(uint64_t a,uint64_t b){require(!a||b<=UINT64_MAX/a,"size overflow");return a*b;}
struct File {
 int fd=-1;const uint8_t* data=nullptr;uint64_t bytes=0;struct stat identity{};
 explicit File(const std::string& path,uint64_t expectedBytes){
  fd=open(path.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);require(fd>=0,"source open failed");
  struct stat st{};if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<=0||uint64_t(st.st_size)!=expectedBytes){close(fd);fd=-1;throw std::runtime_error("source identity size mismatch");}
  identity=st;bytes=uint64_t(st.st_size);void* p=mmap(nullptr,bytes,PROT_READ,MAP_PRIVATE,fd,0);if(p==MAP_FAILED){close(fd);fd=-1;throw std::runtime_error("source mmap failed");}data=static_cast<const uint8_t*>(p);
 }
 void checkStable()const{struct stat now{};require(fstat(fd,&now)==0&&now.st_dev==identity.st_dev&&now.st_ino==identity.st_ino&&now.st_size==identity.st_size&&now.st_mtim.tv_sec==identity.st_mtim.tv_sec&&now.st_mtim.tv_nsec==identity.st_mtim.tv_nsec&&now.st_ctim.tv_sec==identity.st_ctim.tv_sec&&now.st_ctim.tv_nsec==identity.st_ctim.tv_nsec,"mapped source changed during run");}
 void verifySha256(const std::string& expected)const{
  checkStable();std::unique_ptr<EVP_MD_CTX,decltype(&EVP_MD_CTX_free)> ctx(EVP_MD_CTX_new(),EVP_MD_CTX_free);require(bool(ctx)&&EVP_DigestInit_ex(ctx.get(),EVP_sha256(),nullptr)==1,"SHA initialization");
  for(uint64_t offset=0;offset<bytes;){auto n=std::min<uint64_t>(65536,bytes-offset);require(EVP_DigestUpdate(ctx.get(),data+offset,n)==1,"SHA update");offset+=n;}
  unsigned char digest[EVP_MAX_MD_SIZE];unsigned n=0;require(EVP_DigestFinal_ex(ctx.get(),digest,&n)==1&&n==32,"SHA finish");std::string actual;const char* hex="0123456789abcdef";for(unsigned i=0;i<n;++i){actual+=hex[digest[i]>>4];actual+=hex[digest[i]&15];}checkStable();require(actual==expected,"source SHA256 mismatch");
 }
 File(const File&)=delete;File& operator=(const File&)=delete;
 ~File(){if(data)munmap(const_cast<uint8_t*>(data),bytes);if(fd>=0)close(fd);}
};
enum class Transform {Identity,Bf16ToFp32Bits,Zero};
struct View {
 uint64_t address=0,allocationBase=0,allocationBytes=0,sourceOffset=0;
 unsigned sourceElementBytes=0,destinationElementBytes=0;
 std::vector<uint64_t> shape,destinationStrides,sourceStrides;
 std::shared_ptr<File> source;Transform transform=Transform::Identity;
 std::vector<size_t> order;uint64_t end=0;
 void validate(){
  require(transform==Transform::Identity||transform==Transform::Bf16ToFp32Bits||transform==Transform::Zero,"unknown transform");
  require(transform==Transform::Zero||sourceElementBytes==1||sourceElementBytes==2||sourceElementBytes==4,"source element bytes");
  require(!shape.empty()&&shape.size()<=8&&shape.size()==destinationStrides.size()&&shape.size()==sourceStrides.size(),"view rank");
  require(destinationElementBytes==1||destinationElementBytes==2||destinationElementBytes==4,"destination element bytes");
  require(transform==Transform::Zero||source,"missing source");
  require(transform!=Transform::Identity||sourceElementBytes==destinationElementBytes,"identity element size");
  require(transform!=Transform::Bf16ToFp32Bits||(sourceElementBytes==2&&destinationElementBytes==4),"bit expansion shape");
  order.resize(shape.size());uint64_t last=0,lastSource=sourceOffset;
  for(size_t i=0;i<shape.size();++i){require(shape[i]>0&&destinationStrides[i]>0,"shape/stride positive");order[i]=i;last=add(last,mul(shape[i]-1,destinationStrides[i]));if(transform!=Transform::Zero)lastSource=add(lastSource,mul(shape[i]-1,sourceStrides[i]));}
  std::sort(order.begin(),order.end(),[&](size_t a,size_t b){return destinationStrides[a]>destinationStrides[b];});
  // Reject self-overlap or non-hierarchical layouts; singleton axes do not consume span.
  uint64_t inner=destinationElementBytes;
  for(auto it=order.rbegin();it!=order.rend();++it){auto i=*it;if(shape[i]>1){require(destinationStrides[i]>=inner,"overlapping destination view");inner=add(mul(shape[i]-1,destinationStrides[i]),inner);}}
  end=add(address,add(last,destinationElementBytes));require(address>=allocationBase&&end<=add(allocationBase,allocationBytes),"view crosses allocation");
  if(transform!=Transform::Zero)require(add(lastSource,sourceElementBytes)<=source->bytes,"source extent");
 }
 bool byte(uint64_t a,uint8_t& value)const{
  if(a<address||a>=end)return false;
  uint64_t rem=a-address,off=sourceOffset;
  for(auto i:order){if(shape[i]==1)continue;auto c=rem/destinationStrides[i];if(c>=shape[i])return false;rem%=destinationStrides[i];if(transform!=Transform::Zero)off=add(off,mul(c,sourceStrides[i]));}
  if(rem>=destinationElementBytes)return false;
  if(transform==Transform::Zero)value=0;
  else if(transform==Transform::Bf16ToFp32Bits)value=rem<2?0:source->data[off+rem-2];
  else value=source->data[off+rem];
  return true;
 }
};
class ReadOnly {
 std::vector<View> views;
 public:
 void checkStable()const{for(const auto& v:views)if(v.source)v.source->checkStable();}
 void addView(View v){require(views.size()<65536,"view count");v.validate();views.push_back(std::move(v));}
 uint8_t byte(uint64_t address)const{uint8_t value=0,next=0;unsigned found=0;for(const auto& v:views)if(v.byte(address,next)){value=next;require(++found==1,"ambiguous overlapping immutable views");}require(found==1,"unmapped immutable byte");return value;}
 void read(uint64_t address,uint8_t* out,size_t n)const{require(out!=nullptr&&n>0&&n<=4096,"bounded byte read");add(address,n);for(size_t i=0;i<n;++i)out[i]=byte(address+i);}
};
} // namespace stimulus
