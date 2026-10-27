// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "finite_fp32_gmp.hpp"
#include <array>
#include <memory>
#include <optional>

namespace retained_model {
// One original 512-lane endpoint, five original accumulator contexts.
// Eight such instances are mandatory in the full4096 service model.
struct EndpointInputs {
  bool rst_n=false,cmd_valid=false,step_valid=false,step_clear=false,step_last=false;
  bool command_last_tile=false,out_ready=false,completion_ready=false;
  uint8_t step_context=0;
  mpz_class command=0,a=0,b=0;
  bool seed_begin_valid=false,seed_beat_valid=false,seed_commit_valid=false,seed_abort=false,seed_ack_ready=false;
  uint8_t seed_context=0,seed_cluster=0;
  uint32_t seed_tag=0,seed_sequence=0,seed_generation=0;
  mpz_class seed_data=0;
};
struct EndpointOutputs {
  bool cmd_ready=false,step_ready=false,out_valid=false,out_last=false,completion_valid=false,protocol_error=false;
  uint8_t out_context=0;
  mpz_class out_acc=0; uint64_t completion_data=0;
  bool seed_begin_ready=false,seed_beat_ready=false,seed_commit_ready=false,seed_ack_valid=false,seed_ack_error=false,seed_reset_required=false;
  uint8_t seed_ack_context=0,arithmetic_busy=0;
  uint32_t seed_ack_tag=0,seed_ack_sequence=0,seed_ack_generation=0;
  bool arithmetic_out_valid=false;
};
class EndpointModel {
  const bool seed_enabled;
  std::array<std::array<uint32_t,512>,5> bank{};
  std::array<bool,5> bank_valid{},busy{},scheduler_valid{};
  std::array<unsigned,8> contexts{}; std::array<bool,8> lasts{};
  std::array<mpz_class,5> results{}; std::array<unsigned,5> result_flags{};
  unsigned tag_write=0,tag_read=0,tag_count=0,result_write=0,result_read=0,tokens=0;
  bool active=false,pending=false,protocol=false,reset_observed=false;
  unsigned event=0,status=0; uint32_t accepted=0,completed=0;
  struct Issue { unsigned context;bool clear;mpz_class a,b; };
  struct Computed { unsigned context;std::array<uint32_t,512> words;mpz_class packed;unsigned flags; };
  std::optional<Issue> input_stage;
  std::shared_ptr<Computed> pre_stage,mul_stage,post_stage;
  unsigned seed_context=0,seed_beats=0;
  uint32_t seed_tag=0,seed_sequence=0,seed_generation=0;
  bool seed_reserved=false,seed_ack=false,seed_ack_error=false,seed_poison=false;
  template<size_t N> static unsigned mask(const std::array<bool,N>& a) {
    unsigned m=0;for(unsigned i=0;i<N;++i)if(a[i])m|=1u<<i;return m;
  }
  static uint32_t word_at(const mpz_class& x,unsigned bit) {
    const mpz_class part=x>>bit; return uint32_t(part.get_ui()&0xfffffffful);
  }
  struct Comb {
    unsigned context;bool last,array_out,matrix_out,pop,issue,matrix_ready,cmd_ready;
    bool seed_block,seed_hold,begin_ready,beat_ready,commit_ready,begin_fire,beat_fire,commit_fire;
    bool legal_begin,legal_commit,reserve,seed_write,commit,invalidate;
    unsigned bank_context;bool fault;
  };
  Comb comb(const EndpointInputs& x) const {
    const unsigned ctx=tag_count?contexts[tag_read]:0; const bool last=tag_count&&lasts[tag_read];
    const bool array_out=tokens!=0, matrix_out=array_out&&tag_count!=0;
    const bool pop=matrix_out&&active&&x.out_ready;
    const bool block=seed_enabled&&(seed_reserved||seed_ack||seed_poison||x.seed_abort||x.seed_begin_valid||x.seed_beat_valid||x.seed_commit_valid);
    const unsigned c=x.step_context;
    const bool available=c<5&&(!busy[c]||(pop&&ctx==c));
    const bool ready=available&&tag_count<8&&tokens<8&&!block;
    const bool issue=active&&x.step_valid&&ready;
    const bool quiescent=mask(busy)==0&&!matrix_out&&!array_out&&!issue&&!input_stage&&!pre_stage&&!mul_stage&&!post_stage;
    const bool begin_ready=seed_enabled&&!seed_reserved&&!seed_ack&&!seed_poison&&!x.seed_abort&&quiescent;
    const bool beat_ready=seed_enabled&&seed_reserved&&!seed_ack&&!seed_poison&&!x.seed_abort&&quiescent;
    const bool commit_ready=beat_ready;
    const bool begin_fire=x.seed_begin_valid&&begin_ready,beat_fire=x.seed_beat_valid&&beat_ready,commit_fire=x.seed_commit_valid&&commit_ready;
    const bool identity=x.seed_context==seed_context&&x.seed_tag==seed_tag&&x.seed_sequence==seed_sequence&&x.seed_generation==seed_generation;
    const bool legal_begin=x.seed_context<5&&!x.seed_beat_valid&&!x.seed_commit_valid;
    bool finite_data=true;for(unsigned j=0;j<16;++j)finite_data&=finite(word_at(x.seed_data,j*32));
    const bool legal_beat=identity&&seed_beats<32&&x.seed_cluster==seed_beats&&finite_data&&!x.seed_commit_valid&&!x.seed_begin_valid;
    const bool legal_commit=identity&&seed_beats==32&&!x.seed_beat_valid&&!x.seed_begin_valid;
    const bool fault=seed_enabled&&(x.seed_abort||(seed_reserved&&!quiescent)||(x.seed_begin_valid&&!quiescent)||
      (begin_fire&&!legal_begin)||(beat_fire&&!legal_beat)||(commit_fire&&!legal_commit)||
      (x.seed_begin_valid&&(seed_reserved||seed_ack))||((x.seed_beat_valid||x.seed_commit_valid)&&(!seed_reserved||seed_ack)));
    const bool reserve=begin_fire&&legal_begin&&!fault;
    return {ctx,last,array_out,matrix_out,pop,issue,ready,!active&&!pending&&!block,block,seed_enabled&&(seed_reserved||seed_ack),
      begin_ready,beat_ready,commit_ready,begin_fire,beat_fire,commit_fire,legal_begin,legal_commit,reserve,
      beat_fire&&legal_beat&&!fault,commit_fire&&legal_commit&&!fault,seed_enabled&&(fault||seed_poison),reserve?unsigned(x.seed_context):seed_context,fault};
  }
  std::shared_ptr<Computed> calculate(const Issue& i) const {
    auto p=std::make_shared<Computed>();p->context=i.context;p->packed=0;p->flags=0;
    for(unsigned lane=0;lane<512;++lane) {
      const uint32_t a=(word_at(i.a,(lane/32)*16)&65535u)<<16;
      const uint32_t b=(word_at(i.b,(lane%32)*16)&65535u)<<16;
      const uint32_t old=(i.clear||!bank_valid[i.context])?0:bank[i.context][lane];
      const Rounded f=retained_model::fma(a,b,old);
      p->words[lane]=f.value;p->packed|=mpz_class(f.value)<<(lane*32);p->flags|=f.flags;
    }
    return p;
  }
public:
  explicit EndpointModel(bool seed):seed_enabled(seed){}
  static void validate(const EndpointInputs& x) {
    require(x.step_context<8&&x.seed_context<8&&x.seed_cluster<32,"endpoint scalar widths");
    auto fits=[](const mpz_class& n,unsigned width){return n>=0&&(n==0||mpz_sizeinbase(n.get_mpz_t(),2)<=width);};
    require(fits(x.command,128)&&fits(x.a,256)&&fits(x.b,512)&&fits(x.seed_data,512),"endpoint packed input widths");
  }
  void async_reset() {
    reset_observed=true;bank_valid.fill(false);busy.fill(false);scheduler_valid.fill(false);
    // Real provider accumulator storage is NOT reset, only validity.
    tag_write=tag_read=tag_count=result_write=result_read=tokens=0;
    for(unsigned i=0;i<5;++i){results[i]=0;result_flags[i]=0;}
    active=pending=protocol=false;event=status=0;accepted=completed=0;
    input_stage.reset();pre_stage.reset();mul_stage.reset();post_stage.reset();
    seed_context=seed_beats=0;seed_tag=seed_sequence=seed_generation=0;
    seed_reserved=seed_ack=seed_ack_error=seed_poison=false;
  }
  EndpointOutputs output(const EndpointInputs& x) const {
    validate(x);const Comb c=comb(x);EndpointOutputs o;
    o.cmd_ready=c.cmd_ready;o.step_ready=active&&c.matrix_ready;o.out_valid=active&&c.matrix_out;
    o.out_context=c.context;o.out_last=c.last;o.out_acc=results[result_read];o.completion_valid=pending;
    o.completion_data=(uint64_t(event)<<40)|(uint64_t(status)<<32)|(uint64_t(2)<<29);o.protocol_error=protocol||seed_poison;
    o.arithmetic_busy=mask(busy);o.arithmetic_out_valid=c.matrix_out;
    o.seed_begin_ready=c.begin_ready;o.seed_beat_ready=c.beat_ready;o.seed_commit_ready=c.commit_ready;
    o.seed_ack_valid=seed_enabled&&seed_ack;o.seed_ack_context=seed_enabled?seed_context:0;
    o.seed_ack_tag=seed_enabled?seed_tag:0;o.seed_ack_sequence=seed_enabled?seed_sequence:0;o.seed_ack_generation=seed_enabled?seed_generation:0;
    o.seed_ack_error=seed_enabled&&seed_ack_error;o.seed_reset_required=seed_enabled&&seed_poison;
    return o;
  }
  void rising_edge(const EndpointInputs& x) {
    validate(x);require(reset_observed,"explicit reset before endpoint functional execution");
    if(!x.rst_n){async_reset();return;}
    const Comb c=comb(x);const bool was_pending=pending,was_seed_ack=seed_ack,was_seed_poison=seed_poison;
    const bool pushed=bool(post_stage);
    // PRE samples OLD bank before same-edge ROUND and seed writes.
    auto next_pre=!c.seed_hold?(input_stage?calculate(*input_stage):nullptr):pre_stage;
    if(!c.seed_hold) {
      if(post_stage) {
        bank[post_stage->context]=post_stage->words;bank_valid[post_stage->context]=true;
        results[result_write]=post_stage->packed;result_flags[result_write]=post_stage->flags;result_write=(result_write+1)%5;
      }
      if(c.pop)result_read=(result_read+1)%5;
    }
    if(active&&x.step_valid&&x.step_context>=5)protocol=true;
    if(c.array_out&&tag_count==0)protocol=true;
    if(c.pop){scheduler_valid[c.context]=true;busy[c.context]=false;tag_read=(tag_read+1)&7;++completed;}
    if(c.issue){contexts[tag_write]=x.step_context;lasts[tag_write]=x.step_last;tag_write=(tag_write+1)&7;busy[x.step_context]=true;++accepted;}
    // Signed temporaries preserve fail-closed invariant checking, never unsigned wrap.
    const int next_tags=int(tag_count)+int(c.issue)-int(c.pop),next_tokens=int(tokens)+int(pushed)-int(c.pop);
    require(next_tags>=0&&next_tags<=8&&next_tokens>=0&&next_tokens<=8,"provider credit invariant");
    tag_count=unsigned(next_tags);tokens=unsigned(next_tokens);
    if(!c.seed_hold){post_stage=mul_stage;mul_stage=pre_stage;pre_stage=next_pre;}
    else{post_stage.reset();mul_stage.reset();pre_stage.reset();}
    input_stage=c.issue?std::optional<Issue>(Issue{unsigned(x.step_context),x.step_clear,x.a,x.b}):std::nullopt;
    if(seed_enabled) {
      if(c.seed_write)for(unsigned j=0;j<16;++j)bank[c.bank_context][unsigned(x.seed_cluster)*16+j]=word_at(x.seed_data,j*32);
      if(c.commit&&c.bank_context<5){bank_valid[c.bank_context]=true;scheduler_valid[c.bank_context]=true;}
      if((c.reserve||c.invalidate)&&c.bank_context<5){bank_valid[c.bank_context]=false;scheduler_valid[c.bank_context]=false;}
      if(c.begin_fire){seed_context=x.seed_context;seed_tag=x.seed_tag;seed_sequence=x.seed_sequence;seed_generation=x.seed_generation;seed_beats=0;seed_reserved=c.legal_begin;seed_ack_error=false;}
      if(c.seed_write)++seed_beats;
      if(c.commit_fire){seed_ack=true;seed_ack_error=!c.legal_commit||c.fault;}
      if(was_seed_ack&&x.seed_ack_ready){seed_ack=false;if(!was_seed_poison&&!c.fault)seed_reserved=false;}
      if(c.fault)seed_poison=true;
    }
    if(x.cmd_valid&&c.cmd_ready){event=word_at(x.command,40)&65535;const unsigned opcode=word_at(x.command,0)&255;
      if(opcode==0x20||opcode==0x21||opcode==0x23||opcode==0x24){active=true;status=0;}else{pending=true;status=4;}}
    if(c.pop&&c.last&&x.command_last_tile){active=false;pending=true;}
    if(was_pending&&x.completion_ready)pending=false;
  }
  std::array<uint64_t,6> diagnostics() const {return {accepted,completed,mask(busy),mask(scheduler_valid),mask(bank_valid),result_flags[result_read]};}
};
}
