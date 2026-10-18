// Fixed no-argument production factory; new runtime has not loaded real inputs.
#pragma once
#include "runtime_ram.hpp"
namespace canonical_runtime_v1 {
inline RuntimeOwner make_canonical_runtime() { return RuntimeOwner::canonical(); }
}
