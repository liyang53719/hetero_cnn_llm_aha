// Generated test fixture with the retained public ISA encoder. No RTL edits.
#pragma once
#include <cstdint>
struct TensorSpec { const char* name; uint64_t address; uint64_t words; bool readonly; bool virtualValue; };
static constexpr uint64_t BASE=4294967296ULL;
static constexpr uint64_t COMMAND_BASE=4294967296ULL;
static constexpr uint64_t COMMAND_LIMIT=4294967680ULL;
static constexpr uint64_t DESC_BASE=4294971392ULL;
static constexpr uint64_t DESC_LIMIT=4294974848ULL;
static constexpr uint64_t META_LIMIT=4295032832ULL;
static constexpr uint64_t SCRATCH=4482847680ULL;
static constexpr uint64_t LIMIT=4485691712ULL;
static constexpr unsigned TOKENS=16,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=4295032896ULL;
static constexpr uint64_t A_WK=4304470144ULL;
static constexpr uint64_t A_WV=4306043072ULL;
static constexpr uint64_t A_WO=4307616000ULL;
static constexpr uint64_t A_WG=4317053248ULL;
static constexpr uint64_t A_WU=4372103552ULL;
static constexpr uint64_t A_WD=4427153856ULL;
static constexpr uint64_t A_GAMMA0=4482204160ULL;
static constexpr uint64_t A_GAMMA1=4482210368ULL;
static constexpr uint64_t A_BQ=4482216576ULL;
static constexpr uint64_t A_BK=4482222784ULL;
static constexpr uint64_t A_BV=4482223872ULL;
static constexpr uint64_t A_ROPE=4482224960ULL;
static constexpr uint64_t A_X=4482749312ULL;
static constexpr uint64_t A_N0=4482847744ULL;
static constexpr uint64_t A_QRAW=4482946112ULL;
static constexpr uint64_t A_QR=4483044480ULL;
static constexpr uint64_t A_Q=4483142848ULL;
static constexpr uint64_t A_KRAW=4483241216ULL;
static constexpr uint64_t A_KR=4483257664ULL;
static constexpr uint64_t A_K=4483274112ULL;
static constexpr uint64_t A_VRAW=4483290560ULL;
static constexpr uint64_t A_V=4483307008ULL;
static constexpr uint64_t A_KV=4483323456ULL;
static constexpr uint64_t A_CACHE_K=4483323456ULL;
static constexpr uint64_t A_CACHE_V=4483339840ULL;
static constexpr uint64_t A_SCORES=4483356288ULL;
static constexpr uint64_t A_PROBABILITIES=4483368640ULL;
static constexpr uint64_t A_ATT=4483380992ULL;
static constexpr uint64_t A_O=4483479360ULL;
static constexpr uint64_t A_R=4483577728ULL;
static constexpr uint64_t A_N1=4483676096ULL;
static constexpr uint64_t A_GATE=4483774464ULL;
static constexpr uint64_t A_UP=4484347968ULL;
static constexpr uint64_t A_ACT=4484921472ULL;
static constexpr uint64_t A_DOWN=4485494976ULL;
static constexpr uint64_t A_Y=4485593344ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",4295032896ULL,2359296ULL,true,false},
{"wk",4304470144ULL,393216ULL,true,false},
{"wv",4306043072ULL,393216ULL,true,false},
{"wo",4307616000ULL,2359296ULL,true,false},
{"wg",4317053248ULL,13762560ULL,true,false},
{"wu",4372103552ULL,13762560ULL,true,false},
{"wd",4427153856ULL,13762560ULL,true,false},
{"gamma0",4482204160ULL,1536ULL,true,false},
{"gamma1",4482210368ULL,1536ULL,true,false},
{"bq",4482216576ULL,1536ULL,true,false},
{"bk",4482222784ULL,256ULL,true,false},
{"bv",4482223872ULL,256ULL,true,false},
{"rope",4482224960ULL,131072ULL,true,false},
{"x",4482749312ULL,24576ULL,true,false},
{"n0",4482847744ULL,24576ULL,false,false},
{"qraw",4482946112ULL,24576ULL,false,false},
{"qr",4483044480ULL,24576ULL,false,false},
{"q",4483142848ULL,24576ULL,false,false},
{"kraw",4483241216ULL,4096ULL,false,false},
{"kr",4483257664ULL,4096ULL,false,false},
{"k",4483274112ULL,4096ULL,false,false},
{"vraw",4483290560ULL,4096ULL,false,false},
{"v",4483307008ULL,4096ULL,false,false},
{"kv",4483323456ULL,8192ULL,false,false},
{"scores",4483356288ULL,3072ULL,false,true},
{"probabilities",4483368640ULL,3072ULL,false,true},
{"att",4483380992ULL,24576ULL,false,false},
{"o",4483479360ULL,24576ULL,false,false},
{"r",4483577728ULL,24576ULL,false,false},
{"n1",4483676096ULL,24576ULL,false,false},
{"gate",4483774464ULL,143360ULL,false,false},
{"up",4484347968ULL,143360ULL,false,false},
{"act",4484921472ULL,143360ULL,false,false},
{"down",4485494976ULL,24576ULL,false,false},
{"y",4485593344ULL,24576ULL,false,false},
};
