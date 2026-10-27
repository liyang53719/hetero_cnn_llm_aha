// SPDX-License-Identifier: Apache-2.0
#include "retained_endpoint_model.hpp"
#include "svdpi.h"
#include <array>
#include <memory>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <exception>

namespace {
using retained_model::EndpointInputs;
using retained_model::EndpointModel;
std::array<std::unique_ptr<EndpointModel>,8> endpoints;
unsigned created=0;
[[noreturn]] void failure(const char* why) { std::fprintf(stderr,"RETAINED_MODEL_FAIL %s\n",why);std::fflush(stderr);std::abort(); }
EndpointModel& checked(void* h) {
  for(const auto& p:endpoints)if(p && p.get()==h)return *p;
  throw std::runtime_error("unknown endpoint handle");
}
mpz_class packed(const svBitVecVal* x,unsigned words) {
  mpz_class n=0;mpz_import(n.get_mpz_t(),words,-1,sizeof(svBitVecVal),0,0,x);return n;
}
void export_packed(const mpz_class& x,svBitVecVal* out,unsigned words) {
  retained_model::require(x>=0&&(x==0||mpz_sizeinbase(x.get_mpz_t(),2)<=words*32),"packed DPI output width");
  std::fill(out,out+words,0);size_t count=0;mpz_export(out,&count,-1,sizeof(svBitVecVal),0,0,x.get_mpz_t());
  retained_model::require(count<=words,"packed DPI export bound");
}
EndpointInputs inputs(svBit rst,svBit cv,const svBitVecVal* cmd,svBit sv,unsigned ctx,svBit clear,svBit last,
    svBit command_last,const svBitVecVal* a,const svBitVecVal* b,svBit out_ready,svBit completion_ready) {
  retained_model::require(rst<=1&&cv<=1&&sv<=1&&clear<=1&&last<=1&&command_last<=1&&out_ready<=1&&completion_ready<=1&&ctx<8,"DPI scalar widths");
  EndpointInputs x;x.rst_n=rst;x.cmd_valid=cv;x.command=packed(cmd,4);x.step_valid=sv;x.step_context=ctx;
  x.step_clear=clear;x.step_last=last;x.command_last_tile=command_last;x.a=packed(a,8);x.b=packed(b,16);
  x.out_ready=out_ready;x.completion_ready=completion_ready;return x;
}
}
// This first wrapper is strictly unseeded. Seed-capable DUT and its new control
// are a separate qualification and must not be silently selected by a flag.
extern "C" void* retained_endpoint_create_unseeded() {
  try {retained_model::require(created<8,"more than eight full512 endpoints");
    auto p=std::make_unique<EndpointModel>(false);void* h=p.get();endpoints[created++]=std::move(p);return h;
  } catch(const std::exception& e){failure(e.what());}
}
extern "C" void retained_endpoint_reset(void* handle) {
  try {checked(handle).async_reset();}catch(const std::exception& e){failure(e.what());}
}
extern "C" void retained_endpoint_edge(void* handle,svBit rst,svBit cv,const svBitVecVal* cmd,svBit sv,
    unsigned ctx,svBit clear,svBit last,svBit command_last,const svBitVecVal* a,const svBitVecVal* b,
    svBit out_ready,svBit completion_ready) {
  try {auto& m=checked(handle);if(!rst)m.async_reset();else m.rising_edge(inputs(rst,cv,cmd,sv,ctx,clear,last,command_last,a,b,out_ready,completion_ready));}
  catch(const std::exception& e){failure(e.what());}
}
// Unseeded-only dependency partition. These are two independent read-only
// queries into the unchanged EndpointModel, not a cache or a second model.
// cmd_ready and every returned state output are independent of all live inputs
// when seed_enabled=false. The physical edge above still receives ALL inputs.
extern "C" void retained_endpoint_state_outputs(void* handle,unsigned long long revision,
    svBit* cmd_ready,svBit* out_valid,unsigned* out_context,svBit* out_last,
    svBitVecVal* out_acc,svBit* completion_valid,unsigned long long* completion_data,svBit* protocol_error) {
  try {
    (void)revision; // Explicit SV state dependency; never infer a clock here.
    const auto o=checked(handle).output(EndpointInputs{});
    *cmd_ready=o.cmd_ready;*out_valid=o.out_valid;*out_context=o.out_context;*out_last=o.out_last;
    export_packed(o.out_acc,out_acc,512);*completion_valid=o.completion_valid;*completion_data=o.completion_data;*protocol_error=o.protocol_error;
  } catch(const std::exception& e){failure(e.what());}
}
// Keep the real same-context pop/refill combinational dependency: out_ready
// affects pop, which can release busy[step_context] in the current cycle.
extern "C" svBit retained_endpoint_step_ready(void* handle,unsigned long long revision,
    unsigned ctx,svBit out_ready) {
  try {
    (void)revision;
    retained_model::require(ctx<8&&out_ready<=1,"DPI ready input widths");
    EndpointInputs x;x.step_context=ctx;x.out_ready=out_ready;
    return checked(handle).output(x).step_ready;
  } catch(const std::exception& e){failure(e.what());}
}
extern "C" void retained_endpoint_require_complete() {
  try {retained_model::require(created==8,"exactly eight full512 live endpoint objects required");}
  catch(const std::exception& e){failure(e.what());}
}
