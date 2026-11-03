// SPDX-License-Identifier: Apache-2.0
// Host wall-time sampling only. No DUT signal, clock, memory or arithmetic access.
#pragma once
#include <array>
#include <chrono>
#include <cstdint>
#include <ostream>
namespace host_phase_profile {
struct SteadyClock {
 static uint64_t now() noexcept {
  return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(
   std::chrono::steady_clock::now().time_since_epoch()).count());
 }
};
enum class Part : unsigned { EvalLowBefore=0, EvalRising=1, EvalFalling=2,
 ReadonlyOffer=3, MutableOffer=4, ReadonlyValidation=5, MutableValidation=6, Step=7 };
// Fixed storage: 64 program-counter buckets, 8 counters per bucket. No allocations.
// These are elapsed wall nanoseconds (including preemption), NOT CPU time or cycles.
template<class Clock=SteadyClock> class Profiler {
public:
 static constexpr unsigned Buckets=64, Parts=8, SampleLog2=10;
 static constexpr uint64_t Mask=(uint64_t(1)<<SampleLog2)-1;
 struct Counter { uint64_t calls=0, nanoseconds=0, max_nanoseconds=0; };
 struct Bucket {
  uint64_t visited=0, selected=0, completed_selected=0, failed_selected=0;
  std::array<Counter,Parts> parts{};
 };
private:
 std::array<Bucket,Buckets> buckets_{};
 bool selected_=false, completed_=false;
 unsigned pc_=0;
 uint64_t step_start_=0, invalid_pc_steps_=0, clock_regressions_=0;
 static uint64_t mix(uint64_t value) noexcept {
  // Fixed deterministic sampling, separate from simulation random state; mixes cycle and PC.
  value+=0x9e3779b97f4a7c15ULL;
  value=(value^(value>>30))*0xbf58476d1ce4e5b9ULL;
  value=(value^(value>>27))*0x94d049bb133111ebULL;
  return value^(value>>31);
 }
 void add(Part part,uint64_t start) noexcept {
  const auto end=Clock::now(); auto& c=buckets_[pc_].parts[unsigned(part)];
  const uint64_t elapsed=end>=start?end-start:0;
  if(end<start)++clock_regressions_;
  ++c.calls;c.nanoseconds+=elapsed;if(elapsed>c.max_nanoseconds)c.max_nanoseconds=elapsed;
 }
public:
 static bool choose(uint64_t active_cycle,unsigned pc) noexcept {
  return (mix(active_cycle^(uint64_t(pc)<<48))&Mask)==0;
 }
 class Span {
  Profiler* owner_; Part part_; uint64_t start_;
 public:
  Span(Profiler& p,Part part) noexcept:owner_(p.selected_?&p:nullptr),part_(part),
   start_(owner_?Clock::now():0) {}
  Span(const Span&)=delete;Span& operator=(const Span&)=delete;
  ~Span() noexcept {if(owner_)owner_->add(part_,start_);}
 };
 class StepSpan {
  Profiler* owner_;
 public:
  StepSpan(Profiler& p,bool active,uint64_t cycle,unsigned pc) noexcept:owner_(&p) {
   p.selected_=false;p.completed_=false;
   if(!active)return;
   if(pc>=Buckets){++p.invalid_pc_steps_;return;}
   p.pc_=pc;++p.buckets_[pc].visited;p.selected_=choose(cycle,pc);
   if(p.selected_){++p.buckets_[pc].selected;p.step_start_=Clock::now();}
  }
  StepSpan(const StepSpan&)=delete;StepSpan& operator=(const StepSpan&)=delete;
  void completed() noexcept {owner_->completed_=true;}
  ~StepSpan() noexcept {
   if(owner_->selected_){auto& b=owner_->buckets_[owner_->pc_];
    owner_->add(Part::Step,owner_->step_start_);
    if(owner_->completed_)++b.completed_selected;else ++b.failed_selected;
   }
   owner_->selected_=false;
  }
 };
 const Bucket& bucket(unsigned pc) const noexcept {return buckets_[pc];}
 uint64_t clock_regressions() const noexcept {return clock_regressions_;}
 void report(std::ostream& out,unsigned pc,const char* reason) const {
  if(pc>=Buckets||!buckets_[pc].visited)return;const auto& b=buckets_[pc];
  out<<"HOST_WALL_SAMPLE_V1 reason="<<reason<<" pc="<<pc
   <<" visited="<<b.visited<<" selected="<<b.selected
   <<" completed_selected="<<b.completed_selected<<" failed_selected="<<b.failed_selected
   <<" in_flight_selected="<<unsigned(selected_&&pc_==pc)
   <<" sample_log2="<<SampleLog2<<" scope=SAMPLED_HOST_ELAPSED_NS_NOT_DUT_CPU_OR_RTL_CYCLES";
  static constexpr const char* names[Parts]={"eval_low_before","eval_rising","eval_falling",
   "readonly_offer","mutable_offer","readonly_validation","mutable_validation","step"};
  for(unsigned i=0;i<Parts;++i){const auto& c=b.parts[i];out<<' '<<names[i]<<"_calls="<<c.calls
   <<' '<<names[i]<<"_ns="<<c.nanoseconds<<' '<<names[i]<<"_max_ns="<<c.max_nanoseconds;}
  out<<" invalid_pc_steps="<<invalid_pc_steps_<<" clock_regressions="<<clock_regressions_<<'\n';
 }
 void reportAll(std::ostream& out,const char* reason) const {
  for(unsigned pc=0;pc<Buckets;++pc)report(out,pc,reason);
 }
};
using HostProfiler=Profiler<>;
}
