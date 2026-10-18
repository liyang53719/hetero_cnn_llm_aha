// Read-only public facade; all transactional methods stay private.
#pragma once
#include "runtime_ram.hpp"
namespace canonical_runtime_v1 { using HostMemory = RuntimeOwner::RuntimeSession; }
