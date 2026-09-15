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
static constexpr uint64_t SCRATCH=4295317440ULL;
static constexpr uint64_t LIMIT=4295402816ULL;
static constexpr unsigned TOKENS=16,DESCRIPTORS=215,COMMANDS=21;
static constexpr uint64_t A_WQ=4295032896ULL;
static constexpr uint64_t A_WK=4295049344ULL;
static constexpr uint64_t A_WV=4295057600ULL;
static constexpr uint64_t A_WO=4295065856ULL;
static constexpr uint64_t A_WG=4295082304ULL;
static constexpr uint64_t A_WU=4295115136ULL;
static constexpr uint64_t A_WD=4295147968ULL;
static constexpr uint64_t A_GAMMA0=4295180800ULL;
static constexpr uint64_t A_GAMMA1=4295181120ULL;
static constexpr uint64_t A_BQ=4295181440ULL;
static constexpr uint64_t A_BK=4295181760ULL;
static constexpr uint64_t A_BV=4295181952ULL;
static constexpr uint64_t A_ROPE=4295182144ULL;
static constexpr uint64_t A_X=4295313280ULL;
static constexpr uint64_t A_N0=4295317504ULL;
static constexpr uint64_t A_QRAW=4295321664ULL;
static constexpr uint64_t A_QR=4295325824ULL;
static constexpr uint64_t A_Q=4295329984ULL;
static constexpr uint64_t A_KRAW=4295334144ULL;
static constexpr uint64_t A_KR=4295336256ULL;
static constexpr uint64_t A_K=4295338368ULL;
static constexpr uint64_t A_VRAW=4295340480ULL;
static constexpr uint64_t A_V=4295342592ULL;
static constexpr uint64_t A_KV=4295344704ULL;
static constexpr uint64_t A_CACHE_K=4295344704ULL;
static constexpr uint64_t A_CACHE_V=4295346752ULL;
static constexpr uint64_t A_SCORES=4295348864ULL;
static constexpr uint64_t A_PROBABILITIES=4295350976ULL;
static constexpr uint64_t A_ATT=4295353088ULL;
static constexpr uint64_t A_O=4295357248ULL;
static constexpr uint64_t A_R=4295361408ULL;
static constexpr uint64_t A_N1=4295365568ULL;
static constexpr uint64_t A_GATE=4295369728ULL;
static constexpr uint64_t A_UP=4295377984ULL;
static constexpr uint64_t A_ACT=4295386240ULL;
static constexpr uint64_t A_DOWN=4295394496ULL;
static constexpr uint64_t A_Y=4295398656ULL;
static const TensorSpec ALLOCATIONS[]={
{"wq",4295032896ULL,4096ULL,true,false},
{"wk",4295049344ULL,2048ULL,true,false},
{"wv",4295057600ULL,2048ULL,true,false},
{"wo",4295065856ULL,4096ULL,true,false},
{"wg",4295082304ULL,8192ULL,true,false},
{"wu",4295115136ULL,8192ULL,true,false},
{"wd",4295147968ULL,8192ULL,true,false},
{"gamma0",4295180800ULL,64ULL,true,false},
{"gamma1",4295181120ULL,64ULL,true,false},
{"bq",4295181440ULL,64ULL,true,false},
{"bk",4295181760ULL,32ULL,true,false},
{"bv",4295181952ULL,32ULL,true,false},
{"rope",4295182144ULL,32768ULL,true,false},
{"x",4295313280ULL,1024ULL,true,false},
{"n0",4295317504ULL,1024ULL,false,false},
{"qraw",4295321664ULL,1024ULL,false,false},
{"qr",4295325824ULL,1024ULL,false,false},
{"q",4295329984ULL,1024ULL,false,false},
{"kraw",4295334144ULL,512ULL,false,false},
{"kr",4295336256ULL,512ULL,false,false},
{"k",4295338368ULL,512ULL,false,false},
{"vraw",4295340480ULL,512ULL,false,false},
{"v",4295342592ULL,512ULL,false,false},
{"kv",4295344704ULL,1024ULL,false,false},
{"scores",4295348864ULL,512ULL,false,true},
{"probabilities",4295350976ULL,512ULL,false,true},
{"att",4295353088ULL,1024ULL,false,false},
{"o",4295357248ULL,1024ULL,false,false},
{"r",4295361408ULL,1024ULL,false,false},
{"n1",4295365568ULL,1024ULL,false,false},
{"gate",4295369728ULL,2048ULL,false,false},
{"up",4295377984ULL,2048ULL,false,false},
{"act",4295386240ULL,2048ULL,false,false},
{"down",4295394496ULL,1024ULL,false,false},
{"y",4295398656ULL,1024ULL,false,false},
};
