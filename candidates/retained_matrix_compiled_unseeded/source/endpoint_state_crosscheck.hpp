// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "retained_endpoint_model.hpp"
#include <array>
#include <vector>
// TEST ONLY. The bounded existing Scala A7 model state cases translated to C++.
// These checks validate the model port, NOT Chisel/provider RTL or full domains.
namespace endpoint_state_test {
using namespace retained_model;
inline uint32_t raw(unsigned n){if(!n)return 0;unsigned e=0;for(unsigned v=n;v>>=1;)++e;require(e<=23,"test integer domain");return ((e+127)<<23)|((n<<(23-e))&0x7fffff);}
template<class F> mpz_class pack(unsigned count,unsigned width,F f){mpz_class p=0;for(unsigned i=0;i<count;++i)p|=mpz_class(f(i))<<(width*i);return p;}
inline void reset(EndpointModel& m,EndpointInputs& x){x.rst_n=false;m.async_reset();x.rst_n=true;}
inline void command(EndpointModel& m,EndpointInputs& x,unsigned tag){require(m.output(x).cmd_ready,"state command ready");x.command=(mpz_class(tag)<<40)|0x220;x.cmd_valid=true;m.rising_edge(x);x.cmd_valid=false;}
inline void run(){
  // All eight independent full-capacity objects, five contexts, no zero padding.
  {
    std::array<std::unique_ptr<EndpointModel>,8> m;std::array<EndpointInputs,8> x;
    for(unsigned ep=0;ep<8;++ep){m[ep]=std::make_unique<EndpointModel>(true);reset(*m[ep],x[ep]);command(*m[ep],x[ep],100+ep);
      x[ep].a=pack(16,16,[&](unsigned i){return raw(i+1+ep)>>16;});x[ep].b=pack(32,16,[](unsigned i){return raw(i+1)>>16;});}
    for(unsigned c=0;c<5;++c)for(unsigned ep=0;ep<8;++ep){auto& a=x[ep];a.step_context=c;a.step_clear=true;a.step_valid=true;a.step_last=false;
      require(m[ep]->output(a).step_ready,"five-context ready");if(c<4)require(!m[ep]->output(a).out_valid,"original five-edge latency");m[ep]->rising_edge(a);}
    std::array<mpz_class,8> held;
    for(unsigned ep=0;ep<8;++ep){x[ep].step_valid=false;require(m[ep]->output(x[ep]).out_valid,"original fifth-edge output");held[ep]=m[ep]->output(x[ep]).out_acc;}
    for(unsigned stall=0;stall<7;++stall)for(unsigned ep=0;ep<8;++ep){m[ep]->rising_edge(x[ep]);require(m[ep]->output(x[ep]).out_acc==held[ep],"all512 held value");}
    for(unsigned c=0;c<5;++c)for(unsigned ep=0;ep<8;++ep){auto& a=x[ep];auto out=m[ep]->output(a);
      require(out.out_context==c,"original FIFO context order");
      const auto expected=pack(512,32,[&](unsigned lane){return raw((lane/32+1+ep)*(lane%32+1));});
      require(out.out_acc==expected,"full512 first arithmetic result");
      a.out_ready=true;a.step_context=c;a.step_clear=false;a.step_valid=true;require(m[ep]->output(a).step_ready,"same-context retire/refill");m[ep]->rising_edge(a);}
    for(auto& a:x)a.step_valid=false;
    for(unsigned c=0;c<5;++c)for(unsigned ep=0;ep<8;++ep){const auto out=m[ep]->output(x[ep]);require(out.out_valid&&out.out_context==c,"second FIFO order");
      const auto expected=pack(512,32,[&](unsigned lane){return raw(2*(lane/32+1+ep)*(lane%32+1));});
      require(out.out_acc==expected&&m[ep]->diagnostics()[5]==0,"full512 retained accumulation and flags");m[ep]->rising_edge(x[ep]);}
    for(unsigned ep=0;ep<8;++ep)require(m[ep]->diagnostics()==std::array<uint64_t,6>{10,10,0,31,31,0}&&!m[ep]->output(x[ep]).out_valid,"all-context complete");
    reset(*m[0],x[0]);require(m[0]->diagnostics()[4]==0,"independent endpoint reset");
    for(unsigned ep=1;ep<8;++ep)require(m[ep]->diagnostics()[4]==31,"other seven banks retained");
  }
  {
    EndpointModel m(true);EndpointInputs x;reset(m,x);x.seed_context=3;x.seed_tag=9;x.seed_sequence=7;x.seed_generation=11;
    x.seed_begin_valid=true;require(m.output(x).seed_begin_ready,"seed begin ready");m.rising_edge(x);x.seed_begin_valid=false;
    for(unsigned cluster=0;cluster<32;++cluster){x.seed_cluster=cluster;x.seed_data=pack(16,32,[&](unsigned j){return raw(cluster*16+j+1);});
      x.seed_beat_valid=true;require(m.output(x).seed_beat_ready,"actual seed write ready");m.rising_edge(x);require(m.diagnostics()[4]==0,"seed not valid before commit");}
    x.seed_beat_valid=false;x.seed_commit_valid=true;require(!m.output(x).seed_ack_valid,"no early ACK");m.rising_edge(x);x.seed_commit_valid=false;
    require(m.output(x).seed_ack_valid&&m.diagnostics()[4]==8,"registered commit ACK/bank valid");
    x.seed_ack_ready=true;m.rising_edge(x);x.seed_ack_ready=false;command(m,x,900);
    x.step_context=3;x.step_valid=true;x.a=pack(16,16,[](unsigned){return 0x3f80u;});x.b=pack(32,16,[](unsigned){return 0x3f80u;});
    x.step_clear=false;x.step_last=true;x.command_last_tile=true;m.rising_edge(x);x.step_valid=false;
    for(unsigned i=0;i<4;++i)m.rising_edge(x);
    require(m.output(x).out_acc==pack(512,32,[](unsigned i){return raw(i+2);}),"seeded full512 FP32 arithmetic result");
    x.out_ready=true;m.rising_edge(x);require(m.output(x).completion_valid&&m.output(x).completion_data==((uint64_t(900)<<40)|(uint64_t(2)<<29)),"original command completion");
    x.completion_ready=true;m.rising_edge(x);
    x.seed_begin_valid=true;m.rising_edge(x);x.seed_begin_valid=false;
    for(unsigned c=0;c<32;++c){x.seed_cluster=c;x.seed_beat_valid=true;m.rising_edge(x);}
    x.seed_beat_valid=false;x.seed_commit_valid=true;m.rising_edge(x);x.seed_commit_valid=false;
    require(!m.output(x).seed_ack_error,"held success ACK");x.seed_abort=true;m.rising_edge(x);
    const auto o=m.output(x);require(o.seed_ack_valid&&!o.seed_ack_error&&o.seed_reset_required&&m.diagnostics()[4]==0&&!o.cmd_ready,"late poison preserves ACK and invalidates bank");
  }
  for(unsigned which=0;which<3;++which){EndpointModel m(true);EndpointInputs x;reset(m,x);x.seed_context=2;x.seed_begin_valid=true;m.rising_edge(x);x.seed_begin_valid=false;
    if(which==0){x.seed_cluster=1;x.seed_beat_valid=true;}else if(which==1){x.seed_data=0x7f800000u;x.seed_beat_valid=true;}else{x.seed_commit_valid=true;}
    m.rising_edge(x);require(m.output(x).seed_reset_required&&!m.output(x).out_valid&&m.diagnostics()[4]==0,"bad seed order/domain/early commit rejection");}
  {EndpointModel m(false);EndpointInputs x;reset(m,x);x.command=(mpz_class(42)<<40)|0xff;x.cmd_valid=true;m.rising_edge(x);
    const auto o=m.output(x);require(o.completion_valid&&o.completion_data==((uint64_t(42)<<40)|(uint64_t(4)<<32)|(uint64_t(2)<<29))&&!o.step_ready&&m.diagnostics()[0]==0,"invalid opcode without invented arithmetic");}
}
}
