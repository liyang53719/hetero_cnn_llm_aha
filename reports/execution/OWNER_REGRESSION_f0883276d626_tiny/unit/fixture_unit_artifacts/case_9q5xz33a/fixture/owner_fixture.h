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
static constexpr uint64_t SCRATCH=4295317696ULL;
static constexpr uint64_t LIMIT=4295408704ULL;
static constexpr unsigned TOKENS=17,DESCRIPTORS=215,COMMANDS=21;
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
static constexpr uint64_t A_N0=4295317760ULL;
static constexpr uint64_t A_QRAW=4295322176ULL;
static constexpr uint64_t A_QR=4295326592ULL;
static constexpr uint64_t A_Q=4295331008ULL;
static constexpr uint64_t A_KRAW=4295335424ULL;
static constexpr uint64_t A_KR=4295337664ULL;
static constexpr uint64_t A_K=4295339904ULL;
static constexpr uint64_t A_VRAW=4295342144ULL;
static constexpr uint64_t A_V=4295344384ULL;
static constexpr uint64_t A_KV=4295346624ULL;
static constexpr uint64_t A_CACHE_K=4295346624ULL;
static constexpr uint64_t A_CACHE_V=4295348800ULL;
static constexpr uint64_t A_SCORES=4295351040ULL;
static constexpr uint64_t A_PROBABILITIES=4295353472ULL;
static constexpr uint64_t A_ATT=4295355904ULL;
static constexpr uint64_t A_O=4295360320ULL;
static constexpr uint64_t A_R=4295364736ULL;
static constexpr uint64_t A_N1=4295369152ULL;
static constexpr uint64_t A_GATE=4295373568ULL;
static constexpr uint64_t A_UP=4295382336ULL;
static constexpr uint64_t A_ACT=4295391104ULL;
static constexpr uint64_t A_DOWN=4295399872ULL;
static constexpr uint64_t A_Y=4295404288ULL;
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
{"x",4295313280ULL,1088ULL,true,false},
{"n0",4295317760ULL,1088ULL,false,false},
{"qraw",4295322176ULL,1088ULL,false,false},
{"qr",4295326592ULL,1088ULL,false,false},
{"q",4295331008ULL,1088ULL,false,false},
{"kraw",4295335424ULL,544ULL,false,false},
{"kr",4295337664ULL,544ULL,false,false},
{"k",4295339904ULL,544ULL,false,false},
{"vraw",4295342144ULL,544ULL,false,false},
{"v",4295344384ULL,544ULL,false,false},
{"kv",4295346624ULL,1088ULL,false,false},
{"scores",4295351040ULL,578ULL,false,true},
{"probabilities",4295353472ULL,578ULL,false,true},
{"att",4295355904ULL,1088ULL,false,false},
{"o",4295360320ULL,1088ULL,false,false},
{"r",4295364736ULL,1088ULL,false,false},
{"n1",4295369152ULL,1088ULL,false,false},
{"gate",4295373568ULL,2176ULL,false,false},
{"up",4295382336ULL,2176ULL,false,false},
{"act",4295391104ULL,2176ULL,false,false},
{"down",4295399872ULL,1088ULL,false,false},
{"y",4295404288ULL,1088ULL,false,false},
};
