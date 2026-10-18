// Each NEGATIVE_CASE must fail compilation, without the unit-test macro.
#include "canonical16_runtime_binding.hpp"
#include "n0_retirement_adapter.hpp"
#ifndef NEGATIVE_CASE
#define NEGATIVE_CASE 1
#endif
using namespace canonical_runtime_v1;
void forbidden(RuntimeOwner& owner) {
#if NEGATIVE_CASE == 1
    RuntimeOwner::N0RetirementAdapter* private_adapter=nullptr;(void)private_adapter;
#elif NEGATIVE_CASE == 2
    owner.stage_aw(nullptr,{4544,1,0,6,1},{0,7U<<16,0,false});
#elif NEGATIVE_CASE == 3
    auto* pointer=owner.payload_.data();(void)pointer;
#elif NEGATIVE_CASE == 4
    RuntimeOwner alternate(canonical_policy(),std::vector<InputSpec>{});(void)alternate;
#else
#error unknown negative case
#endif
    (void)owner;
}
