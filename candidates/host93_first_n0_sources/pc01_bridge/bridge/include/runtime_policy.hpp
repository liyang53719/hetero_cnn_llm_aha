// Fixed canonical M128 runtime classification. SOURCE candidate only.
// Region RW and Access::N0 are necessary classifications, never write authority.
// Access::Workspace must fail closed until a real generation/lease observer exists.
// Payload bytes exclude reserved tails; unnamed guards and gaps are inaccessible.
// cache_k/cache_v are views into kv, not independent allocations.
#pragma once
#include <cstdint>
#include <vector>

namespace canonical_runtime_v1 {

enum class Access { Input, N0, Qraw, Denied, Workspace };

struct Region {
    std::uint64_t base, limit;
    bool read, write;
};

struct Allocation {
    const char* name;
    std::uint64_t base, bytes, reserved_bytes;
    Access access;
};

struct Policy {
    std::uint64_t base, bytes;
    std::vector<Region> regions;
    std::vector<Allocation> allocations;
};

// No address, input, region, or permission override parameters.
// All non-input allocations except n0 remain denied in this N0-only stage.
inline Policy canonical_policy() {
    return Policy{
        4294967296ULL, 213473600ULL,
        {
            {4295032832ULL, 4483535808ULL, true, false},
            {4483535808ULL, 4507654464ULL, true, true},
            {4294967296ULL, 4295032832ULL, true, false},
            {4507654464ULL, 4508440896ULL, true, true},
        },
        {
            {"commands", 4294967296ULL, 384ULL, 384ULL, Access::Input},
            {"descriptors", 4294971392ULL, 3456ULL, 3456ULL, Access::Input},
            {"wq", 4295032896ULL, 4718592ULL, 9437184ULL, Access::Input},
            {"wk", 4304470144ULL, 786432ULL, 1572864ULL, Access::Input},
            {"wv", 4306043072ULL, 786432ULL, 1572864ULL, Access::Input},
            {"wo", 4307616000ULL, 4718592ULL, 9437184ULL, Access::Input},
            {"wg", 4317053248ULL, 27525120ULL, 55050240ULL, Access::Input},
            {"wu", 4372103552ULL, 27525120ULL, 55050240ULL, Access::Input},
            {"wd", 4427153856ULL, 27525120ULL, 55050240ULL, Access::Input},
            {"gamma0", 4482204160ULL, 6144ULL, 6144ULL, Access::Input},
            {"gamma1", 4482210368ULL, 6144ULL, 6144ULL, Access::Input},
            {"bq", 4482216576ULL, 6144ULL, 6144ULL, Access::Input},
            {"bk", 4482222784ULL, 1024ULL, 1024ULL, Access::Input},
            {"bv", 4482223872ULL, 1024ULL, 1024ULL, Access::Input},
            {"rope", 4482224960ULL, 524288ULL, 524288ULL, Access::Input},
            {"x", 4482749312ULL, 786432ULL, 786432ULL, Access::Input},
            {"n0", 4483535872ULL, 786432ULL, 786432ULL, Access::N0},
            {"qraw", 4484322368ULL, 786432ULL, 786432ULL, Access::Qraw},
            {"qr", 4485108864ULL, 786432ULL, 786432ULL, Access::Denied},
            {"q", 4485895360ULL, 786432ULL, 786432ULL, Access::Denied},
            {"kraw", 4486681856ULL, 131072ULL, 131072ULL, Access::Denied},
            {"kr", 4486812992ULL, 131072ULL, 131072ULL, Access::Denied},
            {"k", 4486944128ULL, 131072ULL, 131072ULL, Access::Denied},
            {"vraw", 4487075264ULL, 131072ULL, 131072ULL, Access::Denied},
            {"v", 4487206400ULL, 131072ULL, 131072ULL, Access::Denied},
            {"kv", 4487337536ULL, 262144ULL, 262144ULL, Access::Denied},
            // Attention intermediates are virtual and never ordinary DDR.
            {"scores", 4487599744ULL, 786432ULL, 786432ULL, Access::Denied},
            {"probabilities", 4488386240ULL, 786432ULL, 786432ULL, Access::Denied},
            {"att", 4489172736ULL, 786432ULL, 786432ULL, Access::Denied},
            {"o", 4489959232ULL, 786432ULL, 786432ULL, Access::Denied},
            {"r", 4490745728ULL, 786432ULL, 786432ULL, Access::Denied},
            {"n1", 4491532224ULL, 786432ULL, 786432ULL, Access::Denied},
            // Resident FFN gate/up are denied even though fixture virtual=false.
            {"gate", 4492318720ULL, 4587520ULL, 4587520ULL, Access::Denied},
            {"up", 4496906304ULL, 4587520ULL, 4587520ULL, Access::Denied},
            {"act", 4501493888ULL, 4587520ULL, 4587520ULL, Access::Denied},
            {"down", 4506081472ULL, 786432ULL, 786432ULL, Access::Denied},
            {"y", 4506867968ULL, 786432ULL, 786432ULL, Access::Denied},
            // Classification only; no successful workspace access path is implied.
            {"workspace", 4507654464ULL, 786432ULL, 786432ULL, Access::Workspace},
        }
    };
}

} // namespace canonical_runtime_v1
